"""sigma_paths (the single path source) and the A14 git-clean gate built on it.

sigma_paths computes its paths at import time, so each case runs a fresh
interpreter with a controlled environment instead of reloading the module.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import HOOKS_DIR, subprocess_env

_spec = importlib.util.spec_from_file_location("chain_evaluator_paths_test", HOOKS_DIR / "chain-evaluator.py")
ce = importlib.util.module_from_spec(_spec)
sys.modules["chain_evaluator_paths_test"] = ce
_spec.loader.exec_module(ce)

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

_PROBE = (
    "import json, sys; sys.path.insert(0, sys.argv[1]); import sigma_paths as sp; "
    "print(json.dumps({k: str(getattr(sp, k)) for k in "
    "('SIGMA_HOME','SHARED','STATE_DIR','AGENT_DEFS','WORKSPACE','BUILDS_DIR','ARCHIVE_DIR',"
    "'WIKI_DIR','TEMPLATES_DIR','CALIBRATION_LOG','PLUGIN_ROOT')} | {'archive_repo': sp.archive_repo()}))"
)


def _probe(home: Path, **env) -> dict:
    full_env = subprocess_env(home)
    full_env.pop("SIGMA_HOME", None)
    full_env.update(env)
    out = subprocess.run(
        [sys.executable, "-c", _PROBE, str(HOOKS_DIR)],
        capture_output=True, text=True, env=full_env, timeout=10, check=True,
    )
    return json.loads(out.stdout)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=sigma-test", "-c", "user.email=sigma-test@example.invalid",
         "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false", *args],
        cwd=repo, check=True, capture_output=True, timeout=15,
        env=subprocess_env(repo.parent, GIT_CONFIG_NOSYSTEM="1"),
    )


# ─── sigma_paths ───


class TestSigmaPaths:
    def test_defaults_derive_from_home(self, tmp_path):
        paths = _probe(tmp_path)
        home = tmp_path / ".claude" / "teams" / "sigma-review"
        assert paths["SIGMA_HOME"] == str(home)
        assert paths["SHARED"] == str(home / "shared")
        assert paths["STATE_DIR"] == str(home / ".state")
        assert paths["AGENT_DEFS"] == str(home / "agent-defs")
        assert paths["WORKSPACE"] == str(home / "shared" / "workspace.md")
        assert paths["CALIBRATION_LOG"] == str(home / "shared" / "calibration-log.md")

    def test_sigma_home_env_override(self, tmp_path):
        custom = tmp_path / "elsewhere" / "sigma"
        paths = _probe(tmp_path / "home", SIGMA_HOME=str(custom))
        assert paths["SIGMA_HOME"] == str(custom)
        for key in ("SHARED", "WORKSPACE", "BUILDS_DIR", "ARCHIVE_DIR", "WIKI_DIR", "TEMPLATES_DIR"):
            assert paths[key].startswith(str(custom)), key
        assert paths["STATE_DIR"] == str(custom / ".state")

    def test_sigma_home_expands_user(self, tmp_path):
        paths = _probe(tmp_path, SIGMA_HOME="~/custom-sigma")
        assert paths["SIGMA_HOME"] == str(tmp_path / "custom-sigma")

    def test_plugin_root_is_parent_of_hooks(self, tmp_path):
        assert _probe(tmp_path)["PLUGIN_ROOT"] == str(HOOKS_DIR.parent)

    def test_archive_repo_none_without_git(self, tmp_path):
        assert _probe(tmp_path)["archive_repo"] is None

    def test_archive_repo_env_wins(self, tmp_path):
        repo = tmp_path / "explicit-repo"
        repo.mkdir()
        # Even with SIGMA_HOME inside a git tree, the explicit variable wins.
        (tmp_path / ".git").mkdir()
        paths = _probe(tmp_path, SIGMA_ARCHIVE_REPO=str(repo))
        assert paths["archive_repo"] == str(repo)

    def test_archive_repo_env_expands_user(self, tmp_path):
        paths = _probe(tmp_path, SIGMA_ARCHIVE_REPO="~/backup")
        assert paths["archive_repo"] == str(tmp_path / "backup")

    def test_archive_repo_is_sigma_home_when_it_is_a_repo(self, tmp_path):
        sigma_home = tmp_path / ".claude" / "teams" / "sigma-review"
        (sigma_home / ".git").mkdir(parents=True)
        assert _probe(tmp_path)["archive_repo"] == str(sigma_home)

    def test_archive_repo_walks_up_to_enclosing_work_tree(self, tmp_path):
        (tmp_path / ".claude" / ".git").mkdir(parents=True)
        assert _probe(tmp_path)["archive_repo"] == str(tmp_path / ".claude")

    def test_empty_env_var_is_ignored(self, tmp_path):
        assert _probe(tmp_path, SIGMA_ARCHIVE_REPO="")["archive_repo"] is None


# ─── A14 git-clean gate ───

_WS = "# workspace\n## status: active\n## mode: ANALYZE\n## task\nA14 probe\n"


class TestA14ArchiveRepo:
    def test_na_when_no_repo(self, monkeypatch):
        monkeypatch.setattr(ce, "_A14_REPO_PATH", None)
        item = ce.check_a14(_WS)
        assert item.passed is True
        assert item.details["a14_wrapper_status"].startswith("N/A")
        assert item.issues == []

    def test_na_via_cli_in_fresh_home(self, tmp_home):
        ws = tmp_home / ".claude/teams/sigma-review/shared/workspace.md"
        ws.write_text(_WS)
        out = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "chain-evaluator.py"), "item", "A14", str(ws)],
            capture_output=True, text=True, env=subprocess_env(tmp_home), timeout=15,
        )
        assert out.returncode == 0, out.stderr
        item = json.loads(out.stdout)
        assert item["passed"] is True
        assert "N/A" in json.dumps(item)

    def test_gate_checks_session_end_na_without_repo(self, monkeypatch):
        import gate_checks as gc
        monkeypatch.setattr(gc.sp, "archive_repo", lambda: None)
        result = gc.check_session_end(_WS)
        assert result.details["git_clean"] is True
        assert result.details["git_error"] is None

    @needs_git
    def test_clean_repo_passes(self, tmp_path, monkeypatch):
        repo = tmp_path / "archive"
        repo.mkdir()
        _git(repo, "init", "-q")
        (repo / "notes.md").write_text("x\n")
        _git(repo, "add", "notes.md")
        _git(repo, "commit", "-q", "-m", "init")
        monkeypatch.setattr(ce, "_A14_REPO_PATH", str(repo))
        item = ce.check_a14(_WS)
        assert item.passed is True, item.issues
        assert "N/A" not in str(item.details.get("a14_wrapper_status", ""))

    @needs_git
    def test_dirty_repo_fails(self, tmp_path, monkeypatch):
        repo = tmp_path / "archive"
        repo.mkdir()
        _git(repo, "init", "-q")
        (repo / "notes.md").write_text("x\n")
        _git(repo, "add", "notes.md")
        _git(repo, "commit", "-q", "-m", "init")
        (repo / "notes.md").write_text("changed\n")
        monkeypatch.setattr(ce, "_A14_REPO_PATH", str(repo))
        item = ce.check_a14(_WS)
        assert item.passed is False
        assert any("notes.md" in f for f in item.details["uncommitted_files"])

    @needs_git
    def test_cli_uses_sigma_archive_repo(self, tmp_home, tmp_path):
        repo = tmp_path / "archive"
        repo.mkdir()
        _git(repo, "init", "-q")
        (repo / "untracked.md").write_text("pending\n")
        ws = tmp_home / ".claude/teams/sigma-review/shared/workspace.md"
        ws.write_text(_WS)
        out = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "chain-evaluator.py"), "item", "A14", str(ws)],
            capture_output=True, text=True, timeout=15,
            env=subprocess_env(tmp_home, SIGMA_ARCHIVE_REPO=str(repo)),
        )
        assert out.returncode == 0, out.stderr
        item = json.loads(out.stdout)
        assert item["passed"] is False
        assert "N/A" not in json.dumps(item)
