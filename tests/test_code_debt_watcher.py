"""Tests for code-debt-watcher.py — PostToolUse hook on Write|Edit."""
import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import importlib
watcher = importlib.import_module("code-debt-watcher")


class TestScanContent:
    def test_detects_bare_except(self):
        code = "try:\n    do_thing()\nexcept:\n    pass"
        findings = watcher.scan_content(code, "test.py")
        patterns_found = [f["pattern"] for f in findings]
        assert "error-swallowing" in patterns_found

    def test_detects_empty_js_catch(self):
        code = "try { doThing(); } catch (e) {}"
        findings = watcher.scan_content(code, "test.js")
        patterns_found = [f["pattern"] for f in findings]
        assert "error-swallowing" in patterns_found

    def test_detects_global_mutable_state(self):
        code = "def update():\n    global counter\n    counter += 1"
        findings = watcher.scan_content(code, "test.py")
        patterns_found = [f["pattern"] for f in findings]
        assert "shared-mutable-state" in patterns_found

    def test_detects_assert_true(self):
        code = "def test_something():\n    assert True"
        findings = watcher.scan_content(code, "test.py")
        patterns_found = [f["pattern"] for f in findings]
        assert "coincidental-correctness" in patterns_found

    def test_detects_sleep_sync(self):
        code = "import time\ntime.sleep(5)\ncheck_result()"
        findings = watcher.scan_content(code, "test.py")
        patterns_found = [f["pattern"] for f in findings]
        assert "implicit-ordering" in patterns_found

    def test_detects_mutable_default_arg(self):
        code = "def process(items=[]):\n    items.append(1)\n    return items"
        findings = watcher.scan_content(code, "test.py")
        patterns_found = [f["pattern"] for f in findings]
        assert "load-bearing-defaults" in patterns_found

    def test_detects_blanket_type_ignore(self):
        code = "result = weird_func()  # type: ignore"
        findings = watcher.scan_content(code, "test.py")
        patterns_found = [f["pattern"] for f in findings]
        assert "invisible-invariants" in patterns_found

    def test_allows_specific_type_ignore(self):
        code = "result = weird_func()  # type: ignore[assignment]"
        findings = watcher.scan_content(code, "test.py")
        patterns_found = [f["pattern"] for f in findings]
        assert "invisible-invariants" not in patterns_found

    def test_detects_blanket_noqa(self):
        code = "x = 1  # noqa"
        findings = watcher.scan_content(code, "test.py")
        patterns_found = [f["pattern"] for f in findings]
        assert "invisible-invariants" in patterns_found

    def test_allows_specific_noqa(self):
        code = "x = 1  # noqa: E501"
        findings = watcher.scan_content(code, "test.py")
        patterns_found = [f["pattern"] for f in findings]
        assert "invisible-invariants" not in patterns_found

    def test_detects_nosec(self):
        code = "password = 'hardcoded'  # nosec"
        findings = watcher.scan_content(code, "test.py")
        patterns_found = [f["pattern"] for f in findings]
        assert "invisible-invariants" in patterns_found

    def test_clean_code_no_findings(self):
        code = "def process(items):\n    return [x * 2 for x in items]"
        findings = watcher.scan_content(code, "test.py")
        assert len(findings) == 0

    def test_high_risk_sorted_first(self):
        code = "except:\n    pass\nassert True\n"
        findings = watcher.scan_content(code, "test.py")
        if len(findings) >= 2:
            assert findings[0]["risk"] == "high"

    def test_go_error_discard(self):
        code = 'result, _ := doSomething("arg")'
        findings = watcher.scan_content(code, "test.go")
        patterns_found = [f["pattern"] for f in findings]
        assert "error-swallowing" in patterns_found


class TestFlagCount:
    def test_starts_at_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(watcher, "STATE_FILE", tmp_path / ".count")
        assert watcher.get_flag_count("b1") == 0

    def test_increments_per_build(self, tmp_path, monkeypatch):
        state = tmp_path / "shared" / ".count"
        monkeypatch.setattr(watcher, "STATE_FILE", state)
        assert watcher.increment_flag_count("b1") == 1
        assert watcher.increment_flag_count("b1") == 2
        assert watcher.increment_flag_count("b2") == 1
        assert watcher.get_flag_count("b1") == 2

    def test_legacy_int_state_is_reset(self, tmp_path, monkeypatch):
        state = tmp_path / ".count"
        state.write_text("3", encoding="utf-8")
        monkeypatch.setattr(watcher, "STATE_FILE", state)
        assert watcher.get_flag_count("b1") == 0


def _make_build(builds, build_id, status="plan-locked", scratch=True):
    builds.mkdir(parents=True, exist_ok=True)
    (builds / f"{build_id}.plan.md").write_text(
        f"# plan\n\n## Meta\n- build-id: {build_id}\n- status: {status}\n", encoding="utf-8"
    )
    path = builds / build_id / "c2-scratch.md"
    if scratch:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("## build-status\n", encoding="utf-8")
    return path


class TestFindActiveBuild:
    def test_plan_locked_with_fresh_scratch_is_active(self, tmp_path, monkeypatch):
        builds = tmp_path / "builds"
        monkeypatch.setattr(watcher, "BUILDS_DIR", builds)
        scratch = _make_build(builds, "2026-09-25-webhook-retry")
        assert watcher.find_active_build() == ("2026-09-25-webhook-retry", scratch)

    def test_plan_locked_without_scratch_is_inactive(self, tmp_path, monkeypatch):
        builds = tmp_path / "builds"
        monkeypatch.setattr(watcher, "BUILDS_DIR", builds)
        _make_build(builds, "2026-04-15-abandoned", scratch=False)
        assert watcher.find_active_build() is None

    def test_stale_scratch_is_inactive(self, tmp_path, monkeypatch):
        builds = tmp_path / "builds"
        monkeypatch.setattr(watcher, "BUILDS_DIR", builds)
        scratch = _make_build(builds, "2026-04-20-old")
        later = scratch.stat().st_mtime + watcher.ACTIVE_WINDOW_SECONDS + 60
        assert watcher.find_active_build(now=later) is None

    def test_completed_build_is_inactive(self, tmp_path, monkeypatch):
        builds = tmp_path / "builds"
        monkeypatch.setattr(watcher, "BUILDS_DIR", builds)
        _make_build(builds, "2026-05-05-done", status="complete")
        assert watcher.find_active_build() is None

    def test_newest_scratch_wins(self, tmp_path, monkeypatch):
        import os
        builds = tmp_path / "builds"
        monkeypatch.setattr(watcher, "BUILDS_DIR", builds)
        older = _make_build(builds, "a-build")
        newer = _make_build(builds, "b-build")
        t = newer.stat().st_mtime
        os.utime(older, (t - 100, t - 100))
        assert watcher.find_active_build()[0] == "b-build"


class TestAppendToScratch:
    def test_appends_findings(self, tmp_path):
        scratch = tmp_path / "c2-scratch.md"
        scratch.write_text("## build-status\nActive\n", encoding="utf-8")
        findings = [{
            "file": "src/auth.py",
            "line": 42,
            "pattern": "error-swallowing",
            "risk": "high",
            "suggestion": "Bare except catches everything",
            "code": "except:",
        }]
        watcher.append_to_workspace(findings, scratch)
        content = scratch.read_text()
        assert "code-debt-watch" in content
        assert "src/auth.py:42" in content
        assert "error-swallowing" in content

    def test_skips_if_no_scratch(self, tmp_path):
        scratch = tmp_path / "nonexistent" / "c2-scratch.md"
        watcher.append_to_workspace([{"file": "x", "line": 1, "pattern": "p",
                                       "risk": "high", "suggestion": "s", "code": "c"}], scratch)
        assert not scratch.exists()


class TestMain:
    def _run(self, monkeypatch, event):
        import io
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        try:
            watcher.main()
        except SystemExit:
            pass

    def _event(self, code="try:\n    x()\nexcept:\n    pass\n"):
        return {"tool_name": "Write", "tool_input": {"file_path": "/repo/src/app.py", "content": code}}

    def test_flags_into_active_build_scratch(self, tmp_path, monkeypatch):
        builds = tmp_path / "builds"
        monkeypatch.setattr(watcher, "BUILDS_DIR", builds)
        monkeypatch.setattr(watcher, "STATE_FILE", tmp_path / ".count")
        scratch = _make_build(builds, "2026-09-25-webhook-retry")
        self._run(monkeypatch, self._event())
        assert "code-debt-watch" in scratch.read_text()
        assert watcher.get_flag_count("2026-09-25-webhook-retry") == 1

    def test_no_active_build_writes_nothing(self, tmp_path, monkeypatch):
        builds = tmp_path / "builds"
        monkeypatch.setattr(watcher, "BUILDS_DIR", builds)
        monkeypatch.setattr(watcher, "STATE_FILE", tmp_path / ".count")
        _make_build(builds, "2026-04-15-abandoned", scratch=False)
        self._run(monkeypatch, self._event())
        assert not (tmp_path / ".count").exists()

    def test_rate_limited_per_build(self, tmp_path, monkeypatch):
        builds = tmp_path / "builds"
        monkeypatch.setattr(watcher, "BUILDS_DIR", builds)
        monkeypatch.setattr(watcher, "STATE_FILE", tmp_path / ".count")
        scratch = _make_build(builds, "b")
        for _ in range(watcher.MAX_FLAGS + 2):
            self._run(monkeypatch, self._event())
        assert scratch.read_text().count("## code-debt-watch") == watcher.MAX_FLAGS
