#!/usr/bin/env python3
"""Audit-calibration gate for β+ WARN-first gates.

Reads calibration-log.md (append-only CAL-EMIT[] records) and evaluates
per-gate promotion thresholds:

    PROMOTE       ≥3 distinct reviews |≤20% FP rate |≥5 DA-verdicted (legit+FP)
    RECALIBRATE   ≥3 distinct reviews |>20% FP rate
    CALIBRATING   insufficient data (fewer reviews OR fewer verdicts)

WARN-first gates evaluated: A20 (§2i precision), A22 (§2j governance
artifact), A23 (§2d severity provenance), A24 (sigma-verify init pre-flight).

Note: A24 has no CONDITION 1 suppression equivalent — sigma-verify presence
is binary (XVERIFY tag in 500-char window or not), unlike A20 which suppresses
on driver/CI/qualifier markers. Intentional asymmetry, not a gate gap.

Thresholds are sourced from directives.md §2i path β+ (~line 347).

This is a STANDALONE script — NOT a chain-evaluator A-check (per CAL[10]).
Run manually or via sigma-audit integration:

    python3 ~/.claude/teams/sigma-review/shared/audit-calibration-gate.py
    python3 audit-calibration-gate.py --file /path/to/log --gate A20

Exit codes:
    0  success — output printed to stdout
    2  malformed input file
    3  input file not found
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import sigma_paths as sp  # noqa: E402

# Match a CAL-EMIT record line. Example line from directives.md:
#   CAL-EMIT[A20]: review-id:2026-04-23-foo |finding-ref:F[TA-1] |fire-reason:>70pct-confidence |workspace-context:tech-architect:excerpt |da-verdict:PENDING
_CAL_EMIT_RE = re.compile(
    r"^CAL-EMIT\[(?P<gate>[A-Z]\d+)\]:\s*"
    r"review-id:(?P<review>\S+)\s*\|"
    r"finding-ref:(?P<finding>\S+)\s*\|"
    r"fire-reason:(?P<reason>[^|]+?)\s*\|"
    r"workspace-context:(?P<context>[^|]+?)\s*\|"
    r"da-verdict:(?P<verdict>PENDING|legitimate|false-positive|not-reviewed)\s*$"
)

# Valid gate IDs per PF[4] lock (c2-scratch) — A21 RESERVED, not valid.
# A24 added 2026-04-24 (R3 fix per CDS r2 cross-section finding): A24 fires
# correctly via chain-evaluator but consumer was bucketing CAL-EMIT[A24]
# records as malformed because the gate-id wasn't in this set.
# 2026-06-04: same drift recurred — chain-evaluator emits CAL-EMIT for A25/A26/
# B5/B6 (all newer gates) but they were absent here, so their records were
# silently bucketed as malformed and could never reach WARN->BLOCK promotion.
VALID_GATES = {"A20", "A22", "A23", "A24", "A25", "A26", "B5", "B6"}

# Promotion thresholds (directives.md §2i path β+)
MIN_REVIEWS = 3
MAX_FP_RATE = 0.20
MIN_VERDICTED = 5
NOT_REVIEWED_WARN_RATE = 0.30  # flag stall when exceeded after ≥3 reviews

DEFAULT_LOG_PATH = sp.CALIBRATION_LOG


@dataclass
class GateStats:
    gate_id: str
    reviews: set[str] = field(default_factory=set)
    legitimate: int = 0
    false_positive: int = 0
    not_reviewed: int = 0
    pending: int = 0

    @property
    def total_fires(self) -> int:
        return self.legitimate + self.false_positive + self.not_reviewed + self.pending

    @property
    def verdicted(self) -> int:
        # Not-reviewed ≠ verdicted per directives.md line 347.
        return self.legitimate + self.false_positive

    @property
    def fp_rate(self) -> float | None:
        if self.verdicted == 0:
            return None
        return self.false_positive / self.verdicted

    @property
    def not_reviewed_rate(self) -> float | None:
        if self.total_fires == 0:
            return None
        return self.not_reviewed / self.total_fires


@dataclass
class GateVerdict:
    gate_id: str
    decision: str  # "PROMOTE" | "RECALIBRATE" | "CALIBRATING"
    reason: str
    stats: GateStats
    warnings: list[str] = field(default_factory=list)


def parse_log(content: str) -> tuple[dict[str, GateStats], list[tuple[int, str]]]:
    """Parse calibration-log.md content into per-gate stats.

    Returns (stats_by_gate, malformed_lines).
    malformed_lines contains (line_number, line_text) tuples for CAL-EMIT[
    prefixed lines that did not match the regex — surfaced as warnings.
    Non-CAL-EMIT lines (markdown prose, comments, header text) are ignored.

    Lines inside fenced code blocks (``` ... ```) are skipped so that
    format examples in the file header don't get parsed as records.
    """
    stats: dict[str, GateStats] = {}
    malformed: list[tuple[int, str]] = []
    in_fence = False

    for lineno, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()

        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.startswith("CAL-EMIT["):
            continue

        m = _CAL_EMIT_RE.match(line)
        if not m:
            malformed.append((lineno, line))
            continue

        gate = m.group("gate")
        if gate not in VALID_GATES:
            malformed.append((lineno, f"unknown gate-id: {gate}"))
            continue

        gs = stats.setdefault(gate, GateStats(gate_id=gate))
        gs.reviews.add(m.group("review"))

        verdict = m.group("verdict")
        if verdict == "legitimate":
            gs.legitimate += 1
        elif verdict == "false-positive":
            gs.false_positive += 1
        elif verdict == "not-reviewed":
            gs.not_reviewed += 1
        elif verdict == "PENDING":
            gs.pending += 1

    return stats, malformed


def evaluate_gate(stats: GateStats) -> GateVerdict:
    """Evaluate a single gate's stats against β+ thresholds."""
    warnings: list[str] = []
    n_reviews = len(stats.reviews)

    if stats.pending > 0:
        warnings.append(
            f"{stats.pending} PENDING records — DA has not verdicted them. "
            "Process violation: DA must verdict all CAL-EMIT[PENDING] at r2 exit-gate."
        )

    # Stall warning (directives.md line 470): >30% not-reviewed after 3 reviews.
    if n_reviews >= MIN_REVIEWS and stats.not_reviewed_rate is not None:
        if stats.not_reviewed_rate > NOT_REVIEWED_WARN_RATE:
            warnings.append(
                f"not-reviewed rate {stats.not_reviewed_rate:.0%} > "
                f"{NOT_REVIEWED_WARN_RATE:.0%} after {n_reviews} reviews — "
                "calibration stall. Lead should flag; sigma-audit may run this manually."
            )

    if n_reviews < MIN_REVIEWS:
        return GateVerdict(
            gate_id=stats.gate_id,
            decision="CALIBRATING",
            reason=f"only {n_reviews} distinct review(s) with fires (need ≥{MIN_REVIEWS})",
            stats=stats,
            warnings=warnings,
        )

    if stats.fp_rate is None:
        return GateVerdict(
            gate_id=stats.gate_id,
            decision="CALIBRATING",
            reason="no DA-verdicted records yet (only PENDING or not-reviewed)",
            stats=stats,
            warnings=warnings,
        )

    if stats.fp_rate > MAX_FP_RATE:
        return GateVerdict(
            gate_id=stats.gate_id,
            decision="RECALIBRATE",
            reason=(
                f"FP rate {stats.fp_rate:.0%} exceeds {MAX_FP_RATE:.0%} after "
                f"{n_reviews} reviews — gate heuristic needs refinement, ¬promotion"
            ),
            stats=stats,
            warnings=warnings,
        )

    if stats.verdicted < MIN_VERDICTED:
        return GateVerdict(
            gate_id=stats.gate_id,
            decision="CALIBRATING",
            reason=(
                f"FP rate {stats.fp_rate:.0%} within threshold but only "
                f"{stats.verdicted} DA-verdicted fires (need ≥{MIN_VERDICTED})"
            ),
            stats=stats,
            warnings=warnings,
        )

    return GateVerdict(
        gate_id=stats.gate_id,
        decision="PROMOTE",
        reason=(
            f"{n_reviews} reviews |FP rate {stats.fp_rate:.0%} ≤ "
            f"{MAX_FP_RATE:.0%} |{stats.verdicted} DA-verdicted ≥ {MIN_VERDICTED}"
        ),
        stats=stats,
        warnings=warnings,
    )


def format_verdict(v: GateVerdict) -> str:
    s = v.stats
    lines = [
        f"[{v.gate_id}] {v.decision}",
        f"  reason: {v.reason}",
        (
            f"  stats: reviews={len(s.reviews)} |fires={s.total_fires} "
            f"|legitimate={s.legitimate} |false-positive={s.false_positive} "
            f"|not-reviewed={s.not_reviewed} |pending={s.pending}"
        ),
    ]
    for w in v.warnings:
        lines.append(f"  WARN: {w}")
    return "\n".join(lines)


def run(log_path: Path, gate_filter: str | None = None) -> tuple[int, str]:
    """Read log_path, evaluate gates, return (exit_code, output_text)."""
    if not log_path.exists():
        return 3, f"ERROR: calibration log not found: {log_path}"

    try:
        content = log_path.read_text(encoding="utf-8")
    except OSError as e:
        return 3, f"ERROR: could not read {log_path}: {e}"

    stats_by_gate, malformed = parse_log(content)

    out: list[str] = []
    out.append(f"audit-calibration-gate |log: {log_path} |records: {sum(s.total_fires for s in stats_by_gate.values())}")

    if malformed:
        out.append("")
        out.append(f"MALFORMED ({len(malformed)} line(s)):")
        for lineno, text in malformed:
            out.append(f"  line {lineno}: {text}")

    gates_to_report = sorted(VALID_GATES) if gate_filter is None else [gate_filter]
    out.append("")
    for gate_id in gates_to_report:
        if gate_id not in VALID_GATES:
            out.append(f"[{gate_id}] UNKNOWN — valid gates: {sorted(VALID_GATES)}")
            continue
        if gate_id not in stats_by_gate:
            out.append(f"[{gate_id}] CALIBRATING\n  reason: 0 records\n  stats: reviews=0 |fires=0")
            out.append("")
            continue
        v = evaluate_gate(stats_by_gate[gate_id])
        out.append(format_verdict(v))
        out.append("")

    # Exit code: 2 only when file is structurally broken (no parseable records + malformed content present).
    # Mere absence of data is not an error — CALIBRATING is the intended state.
    exit_code = 0
    if malformed and not stats_by_gate:
        exit_code = 2

    return exit_code, "\n".join(out).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate β+ calibration thresholds for WARN-first gates (A20/A22/A23/A24)."
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_LOG_PATH,
        help=f"calibration-log path (default: {DEFAULT_LOG_PATH})",
    )
    parser.add_argument(
        "--gate",
        choices=sorted(VALID_GATES),
        default=None,
        help="evaluate one gate only (default: all)",
    )
    args = parser.parse_args(argv)

    exit_code, output = run(args.file, args.gate)
    sys.stdout.write(output)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
