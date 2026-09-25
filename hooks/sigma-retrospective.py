#!/usr/bin/env python3
"""Sigma-Review Retrospective — Stop hook.

Fires after every Stop event but emits at most ONCE per review.
Emits only when the review is finished: workspace `## status: archived` or a
chain-closure header (`## compilation-complete:`, `## synthesis-complete:`,
`## archive-complete:`). Emitting on the first convergence ✓ captured
half-finished reviews (26.9.24: one agent converged, xverify used:0).
Dedup is keyed by the workspace `## review-id:` / `## build-id:` (fallback: task
slug), NOT by date — a date-scoped key re-emitted the same finished review on
every later day it stayed the active workspace. Legacy `{date}:{slug}` keys
still count as done.

CB-fired detection reads the ## circuit-breaker section semantically, inverting
on "NOT triggered" / "not fired" / "not detected" rather than matching any
literal "circuit.?breaker" substring in the whole document.
"""
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import sigma_paths as sp  # noqa: E402


TEAM_DIR = sp.SHARED
WORKSPACE = TEAM_DIR / "workspace.md"
PATTERNS = TEAM_DIR / "patterns.md"
RETRO_STATE = sp.STATE_DIR / ".retro-last-hash"


def read_file(path):
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return ""


def extract_section(text, heading):
    """Extract content under a ## heading."""
    pattern = rf"^## {re.escape(heading)}$(.*?)(?=^## |\Z)"
    m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def count_pattern(text, pattern):
    return len(re.findall(pattern, text, re.IGNORECASE))


def slugify(text, max_len=50):
    """Lowercase, non-alphanum→dash, trim, truncate — used for dedup key."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s[:max_len]


def detect_cb_fired(content):
    """Semantic CB-fired detection from the ## circuit-breaker section.

    Reads the dedicated section and inverts on explicit negation rather than
    matching substring occurrences throughout the whole workspace. Fixes the
    26.4.16 R18 bug where "circuit breaker NOT triggered" was reported as fired.
    """
    cb_section = extract_section(content, "circuit-breaker")
    if not cb_section:
        return False
    if re.search(r"\bnot\s+(?:triggered|fired|detected|needed)\b",
                 cb_section, re.IGNORECASE):
        return False
    return bool(re.search(
        r"(?:CB|circuit[\s-]?breaker)\s*(?:was\s+)?(?:fired|triggered)"
        r"|herding\s+(?:detected|confirmed)",
        cb_section, re.IGNORECASE,
    ))


def get_workspace_status(content):
    """Return the value of `## status: <x>` header — 'active', 'archived', etc."""
    m = re.search(r"^##\s*status:\s*(\S+)", content, re.MULTILINE | re.IGNORECASE)
    return m.group(1).lower() if m else "unknown"


def load_state():
    """Load dedup state: {task_key: content_hash}. Migrates legacy single-hash."""
    raw = read_file(RETRO_STATE).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}  # legacy single-string hash format, discard


def save_state(state):
    RETRO_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def analyze_workspace(content):
    """Extract metrics from workspace content."""
    convergence = extract_section(content, "convergence")
    infrastructure = extract_section(content, "infrastructure")

    agents_converged = re.findall(r"^(\S+):\s*✓", convergence, re.MULTILINE)
    agents_timeout = re.findall(r"auto-shutdown", convergence, re.IGNORECASE)

    cb_fired = detect_cb_fired(content)

    outcome_1 = count_pattern(content, r"outcome.?1|revised from|CHECK CHANGES")
    outcome_2 = count_pattern(content, r"outcome.?2|confirmed.*risk|CHECK CONFIRMS")
    outcome_3 = count_pattern(content, r"outcome.?3|gap:|CHECK REVEALS")
    total_checks = outcome_1 + outcome_2 + outcome_3

    perfunctory_risk = "low"
    if total_checks > 0:
        confirm_ratio = outcome_2 / total_checks
        if confirm_ratio > 0.8:
            perfunctory_risk = "high"
        elif confirm_ratio > 0.6:
            perfunctory_risk = "medium"

    da_revisions = count_pattern(content, r"revised|changed|updated.*(?:after|following).*DA|challenge.?accepted")
    da_concessions = count_pattern(content, r"concede|accept.*challenge|acknowledge.*point")
    da_total = da_revisions + da_concessions
    revision_rate = round(da_revisions / da_total * 100) if da_total > 0 else 0
    concession_type = "genuine" if revision_rate > 40 else "performative" if da_total > 0 else "n/a"

    t1_count = count_pattern(content, r":T1(?=[|\]\s(]|$)")
    t2_count = count_pattern(content, r":T2(?=[|\]\s(]|$)")
    t3_count = count_pattern(content, r":T3(?=[|\]\s(]|$)")

    xverify_used = count_pattern(content, r"XVERIFY\[")
    xverify_failed = count_pattern(content, r"XVERIFY-FAIL")
    xverify_available = bool(re.search(
        r"ΣVerify.*available|sigma.?verify.*available",
        infrastructure, re.IGNORECASE,
    ))

    tier_match = re.search(r"TIER-(\d)", content)
    tier_assessed = int(tier_match.group(1)) if tier_match else 0

    task_match = re.search(r"##\s*task\s*\n+(.*?)(?:\n|$)", content, re.IGNORECASE)
    task_slug = task_match.group(1).strip()[:60] if task_match else "unknown"

    return {
        "task_slug": task_slug,
        "agents_converged": agents_converged,
        "agents_timeout": len(agents_timeout),
        "cb_fired": cb_fired,
        "outcome_1": outcome_1,
        "outcome_2": outcome_2,
        "outcome_3": outcome_3,
        "perfunctory_risk": perfunctory_risk,
        "revision_rate": revision_rate,
        "concession_type": concession_type,
        "t1": t1_count,
        "t2": t2_count,
        "t3": t3_count,
        "xverify_used": xverify_used,
        "xverify_failed": xverify_failed,
        "xverify_available": xverify_available,
        "tier_assessed": tier_assessed,
    }


def generate_recommendation(metrics):
    """One actionable suggestion based on metrics."""
    if metrics["perfunctory_risk"] == "high":
        return "High outcome-2 ratio — checks may be rubber-stamping. DA should probe specifics."
    if metrics["concession_type"] == "performative" and metrics["revision_rate"] < 20:
        return "DA challenges producing low revision rate — challenges may be formulaic or agents conceding without changing."
    if metrics["t3"] > metrics["t1"] + metrics["t2"]:
        return "T3 sources dominate — push agents toward T1/T2 primary sources for load-bearing findings."
    if metrics["xverify_available"] and metrics["xverify_used"] == 0:
        return "ΣVerify available but unused — check if agents are skipping cross-model verification."
    if len(metrics["agents_converged"]) <= 2:
        return "Low agent convergence count — check if agents are stalling or timing out."
    if not metrics["cb_fired"] and len(metrics["agents_converged"]) > 3:
        return "No circuit breaker with 4+ agents — verify genuine divergence exists (not just surface-level agreement)."
    return "Review metrics within normal ranges — no immediate action."


def write_retro(metrics):
    """Append retrospective to patterns.md."""
    date = datetime.now().strftime("%Y-%m-%d")
    review_num_match = re.search(r"R(\d+)", read_file(PATTERNS))
    last_num = int(review_num_match.group(1)) if review_num_match else 0
    review_num = last_num + 1

    agents_str = ", ".join(metrics["agents_converged"]) if metrics["agents_converged"] else "none detected"
    recommendation = generate_recommendation(metrics)

    entry = f"""
## Retro: R{review_num} — {metrics['task_slug']} ({date})
value: {agents_str} converged ({metrics['agents_timeout']} timeouts)
herding: {'CB fired' if metrics['cb_fired'] else 'not detected'}, CB fired: {'yes' if metrics['cb_fired'] else 'no'}
hygiene: outcome-1: {metrics['outcome_1']}, outcome-2: {metrics['outcome_2']}, outcome-3: {metrics['outcome_3']} — perfunctory risk: {metrics['perfunctory_risk']}
da-effectiveness: revision-rate: {metrics['revision_rate']}%, concession-type: {metrics['concession_type']}
sources: T1:{metrics['t1']} T2:{metrics['t2']} T3:{metrics['t3']}
xverify: used:{metrics['xverify_used']} failed:{metrics['xverify_failed']} available:{'yes' if metrics['xverify_available'] else 'no'}
complexity: tier-assessed: {metrics['tier_assessed']}
-> recommendation: {recommendation}
"""

    with open(PATTERNS, "a", encoding="utf-8") as f:
        f.write(entry)


_COMPLETION_HEADER_RE = re.compile(
    r"^##\s*(?:compilation-complete|synthesis-complete|archive-complete):",
    re.MULTILINE | re.IGNORECASE,
)


def should_emit(content):
    """Gate: only emit at review completion, not on every intermediate Stop.

    Completion = workspace ## status is archived OR a chain-closure header
    exists. Convergence ✓ alone is NOT completion — agents converge one at a
    time during R1, so that trigger recorded partial metrics.
    """
    status = get_workspace_status(content)
    return status == "archived" or bool(_COMPLETION_HEADER_RE.search(content))


def review_key(content, task_slug):
    """Stable identity for dedup: review-id, else build-id, else task slug."""
    for header in ("review-id", "build-id"):
        m = re.search(rf"^##\s*{header}:\s*(\S+)", content, re.MULTILINE | re.IGNORECASE)
        if m:
            return f"{header}:{m.group(1)}"
    return f"task:{slugify(task_slug)}"


def already_retrod(state, key, task_slug):
    """True if this review was retro'd under the current or legacy key scheme."""
    if key in state:
        return True
    legacy_suffix = f":{slugify(task_slug)}"
    return any(
        re.match(r"^\d{4}-\d{2}-\d{2}:", k) and k.endswith(legacy_suffix)
        for k in state
    )


def main():
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        data = {}

    if data.get("hook_event_name") != "Stop":
        sys.exit(0)

    workspace_content = read_file(WORKSPACE)
    if not workspace_content:
        sys.exit(0)

    if not should_emit(workspace_content):
        sys.exit(0)

    metrics = analyze_workspace(workspace_content)
    task_key = review_key(workspace_content, metrics["task_slug"])

    state = load_state()
    convergence = extract_section(workspace_content, "convergence")
    content_hash = hashlib.sha256(convergence.encode()).hexdigest()[:16]
    if already_retrod(state, task_key, metrics["task_slug"]):
        sys.exit(0)  # already retro'd this review

    write_retro(metrics)
    state[task_key] = content_hash
    save_state(state)

    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
