"""Protocol and mapping validation tests.

Validates ΣComm notation rules against the shipped protocol specs
(framework/agents/sigma-comm.md and SIGMA-COMM-SPEC.md) and roster
wake-for patterns in the seeded roster. These are drift-catching tests that
read the shipped files.
"""
import re
from collections import Counter
from pathlib import Path

import pytest

from conftest import get_infra_dir

CLAUDE_DIR = get_infra_dir()  # plugin root
AGENTS_DIR = CLAUDE_DIR / "framework" / "agents"
ROSTER_PATH = CLAUDE_DIR / "framework" / "seed" / "shared" / "roster.md"
SIGMA_COMM_AGENT = AGENTS_DIR / "sigma-comm.md"
SIGMA_COMM_SPEC = AGENTS_DIR / "SIGMA-COMM-SPEC.md"


# ---------- Constants ----------

VALID_STATUS_CODES = {"✓", "◌", "!", "?", "✗", "↻"}

VALID_BODY_SYMBOLS = {"|", ",", ">", "→", "+", "!"}

VALID_ENTRY_PREFIXES = {"C[]", "C~[]", "R[]", "P[]", "F[]", "¬[]", "D[]"}

# Regex for entry types as they appear inline: prefix + content
ENTRY_PATTERN = re.compile(
    r"(C\[|C~\[|R\[|P\[|F\[|¬\[|D\[)"
)

# YY.M.D date format -- e.g. 26.3.14, 26.12.1
DATE_PATTERN = re.compile(r"\b(\d{2}\.\d{1,2}\.\d{1,2})\b")

# Count format |N| or |N|YY.M
COUNT_PATTERN = re.compile(r"\|(\d+)\|")


# ---------- Helpers ----------

def read_file(path: Path) -> str:
    """Read a file and return its content, or empty string if missing."""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def parse_roster(content: str) -> list[dict]:
    """Parse roster.md entries.

    Returns list of dicts with keys: name, domain, wake_for
    """
    entries = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("→") or line.startswith("#"):
            continue
        # Format: name |domain: ... |wake-for: ...
        parts = line.split("|")
        if len(parts) < 3:
            continue
        name = parts[0].strip()
        domain_str = ""
        wake_for_str = ""
        for part in parts[1:]:
            part = part.strip()
            if part.startswith("domain:"):
                domain_str = part[len("domain:"):].strip()
            elif part.startswith("wake-for:"):
                wake_for_str = part[len("wake-for:"):].strip()
        if name:
            entries.append({
                "name": name,
                "domain": [d.strip() for d in domain_str.split(",") if d.strip()],
                "wake_for": [w.strip() for w in wake_for_str.split(",") if w.strip()],
            })
    return entries


# ================================================================
# TestSigmaCommNotation
# ================================================================

class TestSigmaCommNotation:
    """Parse and validate ΣComm format rules against real content."""

    # --- Status code validation ---

    @pytest.mark.parametrize("code", sorted(VALID_STATUS_CODES))
    def test_valid_status_codes_recognized(self, code):
        """Each defined status code should be in the valid set."""
        assert code in VALID_STATUS_CODES

    def test_invalid_status_code_detected(self):
        """A made-up status code should not be in the valid set."""
        invalid_codes = {"#", "&", "~", "X", "OK", "DONE"}
        for code in invalid_codes:
            assert code not in VALID_STATUS_CODES, f"'{code}' should not be a valid status code"

    def test_status_codes_in_workspace_sample(self):
        """Workspace sample content should only use valid status codes."""
        from conftest import SAMPLE_WORKSPACE_COMPLETE

        # Find status codes at line starts (after agent name prefix)
        status_pattern = re.compile(r":\s*([✓◌!?✗↻])\s")
        found = status_pattern.findall(SAMPLE_WORKSPACE_COMPLETE)
        assert len(found) > 0, "No status codes found in sample workspace"
        for code in found:
            assert code in VALID_STATUS_CODES, f"Invalid status code '{code}' in workspace sample"

    # --- Date format validation ---

    def test_date_format_yy_m_d_valid(self):
        """YY.M.D dates should match the expected pattern."""
        valid_dates = ["26.3.14", "26.12.1", "25.1.30", "27.11.15"]
        for date in valid_dates:
            assert DATE_PATTERN.search(date), f"Valid date '{date}' not matched"

    def test_date_format_rejects_wrong_format(self):
        """Non-YY.M.D dates should not match the pattern."""
        invalid = ["2026-03-14", "March 14, 2026", "3/14/26"]
        for date in invalid:
            match = DATE_PATTERN.fullmatch(date)
            assert match is None, f"Invalid date format '{date}' should not fullmatch"

    def test_count_format_pipe_n_pipe(self):
        """Count format |N| should be parseable."""
        test_strings = [
            "C[detects perf, honest>polish|3|26.3]",
            "C[probes|5|26.3]",
            "|10|",
        ]
        for s in test_strings:
            matches = COUNT_PATTERN.findall(s)
            assert len(matches) > 0, f"Count not found in '{s}'"
            for m in matches:
                assert m.isdigit(), f"Count '{m}' is not numeric"

    # --- Entry type validation ---

    def test_known_entry_prefixes_parsed(self):
        """All known entry types should match the entry pattern regex."""
        test_entries = [
            "C[detects perf, honest>polish|3|26.3]",
            "C~[prefers-TDD]",
            "R[api-latency-p99=120ms|src:grafana|26.4.1]",
            "P[distribution>technology-for-finserv-moat]",
            "F[26.3.12] r1: 10 findings(4H,2MH,4M)",
            "¬[developer(leader learning to build)]",
            "D[build-sequence]: waterfall+distribution=STAGGERED",
        ]
        for entry in test_entries:
            assert ENTRY_PATTERN.search(entry), f"Entry not matched: '{entry}'"

    def test_unknown_entry_prefix_not_matched(self):
        """An unknown prefix like Z[] should not match known entry types."""
        assert ENTRY_PATTERN.search("Z[something]") is None

    def test_anti_messages_documented(self):
        """Anti-messages (¬) should be documented in the protocol spec."""
        content = read_file(SIGMA_COMM_SPEC)
        assert "Anti-Messages" in content
        assert "¬[" in content

    @pytest.mark.parametrize("spec", [SIGMA_COMM_AGENT, SIGMA_COMM_SPEC], ids=lambda p: p.name)
    def test_body_symbols_documented_in_spec(self, spec):
        """All body notation symbols should be documented in the protocol specs."""
        content = read_file(spec)
        assert "Body Notation" in content
        # Check the body notation table has all symbols
        # Message body symbols (@ and ^ are memory-store notation, not message body)
        for symbol_desc in ["|", ",", ">", "→", "+", "!"]:
            assert symbol_desc in content, f"Body symbol '{symbol_desc}' not documented"

    @pytest.mark.parametrize("spec", [SIGMA_COMM_AGENT, SIGMA_COMM_SPEC], ids=lambda p: p.name)
    def test_mandatory_sections_documented(self, spec):
        """Mandatory sections (¬, →, #N) should be documented."""
        content = read_file(spec)
        assert "¬" in content, "¬ (NOT) section not documented"
        assert "→" in content, "→ (actions) section not documented"
        assert "#N" in content or "#count" in content, "#N (count) section not documented"


# ================================================================
# TestSigmaCommSpecFiles
# ================================================================

class TestSigmaCommSpecFiles:
    """Validate that the shipped ΣComm specs carry the protocol essentials."""

    @pytest.fixture(params=[SIGMA_COMM_AGENT, SIGMA_COMM_SPEC], ids=lambda p: p.name)
    def spec(self, request):
        return request.param

    def test_spec_file_exists(self, spec):
        assert spec.exists(), f"{spec.name} not found"

    def test_has_message_format_section(self, spec):
        assert "## Message Format" in read_file(spec)

    def test_has_status_codes_section(self, spec):
        assert "### Status Codes" in read_file(spec)

    def test_has_inbox_format(self, spec):
        assert "## Inbox Format" in read_file(spec)

    def test_has_workspace_format(self, spec):
        content = read_file(spec)
        assert "## Workspace Format" in content
        for section in ("## task", "## findings", "## convergence"):
            assert section in content, f"{spec.name} workspace format lacks {section}"

    def test_all_six_status_codes_listed(self, spec):
        """Each spec should list all 6 status codes."""
        content = read_file(spec)
        for code in VALID_STATUS_CODES:
            assert code in content, f"Status code '{code}' not found in {spec.name}"

    def test_three_tier_boundary_documented(self):
        """sigma-comm.md defines the Tier 1/2/3 boundary that phase-gate enforces."""
        content = read_file(SIGMA_COMM_AGENT)
        for tier in ("Tier 1", "Tier 2", "Tier 3"):
            assert tier in content, f"{tier} missing from sigma-comm.md"


# ================================================================
# TestRosterWakeForPatterns
# ================================================================

class TestRosterWakeForPatterns:
    """Validate roster pattern quality and consistency."""

    @pytest.fixture
    def roster(self):
        content = read_file(ROSTER_PATH)
        assert content, "seeded roster.md not found"
        return parse_roster(content)

    def test_roster_not_empty(self, roster):
        assert len(roster) > 0, "Roster has no entries"

    def test_wake_for_not_empty(self, roster):
        """Every roster entry should have at least one wake-for keyword."""
        empty = [e["name"] for e in roster if not e["wake_for"]]
        assert not empty, f"Agents with empty wake-for: {empty}"

    def test_domain_not_empty(self, roster):
        """Every roster entry should have at least one domain."""
        empty = [e["name"] for e in roster if not e["domain"]]
        assert not empty, f"Agents with empty domain: {empty}"

    def test_agent_names_valid_identifiers(self, roster):
        """Agent names should be lowercase with hyphens, no spaces."""
        pattern = re.compile(r"^[a-z][a-z0-9-]*$")
        invalid = [e["name"] for e in roster if not pattern.match(e["name"])]
        assert not invalid, f"Invalid agent names: {invalid}"

    def test_no_overbroad_wake_for_keywords(self, roster):
        """No single wake-for keyword should appear in more than 3 agents.

        Over-broad keywords defeat selective waking.
        """
        keyword_counts = Counter()
        for entry in roster:
            for kw in entry["wake_for"]:
                keyword_counts[kw] += 1
        overbroad = {kw: cnt for kw, cnt in keyword_counts.items() if cnt > 3}
        assert not overbroad, (
            f"Wake-for keywords in >3 agents (too broad): {overbroad}"
        )

    def test_devils_advocate_in_roster(self, roster):
        """DA should be present in the roster."""
        names = [e["name"] for e in roster]
        assert "devils-advocate" in names, "devils-advocate missing from roster"

    def test_roster_has_minimum_agents(self, roster):
        """Should have the 11 specialists plus DA on the roster."""
        assert len(roster) >= 12, f"Expected >=12 roster entries, got {len(roster)}"

    def test_every_roster_agent_has_definition(self, roster):
        missing = [e["name"] for e in roster if not (AGENTS_DIR / f"{e['name']}.md").exists()]
        assert not missing, f"Roster agents without definitions: {missing}"

    def test_wake_for_keywords_are_descriptive(self, roster):
        """Wake-for keywords should be multi-word or domain-specific, not single generic words."""
        too_short = []
        for entry in roster:
            for kw in entry["wake_for"]:
                # Single character or very generic single words are suspicious
                if len(kw) < 3:
                    too_short.append(f"{entry['name']}: '{kw}'")
        assert not too_short, f"Wake-for keywords too short/generic: {too_short}"
