"""session-start.py (runtime-home seeding + managed-file sync) and the
framework/bin/chain-evaluator.py launcher.

Each test copies the plugin into a tmp directory so the plugin version can be
changed, and runs the hook as a subprocess with a tmp HOME.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import PLUGIN_ROOT, subprocess_env


@pytest.fixture
def plugin(tmp_path):
    """A private copy of the plugin (hooks, framework, manifest)."""
    root = tmp_path / "plugin"
    for sub in ("hooks", "framework", ".claude-plugin"):
        shutil.copytree(PLUGIN_ROOT / sub, root / sub)
    return root


@pytest.fixture
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


def _sigma_home(home: Path) -> Path:
    return home / ".claude" / "teams" / "sigma-review"


def _set_version(plugin: Path, version: str) -> None:
    manifest = plugin / ".claude-plugin" / "plugin.json"
    data = json.loads(manifest.read_text())
    data["version"] = version
    manifest.write_text(json.dumps(data))


def run_session_start(plugin: Path, home: Path) -> dict:
    out = subprocess.run(
        [sys.executable, str(plugin / "hooks" / "session-start.py")],
        input=json.dumps({"hook_event_name": "SessionStart", "source": "startup"}),
        capture_output=True, text=True, env=subprocess_env(home), timeout=15,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout) if out.stdout.strip() else {}


def _seed_files(plugin: Path) -> list[Path]:
    seed = plugin / "framework" / "seed"
    return [p.relative_to(seed) for p in seed.rglob("*") if p.is_file()]


class TestSeeding:
    def test_first_run_seeds_every_seed_file(self, plugin, home):
        msg = run_session_start(plugin, home)
        sh = _sigma_home(home)
        seeds = _seed_files(plugin)
        assert seeds, "plugin ships no seed files"
        for rel in seeds:
            assert (sh / rel).is_file(), f"not seeded: {rel}"
        assert "initialized runtime home" in msg["systemMessage"]

    def test_first_run_creates_runtime_layout(self, plugin, home):
        run_session_start(plugin, home)
        sh = _sigma_home(home)
        for sub in ("agents", "inboxes", "shared/archive", "shared/builds", "shared/wiki", ".state"):
            assert (sh / sub).is_dir(), sub

    def test_seeded_files_are_never_overwritten(self, plugin, home):
        run_session_start(plugin, home)
        sh = _sigma_home(home)
        roster = sh / "shared" / "roster.md"
        workspace = sh / "shared" / "workspace.md"
        roster.write_text("# my roster\n")
        workspace.write_text("## task\nmy review in progress\n")
        # A new plugin version must not touch user state either.
        _set_version(plugin, "99.0.0")
        run_session_start(plugin, home)
        assert roster.read_text() == "# my roster\n"
        assert workspace.read_text() == "## task\nmy review in progress\n"

    def test_deleted_seed_file_is_restored(self, plugin, home):
        run_session_start(plugin, home)
        patterns = _sigma_home(home) / "shared" / "patterns.md"
        patterns.unlink()
        run_session_start(plugin, home)
        assert patterns.is_file()

    def test_second_run_is_quiet(self, plugin, home):
        run_session_start(plugin, home)
        assert run_session_start(plugin, home) == {}


class TestManagedSync:
    def _managed(self, plugin: Path) -> dict[str, Path]:
        """Expected managed files: {relative path under SIGMA_HOME: source}."""
        mapping = {}
        for src_sub, dest_sub in (("agents", "agent-defs"), ("shared", "shared"), ("bin", "bin")):
            src_dir = plugin / "framework" / src_sub
            for src in src_dir.rglob("*"):
                if src.is_file():
                    mapping[str(Path(dest_sub) / src.relative_to(src_dir))] = src
        return mapping

    def test_syncs_managed_files(self, plugin, home):
        run_session_start(plugin, home)
        sh = _sigma_home(home)
        managed = self._managed(plugin)
        assert "agent-defs/sigma-lead.md" in managed
        assert "shared/directives.md" in managed
        assert "bin/chain-evaluator.py" in managed
        for rel, src in managed.items():
            assert (sh / rel).read_bytes() == src.read_bytes(), rel

    def test_records_managed_manifest(self, plugin, home):
        _set_version(plugin, "1.2.3")
        run_session_start(plugin, home)
        manifest = json.loads((_sigma_home(home) / ".managed.json").read_text())
        assert manifest["version"] == "1.2.3"
        assert set(manifest["files"]) == set(self._managed(plugin))
        assert all(len(h) == 64 for h in manifest["files"].values())

    def test_unchanged_version_does_not_recopy(self, plugin, home):
        run_session_start(plugin, home)
        lead = _sigma_home(home) / "agent-defs" / "sigma-lead.md"
        lead.write_text("locally edited\n")
        run_session_start(plugin, home)
        assert lead.read_text() == "locally edited\n"
        assert not list(lead.parent.glob("sigma-lead.md.user-modified-*"))

    def test_version_change_backs_up_user_modified_file(self, plugin, home):
        run_session_start(plugin, home)
        lead = _sigma_home(home) / "agent-defs" / "sigma-lead.md"
        lead.write_text("locally edited\n")
        _set_version(plugin, "99.0.0")
        msg = run_session_start(plugin, home)
        backups = list(lead.parent.glob("sigma-lead.md.user-modified-*"))
        assert len(backups) == 1
        assert backups[0].read_text() == "locally edited\n"
        assert lead.read_bytes() == (plugin / "framework" / "agents" / "sigma-lead.md").read_bytes()
        assert "backed up" in msg["systemMessage"]
        assert "framework files updated" in msg["systemMessage"]

    def test_version_change_without_edits_makes_no_backup(self, plugin, home):
        run_session_start(plugin, home)
        _set_version(plugin, "99.0.0")
        run_session_start(plugin, home)
        assert not list(_sigma_home(home).rglob("*.user-modified-*"))

    def test_version_change_picks_up_new_framework_content(self, plugin, home):
        run_session_start(plugin, home)
        src = plugin / "framework" / "shared" / "protocols.md"
        src.write_text(src.read_text() + "\n<!-- new in 99.0.0 -->\n")
        _set_version(plugin, "99.0.0")
        run_session_start(plugin, home)
        assert "new in 99.0.0" in (_sigma_home(home) / "shared" / "protocols.md").read_text()


class TestPluginRoot:
    def test_writes_plugin_root(self, plugin, home):
        run_session_start(plugin, home)
        recorded = (_sigma_home(home) / ".plugin-root").read_text().strip()
        assert Path(recorded) == plugin.resolve()

    def test_plugin_root_follows_plugin_move(self, plugin, home, tmp_path):
        run_session_start(plugin, home)
        moved = tmp_path / "plugin-v2"
        shutil.copytree(plugin, moved)
        run_session_start(moved, home)
        assert Path((_sigma_home(home) / ".plugin-root").read_text().strip()) == moved.resolve()

    def test_failure_is_reported_not_raised(self, plugin, home):
        # A file where SIGMA_HOME should be makes every step fail.
        (home / ".claude" / "teams").mkdir(parents=True)
        (home / ".claude" / "teams" / "sigma-review").write_text("not a directory")
        msg = run_session_start(plugin, home)
        assert "session-start sync failed" in msg["systemMessage"]


class TestLauncher:
    def _launcher(self, home: Path) -> Path:
        return _sigma_home(home) / "bin" / "chain-evaluator.py"

    def test_status_runs_installed_plugin(self, plugin, home):
        run_session_start(plugin, home)
        (_sigma_home(home) / "shared" / "workspace.md").write_text(
            "# workspace\n## status: active\n## task\nReview a payments API\n"
        )
        out = subprocess.run(
            [sys.executable, str(self._launcher(home)), "status"],
            capture_output=True, text=True, env=subprocess_env(home), timeout=15,
        )
        assert out.returncode == 0, out.stderr
        summary = json.loads(out.stdout)
        assert summary["complete"] is False
        assert summary["total"] == summary["passed"] + summary["failed"] > 0

    def test_status_on_seeded_idle_workspace(self, plugin, home):
        run_session_start(plugin, home)
        out = subprocess.run(
            [sys.executable, str(self._launcher(home)), "status"],
            capture_output=True, text=True, env=subprocess_env(home), timeout=15,
        )
        assert out.returncode == 0, out.stderr
        assert "total" in json.loads(out.stdout)

    def test_missing_plugin_root_exits_with_hint(self, plugin, home):
        run_session_start(plugin, home)
        (_sigma_home(home) / ".plugin-root").unlink()
        out = subprocess.run(
            [sys.executable, str(self._launcher(home)), "status"],
            capture_output=True, text=True, env=subprocess_env(home), timeout=15,
        )
        assert out.returncode != 0
        assert "plugin root unknown" in out.stderr

    def test_stale_plugin_root_exits_with_hint(self, plugin, home, tmp_path):
        run_session_start(plugin, home)
        (_sigma_home(home) / ".plugin-root").write_text(str(tmp_path / "gone") + "\n")
        out = subprocess.run(
            [sys.executable, str(self._launcher(home)), "status"],
            capture_output=True, text=True, env=subprocess_env(home), timeout=15,
        )
        assert out.returncode != 0
        assert "not found" in out.stderr
