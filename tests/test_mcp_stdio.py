"""Exercise installed MCP entry points over stdio, with synthetic data only."""

import json
import sys
from contextlib import asynccontextmanager

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PRIVATE_MARKER = "SYNTHETIC_MCP_PRIVATE_INPUT_MARKER"
NETWORK_MARKER = "SYNTHETIC_UNEXPECTED_NETWORK_ATTEMPT"

# Run the real module/CLI after forbidding DNS and Internet socket connections.
# Stdio and event-loop Unix socket pairs remain available. No credentials or
# filesystem configuration from the invoking developer are copied into fixtures.
OFFLINE_LAUNCHER = """
import runpy
import socket
import sys

def deny_network(*args, **kwargs):
    sys.stderr.write('SYNTHETIC_UNEXPECTED_NETWORK_ATTEMPT\\n')
    raise RuntimeError('Network is disabled for this integration test')

original_socket = socket.socket
class OfflineSocket(original_socket):
    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            return deny_network()
        return super().connect(address)

    def connect_ex(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            return deny_network()
        return super().connect_ex(address)

socket.socket = OfflineSocket
socket.getaddrinfo = deny_network
socket.gethostbyname = deny_network
socket.gethostbyname_ex = deny_network
socket.create_connection = deny_network
module = sys.argv.pop(1)
sys.argv[0] = module
runpy.run_module(module, run_name='__main__')
"""


@asynccontextmanager
async def server_session(tmp_path, module, arguments=(), log_name="server.stderr"):
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-I", "-c", OFFLINE_LAUNCHER, module, *arguments],
        cwd=str(tmp_path),
        env={
            "SIGMA_PUBLIC_VERIFY_TOKEN": "synthetic-unused-credential",
            "OPENAI_API_KEY": "synthetic-unused-ambient-credential",
        },
    )
    with (tmp_path / log_name).open("w+") as errors:
        with anyio.fail_after(20):
            async with stdio_client(parameters, errlog=errors) as (read, write):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    yield session, initialized
        errors.seek(0)
        log = errors.read()
        assert PRIVATE_MARKER not in log
        assert NETWORK_MARKER not in log
        assert "synthetic-unused-credential" not in log
        assert "synthetic-unused-ambient-credential" not in log


def memory_arguments(tmp_path, *, tenant="synthetic-tenant", project="synthetic-project"):
    return [
        "--db",
        str(tmp_path / "memory.sqlite3"),
        "--tenant",
        tenant,
        "--project",
        project,
        "--actor",
        "synthetic-host",
    ]


def result_data(result):
    assert not result.isError, result.model_dump_json()
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads(next(block.text for block in result.content if block.type == "text"))


def assert_private_error(result):
    assert result.isError
    assert PRIVATE_MARKER not in result.model_dump_json()


@pytest.mark.asyncio
async def test_memory_actual_stdio_lifecycle_and_restart(tmp_path):
    arguments = memory_arguments(tmp_path)
    async with server_session(tmp_path, "sigma_public_memory.server", arguments) as (session, initialized):
        assert initialized.serverInfo.name == "sigma-public-memory"
        catalog = (await session.list_tools()).tools
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
            assert not {"scope", "tenant", "project", "actor", "path", "db"} & set(
                tool.inputSchema["properties"]
            )
        added = result_data(
            await session.call_tool(
                "memory_add",
                {
                    "content": "Synthetic order observation",
                    "source_ids": ["fixture:order-1"],
                },
            )
        )
        found = result_data(await session.call_tool("memory_get", {"memory_id": added["id"]}))
        assert found == added
        revised = result_data(
            await session.call_tool(
                "memory_revise",
                {
                    "memory_id": added["id"],
                    "expected_version": 1,
                    "content": "Revised synthetic order observation",
                    "source_ids": ["fixture:order-2"],
                },
            )
        )
        assert revised["version"] == 2
        assert revised["source_ids"] == ["fixture:order-2"]
        assert result_data(await session.call_tool("memory_search", {"query": "Revised"}))["records"] == [
            revised
        ]

    async with server_session(tmp_path, "sigma_public_memory.server", arguments, "restart.stderr") as (
        session,
        _,
    ):
        assert result_data(await session.call_tool("memory_get", {"memory_id": added["id"]})) == revised
        retracted = result_data(
            await session.call_tool(
                "memory_retract",
                {
                    "memory_id": added["id"],
                    "expected_version": 2,
                },
            )
        )
        assert retracted["status"] == "retracted"
        assert retracted["content"] is None
        assert retracted["source_ids"] == []
        assert_private_error(await session.call_tool("memory_get", {"memory_id": added["id"]}))
        assert result_data(await session.call_tool("memory_search", {"query": ""}))["records"] == []
        deleted = result_data(
            await session.call_tool(
                "memory_delete",
                {
                    "memory_id": added["id"],
                    "expected_version": 3,
                },
            )
        )
        assert deleted["status"] == "deleted"
        assert deleted["content"] is None
        assert deleted["source_ids"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("other_scope", [{"project": "other-project"}, {"tenant": "other-tenant"}])
async def test_memory_actual_stdio_cannot_read_or_mutate_another_scope(tmp_path, other_scope):
    async with server_session(tmp_path, "sigma_public_memory.server", memory_arguments(tmp_path)) as (
        session,
        _,
    ):
        record = result_data(await session.call_tool("memory_add", {"content": "Synthetic scoped canary"}))

    async with server_session(
        tmp_path,
        "sigma_public_memory.server",
        memory_arguments(tmp_path, **other_scope),
        "other-scope.stderr",
    ) as (session, _):
        errors = []
        for tool, arguments in (
            ("memory_get", {"memory_id": record["id"]}),
            ("memory_get", {"memory_id": "unknown"}),
            ("memory_revise", {"memory_id": record["id"], "expected_version": 1, "content": "attempt"}),
            ("memory_retract", {"memory_id": record["id"], "expected_version": 1}),
            ("memory_delete", {"memory_id": record["id"], "expected_version": 1}),
        ):
            denied = await session.call_tool(tool, arguments)
            assert_private_error(denied)
            assert "Synthetic scoped canary" not in denied.model_dump_json()
            errors.append(denied.structuredContent)
        assert errors == [{"error": "memory_unavailable"}] * len(errors)
        assert result_data(await session.call_tool("memory_search", {"query": ""}))["records"] == []


@pytest.mark.asyncio
async def test_memory_actual_stdio_rejects_invalid_arguments_without_reflection(tmp_path):
    async with server_session(tmp_path, "sigma_public_memory.server", memory_arguments(tmp_path)) as (
        session,
        _,
    ):
        for tool, arguments in (
            ("memory_add", {"content": {PRIVATE_MARKER: 1}}),
            ("memory_add", {"content": "synthetic", "scope": PRIVATE_MARKER}),
            ("memory_search", {"query": "", "project": PRIVATE_MARKER}),
            ("memory_get", {"memory_id": PRIVATE_MARKER}),
        ):
            assert_private_error(await session.call_tool(tool, arguments))
        record = result_data(await session.call_tool("memory_add", {"content": "Synthetic stable record"}))
        for wrong_version in (True, "1"):
            assert_private_error(
                await session.call_tool(
                    "memory_delete",
                    {
                        "memory_id": record["id"],
                        "expected_version": wrong_version,
                    },
                )
            )
        assert result_data(await session.call_tool("memory_get", {"memory_id": record["id"]})) == record


@pytest.mark.asyncio
async def test_verifier_actual_stdio_offline_quote_and_policy_boundaries(tmp_path):
    evidence = [
        {"id": "fixture-1", "text": "Synthetic order shipped on Tuesday.", "source": "synthetic fixture"}
    ]
    async with server_session(tmp_path, "sigma_public_verify.server") as (session, initialized):
        assert initialized.serverInfo.name == "sigma-public-verify"
        tools = (await session.list_tools()).tools
        assert {tool.name for tool in tools} == {"verification_status", "check_quote", "assess_claim"}
        for tool in tools:
            assert not {
                "scope",
                "provider",
                "model",
                "endpoint",
                "export_classification",
                "external_enabled",
                "token",
            } & set(tool.inputSchema["properties"])
        status = result_data(await session.call_tool("verification_status", {}))
        assert status["external_enabled"] is False
        assert status["export_permitted"] is False
        assert status["provider"] is None
        offline = result_data(
            await session.call_tool(
                "assess_claim",
                {
                    "claim": "The synthetic order shipped.",
                    "evidence": evidence,
                },
            )
        )
        assert offline["status"] == "offline"
        assert offline["assessment"] is None
        assert offline["consensus"] == "not_measured"
        quote = result_data(
            await session.call_tool(
                "check_quote",
                {
                    "quote": "shipped on Tuesday",
                    "evidence": evidence,
                },
            )
        )
        assert quote == {
            "status": "matched",
            "evidence_ids": ["fixture-1"],
            "method": "exact_quotation_presence_only",
        }
        for override in ("endpoint", "provider", "model", "export_classification", "external_enabled"):
            result = await session.call_tool(
                "assess_claim",
                {
                    "claim": "synthetic",
                    "evidence": evidence,
                    override: PRIVATE_MARKER,
                },
            )
            assert_private_error(result)
        for tool, arguments in (
            ("assess_claim", {"claim": {PRIVATE_MARKER: 1}, "evidence": evidence}),
            ("check_quote", {"quote": "synthetic", "evidence": [{"text": PRIVATE_MARKER}]}),
            ("verification_status", {"token": PRIVATE_MARKER}),
        ):
            assert_private_error(await session.call_tool(tool, arguments))


@pytest.mark.asyncio
@pytest.mark.parametrize("module", ["sigma_public_memory.server", "sigma_public_verify.server"])
async def test_actual_stdio_unknown_tool_does_not_reflect_name_into_logs(tmp_path, module):
    arguments = memory_arguments(tmp_path) if module == "sigma_public_memory.server" else ()
    async with server_session(tmp_path, module, arguments) as (session, _):
        assert_private_error(await session.call_tool(PRIVATE_MARKER, {}))
