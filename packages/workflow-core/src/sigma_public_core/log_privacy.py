"""Remove input data from specific MCP SDK diagnostics before handlers see it.

The SDK logs some protocol validation failures before application tool handlers
run. This filter preserves diagnostic categories and severity; it does not disable
logging or inspect/redact arbitrary application messages. Keep the protocol tests
when upgrading the SDK: these adapters cover its current known log sites.
"""

from __future__ import annotations

import logging


class _MCPInputFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        source = record.pathname.replace("\\", "/")
        message = str(record.msg)
        replacement = None
        if source.endswith("/mcp/server/lowlevel/server.py"):
            for prefix, safe in (
                ("Tool '%s' not listed", "MCP unknown tool rejected"),
                ("Tool cache miss for %s", "MCP tool catalog refreshed"),
                ("Received message:", "MCP message received"),
                ("Received exception from stream:", "MCP invalid transport message"),
                ("Warning: %s: %s", "MCP handler warning"),
                ("Request %s cancelled", "MCP request cancelled"),
                ("Response for %s dropped", "MCP response dropped after transport closure"),
                ("Uncaught exception in notification handler", "MCP notification handler failed"),
            ):
                if message.startswith(prefix):
                    replacement = safe
                    break
        elif source.endswith("/mcp/shared/session.py"):
            for prefix, safe in (
                ("Failed to validate request:", "MCP invalid request parameters"),
                ("Message that failed validation:", "MCP request validation failed"),
                ("Failed to validate notification:", "MCP invalid notification parameters"),
                ("Progress callback raised an exception:", "MCP progress callback failed"),
                ("Unhandled exception in receive loop:", "MCP receive loop failed"),
                ("Response ID ", "MCP response identifier could not be normalized"),
            ):
                if message.startswith(prefix):
                    replacement = safe
                    break
        elif source.endswith("/mcp/server/fastmcp/server.py"):
            if message.startswith("Error getting prompt "):
                replacement = "MCP prompt unavailable"
            elif message.startswith("Error reading resource "):
                replacement = "MCP resource unavailable"
        elif source.endswith("/mcp/server/fastmcp/resources/resource_manager.py") and message == "Getting resource":
            # This SDK site puts its untrusted URI in an extra LogRecord field.
            record.__dict__.pop("uri", None)
        if replacement is not None:
            record.msg = replacement
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return True


def protect_mcp_diagnostics() -> None:
    """Install idempotent filters only on loggers used by known SDK log sites.

    The SDK session logs directly on root; its filter checks the exact source
    module before changing a message. Unrelated host diagnostics are unchanged.
    """
    for name in (
        "", "mcp.server.lowlevel.server", "mcp.server.fastmcp.server",
        "mcp.server.fastmcp.resources.resource_manager",
    ):
        logger = logging.getLogger(name)
        if not any(isinstance(item, _MCPInputFilter) for item in logger.filters):
            logger.addFilter(_MCPInputFilter())
