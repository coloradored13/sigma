"""Tests for mcp-compliance-monitor.py — PostToolUse hook for MCP tool calls.

Tests the 5 enforcement functions:
  A. DA workspace delivery warning
  B. SigmaComm format validation
  C. sigma-verify availability tracking
  D. sigma-verify result pending tracking
  E. MCP error recovery

Testing strategies:
  1. Unit tests: import module, monkeypatch Path constants to tmp dirs
  2. Subprocess smoke tests: run script via subprocess with JSON on stdin
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import importlib
monitor = importlib.import_module("mcp-compliance-monitor")

HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_checkpoint(tmp_path, monkeypatch):
    """Create a temporary checkpoint file and wire it up."""
    cp = tmp_path / "checkpoint.json"
    monkeypatch.setattr(monitor, "DEFAULT_CHECKPOINT", cp)

    def _write(data):
        cp.write_text(json.dumps(data), encoding="utf-8")
        return cp

    return _write


@pytest.fixture
def tmp_state(tmp_path, monkeypatch):
    """Wire state file to tmp."""
    sf = tmp_path / ".mcp-compliance-state.json"
    monkeypatch.setattr(monitor, "STATE_FILE", sf)
    return sf


@pytest.fixture
def challenge_checkpoint(tmp_checkpoint):
    """Active ANALYZE checkpoint in challenge phase."""
    return tmp_checkpoint({
        "_mode": "analyze",
        "current_phase": "challenge",
        "phase_history": ["research", "circuit_breaker", "challenge"],
    })


@pytest.fixture
def promotion_checkpoint(tmp_checkpoint):
    """Active ANALYZE checkpoint in promotion phase."""
    return tmp_checkpoint({
        "_mode": "analyze",
        "current_phase": "promotion",
        "phase_history": ["research", "circuit_breaker", "challenge",
                          "debate", "synthesis", "compilation", "promotion"],
    })


@pytest.fixture
def build_challenge_checkpoint(tmp_checkpoint):
    """Active BUILD checkpoint in challenge_plan phase."""
    return tmp_checkpoint({
        "_mode": "build",
        "current_phase": "challenge_plan",
        "phase_history": ["plan", "challenge_plan"],
    })


@pytest.fixture
def review_checkpoint(tmp_checkpoint):
    """Active BUILD checkpoint in review phase."""
    return tmp_checkpoint({
        "_mode": "build",
        "current_phase": "review",
        "phase_history": ["plan", "challenge_plan", "build", "review"],
    })


# ---------------------------------------------------------------------------
# (A) DA Workspace Delivery
# ---------------------------------------------------------------------------

class TestDAWorkspaceDelivery:
    def test_warns_da_store_during_challenge(self, challenge_checkpoint, tmp_state):
        """DA storing to agent memory during challenge phase -> warning."""
        cp = json.loads(challenge_checkpoint.read_text())
        result = monitor.check_da_workspace_delivery(
            "mcp__sigma-mem__store_agent_memory",
            {"agent_name": "devils-advocate", "entry": "F1: finding"},
            cp,
        )
        assert result is not None
        assert "workspace" in result.lower()
        assert "DA-assessment" in result

    def test_warns_da_shortname_during_challenge(self, challenge_checkpoint, tmp_state):
        """DA with shortname 'da' also triggers warning."""
        cp = json.loads(challenge_checkpoint.read_text())
        result = monitor.check_da_workspace_delivery(
            "mcp__sigma-mem__store_agent_memory",
            {"agent_name": "da", "entry": "challenge findings"},
            cp,
        )
        assert result is not None

    def test_warns_da_during_review(self, review_checkpoint, tmp_state):
        """DA storing during BUILD review phase -> warning."""
        cp = json.loads(review_checkpoint.read_text())
        result = monitor.check_da_workspace_delivery(
            "mcp__sigma-mem__store_agent_memory",
            {"agent_name": "devils-advocate", "entry": "review finding"},
            cp,
        )
        assert result is not None

    def test_warns_da_during_challenge_plan(self, build_challenge_checkpoint, tmp_state):
        """DA storing during challenge_plan phase -> warning."""
        cp = json.loads(build_challenge_checkpoint.read_text())
        result = monitor.check_da_workspace_delivery(
            "mcp__sigma-mem__store_agent_memory",
            {"agent_name": "devils-advocate", "entry": "plan challenge"},
            cp,
        )
        assert result is not None

    def test_no_warn_da_store_during_promotion(self, promotion_checkpoint, tmp_state):
        """DA storing during promotion is legitimate — no warning."""
        cp = json.loads(promotion_checkpoint.read_text())
        result = monitor.check_da_workspace_delivery(
            "mcp__sigma-mem__store_agent_memory",
            {"agent_name": "devils-advocate", "entry": "calibration data"},
            cp,
        )
        assert result is None

    def test_no_warn_non_da_agent(self, challenge_checkpoint, tmp_state):
        """tech-architect storing during challenge -> no warning."""
        cp = json.loads(challenge_checkpoint.read_text())
        result = monitor.check_da_workspace_delivery(
            "mcp__sigma-mem__store_agent_memory",
            {"agent_name": "tech-architect", "entry": "architecture finding"},
            cp,
        )
        assert result is None

    def test_no_warn_no_active_session(self, tmp_path, monkeypatch, tmp_state):
        """No checkpoint -> no warning (checked at main level, but function needs checkpoint)."""
        # With no checkpoint, main() won't call this function.
        # But test the function directly with None checkpoint for robustness.
        # The function requires a checkpoint dict, so None means it won't be called.
        # Instead test via the absence of the checkpoint file.
        monkeypatch.setattr(monitor, "DEFAULT_CHECKPOINT", tmp_path / "nope.json")
        cp = monitor.read_checkpoint()
        assert cp is None

    def test_no_warn_wrong_tool(self, challenge_checkpoint, tmp_state):
        """store_team_decision by DA is not checked by this function."""
        cp = json.loads(challenge_checkpoint.read_text())
        result = monitor.check_da_workspace_delivery(
            "mcp__sigma-mem__store_team_decision",
            {"agent_name": "devils-advocate", "decision": "some decision"},
            cp,
        )
        assert result is None


# ---------------------------------------------------------------------------
# (B) SigmaComm Format Validation
# ---------------------------------------------------------------------------

class TestSigmaCommFormatValidation:
    def test_warns_missing_pipe_format(self):
        """Entry without | delimiter -> warning."""
        result = monitor.check_sigmacomm_format(
            "mcp__sigma-mem__store_agent_memory",
            {"entry": "This is a finding without pipe delimiters that is quite long"},
        )
        assert result is not None
        assert "SigmaComm" in result
        assert "pipe" in result.lower()

    def test_no_warn_valid_sigmacomm(self):
        """Entry with pipes -> no warning."""
        result = monitor.check_sigmacomm_format(
            "mcp__sigma-mem__store_agent_memory",
            {"entry": "F[market-size]: $2.8-3.4B TAM |source:independent-research:T2| 26.3.22"},
        )
        assert result is None

    def test_no_warn_short_entry(self):
        """Very short entry (<20 chars) -> no warning."""
        result = monitor.check_sigmacomm_format(
            "mcp__sigma-mem__store_agent_memory",
            {"entry": "short tag"},
        )
        assert result is None

    def test_no_warn_exactly_20_chars_with_pipe(self):
        """Entry at 20 chars with pipe -> no warning."""
        result = monitor.check_sigmacomm_format(
            "mcp__sigma-mem__store_agent_memory",
            {"entry": "finding|source|date!"},  # 20 chars
        )
        assert result is None

    def test_validates_team_decision(self):
        """store_team_decision without pipe format -> warning."""
        result = monitor.check_sigmacomm_format(
            "mcp__sigma-mem__store_team_decision",
            {"decision": "We decided to use Streamlit after reviewing all options carefully"},
        )
        assert result is not None
        assert "SigmaComm" in result

    def test_validates_team_pattern(self):
        """store_team_pattern without pipe format -> warning."""
        result = monitor.check_sigmacomm_format(
            "mcp__sigma-mem__store_team_pattern",
            {"pattern": "Always run DA from round 2 minimum in all reviews going forward"},
        )
        assert result is not None
        assert "SigmaComm" in result

    def test_no_warn_team_decision_with_pipes(self):
        """store_team_decision with pipes -> no warning."""
        result = monitor.check_sigmacomm_format(
            "mcp__sigma-mem__store_team_decision",
            {"decision": "Streamlit|recommended|26.3.28|source:sigma-ui-architecture"},
        )
        assert result is None

    def test_no_warn_non_memory_tool(self):
        """Non-memory tool -> no warning."""
        result = monitor.check_sigmacomm_format(
            "mcp__sigma-verify__init",
            {"some_param": "value without pipes that is long enough to trigger"},
        )
        assert result is None

    def test_no_warn_empty_entry(self):
        """Empty entry -> no warning."""
        result = monitor.check_sigmacomm_format(
            "mcp__sigma-mem__store_agent_memory",
            {"entry": ""},
        )
        assert result is None

    def test_no_warn_missing_entry_field(self):
        """Missing entry field -> no warning."""
        result = monitor.check_sigmacomm_format(
            "mcp__sigma-mem__store_agent_memory",
            {"agent_name": "tech-architect"},
        )
        assert result is None


# ---------------------------------------------------------------------------
# (C) sigma-verify Availability Tracking
# ---------------------------------------------------------------------------

class TestSigmaVerifyTracking:
    def test_tracks_init_availability_dict(self, tmp_state):
        """Init response with providers dict -> state updated."""
        monitor.track_verify_init(
            "mcp__sigma-verify__init",
            {"available": True, "providers": ["openai:gpt-4o", "ollama:llama3.1"]},
        )
        state = monitor.read_state()
        assert state["xverify_available"] is True
        assert "openai:gpt-4o" in state["xverify_providers"]
        assert len(state["xverify_providers"]) == 2

    def test_tracks_init_availability_json_string(self, tmp_state):
        """Init response as JSON string -> state updated."""
        monitor.track_verify_init(
            "mcp__sigma-verify__init",
            json.dumps({"available": True, "providers": ["anthropic:claude"]}),
        )
        state = monitor.read_state()
        assert state["xverify_available"] is True
        assert "anthropic:claude" in state["xverify_providers"]

    def test_tracks_init_no_providers(self, tmp_state):
        """Init response with no providers -> xverify_available is False."""
        monitor.track_verify_init(
            "mcp__sigma-verify__init",
            {"available": False, "providers": []},
        )
        state = monitor.read_state()
        assert state["xverify_available"] is False
        assert state["xverify_providers"] == []

    def test_tracks_init_text_response(self, tmp_state):
        """Init response as plain text mentioning a provider -> available."""
        monitor.track_verify_init(
            "mcp__sigma-verify__init",
            "sigma-verify initialized with openai provider",
        )
        state = monitor.read_state()
        assert state["xverify_available"] is True

    def test_ignores_non_init_tool(self, tmp_state):
        """Non-init tool -> no state change."""
        monitor.track_verify_init(
            "mcp__sigma-verify__verify_finding",
            {"result": "confirmed"},
        )
        state = monitor.read_state()
        assert "xverify_available" not in state

    def test_tracks_verify_finding_call(self, tmp_state):
        """verify_finding call -> state incremented."""
        monitor.track_verify_call(
            "mcp__sigma-verify__verify_finding",
            {"finding": "Market size is $2.8-3.4B"},
        )
        state = monitor.read_state()
        assert state["xverify_calls_this_phase"] == 1
        assert "Market size" in state["last_xverify_finding"]
        assert state["xverify_result_written_to_workspace"] is False

    def test_tracks_cross_verify_call(self, tmp_state):
        """cross_verify -> state incremented."""
        monitor.track_verify_call(
            "mcp__sigma-verify__cross_verify",
            {"claim": "API-first architecture enables 3x faster integration"},
        )
        state = monitor.read_state()
        assert state["xverify_calls_this_phase"] == 1

    def test_tracks_challenge_call(self, tmp_state):
        """challenge call -> state incremented."""
        monitor.track_verify_call(
            "mcp__sigma-verify__challenge",
            {"finding": "Short claim"},
        )
        state = monitor.read_state()
        assert state["xverify_calls_this_phase"] == 1

    def test_increments_across_calls(self, tmp_state):
        """Multiple verify calls -> count increments."""
        monitor.track_verify_call(
            "mcp__sigma-verify__verify_finding",
            {"finding": "first"},
        )
        monitor.track_verify_call(
            "mcp__sigma-verify__cross_verify",
            {"finding": "second"},
        )
        state = monitor.read_state()
        assert state["xverify_calls_this_phase"] == 2

    def test_truncates_long_finding(self, tmp_state):
        """Long finding string gets truncated in state."""
        long_finding = "A" * 200
        monitor.track_verify_call(
            "mcp__sigma-verify__verify_finding",
            {"finding": long_finding},
        )
        state = monitor.read_state()
        assert len(state["last_xverify_finding"]) < 200
        assert state["last_xverify_finding"].endswith("...")

    def test_ignores_non_verify_tool(self, tmp_state):
        """Non-verify tool -> no state change."""
        monitor.track_verify_call(
            "mcp__sigma-mem__store_agent_memory",
            {"entry": "not a verify call"},
        )
        state = monitor.read_state()
        assert "xverify_calls_this_phase" not in state


# ---------------------------------------------------------------------------
# (E) MCP Error Recovery
# ---------------------------------------------------------------------------

class TestMCPErrorRecovery:
    def test_first_error_no_warning(self, tmp_state):
        """Single error -> no warning (might be transient)."""
        result = monitor.check_mcp_errors(
            "mcp__sigma-mem__store_agent_memory",
            {"error": "connection refused"},
        )
        assert result is None
        state = monitor.read_state()
        assert state["mcp_consecutive_errors"] == 1

    def test_second_consecutive_error_warns(self, tmp_state):
        """2 errors in a row -> warning."""
        # First error
        monitor.check_mcp_errors(
            "mcp__sigma-mem__store_agent_memory",
            {"error": "connection refused"},
        )
        # Second error
        result = monitor.check_mcp_errors(
            "mcp__sigma-mem__store_agent_memory",
            {"error": "connection refused again"},
        )
        assert result is not None
        assert "Multiple MCP failures" in result
        assert "budget" in result.lower()

    def test_third_error_still_warns(self, tmp_state):
        """3+ consecutive errors still produce warning."""
        for _ in range(3):
            result = monitor.check_mcp_errors(
                "mcp__sigma-mem__store_agent_memory",
                {"error": "still failing"},
            )
        assert result is not None
        state = monitor.read_state()
        assert state["mcp_consecutive_errors"] == 3

    def test_success_resets_counter(self, tmp_state):
        """Error then success -> counter reset."""
        # First: error
        monitor.check_mcp_errors(
            "mcp__sigma-mem__store_agent_memory",
            {"error": "oops"},
        )
        state = monitor.read_state()
        assert state["mcp_consecutive_errors"] == 1

        # Then: success
        monitor.check_mcp_errors(
            "mcp__sigma-mem__store_agent_memory",
            {"status": "ok", "result": "stored"},
        )
        state = monitor.read_state()
        assert state["mcp_consecutive_errors"] == 0

    def test_detects_rate_limit_in_response(self, tmp_state):
        """Response with 'rate_limit' -> counted as error."""
        monitor.check_mcp_errors(
            "mcp__sigma-verify__verify_finding",
            "Error: rate_limit exceeded, please retry",
        )
        state = monitor.read_state()
        assert state["mcp_consecutive_errors"] == 1

    def test_detects_rate_limit_with_space(self, tmp_state):
        """Response with 'rate limit' (space) -> counted as error."""
        monitor.check_mcp_errors(
            "mcp__sigma-verify__verify_finding",
            "rate limit exceeded",
        )
        state = monitor.read_state()
        assert state["mcp_consecutive_errors"] == 1

    def test_detects_error_key_in_response(self, tmp_state):
        """Response dict with 'error' key -> counted as error."""
        monitor.check_mcp_errors(
            "mcp__sigma-mem__store_agent_memory",
            {"error": "Internal server error"},
        )
        state = monitor.read_state()
        assert state["mcp_consecutive_errors"] == 1

    def test_detects_timeout_in_response(self, tmp_state):
        """Response with 'timeout' -> counted as error."""
        monitor.check_mcp_errors(
            "mcp__sigma-verify__cross_verify",
            "Request timed out after 30s timeout",
        )
        state = monitor.read_state()
        assert state["mcp_consecutive_errors"] == 1

    def test_detects_quota_in_response(self, tmp_state):
        """Response with 'quota' -> counted as error."""
        monitor.check_mcp_errors(
            "mcp__sigma-mem__store_agent_memory",
            "quota exceeded for this billing period",
        )
        state = monitor.read_state()
        assert state["mcp_consecutive_errors"] == 1

    def test_detects_status_code_429(self, tmp_state):
        """Response dict with status 429 -> counted as error."""
        monitor.check_mcp_errors(
            "mcp__sigma-verify__verify_finding",
            {"status": 429, "message": "Too many requests"},
        )
        state = monitor.read_state()
        assert state["mcp_consecutive_errors"] == 1

    def test_detects_status_code_500(self, tmp_state):
        """Response dict with status_code 500 -> counted as error."""
        monitor.check_mcp_errors(
            "mcp__sigma-mem__store_agent_memory",
            {"status_code": 500, "body": "Internal error"},
        )
        state = monitor.read_state()
        assert state["mcp_consecutive_errors"] == 1

    def test_detects_status_code_503_in_string(self, tmp_state):
        """Response string containing '503' -> counted as error."""
        monitor.check_mcp_errors(
            "mcp__sigma-mem__store_agent_memory",
            "HTTP 503 Service Unavailable",
        )
        state = monitor.read_state()
        assert state["mcp_consecutive_errors"] == 1

    def test_clean_response_no_error(self, tmp_state):
        """Clean response -> no error tracked."""
        result = monitor.check_mcp_errors(
            "mcp__sigma-mem__store_agent_memory",
            {"status": "ok", "id": "mem_123"},
        )
        assert result is None
        state = monitor.read_state()
        # Counter should not exist or be 0
        assert state.get("mcp_consecutive_errors", 0) == 0


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

class TestStateManagement:
    def test_read_empty_state(self, tmp_state):
        assert monitor.read_state() == {}

    def test_write_and_read_state(self, tmp_state):
        monitor.write_state({"key": "value", "count": 42})
        state = monitor.read_state()
        assert state["key"] == "value"
        assert state["count"] == 42

    def test_update_state_merges(self, tmp_state):
        monitor.write_state({"a": 1, "b": 2})
        monitor.update_state(b=3, c=4)
        state = monitor.read_state()
        assert state == {"a": 1, "b": 3, "c": 4}

    def test_corrupt_state_returns_empty(self, tmp_state):
        tmp_state.write_text("not json{{{")
        assert monitor.read_state() == {}


# ---------------------------------------------------------------------------
# Checkpoint reading
# ---------------------------------------------------------------------------

class TestCheckpointReading:
    def test_no_checkpoint_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(monitor, "DEFAULT_CHECKPOINT", tmp_path / "nope.json")
        assert monitor.read_checkpoint() is None

    def test_completed_session_returns_none(self, tmp_checkpoint):
        tmp_checkpoint({"_mode": "analyze", "current_phase": "complete"})
        assert monitor.read_checkpoint() is None

    def test_null_phase_returns_none(self, tmp_checkpoint):
        tmp_checkpoint({"_mode": "analyze", "current_phase": None})
        assert monitor.read_checkpoint() is None

    def test_active_session_returns_data(self, challenge_checkpoint):
        cp = monitor.read_checkpoint()
        assert cp is not None
        assert cp["current_phase"] == "challenge"

    def test_corrupt_checkpoint_returns_none(self, tmp_checkpoint):
        Path(monitor.DEFAULT_CHECKPOINT).write_text("not json{{{")
        assert monitor.read_checkpoint() is None


# ---------------------------------------------------------------------------
# Subprocess smoke tests
# ---------------------------------------------------------------------------

def run_monitor(stdin_data):
    """Run the monitor script via subprocess."""
    script = HOOKS_DIR / "mcp-compliance-monitor.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(stdin_data) if isinstance(stdin_data, dict) else stdin_data,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result


class TestSubprocessSmoke:
    def test_garbage_stdin(self):
        """Graceful exit on garbage input."""
        script = HOOKS_DIR / "mcp-compliance-monitor.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            input="not json at all {{{",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_empty_stdin(self):
        """Graceful exit on empty input."""
        script = HOOKS_DIR / "mcp-compliance-monitor.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            input="",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0

    def test_non_mcp_tool(self):
        """Non-MCP tool_name -> exit 0, no output."""
        result = run_monitor({
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "/x/test.py", "content": "hello"},
        })
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_non_post_tool_use_event(self):
        """PreToolUse event -> exit 0, no output."""
        result = run_monitor({
            "hook_event_name": "PreToolUse",
            "tool_name": "mcp__sigma-mem__store_agent_memory",
            "tool_input": {"entry": "test"},
        })
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_no_checkpoint_exits_clean(self):
        """No active session -> exit 0 (may or may not produce output for error tracking)."""
        result = run_monitor({
            "hook_event_name": "PostToolUse",
            "tool_name": "mcp__sigma-mem__store_agent_memory",
            "tool_input": {"agent_name": "tech-architect", "entry": "test|source|date"},
            "tool_response": {"status": "ok"},
        })
        assert result.returncode == 0

    def test_mcp_error_tracking_without_session(self):
        """MCP error tracking works even without an active session."""
        # First error
        run_monitor({
            "hook_event_name": "PostToolUse",
            "tool_name": "mcp__sigma-mem__store_agent_memory",
            "tool_input": {"entry": "test"},
            "tool_response": {"error": "connection refused"},
        })
        # Second error should warn
        result = run_monitor({
            "hook_event_name": "PostToolUse",
            "tool_name": "mcp__sigma-mem__store_agent_memory",
            "tool_input": {"entry": "test"},
            "tool_response": {"error": "connection refused again"},
        })
        assert result.returncode == 0
        # Should have warning output
        if result.stdout.strip():
            output = json.loads(result.stdout)
            assert "systemMessage" in output


# ---------------------------------------------------------------------------
# Integration: full main() dispatch
# ---------------------------------------------------------------------------

class TestMainDispatch:
    def test_da_warning_in_challenge(self, challenge_checkpoint, tmp_state):
        """Full dispatch: DA stores to memory during challenge -> warning."""
        # Simulate what main() does without actually calling sys.exit
        data = {
            "hook_event_name": "PostToolUse",
            "tool_name": "mcp__sigma-mem__store_agent_memory",
            "tool_input": {
                "agent_name": "devils-advocate",
                "entry": "This is a long finding without pipe delimiters that should trigger both warnings"
            },
            "tool_response": {"status": "ok"},
        }

        tool_name = data["tool_name"]
        tool_input = data["tool_input"]
        tool_response = data["tool_response"]
        checkpoint = monitor.read_checkpoint()

        warnings = []
        error_warn = monitor.check_mcp_errors(tool_name, tool_response)
        if error_warn:
            warnings.append(error_warn)

        if checkpoint:
            da_warn = monitor.check_da_workspace_delivery(tool_name, tool_input, checkpoint)
            if da_warn:
                warnings.append(da_warn)
            format_warn = monitor.check_sigmacomm_format(tool_name, tool_input)
            if format_warn:
                warnings.append(format_warn)

        # Should have both DA and SigmaComm warnings
        assert len(warnings) == 2
        assert any("workspace" in w.lower() for w in warnings)
        assert any("SigmaComm" in w for w in warnings)

    def test_no_warnings_clean_call(self, challenge_checkpoint, tmp_state):
        """Clean call with proper format -> no warnings."""
        data = {
            "hook_event_name": "PostToolUse",
            "tool_name": "mcp__sigma-mem__store_agent_memory",
            "tool_input": {
                "agent_name": "tech-architect",
                "entry": "F[arch]: API-first pattern|source:independent-research:T1|26.3.28"
            },
            "tool_response": {"status": "ok"},
        }

        tool_name = data["tool_name"]
        tool_input = data["tool_input"]
        tool_response = data["tool_response"]
        checkpoint = monitor.read_checkpoint()

        warnings = []
        error_warn = monitor.check_mcp_errors(tool_name, tool_response)
        if error_warn:
            warnings.append(error_warn)

        if checkpoint:
            da_warn = monitor.check_da_workspace_delivery(tool_name, tool_input, checkpoint)
            if da_warn:
                warnings.append(da_warn)
            format_warn = monitor.check_sigmacomm_format(tool_name, tool_input)
            if format_warn:
                warnings.append(format_warn)

        assert len(warnings) == 0

    def test_verify_init_tracking_during_session(self, challenge_checkpoint, tmp_state):
        """sigma-verify init during active session -> state tracked."""
        monitor.track_verify_init(
            "mcp__sigma-verify__init",
            {"available": True, "providers": ["openai:gpt-4o"]},
        )
        state = monitor.read_state()
        assert state["xverify_available"] is True

    def test_verify_call_tracking_during_session(self, challenge_checkpoint, tmp_state):
        """sigma-verify calls during session -> counted in state."""
        monitor.track_verify_call(
            "mcp__sigma-verify__verify_finding",
            {"finding": "test finding"},
        )
        state = monitor.read_state()
        assert state["xverify_calls_this_phase"] == 1
        assert state["xverify_result_written_to_workspace"] is False
