"""Synthetic probes of export policy and strict evidence/result contracts."""

import json
from dataclasses import asdict
from types import SimpleNamespace

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError
from sigma_public_verify import (
    Evidence,
    OpenAICompatibleAdapter,
    VerificationPolicy,
    VerificationRequest,
    Verifier,
    check_quote,
)
from sigma_public_verify.server import create_server
from sigma_public_verify.server import main as server_main


@pytest.fixture
def request_data():
    return VerificationRequest(
        "The synthetic order shipped.",
        (Evidence("e1", "Order test-1 shipped on Tuesday.", "synthetic fixture"),),
    )


def policy(**changes):
    values = dict(
        external_enabled=True, provider="synthetic", model="fixture-model",
        endpoint="https://verify.example.test/v1/chat/completions", export_classification="public",
    )
    values.update(changes)
    return VerificationPolicy(**values)


class Adapter:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def assess(self, request):
        self.calls.append(request)
        if self.error:
            raise self.error
        return self.response


def response(status="assessment", assessment="supported", evidence_ids=None):
    return json.dumps({
        "status": status, "assessment": assessment,
        "evidence_ids": ["e1"] if evidence_ids is None else evidence_ids,
    })


def test_offline_even_with_credentials_and_network_capable_adapter(monkeypatch, request_data):
    monkeypatch.setenv("SIGMA_PUBLIC_VERIFY_TOKEN", "synthetic-secret-canary")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-ambient-secret")
    adapter = Adapter(error=AssertionError("must not execute"))
    result = Verifier(adapter=adapter).verify(request_data)
    assert result.status == "offline"
    assert result.assessment is None
    assert result.consensus == "not_measured"
    assert not adapter.calls


def test_private_host_policy_blocks_before_adapter(request_data):
    adapter = Adapter(error=AssertionError("must not execute"))
    result = Verifier(policy(export_classification="private"), adapter).verify(request_data)
    assert result.status == "blocked"
    assert not adapter.calls


def test_quote_presence_has_no_truth_or_consensus_claim(request_data):
    result = check_quote("shipped on Tuesday", request_data.evidence)
    assert result.status == "matched"
    assert result.evidence_ids == ("e1",)
    assert result.method == "exact_quotation_presence_only"
    assert "assessment" not in asdict(result)
    assert check_quote("Shipped on Tuesday", request_data.evidence).status == "no_match"
    false_evidence = [Evidence("false", "The moon is made of cheese.", "fictional story")]
    assert check_quote("moon is made of cheese", false_evidence).status == "matched"


def test_typed_assessment_is_not_singleton_consensus(request_data):
    result = Verifier(policy(), Adapter(response())).verify(request_data)
    assert result.status == "assessment"
    assert result.assessment == "supported"
    assert result.evidence_ids == ("e1",)
    assert result.consensus == "not_measured"
    assert "coverage" not in asdict(result)


def test_contradiction_and_abstention_are_distinct(request_data):
    result = Verifier(policy(), Adapter(response(assessment="contradicted"))).verify(request_data)
    assert result.assessment == "contradicted"
    result = Verifier(policy(), Adapter(response("abstention", None, []))).verify(request_data)
    assert result.status == "abstention"
    assert result.assessment is None


@pytest.mark.parametrize("raw", [
    "not JSON", "null", "[]", "true", '"supported"', '{}',
    response(status="success"), response(assessment="true"), response(evidence_ids=[]),
    response(evidence_ids=["unknown"]), response(evidence_ids=["e1", "e1"]),
    response(evidence_ids=[1]), response("abstention", "supported"),
    '{"status":"assessment","assessment":"supported","evidence_ids":["e1"],"extra":true}',
    '{"status":"abstention","status":"assessment","assessment":"supported","evidence_ids":["e1"]}',
    '{"status":"assessment","assessment":NaN,"evidence_ids":["e1"]}',
    {"status": "assessment"},
])
def test_malformed_provider_cannot_count_as_assessment(raw, request_data):
    result = Verifier(policy(), Adapter(raw)).verify(request_data)
    assert result.status == "malformed"
    assert result.assessment is None
    assert result.evidence_ids == ()
    assert result.consensus == "not_measured"


@pytest.mark.parametrize("error", [
    TimeoutError("synthetic-private-canary"),
    RuntimeError("Bearer synthetic-private-canary"),
])
def test_errors_do_not_echo_provider_or_secret_content(error, request_data):
    result = Verifier(policy(), Adapter(error=error)).verify(request_data)
    assert result.status == "error"
    assert "canary" not in json.dumps(asdict(result))


def test_malformed_response_does_not_echo_content(request_data):
    result = Verifier(policy(), Adapter("synthetic-private-canary")).verify(request_data)
    assert result.status == "malformed"
    assert "canary" not in json.dumps(asdict(result))


def test_no_evidence_abstains_without_provider_call():
    adapter = Adapter(error=AssertionError("must not execute"))
    result = Verifier(policy(), adapter).verify(VerificationRequest("claim", ()))
    assert result.status == "abstention"
    assert not adapter.calls


def test_request_rejects_ambiguous_evidence_ids():
    evidence = Evidence("id", "one", "synthetic")
    with pytest.raises(ValueError, match="duplicate"):
        VerificationRequest("claim", (evidence, evidence))


@pytest.mark.parametrize("endpoint", [
    "http://provider.example/v1", "file:///tmp/credentials", "https://user:secret@provider.example/v1",
    "https://provider.example/v1?token=canary", "https://provider.example/v1#canary",
    "https://", "https://provider.example:99999/v1", "https://provider.example\\@evil.example/v1",
    "https://provider.example/\nprivate",
])
def test_forbidden_endpoint_is_rejected_without_echo(endpoint):
    with pytest.raises(ValueError) as error:
        policy(endpoint=endpoint)
    assert endpoint not in str(error.value)
    assert "canary" not in str(error.value)


def test_explicit_provider_configuration_is_required():
    with pytest.raises(ValueError, match="fixed provider"):
        VerificationPolicy(external_enabled=True)


def mock_http(monkeypatch, handler):
    """Use real httpx request/redirect/stream processing with an in-memory transport."""
    real_client = httpx.Client
    settings = []

    def factory(**kwargs):
        settings.append(kwargs)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("sigma_public_verify.verifier.httpx.Client", factory)
    return settings


def envelope(content=None, **changes):
    result = {"choices": [{"finish_reason": "stop", "message": {"content": content or response()}}]}
    result.update(changes)
    return result


def test_explicit_http_provider_uses_only_fixed_configuration(monkeypatch, request_data):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=envelope())

    settings = mock_http(monkeypatch, handler)
    configured = policy()
    result = Verifier(configured, OpenAICompatibleAdapter(configured, "synthetic-token")).verify(request_data)
    assert result.status == "assessment"
    assert len(requests) == 1
    assert str(requests[0].url) == configured.endpoint
    assert requests[0].headers["Authorization"] == "Bearer synthetic-token"
    payload = json.loads(requests[0].content)
    assert payload["model"] == "fixture-model"
    exported = json.loads(payload["messages"][1]["content"])
    assert exported == {
        "claim": request_data.claim,
        "evidence": [{"id": "e1", "text": request_data.evidence[0].text, "source": "synthetic fixture"}],
    }
    assert settings[0]["follow_redirects"] is False
    assert settings[0]["trust_env"] is False
    assert settings[0].get("verify", True) is True
    assert settings[0]["timeout"] == 10.0


@pytest.mark.parametrize("status_code", [301, 302, 307, 308, 401, 429, 500])
def test_http_errors_and_redirects_are_not_followed_or_echoed(monkeypatch, request_data, status_code):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status_code, headers={"Location": "https://evil.example/capture"},
            text="synthetic-private-canary",
        )

    mock_http(monkeypatch, handler)
    configured = policy()
    result = Verifier(configured, OpenAICompatibleAdapter(configured, "synthetic-token")).verify(request_data)
    assert result.status == "error"
    assert len(requests) == 1
    assert "canary" not in json.dumps(asdict(result))


def test_http_timeout_has_no_fallback(monkeypatch, request_data):
    requests = []

    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout("synthetic-private-canary")

    mock_http(monkeypatch, handler)
    configured = policy()
    result = Verifier(configured, OpenAICompatibleAdapter(configured, "synthetic-token")).verify(request_data)
    assert result.status == "error"
    assert len(requests) == 1
    assert "canary" not in json.dumps(asdict(result))


@pytest.mark.parametrize("provider_response", [
    "not JSON", "[]", json.dumps(envelope(choices=[])),
    json.dumps(envelope(choices=[{"finish_reason": "length", "message": {"content": "partial"}}])),
    "x" * 2048,
])
def test_http_envelope_and_size_limits(monkeypatch, request_data, provider_response):
    mock_http(monkeypatch, lambda request: httpx.Response(200, text=provider_response))
    configured = policy(max_response_bytes=1024)
    result = Verifier(configured, OpenAICompatibleAdapter(configured, "synthetic-token")).verify(request_data)
    assert result.status == "malformed"


@pytest.mark.asyncio
async def test_mcp_catalog_has_no_policy_override_parameters():
    server = create_server(Verifier())
    tools = await server.list_tools()
    assert {tool.name for tool in tools} == {"verification_status", "check_quote", "assess_claim"}
    for tool in tools:
        assert not {"provider", "model", "endpoint", "export_classification", "external_enabled"}.intersection(
            tool.inputSchema.get("properties", {})
        )


@pytest.mark.asyncio
async def test_mcp_default_is_offline_and_quote_check_works():
    server = create_server(Verifier())
    result = await server.call_tool("assess_claim", {
        "claim": "Synthetic claim", "evidence": [{"id": "e1", "text": "test text", "source": "fixture"}],
    })
    structured = json.loads(result[0].text)
    assert structured["status"] == "offline"
    result = await server.call_tool("check_quote", {
        "quote": "test text", "evidence": [{"id": "e1", "text": "test text", "source": "fixture"}],
    })
    assert json.loads(result[0].text)["method"] == "exact_quotation_presence_only"


@pytest.mark.asyncio
@pytest.mark.parametrize("name,arguments", [
    ("assess_claim", {"claim": "x", "evidence": "synthetic-private-canary"}),
    ("assess_claim", {"claim": "x", "evidence": [{"id": "synthetic-private-canary"}]}),
    ("assess_claim", {"claim": "x", "evidence": [], "endpoint": "synthetic-private-canary"}),
    ("synthetic-private-canary", {}),
])
async def test_mcp_validation_errors_omit_input_values(name, arguments, caplog):
    server = create_server(Verifier())
    with pytest.raises(ToolError) as error:
        await server.call_tool(name, arguments)
    assert "canary" not in str(error.value)
    assert "canary" not in caplog.text
    assert error.value.__suppress_context__


def test_cli_offline_does_not_read_any_credential_environment(monkeypatch):
    class ForbiddenEnvironment:
        def get(self, name):
            raise AssertionError("offline CLI must not read credentials")

    runs = []
    monkeypatch.setattr("sys.argv", ["sigma-public-verify"])
    monkeypatch.setattr("sigma_public_verify.server.os", SimpleNamespace(environ=ForbiddenEnvironment()))

    def server(verifier):
        assert not verifier.policy.external_enabled
        return SimpleNamespace(run=lambda **kwargs: runs.append(kwargs))

    monkeypatch.setattr("sigma_public_verify.server.create_server", server)
    server_main()
    assert runs == [{"transport": "stdio"}]


def test_cli_external_requires_own_token_and_ignores_ambient_auth(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", [
        "sigma-public-verify", "--allow-external", "--provider", "fixture", "--model", "fixture",
        "--endpoint", "https://verify.example.test/v1/chat/completions", "--export-classification", "public",
    ])
    monkeypatch.delenv("SIGMA_PUBLIC_VERIFY_TOKEN", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-private-canary")
    with pytest.raises(SystemExit) as error:
        server_main()
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert "SIGMA_PUBLIC_VERIFY_TOKEN" in captured.err
    assert "canary" not in captured.err


def test_http_slow_response_exceeds_elapsed_budget(monkeypatch, request_data):
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=envelope()))
    times = iter([0.0, 11.0])
    monkeypatch.setattr("sigma_public_verify.verifier.time", SimpleNamespace(monotonic=lambda: next(times)))
    configured = policy(timeout_seconds=10.0)
    result = Verifier(configured, OpenAICompatibleAdapter(configured, "synthetic-token")).verify(request_data)
    assert result.status == "error"


def test_http_rejects_unrequested_compression(monkeypatch, request_data):
    mock_http(monkeypatch, lambda request: httpx.Response(
        200, json=envelope(), headers={"Content-Encoding": "identity, identity"},
    ))
    configured = policy()
    result = Verifier(configured, OpenAICompatibleAdapter(configured, "synthetic-token")).verify(request_data)
    assert result.status == "malformed"
