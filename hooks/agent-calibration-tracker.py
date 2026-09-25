#!/usr/bin/env python3
"""Agent Calibration Tracker — PostToolUse hook on SendMessage.

Tracks per-agent performance across reviews: finding survival,
DA grades, concession patterns, source quality. Writes to
per-agent calibration files in agents/{name}/calibration.md.
"""
import json
import sys
import os
import re
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import sigma_paths as sp  # noqa: E402
from datetime import datetime


TEAM_DIR = sp.SHARED
# Per-agent runtime dirs (memory.md lives here). ~/.claude/agents holds flat .md
# definitions, not directories — pointing there made every entry fall back to a
# single shared log, mixed with messages from non-sigma sessions (fixed 26.9.25).
AGENTS_DIR = sp.SIGMA_HOME / "agents"


def extract_agent_metrics(agent_name, message_content):
    """Parse agent message content for trackable metrics."""
    metrics = {
        "agent": agent_name,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "findings_count": 0,
        "da_grade": None,
        "source_t1": 0,
        "source_t2": 0,
        "source_t3": 0,
        "xverify_used": False,
        "xverify_result": None,
        "hygiene_complete": False,
        "concession": False,
    }

    if not message_content:
        return metrics

    # Count findings (F[], finding patterns)
    metrics["findings_count"] = len(re.findall(r"F\[|finding|F\d+:", message_content, re.IGNORECASE))

    # DA grade
    grade_match = re.search(r"(?:DA|grade|engagement)[:\s]*([A-F][+-]?)", message_content)
    if grade_match:
        metrics["da_grade"] = grade_match.group(1)

    # Source tiers — match :T1, :T2, :T3 followed by any non-alphanumeric
    metrics["source_t1"] = len(re.findall(r":T1(?=[|\]\s(]|$)", message_content))
    metrics["source_t2"] = len(re.findall(r":T2(?=[|\]\s(]|$)", message_content))
    metrics["source_t3"] = len(re.findall(r":T3(?=[|\]\s(]|$)", message_content))

    # XVERIFY
    if re.search(r"XVERIFY", message_content):
        metrics["xverify_used"] = True
        if re.search(r"XVERIFY-FAIL", message_content):
            metrics["xverify_result"] = "fail"
        else:
            metrics["xverify_result"] = "pass"

    # Hygiene completion
    if re.search(r"§2[a-e].*outcome|outcome.*[123].*§2", message_content, re.IGNORECASE):
        metrics["hygiene_complete"] = True

    # Concession pattern
    if re.search(r"concede|accept.*challenge|revise.*(?:per|after).*DA", message_content, re.IGNORECASE):
        metrics["concession"] = True

    return metrics


def write_calibration(metrics):
    """Append calibration entry to agent's calibration.md."""
    agent_dir = AGENTS_DIR / metrics["agent"]
    if not agent_dir.is_dir():
        # Not a roster agent (no runtime dir): skip rather than pool unrelated
        # senders into a shared log.
        return

    cal_file = agent_dir / "calibration.md"

    # Read existing to check for trends
    existing = ""
    if cal_file.exists():
        existing = cal_file.read_text(encoding="utf-8")

    # Only write if we have substantive data (at least findings or a grade)
    if metrics["findings_count"] == 0 and not metrics["da_grade"]:
        return

    entry = f"""
### {metrics['timestamp']}
findings: {metrics['findings_count']}
da-grade: {metrics['da_grade'] or 'n/a'}
concession: {'yes' if metrics['concession'] else 'no'}
sources: T1:{metrics['source_t1']} T2:{metrics['source_t2']} T3:{metrics['source_t3']}
xverify: {'used' if metrics['xverify_used'] else 'skipped'}{f" ({metrics['xverify_result']})" if metrics['xverify_result'] else ''}
hygiene: {'complete' if metrics['hygiene_complete'] else 'incomplete'}
"""

    if not existing:
        existing = f"# Calibration Log: {metrics['agent']}\n"

    with open(cal_file, "a", encoding="utf-8") as f:
        f.write(entry)

    # Generate trends after 3+ entries
    entry_count = existing.count("###")
    if entry_count >= 2:  # This will be the 3rd+
        generate_trends(cal_file, existing + entry)


def generate_trends(cal_file, content):
    """Auto-generate trend summary at end of calibration file."""
    # Extract all findings counts
    findings = [int(x) for x in re.findall(r"findings:\s*(\d+)", content)]
    grades = re.findall(r"da-grade:\s*([A-F][+-]?)", content)
    concessions = re.findall(r"concession:\s*(yes|no)", content)

    if not findings:
        return

    avg_findings = round(sum(findings) / len(findings), 1)
    concession_rate = round(concessions.count("yes") / len(concessions) * 100) if concessions else 0

    # Grade trend (simple: compare last 3 to first 3)
    grade_map = {"A+": 13, "A": 12, "A-": 11, "B+": 10, "B": 9, "B-": 8,
                 "C+": 7, "C": 6, "C-": 5, "D+": 4, "D": 3, "D-": 2, "F": 1}
    grade_values = [grade_map.get(g, 0) for g in grades if g in grade_map]
    grade_trend = "stable"
    if len(grade_values) >= 4:
        first_half = sum(grade_values[:len(grade_values)//2]) / (len(grade_values)//2)
        second_half = sum(grade_values[len(grade_values)//2:]) / (len(grade_values) - len(grade_values)//2)
        if second_half > first_half + 1:
            grade_trend = "improving"
        elif second_half < first_half - 1:
            grade_trend = "declining"

    trend_section = f"""
### Trends (auto-generated, {len(findings)} entries)
avg-findings: {avg_findings}
concession-rate: {concession_rate}%
grade-trend: {grade_trend}
"""

    # Replace existing trends or append
    full_content = cal_file.read_text(encoding="utf-8")
    if "### Trends" in full_content:
        full_content = re.sub(
            r"### Trends.*?(?=\n### (?!Trends)|\Z)",
            trend_section.strip(),
            full_content,
            flags=re.DOTALL
        )
        cal_file.write_text(full_content, encoding="utf-8")
    else:
        with open(cal_file, "a", encoding="utf-8") as f:
            f.write(trend_section)


def main():
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    # Only process SendMessage PostToolUse events
    tool_name = data.get("tool_name", "")
    if "SendMessage" not in tool_name:
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    tool_response = data.get("tool_response", "")

    # Extract agent name from the message sender context
    # SendMessage tool_input typically has 'to' (recipient) and the message
    recipient = tool_input.get("to", tool_input.get("recipient", ""))
    message = tool_input.get("message", tool_input.get("content", ""))

    # We want to track the SENDER's metrics, but hook fires on the tool call
    # which means the caller is sending TO a recipient. The sender context
    # comes from the agent that made the call.
    # For lead→agent messages, we track the agent's response (in tool_response)
    # For agent→lead messages, the tool_input has the agent's findings

    # If response contains agent findings, track those
    response_text = str(tool_response) if tool_response else ""
    message_text = str(message) if message else ""

    # Try to identify the agent from the message content
    agent_match = re.search(r"^(\w[\w-]+):", message_text) or re.search(r"from[:\s]+(\w[\w-]+)", message_text, re.IGNORECASE)
    agent_name = agent_match.group(1) if agent_match else recipient

    if not agent_name:
        sys.exit(0)

    # Analyze the message content (combine input and response)
    combined = message_text + "\n" + response_text
    metrics = extract_agent_metrics(agent_name, combined)

    if metrics["findings_count"] > 0 or metrics["da_grade"]:
        write_calibration(metrics)

    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
