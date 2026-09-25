#!/usr/bin/env python3
"""Chain evaluator for sigma-review / sigma-build atomic checklist enforcement.

Replaces the phase-based orchestrator + 11-bundle gate-check routing with a
single flat checklist evaluated at session end (Stop hook) or on demand (CLI).

Architecture:
  - Reuses check functions from gate_checks.py (imported as a library)
  - Adds peer-verification checks (A16-A18) — new to V2
  - Writes evaluation results to workspace as ## Chain Evaluation (A19)
  - Tracks rejection history for monotonicity enforcement

Usage:
  Stop hook:  python3 chain-evaluator.py              (auto-evaluates, writes to workspace)
  CLI:        python3 chain-evaluator.py evaluate      (full chain, stdout JSON)
  CLI:        python3 chain-evaluator.py status         (mechanical-only quick check)
  CLI:        python3 chain-evaluator.py item A5        (single item)
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import sigma_paths as sp  # noqa: E402
from typing import Any

# ---------------------------------------------------------------------------
# Import gate_checks as a library — reuse all 30 check functions
# ---------------------------------------------------------------------------

import gate_checks as gc  # noqa: E402  (same directory; sigma_paths put it on sys.path)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

VERSION = "2.0.0"
STATE_FILE = sp.STATE_DIR / ".chain-status.json"
DEFAULT_WORKSPACE = gc.DEFAULT_WORKSPACE


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ChainItem:
    """Single checklist item result."""
    item_id: str
    name: str
    passed: bool
    category: str  # "agent-work", "peer-verification", "chain-closure"
    details: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "name": self.name,
            "passed": self.passed,
            "category": self.category,
            "details": self.details,
            "issues": self.issues,
        }


@dataclass
class ChainResult:
    """Full chain evaluation result."""
    mode: str  # ANALYZE or BUILD
    complete: bool
    items: list[ChainItem] = field(default_factory=list)
    timestamp: str = ""
    version: str = VERSION

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def passed_count(self) -> int:
        return sum(1 for i in self.items if i.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for i in self.items if not i.passed)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "complete": self.complete,
            "passed": self.passed_count,
            "failed": self.failed_count,
            "total": len(self.items),
            "timestamp": self.timestamp,
            "version": self.version,
            "items": [i.to_dict() for i in self.items],
        }

    def summary_text(self) -> str:
        """Human-readable summary for workspace / systemMessage."""
        lines = [
            f"## Chain Evaluation",
            f"",
            f"Mode: {self.mode} | Status: {'COMPLETE' if self.complete else 'INCOMPLETE'} "
            f"| {self.passed_count}/{len(self.items)} items passed",
            f"Evaluator: chain-evaluator v{self.version} | {self.timestamp}",
            f"",
        ]
        for item in self.items:
            status = "PASS" if item.passed else "FAIL"
            lines.append(f"- [{status}] {item.item_id}: {item.name}")
            for issue in item.issues:
                lines.append(f"  - {issue}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Checklist items: ANALYZE chain (A1-A19)
# Each function wraps a gate_checks check or implements new logic.
# ---------------------------------------------------------------------------

def _wrap_gc(item_id: str, name: str, category: str, check_result: gc.CheckResult) -> ChainItem:
    """Convert a gate_checks.CheckResult to a ChainItem."""
    return ChainItem(
        item_id=item_id,
        name=name,
        passed=check_result.passed,
        category=category,
        details=check_result.details,
        issues=check_result.issues,
    )


def check_a1(content: str) -> ChainItem:
    """A1: Agent findings — non-empty workspace sections."""
    return _wrap_gc("A1", "Agent findings", "agent-work",
                     gc.check_agent_output_non_empty(content))


def check_a2(content: str) -> ChainItem:
    """A2: Source provenance on all findings."""
    return _wrap_gc("A2", "Source provenance", "agent-work",
                     gc.check_source_provenance(content))


def check_a3(content: str) -> ChainItem:
    """A3: Dialectical bootstrapping — DB[] depth check.

    Layered authority (IC[4], CAL[2]):
      - ``gc.check_dialectical_bootstrapping`` = PRESENCE (upstream, layer 1)
      - this check = DEPTH (layer 2, genuine-exercise count)
      - sequential, NOT redundant — no third layer

    R19 #19 fix (SQ[3]): the pre-rewrite ``re.findall`` matched every
    ``DB[...]`` substring in an agent section — including reference
    citations (``DB[F[A-1]]`` mentioned in prose, summary text linking
    to a prior DB exercise, etc.). That produced false-negative counts
    where 5 reference-DBs looked like 5 genuine exercises.

    Split-by-DB + require (1)(2)(3) marker sequence within a segment:
    genuine DB exercises follow the canonical format
    ``DB[finding]: (1) initial: X (2) assume-wrong: Y (3) strongest-counter: Z
    (4) re-estimate: W (5) reconciled: final``. The literal parenthesised
    numbered markers are the distinguishing signal — finding-reference
    citations lack them. Requiring at least (1), (2), and (3) catches
    partial exercises (which we flag as shallow) while excluding pure
    references from the count entirely.
    """
    result = gc.check_dialectical_bootstrapping(content)
    agents = gc.extract_agents_from_workspace(content)

    shallow_db = []
    genuine_by_agent: dict[str, int] = {}
    reference_by_agent: dict[str, int] = {}

    for agent in agents:
        section = gc._get_agent_section(content, agent)
        # Split the section by DB[ markers so each segment is a
        # candidate exercise (plus whatever prose follows it up to the
        # next DB[ or section boundary).
        segments = re.split(r"(?=DB\[)", section)
        genuine = 0
        references = 0
        for seg in segments:
            if not seg.lstrip().startswith("DB["):
                continue
            # Require parenthesised numbered markers (1), (2), (3) to
            # count as a genuine exercise. Presence of (1)+(2)+(3) is
            # the plan-spec signal per SQ[3] verification 4.
            has_1 = bool(re.search(r"\(\s*1\s*\)", seg))
            has_2 = bool(re.search(r"\(\s*2\s*\)", seg))
            has_3 = bool(re.search(r"\(\s*3\s*\)", seg))
            if has_1 and has_2 and has_3:
                genuine += 1
                # Shallow check — exercise present but missing 4/5 markers
                has_4 = bool(re.search(r"\(\s*4\s*\)", seg))
                has_5 = bool(re.search(r"\(\s*5\s*\)", seg))
                if not (has_4 and has_5):
                    missing = 5 - sum([has_1, has_2, has_3, has_4, has_5])
                    shallow_db.append(
                        f"{agent}: DB entry missing {missing} of 5 numbered markers"
                    )
            else:
                # Reference citation, not an exercise — counted separately
                references += 1
        if genuine:
            genuine_by_agent[agent] = genuine
        if references:
            reference_by_agent[agent] = references

    result.details["db_genuine_by_agent"] = genuine_by_agent
    result.details["db_reference_by_agent"] = reference_by_agent
    if shallow_db:
        result.issues.extend(shallow_db)
        result.details["shallow_db_entries"] = shallow_db

    return _wrap_gc("A3", "Dialectical bootstrapping", "agent-work", result)


def check_a4(content: str) -> ChainItem:
    """A4: Circuit breaker evidence."""
    return _wrap_gc("A4", "Circuit breaker", "agent-work",
                     gc.check_circuit_breaker(content))


def check_a5(content: str) -> ChainItem:
    """A5: DA challenges + agent responses."""
    return _wrap_gc("A5", "DA challenges + responses", "agent-work",
                     gc.check_cross_track_participation(content))


def check_a6(content: str) -> ChainItem:
    """A6: BELIEF state present."""
    return _wrap_gc("A6", "BELIEF state", "agent-work",
                     gc.check_belief_state_written(content))


def check_a7(content: str) -> ChainItem:
    """A7: Exit-gate format and criteria."""
    return _wrap_gc("A7", "Exit-gate", "agent-work",
                     gc.check_exit_gate_format(content))


def check_a8(content: str) -> ChainItem:
    """A8: Contamination check."""
    return _wrap_gc("A8", "Contamination check", "agent-work",
                     gc.check_contamination(content))


def check_a9(content: str) -> ChainItem:
    """A9: Source provenance audit."""
    return _wrap_gc("A9", "Source provenance audit", "agent-work",
                     gc.check_source_provenance_audit(content))


def check_a10(content: str) -> ChainItem:
    """A10: Anti-sycophancy check."""
    return _wrap_gc("A10", "Anti-sycophancy check", "agent-work",
                     gc.check_anti_sycophancy(content))


def check_a11(content: str) -> ChainItem:
    """A11: Synthesis artifact in archive."""
    return _wrap_gc("A11", "Synthesis artifact", "chain-closure",
                     gc.check_synthesis_artifact(content))


def check_a12(content: str) -> ChainItem:
    """A12: Workspace archive.

    24h grace-window (ADR[3]): archive-missing is acceptable when workspace
    was modified <24h ago — session is legitimately ongoing, archive is
    expected at session end. Past 24h, missing archive is a real failure.

    Grace is a synchronous mtime delta per CAL[1] — no poll/wait/sleep;
    the Stop hook is non-looping by design (line 625-640).
    """
    result = gc.check_session_end(content)
    archive_found = result.details.get("archive_file_found", False)
    passed = archive_found
    in_grace = False
    workspace_age_hours: float | None = None

    if not archive_found:
        workspace_path = Path(DEFAULT_WORKSPACE)
        if workspace_path.exists():
            age_seconds = datetime.now(timezone.utc).timestamp() - workspace_path.stat().st_mtime
            workspace_age_hours = age_seconds / 3600.0
            if workspace_age_hours < 24.0:
                passed = True
                in_grace = True

    details = {k: v for k, v in result.details.items() if "archive" in k.lower()}
    details["grace_window_applied"] = in_grace
    if workspace_age_hours is not None:
        details["workspace_age_hours"] = round(workspace_age_hours, 2)

    issues = [] if passed else [i for i in result.issues if "archive" in i.lower()]
    if in_grace:
        issues.append(
            f"A12 archive missing but workspace <24h old "
            f"(age={workspace_age_hours:.1f}h) — grace-window applied, "
            f"archive expected at session end"
        )

    return ChainItem(
        item_id="A12",
        name="Workspace archive",
        passed=passed,
        category="chain-closure",
        details=details,
        issues=issues,
    )


def check_a13(content: str) -> ChainItem:
    """A13: Promotion evidence."""
    return _wrap_gc("A13", "Promotion evidence", "chain-closure",
                     gc.check_promotion_content(content))


# Shared parser helpers per ADR[9]: BOM-strip, fenced-code exclusion before
# section-header search. Used by A25/A26/B5/B6 — all new gates.
_BOM_RE = re.compile(r"^﻿")
_FENCED_BLOCK_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)


def _strip_bom(text: str) -> str:
    """Strip leading BOM if present (per ADR[9])."""
    return _BOM_RE.sub("", text)


def _strip_fenced_blocks(text: str) -> str:
    """Replace fenced ``` ... ``` blocks with blank lines (preserve line offsets).

    Used before section-header detection so headers inside fenced blocks
    don't trigger false matches (per ADR[9]).
    """
    def _replace(m: re.Match) -> str:
        # Preserve newline count so downstream offsets stay aligned.
        return "\n" * m.group(0).count("\n")
    return _FENCED_BLOCK_RE.sub(_replace, text)


# A14 race-fix per ADR[1]/IC[1]: shared/calibration-log.md is a CAL-EMIT
# append-only sink that hooks write at session end. It can race with the
# A14 git-clean check, producing false-positive dirty status. Wrapper-only
# (NOT in gc.check_session_end — A12 protection of shared helper).
_A14_CALIBRATION_LOG_RE = re.compile(r"calibration-log\.md$")
_A14_REPO_PATH = sp.archive_repo()


def _a14_filtered_uncommitted(repo_path: str | None = _A14_REPO_PATH) -> tuple[list[str] | None, str | None]:
    """Re-run `git status --porcelain` independently for full untruncated list,
    apply calibration-log.md exclusion. Returns (filtered_list, error).

    Wrapper-only per ADR[1]: does NOT mutate gc.check_session_end. On
    subprocess failure, returns (None, error) so caller can fall back to
    gc's capped list.
    """
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return None, str(e)
    if result.returncode != 0:
        return None, f"git exit {result.returncode}: {result.stderr.strip()[:200]}"
    raw = [line for line in result.stdout.splitlines() if line.strip()]
    filtered: list[str] = []
    for line in raw:
        # Porcelain format: 'XY path' (XY = 2-char status, then space, then path).
        # Path field starts at index 3.
        path = line[3:] if len(line) > 3 else line
        if _A14_CALIBRATION_LOG_RE.search(path):
            continue
        filtered.append(line)
    return filtered, None


def check_a14(content: str) -> ChainItem:
    """A14: Git clean (race-fix wrapper per ADR[1]/IC[1]).

    Re-runs `git status --porcelain` independently for full untruncated list
    (cap-at-10 fix), applies calibration-log.md exclusion (CAL-EMIT race fix),
    falls back to gc.check_session_end capped list if subprocess fails.
    """
    if _A14_REPO_PATH is None:
        return ChainItem(
            item_id="A14",
            name="Git clean",
            passed=True,
            category="chain-closure",
            details={"a14_wrapper_status": "N/A: no archive repo — set SIGMA_ARCHIVE_REPO "
                     "or put ~/.claude/teams/sigma-review under git to enable"},
            issues=[],
        )
    result = gc.check_session_end(content, repo_path=_A14_REPO_PATH)
    base_details = {
        k: v for k, v in result.details.items()
        if "git" in k.lower() or "commit" in k.lower()
    }
    base_issues = [
        i for i in result.issues
        if "git" in i.lower() or "commit" in i.lower() or "push" in i.lower()
    ]

    filtered, err = _a14_filtered_uncommitted(_A14_REPO_PATH)
    if filtered is None:
        # Subprocess failed → use gc capped list with limitation note.
        base_details["a14_wrapper_status"] = f"fallback-to-gc-capped: {err}"
        base_details["a14_calibration_log_excluded"] = False
        return ChainItem(
            item_id="A14",
            name="Git clean",
            passed=result.details.get("git_clean", False),
            category="chain-closure",
            details=base_details,
            issues=base_issues,
        )

    git_clean = len(filtered) == 0
    base_details["a14_wrapper_status"] = "active"
    base_details["a14_calibration_log_excluded"] = True
    base_details["uncommitted_count"] = len(filtered)
    base_details["uncommitted_files"] = filtered  # full list, not capped
    base_details["git_clean"] = git_clean

    issues: list[str] = []
    # Preserve unpushed/git-error issues from gc; replace dirty-files issue
    # with wrapper's filtered count.
    for i in base_issues:
        if "uncommitted" in i.lower():
            continue
        issues.append(i)
    if not git_clean:
        issues.append(f"Uncommitted changes in repo: {len(filtered)} files (calibration-log.md excluded)")

    return ChainItem(
        item_id="A14",
        name="Git clean",
        passed=git_clean and result.details.get("unpushed_commits", 0) == 0,
        category="chain-closure",
        details=base_details,
        issues=issues,
    )


def check_a15(content: str) -> ChainItem:
    """A15: XVERIFY coverage (conditional on availability)."""
    return _wrap_gc("A15", "XVERIFY coverage", "agent-work",
                     gc.check_xverify_coverage(content))


# ---------------------------------------------------------------------------
# Peer verification checks (A16-A18) — NEW
# ---------------------------------------------------------------------------

_PEER_VERIFY_HEADER = re.compile(
    r"^### Peer Verification:\s*(\S+)\s+verifying\s+(\S+)",
    re.MULTILINE | re.IGNORECASE,
)


def _extract_peer_verifications(content: str) -> list[dict[str, str]]:
    """Extract all peer verification sections from workspace.

    Returns list of {verifier, verified, section_text}.
    """
    verifications = []
    matches = list(_PEER_VERIFY_HEADER.finditer(content))

    for i, m in enumerate(matches):
        start = m.end()
        # Section runs until next ### or ## or end
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        # Also stop at next ## or ### that isn't a peer verification
        next_header = re.search(r"^#{2,3}\s", content[start:end], re.MULTILINE)
        if next_header:
            end = start + next_header.start()

        verifications.append({
            "verifier": m.group(1).lower().strip(),
            "verified": m.group(2).lower().strip(),
            "text": content[start:end].strip(),
        })

    return verifications


def check_a16(content: str) -> ChainItem:
    """A16: Peer verification sections exist.

    Each non-DA agent must have at least one ### Peer Verification: section
    where they verify another agent.
    """
    agents = gc.extract_agents_from_workspace(content)
    verifications = _extract_peer_verifications(content)
    verifier_names = {v["verifier"] for v in verifications}

    agents_without_verification = [a for a in agents if a not in verifier_names]

    return ChainItem(
        item_id="A16",
        name="Peer verification sections",
        passed=len(agents_without_verification) == 0,
        category="peer-verification",
        details={
            "agents": agents,
            "verifications_found": len(verifications),
            "agents_without_verification": agents_without_verification,
        },
        issues=[
            f"Agent '{a}' has no peer verification section" for a in agents_without_verification
        ],
    )


def check_a17(content: str) -> ChainItem:
    """A17: Verification specificity.

    Each peer verification must reference >=3 specific artifact IDs from the
    verified agent's workspace section. Generic confirmations fail.
    """
    verifications = _extract_peer_verifications(content)
    insufficient = []

    # Patterns that count as specific artifact references
    artifact_patterns = [
        r"DB\[[\w-]+\]",           # DB[finding-name]
        r"F\[[\w-]+\]",            # F[finding-id]
        r"FINDING\[[\w-]+\]",      # FINDING[id]
        r"XVERIFY\[[\w:-]+\]",     # XVERIFY[provider:model]
        r"H\d+",                    # H1, H2, etc.
        r"CB\[\d\]",               # CB[1], CB[2]
        r"BELIEF\[[\w]+\]",        # BELIEF[rN]
        r"DA\[#?\d+\]",            # DA[#1]
        r"ADR\[\d+\]",             # ADR[1]
        r"SQ\[\d+\]",              # SQ[1]
        r"IC\[\d+\]",              # IC[1]
        r"\|source:[\w-]+",        # |source:code-read
        r"T[123][-\s]",            # T1, T2, T3 quality tier
    ]

    for v in verifications:
        text = v["text"]
        refs_found = 0
        for pattern in artifact_patterns:
            refs_found += len(re.findall(pattern, text, re.IGNORECASE))

        if refs_found < 3:
            insufficient.append(
                f"{v['verifier']} verifying {v['verified']}: "
                f"only {refs_found} specific artifact references (need >=3)"
            )

    return ChainItem(
        item_id="A17",
        name="Verification specificity",
        passed=len(insufficient) == 0,
        category="peer-verification",
        details={
            "verifications_checked": len(verifications),
            "insufficient": insufficient,
        },
        issues=insufficient,
    )


def check_a18(content: str) -> ChainItem:
    """A18: Verification coverage matrix.

    Every agent must be verified by at least 2 others (1 ring peer + DA).
    Build an NxN verification matrix and check full row coverage.
    """
    agents = gc.extract_agents_from_workspace(content)
    verifications = _extract_peer_verifications(content)

    # Also count DA challenges as verification of all agents
    da_section = gc._get_agent_section(content, "devils-advocate")
    da_verifies_all = bool(re.search(
        r"(?:DA\[#?\d+\]|exit-gate|challenge)", da_section, re.IGNORECASE
    ))

    # Build coverage: who verified whom
    verified_by: dict[str, set[str]] = {a: set() for a in agents}
    for v in verifications:
        if v["verified"] in verified_by:
            verified_by[v["verified"]].add(v["verifier"])

    # DA counts as a verifier for all agents
    if da_verifies_all:
        for a in agents:
            verified_by[a].add("devils-advocate")

    # Check coverage: each agent needs >=2 verifiers
    under_covered = []
    for agent, verifiers in verified_by.items():
        if len(verifiers) < 2:
            under_covered.append(
                f"Agent '{agent}' verified by only {len(verifiers)}: {verifiers or 'none'}"
            )

    return ChainItem(
        item_id="A18",
        name="Verification coverage matrix",
        passed=len(under_covered) == 0,
        category="peer-verification",
        details={
            "agents": agents,
            "coverage": {a: list(v) for a, v in verified_by.items()},
            "da_verifies_all": da_verifies_all,
            "under_covered": under_covered,
        },
        issues=under_covered,
    )


# ---------------------------------------------------------------------------
# BUILD-specific checks (B1-B4)
# ---------------------------------------------------------------------------

def check_b1(content: str) -> ChainItem:
    """B1: Plan lock — ADR/DS/IC sections populated."""
    return _wrap_gc("B1", "Plan lock", "agent-work",
                     gc.check_plan_lock(content))


def check_b2(content: str) -> ChainItem:
    """B2: Build checkpoints."""
    return _wrap_gc("B2", "Build checkpoints", "agent-work",
                     gc.check_checkpoint(content))


def check_b3(content: str) -> ChainItem:
    """B3: Merge verified (if parallel engineers)."""
    return _wrap_gc("B3", "Merge verified", "agent-work",
                     gc.check_merge_verified(content))


def check_b4(content: str) -> ChainItem:
    """B4: Build-track source tags."""
    return _wrap_gc("B4", "Build-track source tags", "agent-work",
                     gc.check_build_track_source_tags(content))


# ---------------------------------------------------------------------------
# CAL-EMIT helpers (path β+ WARN-first gates: A20, A22, A23)
#
# Schema (directives.md §2i lines 351-352, §2j line 434, §2d-severity line 409):
#   CAL-EMIT[{gate-id}]: review-id:{slug} |finding-ref:{F[agent-id]}
#     |fire-reason:{trigger} |workspace-context:{agent}:{50-char-excerpt}
#     |da-verdict:PENDING
#
# Append-only write to shared/calibration-log.md (CQA SQ[CDS-9] target).
# Calibration gate (CDS SQ[CDS-10]) consumes these records to evaluate
# the ≥3-review + ≤20%-FP promotion threshold per path β+.
# ---------------------------------------------------------------------------

CALIBRATION_LOG_PATH = (
    sp.CALIBRATION_LOG
)


def _review_id_from_content(content: str) -> str:
    """Derive a stable review-id slug from workspace header metadata.

    Preference order:
      1. ## build-id or ## review-id header value (explicit)
      2. date prefix from workspace mtime + first-line task excerpt
      3. fallback: today's date + "unnamed"
    """
    m = re.search(r"^##\s*(?:build-id|review-id)\s*:?\s*(.+?)$",
                  content, re.MULTILINE | re.IGNORECASE)
    if m:
        slug = m.group(1).strip()
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug).strip("-")
        if slug:
            return slug
    # Date-prefixed fallback
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    task_match = re.search(r"^##\s*task\s*\n+(.+?)$", content,
                           re.MULTILINE | re.IGNORECASE | re.DOTALL)
    if task_match:
        excerpt = task_match.group(1).splitlines()[0].strip()[:30]
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", excerpt).strip("-")
        if slug:
            return f"{today}-{slug}"
    return f"{today}-unnamed"


def _emit_cal_record(
    gate_id: str,
    review_id: str,
    finding_ref: str,
    fire_reason: str,
    agent: str,
    excerpt: str,
) -> str:
    """Format a CAL-EMIT record per the directives.md §2i schema + append.

    Returns the formatted record string so check functions can stash it
    on details for deterministic testing (CQA SQ[CDS-6..8] tests can
    assert on the emitted record without reading the file).

    Append-only. Never replaces calibration-log.md content. If the file
    does not exist or the write fails, the record is still returned so
    tests can observe detection without a live filesystem dependency.
    """
    # Producer-side pipe-escape: CAL-EMIT record uses `|` as field delimiter,
    # so literal pipes in excerpts break downstream parsing. Translate to `/`
    # before truncation (CDS XVERIFIED openai+google high-agree; DA confirmed).
    clean_excerpt = excerpt.replace("\n", " ").replace("|", "/").strip()[:50]
    record = (
        f"CAL-EMIT[{gate_id}]: review-id:{review_id} "
        f"|finding-ref:{finding_ref} "
        f"|fire-reason:{fire_reason} "
        f"|workspace-context:{agent}:{clean_excerpt} "
        f"|da-verdict:PENDING"
    )
    try:
        if CALIBRATION_LOG_PATH.exists():
            with CALIBRATION_LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(record + "\n")
    except OSError:
        # Silent: calibration-log.md is optional infrastructure per plan;
        # if the write fails the in-memory record still surfaces in
        # workspace chain-evaluation details for downstream DA verdict.
        pass
    return record


# Regex helpers shared across A20/A22/A23 detection.
_FINDING_LINE_RE = re.compile(
    r"^F\[([A-Za-z0-9._-]+)\]\s*(.+?)$",
    re.MULTILINE,
)


def _iter_finding_lines(section: str):
    """Yield (finding_id, full_line_text) for each F[...] finding."""
    for m in _FINDING_LINE_RE.finditer(section):
        yield m.group(1), m.group(0)


# ---------------------------------------------------------------------------
# A20: §2i precision gate (CONDITION 2 code-detected, CONDITION 1 deferred)
# ---------------------------------------------------------------------------

_CONFIDENCE_70_RE = re.compile(
    r"(?:>\s*70\s*%|>=\s*7[0-9]\s*%|>\s*7[0-9]\s*%|\b(?:7[0-9]|[8-9][0-9]|100)\s*%\s*confiden[ct])",
    re.IGNORECASE,
)
_HIGH_SEVERITY_RE = re.compile(
    r"\b(?:HIGH|CRITICAL)[-\s]severity\b",
    re.IGNORECASE,
)
_PRIMARY_REC_RE = re.compile(
    r"\b(?:primary[-\s]recommendation|primary[-\s]conclusion)\b",
    re.IGNORECASE,
)

# CONDITION 1 suppression heuristic — if any of these keywords is
# adjacent to the finding, we treat CONDITION 1 as satisfied and do NOT
# fire. Per directive line 340: driver-breakdown, CI notation, and
# qualitative qualifiers all suppress.
_CONDITION_1_SUPPRESSORS = [
    r"derives\s+from\s*:\s*\[",    # driver breakdown
    r"\b80%\s*CI\b",                # CI notation
    r"\b90%\s*CI\b",
    r"\b95%\s*CI\b",
    r"\bRC\[",                       # reference class
    r"\border[-\s]of[-\s]magnitude\b",
    r"\billustrative\b",
    r"\bapproximately\b",
]
_CONDITION_1_SUPPRESSOR_RE = re.compile(
    "|".join(_CONDITION_1_SUPPRESSORS), re.IGNORECASE
)


def check_a20_precision_gate(content: str) -> ChainItem:
    """A20: §2i precision gate — WARN + CAL-EMIT (path β+).

    Fires WARN when a finding meets CONDITION 2 (load-bearing markers:
    >70% confidence, HIGH/CRITICAL severity, or primary-recommendation
    cited) AND lacks CONDITION 1 suppressors (driver breakdown, CI,
    qualitative qualifier). CONDITION 1 full-semantic detection is
    explicitly deferred per ADR[CDS-2] + DA[#5]; we apply the suppression
    heuristic (directive line 340) on the same line/neighborhood.

    Never BLOCKs — path β+ calibration window requires ≥3 reviews with
    ≤20% FP before lead promotes WARN→BLOCK. Until then, WARN only.
    """
    agents = gc.extract_agents_from_workspace(content)
    review_id = _review_id_from_content(content)
    fires: list[dict[str, str]] = []
    cal_records: list[str] = []

    for agent in agents:
        section = gc._get_agent_section(content, agent)
        for finding_id, line in _iter_finding_lines(section):
            # CONDITION 2 triggers — at least one must hit
            trigger = None
            if _CONFIDENCE_70_RE.search(line):
                trigger = "confidence>=70%"
            elif _HIGH_SEVERITY_RE.search(line):
                trigger = "HIGH/CRITICAL-severity"
            elif _PRIMARY_REC_RE.search(line):
                trigger = "primary-recommendation-cited"
            if not trigger:
                continue
            # CONDITION 1 suppression heuristic — skip if driver/CI/qualifier
            if _CONDITION_1_SUPPRESSOR_RE.search(line):
                continue
            record = _emit_cal_record(
                gate_id="A20",
                review_id=review_id,
                finding_ref=f"F[{finding_id}]",
                fire_reason=trigger,
                agent=agent,
                excerpt=line,
            )
            fires.append({
                "agent": agent,
                "finding_id": finding_id,
                "trigger": trigger,
            })
            cal_records.append(record)

    # WARN-only: passes chain check regardless. Fires surface via issues
    # for operator visibility and via details for DA verdict downstream.
    return ChainItem(
        item_id="A20",
        name="§2i precision gate (WARN, path β+)",
        passed=True,
        category="agent-work",
        details={
            "fires": fires,
            "fire_count": len(fires),
            "cal_emit_records": cal_records,
            "path": "β+ WARN-first",
            "review_id": review_id,
        },
        issues=[
            f"A20 WARN: §2i precision gate fired for F[{f['finding_id']}] "
            f"(agent={f['agent']}, trigger={f['trigger']}) — CAL-EMIT "
            f"written to calibration-log.md, DA verdict PENDING"
            for f in fires
        ],
    )


# ---------------------------------------------------------------------------
# A22: §2j governance minimum artifact (TIER-A/B/C detection)
# ---------------------------------------------------------------------------

_GOVERNANCE_MARKERS_RE = re.compile(
    r"\b(?:committee\s+structure|approval\s+process|oversight\s+role|"
    r"compliance\s+requirement|audit\s+function|governance\s+control)\b",
    re.IGNORECASE,
)
_TIER_ARTIFACT_RE = re.compile(
    r"\bTIER[-\s]?[ABC]\b",
    re.IGNORECASE,
)
_ARTIFACT_GAP_RE = re.compile(
    r"\bARTIFACT[-\s]?GAP\s*:\s*\S+",
    re.IGNORECASE,
)


def check_a22_governance_artifact(content: str) -> ChainItem:
    """A22: §2j HIGH-severity governance minimum artifact — WARN + CAL-EMIT.

    Fires WARN when a finding is HIGH/CRITICAL-severity AND contains a
    governance-scope marker (committee/approval/oversight/compliance/
    audit) AND lacks both a TIER-A/B/C artifact tag and an
    ARTIFACT-GAP:{reason} tag. Per directive line 434.

    Scope is narrow (governance domain only) per directive line 420 to
    prevent anti-gold-plating over-fire on technical/market findings.
    Never BLOCKs — path β+ WARN-first until calibration gate PROMOTEs.
    """
    agents = gc.extract_agents_from_workspace(content)
    review_id = _review_id_from_content(content)
    fires: list[dict[str, str]] = []
    cal_records: list[str] = []

    for agent in agents:
        section = gc._get_agent_section(content, agent)
        for finding_id, line in _iter_finding_lines(section):
            # Must be HIGH/CRITICAL severity
            if not _HIGH_SEVERITY_RE.search(line):
                continue
            # Must be in governance scope
            if not _GOVERNANCE_MARKERS_RE.search(line):
                continue
            # Inspect the finding line + ~3 following lines for tier/gap tag
            line_end = section.find(line) + len(line)
            # Grab up to next finding or section boundary (cap at 800 chars)
            tail_end = min(line_end + 800, len(section))
            tail = section[line_end:tail_end]
            next_finding = _FINDING_LINE_RE.search(tail)
            if next_finding:
                tail = tail[: next_finding.start()]
            window = line + tail
            if _TIER_ARTIFACT_RE.search(window):
                continue
            if _ARTIFACT_GAP_RE.search(window):
                continue
            record = _emit_cal_record(
                gate_id="A22",
                review_id=review_id,
                finding_ref=f"F[{finding_id}]",
                fire_reason="HIGH-severity-governance-no-TIER-artifact",
                agent=agent,
                excerpt=line,
            )
            fires.append({
                "agent": agent,
                "finding_id": finding_id,
                "trigger": "HIGH-severity-governance-no-TIER-artifact",
            })
            cal_records.append(record)

    return ChainItem(
        item_id="A22",
        name="§2j governance minimum artifact (WARN, path β+)",
        passed=True,
        category="agent-work",
        details={
            "fires": fires,
            "fire_count": len(fires),
            "cal_emit_records": cal_records,
            "path": "β+ WARN-first",
            "review_id": review_id,
        },
        issues=[
            f"A22 WARN: §2j governance artifact missing on F[{f['finding_id']}] "
            f"(agent={f['agent']}) — expected TIER-A/B/C tag or "
            f"ARTIFACT-GAP:{{reason}}, neither found. CAL-EMIT written, "
            f"DA verdict PENDING"
            for f in fires
        ],
    )


# ---------------------------------------------------------------------------
# A23: §2d-severity provenance (severity-basis tag on extrapolated severity)
# ---------------------------------------------------------------------------

_SEVERITY_BASIS_RE = re.compile(
    r"\|\s*severity-basis\s*:",
    re.IGNORECASE,
)
# Cross-domain / extrapolation indicators — when one of these appears in
# a HIGH/CRITICAL-severity finding, §2d-severity requires a
# severity-basis tag. We keep the markers narrow to avoid over-fire on
# findings where severity is native to the domain of the source.
_EXTRAPOLATION_INDICATORS_RE = re.compile(
    r"\b(?:extrapolat\w+|transfer[-\s]assumption|cross[-\s]domain|"
    r"applied\s+to|by\s+analogy)\b",
    re.IGNORECASE,
)


def check_a23_severity_provenance(content: str) -> ChainItem:
    """A23: §2d-severity provenance — WARN + CAL-EMIT when severity-basis missing.

    Fires WARN when a finding is HIGH/CRITICAL severity AND the finding
    line (or its immediate window) contains a cross-domain /
    extrapolation indicator AND lacks the |severity-basis:| tag per
    directive line 409.

    Scope is narrow per directive line 409: absence only counts as a
    violation when cross-domain indicators are present — native-domain
    severity findings do not require the tag.
    """
    agents = gc.extract_agents_from_workspace(content)
    review_id = _review_id_from_content(content)
    fires: list[dict[str, str]] = []
    cal_records: list[str] = []

    for agent in agents:
        section = gc._get_agent_section(content, agent)
        for finding_id, line in _iter_finding_lines(section):
            if not _HIGH_SEVERITY_RE.search(line):
                continue
            # Look at the finding line + next ~500 chars for both the
            # extrapolation indicator and the severity-basis tag.
            line_end = section.find(line) + len(line)
            tail_end = min(line_end + 500, len(section))
            tail = section[line_end:tail_end]
            next_finding = _FINDING_LINE_RE.search(tail)
            if next_finding:
                tail = tail[: next_finding.start()]
            window = line + tail
            if not _EXTRAPOLATION_INDICATORS_RE.search(window):
                continue  # native-domain severity — no tag required
            if _SEVERITY_BASIS_RE.search(window):
                continue  # tag present — compliant
            record = _emit_cal_record(
                gate_id="A23",
                review_id=review_id,
                finding_ref=f"F[{finding_id}]",
                fire_reason="extrapolated-severity-missing-basis-tag",
                agent=agent,
                excerpt=line,
            )
            fires.append({
                "agent": agent,
                "finding_id": finding_id,
                "trigger": "extrapolated-severity-missing-basis-tag",
            })
            cal_records.append(record)

    return ChainItem(
        item_id="A23",
        name="§2d-severity provenance (WARN, path β+)",
        passed=True,
        category="agent-work",
        details={
            "fires": fires,
            "fire_count": len(fires),
            "cal_emit_records": cal_records,
            "path": "β+ WARN-first",
            "review_id": review_id,
        },
        issues=[
            f"A23 WARN: §2d-severity missing severity-basis tag on "
            f"F[{f['finding_id']}] (agent={f['agent']}) — extrapolation "
            f"indicator present but |severity-basis:| tag absent. "
            f"CAL-EMIT written, DA verdict PENDING"
            for f in fires
        ],
    )


# ---------------------------------------------------------------------------
# A24: sigma-verify init pre-flight — WARN on load-bearing findings that
# lack XVERIFY coverage when ΣVerify was MCP-available this session.
# ---------------------------------------------------------------------------

# Same-line / small-window presence check. XVERIFY[provider:model] OR
# XVERIFY-FAIL[provider:model] OR XVERIFY-PARTIAL[...] count as covered.
# SQ[7]/ADR[7]/IC[7]: bracket-required form — prose mentions of "XVERIFY"
# (e.g., narration "XVERIFY: TBD", "XVERIFY (note)") MUST NOT suppress A24.
# Single consumer at A24 (search below); grep-audit confirmed no other call sites.
_XVERIFY_ANY_RE = re.compile(
    r"\bXVERIFY(?:-(?:FAIL|PARTIAL))?\[",
    re.IGNORECASE,
)


def check_a24_sigma_verify_coverage(content: str) -> ChainItem:
    """A24: sigma-verify init pre-flight (WARN, path β+).

    Scope (narrow, per DA[#1] r1 finding + SS r1 ship recommendation):
      - ΣVerify is MCP-available per workspace ## infrastructure pre-flight
      - Finding has a load-bearing marker (>=70% confidence, HIGH/CRITICAL
        severity, or primary-recommendation citation — same detectors as A20)
      - Finding's line + 500-char window does NOT contain an XVERIFY / XVERIFY-FAIL /
        XVERIFY-PARTIAL tag

    What A24 catches: load-bearing findings written without XVERIFY coverage
    when ΣVerify was available (agent skipped the mandatory §2h step).

    What A24 does NOT catch: runtime authorization gaps or MCP-Registry
    advertisement issues — those are sigma-verify server-side concerns per
    IC[8] gateway-semantic-contract (see sigma-verify/machine.py docstring).

    A15 (gc.check_xverify_coverage) is the per-agent binary check; A24 is
    the per-finding β+ calibration gate — complementary, not redundant.
    """
    review_id = _review_id_from_content(content)
    fires: list[dict[str, str]] = []
    cal_records: list[str] = []

    # Gate: only fire when ΣVerify was available this session.
    if not gc.is_sigverify_available(content):
        return ChainItem(
            item_id="A24",
            name="sigma-verify init pre-flight (WARN, path β+)",
            passed=True,
            category="agent-work",
            details={
                "fires": [],
                "fire_count": 0,
                "cal_emit_records": [],
                "path": "β+ WARN-first",
                "review_id": review_id,
                "skip_reason": "ΣVerify unavailable — A24 does not apply",
            },
            issues=[],
        )

    agents = gc.extract_agents_from_workspace(content)
    for agent in agents:
        section = gc._get_agent_section(content, agent)
        for finding_id, line in _iter_finding_lines(section):
            # Load-bearing check — reuse A20 triggers verbatim
            trigger = None
            if _CONFIDENCE_70_RE.search(line):
                trigger = "confidence>=70%"
            elif _HIGH_SEVERITY_RE.search(line):
                trigger = "HIGH/CRITICAL-severity"
            elif _PRIMARY_REC_RE.search(line):
                trigger = "primary-recommendation-cited"
            if not trigger:
                continue
            # Window around the finding — line + next 500 chars, bounded by
            # the next F[] so we don't bleed into sibling findings.
            line_end = section.find(line) + len(line)
            tail_end = min(line_end + 500, len(section))
            tail = section[line_end:tail_end]
            next_finding = _FINDING_LINE_RE.search(tail)
            if next_finding:
                tail = tail[: next_finding.start()]
            window = line + tail
            if _XVERIFY_ANY_RE.search(window):
                continue  # XVERIFY / XVERIFY-FAIL / XVERIFY-PARTIAL present
            record = _emit_cal_record(
                gate_id="A24",
                review_id=review_id,
                finding_ref=f"F[{finding_id}]",
                fire_reason=f"load-bearing-without-xverify:{trigger}",
                agent=agent,
                excerpt=line,
            )
            fires.append({
                "agent": agent,
                "finding_id": finding_id,
                "trigger": trigger,
            })
            cal_records.append(record)

    return ChainItem(
        item_id="A24",
        name="sigma-verify init pre-flight (WARN, path β+)",
        passed=True,
        category="agent-work",
        details={
            "fires": fires,
            "fire_count": len(fires),
            "cal_emit_records": cal_records,
            "path": "β+ WARN-first",
            "review_id": review_id,
        },
        issues=[
            f"A24 WARN: load-bearing F[{f['finding_id']}] "
            f"(agent={f['agent']}, trigger={f['trigger']}) has no XVERIFY / "
            f"XVERIFY-FAIL tag — sigma-verify was available this session. "
            f"CAL-EMIT written, DA verdict PENDING"
            for f in fires
        ],
    )


# ---------------------------------------------------------------------------
# A26: Plan-completeness (WARN, path β+)
#
# Trigger: anchored `^## plan-file\s*$` header (case-sensitive, BOM-aware,
# fenced-code excluded). Per ADR[3]/IC[2]:
#   - `## plans` (different word) → no trigger
#   - `## plan-file:` (inline form, colon-followed) → no trigger
#   - `### plan-file` (3-hash) → no trigger
#   - inside fenced ``` ... ``` → no trigger
#
# Body check: parse plan-file path (header line allows `## plan-file: <path>`
# alternative — but ADR[3] excludes that anchor; the canonical workspace
# convention is `## plan-file: <path>` inline so A26 reads the inline-form
# value from a separate `^## plan-file:\s*(\S+)` capture for the path, then
# verifies the file exists. WARN on missing file.
# ---------------------------------------------------------------------------

# Header trigger (anchored, no colon, two-hash, end-of-line)
_A26_PLAN_FILE_HEADER_RE = re.compile(r"^## plan-file\s*$", re.MULTILINE)
# Inline path capture (used to extract path; NOT the trigger anchor)
_A26_PLAN_FILE_PATH_RE = re.compile(
    r"^## plan-file\s*:\s*(\S.*?)\s*$", re.MULTILINE
)


def check_a26_plan_completeness(content: str) -> ChainItem:
    """A26: Plan-completeness — WARN-first when `## plan-file` header is
    present but the referenced plan file is missing or incomplete.

    Trigger anchoring (ADR[3]/IC[2]):
      - matches `## plan-file` exactly (anchored, case-sensitive)
      - DOES NOT match `## plans`, `## plan-file:`, `### plan-file`,
        or fenced-code occurrences
    """
    review_id = _review_id_from_content(content)
    fires: list[dict[str, str]] = []
    cal_records: list[str] = []

    stripped = _strip_fenced_blocks(_strip_bom(content))
    header_match = _A26_PLAN_FILE_HEADER_RE.search(stripped)
    inline_path_match = _A26_PLAN_FILE_PATH_RE.search(stripped)

    if not header_match and not inline_path_match:
        return ChainItem(
            item_id="A26",
            name="Plan-completeness (WARN, path β+)",
            passed=True,
            category="agent-work",
            details={
                "fires": [],
                "fire_count": 0,
                "cal_emit_records": [],
                "path": "β+ WARN-first",
                "review_id": review_id,
                "skip_reason": "no `## plan-file` header in workspace",
            },
            issues=[],
        )

    plan_path: str | None = None
    parse_mode: str = "none"
    if inline_path_match:
        plan_path = inline_path_match.group(1).strip()
        parse_mode = "inline-colon"
    elif header_match:
        # Header anchored without colon — read first non-empty line below
        tail_start = header_match.end()
        tail = stripped[tail_start:tail_start + 500]
        for line in tail.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                break
            plan_path = line
            parse_mode = "header-then-line"
            break

    plan_exists = False
    plan_resolved: str | None = None
    if plan_path:
        plan_resolved = str(Path(plan_path).expanduser())
        plan_exists = Path(plan_resolved).is_file()

    if plan_path and not plan_exists:
        record = _emit_cal_record(
            gate_id="A26",
            review_id=review_id,
            finding_ref=f"PLAN[{plan_path[:30]}]",
            fire_reason="plan-file-referenced-but-missing",
            agent="lead",
            excerpt=f"plan-path={plan_path}",
        )
        fires.append({
            "trigger": "plan-file-missing",
            "plan_path": plan_path,
            "parse_mode": parse_mode,
        })
        cal_records.append(record)
    elif not plan_path:
        record = _emit_cal_record(
            gate_id="A26",
            review_id=review_id,
            finding_ref="PLAN[unparsed]",
            fire_reason="plan-file-header-present-but-no-path-parsed",
            agent="lead",
            excerpt="header present, path empty",
        )
        fires.append({
            "trigger": "plan-file-no-path",
            "plan_path": None,
            "parse_mode": parse_mode,
        })
        cal_records.append(record)

    return ChainItem(
        item_id="A26",
        name="Plan-completeness (WARN, path β+)",
        passed=True,  # WARN-first per H1
        category="agent-work",
        details={
            "fires": fires,
            "fire_count": len(fires),
            "cal_emit_records": cal_records,
            "path": "β+ WARN-first",
            "review_id": review_id,
            "plan_path": plan_path,
            "plan_resolved": plan_resolved,
            "plan_exists": plan_exists,
            "parse_mode": parse_mode,
        },
        issues=[
            f"A26 WARN: {f['trigger']} — plan_path={f.get('plan_path')!r} "
            f"(CAL-EMIT written, DA verdict PENDING)"
            for f in fires
        ],
    )


# ---------------------------------------------------------------------------
# B5: C2 boot validation (WARN, path β+)
#
# Per ADR[2]/IC[3]/IC[8]:
#   - Reads `## agent-assignments`; falls back to `## sub-task-decomposition`
#   - Format: `SQ[N]: owner=AGENT |cluster=FILE,FILE2,...`
#   - Edge cases: BOM-strip, empty-section→WARN-not-crash, fenced-code
#     exclusion BEFORE section-header search
#   - Emits explicit zero-parse WARN on schema gap (NOT silent empty)
# ---------------------------------------------------------------------------

_B5_SECTION_HEADER_RE = re.compile(
    r"^## (agent-assignments|sub-task-decomposition)\s*$",
    re.MULTILINE,
)
_B5_ASSIGNMENT_LINE_RE = re.compile(
    r"^\s*SQ\[([\w-]+)\]\s*:\s*owner\s*=\s*(\S[^|]*?)\s*\|\s*cluster\s*=\s*(.+?)\s*$",
    re.MULTILINE,
)


def _b5_extract_section(content: str) -> tuple[str, str | None, str]:
    """Extract the agent-assignments section body. Returns
    (body, source_section, parse_state).

    parse_state ∈ {'agent-assignments', 'sub-task-decomposition-fallback',
                   'no-section', 'empty-section'}
    """
    stripped = _strip_fenced_blocks(_strip_bom(content))
    headers = list(_B5_SECTION_HEADER_RE.finditer(stripped))
    if not headers:
        return "", None, "no-section"

    # Prefer agent-assignments over sub-task-decomposition
    target_match = None
    for m in headers:
        if m.group(1) == "agent-assignments":
            target_match = m
            break
    if target_match is None:
        target_match = headers[0]  # fallback section

    src = target_match.group(1)
    parse_state = (
        "agent-assignments" if src == "agent-assignments"
        else "sub-task-decomposition-fallback"
    )

    start = target_match.end()
    next_section = re.search(r"^##\s\S", stripped[start:], re.MULTILINE)
    end = start + next_section.start() if next_section else len(stripped)
    body = stripped[start:end].strip()
    if not body:
        parse_state = "empty-section"
    return body, src, parse_state


def check_b5_c2_boot(content: str) -> ChainItem:
    """B5: C2 boot validation — WARN-first when `## agent-assignments`
    section is missing or unparsable.

    BUILD-only. Fires only when `## status: building` or BUILD mode signals
    are present. Per ADR[2]/IC[3]: explicit zero-parse WARN on schema gap.
    """
    review_id = _review_id_from_content(content)
    fires: list[dict[str, str]] = []
    cal_records: list[str] = []

    body, src, parse_state = _b5_extract_section(content)

    assignments: list[dict[str, str]] = []
    if body and parse_state != "empty-section":
        for m in _B5_ASSIGNMENT_LINE_RE.finditer(body):
            sq_id, owner, cluster = m.group(1), m.group(2).strip(), m.group(3).strip()
            files = [f.strip() for f in cluster.split(",") if f.strip()]
            assignments.append({
                "sq_id": sq_id,
                "owner": owner,
                "files": files,
            })

    fire_reason: str | None = None
    if parse_state == "no-section":
        fire_reason = "no-agent-assignments-section"
    elif parse_state == "empty-section":
        fire_reason = "agent-assignments-section-empty"
    elif parse_state == "sub-task-decomposition-fallback":
        # Fallback used — emit WARN to surface schema gap
        fire_reason = "fallback-to-sub-task-decomposition"
    elif not assignments:
        fire_reason = "agent-assignments-zero-parse"

    if fire_reason:
        record = _emit_cal_record(
            gate_id="B5",
            review_id=review_id,
            finding_ref=f"SECTION[{src or 'missing'}]",
            fire_reason=fire_reason,
            agent="lead",
            excerpt=f"parse_state={parse_state}, parsed={len(assignments)}",
        )
        fires.append({
            "trigger": fire_reason,
            "parse_state": parse_state,
            "parsed_count": len(assignments),
        })
        cal_records.append(record)

    return ChainItem(
        item_id="B5",
        name="C2 boot validation (WARN, path β+)",
        passed=True,  # WARN-first
        category="agent-work",
        details={
            "fires": fires,
            "fire_count": len(fires),
            "cal_emit_records": cal_records,
            "path": "β+ WARN-first",
            "review_id": review_id,
            "section_used": src,
            "parse_state": parse_state,
            "assignments_parsed": assignments,
        },
        issues=[
            f"B5 WARN: {f['trigger']} (parse_state={f['parse_state']}, "
            f"parsed_count={f['parsed_count']}) — CAL-EMIT written, "
            f"DA verdict PENDING"
            for f in fires
        ],
    )


# ---------------------------------------------------------------------------
# B6: C2 exit-gate diff (WARN, path β+)
#
# Per ADR[4]/IC[4]: 3-pass CHECKPOINT parser
#   1. keyword=value primary: `CHECKPOINT[agent]: files-created=A,B |functions-done=foo,bar |...`
#   2. prose fallback: `CHECKPOINT[agent]: files-created: ... |functions-done: ...`
#   3. parse-fail: line matches `CHECKPOINT[...]:` but neither pass extracts fields
#
# Extends gc.check_checkpoint by requiring per-field structure, not just
# tag presence. WARN-first per ADR[8].
# ---------------------------------------------------------------------------

_B6_CHECKPOINT_LINE_RE = re.compile(
    r"^\s*CHECKPOINT\[([\w-]+)\]\s*:\s*(.+?)\s*$",
    re.MULTILINE,
)
_B6_KEYVAL_FIELD_RE = re.compile(
    r"\b([a-z][\w-]*)\s*=\s*([^|]+?)(?=\s*\||\s*$)",
    re.IGNORECASE,
)
_B6_PROSE_FIELD_RE = re.compile(
    r"\b([a-z][\w-]*)\s*:\s*([^|]+?)(?=\s*\||\s*$)",
    re.IGNORECASE,
)


def _b6_parse_checkpoint(line_body: str) -> tuple[dict[str, str], str]:
    """3-pass CHECKPOINT body parser. Returns (fields, parse_mode).

    parse_mode ∈ {'keyword=value', 'prose-fallback', 'parse-fail'}.
    """
    # Pass 1: keyword=value
    kv = {m.group(1).lower(): m.group(2).strip()
          for m in _B6_KEYVAL_FIELD_RE.finditer(line_body)}
    if kv:
        return kv, "keyword=value"
    # Pass 2: prose fallback (key: value)
    prose = {m.group(1).lower(): m.group(2).strip()
             for m in _B6_PROSE_FIELD_RE.finditer(line_body)}
    if prose:
        return prose, "prose-fallback"
    # Pass 3: parse-fail
    return {}, "parse-fail"


def check_b6_c2_exit_gate(content: str) -> ChainItem:
    """B6: C2 exit-gate diff — WARN-first when CHECKPOINT parses fail or
    declared files diverge from agent-assignments.

    BUILD-only. Extends gc.check_checkpoint with structured-field validation.
    """
    review_id = _review_id_from_content(content)
    fires: list[dict[str, str]] = []
    cal_records: list[str] = []

    stripped = _strip_fenced_blocks(_strip_bom(content))
    checkpoints = list(_B6_CHECKPOINT_LINE_RE.finditer(stripped))

    # Pull agent-assignments for cross-check
    body, _src, _ps = _b5_extract_section(content)
    expected_files: dict[str, set[str]] = {}
    if body:
        for m in _B5_ASSIGNMENT_LINE_RE.finditer(body):
            owner = m.group(2).strip()
            files = {f.strip() for f in m.group(3).split(",") if f.strip()}
            expected_files.setdefault(owner, set()).update(files)

    parsed: list[dict[str, Any]] = []
    for m in checkpoints:
        agent = m.group(1).strip().lower()
        line_body = m.group(2).strip()
        fields, parse_mode = _b6_parse_checkpoint(line_body)
        entry = {
            "agent": agent,
            "parse_mode": parse_mode,
            "fields": fields,
        }
        parsed.append(entry)

        if parse_mode == "parse-fail":
            record = _emit_cal_record(
                gate_id="B6",
                review_id=review_id,
                finding_ref=f"CHECKPOINT[{agent}]",
                fire_reason="checkpoint-parse-fail",
                agent=agent,
                excerpt=line_body[:50],
            )
            fires.append({
                "agent": agent,
                "trigger": "checkpoint-parse-fail",
                "parse_mode": parse_mode,
            })
            cal_records.append(record)
            continue

        # Diff declared files against agent-assignments
        declared = fields.get("files-created") or fields.get("files") or ""
        declared_files = {f.strip() for f in re.split(r"[,;]", declared) if f.strip()}
        # Strip CHECKPOINT format noise like leading paths
        expected = expected_files.get(agent, set())
        # Only diff when both sides have content
        if declared_files and expected:
            unexpected = {
                f for f in declared_files
                if not any(f.endswith(e) or e.endswith(f) for e in expected)
            }
            if unexpected:
                record = _emit_cal_record(
                    gate_id="B6",
                    review_id=review_id,
                    finding_ref=f"CHECKPOINT[{agent}]",
                    fire_reason="files-diff-from-assignments",
                    agent=agent,
                    excerpt=f"unexpected={sorted(unexpected)[:3]}",
                )
                fires.append({
                    "agent": agent,
                    "trigger": "files-diff-from-assignments",
                    "parse_mode": parse_mode,
                    "unexpected": sorted(unexpected),
                })
                cal_records.append(record)

    return ChainItem(
        item_id="B6",
        name="C2 exit-gate diff (WARN, path β+)",
        passed=True,  # WARN-first
        category="agent-work",
        details={
            "fires": fires,
            "fire_count": len(fires),
            "cal_emit_records": cal_records,
            "path": "β+ WARN-first",
            "review_id": review_id,
            "checkpoints_parsed": parsed,
            "checkpoint_count": len(parsed),
        },
        issues=[
            f"B6 WARN: {f['trigger']} for CHECKPOINT[{f['agent']}] "
            f"(parse_mode={f['parse_mode']}) — CAL-EMIT written, "
            f"DA verdict PENDING"
            for f in fires
        ],
    )


# ---------------------------------------------------------------------------
# A25: Template-drift detection (WARN, path β+)
#
# Per ADR[5]/IC[5]: SHA256 hash of canonical template content (LF-normalized,
# BOM-stripped, lines rstripped) compared against baseline. Drift → WARN.
# Recovery: re-run sync-templates.sh and commit sidecar baseline file.
# ---------------------------------------------------------------------------

_A25_TEMPLATES_DIR = sp.TEMPLATES_DIR
_A25_BASELINE_FILE = _A25_TEMPLATES_DIR / ".templates-hash-baseline.json"


def _a25_normalize(content: str) -> str:
    """Normalize for hash-identity (per IC[5]/PM[4]):
      - LF line endings (replace CRLF)
      - strip BOM
      - rstrip each line (trailing whitespace)
    """
    text = _strip_bom(content).replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n"))


def _a25_hash(text: str) -> str:
    return hashlib.sha256(_a25_normalize(text).encode("utf-8")).hexdigest()


def check_a25_template_drift(content: str) -> ChainItem:
    """A25: Template-drift — WARN-first when canonical template hash drifts
    from baseline.

    Reads baseline from shared/templates/.templates-hash-baseline.json
    (sidecar). Each template file's current hash is compared to baseline.
    Missing baseline → no fire (first-time setup is benign). Drift → WARN
    with recovery instruction.
    """
    review_id = _review_id_from_content(content)
    fires: list[dict[str, str]] = []
    cal_records: list[str] = []
    baseline: dict[str, str] = {}

    if _A25_BASELINE_FILE.exists():
        try:
            baseline = json.loads(_A25_BASELINE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            baseline = {}

    drifted: list[dict[str, str]] = []
    checked: list[str] = []
    if _A25_TEMPLATES_DIR.is_dir() and baseline:
        for fname, expected_hash in baseline.items():
            tpath = _A25_TEMPLATES_DIR / fname
            if not tpath.is_file():
                drifted.append({
                    "template": fname,
                    "reason": "template-file-missing",
                    "expected_hash": expected_hash,
                })
                continue
            try:
                current = _a25_hash(tpath.read_text(encoding="utf-8"))
            except OSError as e:
                drifted.append({
                    "template": fname,
                    "reason": f"read-error:{e}",
                    "expected_hash": expected_hash,
                })
                continue
            checked.append(fname)
            if current != expected_hash:
                drifted.append({
                    "template": fname,
                    "reason": "hash-mismatch",
                    "expected_hash": expected_hash,
                    "current_hash": current,
                })

    for d in drifted:
        record = _emit_cal_record(
            gate_id="A25",
            review_id=review_id,
            finding_ref=f"TEMPLATE[{d['template']}]",
            fire_reason=d["reason"],
            agent="lead",
            excerpt=f"expected={d['expected_hash'][:12]}",
        )
        fires.append({
            "template": d["template"],
            "trigger": d["reason"],
        })
        cal_records.append(record)

    return ChainItem(
        item_id="A25",
        name="Template-drift (WARN, path β+)",
        passed=True,  # WARN-first
        category="agent-work",
        details={
            "fires": fires,
            "fire_count": len(fires),
            "cal_emit_records": cal_records,
            "path": "β+ WARN-first",
            "review_id": review_id,
            "templates_dir": str(_A25_TEMPLATES_DIR),
            "baseline_present": bool(baseline),
            "templates_checked": checked,
            "drift_records": drifted,
        },
        issues=[
            f"A25 WARN: {f['trigger']} on {f['template']} — "
            f"recovery: re-run sync-templates.sh + commit baseline. "
            f"CAL-EMIT written, DA verdict PENDING"
            for f in fires
        ],
    )


# ---------------------------------------------------------------------------
# Chain evaluation: run all items
# ---------------------------------------------------------------------------

ANALYZE_CHAIN = [
    check_a1, check_a2, check_a3, check_a4, check_a5,
    check_a6, check_a7, check_a8, check_a9, check_a10,
    check_a15,  # XVERIFY (conditional)
    # Peer verification
    check_a16, check_a17, check_a18,
    # Path β+ calibration gates (WARN-first, CAL-EMIT)
    check_a20_precision_gate,
    check_a22_governance_artifact,
    check_a23_severity_provenance,
    check_a24_sigma_verify_coverage,
    check_a25_template_drift,      # SQ[6] WARN-first template hash-identity
    check_a26_plan_completeness,  # SQ[1] WARN-first plan-file presence + completeness
    # Chain closure
    check_a11, check_a12, check_a13, check_a14,
]

BUILD_EXTRAS = [check_b1, check_b2, check_b3, check_b4, check_b5_c2_boot, check_b6_c2_exit_gate]


def evaluate_chain(workspace_path: str | Path | None = None,
                   mode: str | None = None) -> ChainResult:
    """Evaluate the full atomic chain against workspace content.

    Args:
        workspace_path: Path to workspace file (default: shared/workspace.md)
        mode: ANALYZE or BUILD (auto-detected from workspace if None)

    Returns:
        ChainResult with per-item pass/fail
    """
    content = gc.read_workspace(workspace_path)
    if mode is None:
        mode = gc.get_mode(content)

    checks = list(ANALYZE_CHAIN)
    if mode == "BUILD":
        checks.extend(BUILD_EXTRAS)

    items = [fn(content) for fn in checks]
    complete = all(item.passed for item in items)

    return ChainResult(mode=mode, complete=complete, items=items)


def evaluate_single(item_id: str, workspace_path: str | Path | None = None) -> ChainItem:
    """Evaluate a single checklist item by ID."""
    content = gc.read_workspace(workspace_path)

    # Map item IDs to functions
    all_checks = {
        "A1": check_a1, "A2": check_a2, "A3": check_a3, "A4": check_a4,
        "A5": check_a5, "A6": check_a6, "A7": check_a7, "A8": check_a8,
        "A9": check_a9, "A10": check_a10, "A11": check_a11, "A12": check_a12,
        "A13": check_a13, "A14": check_a14, "A15": check_a15,
        "A16": check_a16, "A17": check_a17, "A18": check_a18,
        # Path β+ calibration gates (WARN-first, CAL-EMIT)
        "A20": check_a20_precision_gate,
        "A22": check_a22_governance_artifact,
        "A23": check_a23_severity_provenance,
        "A24": check_a24_sigma_verify_coverage,
        "A25": check_a25_template_drift,
        "A26": check_a26_plan_completeness,
        "B1": check_b1, "B2": check_b2, "B3": check_b3, "B4": check_b4,
        "B5": check_b5_c2_boot,
        "B6": check_b6_c2_exit_gate,
    }

    fn = all_checks.get(item_id.upper())
    if fn is None:
        return ChainItem(
            item_id=item_id, name="Unknown", passed=False,
            category="error", issues=[f"Unknown item ID: {item_id}"],
        )
    return fn(content)


# ---------------------------------------------------------------------------
# Rejection monotonicity — prevent brute-force retries
# ---------------------------------------------------------------------------

def _content_hash(content: str) -> str:
    """Hash workspace content for change detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _load_state() -> dict:
    """Load chain status tracking state."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_state(state: dict) -> None:
    """Save chain status tracking state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def check_monotonicity(result: ChainResult, workspace_path: str | Path | None = None) -> ChainResult:
    """Apply rejection monotonicity: items that previously failed require
    material workspace changes before re-evaluation.

    Modifies result in-place if a previously-failed item hasn't changed.
    """
    content = gc.read_workspace(workspace_path)
    current_hash = _content_hash(content)
    state = _load_state()

    prev_hash = state.get("last_content_hash", "")
    prev_failures = state.get("failed_items", {})

    if current_hash == prev_hash:
        # No workspace changes — all previously failed items stay failed
        for item in result.items:
            if item.item_id in prev_failures and item.passed:
                item.passed = False
                item.issues.append(
                    f"Monotonicity: previously failed, workspace unchanged since last evaluation"
                )

    # Update state with current failures
    state["last_content_hash"] = current_hash
    state["last_evaluation"] = result.timestamp
    state["last_complete"] = result.complete
    state["failed_items"] = {
        item.item_id: item.issues[0] if item.issues else "failed"
        for item in result.items if not item.passed
    }
    _save_state(state)

    return result


# ---------------------------------------------------------------------------
# Workspace writer — A19: Chain evaluation output as artifact
# ---------------------------------------------------------------------------

def write_evaluation_to_workspace(result: ChainResult,
                                   workspace_path: str | Path | None = None) -> None:
    """Write ## Chain Evaluation section to workspace.

    This is checklist item A19 — the evaluator's output IS part of the chain.
    """
    p = Path(workspace_path) if workspace_path else DEFAULT_WORKSPACE
    if not p.exists():
        return  # No workspace to write to — not a sigma session

    content = p.read_text(encoding="utf-8")

    # Remove existing ## Chain Evaluation section if present
    content = re.sub(
        r"^## Chain Evaluation\n.*?(?=^## |\Z)",
        "",
        content,
        flags=re.MULTILINE | re.DOTALL,
    )

    # Append new evaluation
    summary = result.summary_text()
    content = content.rstrip() + "\n\n" + summary + "\n"

    p.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Hook dispatch (Stop hook entry point)
# ---------------------------------------------------------------------------

def enforce_stop(data: dict) -> dict:
    """Stop hook handler: evaluate chain, write to workspace, return systemMessage.

    Non-looping design: returns informational messages only, never actionable
    demands that would cause Claude to retry and trigger the Stop hook again.
    Idempotent: skips re-evaluation if workspace hasn't changed since last eval.
    """
    # Only evaluate if a workspace exists (we're in a sigma session)
    if not DEFAULT_WORKSPACE.exists():
        return {}

    try:
        content = gc.read_workspace()
    except FileNotFoundError:
        return {}

    # Check if this is a sigma-review or sigma-build session
    # (workspace must have ## task or ## mode section)
    if "## task" not in content.lower() and "## mode" not in content.lower():
        return {}

    # Idempotency: skip if workspace hasn't changed since last evaluation
    current_hash = _content_hash(content)
    state = _load_state()
    if state.get("last_content_hash") == current_hash and "## Chain Evaluation" in content:
        # Already evaluated this exact workspace content — no-op
        return {}

    result = evaluate_chain()
    result = check_monotonicity(result)
    write_evaluation_to_workspace(result)

    # Update state hash to reflect post-write workspace content.
    # Without this, the idempotency guard fails on the next call because
    # write_evaluation_to_workspace changed the workspace content.
    try:
        post_write_content = gc.read_workspace()
        post_write_hash = _content_hash(post_write_content)
        state = _load_state()
        state["last_content_hash"] = post_write_hash
        _save_state(state)
    except (FileNotFoundError, OSError):
        pass

    # Informational messages only — do NOT phrase as demands or instructions.
    # The lead runs chain-evaluator.py evaluate explicitly before declaring done.
    if result.complete:
        return {"systemMessage": f"[chain-eval] {result.passed_count}/{len(result.items)} items passed. Chain complete."}

    return {"systemMessage": (
        f"[chain-eval] {result.passed_count}/{len(result.items)} items passed. "
        f"Results written to workspace ## Chain Evaluation."
    )}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    """CLI and hook dispatch."""
    # Check CLI args FIRST — they take priority over stdin detection.
    # When run via Claude Code's Bash tool, stdin is piped (not a tty)
    # even for CLI invocations, so stdin-first detection misroutes CLI
    # calls to the hook path where they silently exit 0.
    args = sys.argv[1:]

    if args:
        # Explicit CLI invocation — skip stdin detection entirely
        pass
    elif not sys.stdin.isatty():
        # No CLI args + stdin is piped → likely a hook invocation
        try:
            data = json.loads(sys.stdin.read())
        except (json.JSONDecodeError, EOFError):
            data = {}

        event = data.get("hook_event_name", "")
        if event == "Stop":
            output = enforce_stop(data)
            if output:
                print(json.dumps(output))
            sys.exit(0)
        else:
            # Not a Stop event — chain-evaluator only runs on Stop
            sys.exit(0)
    else:
        # No args, stdin is a tty — show usage
        print("Usage: chain-evaluator.py [evaluate|status|item <ID>]", file=sys.stderr)
        sys.exit(1)

    if not args:
        sys.exit(0)

    cmd = args[0].lower()
    # evaluate/status accept workspace path as args[1]; item uses args[1] as the item ID
    # and args[2] (if present) as the workspace path.
    if cmd in ("evaluate", "status"):
        workspace = args[1] if len(args) > 1 else None
    elif cmd == "item":
        workspace = args[2] if len(args) > 2 else None
    else:
        workspace = None

    if cmd == "evaluate":
        result = evaluate_chain(workspace)
        result = check_monotonicity(result, workspace)
        print(json.dumps(result.to_dict(), indent=2))
    elif cmd == "status":
        # Quick mechanical-only check — skip analytical checks
        result = evaluate_chain(workspace)
        summary = {
            "complete": result.complete,
            "passed": result.passed_count,
            "failed": result.failed_count,
            "total": len(result.items),
            "failed_items": [
                {"id": i.item_id, "name": i.name}
                for i in result.items if not i.passed
            ],
        }
        print(json.dumps(summary, indent=2))
    elif cmd == "item":
        if len(args) < 2:
            print("Usage: chain-evaluator.py item <ID> [workspace]", file=sys.stderr)
            sys.exit(1)
        item = evaluate_single(args[1], workspace)
        print(json.dumps(item.to_dict(), indent=2))
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
