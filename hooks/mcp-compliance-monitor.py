#!/usr/bin/env python3
"""MCP Tool Call Compliance Monitor — PostToolUse hook.

Monitors sigma-mem and sigma-verify MCP tool calls during
sigma-review and sigma-build sessions. Warns on violations.

Enforces:
  A. DA workspace delivery — DA findings must go to workspace, not agent memory
  B. SigmaComm format validation — memory entries must use pipe-delimited notation
  C. sigma-verify availability tracking — records provider state
  D. sigma-verify result pending tracking — counts calls per phase
  E. MCP error recovery — warns on consecutive failures

PostToolUse hooks can only WARN (systemMessage in output JSON), not BLOCK.
"""
import json
import os
import sys
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import sigma_paths as sp  # noqa: E402


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_CHECKPOINT = Path("/tmp/sigma-review-orchestrator.json")
STATE_FILE = sp.STATE_DIR / ".mcp-compliance-state.json"

# Phases where DA legitimately writes to workspace, not memory
DA_WORKSPACE_PHASES = {"challenge", "review", "challenge_plan"}

# Tool names that write to sigma-mem memory
SIGMA_MEM_MEMORY_TOOLS = {
    "mcp__sigma-mem__store_agent_memory",
    "mcp__sigma-mem__store_team_decision",
    "mcp__sigma-mem__store_team_pattern",
}

# Tool names for sigma-verify calls
SIGMA_VERIFY_RESULT_TOOLS = {
    "mcp__sigma-verify__verify_finding",
    "mcp__sigma-verify__cross_verify",
    "mcp__sigma-verify__challenge",
}

# Error indicator strings in MCP responses
ERROR_STRINGS = {"rate_limit", "timeout", "quota", "rate limit", "timed out"}
ERROR_STATUS_CODES = {429, 500, 503}


# ---------------------------------------------------------------------------
# State management (same pattern as phase-compliance-enforcer)
# ---------------------------------------------------------------------------

def read_checkpoint():
    """Read orchestrator checkpoint. Returns dict or None if no active session."""
    if not DEFAULT_CHECKPOINT.exists():
        return None
    try:
        with open(DEFAULT_CHECKPOINT) as f:
            data = json.load(f)
        phase = data.get("current_phase")
        if not phase or phase == "complete":
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def read_state():
    """Read MCP compliance tracking state."""
    if not STATE_FILE.exists():
        return {}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def write_state(state):
    """Write MCP compliance tracking state (atomic)."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, str(STATE_FILE))


def update_state(**kwargs):
    """Merge keys into state."""
    state = read_state()
    state.update(kwargs)
    write_state(state)
    return state


# ---------------------------------------------------------------------------
# (A) DA workspace delivery warning
# ---------------------------------------------------------------------------

def check_da_workspace_delivery(tool_name, tool_input, checkpoint):
    """Warn if DA stores findings to agent memory during challenge/review phases.

    DA findings must go to workspace ## DA-assessment for audit trail.
    DA legitimately stores calibration to memory during promotion phase.
    """
    if tool_name != "mcp__sigma-mem__store_agent_memory":
        return None

    agent_name = tool_input.get("agent_name", "").lower()
    if "devils-advocate" not in agent_name and agent_name != "da":
        return None

    current_phase = checkpoint.get("current_phase", "")
    if current_phase not in DA_WORKSPACE_PHASES:
        return None

    return (
        "DA findings must go to workspace ## DA-assessment, not agent memory. "
        "Workspace delivery required for audit trail."
    )


# ---------------------------------------------------------------------------
# (B) SigmaComm format validation
# ---------------------------------------------------------------------------

def check_sigmacomm_format(tool_name, tool_input):
    """Warn if memory entry is missing pipe-delimited SigmaComm format.

    Applies to store_agent_memory, store_team_decision, store_team_pattern.
    Short entries (<20 chars) are exempt — might be simple tags.
    """
    if tool_name not in SIGMA_MEM_MEMORY_TOOLS:
        return None

    # Extract the content field depending on tool
    content = ""
    if tool_name == "mcp__sigma-mem__store_agent_memory":
        content = tool_input.get("entry", "")
    elif tool_name == "mcp__sigma-mem__store_team_decision":
        content = tool_input.get("decision", "")
    elif tool_name == "mcp__sigma-mem__store_team_pattern":
        content = tool_input.get("pattern", "")

    if not content or len(content) < 20:
        return None

    if "|" in content:
        return None

    return (
        "Memory entry may be missing SigmaComm format. "
        "Use pipe-delimited notation: finding|source:type|date"
    )


# ---------------------------------------------------------------------------
# (C) sigma-verify availability tracking
# ---------------------------------------------------------------------------

def track_verify_init(tool_name, tool_response):
    """Track sigma-verify init response — record provider availability."""
    if tool_name != "mcp__sigma-verify__init":
        return

    providers = []
    available = False

    response_str = str(tool_response) if tool_response else ""

    # Parse response for provider information
    if isinstance(tool_response, dict):
        providers = tool_response.get("providers", [])
        available = tool_response.get("available", bool(providers))
    elif isinstance(tool_response, str):
        # Try to parse as JSON
        try:
            resp_data = json.loads(tool_response)
            providers = resp_data.get("providers", [])
            available = resp_data.get("available", bool(providers))
        except (json.JSONDecodeError, TypeError):
            # Check for provider names in text
            available = any(p in response_str.lower() for p in [
                "openai", "anthropic", "ollama", "gemini", "fireworks",
            ])

    update_state(
        xverify_available=available,
        xverify_providers=providers if isinstance(providers, list) else [],
    )


# ---------------------------------------------------------------------------
# (D) sigma-verify result pending tracking
# ---------------------------------------------------------------------------

def track_verify_call(tool_name, tool_input):
    """Track sigma-verify finding/cross_verify/challenge calls."""
    if tool_name not in SIGMA_VERIFY_RESULT_TOOLS:
        return

    state = read_state()
    count = state.get("xverify_calls_this_phase", 0) + 1

    # Extract brief description of what was verified
    brief = tool_input.get("finding", tool_input.get("claim", ""))
    if isinstance(brief, str) and len(brief) > 80:
        brief = brief[:80] + "..."

    update_state(
        xverify_calls_this_phase=count,
        last_xverify_finding=brief,
        xverify_result_written_to_workspace=False,
    )


# ---------------------------------------------------------------------------
# (E) MCP error recovery
# ---------------------------------------------------------------------------

def check_mcp_errors(tool_name, tool_response):
    """Track MCP errors and warn on consecutive failures.

    Returns warning string or None.
    """
    is_error = False
    response_str = str(tool_response) if tool_response else ""

    # Check for error key in dict response
    if isinstance(tool_response, dict):
        if "error" in tool_response:
            is_error = True
        # Check for HTTP status codes
        status = tool_response.get("status", tool_response.get("status_code", 0))
        if isinstance(status, int) and status in ERROR_STATUS_CODES:
            is_error = True

    # Check for error strings in response text
    response_lower = response_str.lower()
    for indicator in ERROR_STRINGS:
        if indicator in response_lower:
            is_error = True
            break

    # Also check for HTTP status codes in string form
    for code in ERROR_STATUS_CODES:
        if str(code) in response_str:
            is_error = True
            break

    state = read_state()

    if is_error:
        consecutive = state.get("mcp_consecutive_errors", 0) + 1
        update_state(mcp_consecutive_errors=consecutive)

        if consecutive >= 2:
            return (
                "Multiple MCP failures detected. Consider pausing and "
                "notifying user before continuing. API budget may need "
                "replenishing."
            )
    else:
        # Success — reset counter
        if state.get("mcp_consecutive_errors", 0) > 0:
            update_state(mcp_consecutive_errors=0)

    return None


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

def main():
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError, ValueError):
        sys.exit(0)

    if data.get("hook_event_name") != "PostToolUse":
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if not (tool_name.startswith("mcp__sigma-mem__") or
            tool_name.startswith("mcp__sigma-verify__")):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    tool_response = data.get("tool_response", "")

    checkpoint = read_checkpoint()

    warnings = []

    # (E) MCP error recovery — runs even without active session
    error_warn = check_mcp_errors(tool_name, tool_response)
    if error_warn:
        warnings.append(error_warn)

    # For remaining checks, need active session
    if checkpoint:
        # (A) DA workspace delivery
        da_warn = check_da_workspace_delivery(tool_name, tool_input, checkpoint)
        if da_warn:
            warnings.append(da_warn)

        # (B) SigmaComm format validation
        format_warn = check_sigmacomm_format(tool_name, tool_input)
        if format_warn:
            warnings.append(format_warn)

        # (C) sigma-verify init tracking (no warning, just state)
        track_verify_init(tool_name, tool_response)

        # (D) sigma-verify result tracking (no warning, just state)
        track_verify_call(tool_name, tool_input)
    else:
        # Even without session, track verify init if it happens
        track_verify_init(tool_name, tool_response)

    if warnings:
        print(json.dumps({"systemMessage": " | ".join(warnings)}))

    sys.exit(0)


if __name__ == "__main__":
    main()
