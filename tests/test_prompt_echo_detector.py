"""Tests for prompt-echo-detector.py — PostToolUse hook on Write|Edit."""
import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import importlib
echo = importlib.import_module("prompt-echo-detector")


WORKSPACE_WITH_DECOMPOSITION = """\
## prompt-decomposition
Q1: Who are the real competitors?
H1: Technology is the primary differentiator in payments API
H2: Private credit is the best entry point for new entrants
H3: Incumbents have aging technology stacks that are hard to modernize
C1: Scope is third-party payments APIs only

## task
Analyze the competitive landscape for payments API tooling
"""


class TestExtractHypotheses:
    def test_extracts_h_entries(self):
        hyps = echo.extract_hypotheses(WORKSPACE_WITH_DECOMPOSITION)
        assert len(hyps) == 3
        assert any("differentiator" in h.lower() for h in hyps)
        assert any("private credit" in h.lower() for h in hyps)
        assert any("aging" in h.lower() or "modernize" in h.lower() for h in hyps)

    def test_strips_test_verify_prefixes(self):
        content = "## prompt-decomposition\nH1: Test: whether technology matters\nH2: Verify: market size is correct\n"
        hyps = echo.extract_hypotheses(content)
        # Prefixes should be stripped
        for h in hyps:
            assert not h.lower().startswith("test:")
            assert not h.lower().startswith("verify:")

    def test_skips_short_claims(self):
        content = "## prompt-decomposition\nH1: short\nH2: This is a substantive claim about the market\n"
        hyps = echo.extract_hypotheses(content)
        assert len(hyps) == 1  # Only the substantive one

    def test_empty_workspace(self):
        assert echo.extract_hypotheses("") == []

    def test_no_decomposition_section(self):
        assert echo.extract_hypotheses("## other section\nstuff") == []


class TestExtractOriginalPrompt:
    def test_extracts_task(self):
        prompt = echo.extract_original_prompt(WORKSPACE_WITH_DECOMPOSITION)
        assert "competitive landscape" in prompt.lower()

    def test_empty_workspace(self):
        assert echo.extract_original_prompt("") == ""


class TestNormalize:
    def test_lowercases(self):
        assert echo.normalize("Hello WORLD") == "hello world"

    def test_strips_punctuation(self):
        assert echo.normalize("hello, world!") == "hello world"

    def test_collapses_whitespace(self):
        assert echo.normalize("hello   world") == "hello world"


class TestComputeEchoScore:
    def test_exact_echo_scores_high(self):
        hypotheses = ["Technology is the primary differentiator in payments API"]
        # Content that directly repeats the hypothesis
        content = "Our analysis confirms that technology is the primary differentiator in payments API. " * 3
        score, claims = echo.compute_echo_score(content, hypotheses, "")
        assert score >= 40  # High echo
        assert "H1" in claims

    def test_independent_content_scores_low(self):
        hypotheses = ["Technology is the primary differentiator"]
        # Content that discusses completely different topics
        content = (
            "The regulatory framework for banking charters requires a minimum capital reserve "
            "of $50 million. Market analysis of the Southeast Asian fintech landscape shows "
            "rapid growth in mobile payment adoption among rural populations over age 45."
        )
        score, claims = echo.compute_echo_score(content, hypotheses, "")
        assert score < 20  # Low echo
        assert len(claims) == 0

    def test_no_hypotheses_no_prompt(self):
        score, claims = echo.compute_echo_score("any content here", [], "")
        assert score == 0
        assert claims == []

    def test_short_content_ignored(self):
        score, claims = echo.compute_echo_score("short", ["hypothesis"], "")
        assert score == 0

    def test_prompt_ngram_echo(self):
        hypotheses = []
        prompt = "analyze the competitive landscape for payments API infrastructure"
        content = (
            "We need to analyze the competitive landscape for payments API infrastructure "
            "because the market is evolving rapidly and new entrants are emerging."
        )
        score, claims = echo.compute_echo_score(content, hypotheses, prompt)
        assert score > 0  # Should detect prompt language echo


class TestClassifyEcho:
    def test_low(self):
        assert echo.classify_echo(0) == "low"
        assert echo.classify_echo(19) == "low"

    def test_medium(self):
        assert echo.classify_echo(20) == "medium"
        assert echo.classify_echo(39) == "medium"

    def test_high(self):
        assert echo.classify_echo(40) == "high"
        assert echo.classify_echo(100) == "high"


class TestFlagCount:
    def test_starts_at_zero(self, tmp_path, monkeypatch):
        monkeypatch.setattr(echo, "STATE_FILE", tmp_path / ".count")
        assert echo.get_flag_count() == 0

    def test_increments(self, tmp_path, monkeypatch):
        state = tmp_path / "shared" / ".count"
        state.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(echo, "STATE_FILE", state)
        assert echo.increment_flag_count() == 1
        assert echo.increment_flag_count() == 2


class TestAppendEchoFlag:
    def test_writes_flag_to_workspace(self, tmp_path):
        ws = tmp_path / "workspace.md"
        ws.write_text("## task\nTest\n", encoding="utf-8")

        echo.append_echo_flag(ws, "product-strategist", "R1-research", "high", 65, ["H1", "H2"], False)

        content = ws.read_text()
        assert "echo-watch" in content
        assert "product-strategist" in content
        assert "high (65%)" in content
        assert "H1, H2" in content
        assert "independent-sourcing: absent" in content

    def test_independent_sourcing_present(self, tmp_path):
        ws = tmp_path / "workspace.md"
        ws.write_text("", encoding="utf-8")

        echo.append_echo_flag(ws, "agent", "R1-research", "medium", 25, ["H1"], True)

        content = ws.read_text()
        assert "independent-sourcing: present" in content
