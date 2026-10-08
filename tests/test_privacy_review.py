"""Independent protocol/privacy regression probes using only synthetic data."""

import logging
import sys

import anyio
import pytest
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError
from mcp.shared.message import SessionMessage
from mcp.types import JSONRPCMessage, JSONRPCNotification, JSONRPCRequest
from pydantic import AnyUrl
from sigma_public_core.log_privacy import protect_mcp_diagnostics
from test_mcp_stdio import OFFLINE_LAUNCHER, PRIVATE_MARKER, memory_arguments, server_session

CANARY = "SYNTHETIC_PRIVATE_PROTOCOL_PARAMETER"


@pytest.mark.asyncio
@pytest.mark.parametrize("module", ["sigma_public_memory.server", "sigma_public_verify.server"])
async def test_malformed_protocol_parameters_are_not_logged(tmp_path, module):
    """Bypass ClientSession validation and exercise the SDK before tool dispatch."""
    arguments = memory_arguments(tmp_path) if module == "sigma_public_memory.server" else []
    parameters = StdioServerParameters(
        command=sys.executable, args=["-I", "-c", OFFLINE_LAUNCHER, module, *arguments],
        cwd=str(tmp_path), env={},
    )
    with (tmp_path / "protocol.stderr").open("w+") as errors:
        with anyio.fail_after(20):
            async with stdio_client(parameters, errlog=errors) as (read, write):
                await write.send(SessionMessage(JSONRPCMessage(JSONRPCRequest(
                    jsonrpc="2.0", id=1, method="initialize", params={
                        "protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "synthetic-protocol-test", "version": "1"},
                    },
                ))))
                initialized = await read.receive()
                assert initialized.message.root.id == 1
                await write.send(SessionMessage(JSONRPCMessage(JSONRPCNotification(
                    jsonrpc="2.0", method="notifications/initialized",
                ))))
                await write.send(SessionMessage(JSONRPCMessage(JSONRPCRequest(
                    jsonrpc="2.0", id=2, method="tools/call", params={"name": {CANARY: "value"}},
                ))))
                denied = await read.receive()
                assert denied.message.root.id == 2
                assert CANARY not in denied.message.model_dump_json()
                assert denied.message.root.error.code == -32602
                # Notification failures use a separate SDK warning site. A ping
                # confirms the receive loop processed it before closing stdin.
                await write.send(SessionMessage(JSONRPCMessage(JSONRPCNotification(
                    jsonrpc="2.0", method="notifications/progress", params={
                        "progressToken": "synthetic", "progress": {CANARY: "value"},
                    },
                ))))
                await write.send(SessionMessage(JSONRPCMessage(JSONRPCRequest(
                    jsonrpc="2.0", id=3, method="ping",
                ))))
                assert (await read.receive()).message.root.id == 3
        errors.seek(0)
        log = errors.read()
        assert CANARY not in log
        assert "MCP invalid request parameters" in log
        assert "MCP invalid notification parameters" in log


def test_diagnostic_filter_is_idempotent_and_preserves_host_logs(caplog):
    protect_mcp_diagnostics()
    before = tuple(logging.getLogger().filters)
    protect_mcp_diagnostics()
    assert tuple(logging.getLogger().filters) == before
    logging.warning("Synthetic host diagnostic remains useful")
    assert "Synthetic host diagnostic remains useful" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("module", ["sigma_public_memory.server", "sigma_public_verify.server"])
@pytest.mark.parametrize("method", ["resources/read", "prompts/get"])
async def test_unsupported_protocol_methods_do_not_reflect_input(tmp_path, module, method):
    arguments = memory_arguments(tmp_path) if module == "sigma_public_memory.server" else []
    async with server_session(tmp_path, module, arguments) as (session, _):
        with pytest.raises(McpError) as error:
            if method == "resources/read":
                await session.read_resource(AnyUrl(f"file:///synthetic/{PRIVATE_MARKER}"))
            else:
                await session.get_prompt(PRIVATE_MARKER, {"text": PRIVATE_MARKER})
        assert PRIVATE_MARKER not in str(error.value)
