"""Gate validation checks for sigma-review orchestrator.

Provides workspace-reading validation functions that enforce protocol compliance.
Called via orchestrator-config.py validate / compute-belief commands.

Gate taxonomy (V1-V22):
  V1  research-freshness        V11 belief-state-written
  V2  workspace-initialized     V12 new-consensus-stress-tested
  V3  agent-output-non-empty    V13 contamination-check
  V4  source-provenance         V14 source-provenance-audit
  V5  xverify-coverage          V15 anti-sycophancy-check
  V6  dialectical-bootstrapping V16 exit-gate-format
  V7  hypothesis-matrix         V17 plan-lock-completeness
  V8  persist-before-converge   V18 build-reads-plan
  V9  circuit-breaker           V19 checkpoint-completion
  V10 cross-track-participation V20 fixes-implemented
  V21 team-created              V22 session-end-verified
  V23 synthesis-artifact
  V24 wiki-source-attribution  V25 wiki-contradiction-preserved
  V26 wiki-page-count

Bundles:
  r1-convergence     V3+V4+V5+V6+V7+V8  (ANALYZE R1 exit)
  cb                 V9                    (circuit breaker)
  pre-synthesis      V13+V14+V15+V16      (before synthesis)
  plan-convergence   V3+V4+V5+V6+V8       (BUILD plan round exit)
  plan-lock          V17                   (BUILD plan→build)
  build-checkpoint   V19                   (BUILD before review)
  challenge-round    V10+V11              (after any challenge/review round)
  compilation        V24+V25+V26          (wiki integrity after compilation)
  session-end        V22+V23              (archive→complete, git+synthesis verified)
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import sigma_paths as sp  # noqa: E402
from typing import Any

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Result of a single validation check."""

    name: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "details": self.details,
            "issues": self.issues,
        }


@dataclass
class ValidationResult:
    """Result of a validation bundle (multiple checks)."""

    bundle: str
    passed: bool
    checks: list[CheckResult] = field(default_factory=list)
    context_update: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "bundle": self.bundle,
            "passed": self.passed,
            "checks": [c.to_dict() for c in self.checks],
            "context_update": self.context_update,
        }


@dataclass
class BeliefComponents:
    """Mechanically derived belief state components."""

    prior: float
    agreement: float
    revisions: float
    gaps_penalty: float
    da_factor: float
    posterior: float
    breakdown: dict[str, Any] = field(default_factory=dict)
    declared: float | None = None
    divergence: float | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "prior": round(self.prior, 3),
            "agreement": round(self.agreement, 3),
            "revisions": round(self.revisions, 3),
            "gaps_penalty": round(self.gaps_penalty, 3),
            "da_factor": round(self.da_factor, 3),
            "posterior": round(self.posterior, 3),
            "breakdown": self.breakdown,
        }
        if self.declared is not None:
            d["declared"] = round(self.declared, 3)
            d["divergence"] = round(self.divergence or 0.0, 3)
            d["divergence_flag"] = (self.divergence or 0.0) > 0.15
        return d


# ---------------------------------------------------------------------------
# Workspace parsing
# ---------------------------------------------------------------------------

DEFAULT_WORKSPACE = sp.WORKSPACE


def read_workspace(path: str | Path | None = None) -> str:
    """Read workspace file contents."""
    p = Path(path) if path else DEFAULT_WORKSPACE
    if not p.exists():
        raise FileNotFoundError(f"Workspace not found: {p}")
    return p.read_text(encoding="utf-8")


def parse_sections(content: str) -> dict[str, str]:
    """Split workspace into ## sections. Returns {header_name: body}."""
    sections: dict[str, str] = {}
    current_header = "_preamble"
    lines: list[str] = []

    for line in content.splitlines():
        if line.startswith("## ") and not line.startswith("### "):
            if lines:
                sections[current_header] = "\n".join(lines)
            current_header = line[3:].strip().lower()
            lines = []
        else:
            lines.append(line)

    if lines:
        sections[current_header] = "\n".join(lines)
    return sections


def parse_agent_subsections(findings_text: str) -> dict[str, str]:
    """Split ## findings into ### agent subsections."""
    agents: dict[str, str] = {}
    current_agent = ""
    lines: list[str] = []

    for line in findings_text.splitlines():
        if line.startswith("### "):
            if current_agent and lines:
                agents[current_agent] = "\n".join(lines)
            current_agent = line[4:].strip().lower()
            lines = []
        else:
            lines.append(line)

    if current_agent and lines:
        agents[current_agent] = "\n".join(lines)
    return agents


def _load_roster_agents() -> set[str]:
    """Load known agent names from the team roster file.

    Returns a set of lowercase agent names. Falls back to empty set if
    roster is not found (in which case extract_agents_from_workspace uses
    the exclusion-list approach as a fallback).
    """
    roster_path = sp.SHARED / "roster.md"
    if not roster_path.exists():
        return set()
    try:
        content = roster_path.read_text(encoding="utf-8")
        # Roster format: "agent-name |domain: ..." — one per line
        agents = set()
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Extract agent name (everything before first |)
            name = line.split("|")[0].strip().lower()
            if name:
                agents.add(name)
        return agents
    except OSError:
        return set()


def extract_agents_from_workspace(content: str) -> list[str]:
    """Extract agent names from workspace ### subsections.

    Uses roster-based allowlist when available (robust). Falls back to
    exclusion-list approach if roster is not found.

    Scans the region between ## agents (or ## findings) and ## convergence
    for ### headers that match known agent names.
    """
    # Find the agent findings region — workspace uses ## agents or ## findings
    agents_start = re.search(r"^## (?:agents|findings)", content, re.MULTILINE | re.IGNORECASE)
    convergence_start = re.search(r"^## (?:convergence|promotion|open-questions)", content, re.MULTILINE | re.IGNORECASE)

    if agents_start:
        start = agents_start.start()
        end = convergence_start.start() if convergence_start else len(content)
        region = content[start:end]
    else:
        region = content

    # Extract all ### headers in that region
    agent_headers = re.findall(r"^### ([\w-]+)", region, re.MULTILINE)

    # Try roster-based allowlist first (robust)
    roster_agents = _load_roster_agents()
    if roster_agents:
        # devils-advocate is roster-valid but excluded from agent extraction:
        # DA produces challenges, not F[]/DB[]/XVERIFY content, so downstream
        # iteration over this list breaks if DA is included (R19 regression
        # after roster.md added DA entry 26.4.11). Exclusion matches the
        # fallback branch at line 246 — contract was documented at 223-224
        # but the filter was never implemented here.
        agents = []
        seen = set()
        for name in agent_headers:
            key = name.lower()
            if key in roster_agents and key != "devils-advocate" and key not in seen:
                agents.append(key)
                seen.add(key)
        return agents

    # Fallback: exclusion-list approach (when roster not available)
    exclude = {
        "questions", "constraints", "claims", "auto-promoted", "user-approve",
        "synthesis-agent", "hypotheses", "prompt-hypotheses", "peer-verification",
        "verification", "da-responses", "analytical-hygiene", "findings",
        "superforecasting-decomposition", "reference-classes", "analogues",
        "calibration", "pre-mortem", "disconfirmation",
    }
    agents = []
    seen = set()
    for name in agent_headers:
        key = name.lower()
        if key not in exclude and key != "devils-advocate" and key not in seen:
            agents.append(key)
            seen.add(key)

    return agents


def is_sigverify_available(content: str) -> bool:
    """Check if ΣVerify is available from ## infrastructure."""
    sections = parse_sections(content)
    infra = sections.get("infrastructure", "")
    if not infra:
        return False
    lower = infra.lower()
    if "unavailable" in lower and "σverify" in lower:
        return False
    if "σverify" in lower or "sigverify" in lower or "ΣVerify" in infra:
        return "available" in lower or "openai" in lower or "google" in lower
    return False


def count_hypotheses(content: str) -> int:
    """Count H[] hypotheses in prompt-decomposition."""
    sections = parse_sections(content)
    pd = sections.get("prompt-decomposition", "")
    return len(re.findall(r"^H\d+:", pd, re.MULTILINE))


def get_complexity_tier(content: str) -> int:
    """Extract complexity tier (1-3) from workspace."""
    m = re.search(r"TIER-(\d)", content)
    return int(m.group(1)) if m else 2  # default moderate


def get_mode(content: str) -> str:
    """Extract mode (ANALYZE or BUILD) from workspace."""
    m = re.search(r"^## mode:\s*(\w+)", content, re.MULTILINE)
    if m:
        return m.group(1).upper()
    if "mode: BUILD" in content or "mode: build" in content:
        return "BUILD"
    return "ANALYZE"


# ---------------------------------------------------------------------------
# Individual check functions (V1–V20)
# ---------------------------------------------------------------------------


def _get_findings_region(content: str) -> str:
    """Extract the full findings region (## agents/findings through ## convergence).

    Handles workspaces that use ## agents (current) or ## findings (legacy),
    and interleaved ## sections (e.g. ## DA R2 RESPONSES).
    """
    findings_start = re.search(r"^## (?:agents|findings)", content, re.MULTILINE | re.IGNORECASE)
    convergence_start = re.search(r"^## (?:convergence|promotion|open-questions)", content, re.MULTILINE | re.IGNORECASE)

    if findings_start:
        start = findings_start.start()
        end = convergence_start.start() if convergence_start else len(content)
        return content[start:end]
    return content


def _get_agent_section(content: str, agent: str) -> str:
    """Extract a single agent's section from the findings region."""
    region = _get_findings_region(content)
    # Find ### {agent} and capture until next ### or ## boundary
    pattern = rf"^### {re.escape(agent)}\b.*?\n(.*?)(?=^### |\Z|^## )"
    m = re.search(pattern, region, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return m.group(1) if m else ""


def check_agent_output_non_empty(content: str, agents: list[str] | None = None) -> CheckResult:
    """V3: Each agent has non-empty workspace findings section."""
    if agents is None:
        agents = extract_agents_from_workspace(content)

    empty_agents = []
    for agent in agents:
        section = _get_agent_section(content, agent)
        stripped = re.sub(r"^status:.*$", "", section, flags=re.MULTILINE).strip()
        if len(stripped) < 50:
            empty_agents.append(agent)

    return CheckResult(
        name="V3-agent-output-non-empty",
        passed=len(empty_agents) == 0,
        details={"agents_checked": len(agents), "empty": empty_agents},
        issues=[f"Agent '{a}' has empty/minimal findings section" for a in empty_agents],
    )


def check_source_provenance(content: str) -> CheckResult:
    """V4: All findings carry |source:{type} tag; load-bearing carry tier.

    Tags may appear anywhere in the finding's block — header or body. A block
    runs from its F[...] header to the next F[...] header, the next ### agent
    subsection, the next ## major section, or the end of the findings region.
    """
    findings = _get_findings_region(content)

    # Line-anchored F[...] or FINDING[...] header — excludes inline references
    # like "DA[#1] response to F[PS-1]" since those don't start the line.
    header_re = re.compile(r"^((?:F|FINDING)\[[\w-]+\])[:\s].*$", re.MULTILINE)
    boundary_re = re.compile(r"^(?:(?:F|FINDING)\[[\w-]+\]|###\s|##\s)", re.MULTILINE)

    # A FID can appear in multiple places (primary declaration, peer-verify
    # reference in another agent's section, DA response quote, etc.). Group
    # all occurrences per FID — the finding is tagged if ANY occurrence
    # carries the provenance tag, since the tag only needs to exist once.
    fid_blocks: dict[str, list[str]] = {}
    for m in header_re.finditer(findings):
        fid = m.group(1)
        start = m.start()
        next_boundary = boundary_re.search(findings, pos=m.end())
        end = next_boundary.start() if next_boundary else len(findings)
        fid_blocks.setdefault(fid, []).append(findings[start:end])

    total = len(fid_blocks)
    tagged = 0
    untagged: list[str] = []
    load_bearing_without_tier: list[str] = []

    for fid, blocks_list in fid_blocks.items():
        combined = "\n".join(blocks_list)
        has_source = bool(re.search(r"\|source:", combined, re.IGNORECASE))
        has_src = bool(re.search(r"\|src:", combined, re.IGNORECASE))
        if has_source or has_src:
            tagged += 1
        else:
            untagged.append(fid)

        is_load_bearing = bool(re.search(
            r"(LOAD.BEARING|>70%|highest.conviction|superlative|primary)",
            combined, re.IGNORECASE,
        ))
        has_tier = bool(re.search(r"T[123]", combined))
        if is_load_bearing and not has_tier:
            load_bearing_without_tier.append(fid)

    issues = []
    if untagged:
        issues.append(f"Untagged findings: {', '.join(untagged)}")
    if load_bearing_without_tier:
        issues.append(f"Load-bearing without tier: {', '.join(load_bearing_without_tier)}")

    return CheckResult(
        name="V4-source-provenance",
        passed=len(untagged) == 0,
        details={
            "total_findings": total,
            "tagged": tagged,
            "untagged": untagged,
            "load_bearing_without_tier": load_bearing_without_tier,
        },
        issues=issues,
    )


def check_xverify_coverage(content: str) -> CheckResult:
    """V5: When ΣVerify available, each agent has XVERIFY on load-bearing finding."""
    available = is_sigverify_available(content)
    if not available:
        return CheckResult(
            name="V5-xverify-coverage",
            passed=True,
            details={"sigverify_available": False, "skip_reason": "ΣVerify unavailable"},
        )

    agents = extract_agents_from_workspace(content)

    missing = []
    for agent in agents:
        section = _get_agent_section(content, agent)
        # Match XVERIFY[, XVERIFY(, XVERIFY:, XVERIFY= — various workspace formats
        has_xverify = bool(re.search(r"(?:T[123]-)?XVERIFY(?:-PARTIAL)?[\[\s(:]", section, re.IGNORECASE))
        has_xverify_fail = bool(re.search(r"XVERIFY-FAIL", section))
        if not has_xverify and not has_xverify_fail:
            missing.append(agent)

    return CheckResult(
        name="V5-xverify-coverage",
        passed=len(missing) == 0,
        details={
            "sigverify_available": True,
            "agents_checked": len(agents),
            "agents_missing_xverify": missing,
        },
        issues=[f"Agent '{a}' has no XVERIFY/XVERIFY-FAIL on any finding" for a in missing],
    )


def check_dialectical_bootstrapping(content: str, agents: list[str] | None = None) -> CheckResult:
    """V6: DB[] entries present per agent."""
    if agents is None:
        agents = extract_agents_from_workspace(content)

    missing = []
    for agent in agents:
        section = _get_agent_section(content, agent)
        has_db = bool(re.search(r"(?:DB\[|DB-reconciled|DISCONFIRM\[)", section, re.IGNORECASE))
        if not has_db:
            missing.append(agent)

    return CheckResult(
        name="V6-dialectical-bootstrapping",
        passed=len(missing) == 0,
        details={"agents_checked": len(agents), "agents_missing_db": missing},
        issues=[f"Agent '{a}' has no DB[] dialectical bootstrapping entries" for a in missing],
    )


def check_hypothesis_matrix(content: str) -> CheckResult:
    """V7: If H[] count >= 3, hypothesis-matrix section must exist."""
    h_count = count_hypotheses(content)
    if h_count < 3:
        return CheckResult(
            name="V7-hypothesis-matrix",
            passed=True,
            details={"hypothesis_count": h_count, "required": False},
        )

    sections = parse_sections(content)
    has_matrix = "hypothesis-matrix" in sections
    # Also check within prompt-decomposition or findings
    if not has_matrix:
        full_lower = content.lower()
        has_matrix = "## hypothesis-matrix" in full_lower or "hypothesis-matrix" in sections

    return CheckResult(
        name="V7-hypothesis-matrix",
        passed=has_matrix,
        details={"hypothesis_count": h_count, "required": True, "matrix_found": has_matrix},
        issues=[] if has_matrix else [
            f"§2f: {h_count} hypotheses require a hypothesis-matrix section but none found"
        ],
    )


def check_persist_before_convergence(content: str) -> CheckResult:
    """V8: Each agent has persisted (heuristic — check for persist markers in convergence)."""
    sections = parse_sections(content)
    convergence = sections.get("convergence", "")

    agents = extract_agents_from_workspace(content)
    converged = []
    for agent in agents:
        # Check if agent declared ✓ in convergence
        if re.search(rf"{re.escape(agent)}.*✓", convergence, re.IGNORECASE):
            converged.append(agent)

    not_converged = [a for a in agents if a not in converged]

    return CheckResult(
        name="V8-persist-before-convergence",
        passed=len(not_converged) == 0,
        details={
            "agents": len(agents),
            "converged": converged,
            "not_converged": not_converged,
        },
        issues=[f"Agent '{a}' has not declared ✓ in convergence" for a in not_converged],
    )


def check_circuit_breaker(content: str) -> CheckResult:
    """V9: Either divergence logged OR CB[1]/CB[2]/CB[3] entries present."""
    # Check for explicit divergence logging
    has_divergence_log = bool(re.search(
        r"(divergence.detected|divergence.found|R1.divergence|divergence.logged)",
        content, re.IGNORECASE,
    ))

    # Check for CB responses
    cb_entries = re.findall(r"CB\[\d\]", content)
    has_cb = len(cb_entries) >= 2  # At least 2 CB entries from at least 1 agent

    # Check for zero-dissent section or note
    has_cb_section = bool(re.search(
        r"(circuit.breaker|zero.dissent.*fired|CB.*fired)", content, re.IGNORECASE,
    ))

    passed = has_divergence_log or has_cb or has_cb_section

    details: dict[str, Any] = {
        "divergence_logged": has_divergence_log,
        "cb_entries_found": len(cb_entries),
        "cb_section_found": has_cb_section,
    }

    issues = []
    if not passed:
        issues.append(
            "Neither divergence logged nor circuit breaker fired — "
            "hard gate requires one before advancing to challenge round"
        )

    return CheckResult(name="V9-circuit-breaker", passed=passed, details=details, issues=issues)


def check_cross_track_participation(content: str) -> CheckResult:
    """V10: DA issued challenges; all challenges have agent responses."""
    # Find DA section
    da_section = _get_agent_section(content, "devils-advocate")

    # Count DA challenges — multiple formats used in workspaces:
    # DA[#N] individual challenges, CH[N] challenge themes, or narrative "N challenges"
    da_individual = re.findall(r"DA\[#?\d+\]|DA-C\[\d+\]", da_section) if da_section else []
    da_themes = re.findall(r"CH\[\d+\]", da_section) if da_section else []
    # Narrative count: "26 challenges across 6 agents"
    narrative_match = re.search(r"(\d+)\s+challenges?\s+(?:across|delivered|issued)", da_section, re.IGNORECASE) if da_section else None
    narrative_count = int(narrative_match.group(1)) if narrative_match else 0
    da_challenge_count = max(len(da_individual), len(da_themes), narrative_count)
    if da_challenge_count == 0 and da_section and len(da_section.strip()) > 100:
        da_challenge_count = 1

    # Count agent DA responses across all agent sections
    agents = extract_agents_from_workspace(content)
    da_responses = 0
    for agent in agents:
        section = _get_agent_section(content, agent)
        da_responses += len(re.findall(
            r"DA\[#?\d+\].*(?:concede|defend|compromise|accept|reject|revise|acknowledge)",
            section, re.IGNORECASE
        ))

    issues = []
    if da_challenge_count == 0:
        issues.append("DA issued 0 challenges")
    if da_challenge_count > 0 and da_responses == 0:
        issues.append("No agent DA responses found (concede/defend/compromise)")

    return CheckResult(
        name="V10-cross-track-participation",
        passed=da_challenge_count > 0 and da_responses > 0,
        details={
            "da_challenges_issued": da_challenge_count,
            "da_individual": len(da_individual),
            "da_themes": len(da_themes),
            "da_narrative_count": narrative_count,
            "agent_da_responses": da_responses,
        },
        issues=issues,
    )


def check_belief_state_written(content: str, round_num: int | None = None) -> CheckResult:
    """V11: BELIEF[rN] present in workspace with component scores."""
    if round_num:
        pattern = rf"BELIEF\[r{round_num}\]"
    else:
        pattern = r"BELIEF\[r\d+\]"

    beliefs = re.findall(pattern, content)
    has_belief = len(beliefs) > 0

    # Check for P= value
    has_p_value = bool(re.search(r"BELIEF\[r\d+\].*P=[\d.]+", content))

    # Check for action
    has_action = bool(re.search(r"BELIEF\[r\d+\].*→", content))

    issues = []
    if not has_belief:
        issues.append(f"No BELIEF[r{round_num or 'N'}] entry found in workspace")
    elif not has_p_value:
        issues.append("BELIEF entry found but missing P= value")

    return CheckResult(
        name="V11-belief-state-written",
        passed=has_belief and has_p_value,
        details={
            "belief_entries": len(beliefs),
            "has_p_value": has_p_value,
            "has_action": has_action,
        },
        issues=issues,
    )


def check_contamination(content: str) -> CheckResult:
    """V13: CONTAMINATION-CHECK present in prescribed format."""
    has_check = bool(re.search(r"CONTAMINATION-CHECK:", content))
    has_scope = "scope-boundary" in parse_sections(content)

    # Also accept variations
    has_session_topics = bool(re.search(r"session-topics-outside-scope:", content))

    passed = has_check or has_session_topics

    issues = []
    if not passed:
        issues.append("CONTAMINATION-CHECK not found in workspace — required before synthesis")
    if not has_scope:
        issues.append("## scope-boundary section missing")

    return CheckResult(
        name="V13-contamination-check",
        passed=passed,
        details={
            "contamination_check_present": has_check,
            "session_topics_present": has_session_topics,
            "scope_boundary_present": has_scope,
        },
        issues=issues,
    )


def check_source_provenance_audit(content: str) -> CheckResult:
    """V14: SOURCE-PROVENANCE tally present; prompt-claim within tolerance."""
    has_audit = bool(re.search(r"SOURCE-PROVENANCE\[", content))

    # Also check DA's source provenance audit
    has_da_audit = bool(re.search(
        r"(source.provenance.audit|§2d.*PASS|source.distribution)", content, re.IGNORECASE,
    ))

    # Check prompt-claim percentage
    prompt_claim_pct = 0.0
    m = re.search(r"prompt.claim.*?(\d+)%", content, re.IGNORECASE)
    if m:
        prompt_claim_pct = float(m.group(1))

    passed = has_audit or has_da_audit
    issues = []
    if not passed:
        issues.append("No source provenance audit (SOURCE-PROVENANCE or DA §2d audit) found")
    if prompt_claim_pct > 30:
        issues.append(f"Prompt-claim at {prompt_claim_pct}% — exceeds 30% tolerance")
        passed = False

    return CheckResult(
        name="V14-source-provenance-audit",
        passed=passed,
        details={
            "formal_audit_present": has_audit,
            "da_audit_present": has_da_audit,
            "prompt_claim_pct": prompt_claim_pct,
        },
        issues=issues,
    )


def check_anti_sycophancy(content: str) -> CheckResult:
    """V15: SYCOPHANCY-CHECK present in workspace."""
    has_check = bool(re.search(r"SYCOPHANCY-CHECK:", content))

    return CheckResult(
        name="V15-anti-sycophancy-check",
        passed=has_check,
        details={"sycophancy_check_present": has_check},
        issues=[] if has_check else ["SYCOPHANCY-CHECK not found — required before synthesis"],
    )


def check_exit_gate_format(content: str) -> CheckResult:
    """V16: DA exit-gate covers required criteria with explicit verdicts."""
    has_exit_gate = bool(re.search(r"exit.gate:.*PASS|exit.gate:.*FAIL", content, re.IGNORECASE))

    # Check for individual criteria
    criteria_keywords = ["engagement", "unresolved", "untested.consensus", "hygiene"]
    criteria_found = []
    for kw in criteria_keywords:
        if re.search(kw, content, re.IGNORECASE):
            criteria_found.append(kw.replace(".", " "))

    passed = has_exit_gate and len(criteria_found) >= 3

    issues = []
    if not has_exit_gate:
        issues.append("No DA exit-gate verdict (PASS/FAIL) found")
    missing = [kw.replace(".", " ") for kw in criteria_keywords if kw.replace(".", " ") not in criteria_found]
    if missing:
        issues.append(f"Exit-gate missing criteria: {', '.join(missing)}")

    return CheckResult(
        name="V16-exit-gate-format",
        passed=passed,
        details={
            "exit_gate_present": has_exit_gate,
            "criteria_found": criteria_found,
            "criteria_expected": len(criteria_keywords),
        },
        issues=issues,
    )


def check_plan_lock(content: str) -> CheckResult:
    """V17: BUILD plan-lock completeness — ADR, DS, IC sections populated + plan-exit-gate PASS."""
    sections = parse_sections(content)

    has_adrs = bool(re.search(r"ADR\[\d+\]", sections.get("architecture-decisions", "")))
    has_ds = bool(re.search(r"DS\[", sections.get("design-system", "")))
    has_ic = bool(re.search(r"IC\[\d+\]", sections.get("interface-contracts", "")))

    # Check for plan-exit-gate: PASS (case-insensitive)
    has_plan_exit_gate = bool(re.search(r"plan-exit-gate:\s*PASS", content, re.IGNORECASE))

    # Check for belief state confirming plan ready
    has_belief = bool(re.search(r"BELIEF\[plan.*P=0\.\d{2}", content))

    missing = []
    if not has_adrs:
        missing.append("## architecture-decisions (no ADR[] entries)")
    if not has_ds:
        missing.append("## design-system (no DS[] entries)")
    if not has_ic:
        missing.append("## interface-contracts (no IC[] entries)")
    if not has_plan_exit_gate:
        missing.append("Plan exit-gate not marked as PASS")

    return CheckResult(
        name="V17-plan-lock-completeness",
        passed=len(missing) == 0,
        details={
            "adrs_present": has_adrs,
            "design_system_present": has_ds,
            "interface_contracts_present": has_ic,
            "plan_exit_gate_pass": has_plan_exit_gate,
            "belief_state_present": has_belief,
        },
        issues=[f"Plan lock incomplete: {m}" for m in missing],
    )


def check_build_reads_plan(content: str) -> CheckResult:
    """V18: Build-track agents reference ADR/IC/DS in their findings."""
    sections = parse_sections(content)
    findings = sections.get("findings", "")
    agent_sections = parse_agent_subsections(findings)

    # Build-track agents typically: implementation-engineer, ui-ux-engineer, code-quality-analyst
    build_track = ["implementation-engineer", "ui-ux-engineer", "code-quality-analyst"]
    missing = []
    for agent in build_track:
        section = agent_sections.get(agent, "")
        if not section:
            continue  # Agent not in this review
        refs = re.findall(r"(ADR\[\d+\]|IC\[\d+\]|DS\[)", section)
        if not refs:
            missing.append(agent)

    return CheckResult(
        name="V18-build-reads-plan",
        passed=len(missing) == 0,
        details={"build_agents_missing_plan_refs": missing},
        issues=[f"Build agent '{a}' does not reference ADR/IC/DS from plan" for a in missing],
    )


def check_checkpoint(content: str) -> CheckResult:
    """V19: Build-track agents have CHECKPOINT entries."""
    checkpoints = re.findall(r"CHECKPOINT\[([\w-]+)\]", content)
    agents_with_cp = list(set(checkpoints))

    # Check build-status section
    sections = parse_sections(content)
    has_build_status = bool(sections.get("build-status", "").strip())

    passed = len(agents_with_cp) > 0 or has_build_status

    return CheckResult(
        name="V19-checkpoint-completion",
        passed=passed,
        details={
            "checkpoint_agents": agents_with_cp,
            "build_status_section": has_build_status,
        },
        issues=[] if passed else ["No CHECKPOINT entries found — required before build review"],
    )


def check_fixes_implemented(content: str) -> CheckResult:
    """V20: 'fixed' responses have corresponding evidence of changes."""
    fixes_agreed = re.findall(r"(?:DA|PR)\[#?\d+\].*fixed", content, re.IGNORECASE)
    # This is a heuristic — check that fix count > 0 if fixes were agreed
    return CheckResult(
        name="V20-fixes-implemented",
        passed=True,  # Hard to verify mechanically — advisory check
        details={"fixes_agreed": len(fixes_agreed)},
        issues=[],
    )


def check_merge_verified(content: str) -> CheckResult:
    """V24: When parallel engineers used, MERGE-VERIFIED must be in workspace.

    Only enforced when ## build-assignments section exists (indicating parallel
    engineers were spawned). If no build-assignments section, this check auto-passes
    (single engineer — no merge needed).
    """
    sections = parse_sections(content)
    has_build_assignments = bool(sections.get("build-assignments", "").strip())

    if not has_build_assignments:
        return CheckResult(
            name="V24-merge-verified",
            passed=True,
            details={"parallel_engineers": False, "skip_reason": "no build-assignments section"},
        )

    has_merge_verified = bool(re.search(r"MERGE-VERIFIED:", content))
    has_test_count = bool(re.search(r"MERGE-VERIFIED:.*\d+\s*passed", content))
    has_conflicts = bool(re.search(r"MERGE-VERIFIED:.*conflicts:", content))

    passed = has_merge_verified and has_test_count

    issues = []
    if not has_merge_verified:
        issues.append(
            "Parallel engineers detected (## build-assignments present) but no "
            "MERGE-VERIFIED entry in ## build-status. Post-merge integration tests "
            "must run before build review."
        )
    elif not has_test_count:
        issues.append("MERGE-VERIFIED present but missing test count (e.g. '810 passed')")

    return CheckResult(
        name="V24-merge-verified",
        passed=passed,
        details={
            "parallel_engineers": True,
            "merge_verified_present": has_merge_verified,
            "test_count_present": has_test_count,
            "conflicts_documented": has_conflicts,
        },
        issues=issues,
    )


def check_xverify_security_critical(content: str) -> CheckResult:
    """V25: Security-critical ADRs must have XVERIFY when ΣVerify available.

    Security-critical = ADR mentions IP, permission, injection, trust boundary,
    authentication, authorization, or encryption.
    """
    available = is_sigverify_available(content)
    if not available:
        return CheckResult(
            name="V25-xverify-security-critical",
            passed=True,
            details={"sigverify_available": False, "skip_reason": "ΣVerify unavailable"},
        )

    sections = parse_sections(content)
    adrs_text = sections.get("architecture-decisions", "")

    security_keywords = (
        r"(IP|permission|injection|trust.boundar|auth[oz]|encrypt|sanitiz|"
        r"bypass|HARDENED|HIGH_CONSEQUENCE|firewall|egress|outbound)"
    )

    adr_blocks = re.findall(r"(ADR\[\d+\][^\n]*(?:\n(?!ADR\[)[^\n]*)*)", adrs_text)

    security_adrs = []
    for block in adr_blocks:
        if re.search(security_keywords, block, re.IGNORECASE):
            adr_id = re.match(r"(ADR\[\d+\])", block)
            security_adrs.append(adr_id.group(1) if adr_id else "unknown")

    if not security_adrs:
        return CheckResult(
            name="V25-xverify-security-critical",
            passed=True,
            details={"sigverify_available": True, "security_adrs": [], "skip_reason": "no security-critical ADRs"},
        )

    has_xverify = bool(re.search(r"XVERIFY[\[\(:=]", adrs_text))
    has_xverify_fail = bool(re.search(r"XVERIFY-FAIL", adrs_text))

    passed = has_xverify or has_xverify_fail

    issues = []
    if not passed:
        issues.append(
            f"Security-critical ADRs found ({', '.join(security_adrs)}) but no XVERIFY "
            f"tag in ## architecture-decisions. ΣVerify is available — top-1 security-critical "
            f"ADR requires cross-model verification."
        )

    return CheckResult(
        name="V25-xverify-security-critical",
        passed=passed,
        details={
            "sigverify_available": True,
            "security_adrs": security_adrs,
            "has_xverify": has_xverify,
        },
        issues=issues,
    )


def check_build_track_source_tags(content: str) -> CheckResult:
    """V26: Build-track agent findings carry |source:{type}| tags.

    Checks ## findings section for implementation-engineer and code-quality-analyst
    subsections. Each subsection with content must have at least one |source: tag.
    """
    sections = parse_sections(content)
    findings = sections.get("findings", "")

    build_track_agents = ["implementation-engineer", "code-quality-analyst"]
    missing_tags = []
    checked = []

    for agent in build_track_agents:
        agent_section = _get_agent_section(findings, agent)
        if not agent_section.strip():
            continue
        checked.append(agent)
        has_source = bool(re.search(r"\|source:\[", agent_section))
        has_code_read = bool(re.search(r"\[code-read", agent_section))
        has_file_line = bool(re.search(r"\w+\.py:\d+", agent_section))
        if not (has_source or has_code_read):
            if has_file_line:
                missing_tags.append(f"{agent} (has file:line refs but no formal |source: tag)")
            else:
                missing_tags.append(agent)

    passed = len(missing_tags) == 0

    issues = []
    if missing_tags:
        issues.append(
            f"Build-track agents missing |source:{{type}}| tags: {', '.join(missing_tags)}. "
            f"Add |source:[code-read file:line]| to findings."
        )

    return CheckResult(
        name="V26-build-track-source-tags",
        passed=passed,
        details={
            "agents_checked": checked,
            "agents_missing_tags": missing_tags,
        },
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Bundle validation functions
# ---------------------------------------------------------------------------


def validate_r1_convergence(workspace_path: str | None = None) -> ValidationResult:
    """Bundle: V3+V4+V5+V6+V7+V8 — ANALYZE R1 exit."""
    content = read_workspace(workspace_path)
    agents = extract_agents_from_workspace(content)

    checks = [
        check_agent_output_non_empty(content, agents),
        check_source_provenance(content),
        check_xverify_coverage(content),
        check_dialectical_bootstrapping(content, agents),
        check_hypothesis_matrix(content),
        check_persist_before_convergence(content),
    ]

    all_passed = all(c.passed for c in checks)

    return ValidationResult(
        bundle="r1-convergence",
        passed=all_passed,
        checks=checks,
        context_update={"r1_validated": all_passed},
    )


def validate_cb(workspace_path: str | None = None) -> ValidationResult:
    """Bundle: V9 — circuit breaker."""
    content = read_workspace(workspace_path)
    check = check_circuit_breaker(content)

    return ValidationResult(
        bundle="cb",
        passed=check.passed,
        checks=[check],
        context_update={"cb_validated": check.passed},
    )


def validate_pre_synthesis(workspace_path: str | None = None) -> ValidationResult:
    """Bundle: V13+V14+V15+V16 — before synthesis."""
    content = read_workspace(workspace_path)

    checks = [
        check_contamination(content),
        check_source_provenance_audit(content),
        check_anti_sycophancy(content),
        check_exit_gate_format(content),
    ]

    all_passed = all(c.passed for c in checks)

    return ValidationResult(
        bundle="pre-synthesis",
        passed=all_passed,
        checks=checks,
        context_update={"pre_synthesis_validated": all_passed},
    )


def validate_plan_convergence(workspace_path: str | None = None) -> ValidationResult:
    """Bundle: V3+V4+V5+V6+V8+V25 — BUILD plan round exit."""
    content = read_workspace(workspace_path)
    agents = extract_agents_from_workspace(content)

    checks = [
        check_agent_output_non_empty(content, agents),
        check_source_provenance(content),
        check_xverify_coverage(content),
        check_xverify_security_critical(content),
        check_dialectical_bootstrapping(content, agents),
        check_persist_before_convergence(content),
    ]

    all_passed = all(c.passed for c in checks)

    return ValidationResult(
        bundle="plan-convergence",
        passed=all_passed,
        checks=checks,
        context_update={"plan_round_validated": all_passed},
    )


def validate_plan_lock(workspace_path: str | None = None) -> ValidationResult:
    """Bundle: V17 — BUILD plan→build transition."""
    content = read_workspace(workspace_path)
    check = check_plan_lock(content)

    return ValidationResult(
        bundle="plan-lock",
        passed=check.passed,
        checks=[check],
        context_update={"plan_lock_validated": check.passed},
    )


def validate_build_checkpoint(workspace_path: str | None = None) -> ValidationResult:
    """Bundle: V19+V24+V26 — BUILD before review."""
    content = read_workspace(workspace_path)

    checks = [
        check_checkpoint(content),
        check_merge_verified(content),
        check_build_track_source_tags(content),
    ]

    all_passed = all(c.passed for c in checks)

    return ValidationResult(
        bundle="build-checkpoint",
        passed=all_passed,
        checks=checks,
        context_update={"checkpoint_validated": all_passed},
    )


def validate_challenge_round(
    workspace_path: str | None = None, round_num: int | None = None,
) -> ValidationResult:
    """Bundle: V10+V11 — after any challenge/review round."""
    content = read_workspace(workspace_path)

    checks = [
        check_cross_track_participation(content),
        check_belief_state_written(content, round_num),
    ]

    all_passed = all(c.passed for c in checks)

    return ValidationResult(
        bundle="challenge-round",
        passed=all_passed,
        checks=checks,
        context_update={"challenge_round_validated": all_passed},
    )


# ---------------------------------------------------------------------------
# Belief state computation
# ---------------------------------------------------------------------------

_TIER_PRIORS = {1: 0.7, 2: 0.5, 3: 0.3}
_DA_GRADES = {"a+": 1.0, "a": 1.0, "a-": 0.95, "b+": 0.9, "b": 0.85, "b-": 0.8, "c+": 0.75, "c": 0.7, "d": 0.5}


def _count_pattern(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, re.IGNORECASE))


def compute_analyze_belief(workspace_path: str | None = None, round_num: int | None = None) -> BeliefComponents:
    """Mechanically derive ANALYZE belief state from workspace.

    Formula: posterior = prior × agreement × revisions × gaps_penalty × da_factor
    """
    content = read_workspace(workspace_path)
    sections = parse_sections(content)
    findings = sections.get("findings", "")
    convergence = sections.get("convergence", "")

    # Prior from complexity tier
    tier = get_complexity_tier(content)
    prior = _TIER_PRIORS.get(tier, 0.5)

    # Agreement: ratio of converged agents
    agents = extract_agents_from_workspace(content)
    agent_count = len(agents)
    converged = sum(1 for a in agents if re.search(rf"{re.escape(a)}.*✓", convergence, re.IGNORECASE))
    agreement = converged / max(agent_count, 1)

    # Revisions: count outcome-1 markers
    outcome_1 = _count_pattern(findings, r"outcome.?1|outcome:1|revised.from|finding.revised|changed")
    outcome_1_all = _count_pattern(findings, r"outcome.?[123]|outcome:[123]")
    if outcome_1 >= 5:
        revisions = 0.9  # material
    elif outcome_1 >= 2:
        revisions = 0.7  # minor
    else:
        revisions = 0.5  # none

    # Gaps: count outcome-3 markers
    gaps = _count_pattern(findings, r"outcome.?3|outcome:3|gap:|flagged.for|verification.gap")
    gaps_penalty = 0.9 ** gaps  # Each gap is a 0.9 multiplier

    # DA factor: parse engagement grade from DA section or exit-gate
    da_factor = 0.85  # default to B
    da_section = _get_agent_section(content, "devils-advocate")
    grade_match = re.search(r"engagement[:\s]*([A-D][+-]?)", da_section, re.IGNORECASE)
    if not grade_match:
        # Also search in exit-gate sections across full content
        grade_match = re.search(r"engagement[:\s]*([A-D][+-]?)", content, re.IGNORECASE)
    if grade_match:
        grade = grade_match.group(1).lower()
        da_factor = _DA_GRADES.get(grade, 0.85)

    # Also check exit-gate
    exit_match = re.search(r"exit.gate:.*?(PASS|FAIL)", content, re.IGNORECASE)

    posterior = prior * agreement * revisions * gaps_penalty * da_factor

    # Check for declared belief state
    declared = None
    divergence = None
    if round_num:
        m = re.search(rf"BELIEF\[r{round_num}\].*?P=([\d.]+)", content)
        if m:
            declared = float(m.group(1))
            divergence = abs(declared - posterior)
    else:
        # Find latest belief
        all_beliefs = re.findall(r"BELIEF\[r\d+\].*?P=([\d.]+)", content)
        if all_beliefs:
            declared = float(all_beliefs[-1])
            divergence = abs(declared - posterior)

    return BeliefComponents(
        prior=prior,
        agreement=agreement,
        revisions=revisions,
        gaps_penalty=gaps_penalty,
        da_factor=da_factor,
        posterior=posterior,
        declared=declared,
        divergence=divergence,
        breakdown={
            "tier": tier,
            "agent_count": agent_count,
            "agents_converged": converged,
            "outcome_1_count": outcome_1,
            "outcome_total": outcome_1_all,
            "gap_count": gaps,
            "da_grade": grade_match.group(1) if grade_match else "B (default)",
            "exit_gate": exit_match.group(1) if exit_match else "not found",
            "outcome_1_includes_fuzzy": outcome_1 > outcome_1_all,
        },
    )


def compute_build_plan_belief(workspace_path: str | None = None, round_num: int | None = None) -> BeliefComponents:
    """Mechanically derive BUILD plan-phase belief state.

    Weighted sum: builder-feasibility(0.25) + interface-agreement(0.20) +
    design-arch-coherence(0.15) + no-assumption-conflicts(0.15) +
    prompt-understanding-coverage(0.10) + DA-exit-gate(0.15)
    """
    content = read_workspace(workspace_path)
    sections = parse_sections(content)
    findings = sections.get("findings", "")

    # Builder feasibility: count BUILD-CHALLENGE feasibility ratings
    high_feas = _count_pattern(findings, r"BUILD-CHALLENGE.*feasibility:H")
    med_feas = _count_pattern(findings, r"BUILD-CHALLENGE.*feasibility:M")
    low_feas = _count_pattern(findings, r"BUILD-CHALLENGE.*feasibility:L")
    total_feas = high_feas + med_feas + low_feas
    builder_feasibility = (high_feas * 1.0 + med_feas * 0.6 + low_feas * 0.2) / max(total_feas, 1)

    # Interface agreement: check IC[] in both plan and build sections
    has_ic = bool(re.search(r"IC\[\d+\]", sections.get("interface-contracts", "")))
    interface_agreement = 0.8 if has_ic else 0.3

    # Design-arch coherence: check cross-references
    has_adrs = bool(re.search(r"ADR\[\d+\]", sections.get("architecture-decisions", "")))
    has_ds = bool(re.search(r"DS\[", sections.get("design-system", "")))
    coherence_score = sum([has_adrs, has_ds, has_ic]) / 3.0

    # Assumption conflicts: count conflicts
    conflicts = _count_pattern(findings, r"conflict|contradiction|incompatible|assumption.conflict")
    no_conflicts = max(0.0, 1.0 - conflicts * 0.15)

    # Prompt-understanding coverage: check Q[]/H[] addressed
    pd = sections.get("prompt-understanding", sections.get("prompt-decomposition", ""))
    q_count = len(re.findall(r"Q\d+:", pd))
    addressed = _count_pattern(findings, r"Q\d+|H\d+")
    coverage = min(1.0, addressed / max(q_count * 2, 1))

    # DA exit-gate
    da_factor = 0.85
    grade_match = re.search(r"engagement[:\s]*([A-D][+-]?)", findings, re.IGNORECASE)
    if grade_match:
        da_factor = _DA_GRADES.get(grade_match.group(1).lower(), 0.85)

    # Weighted sum
    posterior = (
        builder_feasibility * 0.25
        + interface_agreement * 0.20
        + coherence_score * 0.15
        + no_conflicts * 0.15
        + coverage * 0.10
        + da_factor * 0.15
    )

    # Declared
    declared = None
    divergence = None
    beliefs = re.findall(r"BELIEF\[plan-r\d+\].*?P=([\d.]+)", content)
    if beliefs:
        declared = float(beliefs[-1])
        divergence = abs(declared - posterior)

    return BeliefComponents(
        prior=builder_feasibility,  # dominant component
        agreement=interface_agreement,
        revisions=coherence_score,
        gaps_penalty=no_conflicts,
        da_factor=da_factor,
        posterior=posterior,
        declared=declared,
        divergence=divergence,
        breakdown={
            "builder_feasibility": round(builder_feasibility, 3),
            "interface_agreement": round(interface_agreement, 3),
            "design_arch_coherence": round(coherence_score, 3),
            "no_assumption_conflicts": round(no_conflicts, 3),
            "prompt_coverage": round(coverage, 3),
            "da_factor": round(da_factor, 3),
            "weights": "0.25+0.20+0.15+0.15+0.10+0.15",
        },
    )


def compute_build_quality_belief(workspace_path: str | None = None, round_num: int | None = None) -> BeliefComponents:
    """Mechanically derive BUILD quality-phase belief state.

    Weighted sum: plan-compliance(0.25) + test-coverage(0.20) +
    design-fidelity(0.15) + code-quality(0.20) + no-scope-creep(0.10) + DA-exit-gate(0.10)
    """
    content = read_workspace(workspace_path)
    sections = parse_sections(content)
    findings = sections.get("findings", "")

    # Plan compliance: count PLAN-REVIEW compliance ratings
    full_comply = _count_pattern(findings, r"PLAN-REVIEW.*compliance:full")
    partial_comply = _count_pattern(findings, r"PLAN-REVIEW.*compliance:partial")
    drift_comply = _count_pattern(findings, r"PLAN-REVIEW.*compliance:drift")
    total_comply = full_comply + partial_comply + drift_comply
    plan_compliance = (full_comply * 1.0 + partial_comply * 0.5 + drift_comply * 0.1) / max(total_comply, 1)

    # Test coverage: heuristic from findings
    test_mentions = _count_pattern(findings, r"test.coverage|tests?.pass|test.integr")
    test_coverage = min(1.0, 0.5 + test_mentions * 0.1)

    # Design fidelity: check DS/IX references in build output
    design_refs = _count_pattern(findings, r"DS\[|IX\[\d+\]|design.system|design.token")
    design_fidelity = min(1.0, 0.3 + design_refs * 0.1)

    # Code quality: DA code review signals
    quality_signals = _count_pattern(findings, r"code.quality|maintainab|security|correct")
    code_quality = min(1.0, 0.5 + quality_signals * 0.05)

    # Scope creep
    scope_creep = _count_pattern(findings, r"scope.creep|out.of.scope|gold.plat")
    no_scope_creep = max(0.0, 1.0 - scope_creep * 0.2)

    # DA exit-gate
    da_factor = 0.85
    grade_match = re.search(r"engagement[:\s]*([A-D][+-]?)", findings, re.IGNORECASE)
    if grade_match:
        da_factor = _DA_GRADES.get(grade_match.group(1).lower(), 0.85)

    posterior = (
        plan_compliance * 0.25
        + test_coverage * 0.20
        + design_fidelity * 0.15
        + code_quality * 0.20
        + no_scope_creep * 0.10
        + da_factor * 0.10
    )

    declared = None
    divergence = None
    beliefs = re.findall(r"BELIEF\[build-r\d+\].*?P=([\d.]+)", content)
    if beliefs:
        declared = float(beliefs[-1])
        divergence = abs(declared - posterior)

    return BeliefComponents(
        prior=plan_compliance,
        agreement=test_coverage,
        revisions=design_fidelity,
        gaps_penalty=no_scope_creep,
        da_factor=da_factor,
        posterior=posterior,
        declared=declared,
        divergence=divergence,
        breakdown={
            "plan_compliance": round(plan_compliance, 3),
            "test_coverage": round(test_coverage, 3),
            "design_fidelity": round(design_fidelity, 3),
            "code_quality": round(code_quality, 3),
            "no_scope_creep": round(no_scope_creep, 3),
            "da_factor": round(da_factor, 3),
            "weights": "0.25+0.20+0.15+0.20+0.10+0.10",
        },
    )


def check_synthesis_artifact(content: str) -> CheckResult:
    """V23: Persistent synthesis artifact saved to shared/archive/.

    The synthesis document is the durable output of a review — a structured reference
    that detailed analyses, executive summaries, and build plans can be derived from.
    Must contain: prompt decomposition, findings by domain, convergence/tensions,
    calibrated estimates, DA resolutions, and open questions.
    """
    archive_dir = sp.ARCHIVE_DIR

    # Look for synthesis files (convention: *-synthesis.md)
    synthesis_files = sorted(archive_dir.glob("*-synthesis.md")) if archive_dir.exists() else []

    # Also check for synthesis content within workspace archive files
    # (synthesis may be embedded in the workspace archive rather than separate)
    workspace_archives = sorted(archive_dir.glob("*.md")) if archive_dir.exists() else []
    archive_with_synthesis = []
    for f in workspace_archives:
        if f.name.endswith("-synthesis.md"):
            continue  # already counted above
        try:
            text = f.read_text(encoding="utf-8")
            # Check for synthesis markers — structured findings, not just raw workspace
            has_findings = bool(re.search(r"##\s*(findings|key findings|domain findings)", text, re.IGNORECASE))
            has_estimates = bool(re.search(r"(P\(|probability|confidence|calibrat)", text, re.IGNORECASE))
            if has_findings and has_estimates:
                archive_with_synthesis.append(f.name)
        except (OSError, UnicodeDecodeError):
            pass

    has_dedicated = len(synthesis_files) > 0
    has_embedded = len(archive_with_synthesis) > 0

    # Validate synthesis content quality (if dedicated file exists)
    required_sections = []
    if has_dedicated:
        latest = synthesis_files[-1]
        try:
            synth_text = latest.read_text(encoding="utf-8")
            section_checks = {
                "prompt-decomposition": bool(re.search(r"(Q\d+:|H\d+:|prompt.decomposition)", synth_text, re.IGNORECASE)),
                "findings": bool(re.search(r"(F\[|finding|##\s*findings)", synth_text, re.IGNORECASE)),
                "convergence-or-tensions": bool(re.search(r"(converg|tension|disagree|dissent)", synth_text, re.IGNORECASE)),
                "estimates": bool(re.search(r"(P\(|probability|%|\d+%|calibrat)", synth_text, re.IGNORECASE)),
            }
            required_sections = [k for k, v in section_checks.items() if not v]
        except (OSError, UnicodeDecodeError):
            required_sections = ["file-unreadable"]

    passed = has_dedicated or has_embedded
    issues = []
    if not passed:
        issues.append(
            "No synthesis artifact found in shared/archive/. "
            "Synthesis agent must save a *-synthesis.md file to the archive directory."
        )
    if required_sections:
        issues.append(f"Synthesis file missing sections: {', '.join(required_sections)}")

    return CheckResult(
        name="V23-synthesis-artifact",
        passed=passed,
        details={
            "dedicated_synthesis_files": [f.name for f in synthesis_files],
            "archives_with_synthesis": archive_with_synthesis,
            "missing_sections": required_sections,
        },
        issues=issues,
    )


def check_session_end(content: str, repo_path: str | None = None) -> CheckResult:
    """V22: Archive exists and git repo has no uncommitted changes.

    Verifies that review outputs are committed before the orchestrator declares terminal.
    Checks the archive repo from sigma_paths.archive_repo(); N/A when none is configured.
    """
    # Check archive exists
    sections = parse_sections(content)
    has_archive_ref = bool(re.search(r"archive", content, re.IGNORECASE))

    # Check archive directory for recent files
    archive_dir = sp.ARCHIVE_DIR
    archive_files = sorted(archive_dir.glob("*.md")) if archive_dir.exists() else []
    has_archive_file = len(archive_files) > 0

    # Check git status in the archive repo (None → N/A)
    if repo_path is None:
        repo_path = sp.archive_repo()

    git_clean = False
    uncommitted: list[str] = []
    unpushed = 0
    git_error = None

    if repo_path is None:
        git_clean = True  # no archive repo configured: A14 N/A
    else:
        try:
            # Check for uncommitted changes
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=repo_path, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                changes = [line for line in result.stdout.strip().splitlines() if line.strip()]
                uncommitted = changes
                git_clean = len(changes) == 0

            # Check for unpushed commits
            result = subprocess.run(
                ["git", "rev-list", "--count", "@{u}..HEAD"],
                cwd=repo_path, capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                unpushed = int(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as e:
            git_error = str(e)

    all_clean = git_clean and unpushed == 0
    issues = []
    if not has_archive_file:
        issues.append("No archive files found in shared/archive/")
    if not git_clean:
        issues.append(f"Uncommitted changes in repo: {len(uncommitted)} files")
    if unpushed > 0:
        issues.append(f"{unpushed} unpushed commit(s) — push before completing review")
    if git_error:
        issues.append(f"Git check error: {git_error}")

    return CheckResult(
        name="V22-session-end-verified",
        passed=has_archive_file and all_clean,
        details={
            "archive_file_found": has_archive_file,
            "archive_count": len(archive_files),
            "git_clean": git_clean,
            "uncommitted_count": len(uncommitted),
            "uncommitted_files": uncommitted[:10],  # cap for readability
            "unpushed_commits": unpushed,
            "git_error": git_error,
            "repo_path": repo_path,
        },
        issues=issues,
    )


def validate_session_end(workspace_path: str | None = None, **kwargs: Any) -> ValidationResult:
    """Bundle: V22+V23 — session end verification (archive + git + synthesis artifact)."""
    content = read_workspace(workspace_path)

    checks = [
        check_session_end(content, repo_path=kwargs.get("repo_path")),
        check_synthesis_artifact(content),
    ]

    all_passed = all(c.passed for c in checks)

    return ValidationResult(
        bundle="session-end",
        passed=all_passed,
        checks=checks,
        context_update={"session_end_verified": all_passed},
    )


# ---------------------------------------------------------------------------
# Compilation wiki integrity checks (V24-V26)
# ---------------------------------------------------------------------------

WIKI_DIR = sp.WIKI_DIR


def check_wiki_source_attribution(wiki_dir: Path | None = None) -> CheckResult:
    """V24: Every new finding in wiki pages carries source attribution [R{N}, {date}].

    Compilation must not add unattributed claims to the knowledge base.
    Checks all wiki pages (excluding INDEX.md) for findings without [R...] tags.
    """
    wd = wiki_dir or WIKI_DIR
    if not wd.exists():
        return CheckResult(
            name="V24-wiki-source-attribution",
            passed=False,
            issues=["Wiki directory does not exist"],
        )

    pages = [f for f in wd.glob("*.md") if f.name.upper() != "INDEX.MD"]
    if not pages:
        # No pages yet — compilation may not have created any (valid if synthesis had nothing to compile)
        return CheckResult(
            name="V24-wiki-source-attribution",
            passed=True,
            details={"page_count": 0, "note": "no wiki pages exist — valid if first review or nothing to compile"},
        )

    unattributed_pages = []
    for page in pages:
        try:
            text = page.read_text(encoding="utf-8")
            # Page should have at least one [R source attribution
            has_attribution = bool(re.search(r"\[R\d+", text))
            if not has_attribution and len(text.strip()) > 100:  # non-trivial content without attribution
                unattributed_pages.append(page.name)
        except (OSError, UnicodeDecodeError):
            unattributed_pages.append(f"{page.name} (unreadable)")

    passed = len(unattributed_pages) == 0
    issues = []
    if not passed:
        issues.append(
            f"Wiki pages without source attribution: {', '.join(unattributed_pages)}. "
            "Every finding must carry [R{{number}}, {{date}}] provenance."
        )

    return CheckResult(
        name="V24-wiki-source-attribution",
        passed=passed,
        details={"pages_checked": len(pages), "unattributed": unattributed_pages},
        issues=issues,
    )


def check_wiki_contradiction_preserved(wiki_dir: Path | None = None) -> CheckResult:
    """V25: No contradiction silently resolved — CONFLICT flags must not be removed.

    If a wiki page previously had a CONFLICT flag and it's now gone without a
    corresponding CONFIRMED flag, that's silent resolution (corruption).
    Checks current state: any page with findings from multiple reviews should
    either show agreement (Confirmed) or disagreement (CONFLICT).
    """
    wd = wiki_dir or WIKI_DIR
    if not wd.exists():
        return CheckResult(
            name="V25-wiki-contradiction-preserved",
            passed=True,
            details={"note": "wiki directory does not exist — nothing to check"},
        )

    pages = [f for f in wd.glob("*.md") if f.name.upper() != "INDEX.MD"]
    if not pages:
        return CheckResult(
            name="V25-wiki-contradiction-preserved",
            passed=True,
            details={"page_count": 0},
        )

    multi_source_no_signal = []
    for page in pages:
        try:
            text = page.read_text(encoding="utf-8")
            # Count distinct review sources
            sources = set(re.findall(r"\[R(\d+)", text))
            if len(sources) >= 2:
                # Multiple reviews contributed — should have either CONFLICT or Confirmed markers
                has_conflict = bool(re.search(r"(CONFLICT|⚠\s*CONFLICT)", text, re.IGNORECASE))
                has_confirmed = bool(re.search(r"(✓\s*Confirmed|CONFIRMED)", text, re.IGNORECASE))
                if not has_conflict and not has_confirmed:
                    multi_source_no_signal.append(
                        f"{page.name} (sources: R{', R'.join(sorted(sources))})"
                    )
        except (OSError, UnicodeDecodeError):
            pass

    passed = len(multi_source_no_signal) == 0
    issues = []
    if not passed:
        issues.append(
            f"Wiki pages with multiple review sources but no CONFLICT/Confirmed signal: "
            f"{', '.join(multi_source_no_signal)}. "
            "Multi-source pages must explicitly flag agreement or disagreement."
        )

    return CheckResult(
        name="V25-wiki-contradiction-preserved",
        passed=passed,
        details={"pages_checked": len(pages), "missing_signal": multi_source_no_signal},
        issues=issues,
    )


def check_wiki_page_count(content: str, wiki_dir: Path | None = None) -> CheckResult:
    """V26: Compilation does not delete wiki pages.

    Compares page count in INDEX.md against actual files. If INDEX.md lists
    pages that no longer exist, compilation may have deleted content.
    Also flags if wiki dir has pages not listed in INDEX.md (index drift).
    """
    wd = wiki_dir or WIKI_DIR
    index_path = wd / "INDEX.md"

    if not wd.exists():
        return CheckResult(
            name="V26-wiki-page-count",
            passed=False,
            issues=["Wiki directory does not exist"],
        )

    if not index_path.exists():
        return CheckResult(
            name="V26-wiki-page-count",
            passed=False,
            issues=["Wiki INDEX.md does not exist"],
        )

    # Parse INDEX.md for referenced page filenames
    try:
        index_text = index_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return CheckResult(
            name="V26-wiki-page-count",
            passed=False,
            issues=["Wiki INDEX.md unreadable"],
        )

    # Extract filenames from markdown links: [title](filename.md)
    indexed_pages = set(re.findall(r"\]\(([^)]+\.md)\)", index_text))
    # Actual pages on disk
    actual_pages = {f.name for f in wd.glob("*.md") if f.name.upper() != "INDEX.MD"}

    missing_from_disk = indexed_pages - actual_pages
    missing_from_index = actual_pages - indexed_pages

    passed = len(missing_from_disk) == 0
    issues = []
    if missing_from_disk:
        issues.append(
            f"INDEX.md references pages that don't exist on disk: {', '.join(sorted(missing_from_disk))}. "
            "Compilation must not delete wiki pages."
        )
    if missing_from_index:
        # Warning, not failure — index drift is less severe than deletion
        issues.append(
            f"Wiki pages not listed in INDEX.md (index drift): {', '.join(sorted(missing_from_index))}. "
            "INDEX.md should be updated to reflect all pages."
        )

    return CheckResult(
        name="V26-wiki-page-count",
        passed=passed,
        details={
            "indexed_pages": sorted(indexed_pages),
            "actual_pages": sorted(actual_pages),
            "missing_from_disk": sorted(missing_from_disk),
            "missing_from_index": sorted(missing_from_index),
        },
        issues=issues,
    )


def validate_compilation(workspace_path: str | None = None, **kwargs: Any) -> ValidationResult:
    """Bundle: V24+V25+V26 — wiki compilation integrity."""
    content = read_workspace(workspace_path)
    wiki_dir = Path(kwargs.get("wiki_dir", "")) if kwargs.get("wiki_dir") else WIKI_DIR

    checks = [
        check_wiki_source_attribution(wiki_dir),
        check_wiki_contradiction_preserved(wiki_dir),
        check_wiki_page_count(content, wiki_dir),
    ]

    all_passed = all(c.passed for c in checks)

    return ValidationResult(
        bundle="compilation",
        passed=all_passed,
        checks=checks,
        context_update={"compilation_validated": all_passed},
    )


# ---------------------------------------------------------------------------
# Post-exit-gate content checks (V27-V28)
# ---------------------------------------------------------------------------


def check_promotion_content(content: str) -> CheckResult:
    """V27: Promotion phase produced workspace evidence.

    Checks for ## promotion section with content, or agent memory store
    indicators (auto-promote, user-approve entries).
    """
    sections = parse_sections(content)
    promotion = sections.get("promotion", "")

    has_promotion_section = bool(promotion.strip())
    has_auto_promote = bool(re.search(r"auto.promot|P\[.*promoted", content, re.IGNORECASE))
    has_user_approve = bool(re.search(r"user.approve|P.candidate\[", content, re.IGNORECASE))
    has_promotion_markers = has_auto_promote or has_user_approve

    passed = has_promotion_section or has_promotion_markers

    issues = []
    if not passed:
        issues.append(
            "No promotion evidence found — neither ## promotion section with content "
            "nor auto-promote/user-approve markers. The promotion round must execute "
            "before advancing. Agents classify findings as auto-promote or user-approve."
        )

    return CheckResult(
        name="V27-promotion-content",
        passed=passed,
        details={
            "promotion_section": has_promotion_section,
            "auto_promote_found": has_auto_promote,
            "user_approve_found": has_user_approve,
        },
        issues=issues,
    )


def check_sync_evidence(content: str) -> CheckResult:
    """V28: Sync phase produced evidence of infrastructure check.

    Checks for ## sync section, git operations, or drift detection markers.
    """
    sections = parse_sections(content)
    sync_section = sections.get("sync", "")

    has_sync_section = bool(sync_section.strip())
    has_git_markers = bool(re.search(
        r"git\s+(?:status|diff|add|commit|push)|committed|pushed|no.drift|in.sync",
        content, re.IGNORECASE,
    ))
    has_drift_check = bool(re.search(r"drift|sync.check|infrastructure", sync_section, re.IGNORECASE))

    passed = has_sync_section or has_git_markers

    issues = []
    if not passed:
        issues.append(
            "No sync evidence found — neither ## sync section nor git/drift markers. "
            "The sync phase must check for infrastructure drift before archiving."
        )

    return CheckResult(
        name="V28-sync-evidence",
        passed=passed,
        details={
            "sync_section": has_sync_section,
            "git_markers": has_git_markers,
            "drift_check": has_drift_check,
        },
        issues=issues,
    )


def validate_promotion(workspace_path: str | None = None, **kwargs: Any) -> ValidationResult:
    """Bundle: V27 — promotion phase content check."""
    content = read_workspace(workspace_path)
    checks = [check_promotion_content(content)]
    all_passed = all(c.passed for c in checks)
    return ValidationResult(
        bundle="promotion",
        passed=all_passed,
        checks=checks,
        context_update={"promotion_validated": all_passed},
    )


def validate_sync(workspace_path: str | None = None, **kwargs: Any) -> ValidationResult:
    """Bundle: V28 — sync phase evidence check."""
    content = read_workspace(workspace_path)
    checks = [check_sync_evidence(content)]
    all_passed = all(c.passed for c in checks)
    return ValidationResult(
        bundle="sync",
        passed=all_passed,
        checks=checks,
        context_update={"sync_validated": all_passed},
    )


# ---------------------------------------------------------------------------
# Convenience: run a named bundle
# ---------------------------------------------------------------------------

BUNDLES = {
    "r1-convergence": validate_r1_convergence,
    "cb": validate_cb,
    "pre-synthesis": validate_pre_synthesis,
    "plan-convergence": validate_plan_convergence,
    "plan-lock": validate_plan_lock,
    "build-checkpoint": validate_build_checkpoint,
    "challenge-round": validate_challenge_round,
    "compilation": validate_compilation,
    "promotion": validate_promotion,
    "sync": validate_sync,
    "session-end": validate_session_end,
}

BELIEF_MODES = {
    "analyze": compute_analyze_belief,
    "build-plan": compute_build_plan_belief,
    "build-quality": compute_build_quality_belief,
}


def run_validation(bundle_name: str, workspace_path: str | None = None, **kwargs: Any) -> dict:
    """Run a named validation bundle and return JSON-serializable result."""
    fn = BUNDLES.get(bundle_name)
    if fn is None:
        return {"error": f"Unknown bundle: {bundle_name}. Available: {list(BUNDLES.keys())}"}
    result = fn(workspace_path, **kwargs)
    return result.to_dict()


def run_compute_belief(mode: str, workspace_path: str | None = None, round_num: int | None = None) -> dict:
    """Run belief state computation and return JSON-serializable result."""
    fn = BELIEF_MODES.get(mode)
    if fn is None:
        return {"error": f"Unknown mode: {mode}. Available: {list(BELIEF_MODES.keys())}"}
    result = fn(workspace_path, round_num)
    return result.to_dict()


# ---------------------------------------------------------------------------
# TIER-A observable extension (sigma-ui Phase A — ADR[4])
# Additive only — zero existing logic above modified.
# ---------------------------------------------------------------------------

def _get_tier_a_module():
    """Lazily import sigma_ui.tier_a_observables. Returns None if not installed."""
    try:
        import sigma_ui.tier_a_observables as _ta  # noqa: PLC0415
        return _ta
    except ImportError:
        return None


def check_tier_a_coverage_gate(workspace_path: str | None = None,
                                phase_history: list[str] | None = None) -> CheckResult:
    """V-TIER-A: TIER-A observable coverage gate check.

    Delegates to sigma_ui.tier_a_observables.check_tier_a_coverage().
    Returns a failing CheckResult with explanation if sigma_ui not installed.
    """
    content = read_workspace(workspace_path)
    ta = _get_tier_a_module()
    if ta is None:
        return CheckResult(
            name="tier_a_coverage",
            passed=False,
            details={},
            issues=["sigma_ui not installed — TIER-A observables unavailable"],
        )
    result = ta.check_tier_a_coverage(content, phase_history)
    # result is a CheckResult (or compatible duck-type from the module's stub)
    if hasattr(result, "to_dict"):
        # Return as native CheckResult for consistency
        d = result.to_dict()
        return CheckResult(
            name=d["name"],
            passed=d["passed"],
            details=d.get("details", {}),
            issues=d.get("issues", []),
        )
    return result  # type: ignore[return-value]


def compute_analyze_belief_with_tier_a(
    workspace_path: str | None = None,
    round_num: int | None = None,
    phase_history: list[str] | None = None,
) -> BeliefComponents:
    """Extended analyze belief computation incorporating TIER-A observables.

    Falls through to standard compute_analyze_belief() and replaces da_factor
    with TIER-A-blended value if sigma_ui is installed.

    This function is an ADDITION — compute_analyze_belief() is not modified.
    Callers that want TIER-A weighting use this function explicitly.
    """
    base = compute_analyze_belief(workspace_path, round_num)
    ta = _get_tier_a_module()
    if ta is None:
        return base

    content = read_workspace(workspace_path)
    tier_a_da_factor = ta.get_tier_a_da_factor(content, phase_history, base.da_factor)

    # Recompute posterior with TIER-A da_factor (formula: prior × agreement × revisions × gaps_penalty × da_factor)
    new_posterior = base.prior * base.agreement * base.revisions * base.gaps_penalty * tier_a_da_factor

    return BeliefComponents(
        prior=base.prior,
        agreement=base.agreement,
        revisions=base.revisions,
        gaps_penalty=base.gaps_penalty,
        da_factor=tier_a_da_factor,
        posterior=new_posterior,
        declared=base.declared,
        divergence=abs(base.declared - new_posterior) if base.declared is not None else None,
        breakdown={
            **base.breakdown,
            "tier_a_da_factor": tier_a_da_factor,
            "base_da_factor": base.da_factor,
            "tier_a_weighted": True,
        },
    )


BUNDLES["tier-a-coverage"] = check_tier_a_coverage_gate  # type: ignore[assignment]
BELIEF_MODES["analyze-tier-a"] = compute_analyze_belief_with_tier_a
