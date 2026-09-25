#!/usr/bin/env python3
"""Prompt Echo Detector — PostToolUse hook on Write|Edit.

Detects when agents reproduce the user's prompt language instead of
independent analysis. Checks workspace writes against the prompt
decomposition (H[] claims). Flags medium+ echo levels.

Only fires during sigma-review R1 research phase. Max 2 flags per phase.
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
from difflib import SequenceMatcher


TEAM_DIR = sp.SHARED
WORKSPACE = TEAM_DIR / "workspace.md"
STATE_FILE = sp.STATE_DIR / ".echo-detect-count"

MAX_FLAGS = 2


def read_file(path):
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return ""


def extract_hypotheses(workspace_content):
    """Extract H[] claims from prompt-decomposition section."""
    # Find prompt-decomposition section
    match = re.search(
        r"##\s*prompt.?decomposition(.*?)(?=^## |\Z)",
        workspace_content,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return []

    section = match.group(1)
    hypotheses = []

    # Extract H[] entries
    for h_match in re.finditer(r"H\d+[:\s]+(.+?)(?:\n|$)", section):
        claim = h_match.group(1).strip()
        # Clean up claim text — remove test/verify prefixes
        claim = re.sub(r"^(?:test|verify|check)[:\s]*", "", claim, flags=re.IGNORECASE)
        if len(claim) > 10:  # Skip trivially short
            hypotheses.append(claim)

    return hypotheses


def extract_original_prompt(workspace_content):
    """Extract original user prompt from workspace."""
    match = re.search(
        r"##\s*(?:task|prompt|original)\s*\n+(.*?)(?=^## |\Z)",
        workspace_content,
        re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def normalize(text):
    """Normalize text for comparison: lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_echo_score(new_content, hypotheses, original_prompt):
    """Compute echo level between new content and prompt claims.

    Returns (score 0-100, list of echoed claims).
    """
    if not hypotheses and not original_prompt:
        return 0, []

    norm_content = normalize(new_content)
    if len(norm_content) < 50:
        return 0, []

    echoed_claims = []
    total_similarity = 0.0

    for i, hyp in enumerate(hypotheses, 1):
        norm_hyp = normalize(hyp)
        if len(norm_hyp) < 10:
            continue

        # Check for substring inclusion
        if norm_hyp in norm_content:
            echoed_claims.append(f"H{i}")
            total_similarity += 1.0
            continue

        # Check for high sequence similarity
        # Compare against sliding windows of similar length
        hyp_words = norm_hyp.split()
        content_words = norm_content.split()
        window_size = len(hyp_words)

        max_sim = 0.0
        for j in range(max(1, len(content_words) - window_size + 1)):
            window = " ".join(content_words[j:j + window_size])
            sim = SequenceMatcher(None, norm_hyp, window).ratio()
            max_sim = max(max_sim, sim)

        if max_sim > 0.6:
            echoed_claims.append(f"H{i}")
            total_similarity += max_sim

    # Also check against original prompt phrases (3+ word n-grams)
    if original_prompt:
        prompt_words = normalize(original_prompt).split()
        content_words_set = set(norm_content.split())
        ngram_matches = 0
        ngram_total = 0

        for n in range(3, min(7, len(prompt_words))):
            for i in range(len(prompt_words) - n + 1):
                ngram = " ".join(prompt_words[i:i + n])
                ngram_total += 1
                if ngram in norm_content:
                    ngram_matches += 1

        if ngram_total > 0:
            prompt_echo = ngram_matches / ngram_total
            total_similarity += prompt_echo * len(hypotheses) if hypotheses else prompt_echo

    # Normalize score
    denominator = len(hypotheses) if hypotheses else 1
    score = min(100, int(total_similarity / denominator * 100))

    return score, echoed_claims


def classify_echo(score):
    """Classify echo level."""
    if score < 20:
        return "low"
    elif score < 40:
        return "medium"
    else:
        return "high"


def get_flag_count():
    try:
        return int(STATE_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return 0


def increment_flag_count():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    count = get_flag_count() + 1
    STATE_FILE.write_text(str(count), encoding="utf-8")
    return count


def append_echo_flag(workspace_path, agent_name, phase, echo_level, score, echoed_claims, has_independent):
    """Append echo watch entry to workspace."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    claims_str = ", ".join(echoed_claims) if echoed_claims else "general prompt language"
    independent_str = "present" if has_independent else "absent"

    entry = f"""
## echo-watch ({agent_name}, {phase})
echo-level: {echo_level} ({score}%)
echoed-claims: {claims_str}
independent-sourcing: {independent_str}
-> {agent_name}: verify {claims_str} independently or mark as [prompt-claim:unverified]
"""

    with open(workspace_path, "a", encoding="utf-8") as f:
        f.write(entry)


def main():
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")

    # Quick exit: only watch workspace writes
    if "workspace" not in file_path.lower():
        sys.exit(0)

    # Quick exit: only during sigma-review
    workspace_content = read_file(WORKSPACE)
    if not workspace_content:
        sys.exit(0)

    # Only fire during R1 (research phase) — not R2+ where cross-referencing is expected
    if "## challenge" in workspace_content.lower() or "## circuit-breaker" in workspace_content.lower():
        sys.exit(0)

    # Rate limit
    if get_flag_count() >= MAX_FLAGS:
        sys.exit(0)

    # Get the content being written
    if tool_name == "Write":
        new_content = tool_input.get("content", "")
    else:
        new_content = tool_input.get("new_string", "")

    if not new_content or len(new_content) < 100:
        sys.exit(0)

    # Skip if content has explicit prompt-claim tags (proper handling)
    if "[prompt-claim]" in new_content:
        sys.exit(0)

    # Extract hypotheses and prompt
    hypotheses = extract_hypotheses(workspace_content)
    original_prompt = extract_original_prompt(workspace_content)

    if not hypotheses and not original_prompt:
        sys.exit(0)

    # Compute echo score
    score, echoed_claims = compute_echo_score(new_content, hypotheses, original_prompt)
    echo_level = classify_echo(score)

    # Only flag medium+
    if echo_level == "low":
        sys.exit(0)

    # Check for independent sourcing in the content
    has_independent = bool(re.search(
        r"\[independent.?research\]|source:.*T[12]|WebSearch|web.*search",
        new_content,
        re.IGNORECASE,
    ))

    # Try to identify agent name from content
    agent_match = re.search(r"^(\w[\w-]+):", new_content[:200])
    agent_name = agent_match.group(1) if agent_match else "unknown-agent"

    phase = "R1-research"

    append_echo_flag(WORKSPACE, agent_name, phase, echo_level, score, echoed_claims, has_independent)
    increment_flag_count()

    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
