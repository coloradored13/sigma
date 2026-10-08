"""Behavioral counterexamples for resource binding, isolation, and atomicity."""

import multiprocessing
import sqlite3
import stat
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from sigma_public_core import Scope, Transition, WorkflowDefinition, WorkflowError, WorkflowStore


def definition():
    return WorkflowDefinition(
        "pending",
        {
            "approve": Transition({"pending"}, "approved"),
            "ship": Transition({"approved"}, "shipped"),
            "refund": Transition({"shipped"}, "refunded", lambda data: data["total"] < 500),
            "inspect": Transition({"pending"}, "pending"),
        },
    )


@pytest.fixture
def store(tmp_path):
    return WorkflowStore(tmp_path / "orders.db", Scope("synthetic", "orders", "reviewer"), definition())


def shipped(store, entity_id, total):
    store.create(entity_id, {"total": total})
    store.transition(entity_id, "approve", 0, f"approve-{entity_id}")
    store.transition(entity_id, "ship", 1, f"ship-{entity_id}")


def error_code(code):
    return pytest.raises(WorkflowError, match=WorkflowError._MESSAGES[code])


def test_lateral_action_uses_target_state(store):
    shipped(store, "order-A", 25)
    store.create("order-B", {"total": 999.99})
    assert store.allowed_actions("order-A") == ["refund"]
    result = store.transition("order-B", "approve", 0, "approve-B")
    assert result.to_state == "approved"
    store.create("order-C", {"total": 10})
    assert "approve" in store.allowed_actions("order-C")
    with error_code("action_not_allowed"):
        store.transition("order-A", "approve", 2, "wrong-target")
    assert store.get("order-A").state == "shipped"


def test_guard_uses_actual_target_and_payload_cannot_override_data(store):
    shipped(store, "cheap", 25)
    shipped(store, "expensive", 999.99)
    assert "refund" in store.allowed_actions("cheap")
    with error_code("guard_rejected"):
        store.transition("expensive", "refund", 2, "refund", {"total": 25})
    assert store.get("expensive").state == "shipped"
    assert len(store.events("expensive")) == 2


@pytest.mark.parametrize("changed", [{"project_id": "other"}, {"tenant_id": "other"}])
def test_other_scopes_cannot_discover_or_mutate_entities(store, changed):
    store.create("private-order", {"marker": "SYNTHETIC-PRIVATE-CANARY"})
    other = WorkflowStore(store.path, replace(store.scope, **changed), definition())
    for entity_id in ("private-order", "does-not-exist"):
        for operation in (
            lambda: other.get(entity_id),
            lambda: other.allowed_actions(entity_id),
            lambda: other.events(entity_id),
            lambda: other.transition(entity_id, "approve", 0, "key"),
        ):
            with error_code("not_found") as caught:
                operation()
            assert "SYNTHETIC" not in str(caught.value)
    other.create("private-order", {"public": True})
    other.transition("private-order", "approve", 0, "same-key")
    store.transition("private-order", "approve", 0, "same-key")
    assert store.get("private-order").data == {"marker": "SYNTHETIC-PRIVATE-CANARY"}


def test_retry_after_restart_returns_original_receipt_even_after_later_transition(store):
    store.create("order", {})
    receipt = store.transition("order", "approve", 0, "approve", {"reason": "synthetic"})
    store.transition("order", "ship", 1, "ship")
    restarted = WorkflowStore(store.path, store.scope, definition())
    assert restarted.transition("order", "approve", 0, "approve", {"reason": "synthetic"}) == receipt
    assert restarted.get("order").version == 2
    assert len(restarted.events("order")) == 2


@pytest.mark.parametrize(
    "change",
    [
        {"entity_id": "another"},
        {"action": "ship"},
        {"expected_version": 1},
        {"payload": {"reason": "different"}},
    ],
)
def test_idempotency_key_binds_entire_request(store, change):
    store.create("order", {})
    request = dict(entity_id="order", action="approve", expected_version=0, idempotency_key="key", payload={})
    store.transition(**request)
    with error_code("idempotency_conflict"):
        store.transition(**(request | change))
    assert len(store.events("order")) == 1


def test_idempotency_key_binds_actor(store):
    store.create("order", {})
    store.transition("order", "approve", 0, "key")
    other_actor = WorkflowStore(store.path, replace(store.scope, actor_id="other"), definition())
    with error_code("idempotency_conflict"):
        other_actor.transition("order", "approve", 0, "key")


def test_discovery_is_advisory_and_stale_version_never_transitions(store):
    store.create("order", {})
    assert "approve" in store.allowed_actions("order")
    store.transition("order", "inspect", 0, "inspected")
    with error_code("stale_version"):
        store.transition("order", "approve", 0, "approve")
    assert store.get("order").state == "pending"


def _competing_transition(args):
    path, index, same_key = args
    worker = WorkflowStore(path, Scope("synthetic", "orders", "reviewer"), definition())
    try:
        return worker.transition("order", "inspect", 0, "shared" if same_key else f"key-{index}").id
    except WorkflowError as error:
        return error.code


@pytest.mark.parametrize("same_key", [True, False])
@pytest.mark.parametrize("mode", ["threads", "processes"])
def test_concurrent_transitions_commit_once(store, same_key, mode):
    store.create("order", {})
    requests = [(str(store.path), index, same_key) for index in range(10)]
    if mode == "threads":
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(_competing_transition, requests))
    else:
        with multiprocessing.get_context("spawn").Pool(4) as executor:
            results = executor.map(_competing_transition, requests)
    if same_key:
        assert len(set(results)) == 1
        assert results[0] != "storage_error"
    else:
        assert results.count("stale_version") == 9
    assert store.get("order").version == 1
    assert len(store.events("order")) == 1


def test_concurrent_distinct_creates_survive(store):
    def create(index):
        worker = WorkflowStore(store.path, store.scope, definition())
        return worker.create(f"order-{index}", {"index": index})

    with ThreadPoolExecutor(max_workers=10) as executor:
        entities = list(executor.map(create, range(30)))
    assert len(entities) == 30
    assert [store.get(f"order-{i}").data["index"] for i in range(30)] == list(range(30))


def test_receipt_write_failure_rolls_back_state_and_allows_retry(store):
    store.create("order", {})
    with sqlite3.connect(store.path) as db:
        db.execute("""
            CREATE TRIGGER fail_receipt BEFORE INSERT ON workflow_receipts
            BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END
        """)
    with error_code("storage_error"):
        store.transition("order", "approve", 0, "approve")
    assert store.get("order").state == "pending"
    assert store.get("order").version == 0
    assert store.events("order") == []
    with sqlite3.connect(store.path) as db:
        db.execute("DROP TRIGGER fail_receipt")
    assert store.transition("order", "approve", 0, "approve").version == 1


def test_guard_exception_has_no_data_in_error_and_no_committed_changes(store):
    def guard(data):
        raise RuntimeError(data["marker"])

    failing = WorkflowStore(
        store.path,
        store.scope,
        WorkflowDefinition("pending", {"approve": Transition({"pending"}, "approved", guard)}),
    )
    failing.create("order", {"marker": "SYNTHETIC-PRIVATE-CANARY"})
    with error_code("guard_error") as caught:
        failing.transition("order", "approve", 0, "key")
    assert "CANARY" not in str(caught.value)
    assert failing.get("order").version == 0
    assert failing.events("order") == []


@pytest.mark.parametrize("data", [{"v": float("nan")}, {"v": float("inf")}, {1: "value"}, {"v": object()}])
def test_non_json_data_rejected_without_creating_entity(store, data):
    with error_code("invalid_request"):
        store.create("order", data)
    with error_code("not_found"):
        store.get("order")


def test_non_json_payload_rejected_without_state_change(store):
    store.create("order", {})
    with error_code("invalid_request"):
        store.transition("order", "approve", 0, "key", {"v": float("nan")})
    assert store.get("order").version == 0


@pytest.mark.parametrize("version", [True, -1, 0.0, "0"])
def test_invalid_versions_rejected(store, version):
    store.create("order", {})
    with error_code("invalid_request"):
        store.transition("order", "approve", version, "key")


def test_mutable_return_values_never_change_persisted_data(store):
    entity = store.create("order", {"nested": {"value": "original"}})
    entity.data["nested"]["value"] = "changed"
    assert store.get("order").data["nested"]["value"] == "original"
    receipt = store.transition("order", "approve", 0, "key", {"nested": {"value": "original"}})
    receipt.payload["nested"]["value"] = "changed"
    assert store.events("order")[0].payload["nested"]["value"] == "original"


def test_failed_attempt_does_not_reserve_idempotency_key(store):
    store.create("order", {})
    with error_code("action_not_allowed"):
        store.transition("order", "ship", 0, "key")
    assert store.transition("order", "approve", 0, "key").to_state == "approved"


def test_new_database_has_owner_only_permissions(store):
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_database_symlink_is_rejected(store, tmp_path):
    link = tmp_path / "linked.db"
    link.symlink_to(store.path)
    with error_code("storage_error"):
        WorkflowStore(link, store.scope, definition())


@pytest.mark.parametrize("result", [1, "true", None, {"allowed": True}])
def test_ambiguous_guard_result_fails_closed(store, result):
    guarded = WorkflowStore(
        store.path,
        store.scope,
        WorkflowDefinition("pending", {"approve": Transition({"pending"}, "approved", lambda data: result)}),
    )
    guarded.create("order", {})
    with error_code("guard_error"):
        guarded.transition("order", "approve", 0, "key")
    assert guarded.get("order").version == 0


def test_guard_cannot_modify_persisted_resource_data(store):
    def mutation(data):
        data["total"] = 0
        return True

    guarded = WorkflowStore(
        store.path,
        store.scope,
        WorkflowDefinition("pending", {"approve": Transition({"pending"}, "approved", mutation)}),
    )
    guarded.create("order", {"total": 999.99})
    guarded.transition("order", "approve", 0, "key")
    assert guarded.get("order").data == {"total": 999.99}
