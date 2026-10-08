"""Synthetic privacy and durability regressions for the independent memory store."""

import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

import pytest
from sigma_public_core.scope import Scope
from sigma_public_memory import (
    MemoryConflict,
    MemoryNotFound,
    MemoryStore,
    MemoryStoreError,
    MemoryValidationError,
)
from sigma_public_memory.server import create_server


@pytest.fixture
def store(tmp_path):
    return MemoryStore(tmp_path / "project.sqlite3", Scope("tenant", "project", "host-actor"))


def test_roundtrip_sources_and_restart(store):
    first = store.add("Synthetic order research", ("fixture:one", "fixture:one"))
    assert first.version == 1
    assert first.source_ids == ("fixture:one",)
    assert first.status == "active"
    assert first.created_by == first.updated_by == "host-actor"
    assert MemoryStore(store.path, store.scope).get(first.id) == first
    assert store.search("ORDER") == [first]


def test_new_database_is_owner_only(store):
    assert os.stat(store.path).st_mode & 0o777 == 0o600


def test_scope_canaries_and_unknown_errors_are_indistinguishable(tmp_path):
    path = tmp_path / "shared.sqlite3"
    public = MemoryStore(path, Scope("tenant", "public", "actor"))
    personal = MemoryStore(path, Scope("tenant", "personal", "actor"))
    unrelated = MemoryStore(path, Scope("other-tenant", "personal", "actor"))
    secret = personal.add("SYNTHETIC_PERSONAL_CANARY", ("private-source-marker",))
    public.add("SYNTHETIC_PUBLIC_FIXTURE")
    for restricted in (public, unrelated):
        assert restricted.search("SYNTHETIC_PERSONAL_CANARY") == []
        with pytest.raises(MemoryNotFound) as denied:
            restricted.get(secret.id)
        with pytest.raises(MemoryNotFound) as absent:
            restricted.get("unknown")
        assert str(denied.value) == str(absent.value)
        assert "CANARY" not in str(denied.value)
        for operation in (
            lambda: restricted.revise(secret.id, 1, "attempt"),
            lambda: restricted.retract(secret.id, 1),
            lambda: restricted.delete(secret.id, 1),
        ):
            with pytest.raises(MemoryNotFound):
                operation()
    assert personal.get(secret.id) == secret


def test_scope_is_opaque_not_a_path(tmp_path):
    store = MemoryStore(tmp_path / "explicit.sqlite3", Scope("../tenant", "../../elsewhere", "/actor"))
    record = store.add("Path-looking scope remains an SQL value")
    assert store.get(record.id) == record
    assert {path.name for path in tmp_path.iterdir()} <= {
        "explicit.sqlite3",
        "explicit.sqlite3-wal",
        "explicit.sqlite3-shm",
    }
    other = MemoryStore(store.path, Scope("../tenant", "elsewhere", "/actor"))
    with pytest.raises(MemoryNotFound):
        other.get(record.id)


def test_no_environment_or_legacy_discovery(tmp_path, monkeypatch):
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    marker = legacy / "memory.json"
    marker.write_text('{"content":"SYNTHETIC_LEGACY_CANARY"}')
    monkeypatch.setenv("SIGMA_MEM_PATH", str(marker))
    monkeypatch.setenv("SIGMA_MEMORY_DIR", str(legacy))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "SYNTHETIC_UNUSED_CREDENTIAL")
    store = MemoryStore(tmp_path / "explicit.sqlite3", Scope("t", "p", "a"))
    assert store.search("") == []
    assert marker.read_text() == '{"content":"SYNTHETIC_LEGACY_CANARY"}'


def test_symlink_database_is_rejected_without_following(tmp_path):
    target = tmp_path / "existing"
    target.write_text("SYNTHETIC_UNRELATED_FILE")
    link = tmp_path / "db-link"
    link.symlink_to(target)
    with pytest.raises(MemoryStoreError):
        MemoryStore(link, Scope("t", "p", "a"))
    assert target.read_text() == "SYNTHETIC_UNRELATED_FILE"


def test_concurrent_adds_survive_across_instances(store):
    writers = [MemoryStore(store.path, store.scope) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as executor:
        records = list(executor.map(lambda i: writers[i % 8].add(f"Synthetic finding {i}"), range(64)))
    assert {record.id for record in store.search("Synthetic finding", limit=100)} == {
        record.id for record in records
    }
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT count(*) FROM sp_memory_events").fetchone()[0] == 64


def test_concurrent_revision_allows_one_winner(store):
    record = store.add("Before")

    def revise(index):
        try:
            return store.revise(record.id, 1, f"Replacement {index}")
        except MemoryConflict:
            return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(revise, range(24)))
    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    assert store.get(record.id) == winners[0]
    assert winners[0].version == 2


def test_versions_source_replacement_and_actor_receipts(store):
    record = store.add("Initial hypothesis", ("fixture:old",))
    next_actor = MemoryStore(store.path, Scope("tenant", "project", "second-actor"))
    revised = next_actor.revise(record.id, 1, "Corrected hypothesis", ("fixture:new",))
    assert revised.version == 2
    assert revised.source_ids == ("fixture:new",)
    assert revised.created_by == "host-actor"
    assert revised.updated_by == "second-actor"
    for operation in (
        lambda: next_actor.revise(record.id, 1, "stale"),
        lambda: next_actor.retract(record.id, 1),
        lambda: next_actor.delete(record.id, 1),
    ):
        with pytest.raises(MemoryConflict):
            operation()
    with sqlite3.connect(store.path) as connection:
        events = connection.execute("SELECT action, version, actor_id FROM sp_memory_events").fetchall()
    assert events == [("add", 1, "host-actor"), ("revise", 2, "second-actor")]


def test_receipt_failure_rolls_back_record_change(store, monkeypatch):
    record = store.add("Original")

    def fail_receipt(*args):
        raise MemoryStoreError("Synthetic transaction failure")

    monkeypatch.setattr(store, "_receipt", fail_receipt)
    with pytest.raises(MemoryStoreError):
        store.revise(record.id, 1, "Must not persist")
    assert store.get(record.id) == record
    with pytest.raises(MemoryStoreError):
        store.add("Must not persist either")
    assert store.search("") == [record]


def test_expiry_and_retraction_hide_reads_but_allow_deletion(store):
    expired = store.add("Expired synthetic note", expires_at=time.time() - 1)
    active = store.add("Visible synthetic note", expires_at=time.time() + 3600)
    retracted = store.retract(active.id, 1)
    assert retracted.version == 2
    assert retracted.status == "retracted"
    for record in (expired, retracted):
        with pytest.raises(MemoryNotFound):
            store.get(record.id)
        with pytest.raises(MemoryNotFound):
            store.revise(record.id, record.version, "No revival")
    assert store.search("synthetic") == []
    assert store.delete(expired.id, 1).status == "deleted"
    assert store.delete(retracted.id, 2).status == "deleted"


@pytest.mark.parametrize("expired", [False, True])
def test_retraction_returns_metadata_without_revealing_hidden_content(store, expired):
    record = store.add(
        "SYNTHETIC_RETRACTED_PRIVATE_CANARY",
        ("SYNTHETIC_RETRACTED_SOURCE_CANARY",),
        expires_at=time.time() - 1 if expired else None,
    )
    retracted = store.retract(record.id, 1)
    assert retracted.status == "retracted"
    assert retracted.version == 2
    assert retracted.content is None
    assert retracted.source_ids == ()
    assert "CANARY" not in json.dumps(asdict(retracted))
    with pytest.raises(MemoryNotFound):
        store.get(record.id)


def test_delete_clears_logical_content_and_sources_after_restart(store):
    record = store.add("SYNTHETIC_DELETION_CANARY", ("SYNTHETIC_SOURCE_CANARY",))
    deleted = store.delete(record.id, 1)
    assert deleted.content is None
    assert deleted.source_ids == ()
    assert deleted.version == 2
    reopened = MemoryStore(store.path, store.scope)
    assert reopened.search("CANARY") == []
    with pytest.raises(MemoryNotFound):
        reopened.get(record.id)
    with sqlite3.connect(store.path) as connection:
        rows = connection.execute("SELECT * FROM sp_memory_records").fetchall()
        receipts = connection.execute("SELECT * FROM sp_memory_events").fetchall()
    assert "SYNTHETIC_DELETION_CANARY" not in repr(rows + receipts)
    assert "SYNTHETIC_SOURCE_CANARY" not in repr(rows + receipts)


def test_repetition_never_promotes_truth(store):
    for _ in range(3):
        record = store.add("Repeated synthetic assertion", ("same-source",))
        assert record.status == "active"
        assert set(asdict(record)) == {
            "id",
            "content",
            "version",
            "source_ids",
            "status",
            "expires_at",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        }
    assert len(store.search("Repeated")) == 3


def test_search_treats_wildcards_and_sql_as_literal(store):
    literal = store.add("A literal %_ marker")
    store.add("Ordinary text")
    assert store.search("%_") == [literal]
    assert store.search("' OR 1=1 --") == []
    assert len(store.search("", limit=1)) == 1


@pytest.mark.parametrize("expiry", [True, float("nan"), float("inf"), "SYNTHETIC_PRIVATE_INPUT"])
def test_invalid_expiry_does_not_echo_input(store, expiry):
    with pytest.raises(MemoryValidationError) as error:
        store.add("synthetic", expires_at=expiry)
    assert "SYNTHETIC_PRIVATE_INPUT" not in str(error.value)


@pytest.mark.parametrize("limit", [0, -1, 101, True, "SYNTHETIC_PRIVATE_INPUT"])
def test_search_limits_are_bounded(store, limit):
    with pytest.raises(MemoryValidationError):
        store.search("", limit=limit)


def test_invalid_content_and_version_are_generic(store):
    for content in (None, "", "   ", "\ud800"):
        with pytest.raises(MemoryValidationError):
            store.add(content)
    record = store.add("valid")
    for version in (True, 0, -1, 1.5):
        with pytest.raises(MemoryValidationError):
            store.delete(record.id, version)


@pytest.mark.asyncio
async def test_mcp_catalog_and_validation_do_not_expose_scope_or_input(store):
    server = create_server(store)
    catalog = await server.list_tools()
    assert {tool.name for tool in catalog} == {
        "memory_add",
        "memory_get",
        "memory_search",
        "memory_revise",
        "memory_retract",
        "memory_delete",
    }
    for tool in catalog:
        assert tool.outputSchema is not None
        assert not {"scope", "tenant", "project", "actor", "db", "path"} & set(tool.inputSchema["properties"])
    # This fails in SDK validation before our function can run. The SDK's normal
    # exception would reflect input_value, so the server boundary must redact it.
    result = await server.call_tool("memory_add", {"content": {"SYNTHETIC_PRIVATE_INPUT": "marker"}})
    assert result.isError
    assert "SYNTHETIC_PRIVATE_INPUT" not in result.model_dump_json()
    forbidden = await server.call_tool("memory_search", {"query": "", "project": "personal"})
    assert forbidden.isError
    assert store.search("") == []


@pytest.mark.asyncio
async def test_mcp_denied_and_stale_codes_are_fixed(store):
    record = store.add("Synthetic MCP record")
    server = create_server(store)
    missing = await server.call_tool("memory_get", {"memory_id": "SYNTHETIC_PRIVATE_INPUT"})
    assert missing.structuredContent == {"error": "memory_unavailable"}
    stale = await server.call_tool("memory_delete", {"memory_id": record.id, "expected_version": 2})
    assert stale.structuredContent == {"error": "version_conflict"}
    assert "SYNTHETIC_PRIVATE_INPUT" not in json.dumps(missing.model_dump())


@pytest.mark.asyncio
async def test_mcp_rejects_coercible_arguments_before_mutation(store):
    record = store.add("Synthetic unchanged record")
    server = create_server(store)
    for version in (True, "1"):
        result = await server.call_tool(
            "memory_delete", {"memory_id": record.id, "expected_version": version}
        )
        assert result.isError
        assert result.structuredContent == {"error": "invalid_request"}
    assert store.get(record.id) == record


@pytest.mark.asyncio
async def test_mcp_unexpected_exceptions_do_not_expose_content(store, monkeypatch):
    def synthetic_failure(*args):
        raise RuntimeError("SYNTHETIC_PRIVATE_EXCEPTION_CONTENT")

    monkeypatch.setattr(store, "search", synthetic_failure)
    server = create_server(store)
    result = await server.call_tool("memory_search", {"query": ""})
    assert result.isError
    assert "SYNTHETIC_PRIVATE_EXCEPTION_CONTENT" not in result.model_dump_json()
