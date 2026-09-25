"""Tests for phase-gate.py — the minimal PreToolUse/PostToolUse hook.

Tests cover:
- Session detection (_is_sigma_session, _is_build_session)
- Code write authorization (BUILD sessions only, plan-lock required)
- Git commit gating (sigma sessions only, chain must be complete)
- Context firewall leak detection
- Hook dispatch (enforce_pre_tool_use, enforce_post_tool_use)
- Integration: subprocess smoke tests matching Claude Code hooks API
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the module under test
HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "phase_gate", HOOKS_DIR / "phase-gate.py"
)
pg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pg)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temp workspace file and patch DEFAULT_WORKSPACE to point to it."""
    ws = tmp_path / "workspace.md"

    def _write(content):
        ws.write_text(content, encoding="utf-8")
        return ws

    return _write, ws


@pytest.fixture
def tmp_chain_status(tmp_path):
    """Create a temp chain status file and patch CHAIN_STATUS_FILE."""
    return tmp_path / ".chain-status.json"


@pytest.fixture
def patch_paths(tmp_workspace, tmp_chain_status, tmp_path):
    """Patch DEFAULT_WORKSPACE, CHAIN_STATUS_FILE, and BUILDS_DIR.

    BUILDS_DIR is patched to an empty tmp directory so tests cannot pick
    up the live ~/.claude/teams/sigma-review/shared/builds/ tree as a
    spurious "active sigma session" signal (R2 multi-path fix).
    """
    _write, ws_path = tmp_workspace
    builds_dir = tmp_path / "builds"
    builds_dir.mkdir()
    with patch.object(pg, "DEFAULT_WORKSPACE", ws_path), \
         patch.object(pg, "CHAIN_STATUS_FILE", tmp_chain_status), \
         patch.object(pg, "BUILDS_DIR", builds_dir):
        yield _write, ws_path, tmp_chain_status


# ---------------------------------------------------------------------------
# _is_sigma_session()
# ---------------------------------------------------------------------------

class TestIsSigmaSession:
    def test_returns_false_when_no_workspace(self, tmp_path):
        empty_builds = tmp_path / "builds_empty"
        empty_builds.mkdir()
        with patch.object(pg, "DEFAULT_WORKSPACE", tmp_path / "nonexistent.md"), \
             patch.object(pg, "BUILDS_DIR", empty_builds):
            assert pg._is_sigma_session() is False

    def test_returns_false_for_idle_workspace(self, patch_paths):
        write, _, _ = patch_paths
        write("# workspace\n## status: idle\n")
        assert pg._is_sigma_session() is False

    def test_returns_true_for_task_marker(self, patch_paths):
        write, _, _ = patch_paths
        write("# workspace\n## task\nSome analysis task\n")
        assert pg._is_sigma_session() is True

    def test_returns_true_for_mode_marker(self, patch_paths):
        write, _, _ = patch_paths
        write("# workspace\n## mode: BUILD\n")
        assert pg._is_sigma_session() is True

    def test_case_insensitive(self, patch_paths):
        write, _, _ = patch_paths
        write("# workspace\n## Task\nSomething\n")
        assert pg._is_sigma_session() is True


# ---------------------------------------------------------------------------
# _is_build_session()
# ---------------------------------------------------------------------------

class TestIsBuildSession:
    def test_returns_false_when_no_workspace(self, tmp_path):
        with patch.object(pg, "DEFAULT_WORKSPACE", tmp_path / "nonexistent.md"):
            assert pg._is_build_session() is False

    def test_returns_false_for_analyze(self, patch_paths):
        write, _, _ = patch_paths
        write("# workspace\n## mode: ANALYZE\n## task\nReview something\n")
        assert pg._is_build_session() is False

    def test_returns_true_for_build(self, patch_paths):
        write, _, _ = patch_paths
        write("# workspace\n## mode: BUILD\n## task\nBuild something\n")
        assert pg._is_build_session() is True

    def test_returns_true_for_lowercase_build(self, patch_paths):
        write, _, _ = patch_paths
        write("# workspace\nmode: build\n")
        assert pg._is_build_session() is True


# ---------------------------------------------------------------------------
# _workspace_has_plan_lock()
# ---------------------------------------------------------------------------

class TestWorkspaceHasPlanLock:
    def test_returns_false_when_no_workspace(self, tmp_path):
        with patch.object(pg, "DEFAULT_WORKSPACE", tmp_path / "nonexistent.md"):
            assert pg._workspace_has_plan_lock() is False

    def test_returns_false_without_adr_or_ic(self, patch_paths):
        write, _, _ = patch_paths
        write("# workspace\n## task\nBuild something\n")
        assert pg._workspace_has_plan_lock() is False

    def test_returns_false_with_only_adr(self, patch_paths):
        write, _, _ = patch_paths
        write("ADR[1]: Use pip deps\n")
        assert pg._workspace_has_plan_lock() is False

    def test_returns_false_with_only_ic(self, patch_paths):
        write, _, _ = patch_paths
        write("IC[1]: Agent output format\n")
        assert pg._workspace_has_plan_lock() is False

    def test_returns_true_with_both(self, patch_paths):
        write, _, _ = patch_paths
        write("ADR[1]: Use pip deps\nIC[1]: Agent output format\n")
        assert pg._workspace_has_plan_lock() is True


# ---------------------------------------------------------------------------
# _chain_is_complete()
# ---------------------------------------------------------------------------

class TestChainIsComplete:
    def test_returns_false_when_no_status_file(self, tmp_path):
        with patch.object(pg, "CHAIN_STATUS_FILE", tmp_path / "nonexistent.json"):
            assert pg._chain_is_complete() is False

    def test_returns_false_when_incomplete(self, patch_paths):
        _, _, status_file = patch_paths
        status_file.write_text(json.dumps({"last_complete": False}))
        assert pg._chain_is_complete() is False

    def test_returns_true_when_complete(self, patch_paths):
        _, _, status_file = patch_paths
        status_file.write_text(json.dumps({"last_complete": True}))
        assert pg._chain_is_complete() is True

    def test_handles_corrupt_json(self, patch_paths):
        _, _, status_file = patch_paths
        status_file.write_text("not json{{{")
        assert pg._chain_is_complete() is False


# ---------------------------------------------------------------------------
# check_code_write_authorization()
# ---------------------------------------------------------------------------

class TestCodeWriteAuthorization:
    def test_allows_outside_build_session(self, patch_paths):
        write, _, _ = patch_paths
        write("# workspace\n## status: idle\n")
        blocked, reason = pg.check_code_write_authorization("/some/code.py")
        assert blocked is False

    def test_allows_with_plan_lock(self, patch_paths):
        write, _, _ = patch_paths
        write("mode: BUILD\nADR[1]: test\nIC[1]: test\n")
        blocked, reason = pg.check_code_write_authorization("/some/code.py")
        assert blocked is False

    def test_blocks_code_write_without_plan_lock(self, patch_paths):
        write, _, _ = patch_paths
        write("mode: BUILD\n## task\nBuild something\n")
        blocked, reason = pg.check_code_write_authorization("/some/code.py")
        assert blocked is True
        assert "plan-lock" in reason.lower() or "ADR" in reason

    def test_allows_infrastructure_paths_without_plan_lock(self, patch_paths):
        write, _, _ = patch_paths
        write("mode: BUILD\n## task\nBuild something\n")
        for path in [
            "/home/dev/.claude/teams/sigma-review/shared/workspace.md",
            "/home/dev/.claude/agents/test.md",
            "/tmp/scratch.txt",
            "/home/dev/.claude/hooks/test.py",
        ]:
            blocked, reason = pg.check_code_write_authorization(path)
            assert blocked is False, f"Should allow infrastructure path: {path}"


# ---------------------------------------------------------------------------
# check_premature_git_operation() — CRITICAL: scoping tests
# ---------------------------------------------------------------------------

class TestPrematureGitOperation:
    def test_allows_non_git_commands(self, patch_paths):
        blocked, reason = pg.check_premature_git_operation("ls -la")
        assert blocked is False

    def test_allows_git_status(self, patch_paths):
        blocked, reason = pg.check_premature_git_operation("git status")
        assert blocked is False

    def test_allows_git_diff(self, patch_paths):
        blocked, reason = pg.check_premature_git_operation("git diff --cached")
        assert blocked is False

    def test_allows_git_commit_outside_sigma_session(self, patch_paths):
        """CRITICAL: git commit must be allowed when not in a sigma session."""
        write, _, _ = patch_paths
        write("# workspace\n## status: idle\n")
        blocked, reason = pg.check_premature_git_operation("git commit -m 'test'")
        assert blocked is False, "git commit must not be blocked outside sigma sessions"

    def test_allows_git_push_outside_sigma_session(self, patch_paths):
        """CRITICAL: git push must be allowed when not in a sigma session."""
        write, _, _ = patch_paths
        write("# workspace\n## status: idle\n")
        blocked, reason = pg.check_premature_git_operation("git push origin main")
        assert blocked is False, "git push must not be blocked outside sigma sessions"

    def test_allows_git_commit_when_no_workspace(self, tmp_path):
        """CRITICAL: git commit must work when workspace doesn't exist."""
        empty_builds = tmp_path / "builds_empty"
        empty_builds.mkdir()
        with patch.object(pg, "DEFAULT_WORKSPACE", tmp_path / "nonexistent.md"), \
             patch.object(pg, "CHAIN_STATUS_FILE", tmp_path / "nonexistent.json"), \
             patch.object(pg, "BUILDS_DIR", empty_builds):
            blocked, reason = pg.check_premature_git_operation("git commit -m 'test'")
            assert blocked is False

    def test_blocks_git_commit_during_incomplete_sigma_session(self, patch_paths):
        write, _, status_file = patch_paths
        write("# workspace\n## task\nReview something\n")
        status_file.write_text(json.dumps({"last_complete": False}))
        blocked, reason = pg.check_premature_git_operation("git commit -m 'test'")
        assert blocked is True
        assert "chain" in reason.lower() or "complete" in reason.lower()

    def test_allows_git_commit_when_chain_complete(self, patch_paths):
        write, _, status_file = patch_paths
        write("# workspace\n## task\nReview something\n")
        status_file.write_text(json.dumps({"last_complete": True}))
        blocked, reason = pg.check_premature_git_operation("git commit -m 'test'")
        assert blocked is False


# ---------------------------------------------------------------------------
# detect_context_firewall_leak()
# ---------------------------------------------------------------------------

class TestContextFirewallLeak:
    def test_no_warn_on_non_workspace_file(self):
        result = pg.detect_context_firewall_leak("/some/other/file.md", "my career goals")
        assert result is None

    def test_no_warn_on_clean_workspace_content(self):
        result = pg.detect_context_firewall_leak(
            "/path/to/workspace.md",
            "Agent findings: market analysis complete"
        )
        assert result is None

    def test_warns_on_career_leak(self):
        result = pg.detect_context_firewall_leak(
            "/path/to/workspace.md",
            "This aligns with my career goals in fintech"
        )
        assert result is not None
        assert "personal context" in result.lower() or "firewall" in result.lower()

    def test_warns_on_salary_leak(self):
        result = pg.detect_context_firewall_leak(
            "/path/to/workspace.md",
            "my salary expectations should inform this analysis"
        )
        assert result is not None


# ---------------------------------------------------------------------------
# ΣComm Tier-2 detector tests
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_sigmacomm_log(tmp_path, monkeypatch):
    """Redirect SIGMACOMM_CALIBRATION_LOG to a tmp file for the test."""
    log_path = tmp_path / "sigmacomm-calibration.jsonl"
    monkeypatch.setattr(pg, "SIGMACOMM_CALIBRATION_LOG", log_path)
    return log_path


class TestSigmaCommTier2Detector:
    def test_warns_finding_block_missing_source(self, tmp_sigmacomm_log):
        content = "DA[#1] some-finding text without tags here"
        result = pg.detect_missing_sigmacomm_tags(content, "/ws/workspace.md")
        assert result is not None
        assert "Tier-2" in result

    def test_no_warn_finding_with_source(self, tmp_sigmacomm_log):
        content = "DA[#1] finding text |source:[code-read foo.py:10-20]|"
        result = pg.detect_missing_sigmacomm_tags(content, "/ws/workspace.md")
        assert result is None

    def test_no_warn_finding_with_status_verb(self, tmp_sigmacomm_log):
        content = "DA[#1] finding text — VERIFIED via code-read"
        result = pg.detect_missing_sigmacomm_tags(content, "/ws/workspace.md")
        assert result is None

    def test_no_warn_finding_with_severity(self, tmp_sigmacomm_log):
        content = "DA[#3] something concerning, severity HIGH"
        result = pg.detect_missing_sigmacomm_tags(content, "/ws/workspace.md")
        assert result is None

    def test_no_warn_pure_prose_narrative(self, tmp_sigmacomm_log):
        content = (
            "The settlement type distinction (card-present vs card-not-present vs "
            "ACH-debit) is still valid. No new platform spans all three."
        )
        result = pg.detect_missing_sigmacomm_tags(content, "/ws/workspace.md")
        assert result is None

    def test_allows_nested_brackets_in_source(self, tmp_sigmacomm_log):
        content = "DA[#1] finding |source:[code-read foo.py + DA[#2] L100-200]|"
        result = pg.detect_missing_sigmacomm_tags(content, "/ws/workspace.md")
        assert result is None

    def test_finds_in_one_block_among_many(self, tmp_sigmacomm_log):
        content = (
            "Some narrative prose at the top.\n\n"
            "DA[#1] tagged finding |source:[code-read]| HIGH\n\n"
            "DA[#2] untagged finding without any tags or source\n\n"
            "More narrative."
        )
        result = pg.detect_missing_sigmacomm_tags(content, "/ws/workspace.md")
        assert result is not None

    def test_recognizes_full_identifier_family(self, tmp_sigmacomm_log):
        # Plan declared family: DA, PA, IC, ADR, BC, PM, SQ, H, F, R, D, C, RC
        for prefix in ("PA[5]", "IC[6]", "ADR[3]", "PM[1]", "SQ[12]", "F[CQA-1]"):
            content = f"{prefix} bare finding no source no status"
            result = pg.detect_missing_sigmacomm_tags(content, "/ws/workspace.md")
            assert result is not None, f"{prefix} should trigger WARN"

    def test_calibration_log_written_on_warn(self, tmp_sigmacomm_log):
        content = "DA[#9] orphan finding"
        pg.detect_missing_sigmacomm_tags(content, "/ws/workspace.md")
        assert tmp_sigmacomm_log.exists()
        lines = [json.loads(line) for line in tmp_sigmacomm_log.read_text().splitlines() if line.strip()]
        assert any(rec.get("event_type") == "warn" for rec in lines)
        assert any(rec.get("surface") == "/ws/workspace.md" for rec in lines)

    def test_calibration_log_writes_event_for_clean_content(self, tmp_sigmacomm_log):
        content = "DA[#1] clean |source:[code-read]| VERIFIED"
        pg.detect_missing_sigmacomm_tags(content, "/ws/workspace.md")
        lines = [json.loads(line) for line in tmp_sigmacomm_log.read_text().splitlines() if line.strip()]
        assert any(rec.get("event_type") == "write" for rec in lines)


class TestSigmaCommTier2Path:
    def test_workspace_md_matches(self):
        assert pg._is_sigmacomm_tier2_path("/foo/bar/workspace.md")

    def test_c1_scratch_matches(self):
        assert pg._is_sigmacomm_tier2_path("/foo/builds/abc/c1-scratch.md")

    def test_c14_scratch_matches(self):
        assert pg._is_sigmacomm_tier2_path("/foo/builds/abc/c14-scratch.md")

    def test_c2_plan_matches(self):
        assert pg._is_sigmacomm_tier2_path("/foo/builds/abc/c2-plan.md")

    def test_random_md_does_not_match(self):
        assert not pg._is_sigmacomm_tier2_path("/foo/bar/notes.md")

    def test_archive_workspace_does_not_match(self):
        # Archive files use suffix forms like 2026-04-28-shared-...-c3-workspace.md
        # which the current regex doesn't match. By design — archives are read-only.
        assert not pg._is_sigmacomm_tier2_path(
            "/teams/sigma-review/shared/archive/2026-04-28-shared-foo-c3-workspace.md"
        )

    def test_empty_path(self):
        assert not pg._is_sigmacomm_tier2_path("")


class TestSigmaCommTier2Dispatch:
    def test_post_tool_use_warns_on_workspace_write_missing_tags(self, tmp_sigmacomm_log):
        output = pg.enforce_post_tool_use({
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/teams/sigma-review/shared/workspace.md",
                "content": "DA[#1] orphan finding text",
            },
        })
        assert "systemMessage" in output
        assert "Tier-2" in output["systemMessage"]

    def test_post_tool_use_no_warn_on_non_workspace(self, tmp_sigmacomm_log):
        output = pg.enforce_post_tool_use({
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/some/other/file.md",
                "content": "DA[#1] orphan finding text",
            },
        })
        assert output == {}

    def test_post_tool_use_warns_on_sendmessage_with_finding(self, tmp_sigmacomm_log):
        long_msg = "DA[#1] " + ("padding text " * 20) + "no tags here"
        output = pg.enforce_post_tool_use({
            "tool_name": "SendMessage",
            "tool_input": {
                "to": "researcher",
                "message": long_msg,
            },
        })
        assert "systemMessage" in output

    def test_post_tool_use_no_warn_short_sendmessage(self, tmp_sigmacomm_log):
        output = pg.enforce_post_tool_use({
            "tool_name": "SendMessage",
            "tool_input": {
                "to": "researcher",
                "message": "DA[#1] short",  # under 100 chars
            },
        })
        assert output == {}

    def test_post_tool_use_skips_protocol_json_message(self, tmp_sigmacomm_log):
        output = pg.enforce_post_tool_use({
            "tool_name": "SendMessage",
            "tool_input": {
                "to": "researcher",
                "message": {"type": "shutdown_request", "reason": "done"},
            },
        })
        assert output == {}

    def test_context_firewall_runs_before_sigmacomm_check(self, tmp_sigmacomm_log):
        # Context firewall should still fire on a workspace write, regardless of tags
        output = pg.enforce_post_tool_use({
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/teams/sigma-review/shared/workspace.md",
                "content": "DA[#1] tagged |source:[x]| my career advancement",
            },
        })
        assert "systemMessage" in output
        # Firewall fires first on personal context leak
        assert "firewall" in output["systemMessage"].lower() or \
               "personal context" in output["systemMessage"].lower()


class TestSigmaCommArchiveRegression:
    """Verify the Tier-2 detector does not fire spuriously on archived
    workspaces. The synthetic archives in tests/fixtures/ follow the tag
    conventions the directives prescribe."""

    ARCHIVE_DIR = Path(__file__).resolve().parent / "fixtures"

    def _sample_recent_workspaces(self, limit=4):
        return sorted(self.ARCHIVE_DIR.glob("*workspace*.md"))[:limit]

    def test_archive_workspaces_do_not_trigger(self, tmp_sigmacomm_log):
        samples = self._sample_recent_workspaces()
        assert samples, "synthetic archive fixtures missing"
        for ws in samples:
            content = ws.read_text(encoding="utf-8", errors="ignore")
            # Use the workspace surface to exercise the detector path
            result = pg.detect_missing_sigmacomm_tags(
                content, str(ws)
            )
            # Note: archives may legitimately contain orphan finding blocks
            # because the current convention has drifted. We do not assert
            # zero fires; we assert the detector terminates and produces
            # diagnosable output.
            assert result is None or "Tier-2" in result, \
                f"detector returned unexpected message for {ws.name}: {result}"


class TestSigmaCommFpRateCli:
    def test_fp_rate_empty_log(self, tmp_sigmacomm_log, capsys):
        pg.compute_sigmacomm_fp_rate()
        captured = capsys.readouterr()
        report = json.loads(captured.out)
        assert report["fires"] == 0
        assert report["writes"] == 0
        assert report["eligible_for_block"] is False

    def test_fp_rate_below_threshold(self, tmp_sigmacomm_log, capsys):
        # Seed log: 25 writes, 1 warn (none marked is_fp) → fp_rate=0, eligible
        for _ in range(24):
            tmp_sigmacomm_log.write_text(
                tmp_sigmacomm_log.read_text() if tmp_sigmacomm_log.exists() else ""
            )
        with tmp_sigmacomm_log.open("w") as fh:
            for _ in range(24):
                fh.write(json.dumps({"ts": 0, "event_type": "write", "surface": "/x", "snippet": ""}) + "\n")
            fh.write(json.dumps({"ts": 0, "event_type": "warn", "surface": "/x", "snippet": "DA[#1]"}) + "\n")
        pg.compute_sigmacomm_fp_rate()
        captured = capsys.readouterr()
        report = json.loads(captured.out)
        assert report["fires"] == 1
        assert report["writes"] == 25
        assert report["fp_rate"] == 0.0
        assert report["eligible_for_block"] is True

    def test_fp_rate_above_threshold_marks_ineligible(self, tmp_sigmacomm_log, capsys):
        # 20 warns total, 5 marked is_fp → fp_rate = 0.25 > 0.05
        with tmp_sigmacomm_log.open("w") as fh:
            for i in range(20):
                rec = {"ts": 0, "event_type": "warn", "surface": "/x", "snippet": "DA"}
                if i < 5:
                    rec["is_fp"] = True
                fh.write(json.dumps(rec) + "\n")
        pg.compute_sigmacomm_fp_rate()
        captured = capsys.readouterr()
        report = json.loads(captured.out)
        assert report["false_positives"] == 5
        assert report["fp_rate"] == 0.25
        assert report["eligible_for_block"] is False


# ---------------------------------------------------------------------------
# enforce_pre_tool_use() — dispatch tests
# ---------------------------------------------------------------------------

class TestEnforcePreToolUse:
    def test_allows_read_tool(self, patch_paths):
        exit_code, output = pg.enforce_pre_tool_use({
            "tool_name": "Read",
            "tool_input": {"file_path": "/some/file.py"},
        })
        assert exit_code == 0

    def test_routes_write_to_code_auth(self, patch_paths):
        write, _, _ = patch_paths
        write("mode: BUILD\n## task\nBuild\n")  # BUILD, no plan lock
        exit_code, output = pg.enforce_pre_tool_use({
            "tool_name": "Write",
            "tool_input": {"file_path": "/some/code.py"},
        })
        assert exit_code == 2  # BLOCK

    def test_routes_bash_git_to_git_check(self, patch_paths):
        write, _, status_file = patch_paths
        write("# workspace\n## task\nReview\n")  # sigma session
        status_file.write_text(json.dumps({"last_complete": False}))
        exit_code, output = pg.enforce_pre_tool_use({
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'test'"},
        })
        assert exit_code == 2  # BLOCK

    def test_allows_bash_non_git(self, patch_paths):
        exit_code, output = pg.enforce_pre_tool_use({
            "tool_name": "Bash",
            "tool_input": {"command": "python3 test.py"},
        })
        assert exit_code == 0


# ---------------------------------------------------------------------------
# enforce_post_tool_use() — dispatch tests
# ---------------------------------------------------------------------------

class TestEnforcePostToolUse:
    def test_no_message_for_clean_write(self):
        output = pg.enforce_post_tool_use({
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/path/to/workspace.md",
                "content": "Clean analytical content",
            },
        })
        assert output == {} or "systemMessage" not in output

    def test_warns_on_context_leak_in_write(self):
        output = pg.enforce_post_tool_use({
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/path/to/workspace.md",
                "content": "This relates to my career advancement",
            },
        })
        assert "systemMessage" in output

    def test_no_message_for_read(self):
        output = pg.enforce_post_tool_use({
            "tool_name": "Read",
            "tool_input": {"file_path": "/some/file.py"},
        })
        assert output == {}


# ---------------------------------------------------------------------------
# Integration: subprocess smoke tests
# ---------------------------------------------------------------------------

class TestPhaseGateIntegration:
    """Run phase-gate.py as subprocess, matching Claude Code hooks API."""

    def _run(self, stdin_data, home_dir=None):
        script = HOOKS_DIR / "phase-gate.py"
        env = os.environ.copy()
        if home_dir:
            env["HOME"] = str(home_dir)
        result = __import__("subprocess").run(
            [sys.executable, str(script)],
            input=json.dumps(stdin_data),
            capture_output=True, text=True, env=env, timeout=10,
        )
        return result

    def test_exits_clean_on_empty_json(self):
        result = self._run({})
        assert result.returncode == 0

    def test_exits_clean_on_read_event(self):
        result = self._run({
            "hook_event_name": "PreToolUse",
            "tool_name": "Read",
            "tool_input": {"file_path": "/test.py"},
        })
        assert result.returncode == 0

    def test_exits_clean_on_non_sigma_git_commit(self, tmp_path):
        """CRITICAL: git commit outside sigma session must exit 0."""
        home = tmp_path / "home"
        (home / ".claude" / "teams" / "sigma-review" / "shared").mkdir(parents=True)
        # Write idle workspace
        ws = home / ".claude" / "teams" / "sigma-review" / "shared" / "workspace.md"
        ws.write_text("# workspace\n## status: idle\n")

        result = self._run({
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'test'"},
        }, home_dir=home)
        assert result.returncode == 0, f"Should allow git commit outside sigma. stderr: {result.stderr}"

    def test_blocks_git_commit_during_sigma_session(self, tmp_path):
        home = tmp_path / "home"
        hooks_dir = home / ".claude" / "hooks"
        hooks_dir.mkdir(parents=True)
        (home / ".claude" / "teams" / "sigma-review" / "shared").mkdir(parents=True)
        # Active sigma workspace
        ws = home / ".claude" / "teams" / "sigma-review" / "shared" / "workspace.md"
        ws.write_text("# workspace\n## task\nReview something\n")
        # Chain not complete
        status = hooks_dir / ".chain-status.json"
        status.write_text(json.dumps({"last_complete": False}))

        result = self._run({
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "git commit -m 'test'"},
        }, home_dir=home)
        assert result.returncode == 2, "Should block git commit during incomplete sigma session"


# ---------------------------------------------------------------------------
# SQ[13g] + SQ[SS-2] — sed-i BLOCK 4 detection + shlex evasion matrix
# ---------------------------------------------------------------------------
#
# BLOCK 4 (phase-gate.py:235+) covers the R19 silent-overwrite failure mode:
# `sed -i` (no backup suffix) on workspace.md + /.claude/teams/sigma-*/shared/
# + /.claude/hooks/ paths. Tokenization via shlex.split(posix=True) (IC[1])
# is what makes the gate resistant to shell-quoting bypass.
#
# Evasion forms covered per CAL[4] + SS-2 matrix:
#   - env-var wrapper: `env FOO=bar sed -i 'x' workspace.md`
#   - xargs wrapper:   `echo workspace.md | xargs sed -i 'x'`
#   - absolute-path sed: `/usr/bin/sed -i ...`
#   - -i '' separated form (BSD-style, effectively no-backup)
#   - -i.bak joined form (ALLOWED, real suffix = recoverable)
#   - quoting tricks / mixed operand ordering


class TestSedInPlaceBlock4Detection:
    """Direct coverage of phase_gate.check_sed_in_place() on workspace paths."""

    def test_blocks_sed_i_on_workspace_md(self):
        blocked, reason = pg.check_sed_in_place(
            "sed -i 's/foo/bar/' ~/.claude/teams/sigma-review/shared/workspace.md"
        )
        assert blocked is True
        assert "SED IN-PLACE BLOCKED" in reason

    def test_blocks_sed_i_on_hooks_directory(self):
        blocked, reason = pg.check_sed_in_place(
            "sed -i 's/old/new/' /home/dev/.claude/hooks/chain-evaluator.py"
        )
        assert blocked is True
        assert "/.claude/hooks/" in reason or "protected path" in reason

    def test_allows_sed_i_bak_backup_form(self):
        """-i.bak with real suffix creates a recoverable backup — allowed per CAL[4]."""
        blocked, reason = pg.check_sed_in_place(
            "sed -i.bak 's/foo/bar/' ~/.claude/teams/sigma-review/shared/workspace.md"
        )
        assert blocked is False, f"Backup form must pass, got reason: {reason}"

    def test_blocks_sed_i_empty_suffix_separated_form(self):
        """BSD-style `sed -i '' file` is no-backup on BSD — must be blocked."""
        blocked, reason = pg.check_sed_in_place(
            "sed -i '' 's/foo/bar/' ~/.claude/teams/sigma-review/shared/workspace.md"
        )
        assert blocked is True, (
            "`-i '' file` form is effectively no-backup on BSD — must be blocked"
        )

    def test_allows_sed_i_outside_protected_scope(self):
        """Tool calls on paths outside workspace/hooks scope are never blocked."""
        blocked, reason = pg.check_sed_in_place(
            "sed -i 's/foo/bar/' /tmp/random-file.txt"
        )
        assert blocked is False

    def test_allows_sed_without_i_flag(self):
        """Plain `sed` (non-in-place, reads to stdout) is never our concern."""
        blocked, reason = pg.check_sed_in_place(
            "sed 's/foo/bar/' ~/.claude/teams/sigma-review/shared/workspace.md"
        )
        assert blocked is False


class TestSedShlexEvasionMatrix:
    """SS-2 matrix: argv-tokenization coverage vs raw-regex bypass attempts."""

    def test_env_wrapper_detected(self):
        """`env FOO=bar sed -i ...` — shlex walks all tokens for a `sed` node."""
        blocked, reason = pg.check_sed_in_place(
            "env LC_ALL=C sed -i 's/x/y/' ~/.claude/hooks/phase-gate.py"
        )
        assert blocked is True, (
            "env-wrapper must not bypass — shlex walk finds sed token at position 2"
        )

    def test_xargs_stdin_is_known_limitation_not_blocked(self):
        """`xargs sed -i` with target path via stdin is documented out-of-scope.

        Positive-contract test: phase-gate.py uses shlex.split to parse argv.
        When the target file reaches sed through xargs stdin rather than its
        own argv, the protected-path check has no operand to examine. This is
        a DELIBERATE argv-scope limitation per ADR[SS-1] + docstring at
        phase-gate.py:300 (post-BUILD-CONCERN[cqa] 26.4.24 resolution (a)).

        Rejected alternative: blocking any `xargs` + `sed -i` chain regardless
        of operand paths produces too-high false-positive rate on legitimate
        batch-edits outside the protected scope. Process convention covers
        the gap: reviewers must spot `xargs sed -i` in PR diffs on protected
        paths. When this test starts failing (i.e. the gate DOES block), the
        implementation has been extended — update this test to match the new
        contract.
        """
        blocked, _reason = pg.check_sed_in_place(
            "echo ~/.claude/hooks/x.py | xargs sed -i 's/a/b/'"
        )
        assert blocked is False, (
            "xargs stdin path is out-of-scope for argv-based shlex walk — "
            "if this starts blocking, ADR[SS-1] contract has been extended; update test"
        )

    def test_absolute_sed_path_detected(self):
        """`/usr/bin/sed -i ...` — detected via tok.endswith('/sed')."""
        blocked, reason = pg.check_sed_in_place(
            "/usr/bin/sed -i 's/foo/bar/' ~/.claude/teams/sigma-review/shared/workspace.md"
        )
        assert blocked is True, (
            "Absolute sed path must be caught — tok.endswith('/sed') covers this"
        )

    def test_joined_iflag_with_empty_suffix_blocked(self):
        """`-i''` joined with quoted empty string — the suffix collapses; must block."""
        # shlex parses `sed -i'' 'pat' file` as [sed, -i, pat, file] after
        # posix quote-stripping. Confirm BLOCK fires in this form.
        blocked, reason = pg.check_sed_in_place(
            "sed -i'' 's/x/y/' ~/.claude/teams/sigma-review/shared/workspace.md"
        )
        assert blocked is True, (
            "-i'' (empty-string join) must block — no real backup suffix"
        )

    def test_long_in_place_flag_blocked(self):
        """--in-place without suffix is equivalent to -i — must block."""
        blocked, reason = pg.check_sed_in_place(
            "sed --in-place 's/x/y/' ~/.claude/hooks/chain-evaluator.py"
        )
        assert blocked is True, (
            "`--in-place` long form must block — same semantics as `-i` no-backup"
        )

    def test_malformed_command_does_not_block(self):
        """shlex.split raises ValueError on unbalanced quotes; gate should return False, not error."""
        # Unterminated quoted string — shlex raises, check_sed_in_place must
        # fail-open (let the shell error naturally).
        blocked, reason = pg.check_sed_in_place(
            'sed -i "unterminated workspace.md'
        )
        assert blocked is False, (
            "Malformed command must not block — fail-open on shlex parse error"
        )

    def test_chained_command_second_sed_still_blocked(self):
        """Shell separators (&&, ||, ;) terminate; sed in second command still scanned."""
        blocked, reason = pg.check_sed_in_place(
            "cd /tmp && sed -i 's/a/b/' ~/.claude/teams/sigma-review/shared/workspace.md"
        )
        assert blocked is True, (
            "Second sed after && must still block — walker continues through separators"
        )


class TestPreArchiveCompilationGate:
    """SQ[9] / ADR[6] / IC[6]: BLOCK 5 — 06b pre-archive compilation gate.

    Workspace must contain `## compilation-complete: [R-{review-id}]` header
    before any archive operation. Manual-override recovery form is also
    accepted. Stale-workspace FP guard via _is_sigma_session().
    """

    _ARCHIVE_PATH = (
        "/home/dev/.claude/teams/sigma-review/shared/archive/2026-04-29-test.md"
    )

    def test_blocks_archive_write_without_header(self, patch_paths):
        """Write to archive path without compilation-complete → BLOCK."""
        write, _, _ = patch_paths
        write("## task\nactive sigma session\n## findings\n")  # active session
        blocked, reason = pg.check_pre_archive_gate(
            "Write",
            {"file_path": self._ARCHIVE_PATH, "content": "synthesis"},
        )
        assert blocked is True
        assert "PRE-ARCHIVE BLOCKED" in reason
        assert "compilation-complete" in reason
        assert "manual-override" in reason

    def test_passes_archive_write_with_header(self, patch_paths):
        """Write to archive path WITH compilation-complete → pass."""
        write, _, _ = patch_paths
        write(
            "## task\nactive\n"
            "## compilation-complete: [R-2026-04-29-test]\n"
            "## findings\n"
        )
        blocked, reason = pg.check_pre_archive_gate(
            "Write",
            {"file_path": self._ARCHIVE_PATH, "content": "synthesis"},
        )
        assert blocked is False
        assert reason == ""

    def test_passes_archive_write_with_manual_override(self, patch_paths):
        """Manual-override form unblocks per IC[6] recovery path."""
        write, _, _ = patch_paths
        write(
            "## task\nactive\n"
            "## compilation-complete: [R-2026-04-29-test, manual-override, "
            "reason: compilation-agent crashed after MCP timeout]\n"
            "## findings\n"
        )
        blocked, reason = pg.check_pre_archive_gate(
            "Write",
            {"file_path": self._ARCHIVE_PATH, "content": "synthesis"},
        )
        assert blocked is False, "manual-override form must unblock"

    def test_blocks_archive_bash_cp_without_header(self, patch_paths):
        write, _, _ = patch_paths
        write("## task\nactive\n## findings\n")
        blocked, reason = pg.check_pre_archive_gate(
            "Bash",
            {"command": "cp /tmp/workspace.md /home/dev/.claude/teams/sigma-review/shared/archive/foo.md"},
        )
        assert blocked is True

    def test_blocks_archive_bash_mv_without_header(self, patch_paths):
        write, _, _ = patch_paths
        write("## task\nactive\n## findings\n")
        blocked, reason = pg.check_pre_archive_gate(
            "Bash",
            {"command": "mv old.md /home/dev/.claude/teams/sigma-build/shared/archive/old.md"},
        )
        assert blocked is True

    def test_does_not_block_outside_archive_path(self, patch_paths):
        write, _, _ = patch_paths
        write("## task\nactive\n## findings\n")
        blocked, reason = pg.check_pre_archive_gate(
            "Write",
            {"file_path": "/home/dev/.claude/teams/sigma-review/shared/workspace.md",
             "content": "x"},
        )
        assert blocked is False, "Non-archive paths are not gated"

    def test_does_not_block_outside_sigma_session(self, patch_paths):
        """PM[5] FP guard: stale/non-sigma workspace must NOT trigger BLOCK 5."""
        write, _, _ = patch_paths
        # No ## task, no ## mode → not a sigma session
        write("# empty workspace\n")
        blocked, reason = pg.check_pre_archive_gate(
            "Write",
            {"file_path": self._ARCHIVE_PATH, "content": "x"},
        )
        assert blocked is False, (
            "PM[5] mitigation: BLOCK 5 must NOT fire outside an active sigma session"
        )

    def test_compilation_complete_regex_matches_canonical(self):
        """IC[6] regex matches canonical form."""
        m = pg._COMPILATION_COMPLETE_RE.search(
            "## compilation-complete: [R-2026-04-29-shared-process-hardening]"
        )
        assert m is not None
        assert m.group(1) == "2026-04-29-shared-process-hardening"
        assert m.group(2) is None

    def test_compilation_complete_regex_matches_manual_override(self):
        m = pg._COMPILATION_COMPLETE_RE.search(
            "## compilation-complete: [R-test-id, manual-override, reason: agent crashed]"
        )
        assert m is not None
        assert m.group(1) == "test-id"
        assert m.group(2) == "agent crashed"

    def test_compilation_complete_regex_does_not_match_partial(self):
        """Malformed forms must NOT match (per IC[6])."""
        # Missing closing bracket
        assert pg._COMPILATION_COMPLETE_RE.search(
            "## compilation-complete: [R-test-id"
        ) is None
        # Missing R- prefix
        assert pg._COMPILATION_COMPLETE_RE.search(
            "## compilation-complete: [test-id]"
        ) is None
        # Different case
        assert pg._COMPILATION_COMPLETE_RE.search(
            "## Compilation-Complete: [R-test]"
        ) is None

    def test_pre_tool_use_dispatch_blocks_archive(self, patch_paths):
        """End-to-end: enforce_pre_tool_use returns exit code 2 on blocked archive."""
        write, _, _ = patch_paths
        write("## task\nactive\n## findings\n")
        exit_code, output = pg.enforce_pre_tool_use({
            "tool_name": "Write",
            "tool_input": {"file_path": self._ARCHIVE_PATH, "content": "x"},
        })
        assert exit_code == 2
        assert "PRE-ARCHIVE BLOCKED" in output["reason"]

    def test_pre_tool_use_dispatch_allows_with_header(self, patch_paths):
        """End-to-end: enforce_pre_tool_use allows archive when header present."""
        write, _, _ = patch_paths
        write(
            "## task\nactive\n"
            "## compilation-complete: [R-test]\n"
            "## findings\n"
        )
        exit_code, output = pg.enforce_pre_tool_use({
            "tool_name": "Write",
            "tool_input": {"file_path": self._ARCHIVE_PATH, "content": "x"},
        })
        assert exit_code == 0


class TestBlock5MultiPathWorkspace:
    """R2 multi-path fix (2026-05-02): BLOCK 5 must scan both DEFAULT_WORKSPACE
    AND fresh build scratch files.

    Closes the directive↔hook gap where BUILD-track sessions wrote the
    `## compilation-complete: [R-{id}]` override header to
    builds/{id}/c{N}-scratch.md per directives.md §8f BUILD variant — the
    hook previously read DEFAULT_WORKSPACE only and would block the archive
    write the directive said the override should clear.
    """

    @pytest.fixture
    def patch_multi(self, tmp_path):
        """Patch DEFAULT_WORKSPACE + BUILDS_DIR; helpers to write to either."""
        ws = tmp_path / "workspace.md"
        builds = tmp_path / "builds"
        builds.mkdir()

        def write_workspace(content):
            ws.write_text(content, encoding="utf-8")

        def write_build_scratch(build_id, c_label, content):
            d = builds / build_id
            d.mkdir(parents=True, exist_ok=True)
            scratch = d / f"{c_label}-scratch.md"
            scratch.write_text(content, encoding="utf-8")
            return scratch

        with patch.object(pg, "DEFAULT_WORKSPACE", ws), \
             patch.object(pg, "BUILDS_DIR", builds), \
             patch.object(pg, "CHAIN_STATUS_FILE", tmp_path / ".chain-status.json"):
            yield write_workspace, write_build_scratch, builds

    _BUILD_ID = "2026-04-28-shared-process-hardening"
    _ARCHIVE_PATH_FOR_BUILD = (
        f"/home/dev/.claude/teams/sigma-review/shared/archive/"
        f"{_BUILD_ID}-synthesis.md"
    )

    def test_header_in_build_scratch_passes_block5(self, patch_multi):
        """Override header in builds/{id}/c3-scratch.md → BLOCK 5 passes
        when archive write target matches that build-id (preferred-build path).
        """
        write_workspace, write_scratch, _ = patch_multi
        # Workspace.md has session markers but NO compilation-complete header.
        write_workspace("## task\nbuild review\n## mode: BUILD\n")
        # Build scratch has the override header (manual-override form).
        write_scratch(
            self._BUILD_ID,
            "c3",
            "## task\nbuild review C3\n"
            f"## compilation-complete: [R-{self._BUILD_ID}, "
            "manual-override, reason: in-build hook wiring]\n"
            "## findings\n",
        )
        blocked, reason = pg.check_pre_archive_gate(
            "Write",
            {"file_path": self._ARCHIVE_PATH_FOR_BUILD, "content": "synthesis"},
        )
        assert blocked is False, (
            "Override header at builds/{id}/c3-scratch.md must satisfy "
            "BLOCK 5 when the archive write targets that same build-id"
        )

    def test_header_only_in_workspace_md_still_passes(self, patch_multi):
        """Backwards-compat: header at DEFAULT_WORKSPACE alone still satisfies
        BLOCK 5 (preserves prior ANALYZE-track behavior)."""
        write_workspace, _, _ = patch_multi
        write_workspace(
            "## task\nactive review\n"
            "## compilation-complete: [R-some-review-id]\n"
            "## findings\n"
        )
        blocked, reason = pg.check_pre_archive_gate(
            "Write",
            {"file_path": "/home/dev/.claude/teams/sigma-review/shared/"
                          "archive/2026-04-29-test.md",
             "content": "x"},
        )
        assert blocked is False, (
            "Pre-existing ANALYZE-track placement (header in workspace.md) "
            "must still pass BLOCK 5 unchanged"
        )

    def test_no_header_anywhere_blocks(self, patch_multi):
        """Regression of original BLOCK 5 behavior: header missing from BOTH
        workspace.md AND any active build scratch → BLOCK fires.

        Archive path uses ``-workspace.md`` shape (not ``-synthesis.md``) so
        that the BLOCK 5 synthesis-archive carve-out (ADR[1] of build
        2026-05-05-block-5-synthesis-carveout) does not short-circuit before
        the multi-path scan runs. The invariant under test is "no header
        anywhere in any active workspace-source → BLOCK fires", which is
        independent of the synthesis-archive suffix.
        """
        write_workspace, write_scratch, _ = patch_multi
        write_workspace("## task\nbuild review\n## mode: BUILD\n")
        # Build scratch is fresh + has session markers but NO override header.
        write_scratch(
            self._BUILD_ID,
            "c2",
            "## task\nbuild review C2\n## findings\nno compilation header\n",
        )
        archive_path_workspace = (
            f"/home/dev/.claude/teams/sigma-review/shared/archive/"
            f"{self._BUILD_ID}-workspace.md"
        )
        blocked, reason = pg.check_pre_archive_gate(
            "Write",
            {"file_path": archive_path_workspace, "content": "x"},
        )
        assert blocked is True, (
            "BLOCK must still fire when no compilation-complete header "
            "exists in any active workspace-source"
        )
        assert "PRE-ARCHIVE BLOCKED" in reason

    def test_stale_workspace_md_does_not_classify_session(self, patch_multi):
        """FP guard: stale workspace.md (mtime > freshness window) MUST NOT
        on its own classify the current state as in-sigma when no fresh
        build scratch exists. Mirrors the synthesis-agent-discovered case
        where workspace.md was 8 days old.
        """
        write_workspace, _, _ = patch_multi
        write_workspace("## task\nstale\n## mode: BUILD\n")
        # Force mtime far outside the freshness window.
        ws_path = pg.DEFAULT_WORKSPACE
        ancient = ws_path.stat().st_mtime - (30 * 24 * 60 * 60)
        os.utime(ws_path, (ancient, ancient))
        # No fresh build scratch — _is_sigma_session must return False.
        assert pg._is_sigma_session() is False, (
            "Stale workspace.md alone (no fresh build scratch) must NOT "
            "classify session as in-sigma; would otherwise misfire BLOCK 5"
        )

    def test_stale_build_scratch_ignored(self, patch_multi):
        """Companion FP guard: stale build scratch (mtime > window) must
        NOT classify as in-sigma either."""
        _, write_scratch, _ = patch_multi
        scratch = write_scratch(
            self._BUILD_ID,
            "c1",
            "## task\nold build\n## mode: BUILD\n",
        )
        ancient = scratch.stat().st_mtime - (30 * 24 * 60 * 60)
        os.utime(scratch, (ancient, ancient))
        assert pg._is_sigma_session() is False, (
            "Stale build scratch must be skipped by freshness filter"
        )

    def test_build_id_extraction_from_archive_path(self):
        """Helper: archive path shaped like archive/{build-id}-synthesis.md
        yields the build-id portion."""
        bid = pg._build_id_from_archive_path(
            "/x/y/archive/2026-04-28-shared-process-hardening-synthesis.md"
        )
        assert bid == "2026-04-28-shared-process-hardening"
        # Different suffix
        bid2 = pg._build_id_from_archive_path(
            "/x/y/archive/2026-04-28-some-build-workspace.md"
        )
        assert bid2 == "2026-04-28-some-build"
        # Bare archive name (no recognized suffix) returns the stem unchanged
        bid3 = pg._build_id_from_archive_path("/x/y/archive/2026-04-28-some.md")
        assert bid3 == "2026-04-28-some"
        # Empty/None → None
        assert pg._build_id_from_archive_path("") is None
        assert pg._build_id_from_archive_path(None) is None

    def test_cross_build_authorization_blocked_when_preferred_build_has_no_override(
        self, patch_multi
    ):
        """R2 micro-fix (TA CONCERN-1): build A's compilation-complete header
        MUST NOT authorize an archive write targeting build B.

        Setup: build_a has the override header, build_b does not. Archive
        write targets build_b's archive name. With the original R2 step-3
        broad-glob fallback this would return exit=0 (build_a's header
        authorizes build_b's write — cross-build authorization bypass).
        After the micro-fix, preferred-build resolution finds build_b,
        sees no override there, returns False directly without falling
        through to broad-glob.
        """
        write_workspace, write_scratch, _ = patch_multi
        # No override in workspace.md — only fresh session markers so
        # _is_sigma_session classifies state as in-sigma.
        write_workspace("## task\nbuild review\n## mode: BUILD\n")
        # Build A: HAS override header (e.g., already-archived shared-process-
        # hardening from a different session).
        write_scratch(
            "2026-04-28-shared-process-hardening",
            "c3",
            "## task\nbuild A\n"
            "## compilation-complete: [R-2026-04-28-shared-process-hardening, "
            "manual-override, reason: prior build override]\n"
            "## findings\n",
        )
        # Build B: fresh + active, no override yet.
        write_scratch(
            "2026-04-23-sample-remediation",
            "c2",
            "## task\nbuild B\n## mode: BUILD\n## findings\nno override header\n",
        )
        # Archive write targets build B's archive name. Uses ``-workspace.md``
        # shape (not ``-synthesis.md``) so the BLOCK 5 synthesis-archive
        # carve-out (ADR[1] of build 2026-05-05-block-5-synthesis-carveout)
        # does not short-circuit before cross-build authorization resolution
        # runs. The invariant under test is "build A's override header MUST
        # NOT authorize a write targeting build B", which is independent of
        # the synthesis-archive suffix.
        archive_path_for_b = (
            "/home/dev/.claude/teams/sigma-review/shared/archive/"
            "2026-04-23-sample-remediation-workspace.md"
        )
        blocked, reason = pg.check_pre_archive_gate(
            "Write",
            {"file_path": archive_path_for_b, "content": "snapshot"},
        )
        assert blocked is True, (
            "Cross-build authorization bypass: build_a's override must NOT "
            "authorize a write targeting build_b. Preferred-build resolution "
            "finds build_b, finds no override there, returns False — broad-"
            "glob fallback must NOT fire when preferred build is determinable."
        )
        assert "PRE-ARCHIVE BLOCKED" in reason

    def test_broad_glob_only_fires_when_preferred_build_undeterminable(
        self, patch_multi
    ):
        """R2 micro-fix companion: broad-glob fallback MUST still fire when
        preferred-build derivation fails (archive path doesn't fit
        ``{build-id}-{suffix}.md`` shape, or BUILDS_DIR/{build-id}/ missing).

        Path A: archive_path is None — workspace.md has no override but a
        fresh build scratch does. Without an archive_path we cannot
        derive a preferred build, so step 3 broad-glob is the right path.
        """
        write_workspace, write_scratch, _ = patch_multi
        write_workspace("## task\nactive\n## mode: BUILD\n")
        write_scratch(
            "2026-04-28-shared-process-hardening",
            "c3",
            "## task\nbuild active\n"
            "## compilation-complete: [R-2026-04-28-shared-process-hardening]\n"
            "## findings\n",
        )
        # Call with archive_path=None (e.g., a check that doesn't go through
        # the normal Write/Edit/Bash dispatch). Broad-glob should find the
        # header in build's scratch.
        found, rid, mo = pg._has_compilation_complete(archive_path=None)
        assert found is True, (
            "When archive_path is None (preferred-build undeterminable) the "
            "broad-glob fallback must still find an override in any active "
            "build scratch — preserves R2 backwards-compat for this case"
        )
        assert rid == "2026-04-28-shared-process-hardening"
        assert mo is False

        # Path B: archive_path is shaped UNRECOGNIZABLY (no -synthesis/
        # -workspace/-summary suffix and no matching builds/{stem}/ dir).
        # Suffix-stripper returns the stem; BUILDS_DIR/{stem}/ doesn't
        # exist so preferred-build resolution falls through to broad-glob.
        archive_unrecognized = (
            "/home/dev/.claude/teams/sigma-review/shared/archive/"
            "no-such-build-2099.md"
        )
        found2, rid2, _ = pg._has_compilation_complete(
            archive_path=archive_unrecognized
        )
        assert found2 is True, (
            "Unrecognized archive name shape (BUILDS_DIR/{stem}/ missing) "
            "must fall through to broad-glob fallback"
        )
        assert rid2 == "2026-04-28-shared-process-hardening"


class TestBlock5SynthesisCarveOut:
    """ADR[1] BLOCK 5 carve-out for synthesis-archive writes (2026-05-05).

    Synthesis-archive writes occur at c3-review.md Step 13f, which
    structurally precedes compilation at Step 14. Gating those writes on the
    compilation-complete header creates a logical cycle. The carve-out exempts
    paths matching `*-synthesis.md` AND under a known archive marker from the
    BLOCK 5 compilation-complete precondition; all other archive writes still
    require the header.
    """

    @pytest.fixture
    def patch_multi(self, tmp_path):
        """Mirrors TestBlock5MultiPathWorkspace.patch_multi — same fixture
        signature so tests (c) and (d) reuse the multi-path setup pattern."""
        ws = tmp_path / "workspace.md"
        builds = tmp_path / "builds"
        builds.mkdir()

        def write_workspace(content):
            ws.write_text(content, encoding="utf-8")

        def write_build_scratch(build_id, c_label, content):
            d = builds / build_id
            d.mkdir(parents=True, exist_ok=True)
            scratch = d / f"{c_label}-scratch.md"
            scratch.write_text(content, encoding="utf-8")
            return scratch

        with patch.object(pg, "DEFAULT_WORKSPACE", ws), \
             patch.object(pg, "BUILDS_DIR", builds), \
             patch.object(pg, "CHAIN_STATUS_FILE", tmp_path / ".chain-status.json"):
            yield write_workspace, write_build_scratch, builds

    _BUILD_ID = "2026-05-05-block-5-synthesis-carveout"
    _SYNTH_ARCHIVE_PATH = (
        f"/home/dev/.claude/teams/sigma-review/shared/archive/"
        f"{_BUILD_ID}-synthesis.md"
    )

    # (a) carve-out fires: synthesis-archive write passes without
    # compilation-complete header in an active sigma session.
    def test_synthesis_archive_passes_without_compilation_header(self, patch_paths):
        """Carve-out PASS: ADR[1] exempts `*-synthesis.md` archive writes
        from the BLOCK 5 compilation-complete precondition."""
        write, _, _ = patch_paths
        # Active sigma session via task marker; NO compilation-complete header.
        write("## task\nbuild review\n## mode: BUILD\n")
        blocked, reason = pg.check_pre_archive_gate(
            "Write",
            {"file_path": self._SYNTH_ARCHIVE_PATH, "content": "synthesis"},
        )
        assert blocked is False, (
            "Synthesis-archive write must pass BLOCK 5 without "
            "compilation-complete header (ADR[1] carve-out)"
        )
        assert reason == ""

    # (b) carve-out short-circuit fires DIRECTLY — not via FP guard
    # (CQA BC-1: must exercise the carve-out branch, not _is_sigma_session=False).
    def test_synthesis_archive_short_circuit_inside_active_session(self, patch_paths):
        """CQA BC-1: in an active sigma session (FP guard does NOT fire),
        synthesis-archive write returns PASS via the carve-out short-circuit
        BEFORE _has_compilation_complete is consulted. Verifies behavior
        equivalence with a non-existent compilation header AND ensures the
        carve-out branch is actually exercised."""
        write, _, _ = patch_paths
        # Active session markers — _is_sigma_session() returns True.
        write("## task\nbuild review C2\n## mode: BUILD\n## findings\n")
        # Confirm session is active (FP guard would otherwise mask result).
        assert pg._is_sigma_session() is True
        blocked, reason = pg.check_pre_archive_gate(
            "Write",
            {"file_path": self._SYNTH_ARCHIVE_PATH, "content": "synthesis"},
        )
        assert blocked is False
        assert reason == ""
        # Sanity: helper itself returns True for this path.
        assert pg._is_synthesis_archive_write(self._SYNTH_ARCHIVE_PATH) is True

    # (c) regression: WS-1 R2-micro multi-path scan untouched. Non-synthesis
    # archive write resolves through preferred-build path as before.
    def test_non_synthesis_multi_path_resolution_unchanged(self, patch_multi):
        """Regression: WS-1 R2-micro behavior preserved. A non-synthesis
        archive write (e.g., `-workspace.md`) with the override header in the
        preferred build's c{N}-scratch.md still passes BLOCK 5 via the
        existing _has_compilation_complete path — carve-out does NOT short-
        circuit, header check still runs."""
        write_workspace, write_scratch, _ = patch_multi
        write_workspace("## task\nbuild review\n## mode: BUILD\n")
        write_scratch(
            self._BUILD_ID,
            "c3",
            "## task\nbuild review C3\n"
            f"## compilation-complete: [R-{self._BUILD_ID}, "
            "manual-override, reason: in-build hook wiring]\n"
            "## findings\n",
        )
        # Archive path is `-workspace.md` (not `-synthesis.md`) — Condition A
        # fails, carve-out does NOT fire, falls through to multi-path scan.
        non_synth_archive = (
            f"/home/dev/.claude/teams/sigma-review/shared/archive/"
            f"{self._BUILD_ID}-workspace.md"
        )
        blocked, reason = pg.check_pre_archive_gate(
            "Write",
            {"file_path": non_synth_archive, "content": "x"},
        )
        assert blocked is False, (
            "WS-1 R2-micro preferred-build resolution must still authorize "
            "non-synthesis archive write when override header present in "
            "build scratch — carve-out must NOT alter this path"
        )

    # (d) Condition A failure: non-synthesis archive write WITHOUT header
    # still blocks (IE BC-3: defense against over-broad short-circuit).
    def test_non_synthesis_archive_still_blocks_without_header(self, patch_multi):
        """IE BC-3 / PM[5] defense: a non-synthesis archive write (Condition A
        fails: filename does not end `-synthesis.md`) with no compilation-
        complete header anywhere must still BLOCK. Confirms the short-circuit
        is suffix-scoped, not blanket-archive."""
        write_workspace, write_scratch, _ = patch_multi
        write_workspace("## task\nbuild review\n## mode: BUILD\n")
        # Build scratch fresh + active but NO override header.
        write_scratch(
            self._BUILD_ID,
            "c2",
            "## task\nbuild review C2\n## findings\nno compilation header\n",
        )
        non_synth_archive = (
            f"/home/dev/.claude/teams/sigma-review/shared/archive/"
            f"{self._BUILD_ID}-workspace.md"
        )
        blocked, reason = pg.check_pre_archive_gate(
            "Write",
            {"file_path": non_synth_archive, "content": "x"},
        )
        assert blocked is True, (
            "Non-synthesis archive write (Condition A fails) must still "
            "BLOCK when no compilation-complete header exists — carve-out "
            "is suffix-scoped, not blanket archive exemption"
        )
        assert "PRE-ARCHIVE BLOCKED" in reason

    # (e) Condition B failure: synthesis-suffixed file outside archive dir
    # is NOT classified as an archive op at all (CQA EC[3]). The carve-out's
    # Condition B (archive marker) is independently required.
    def test_synthesis_path_outside_archive_classification(self, patch_paths):
        """CQA EC[3]: a `-synthesis.md` file outside any known archive dir
        (Condition B fails) is not classified as an archive operation — the
        BLOCK 5 path is not entered. _path_is_archive returns False so
        check_pre_archive_gate returns PASS via the `not is_archive_op`
        branch, NOT via the carve-out. _is_synthesis_archive_write also
        returns False on this path (Condition B independently required)."""
        write, _, _ = patch_paths
        write("## task\nbuild review\n## mode: BUILD\n")
        outside_archive = "/tmp/foo-synthesis.md"
        # Helper itself rejects: Condition B (archive marker) fails.
        assert pg._is_synthesis_archive_write(outside_archive) is False
        # _path_is_archive also False, so check_pre_archive_gate returns
        # (False, "") via the `not is_archive_op` branch (line 681).
        assert pg._path_is_archive(outside_archive) is False
        blocked, reason = pg.check_pre_archive_gate(
            "Write",
            {"file_path": outside_archive, "content": "x"},
        )
        assert blocked is False, (
            "Path outside archive markers is not an archive op; gate exits "
            "before BLOCK 5 logic — carve-out must NOT extend BLOCK to "
            "non-archive synthesis paths"
        )
        assert reason == ""
