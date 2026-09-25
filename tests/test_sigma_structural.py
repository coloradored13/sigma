"""Structural validation tests for sigma-review/sigma-build agent infrastructure.

Validates:
1. Agent definition files — required sections, boot sequence, consistency
2. Roster-to-agent file mapping — bidirectional consistency
3. Cross-file reference integrity — directives, decisions, patterns, protocols

Note: Phase-file completeness tests (TestReviewPhaseFiles / TestBuildPhaseFiles)
and _template.md step 2a tests (TestAgentTemplateBoot) were removed when the
phase-based architecture was retired in favor of the atomic checklist model
(commit 79bbae5, 2026-04-15). Agent boot template also changed in that refactor.
"""
import re
from pathlib import Path

import pytest

from conftest import get_infra_dir

CLAUDE_DIR = get_infra_dir()  # plugin root
AGENTS_DIR = CLAUDE_DIR / "framework" / "agents"
# Framework-managed shared files (synced to SIGMA_HOME/shared on every upgrade)
FRAMEWORK_SHARED = CLAUDE_DIR / "framework" / "shared"
# First-run user state (seeded once into SIGMA_HOME/shared)
SEED_SHARED = CLAUDE_DIR / "framework" / "seed" / "shared"

# --- Agent lists ---

STANDARD_AGENTS = [
    "code-quality-analyst",
    "cognitive-decision-scientist",
    "devils-advocate",
    "implementation-engineer",
    "product-designer",
    "product-strategist",
    "reference-class-analyst",
    "security-specialist",
    "tech-architect",
    "technical-writer",
    "ui-ux-engineer",
    "ux-researcher",
]

SPECIAL_FILES = {
    "_template.md",
    "SIGMA-COMM-SPEC.md",
    "sigma-comm.md",
    "sigma-lead.md",
    "synthesis-agent.md",
    "compilation-agent.md",
}

# --- Directives key sections ---

DIRECTIVES_REQUIRED_TERMS = [
    "adversarial-layer",
    "hypothesis-matrix",
    "superforecasting",
    "bayesian-consensus",
    "prompt-decomposition",
]


# ============================================================
# Helpers
# ============================================================

def _read_agent(name: str) -> str:
    """Read an agent .md file and return its content."""
    path = AGENTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")


def _section_headers(content: str) -> list[str]:
    """Extract all ## headers from markdown content."""
    return re.findall(r"^## .+", content, re.MULTILINE)


def _parse_roster() -> dict[str, str]:
    """Parse roster.md into {agent_name: full_line} dict."""
    path = SEED_SHARED / "roster.md"
    content = path.read_text(encoding="utf-8")
    roster = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("→"):
            continue
        # Lines are: agent-name |domain: ... |wake-for: ...
        name = line.split("|")[0].strip()
        if name:
            roster[name] = line
    return roster


# ============================================================
# TestAgentDefinitions — parametrized over standard agents
# ============================================================

class TestAgentDefinitions:
    """Validate required sections in every standard agent file."""

    @pytest.fixture(params=sorted(STANDARD_AGENTS))
    def agent_name(self, request):
        return request.param

    @pytest.fixture
    def agent_content(self, agent_name):
        return _read_agent(agent_name)

    def test_agent_file_exists(self, agent_name):
        path = AGENTS_DIR / f"{agent_name}.md"
        assert path.exists(), f"Agent file missing: {agent_name}.md"

    def test_has_role_section(self, agent_name, agent_content):
        assert "## Role" in agent_content, (
            f"{agent_name}.md missing ## Role section"
        )

    def test_role_is_concise(self, agent_name, agent_content):
        """Role should appear early and be a short description."""
        match = re.search(r"^## Role\n(.+)", agent_content, re.MULTILINE)
        assert match, f"{agent_name}.md: ## Role has no content on next line"
        role_line = match.group(1).strip()
        assert len(role_line) > 10, (
            f"{agent_name}.md: Role description too short: '{role_line}'"
        )

    def test_has_expertise_section(self, agent_name, agent_content):
        assert "## Expertise" in agent_content, (
            f"{agent_name}.md missing ## Expertise section"
        )

    def test_expertise_has_content(self, agent_name, agent_content):
        match = re.search(r"^## Expertise\n(.+)", agent_content, re.MULTILINE)
        assert match, f"{agent_name}.md: ## Expertise has no content"
        expertise = match.group(1).strip()
        # Should be comma-separated, so at least one comma
        assert "," in expertise, (
            f"{agent_name}.md: Expertise should be comma-separated list"
        )

    def test_has_boot_section(self, agent_name, agent_content):
        assert "## Boot (FIRST)" in agent_content, (
            f"{agent_name}.md missing ## Boot (FIRST) section"
        )

    def test_boot_has_step_1_sigma_comm(self, agent_name, agent_content):
        assert re.search(r"1→sigma-comm", agent_content), (
            f"{agent_name}.md boot missing step 1→sigma-comm"
        )

    def test_boot_has_step_2_memory(self, agent_name, agent_content):
        assert re.search(r"2→memory", agent_content), (
            f"{agent_name}.md boot missing step 2→memory"
        )

    def test_boot_has_step_3_inbox(self, agent_name, agent_content):
        assert re.search(r"3→inbox", agent_content), (
            f"{agent_name}.md boot missing step 3→inbox"
        )

    def test_boot_has_step_4_workspace(self, agent_name, agent_content):
        assert re.search(r"4→workspace", agent_content), (
            f"{agent_name}.md boot missing step 4→workspace"
        )

    def test_boot_has_step_5(self, agent_name, agent_content):
        """Step 5 should reference decisions.md (or directives.md)."""
        assert re.search(r"5→(decisions|directives)", agent_content), (
            f"{agent_name}.md boot missing step 5→decisions or 5→directives"
        )

    def test_boot_has_init_step(self, agent_name, agent_content):
        """Every standard agent must call mcp__sigma-verify__init in its OWN session.

        The unlock is per-session (HATEOAS gateway): the lead's preflight init
        does not propagate to teammate sessions, so an agent without its own
        call ToolSearches cold and logs XVERIFY-FAIL. This exact fix was made
        once before (R19 added it to _template.md) and reached 1 of 29 agents,
        which is how the failure recurred across five reviews — hence a
        per-agent tripwire, not a template-only one. Presence anywhere in
        the definition satisfies this.
        """
        assert "mcp__sigma-verify__init" in agent_content, (
            f"{agent_name}.md never calls mcp__sigma-verify__init — "
            "its XVERIFY attempts will fail with tools-not-found"
        )

    def test_boot_step_order(self, agent_name, agent_content):
        """Steps 1-5 must appear in sequential order."""
        positions = []
        for step_pattern in [
            r"1→sigma-comm",
            r"2→memory",
            r"3→inbox",
            r"4→workspace",
            r"5→(decisions|directives)",
        ]:
            match = re.search(step_pattern, agent_content)
            assert match, f"{agent_name}.md boot step {step_pattern} not found"
            positions.append(match.start())
        for i in range(len(positions) - 1):
            assert positions[i] < positions[i + 1], (
                f"{agent_name}.md boot steps out of order"
            )

    def test_has_comms_section(self, agent_name, agent_content):
        assert "## Comms" in agent_content, (
            f"{agent_name}.md missing ## Comms section"
        )

    def test_has_persistence_section(self, agent_name, agent_content):
        assert "## Persistence" in agent_content, (
            f"{agent_name}.md missing ## Persistence section"
        )

    def test_persistence_variant(self, agent_name, agent_content):
        """Persistence should use the standard header format."""
        assert "## Persistence (before" in agent_content, (
            f"{agent_name}.md: Persistence section missing standard "
            "'(before ..., no direct file writes)' qualifier"
        )

    def test_has_weight_section(self, agent_name, agent_content):
        assert "## Weight" in agent_content, (
            f"{agent_name}.md missing ## Weight section"
        )

    def test_weight_has_primary(self, agent_name, agent_content):
        """Weight section should declare primary domains."""
        # Extract content after ## Weight
        weight_match = re.search(
            r"^## Weight\n(.*?)(?=^## |\Z)", agent_content,
            re.MULTILINE | re.DOTALL,
        )
        assert weight_match, f"{agent_name}.md: ## Weight section empty"
        weight_body = weight_match.group(1)
        assert "primary:" in weight_body.lower() or len(weight_body.strip()) > 10, (
            f"{agent_name}.md: Weight section lacks primary domain declaration"
        )


# ============================================================
# TestRosterConsistency
# ============================================================

class TestRosterConsistency:
    """Validate roster.md and agent file bidirectional consistency."""

    @pytest.fixture
    def roster(self):
        return _parse_roster()

    def test_roster_file_exists(self):
        assert (SEED_SHARED / "roster.md").exists()

    def test_roster_not_empty(self, roster):
        assert len(roster) > 0, "Roster is empty"

    def test_every_roster_agent_has_file(self, roster):
        """Every agent named in roster.md should have a .md file."""
        missing = []
        for name in roster:
            if not (AGENTS_DIR / f"{name}.md").exists():
                missing.append(name)
        assert not missing, f"Roster agents missing .md files: {missing}"

    def test_standard_agents_in_roster(self, roster):
        """Every standard agent should be in the roster."""
        missing = [name for name in STANDARD_AGENTS if name not in roster]
        assert not missing, (
            f"Standard agents missing from roster: {missing}"
        )

    def test_roster_matches_standard_agents(self, roster):
        """The shipped roster names exactly the shipped team agents."""
        assert set(roster) == set(STANDARD_AGENTS)

    @pytest.fixture(params=sorted(STANDARD_AGENTS))
    def review_agent_name(self, request):
        return request.param

    def test_roster_entry_has_domain_field(self, roster, review_agent_name):
        """Each roster entry should have a |domain: field."""
        line = roster[review_agent_name]
        assert "|domain:" in line, (
            f"Roster entry for {review_agent_name} missing |domain: field"
        )

    def test_roster_entry_has_wake_for_field(self, roster, review_agent_name):
        """Each roster entry should have a |wake-for: field."""
        line = roster[review_agent_name]
        assert "|wake-for:" in line, (
            f"Roster entry for {review_agent_name} missing |wake-for: field"
        )

    def test_every_team_agent_has_seeded_memory(self):
        for name in STANDARD_AGENTS:
            mem = CLAUDE_DIR / "framework" / "seed" / "agents" / name / "memory.md"
            assert mem.is_file(), f"no seeded memory for {name}"

    def test_no_duplicate_roster_entries(self):
        """No agent should appear twice in the roster."""
        path = SEED_SHARED / "roster.md"
        content = path.read_text(encoding="utf-8")
        names = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("→"):
                continue
            name = line.split("|")[0].strip()
            if name:
                names.append(name)
        seen = set()
        dupes = []
        for n in names:
            if n in seen:
                dupes.append(n)
            seen.add(n)
        assert not dupes, f"Duplicate roster entries: {dupes}"

    def test_roster_has_minimum_agents(self, roster):
        """Roster should have the specialists plus DA."""
        assert len(roster) >= 12, (
            f"Roster has {len(roster)} agents, expected >= 12"
        )


# ============================================================
# TestSharedInfrastructure — directives, decisions, patterns, etc.
# ============================================================

class TestSharedInfrastructure:
    """Validate cross-file reference integrity for shared team files."""

    def test_directives_exists(self):
        assert (FRAMEWORK_SHARED / "directives.md").exists(), (
            "directives.md missing from sigma-review shared"
        )

    @pytest.fixture(params=DIRECTIVES_REQUIRED_TERMS)
    def directive_term(self, request):
        return request.param

    def test_directives_has_key_section(self, directive_term):
        content = (FRAMEWORK_SHARED / "directives.md").read_text(encoding="utf-8")
        assert directive_term in content, (
            f"directives.md missing key term: {directive_term}"
        )

    def test_build_directives_exists(self):
        assert (FRAMEWORK_SHARED / "build-directives.md").exists(), (
            "build-directives.md missing from sigma-review shared"
        )

    def test_decisions_exists(self):
        assert (SEED_SHARED / "decisions.md").exists(), (
            "decisions.md missing from sigma-review shared"
        )

    def test_patterns_exists(self):
        assert (SEED_SHARED / "patterns.md").exists(), (
            "patterns.md missing from sigma-review shared"
        )

    def test_protocols_exists(self):
        assert (FRAMEWORK_SHARED / "protocols.md").exists(), (
            "protocols.md missing from sigma-review shared"
        )

    def test_roster_exists(self):
        assert (SEED_SHARED / "roster.md").exists(), (
            "roster.md missing from sigma-review shared"
        )

    def test_workspace_exists(self):
        assert (SEED_SHARED / "workspace.md").exists(), (
            "workspace.md missing from sigma-review shared"
        )

    def test_directives_not_empty(self):
        content = (FRAMEWORK_SHARED / "directives.md").read_text(encoding="utf-8")
        assert len(content.strip()) > 500, (
            "directives.md suspiciously short"
        )

    def test_build_directives_not_empty(self):
        content = (FRAMEWORK_SHARED / "build-directives.md").read_text(
            encoding="utf-8"
        )
        assert len(content.strip()) > 100, (
            "build-directives.md suspiciously short"
        )

    def test_decisions_has_markdown_structure(self):
        content = (SEED_SHARED / "decisions.md").read_text(encoding="utf-8")
        assert re.search(r"^#", content, re.MULTILINE), (
            "decisions.md has no markdown headers"
        )

    def test_patterns_has_markdown_structure(self):
        content = (SEED_SHARED / "patterns.md").read_text(encoding="utf-8")
        assert re.search(r"^#", content, re.MULTILINE), (
            "patterns.md has no markdown headers"
        )

    def test_special_agent_files_exist(self):
        """Special files that were excluded from standard validation should exist."""
        for name in SPECIAL_FILES:
            assert (AGENTS_DIR / name).exists(), (
                f"Special agent file missing: {name}"
            )

    def test_only_expected_agent_files_ship(self):
        """No agent definition outside the published set may ship."""
        shipped = {p.name for p in AGENTS_DIR.glob("*.md")}
        expected = {f"{a}.md" for a in STANDARD_AGENTS} | SPECIAL_FILES
        assert shipped == expected, (
            f"unexpected: {sorted(shipped - expected)}; missing: {sorted(expected - shipped)}"
        )


# ============================================================
# TestTemplateBootCanon — _template.md must match fleet Boot shape
# ============================================================

class TestTemplateBootCanon:
    """The template is the base for every dynamically-created agent (§2 phase-1).

    It diverged from the fleet once (79bbae5 removed the inbox boot step; the
    28 existing agents and these tests kept it) and the init-first fix later
    landed in the template without reaching the fleet. Both directions of
    template/fleet drift produced real review failures, so the canonical Boot
    sequence is pinned here explicitly.
    """

    CANON = [
        r"1→sigma-comm",
        r"2→memory",
        r"3→inbox",
        r"4→workspace",
        r"5→decisions",
        r"6→mcp__sigma-verify__init",
    ]

    def test_template_boot_matches_fleet_canon(self):
        content = (AGENTS_DIR / "_template.md").read_text(encoding="utf-8")
        boot = re.search(r"## Boot.*?\n## ", content, re.DOTALL)
        assert boot, "_template.md has no Boot section"
        text = boot.group(0)
        positions = []
        for pat in self.CANON:
            m = re.search(pat, text)
            assert m, f"_template.md Boot missing canonical step: {pat}"
            positions.append(m.start())
        assert positions == sorted(positions), (
            "_template.md Boot steps out of canonical order"
        )
