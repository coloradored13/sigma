"""Tests for sigma-retrospective.py — Stop hook."""
import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import importlib
retro = importlib.import_module("sigma-retrospective")


class TestExtractSection:
    def test_extracts_convergence(self):
        text = "## convergence\nagent1: ✓ done\nagent2: ✓ done\n## findings\nstuff"
        result = retro.extract_section(text, "convergence")
        assert "agent1: ✓ done" in result
        assert "agent2: ✓ done" in result

    def test_extracts_last_section(self):
        text = "## infrastructure\nΣVerify available\n"
        result = retro.extract_section(text, "infrastructure")
        assert "ΣVerify available" in result

    def test_returns_empty_for_missing(self):
        assert retro.extract_section("## other\nstuff", "convergence") == ""

    def test_handles_empty_text(self):
        assert retro.extract_section("", "convergence") == ""


class TestAnalyzeWorkspace:
    def test_counts_converged_agents(self):
        from conftest import SAMPLE_WORKSPACE_COMPLETE
        metrics = retro.analyze_workspace(SAMPLE_WORKSPACE_COMPLETE)
        assert len(metrics["agents_converged"]) == 5

    def test_detects_no_circuit_breaker(self):
        from conftest import SAMPLE_WORKSPACE_COMPLETE
        metrics = retro.analyze_workspace(SAMPLE_WORKSPACE_COMPLETE)
        assert metrics["cb_fired"] is False

    def test_detects_circuit_breaker(self):
        # CB detection now reads the ## circuit-breaker section specifically,
        # not literal substring matches elsewhere in the workspace.
        content = (
            "## convergence\nagent: ✓\n\n"
            "## circuit-breaker\nCircuit breaker fired due to herding\n"
        )
        metrics = retro.analyze_workspace(content)
        assert metrics["cb_fired"] is True

    def test_counts_outcomes(self):
        from conftest import SAMPLE_WORKSPACE_COMPLETE
        metrics = retro.analyze_workspace(SAMPLE_WORKSPACE_COMPLETE)
        assert metrics["outcome_1"] >= 1  # "Revised from" / "outcome 1"
        assert metrics["outcome_2"] >= 1  # "CHECK CONFIRMS" / "outcome 2"
        assert metrics["outcome_3"] >= 1  # "gap:" / "outcome 3"

    def test_source_tier_counts(self):
        from conftest import SAMPLE_WORKSPACE_COMPLETE
        metrics = retro.analyze_workspace(SAMPLE_WORKSPACE_COMPLETE)
        assert metrics["t1"] >= 2  # :T1| appears twice
        assert metrics["t2"] >= 1  # :T2| appears once

    def test_xverify_detection(self):
        from conftest import SAMPLE_WORKSPACE_COMPLETE
        metrics = retro.analyze_workspace(SAMPLE_WORKSPACE_COMPLETE)
        assert metrics["xverify_used"] >= 1
        assert metrics["xverify_available"] is True

    def test_tier_assessment(self):
        from conftest import SAMPLE_WORKSPACE_COMPLETE
        metrics = retro.analyze_workspace(SAMPLE_WORKSPACE_COMPLETE)
        assert metrics["tier_assessed"] == 2

    def test_task_slug_extraction(self):
        from conftest import SAMPLE_WORKSPACE_COMPLETE
        metrics = retro.analyze_workspace(SAMPLE_WORKSPACE_COMPLETE)
        assert "payments API" in metrics["task_slug"].lower() or "competitive" in metrics["task_slug"].lower()

    def test_concession_detection(self):
        from conftest import SAMPLE_WORKSPACE_COMPLETE
        metrics = retro.analyze_workspace(SAMPLE_WORKSPACE_COMPLETE)
        assert metrics["concession_type"] in ("genuine", "performative", "n/a")

    def test_perfunctory_risk_high(self):
        # All outcomes are outcome 2 → high perfunctory risk
        content = "## convergence\na: ✓\n\nCHECK CONFIRMS risk A\nCHECK CONFIRMS risk B\nCHECK CONFIRMS risk C\nCHECK CONFIRMS risk D\nCHECK CONFIRMS risk E"
        metrics = retro.analyze_workspace(content)
        assert metrics["perfunctory_risk"] == "high"

    def test_empty_workspace(self):
        metrics = retro.analyze_workspace("")
        assert metrics["agents_converged"] == []
        assert metrics["tier_assessed"] == 0


class TestGenerateRecommendation:
    def test_perfunctory_risk_recommendation(self):
        metrics = {"perfunctory_risk": "high", "concession_type": "genuine",
                   "revision_rate": 50, "t1": 5, "t2": 3, "t3": 1,
                   "xverify_available": True, "xverify_used": 1,
                   "agents_converged": ["a", "b", "c", "d"], "cb_fired": True}
        rec = retro.generate_recommendation(metrics)
        assert "rubber-stamping" in rec.lower() or "outcome-2" in rec.lower()

    def test_t3_dominant_recommendation(self):
        metrics = {"perfunctory_risk": "low", "concession_type": "genuine",
                   "revision_rate": 50, "t1": 0, "t2": 1, "t3": 10,
                   "xverify_available": True, "xverify_used": 1,
                   "agents_converged": ["a", "b", "c", "d"], "cb_fired": True}
        rec = retro.generate_recommendation(metrics)
        assert "T3" in rec

    def test_xverify_unused_recommendation(self):
        metrics = {"perfunctory_risk": "low", "concession_type": "genuine",
                   "revision_rate": 50, "t1": 5, "t2": 3, "t3": 1,
                   "xverify_available": True, "xverify_used": 0,
                   "agents_converged": ["a", "b", "c", "d"], "cb_fired": True}
        rec = retro.generate_recommendation(metrics)
        assert "ΣVerify" in rec or "unused" in rec.lower()

    def test_no_cb_with_many_agents(self):
        metrics = {"perfunctory_risk": "low", "concession_type": "genuine",
                   "revision_rate": 50, "t1": 5, "t2": 3, "t3": 1,
                   "xverify_available": True, "xverify_used": 1,
                   "agents_converged": ["a", "b", "c", "d"], "cb_fired": False}
        rec = retro.generate_recommendation(metrics)
        assert "circuit breaker" in rec.lower() or "divergence" in rec.lower()

    def test_normal_ranges(self):
        metrics = {"perfunctory_risk": "low", "concession_type": "genuine",
                   "revision_rate": 50, "t1": 5, "t2": 3, "t3": 1,
                   "xverify_available": True, "xverify_used": 1,
                   "agents_converged": ["a", "b", "c", "d"], "cb_fired": True}
        rec = retro.generate_recommendation(metrics)
        assert "normal ranges" in rec.lower()


class TestWriteRetro:
    def test_appends_to_patterns(self, tmp_path, monkeypatch):
        patterns = tmp_path / "patterns.md"
        patterns.write_text("# Patterns\n", encoding="utf-8")
        monkeypatch.setattr(retro, "PATTERNS", patterns)

        metrics = {
            "task_slug": "test-review",
            "agents_converged": ["agent-a", "agent-b"],
            "agents_timeout": 0,
            "cb_fired": False,
            "outcome_1": 2, "outcome_2": 3, "outcome_3": 1,
            "perfunctory_risk": "low",
            "revision_rate": 45,
            "concession_type": "genuine",
            "t1": 4, "t2": 2, "t3": 1,
            "xverify_used": 1, "xverify_failed": 0, "xverify_available": True,
            "tier_assessed": 2,
        }
        retro.write_retro(metrics)

        content = patterns.read_text()
        assert "## Retro: R1" in content
        assert "test-review" in content
        assert "agent-a, agent-b" in content
        assert "outcome-1: 2" in content

    def test_increments_review_number(self, tmp_path, monkeypatch):
        patterns = tmp_path / "patterns.md"
        patterns.write_text("## Retro: R5 — old\n", encoding="utf-8")
        monkeypatch.setattr(retro, "PATTERNS", patterns)

        metrics = {
            "task_slug": "new", "agents_converged": ["a"], "agents_timeout": 0,
            "cb_fired": False, "outcome_1": 0, "outcome_2": 0, "outcome_3": 0,
            "perfunctory_risk": "low", "revision_rate": 0, "concession_type": "n/a",
            "t1": 0, "t2": 0, "t3": 0, "xverify_used": 0, "xverify_failed": 0,
            "xverify_available": False, "tier_assessed": 1,
        }
        retro.write_retro(metrics)

        content = patterns.read_text()
        assert "## Retro: R6" in content


class TestDeduplication:
    def test_legacy_hash_file_is_discarded(self, tmp_path, monkeypatch):
        """Legacy single-string hash format should migrate to empty dict."""
        state = tmp_path / ".retro-last-hash"
        state.write_text("abc123legacy", encoding="utf-8")
        monkeypatch.setattr(retro, "RETRO_STATE", state)
        assert retro.load_state() == {}

    def test_empty_state_returns_empty_dict(self, tmp_path, monkeypatch):
        state = tmp_path / ".retro-last-hash"
        monkeypatch.setattr(retro, "RETRO_STATE", state)
        assert retro.load_state() == {}

    def test_json_state_round_trips(self, tmp_path, monkeypatch):
        state = tmp_path / ".retro-last-hash"
        monkeypatch.setattr(retro, "RETRO_STATE", state)
        retro.save_state({"2026-04-16:foo": "abc", "2026-04-16:bar": "def"})
        assert retro.load_state() == {"2026-04-16:foo": "abc", "2026-04-16:bar": "def"}


# ---------------------------------------------------------------------------
# Fix 5 (audit residual): CB-detection reads ## circuit-breaker section scope,
# not literal substring matches throughout the workspace.
# ---------------------------------------------------------------------------

class TestCircuitBreakerDetection:
    """detect_cb_fired must read the ## circuit-breaker section semantically."""

    def test_not_triggered_returns_false(self):
        """R18 regression: 'circuit breaker NOT triggered' must NOT report fired."""
        content = (
            "## circuit-breaker\n"
            "R1 divergence detected: 2 substantive tensions found — "
            "circuit breaker NOT triggered.\n"
        )
        assert retro.detect_cb_fired(content) is False

    def test_section_with_fired_returns_true(self):
        content = (
            "## circuit-breaker\n"
            "All agents agreed in R1 — CB fired to force dissent.\n"
        )
        assert retro.detect_cb_fired(content) is True

    def test_missing_section_returns_false(self):
        """No ## circuit-breaker section ⇒ not fired."""
        content = "## convergence\nagent: ✓\n## findings\nbody"
        assert retro.detect_cb_fired(content) is False

    def test_literal_match_outside_section_ignored(self):
        """Old-parser bug: 'circuit breaker' outside the section triggered false positive."""
        content = (
            "## notes\n"
            "The circuit breaker design inspired this pattern.\n"
            "## convergence\n"
            "agent: ✓\n"
        )
        assert retro.detect_cb_fired(content) is False

    def test_herding_detected_fires(self):
        content = "## circuit-breaker\nHerding detected across 4 agents.\n"
        assert retro.detect_cb_fired(content) is True

    def test_not_needed_returns_false(self):
        content = "## circuit-breaker\nNo divergence — CB not needed.\n"
        assert retro.detect_cb_fired(content) is False


# ---------------------------------------------------------------------------
# Fix 5 (audit residual): emission gating prevents multi-Stop duplicate entries
# ---------------------------------------------------------------------------

class TestShouldEmit:
    def test_archived_status_emits(self):
        content = "## status: archived\n## convergence\n\n"
        assert retro.should_emit(content) is True

    def test_converged_active_does_not_emit(self):
        """One agent's ✓ mid-review is not completion (26.9.24 partial-metrics retro)."""
        content = "## status: active\n## convergence\nagent: ✓ done\n"
        assert retro.should_emit(content) is False

    def test_active_without_convergence_skipped(self):
        content = "## status: active\n## convergence\n\n"
        assert retro.should_emit(content) is False

    def test_no_status_converged_without_closure_skipped(self):
        content = "## convergence\nagent: ✓\n"
        assert retro.should_emit(content) is False

    def test_compilation_complete_emits(self):
        content = "## status: active\n## convergence\na: ✓\n## compilation-complete: [R-x]\n"
        assert retro.should_emit(content) is True

    def test_synthesis_and_archive_complete_emit(self):
        assert retro.should_emit("## synthesis-complete: [2026-09-24|synth]\n") is True
        assert retro.should_emit("## archive-complete: [archive/x.md|3|2026-09-24]\n") is True


class TestReviewKey:
    def test_review_id_preferred(self):
        content = "## review-id: demo-review-2026-09-24\n## build-id: other\n"
        assert retro.review_key(content, "Some task") == "review-id:demo-review-2026-09-24"

    def test_build_id_used_when_no_review_id(self):
        assert retro.review_key("## build-id: webhook-retry\n", "t") == "build-id:webhook-retry"

    def test_falls_back_to_task_slug(self):
        assert retro.review_key("## task\nX\n", "Enterprise AI Rollout") == "task:enterprise-ai-rollout"

    def test_legacy_date_key_counts_as_done(self):
        state = {"2026-09-24:assess-and-summarize": "abc"}
        assert retro.already_retrod(state, "review-id:new-id", "Assess and summarize") is True

    def test_unrelated_legacy_key_does_not_match(self):
        state = {"2026-09-24:other-task": "abc"}
        assert retro.already_retrod(state, "review-id:new-id", "Assess and summarize") is False


class TestTaskScopedDedup:
    """A finished review must emit at most once across Stops — and across days."""

    def _make_workspace(self, task, convergence="agent: ✓ done", review_id=None):
        rid = f"## review-id: {review_id}\n" if review_id else ""
        return (
            f"{rid}## task\n{task}\n\n"
            f"## infrastructure\n\n"
            f"## convergence\n{convergence}\n"
            f"## circuit-breaker\nNot triggered.\n"
            f"## compilation-complete: [R-x]\n"
        )

    def _run_main(self, monkeypatch, stop_event):
        """Call retro.main() without caring about SystemExit signaling."""
        monkeypatch.setattr("sys.stdin", __import__("io").StringIO(stop_event))
        try:
            retro.main()
        except SystemExit:
            pass

    def test_same_task_same_date_only_one_entry(self, tmp_path, monkeypatch):
        """Intermediate Stop events during a review must not append duplicates."""
        ws = tmp_path / "workspace.md"
        patterns = tmp_path / "patterns.md"
        patterns.write_text("", encoding="utf-8")
        state = tmp_path / ".retro-last-hash"

        monkeypatch.setattr(retro, "WORKSPACE", ws)
        monkeypatch.setattr(retro, "PATTERNS", patterns)
        monkeypatch.setattr(retro, "RETRO_STATE", state)

        stop_event = json.dumps({"hook_event_name": "Stop"})

        # First Stop: fresh task → 1 entry
        ws.write_text(self._make_workspace("R18 enterprise-ai-rollout"), encoding="utf-8")
        self._run_main(monkeypatch, stop_event)
        assert patterns.read_text().count("## Retro:") == 1

        # Second Stop: same task, convergence has more agents now → must skip
        ws.write_text(
            self._make_workspace(
                "R18 enterprise-ai-rollout",
                convergence="agent-a: ✓\nagent-b: ✓\nagent-c: ✓",
            ),
            encoding="utf-8",
        )
        self._run_main(monkeypatch, stop_event)
        count_after = patterns.read_text().count("## Retro:")
        assert count_after == 1, (
            f"Second Stop on same task must not append; got {count_after} entries"
        )

    def test_different_task_same_date_emits(self, tmp_path, monkeypatch):
        """Different review on the same day should still retro."""
        ws = tmp_path / "workspace.md"
        patterns = tmp_path / "patterns.md"
        patterns.write_text("", encoding="utf-8")
        state = tmp_path / ".retro-last-hash"

        monkeypatch.setattr(retro, "WORKSPACE", ws)
        monkeypatch.setattr(retro, "PATTERNS", patterns)
        monkeypatch.setattr(retro, "RETRO_STATE", state)

        stop_event = json.dumps({"hook_event_name": "Stop"})

        ws.write_text(self._make_workspace("task-A different"), encoding="utf-8")
        self._run_main(monkeypatch, stop_event)

        ws.write_text(self._make_workspace("task-B different"), encoding="utf-8")
        self._run_main(monkeypatch, stop_event)

        count = patterns.read_text().count("## Retro:")
        assert count == 2, f"Different tasks should both emit; got {count}"


    def test_same_review_next_day_does_not_re_emit(self, tmp_path, monkeypatch):
        """26.9.25 regression: a finished review left as the active workspace
        re-emitted on the next calendar day under a date-scoped key."""
        ws = tmp_path / "workspace.md"
        patterns = tmp_path / "patterns.md"
        patterns.write_text("", encoding="utf-8")
        state = tmp_path / ".retro-last-hash"
        monkeypatch.setattr(retro, "WORKSPACE", ws)
        monkeypatch.setattr(retro, "PATTERNS", patterns)
        monkeypatch.setattr(retro, "RETRO_STATE", state)
        stop_event = json.dumps({"hook_event_name": "Stop"})

        ws.write_text(self._make_workspace("Assess growth", review_id="rev-1"), encoding="utf-8")
        self._run_main(monkeypatch, stop_event)
        assert patterns.read_text().count("## Retro:") == 1

        # Simulate the next day: state from day 1 persists, date changes.
        class _Tomorrow(retro.datetime):
            @classmethod
            def now(cls, tz=None):
                return retro.datetime(2099, 1, 2)
        monkeypatch.setattr(retro, "datetime", _Tomorrow)
        self._run_main(monkeypatch, stop_event)
        assert patterns.read_text().count("## Retro:") == 1

    def test_legacy_state_blocks_re_emit(self, tmp_path, monkeypatch):
        """A review retro'd under the old {date}:{slug} key must not emit again."""
        ws = tmp_path / "workspace.md"
        patterns = tmp_path / "patterns.md"
        patterns.write_text("", encoding="utf-8")
        state = tmp_path / ".retro-last-hash"
        state.write_text(json.dumps({"2026-09-24:assess-growth": "abc"}), encoding="utf-8")
        monkeypatch.setattr(retro, "WORKSPACE", ws)
        monkeypatch.setattr(retro, "PATTERNS", patterns)
        monkeypatch.setattr(retro, "RETRO_STATE", state)

        ws.write_text(self._make_workspace("Assess growth", review_id="rev-1"), encoding="utf-8")
        self._run_main(monkeypatch, json.dumps({"hook_event_name": "Stop"}))
        assert patterns.read_text() == ""


class TestSlugify:
    def test_basic_slugify(self):
        assert retro.slugify("Enterprise AI Rollout") == "enterprise-ai-rollout"

    def test_special_chars_collapsed(self):
        assert retro.slugify("Foo / Bar — Baz") == "foo-bar-baz"

    def test_truncation(self):
        s = retro.slugify("a" * 200)
        assert len(s) == 50
