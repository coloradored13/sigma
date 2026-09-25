"""Tests for agent-calibration-tracker.py — PostToolUse hook on SendMessage."""
import sys
import json
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "hooks"))
import importlib
tracker = importlib.import_module("agent-calibration-tracker")


SAMPLE_AGENT_MESSAGE_RICH = """\
product-strategist: ✓ findings complete
F[competitive-landscape]: 5 major competitors identified |source:independent-research(WebSearch):T2(Gartner)|
F[market-entry]: Window closing, 12-18 months |source:agent-inference|
F1: Technology differentiation confirmed |source:independent-research(code-read):T1|
DA grade: B+
§2a outcome 2: positioning confirmed with acknowledged risk
XVERIFY[openai:gpt-4o] market sizing verified
Revised per DA challenge on timeline estimate
"""


class TestExtractAgentMetrics:
    def test_counts_findings(self):
        content = "F[market]: big\nF[tech]: fast\nfinding: third thing\nF1: fourth"
        metrics = tracker.extract_agent_metrics("test-agent", content)
        assert metrics["findings_count"] == 4

    def test_extracts_da_grade(self):
        content = "DA grade: B+\nSome other text"
        metrics = tracker.extract_agent_metrics("test-agent", content)
        assert metrics["da_grade"] == "B+"

    def test_extracts_engagement_grade(self):
        content = "engagement: A-\nSome other text"
        metrics = tracker.extract_agent_metrics("test-agent", content)
        assert metrics["da_grade"] == "A-"

    def test_counts_source_tiers(self):
        content = "|source:T1| and |source:T2| and |source:T3| and another :T1]"
        metrics = tracker.extract_agent_metrics("test-agent", content)
        assert metrics["source_t1"] == 2
        assert metrics["source_t2"] == 1
        assert metrics["source_t3"] == 1

    def test_detects_xverify(self):
        content = "XVERIFY[openai:gpt-4o] verified market size"
        metrics = tracker.extract_agent_metrics("test-agent", content)
        assert metrics["xverify_used"] is True
        assert metrics["xverify_result"] == "pass"

    def test_detects_xverify_fail(self):
        content = "XVERIFY-FAIL[openai:gpt-4o] could not verify"
        metrics = tracker.extract_agent_metrics("test-agent", content)
        assert metrics["xverify_used"] is True
        assert metrics["xverify_result"] == "fail"

    def test_detects_hygiene_completion(self):
        content = "§2a outcome 2: confirmed with risk"
        metrics = tracker.extract_agent_metrics("test-agent", content)
        assert metrics["hygiene_complete"] is True

    def test_detects_concession(self):
        content = "Revised per DA challenge on timeline"
        metrics = tracker.extract_agent_metrics("test-agent", content)
        assert metrics["concession"] is True

    def test_empty_content(self):
        metrics = tracker.extract_agent_metrics("test-agent", "")
        assert metrics["findings_count"] == 0
        assert metrics["da_grade"] is None
        assert metrics["xverify_used"] is False

    def test_none_content(self):
        metrics = tracker.extract_agent_metrics("test-agent", None)
        assert metrics["findings_count"] == 0

    def test_rich_message(self):
        metrics = tracker.extract_agent_metrics("product-strategist", SAMPLE_AGENT_MESSAGE_RICH)
        assert metrics["findings_count"] >= 3
        assert metrics["da_grade"] == "B+"
        assert metrics["source_t1"] >= 1
        assert metrics["source_t2"] >= 1
        assert metrics["xverify_used"] is True
        assert metrics["hygiene_complete"] is True
        assert metrics["concession"] is True


class TestWriteCalibration:
    def test_creates_calibration_file(self, tmp_path, monkeypatch):
        agent_dir = tmp_path / "agents" / "test-agent"
        agent_dir.mkdir(parents=True)
        monkeypatch.setattr(tracker, "AGENTS_DIR", tmp_path / "agents")
        monkeypatch.setattr(tracker, "TEAM_DIR", tmp_path / "team")

        metrics = {
            "agent": "test-agent",
            "timestamp": "2026-04-11 10:00",
            "findings_count": 3,
            "da_grade": "B+",
            "source_t1": 2, "source_t2": 1, "source_t3": 0,
            "xverify_used": True, "xverify_result": "pass",
            "hygiene_complete": True,
            "concession": False,
        }
        tracker.write_calibration(metrics)

        cal = agent_dir / "calibration.md"
        assert cal.exists()
        content = cal.read_text()
        assert "findings: 3" in content
        assert "da-grade: B+" in content
        assert "xverify: used (pass)" in content

    def test_skips_empty_metrics(self, tmp_path, monkeypatch):
        agent_dir = tmp_path / "agents" / "test-agent"
        agent_dir.mkdir(parents=True)
        monkeypatch.setattr(tracker, "AGENTS_DIR", tmp_path / "agents")
        monkeypatch.setattr(tracker, "TEAM_DIR", tmp_path / "team")

        metrics = {
            "agent": "test-agent",
            "timestamp": "2026-04-11 10:00",
            "findings_count": 0,
            "da_grade": None,
            "source_t1": 0, "source_t2": 0, "source_t3": 0,
            "xverify_used": False, "xverify_result": None,
            "hygiene_complete": False,
            "concession": False,
        }
        tracker.write_calibration(metrics)

        cal = agent_dir / "calibration.md"
        assert not cal.exists()

    def test_skips_agent_without_runtime_dir(self, tmp_path, monkeypatch):
        """Non-roster senders (no SIGMA_HOME/agents/{name}/) are skipped, not pooled
        into a shared log — the pooled fallback mixed unrelated sessions' messages."""
        monkeypatch.setattr(tracker, "AGENTS_DIR", tmp_path / "agents")  # no agent subdir
        team_dir = tmp_path / "team"
        monkeypatch.setattr(tracker, "TEAM_DIR", team_dir)

        metrics = {
            "agent": "nonexistent-agent",
            "timestamp": "2026-04-11 10:00",
            "findings_count": 2,
            "da_grade": "A",
            "source_t1": 1, "source_t2": 0, "source_t3": 0,
            "xverify_used": False, "xverify_result": None,
            "hygiene_complete": True,
            "concession": False,
        }
        tracker.write_calibration(metrics)

        assert not (team_dir / "calibration").exists()
        assert not (tmp_path / "agents" / "nonexistent-agent").exists()

    def test_writes_to_roster_agent_runtime_dir(self, tmp_path, monkeypatch):
        agents = tmp_path / "agents"
        (agents / "tech-architect").mkdir(parents=True)
        monkeypatch.setattr(tracker, "AGENTS_DIR", agents)
        monkeypatch.setattr(tracker, "TEAM_DIR", tmp_path / "team")
        metrics = {
            "agent": "tech-architect", "timestamp": "2026-04-11 10:00",
            "findings_count": 3, "da_grade": "B",
            "source_t1": 1, "source_t2": 1, "source_t3": 0,
            "xverify_used": True, "xverify_result": "pass",
            "hygiene_complete": True, "concession": True,
        }
        tracker.write_calibration(metrics)
        cal = agents / "tech-architect" / "calibration.md"
        assert cal.exists()
        assert "findings: 3" in cal.read_text()


class TestGenerateTrends:
    def test_trend_generation_with_enough_data(self, tmp_path):
        cal_file = tmp_path / "calibration.md"
        content = """\
# Calibration Log: test-agent

### 2026-04-09 10:00
findings: 3
da-grade: B
concession: no

### 2026-04-10 10:00
findings: 4
da-grade: B+
concession: yes

### 2026-04-11 10:00
findings: 5
da-grade: A-
concession: no
"""
        cal_file.write_text(content, encoding="utf-8")
        tracker.generate_trends(cal_file, content)

        result = cal_file.read_text()
        assert "### Trends" in result
        assert "avg-findings:" in result
        assert "concession-rate:" in result
