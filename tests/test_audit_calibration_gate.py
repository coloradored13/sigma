"""Tests for audit-calibration-gate.py.

Fixture-isolated: tests construct their own calibration-log.md content
via tmp_path. ZERO coupling to MINIMAL_WORKSPACE or roster.md.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
import pytest

# Import the standalone script (hyphen in filename → importlib.util dance).
# Must register in sys.modules BEFORE exec_module so dataclass() can
# introspect cls.__module__ under Python 3.14+.
_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "hooks" / "audit-calibration-gate.py"
_spec = importlib.util.spec_from_file_location("audit_calibration_gate", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
audit_mod = importlib.util.module_from_spec(_spec)
sys.modules["audit_calibration_gate"] = audit_mod
_spec.loader.exec_module(audit_mod)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _record(
    gate: str = "A20",
    review: str = "2026-04-23-example",
    finding: str = "F[TA-1]",
    reason: str = "confidence-marker",
    context: str = "tech-architect:some excerpt up to fifty chars total here",
    verdict: str = "PENDING",
) -> str:
    """Build a single well-formed CAL-EMIT line."""
    return (
        f"CAL-EMIT[{gate}]: review-id:{review} |finding-ref:{finding} "
        f"|fire-reason:{reason} |workspace-context:{context} |da-verdict:{verdict}"
    )


HEADER = (
    "# calibration-log\n"
    "Prose that should be ignored by the parser.\n"
    "## Records\n"
)


def _log_content(records: list[str]) -> str:
    return HEADER + "\n".join(records) + "\n"


def _write_log(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "calibration-log.md"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParseLog:
    def test_empty_log_returns_empty_stats(self):
        stats, malformed = audit_mod.parse_log(HEADER)
        assert stats == {}
        assert malformed == []

    def test_prose_lines_ignored(self):
        stats, malformed = audit_mod.parse_log(
            "# Header\nRandom prose.\n<!-- comment -->\n"
        )
        assert stats == {}
        assert malformed == []

    def test_single_well_formed_record(self):
        stats, malformed = audit_mod.parse_log(HEADER + _record(verdict="legitimate"))
        assert "A20" in stats
        assert stats["A20"].legitimate == 1
        assert stats["A20"].false_positive == 0
        assert stats["A20"].pending == 0
        assert stats["A20"].reviews == {"2026-04-23-example"}
        assert malformed == []

    def test_multiple_verdict_types_counted_separately(self):
        records = [
            _record(verdict="legitimate"),
            _record(verdict="legitimate"),
            _record(verdict="false-positive"),
            _record(verdict="not-reviewed"),
            _record(verdict="PENDING"),
        ]
        stats, malformed = audit_mod.parse_log(_log_content(records))
        assert stats["A20"].legitimate == 2
        assert stats["A20"].false_positive == 1
        assert stats["A20"].not_reviewed == 1
        assert stats["A20"].pending == 1
        assert stats["A20"].total_fires == 5
        assert stats["A20"].verdicted == 3  # legitimate + false-positive only
        assert malformed == []

    def test_distinct_reviews_counted(self):
        records = [
            _record(review="r1", verdict="legitimate"),
            _record(review="r1", verdict="false-positive"),  # same review, two fires
            _record(review="r2", verdict="legitimate"),
            _record(review="r3", verdict="legitimate"),
        ]
        stats, _ = audit_mod.parse_log(_log_content(records))
        assert len(stats["A20"].reviews) == 3

    def test_multi_gate_records_segregated(self):
        records = [
            _record(gate="A20", verdict="legitimate"),
            _record(gate="A22", verdict="legitimate"),
            _record(gate="A23", verdict="false-positive"),
        ]
        stats, _ = audit_mod.parse_log(_log_content(records))
        assert stats["A20"].legitimate == 1
        assert stats["A22"].legitimate == 1
        assert stats["A23"].false_positive == 1

    def test_malformed_line_captured(self):
        bad = "CAL-EMIT[A20]: missing required fields"
        stats, malformed = audit_mod.parse_log(HEADER + bad + "\n")
        assert stats == {}
        assert len(malformed) == 1
        assert bad in malformed[0][1]

    def test_invalid_gate_id_captured(self):
        # A21 is RESERVED per PF[4] — must be flagged malformed.
        records = [_record(gate="A21", verdict="legitimate")]
        stats, malformed = audit_mod.parse_log(_log_content(records))
        assert "A21" not in stats
        assert len(malformed) == 1
        assert "A21" in malformed[0][1]

    def test_valid_and_malformed_coexist(self):
        records = [
            _record(verdict="legitimate"),
            "CAL-EMIT[A20]: totally broken line",
            _record(verdict="false-positive"),
        ]
        stats, malformed = audit_mod.parse_log(_log_content(records))
        assert stats["A20"].legitimate == 1
        assert stats["A20"].false_positive == 1
        assert len(malformed) == 1

    def test_fenced_code_block_content_ignored(self):
        # Format examples inside ``` fences must not be parsed as records.
        content = (
            "# Header\n"
            "## Format\n"
            "```\n"
            "CAL-EMIT[{gate-id}]: review-id:{slug} |finding-ref:{F[x]} "
            "|fire-reason:{reason} |workspace-context:{agent}:{excerpt} "
            "|da-verdict:{PENDING|legitimate|false-positive|not-reviewed}\n"
            "```\n"
            "## Records\n"
            + _record(verdict="legitimate") + "\n"
        )
        stats, malformed = audit_mod.parse_log(content)
        assert stats["A20"].legitimate == 1
        assert malformed == []


# ---------------------------------------------------------------------------
# Evaluation tests (threshold logic)
# ---------------------------------------------------------------------------


class TestEvaluateGate:
    def test_empty_stats_calibrating(self):
        s = audit_mod.GateStats(gate_id="A20")
        v = audit_mod.evaluate_gate(s)
        assert v.decision == "CALIBRATING"
        assert "0 distinct review" in v.reason or "need ≥3" in v.reason

    def test_two_reviews_calibrating(self):
        # 2 reviews (need ≥3), even if FP rate is perfect.
        s = audit_mod.GateStats(gate_id="A20", legitimate=5)
        s.reviews.update({"r1", "r2"})
        v = audit_mod.evaluate_gate(s)
        assert v.decision == "CALIBRATING"
        assert "2 distinct" in v.reason

    def test_three_reviews_no_verdicts_calibrating(self):
        # 3 reviews but all PENDING → verdicted=0 → CALIBRATING with pending-warn.
        s = audit_mod.GateStats(gate_id="A20", pending=3)
        s.reviews.update({"r1", "r2", "r3"})
        v = audit_mod.evaluate_gate(s)
        assert v.decision == "CALIBRATING"
        assert any("PENDING" in w for w in v.warnings)

    def test_high_fp_rate_recalibrate(self):
        # 3 reviews, 2 legitimate + 3 false-positive → FP rate = 60% > 20% → RECALIBRATE.
        s = audit_mod.GateStats(gate_id="A20", legitimate=2, false_positive=3)
        s.reviews.update({"r1", "r2", "r3"})
        v = audit_mod.evaluate_gate(s)
        assert v.decision == "RECALIBRATE"
        assert "60%" in v.reason

    def test_fp_rate_at_threshold_promote_if_verdicted_enough(self):
        # FP rate exactly 20% (1 FP / 5 verdicted). 3 reviews. ≥5 verdicted → PROMOTE.
        s = audit_mod.GateStats(gate_id="A20", legitimate=4, false_positive=1)
        s.reviews.update({"r1", "r2", "r3"})
        v = audit_mod.evaluate_gate(s)
        assert v.decision == "PROMOTE"

    def test_fp_rate_just_over_threshold_recalibrate(self):
        # 4 legit + 2 FP → FP rate = 33% > 20% → RECALIBRATE.
        s = audit_mod.GateStats(gate_id="A20", legitimate=4, false_positive=2)
        s.reviews.update({"r1", "r2", "r3"})
        v = audit_mod.evaluate_gate(s)
        assert v.decision == "RECALIBRATE"

    def test_under_verdicted_calibrating(self):
        # 3 reviews, 2 legit + 0 FP = 0% FP, but only 2 verdicted < 5 → CALIBRATING.
        s = audit_mod.GateStats(gate_id="A20", legitimate=2)
        s.reviews.update({"r1", "r2", "r3"})
        v = audit_mod.evaluate_gate(s)
        assert v.decision == "CALIBRATING"
        assert "need ≥5" in v.reason

    def test_clean_promote(self):
        # 3 reviews, 5 legit + 0 FP = 0% FP, 5 verdicted ≥ 5 → PROMOTE.
        s = audit_mod.GateStats(gate_id="A20", legitimate=5)
        s.reviews.update({"r1", "r2", "r3"})
        v = audit_mod.evaluate_gate(s)
        assert v.decision == "PROMOTE"

    def test_not_reviewed_stall_warning(self):
        # 3 reviews, mostly not-reviewed — should flag stall even during CALIBRATING.
        s = audit_mod.GateStats(gate_id="A20", legitimate=1, not_reviewed=5)
        s.reviews.update({"r1", "r2", "r3"})
        v = audit_mod.evaluate_gate(s)
        assert any("stall" in w.lower() or "not-reviewed" in w for w in v.warnings)

    def test_not_reviewed_below_threshold_no_warning(self):
        # 3 reviews, 4 legit + 1 not-reviewed = 20% not-reviewed ≤ 30% → no stall warn.
        s = audit_mod.GateStats(gate_id="A20", legitimate=4, not_reviewed=1)
        s.reviews.update({"r1", "r2", "r3"})
        v = audit_mod.evaluate_gate(s)
        stall_warnings = [w for w in v.warnings if "stall" in w.lower() or "not-reviewed rate" in w]
        assert stall_warnings == []


# ---------------------------------------------------------------------------
# End-to-end run() tests with temp files
# ---------------------------------------------------------------------------


class TestRun:
    def test_missing_file_exit_code_3(self, tmp_path):
        missing = tmp_path / "does-not-exist.md"
        code, out = audit_mod.run(missing)
        assert code == 3
        assert "not found" in out

    def test_empty_log_all_gates_calibrating(self, tmp_path):
        log = _write_log(tmp_path, HEADER)
        code, out = audit_mod.run(log)
        assert code == 0
        assert "[A20] CALIBRATING" in out
        assert "[A22] CALIBRATING" in out
        assert "[A23] CALIBRATING" in out

    def test_gate_filter(self, tmp_path):
        log = _write_log(tmp_path, _log_content([_record(gate="A20", verdict="legitimate")]))
        code, out = audit_mod.run(log, gate_filter="A20")
        assert code == 0
        assert "[A20]" in out
        assert "[A22]" not in out
        assert "[A23]" not in out

    def test_promote_rendered(self, tmp_path):
        records = [
            _record(gate="A20", review=f"r{i}", verdict="legitimate")
            for i in range(1, 4)  # r1, r2, r3 — 3 distinct reviews
        ]
        records += [
            _record(gate="A20", review="r1", verdict="legitimate"),
            _record(gate="A20", review="r1", verdict="legitimate"),
        ]  # total 5 legit, 3 distinct reviews, 0 FP
        log = _write_log(tmp_path, _log_content(records))
        code, out = audit_mod.run(log, gate_filter="A20")
        assert code == 0
        assert "[A20] PROMOTE" in out

    def test_recalibrate_rendered(self, tmp_path):
        records = (
            [_record(gate="A20", review=f"r{i}", verdict="legitimate") for i in range(1, 4)]
            + [_record(gate="A20", review="r1", verdict="false-positive") for _ in range(3)]
        )  # 3 legit + 3 FP → 50% FP → RECALIBRATE
        log = _write_log(tmp_path, _log_content(records))
        code, out = audit_mod.run(log, gate_filter="A20")
        assert code == 0
        assert "[A20] RECALIBRATE" in out

    def test_malformed_only_exit_code_2(self, tmp_path):
        # Only broken lines with CAL-EMIT prefix, no valid records.
        content = HEADER + "CAL-EMIT[A20]: junk\nCAL-EMIT[A22]: also junk\n"
        log = _write_log(tmp_path, content)
        code, out = audit_mod.run(log)
        assert code == 2
        assert "MALFORMED" in out

    def test_malformed_coexists_with_valid_exit_0(self, tmp_path):
        content = _log_content([
            _record(gate="A20", verdict="legitimate"),
            "CAL-EMIT[A20]: broken",
        ])
        log = _write_log(tmp_path, content)
        code, out = audit_mod.run(log)
        assert code == 0  # any valid record → exit 0 even with malformed
        assert "MALFORMED" in out

    def test_pending_records_surface_warning(self, tmp_path):
        records = [
            _record(gate="A20", review=f"r{i}", verdict="legitimate")
            for i in range(1, 4)
        ] + [_record(gate="A20", review="r1", verdict="PENDING") for _ in range(2)]
        log = _write_log(tmp_path, _log_content(records))
        code, out = audit_mod.run(log, gate_filter="A20")
        assert code == 0
        assert "PENDING" in out


# ---------------------------------------------------------------------------
# CLI entry-point smoke tests
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_missing_file_returns_3(self, tmp_path, capsys):
        rc = audit_mod.main(["--file", str(tmp_path / "nope.md")])
        assert rc == 3

    def test_main_with_valid_log(self, tmp_path, capsys):
        log = _write_log(tmp_path, _log_content([_record(verdict="legitimate")]))
        rc = audit_mod.main(["--file", str(log)])
        assert rc == 0
        captured = capsys.readouterr()
        assert "A20" in captured.out

    def test_main_gate_filter(self, tmp_path, capsys):
        log = _write_log(tmp_path, HEADER)
        rc = audit_mod.main(["--file", str(log), "--gate", "A22"])
        assert rc == 0
        captured = capsys.readouterr()
        assert "[A22]" in captured.out
        assert "[A20]" not in captured.out
        assert "[A23]" not in captured.out
