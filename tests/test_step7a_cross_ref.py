"""
SQ[TW-6] cross-ref grep-test: verifies "Step 7a" label appears only in BUILD contexts.

Companion to SQ[11] TestArchivedWorkspacePassthrough — documents the dual-test-SQ
structure (per audit PARTIAL-C remediation in plan §post-c1-audit-verdict).

Premise: per H7 r2 falsification, the Step 7a HARD GATE structure survives the
BUILD↔ANALYZE port, but the literal "Step 7a" label is dropped on the ANALYZE side
to avoid renumber-cascade across sigma-review/SKILL.md workflow steps. This test
enforces that label-drop mechanically.

Allowed locations for the literal "Step 7a" label:
  - sigma-build skill phase files (skills/sigma-build/phases/)
  - build-directives.md (framework/shared/build-directives.md)
  - controlled cross-references that explicitly call out the BUILD↔ANALYZE label
    distinction (these mention "Step 7a" while explaining ANALYZE drops the label)

Forbidden locations:
  - sigma-review skill phase/SKILL.md files as a step LABEL (mentions of "Step 7a"
    in cross-ref text are permitted; LABELS like "### Step 7a:" are not)
  - sigma-lead.md as a step LABEL on the ANALYZE-mode workflow

Anchor refs (plan): plan §P2.A row Files; ADR[H7] r2; c1-plan.md:62.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import get_infra_dir


CLAUDE_DIR = get_infra_dir()
SKILLS_DIR = CLAUDE_DIR / "skills"
AGENTS_DIR = CLAUDE_DIR / "framework" / "agents"
SHARED_DIR = CLAUDE_DIR / "framework" / "shared"

# Files where "Step 7a" as a literal LABEL is permitted (BUILD contexts).
BUILD_LABEL_OK_PATHS = [
    SKILLS_DIR / "sigma-build" / "phases" / "c1-plan.md",
    SKILLS_DIR / "sigma-build" / "phases" / "c2-build.md",
    SKILLS_DIR / "sigma-build" / "phases" / "c3-review.md",
    SHARED_DIR / "build-directives.md",
]

# ANALYZE-side files that MUST NOT carry the literal "Step 7a" as a step LABEL
# (controlled cross-ref text mentioning "Step 7a" is allowed).
ANALYZE_NO_LABEL_PATHS = [
    SKILLS_DIR / "sigma-review" / "SKILL.md",
    AGENTS_DIR / "sigma-lead.md",
]

# Patterns that are LABELS (forbidden on ANALYZE side):
# - markdown header beginning with "### Step 7a" or "## Step 7a" or "# Step 7a"
# - bullet line beginning with "- Step 7a" or "* Step 7a" as the leading text
# - bold label "**Step 7a**" used as a step name
LABEL_PATTERNS = [
    re.compile(r"^\s*#{1,6}\s+Step 7a\b", re.MULTILINE),
    re.compile(r"^\s*[-*]\s+\*?\*?Step 7a\*?\*?[:\s]", re.MULTILINE),
    re.compile(r"^\s*\*\*Step 7a\*\*[:\s]", re.MULTILINE),
]


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def test_step7a_label_present_in_build_contexts():
    """At least one BUILD-context file must carry the Step 7a label."""
    found_any = False
    for p in BUILD_LABEL_OK_PATHS:
        text = _read(p)
        if any(pat.search(text) for pat in LABEL_PATTERNS):
            found_any = True
            break
    assert found_any, (
        "Step 7a label not found in any BUILD-context file "
        f"({[str(p) for p in BUILD_LABEL_OK_PATHS]}). "
        "BUILD side should retain the label per c1-plan.md:62 HARD GATE structure."
    )


@pytest.mark.parametrize("path", ANALYZE_NO_LABEL_PATHS)
def test_step7a_label_absent_from_analyze_files(path: Path):
    """ANALYZE-side files must not use 'Step 7a' as a step label."""
    text = _read(path)
    assert text, f"{path} does not ship"
    matches: list[str] = []
    for pat in LABEL_PATTERNS:
        for m in pat.finditer(text):
            matches.append(m.group(0).strip())
    assert not matches, (
        f"{path} contains 'Step 7a' as a step label (forbidden on ANALYZE side per H7 r2). "
        f"Found: {matches}. Use 'premise-audit pre-dispatch' as the ANALYZE-side step name "
        "and reference the BUILD label only in controlled cross-ref text."
    )


def test_premise_audit_results_section_referenced_in_analyze_workflow():
    """SKILL.md must reference the ## premise-audit-results section presence-check."""
    skill_md = _read(SKILLS_DIR / "sigma-review" / "SKILL.md")
    assert "## premise-audit-results" in skill_md, (
        "sigma-review/SKILL.md must reference the ## premise-audit-results "
        "workspace-section (chain-evaluator §2p presence-check anchor)."
    )


def test_directives_2p_cross_refs_build_variant():
    """directives.md §2p must point to build-directives.md §2p as the BUILD variant."""
    directives = _read(SHARED_DIR / "directives.md")
    # §2p ANALYZE side has a BUILD variant pointer
    assert "build-directives.md §2p" in directives, (
        "directives.md must contain a > BUILD variant cross-ref to build-directives.md §2p."
    )


def test_directives_8f_cross_ref_to_2p():
    """§8f DC[3] cross-ref must tie post-exit-gate headers to §2p pre-dispatch sibling."""
    directives = _read(SHARED_DIR / "directives.md")
    assert "§8f post-exit-gate" in directives, (
        "directives.md must contain §8f post-exit-gate workspace-headers directive."
    )
    # DC[3] explicitly names §2p as the pre-dispatch sibling.
    assert re.search(r"DC\[3\][^\n]*§2p", directives), (
        "directives.md §8f must contain DC[3] cross-ref naming §2p as pre-dispatch sibling."
    )


def test_grep_audit_step7a_in_analyze_workflow_files_is_cross_ref_only():
    """Targeted grep on the ANALYZE workflow surface (sigma-review skill tree
    + sigma-lead.md). Any 'Step 7a' occurrence in these files must be a controlled
    cross-reference that frames it as a BUILD-side label, not as an ANALYZE-side
    step label.

    Wiki/patterns/portfolio docs in shared/ legitimately discuss the BUILD-side
    Step 7a label and are out of scope here — this test guards the workflow
    surface where the label-drop actually applies.
    """
    targets = [
        SKILLS_DIR / "sigma-review",  # the entire sigma-review skill tree
        AGENTS_DIR / "sigma-lead.md",
    ]
    files: list[Path] = []
    for t in targets:
        files.extend(sorted(t.rglob("*.md")) if t.is_dir() else [t])
    lines = [
        f"{f}:{n}:{ln}"
        for f in files
        for n, ln in enumerate(_read(f).splitlines(), 1)
        if "Step 7a" in ln
    ]

    cross_ref_markers = ("BUILD variant", "BUILD side", "BUILD-side", "BUILD contexts",
                         "BUILD pre-dispatch", "BUILD-mode", "c1-plan.md")

    violations: list[str] = []
    for ln in lines:
        is_cross_ref = any(marker in ln for marker in cross_ref_markers)
        if not is_cross_ref:
            violations.append(ln)

    assert not violations, (
        "Step 7a appears on the ANALYZE workflow surface without cross-ref framing.\n"
        "Each occurrence on this surface must mention 'BUILD variant', 'BUILD side', "
        "'c1-plan.md', or similar marker to make clear it is a BUILD-side label "
        "reference, not an ANALYZE-side step label.\n\n"
        "Violations:\n" + "\n".join(violations)
    )
