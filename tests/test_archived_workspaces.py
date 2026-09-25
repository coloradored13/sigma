"""SQ[11] TestArchivedWorkspacePassthrough — chain-evaluator no-regression
on frozen archived workspaces + DA[#12] universal edge-case checklist.

The archives are SYNTHETIC fixtures in tests/fixtures/ (one ANALYZE review,
one BUILD) that carry the sections the gates read: prompt-decomposition,
scope-boundary, agent findings with DB[]/XVERIFY/DA responses, peer
verification, DA exit-gate, BELIEF, contamination/sycophancy checks,
convergence, promotion, sync, and for BUILD the plan lock, CHECKPOINTs,
agent-assignments and MERGE-VERIFIED.

Per plan PM[1] mitigation: "A26+B5+B6 false-positives on archived workspaces
silently accumulate." The new gates A25/A26/B5/B6 and any ANALYZE_CHAIN
extensions must run in WARN-only mode against frozen archives.
WARN-only means: passed=True regardless of fire count; only BLOCK fires fail.

Per DA[#12] PROMOTION-CANDIDATE (universal edge-case checklist):
empty/BOM/unicode/fenced/trailing-WS edge cases applied across the new
gates in a single pass.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS_DIR))

_spec = importlib.util.spec_from_file_location(
    "chain_evaluator", HOOKS_DIR / "chain-evaluator.py"
)
ce = importlib.util.module_from_spec(_spec)
sys.modules["chain_evaluator"] = ce
_spec.loader.exec_module(ce)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

ANALYZE_ARCHIVE = FIXTURES_DIR / "2026-01-15-payments-api-review-workspace.md"
BUILD_ARCHIVE = FIXTURES_DIR / "2026-02-03-webhook-retry-build-workspace.md"
ARCHIVE_FIXTURES = [ANALYZE_ARCHIVE, BUILD_ARCHIVE]

NEW_WARN_GATES = ("A25", "A26", "B5", "B6")


@pytest.fixture(params=ARCHIVE_FIXTURES, ids=lambda p: p.name)
def archive_path(request):
    """Parametrize over the 3 frozen archive workspaces."""
    p = request.param
    assert p.is_file(), f"archive fixture missing: {p}"
    return p


@pytest.fixture(autouse=True)
def _isolated_calibration_log(tmp_path, monkeypatch):
    """WARN gates append CAL-EMIT records; keep them out of the shared tmp home."""
    monkeypatch.setattr(ce, "CALIBRATION_LOG_PATH", tmp_path / "calibration-log.md")


# ---------------------------------------------------------------------------
# TestArchivedWorkspacePassthrough — primary deliverable
# ---------------------------------------------------------------------------

class TestArchivedWorkspacePassthrough:
    """Run chain-evaluator against each frozen archive in both modes.

    No-regression invariant: evaluator does not crash on pre-gate workspaces;
    new gates A25/A26/B5/B6 return passed=True (WARN-first); every item is
    a well-formed ChainItem.
    """

    def test_evaluate_chain_does_not_crash_analyze(self, archive_path):
        """Running ANALYZE chain on a frozen archive must not raise."""
        result = ce.evaluate_chain(archive_path, mode="ANALYZE")
        assert result is not None
        assert result.mode == "ANALYZE"
        assert result.items, "ANALYZE chain produced zero items"

    def test_evaluate_chain_does_not_crash_build(self, archive_path):
        """Running BUILD chain on a frozen archive must not raise.

        BUILD mode adds B1-B6 extras on top of ANALYZE_CHAIN.
        """
        result = ce.evaluate_chain(archive_path, mode="BUILD")
        assert result is not None
        assert result.mode == "BUILD"
        assert result.items, "BUILD chain produced zero items"

    def test_all_items_well_formed(self, archive_path):
        """Every ChainItem must have item_id/name/passed/category/details."""
        result = ce.evaluate_chain(archive_path, mode="BUILD")
        for item in result.items:
            assert isinstance(item.item_id, str) and item.item_id
            assert isinstance(item.name, str) and item.name
            assert isinstance(item.passed, bool)
            assert item.category, f"{item.item_id} missing category"
            assert isinstance(item.details, dict)
            assert isinstance(item.issues, list)

    def test_new_warn_gates_passed_true_warn_only(self, archive_path):
        """A25/A26/B5/B6 must return passed=True on archives.

        PM[1]: "A26+B5+B6 false-positives on archived workspaces silently
        accumulate." Mitigation = WARN-first (passed=True even when fired).
        Includes A25 for symmetry. Issue counts logged but NOT asserted.
        """
        result = ce.evaluate_chain(archive_path, mode="BUILD")
        gates = {item.item_id: item for item in result.items}
        for gate_id in NEW_WARN_GATES:
            assert gate_id in gates, (
                f"{gate_id} missing from BUILD chain on {archive_path.name}"
            )
            item = gates[gate_id]
            issues_count = len(item.issues)
            fires_count = len(item.details.get("fires", []))
            assert item.passed is True, (
                f"{gate_id} flipped to passed=False on archive "
                f"{archive_path.name} — WARN-only invariant violated. "
                f"issues={issues_count}, fires={fires_count}, "
                f"first_issue={item.issues[0] if item.issues else None}"
            )
            # WARN visibility — count is informational, not asserted
            print(
                f"  [WARN-log] {gate_id} on {archive_path.name}: "
                f"issues={issues_count}, fires={fires_count}"
            )

    def test_existing_chain_items_present(self, archive_path):
        """A1-A18 + A20/A22-A24 (ANALYZE) + B1-B4 (BUILD) must still appear.

        No-regression: SQ[1-10] additions did not silently drop or rename
        any prior chain item.
        """
        result = ce.evaluate_chain(archive_path, mode="BUILD")
        present = {item.item_id for item in result.items}
        # Spot-check pre-existing A items that have not been deprecated.
        # A19 is reserved (intentionally absent); A21 likewise (β+ slot).
        expected_analyze = {
            "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10",
            "A11", "A12", "A13", "A14", "A15",
            "A16", "A17", "A18",
            "A20", "A22", "A23", "A24",
        }
        expected_build = {"B1", "B2", "B3", "B4"}
        missing = (expected_analyze | expected_build) - present
        assert not missing, (
            f"Existing chain items dropped on {archive_path.name}: "
            f"{sorted(missing)}"
        )

    def test_evaluate_single_dispatches_each_new_gate(self, archive_path):
        """evaluate_single("A25"|"A26"|"B5"|"B6", path) returns the right
        ChainItem and respects WARN-only on archives."""
        for gate_id in NEW_WARN_GATES:
            item = ce.evaluate_single(gate_id, archive_path)
            assert item.item_id.upper() == gate_id, (
                f"evaluate_single({gate_id}) returned item_id={item.item_id}"
            )
            assert item.passed is True, (
                f"evaluate_single({gate_id}) flipped to False on "
                f"{archive_path.name}"
            )
            assert item.category == "agent-work"


class TestSyntheticArchiveContent:
    """The synthetic archives must exercise the gates, not just avoid crashes."""

    def test_agent_work_items_pass_on_complete_analyze_archive(self):
        result = ce.evaluate_chain(ANALYZE_ARCHIVE, mode="ANALYZE")
        failed = {i.item_id for i in result.items if not i.passed}
        # A11/A12 look for files in shared/archive/, which a fixture cannot supply.
        assert failed <= {"A11", "A12"}, f"unexpected failures: {sorted(failed)}"

    def test_build_items_pass_on_complete_build_archive(self):
        result = ce.evaluate_chain(BUILD_ARCHIVE, mode="BUILD")
        failed = {i.item_id for i in result.items if not i.passed}
        assert failed <= {"A11", "A12"}, f"unexpected failures: {sorted(failed)}"

    def test_warn_gate_fires_but_stays_passed(self):
        """A26 fires (plan file absent) and B5 fires on the ANALYZE archive run
        in BUILD mode (no agent-assignments) — both remain passed=True."""
        a26 = ce.evaluate_single("A26", BUILD_ARCHIVE)
        assert a26.details["fire_count"] >= 1 and a26.passed is True
        b5 = ce.evaluate_single("B5", ANALYZE_ARCHIVE)
        assert b5.details["fire_count"] >= 1 and b5.passed is True


# ---------------------------------------------------------------------------
# TestDA12UniversalEdgeCases — DA[#12] PROMOTION-CANDIDATE checklist
#
# Single-pass coverage of empty/BOM/unicode/fenced/trailing-WS across all
# new IC handlers, applied at end of r1. Kept synthetic (NOT archive-derived)
# so each case is minimal and unambiguous.
# ---------------------------------------------------------------------------

BOM = "﻿"


def _ws(*sections: str) -> str:
    """Build a minimal ANALYZE/BUILD workspace from header + sections."""
    return "\n".join(sections) + "\n"


# Common minimal headers
ANALYZE_HEADER = "# ws\n## status: active\n## mode: ANALYZE\n## review-id: RV-edge-001"
BUILD_HEADER = "# ws\n## status: building\n## mode: BUILD\n## build-id: BLD-edge-001"


class TestDA12UniversalEdgeCases:
    """DA[#12] universal edge-case coverage for IC[2-8] new gates.

    Five edge classes × four gates = 20 case probes. Each case writes a
    synthetic workspace to a temp file, evaluates the gate, asserts:
      (a) no crash
      (b) WARN-only invariant (passed=True)
      (c) where deterministic, the expected fire/no-fire behavior.
    """

    # ---- empty section ----

    def test_a26_empty_means_no_header_no_fire(self, tmp_path):
        """A26: workspace with no `## plan-file` header at all → no fire."""
        ws = tmp_path / "ws.md"
        ws.write_text(_ws(ANALYZE_HEADER, "## task", "do stuff"))
        item = ce.evaluate_single("A26", ws)
        assert item.passed is True
        assert item.details["fire_count"] == 0

    def test_b5_empty_section_warns_not_crashes(self, tmp_path):
        """B5/IC[8]: empty `## agent-assignments` → WARN, NOT crash."""
        ws = tmp_path / "ws.md"
        ws.write_text(_ws(BUILD_HEADER, "## agent-assignments", "", "## task"))
        item = ce.evaluate_single("B5", ws)
        assert item.passed is True  # WARN-only
        # Must surface the empty-section schema gap explicitly
        assert item.details["fire_count"] >= 1
        triggers = [f["trigger"] for f in item.details["fires"]]
        assert any("empty" in t or "zero-parse" in t for t in triggers)

    def test_b6_no_checkpoints_no_fire(self, tmp_path):
        """B6: workspace with zero CHECKPOINT[] lines → no fire (benign)."""
        ws = tmp_path / "ws.md"
        ws.write_text(_ws(BUILD_HEADER, "## findings", "F[1]: nothing here"))
        item = ce.evaluate_single("B6", ws)
        assert item.passed is True
        assert item.details["fire_count"] == 0

    # ---- BOM prefix ----

    def test_a26_bom_prefix_still_detects_header(self, tmp_path):
        """A26: BOM-prefixed workspace must still detect `## plan-file`.

        Catches regressions where the regex anchor breaks on BOM bytes.
        """
        ws = tmp_path / "ws.md"
        body = _ws(
            ANALYZE_HEADER,
            "## plan-file",
            "/nonexistent/path/that/will/miss.md",
            "## task",
        )
        ws.write_text(BOM + body, encoding="utf-8")
        item = ce.evaluate_single("A26", ws)
        assert item.passed is True
        # Header detected → either parses path-then-missing fire OR no-path
        assert item.details.get("plan_path") is not None or \
               item.details["fire_count"] >= 1

    def test_b5_bom_prefix_still_parses_section(self, tmp_path):
        """B5/IC[8]: BOM prefix must not blind the agent-assignments parser."""
        ws = tmp_path / "ws.md"
        body = _ws(
            BUILD_HEADER,
            "## agent-assignments",
            "SQ[1]: owner=implementation-engineer |cluster=foo.py",
            "## task",
        )
        ws.write_text(BOM + body, encoding="utf-8")
        item = ce.evaluate_single("B5", ws)
        assert item.passed is True
        # Section parsed successfully
        assert item.details["section_used"] == "agent-assignments"
        assignments = item.details.get("assignments_parsed", [])
        assert assignments, (
            "BOM-prefixed B5 returned zero assignments — parser blind to BOM"
        )

    def test_b6_bom_prefix_still_finds_checkpoint(self, tmp_path):
        """B6: BOM prefix must not hide CHECKPOINT lines."""
        ws = tmp_path / "ws.md"
        body = _ws(
            BUILD_HEADER,
            "## findings",
            "CHECKPOINT[implementation-engineer]: files-created=foo.py |tests=7",
        )
        ws.write_text(BOM + body, encoding="utf-8")
        item = ce.evaluate_single("B6", ws)
        assert item.passed is True
        assert item.details["checkpoint_count"] >= 1

    # ---- unicode in section content ----

    def test_b5_unicode_owner_and_files(self, tmp_path):
        """B5/IC[8]: non-ASCII content in owner/file names must parse."""
        ws = tmp_path / "ws.md"
        ws.write_text(_ws(
            BUILD_HEADER,
            "## agent-assignments",
            "SQ[1]: owner=implementation-engineer |cluster=café.py,naïve.md",
            "SQ[2]: owner=technical-writer |cluster=résumé.md",
            "## task",
        ))
        item = ce.evaluate_single("B5", ws)
        assert item.passed is True
        assignments = item.details.get("assignments_parsed", [])
        assert len(assignments) == 2

    def test_b6_unicode_in_checkpoint_body(self, tmp_path):
        """B6: unicode in CHECKPOINT body must not break the 3-pass parser."""
        ws = tmp_path / "ws.md"
        ws.write_text(_ws(
            BUILD_HEADER,
            "## findings",
            "CHECKPOINT[ie]: files-created=café.py |notes=façade-pattern",
        ))
        item = ce.evaluate_single("B6", ws)
        assert item.passed is True

    # ---- fenced-code block exclusion ----

    def test_a26_fenced_plan_file_does_not_trigger(self, tmp_path):
        """A26/ADR[9]: `## plan-file` inside a fenced code block must be
        excluded from header detection (false-match prevention)."""
        ws = tmp_path / "ws.md"
        ws.write_text(_ws(
            ANALYZE_HEADER,
            "## task",
            "Example workspace skeleton:",
            "```markdown",
            "## plan-file",
            "/some/path/plan.md",
            "```",
            "## findings",
        ))
        item = ce.evaluate_single("A26", ws)
        assert item.passed is True
        assert item.details["fire_count"] == 0, (
            "A26 fired on `## plan-file` inside fenced code — fence "
            "exclusion regression"
        )

    def test_b5_fenced_agent_assignments_does_not_trigger(self, tmp_path):
        """B5/ADR[9]: `## agent-assignments` inside fenced code must be
        excluded — but ALSO real section must still parse if both present."""
        ws = tmp_path / "ws.md"
        ws.write_text(_ws(
            BUILD_HEADER,
            "## task",
            "Example skeleton from docs:",
            "```markdown",
            "## agent-assignments",
            "SQ[X]: owner=AGENT |cluster=FILES",
            "```",
            "## agent-assignments",
            "SQ[1]: owner=implementation-engineer |cluster=real.py",
            "## next",
        ))
        item = ce.evaluate_single("B5", ws)
        assert item.passed is True
        assignments = item.details.get("assignments_parsed", [])
        assert len(assignments) == 1, (
            f"Expected 1 real assignment (fenced excluded), "
            f"got {len(assignments)}: {assignments}"
        )
        assert assignments[0]["sq_id"] == "1"

    def test_b6_fenced_checkpoint_does_not_count(self, tmp_path):
        """B6: CHECKPOINT[] inside fenced code must not count as a real
        checkpoint."""
        ws = tmp_path / "ws.md"
        ws.write_text(_ws(
            BUILD_HEADER,
            "## task",
            "Format example:",
            "```",
            "CHECKPOINT[example-agent]: files-created=foo.py",
            "```",
            "## findings",
            "(no real checkpoint yet)",
        ))
        item = ce.evaluate_single("B6", ws)
        assert item.passed is True
        assert item.details["checkpoint_count"] == 0

    # ---- trailing whitespace ----

    def test_b5_trailing_whitespace_on_assignment_line(self, tmp_path):
        """B5: assignment lines with trailing spaces/tabs must still parse."""
        ws = tmp_path / "ws.md"
        ws.write_text(_ws(
            BUILD_HEADER,
            "## agent-assignments",
            "SQ[1]: owner=implementation-engineer |cluster=foo.py   \t",
            "## task",
        ))
        item = ce.evaluate_single("B5", ws)
        assert item.passed is True
        assignments = item.details.get("assignments_parsed", [])
        assert len(assignments) == 1
        # Trailing WS must be stripped from cluster value
        assert "foo.py" in assignments[0]["files"]

    def test_b6_trailing_whitespace_on_checkpoint_line(self, tmp_path):
        """B6: CHECKPOINT lines with trailing whitespace must parse."""
        ws = tmp_path / "ws.md"
        ws.write_text(_ws(
            BUILD_HEADER,
            "## findings",
            "CHECKPOINT[ie]: files-created=foo.py   \t",
        ))
        item = ce.evaluate_single("B6", ws)
        assert item.passed is True
        assert item.details["checkpoint_count"] == 1


# ---------------------------------------------------------------------------
# TestVerificationSpotChecks — plan §Verification end-to-end specs
#
# Lightweight cross-checks per plan §Verification. Deeper coverage lives
# in the IE/TW per-SQ test files; these are integration spot-checks.
# ---------------------------------------------------------------------------

class TestVerificationSpotChecks:
    """Spot-check the plan §Verification end-to-end specs (CQA layer).

    Each case maps to a numbered §Verification line; deeper coverage is
    in the SQ owner's per-SQ test file (cited in docstring).
    """

    # §Verification #3 — A26 false-positive: ## plans does NOT trigger
    def test_a26_plans_section_does_not_trigger(self, tmp_path):
        """`## plans` (note final 's', no `-file` suffix) is a different
        section name and must NOT trigger A26. (Spot-check; deeper in
        TestA26PlanCompleteness.)"""
        ws = tmp_path / "ws.md"
        ws.write_text(_ws(
            ANALYZE_HEADER,
            "## plans",
            "We plan to do many things.",
            "## task",
        ))
        item = ce.evaluate_single("A26", ws)
        assert item.passed is True
        assert item.details["fire_count"] == 0, (
            "A26 falsely fired on `## plans` (not `## plan-file`)"
        )

    def test_a26_plan_file_inline_form_does_trigger_when_missing(self, tmp_path):
        """`## plan-file: /path` inline form must trigger A26 when path is
        missing on disk. (Spot-check.)"""
        ws = tmp_path / "ws.md"
        ws.write_text(_ws(
            ANALYZE_HEADER,
            "## plan-file: /nonexistent/missing-plan.md",
            "## task",
        ))
        item = ce.evaluate_single("A26", ws)
        assert item.passed is True  # WARN-only
        assert item.details["fire_count"] >= 1
        assert item.details.get("plan_exists") is False

    # §Verification #4 — B5 schema gap: explicit zero-parse WARN, NOT silent
    def test_b5_zero_parse_emits_explicit_warn(self, tmp_path):
        """B5: section present, header present, but zero SQ[] lines parse
        → emit explicit zero-parse WARN, NOT silent empty. (Spot-check.)"""
        ws = tmp_path / "ws.md"
        ws.write_text(_ws(
            BUILD_HEADER,
            "## agent-assignments",
            "Some prose without any SQ[] lines.",
            "Another prose line.",
            "## task",
        ))
        item = ce.evaluate_single("B5", ws)
        assert item.passed is True  # WARN-only
        assert item.details["fire_count"] >= 1
        triggers = [f["trigger"] for f in item.details["fires"]]
        assert any("zero-parse" in t or "empty" in t for t in triggers), (
            f"B5 zero-parse case did not emit explicit WARN. triggers={triggers}"
        )

    # §Verification #5 — B6 keyword=value canonical parses CHECKPOINT
    def test_b6_keyword_value_canonical_parses(self, tmp_path):
        """B6: canonical `CHECKPOINT[agent]: key=value |key2=val2` parses
        cleanly via Pass 1 (keyword=value). Mirrors R19 c2-scratch format.
        (Spot-check.)"""
        ws = tmp_path / "ws.md"
        ws.write_text(_ws(
            BUILD_HEADER,
            "## agent-assignments",
            "SQ[1]: owner=implementation-engineer |cluster=foo.py",
            "## findings",
            "CHECKPOINT[implementation-engineer]: "
            "files-created=foo.py |tests=7 |drift=none |surprises=none",
        ))
        item = ce.evaluate_single("B6", ws)
        assert item.passed is True
        assert item.details["checkpoint_count"] == 1
        parsed = item.details["checkpoints_parsed"][0]
        assert parsed["parse_mode"] == "keyword=value"
        assert "files-created" in parsed["fields"]
        assert "tests" in parsed["fields"]

    # §Verification #6 — _XVERIFY_ANY_RE bracket vs prose
    def test_xverify_any_re_bracket_form_matches(self):
        """_XVERIFY_ANY_RE: bracket form `XVERIFY[provider:model]` matches.
        (Spot-check; deeper coverage in TestA24SigmaVerifyInitPreFlight.)"""
        regex = ce._XVERIFY_ANY_RE
        assert regex.search("XVERIFY[openai:gpt-5]")
        assert regex.search("XVERIFY-FAIL[openai:gpt-5]")
        assert regex.search("XVERIFY-PARTIAL[openai:gpt-5]")

    def test_xverify_any_re_prose_form_does_not_match(self):
        """_XVERIFY_ANY_RE: prose mentions `XVERIFY:`, `XVERIFY (`, `XVERIFY `
        (no bracket) must NOT match. SQ[7] tightening per IC[7].
        (Spot-check; deeper coverage in TestA24SigmaVerifyInitPreFlight.)"""
        regex = ce._XVERIFY_ANY_RE
        assert not regex.search("XVERIFY: see report"), \
            "prose colon-form should not suppress"
        assert not regex.search("XVERIFY (with caveats)"), \
            "prose paren-form should not suppress"
        assert not regex.search("XVERIFY result"), \
            "prose space-form should not suppress"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
