"""Integration smoke tests — end-to-end subprocess tests.

Pipe realistic hook event JSON through each shipped hook script via
subprocess, with HOME pointed at a throwaway directory. Verify exit codes,
stdout contract and file side effects against the Claude Code hooks API.
"""
import json
import subprocess
import sys

import pytest

from conftest import HOOKS_DIR, PLUGIN_ROOT, subprocess_env

SHIPPED_HOOKS = sorted([
    "phase-gate.py",
    "chain-evaluator.py",
    "mcp-compliance-monitor.py",
    "session-start.py",
])


def run_hook(script_name, stdin_data, home_dir, raw=False):
    """Run a hook script via subprocess with JSON (or raw text) on stdin."""
    result = subprocess.run(
        [sys.executable, str(HOOKS_DIR / script_name)],
        input=stdin_data if raw else json.dumps(stdin_data),
        capture_output=True,
        text=True,
        env=subprocess_env(home_dir),
        timeout=15,
    )
    return result


def _sigma_home(home):
    return home / ".claude" / "teams" / "sigma-review"


def _write_workspace(home, content):
    shared = _sigma_home(home) / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    ws = shared / "workspace.md"
    ws.write_text(content, encoding="utf-8")
    return ws


# ─── hooks.json wiring ───


class TestHooksJsonWiring:
    def test_every_command_points_at_a_shipped_script(self):
        config = json.loads((HOOKS_DIR / "hooks.json").read_text())
        commands = [
            h["command"]
            for groups in config["hooks"].values()
            for group in groups
            for h in group["hooks"]
        ]
        assert commands, "hooks.json registers no hooks"
        for cmd in commands:
            assert "${CLAUDE_PLUGIN_ROOT}/hooks/" in cmd
            script = cmd.split("${CLAUDE_PLUGIN_ROOT}/hooks/")[1].split('"')[0]
            assert (HOOKS_DIR / script).is_file(), f"{script} referenced but not shipped"

    def test_all_shipped_hooks_are_registered(self):
        text = (HOOKS_DIR / "hooks.json").read_text()
        for script in SHIPPED_HOOKS:
            assert f"/hooks/{script}" in text, f"{script} not registered in hooks.json"


# ─── phase-gate.py ───


class TestPhaseGateIntegration:
    def test_allows_write_outside_sigma_session(self, tmp_home):
        result = run_hook("phase-gate.py", {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/project/src/main.py", "content": "x = 1\n"},
        }, tmp_home)
        assert result.returncode == 0

    def test_blocks_git_commit_during_incomplete_session(self, tmp_home):
        _write_workspace(tmp_home, "## task\nReview a payments API\n## status: active\n")
        result = run_hook("phase-gate.py", {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'wip'"},
        }, tmp_home)
        assert result.returncode == 2
        assert "GIT OPERATION BLOCKED" in json.loads(result.stdout)["reason"]

    def test_allows_git_commit_when_chain_complete(self, tmp_home):
        _write_workspace(tmp_home, "## task\nReview a payments API\n## status: active\n")
        state = _sigma_home(tmp_home) / ".state"
        state.mkdir(parents=True, exist_ok=True)
        (state / ".chain-status.json").write_text(json.dumps({"last_complete": True, "failed_items": {}}))
        result = run_hook("phase-gate.py", {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'done'"},
        }, tmp_home)
        assert result.returncode == 0

    def test_blocks_sed_in_place_on_workspace(self, tmp_home):
        result = run_hook("phase-gate.py", {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "sed -i 's/a/b/' ~/.claude/teams/sigma-review/shared/workspace.md"},
        }, tmp_home)
        assert result.returncode == 2

    def test_post_tool_use_emits_valid_json_or_nothing(self, tmp_home):
        result = run_hook("phase-gate.py", {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(_sigma_home(tmp_home) / "shared" / "workspace.md"),
                "content": "F[PS-1] untagged finding with no source or status\n",
            },
        }, tmp_home)
        assert result.returncode == 0
        if result.stdout.strip():
            assert isinstance(json.loads(result.stdout), dict)

    def test_sigmacomm_log_lands_in_state_dir(self, tmp_home):
        run_hook("phase-gate.py", {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(_sigma_home(tmp_home) / "shared" / "workspace.md"),
                "content": "DA[#1] challenge to F[PS-1] with no tags at all\n",
            },
        }, tmp_home)
        log = _sigma_home(tmp_home) / ".state" / "sigmacomm-calibration.jsonl"
        assert log.exists(), "ΣComm calibration log should be written under SIGMA_HOME/.state"
        assert not (tmp_home / ".claude" / "hooks").exists(), "nothing may be written to ~/.claude/hooks"


# ─── chain-evaluator.py ───


class TestChainEvaluatorIntegration:
    def test_stop_without_workspace_is_silent(self, tmp_path):
        result = run_hook("chain-evaluator.py", {"hook_event_name": "Stop"}, tmp_path / "empty-home")
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_stop_on_active_workspace_writes_evaluation_and_state(self, tmp_home):
        ws = _write_workspace(tmp_home, "## task\nReview a payments API\n\n## findings\n")
        result = run_hook("chain-evaluator.py", {"hook_event_name": "Stop"}, tmp_home)
        assert result.returncode == 0
        msg = json.loads(result.stdout)["systemMessage"]
        assert msg.startswith("[chain-eval]")
        assert "## Chain Evaluation" in ws.read_text()
        status = json.loads((_sigma_home(tmp_home) / ".state" / ".chain-status.json").read_text())
        assert status["last_complete"] is False

    def test_stop_is_idempotent(self, tmp_home):
        _write_workspace(tmp_home, "## task\nReview a payments API\n\n## findings\n")
        run_hook("chain-evaluator.py", {"hook_event_name": "Stop"}, tmp_home)
        second = run_hook("chain-evaluator.py", {"hook_event_name": "Stop"}, tmp_home)
        assert second.returncode == 0
        assert second.stdout.strip() == ""


# ─── mcp-compliance-monitor.py ───


class TestMcpMonitorIntegration:
    def test_ignores_non_sigma_tools(self, tmp_home):
        result = run_hook("mcp-compliance-monitor.py", {
            "hook_event_name": "PostToolUse",
            "tool_name": "mcp__other__thing",
            "tool_input": {},
        }, tmp_home)
        assert result.returncode == 0
        assert result.stdout.strip() == ""

    def test_sigma_tool_call_exits_clean(self, tmp_home):
        result = run_hook("mcp-compliance-monitor.py", {
            "hook_event_name": "PostToolUse",
            "tool_name": "mcp__sigma-verify__init",
            "tool_input": {},
            "tool_response": "providers: openai, google",
        }, tmp_home)
        assert result.returncode == 0
        if result.stdout.strip():
            assert isinstance(json.loads(result.stdout), dict)


# ─── Cross-cutting ───


class TestAllHooksHandleGarbage:
    """Every shipped hook should handle garbage stdin gracefully."""

    @pytest.mark.parametrize("script", SHIPPED_HOOKS)
    def test_garbage_stdin(self, script, tmp_home):
        result = run_hook(script, "not json at all {{{}}}", tmp_home, raw=True)
        assert result.returncode == 0

    @pytest.mark.parametrize("script", SHIPPED_HOOKS)
    def test_empty_stdin(self, script, tmp_home):
        result = run_hook(script, "", tmp_home, raw=True)
        assert result.returncode == 0

    @pytest.mark.parametrize("script", SHIPPED_HOOKS)
    def test_wrong_event_type(self, script, tmp_home):
        """Scripts should handle events they don't care about."""
        result = run_hook(script, {
            "hook_event_name": "Notification",
            "tool_name": "irrelevant",
        }, tmp_home)
        assert result.returncode == 0

    @pytest.mark.parametrize("script", SHIPPED_HOOKS)
    def test_stdout_is_json_or_empty(self, script, tmp_home):
        result = run_hook(script, {"hook_event_name": "Stop"}, tmp_home)
        assert result.returncode == 0
        if result.stdout.strip():
            assert isinstance(json.loads(result.stdout), dict)


def test_plugin_root_layout():
    """The files the hooks import from each other all ship in hooks/."""
    for name in ("sigma_paths.py", "gate_checks.py", "workspace_write.py", "audit-calibration-gate.py"):
        assert (HOOKS_DIR / name).is_file(), name
    assert (PLUGIN_ROOT / "framework" / "bin" / "chain-evaluator.py").is_file()
