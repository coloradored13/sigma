"""Static stdio tools. The process host selects export policy and credentials."""

from __future__ import annotations

import argparse
import os
from dataclasses import asdict

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ResourceError, ToolError
from sigma_public_core.log_privacy import protect_mcp_diagnostics

from .verifier import (
    Evidence,
    OpenAICompatibleAdapter,
    VerificationPolicy,
    VerificationRequest,
    Verifier,
)
from .verifier import (
    check_quote as check_quote_evidence,
)


def _evidence(items: list[dict]) -> tuple[Evidence, ...]:
    try:
        return tuple(Evidence(**item) for item in items)
    except (ValueError, TypeError):
        raise ValueError("invalid evidence input") from None


class _VerificationServer(FastMCP):
    async def read_resource(self, uri):
        # This server exposes tools only. SDK defaults echo rejected URIs/names.
        raise ResourceError("resource unavailable") from None

    async def get_prompt(self, name, arguments=None):
        raise ValueError("prompt unavailable") from None

    async def call_tool(self, name: str, arguments: dict):
        # SDK validation errors include rejected input values. Keep them out of
        # MCP responses and exception chains, including errors before tool entry.
        allowed = {
            "verification_status": set(),
            "check_quote": {"quote", "evidence"},
            "assess_claim": {"claim", "evidence"},
        }
        try:
            if name not in allowed or not isinstance(arguments, dict) or set(arguments) != allowed[name]:
                raise ValueError("invalid tool request")
            return await super().call_tool(name, arguments)
        except Exception:
            raise ToolError("invalid verification tool request") from None


def create_server(verifier: Verifier) -> FastMCP:
    protect_mcp_diagnostics()
    server = _VerificationServer("sigma-public-verify")

    @server.tool()
    def verification_status() -> dict:
        """Report host-selected policy; model agreement never constitutes consensus."""
        policy = verifier.policy
        return {
            "external_enabled": policy.external_enabled,
            "export_permitted": policy.external_enabled and policy.export_classification == "public",
            "provider": policy.provider,
            "model": policy.model,
            "method": "model_assessment",
            "consensus": "not_measured",
            "quote_check": "exact_quotation_presence_only",
        }

    @server.tool()
    def check_quote(quote: str, evidence: list[dict]) -> dict:
        """Find exact quotation text in supplied evidence; do not establish truth or fetch sources."""
        return asdict(check_quote_evidence(quote, _evidence(evidence)))

    @server.tool()
    def assess_claim(claim: str, evidence: list[dict]) -> dict:
        """Request a labeled model assessment, subject to fixed host export/provider policy."""
        return asdict(verifier.verify(VerificationRequest(claim, _evidence(evidence))))

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=(
        "Sigma Public verification MCP. Defaults to offline quotation checks. External assessment "
        "requires explicit public-project export policy; it does not establish factual truth."
    ))
    parser.add_argument("--allow-external", action="store_true")
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--endpoint", help="Exact HTTPS chat/completions URL; no redirects or fallback")
    parser.add_argument("--export-classification", choices=("private", "public"), default="private")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    arguments = parser.parse_args()
    try:
        policy = VerificationPolicy(
            external_enabled=arguments.allow_external,
            provider=arguments.provider, model=arguments.model, endpoint=arguments.endpoint,
            export_classification=arguments.export_classification, timeout_seconds=arguments.timeout_seconds,
        )
        adapter = None
        if policy.external_enabled:
            if policy.export_classification != "public":
                parser.error("external assessment requires --export-classification public")
            token = os.environ.get("SIGMA_PUBLIC_VERIFY_TOKEN")
            if not token:
                parser.error("external assessment requires host environment SIGMA_PUBLIC_VERIFY_TOKEN")
            adapter = OpenAICompatibleAdapter(policy, token)
    except ValueError as error:
        parser.error(str(error))
    create_server(Verifier(policy, adapter)).run(transport="stdio")


if __name__ == "__main__":
    main()
