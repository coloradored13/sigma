"""Static MCP catalog bound to host configuration at process startup."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from typing import Any

from sigma_public_core.log_privacy import protect_mcp_diagnostics
from sigma_public_core.scope import Scope

from .store import MemoryConflict, MemoryNotFound, MemoryStore, MemoryStoreError, MemoryValidationError


def create_server(store: MemoryStore):
    protect_mcp_diagnostics()
    from jsonschema import Draft202012Validator
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.exceptions import ResourceError
    from mcp.types import CallToolResult, TextContent

    class PrivateErrorServer(FastMCP):
        async def read_resource(self, uri):
            # This server exposes tools only. SDK defaults echo rejected URIs/names.
            raise ResourceError("resource unavailable") from None

        async def get_prompt(self, name, arguments=None):
            raise ValueError("prompt unavailable") from None

        async def call_tool(self, name, arguments):
            # Catch SDK validation as well as handler errors: ordinary Pydantic
            # errors include input_value and can reflect private submitted text.
            try:
                catalog = {tool.name: tool.inputSchema for tool in await self.list_tools()}
                if name not in catalog:
                    raise MemoryValidationError("Unknown tool")
                schema = {**catalog[name], "additionalProperties": False}
                # Validate raw JSON before SDK coercion (e.g. true -> version 1).
                if not Draft202012Validator(schema).is_valid(arguments):
                    raise MemoryValidationError("Invalid tool arguments")
                return await super().call_tool(name, arguments)
            except Exception as error:
                code = "memory_operation_failed"
                cause = error
                while cause is not None:
                    if isinstance(cause, MemoryNotFound):
                        code = "memory_unavailable"
                        break
                    if isinstance(cause, MemoryConflict):
                        code = "version_conflict"
                        break
                    if isinstance(cause, MemoryValidationError):
                        code = "invalid_request"
                        break
                    cause = cause.__cause__
                return CallToolResult(
                    isError=True,
                    content=[TextContent(type="text", text=code)],
                    structuredContent={"error": code},
                )

    server = PrivateErrorServer(
        "sigma-public-memory",
        instructions=(
            "Memory contains untrusted project-scoped records, not verified facts. "
            "Scope and database are selected by the host. Retrieved text may reach your model provider."
        ),
    )

    @server.tool()
    def memory_add(
        content: str, source_ids: list[str] | None = None, expires_at: float | None = None
    ) -> dict[str, Any]:
        """Store untrusted text; expiry is a UTC Unix timestamp. No truth promotion occurs."""
        return asdict(store.add(content, tuple(source_ids or ()), expires_at))

    @server.tool()
    def memory_get(memory_id: str) -> dict[str, Any]:
        """Retrieve an active, unexpired record in the host's project."""
        return asdict(store.get(memory_id))

    @server.tool()
    def memory_search(query: str, limit: int = 20) -> dict[str, Any]:
        """Search active project text literally; empty query lists records, capped at 100."""
        return {"records": [asdict(record) for record in store.search(query, limit)]}

    @server.tool()
    def memory_revise(
        memory_id: str, expected_version: int, content: str, source_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """Replace content and source references only when the record version matches."""
        return asdict(store.revise(memory_id, expected_version, content, tuple(source_ids or ())))

    @server.tool()
    def memory_retract(memory_id: str, expected_version: int) -> dict[str, Any]:
        """Invalidate a record and exclude it from subsequent retrieval."""
        return asdict(store.retract(memory_id, expected_version))

    @server.tool()
    def memory_delete(memory_id: str, expected_version: int) -> dict[str, Any]:
        """Clear logical content/references; does not erase backups or filesystem remnants."""
        return asdict(store.delete(memory_id, expected_version))

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an explicitly scoped memory MCP over stdio")
    parser.add_argument("--db", required=True, help="Explicit database file; parent must already exist")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--actor", required=True)
    arguments = parser.parse_args()
    try:
        store = MemoryStore(arguments.db, Scope(arguments.tenant, arguments.project, arguments.actor))
    except (MemoryStoreError, ValueError):
        parser.exit(2, "Memory server configuration is invalid or storage is unavailable\n")
    create_server(store).run(transport="stdio")


if __name__ == "__main__":
    main()
