#!/usr/bin/env python3
"""Phase Gate — minimal PreToolUse + PostToolUse hook for atomic checklist model.

Replaces phase-compliance-enforcer.py (841 lines → ~120 lines).

HARD BLOCKS (PreToolUse exit code 2):
  1. Code write authorization — default-deny on Write/Edit to code files
     during BUILD sessions unless workspace contains plan-lock evidence (ADR/IC).
  2. Git commit gate — blocks git commit/push unless chain-evaluator reports
     complete (reads .chain-status.json).
  3. Pre-shutdown promotion gate — blocks SendMessage shutdown_request
     unless workspace has promotion + contamination + sycophancy sections.
  4. sed -i workspace/hooks scope — blocks sed -i on workspace.md, shared/
     workspace files, or /.claude/hooks/ paths. Uses shlex.split() argv
     tokenization (CAL[4]) — not raw regex. Backup-extension forms
     (-i.bak, -i '' + path) are permitted (they write to separate files).
  5. 06b pre-archive compilation gate — blocks archive operations unless
     workspace contains `## compilation-complete: [R-{review-id}]` header.
     Manual-override recovery: `## compilation-complete: [R-{id}, manual-override,
     reason: {reason}]`. Per ADR[6]/IC[6] (plan §P2.A row 119: BLOCK day-1).

SOFT WARNS (PostToolUse systemMessage):
  6. Context firewall — warns when personal context detected in workspace writes.

Everything else (phase skip, DA exit-gate, BELIEF-on-advance, CB evidence,
synthesis write, SendMessage dispatch) is handled by the chain-evaluator.py
Stop hook which evaluates completeness at session end.
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent))
import sigma_paths as sp  # noqa: E402


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CHAIN_STATUS_FILE = sp.STATE_DIR / ".chain-status.json"
DEFAULT_WORKSPACE = sp.WORKSPACE
BUILDS_DIR = sp.BUILDS_DIR

# BLOCK 5 / IC[6] multi-path scan (R2 fix, 2026-05-02):
# Build sessions write the override header to builds/{id}/c{N}-scratch.md per
# directives.md §8f BUILD variant. Sessions are considered "active" if their
# scratch file was modified within this window — older scratch files are
# treated as historical/archived and do NOT classify the current session as
# in-sigma (FP guard against stale workspace.md, which used to misfire when
# the only signal was an 8-day-old DEFAULT_WORKSPACE file).
_FRESH_SESSION_WINDOW_SECONDS = 7 * 24 * 60 * 60

# Paths that are always writable (infrastructure, not code)
INFRASTRUCTURE_PATH_MARKERS = [
    "/.claude/teams/",
    "/.claude/plans/",
    "/.claude/memory/",
    "/.claude/projects/",
    "/.claude/hooks/",
    "/.claude/skills/",
    "/.claude/agents/",
    "/.claude/cache/",
    "/tmp/",
]

# Personal context keywords for firewall detection
CONTEXT_FIREWALL_KEYWORDS = [
    r"\bmy career\b", r"\bmy role\b", r"\bmy experience\b",
    r"\bmy salary\b", r"\bmy family\b", r"\bmy job\b",
    r"\bI should\b.*(?:career|job|position|role)",
    r"\bpersonally I\b",
]

# ---------------------------------------------------------------------------
# ΣComm Tier-2 enforcement (per CLAUDE.md three-tier boundary)
# ---------------------------------------------------------------------------
# Tier 2 = workspace findings + agent inbox messages. Required tags on finding
# blocks: |source:|, severity (HIGH/MEDIUM/LOW), and a status verb. Identifier-
# gated: only blocks containing DA[#N]/IC[N]/ADR[N]/etc. trigger the check.

SIGMACOMM_CALIBRATION_LOG = sp.STATE_DIR / "sigmacomm-calibration.jsonl"

FINDING_ID_RE = re.compile(
    r"\b(?:DA|PA|IC|ADR|BC|PM|SQ|H|F|R|D|C|RC)\[#?[\w\-.]+\]"
)
SOURCE_RE = re.compile(r"\|source:[^|\n]+\|", re.IGNORECASE)
STATUS_VERB_RE = re.compile(
    r"\b(VERIFIED|CONVERGED|RESTATE|WITHDRAWN|PASS|FAIL|PENDING|"
    r"CONFIRMED|RESOLVED|BLOCKING|CRITICAL|HIGH|MEDIUM|LOW)\b"
)

_TIER2_PATH_RES = [
    re.compile(r"/workspace\.md$"),
    re.compile(r"/c\d+-scratch\.md$"),
    re.compile(r"/c\d+-plan\.md$"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_fresh(path: Path) -> bool:
    """Return True if ``path`` was modified within the active-session window."""
    try:
        mtime = path.stat().st_mtime
    except (FileNotFoundError, OSError):
        return False
    import time
    return (time.time() - mtime) <= _FRESH_SESSION_WINDOW_SECONDS


def _has_session_markers(path: Path) -> bool:
    """Return True if ``path`` contains ## task or ## mode session markers."""
    try:
        content = path.read_text(encoding="utf-8").lower()
    except (FileNotFoundError, OSError):
        return False
    return "## task" in content or "## mode" in content


def _iter_active_build_scratches():
    """Yield build scratch files (Path) that look active.

    A scratch is "active" when its mtime is within the freshness window AND
    it contains ## task or ## mode markers. Pre-existing builds with stale
    mtimes are skipped (FP guard).
    """
    if not BUILDS_DIR.is_dir():
        return
    try:
        candidates = sorted(BUILDS_DIR.glob("*/c*-scratch.md"))
    except OSError:
        return
    for scratch in candidates:
        if _is_fresh(scratch) and _has_session_markers(scratch):
            yield scratch


def _build_id_from_archive_path(archive_path: str) -> str | None:
    """Extract build-id from an archive write path, if shaped like
    ``shared/archive/{build-id}-{suffix}.md``.

    Returns the {build-id} portion or None if the path doesn't fit the shape.
    Used to prefer the matching build's scratch when scanning for an override
    header.
    """
    if not archive_path:
        return None
    name = os.path.basename(archive_path)
    # Strip leading ".md" / extensions and a trailing -synthesis / -workspace
    # variant; keep the date+task-slug prefix.
    stem = name
    if stem.endswith(".md"):
        stem = stem[:-3]
    for suffix in ("-synthesis", "-workspace", "-summary"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem or None


def _is_sigma_session() -> bool:
    """Check if any sigma session is currently active.

    R2 multi-path fix (2026-05-02): considers DEFAULT_WORKSPACE AND any
    fresh build scratch under BUILDS_DIR. Either a fresh workspace.md with
    session markers OR a fresh c{N}-scratch.md with session markers
    classifies the session as in-sigma. This closes the directive↔hook gap
    where BUILD-track sessions wrote override headers to scratch files the
    hook never read.
    """
    if _is_fresh(DEFAULT_WORKSPACE) and _has_session_markers(DEFAULT_WORKSPACE):
        return True
    for _ in _iter_active_build_scratches():
        return True
    return False


def _is_build_session() -> bool:
    """Check if current workspace is a BUILD session."""
    try:
        content = DEFAULT_WORKSPACE.read_text(encoding="utf-8")
        return "mode: BUILD" in content or "mode: build" in content
    except (FileNotFoundError, OSError):
        return False


def _workspace_has_plan_lock() -> bool:
    """Check if workspace contains plan-lock evidence (ADR/IC sections populated)."""
    try:
        content = DEFAULT_WORKSPACE.read_text(encoding="utf-8")
        has_adr = bool(re.search(r"ADR\[\d+\]", content))
        has_ic = bool(re.search(r"IC\[\d+\]", content))
        return has_adr and has_ic
    except (FileNotFoundError, OSError):
        return False


def _chain_is_complete() -> bool:
    """Check if the chain-evaluator last reported complete.

    Also returns True if the ONLY failing item is A14 (git clean) —
    since the commit IS the action that satisfies A14, blocking commit
    on A14 creates a circular dependency.
    """
    try:
        data = json.loads(CHAIN_STATUS_FILE.read_text())
        if data.get("last_complete", False):
            return True
        # A14-only exception: if the only failure is git clean, allow commit
        failed = data.get("failed_items", {})
        if failed and all(k == "A14" for k in failed):
            return True
        return False
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return False


def _workspace_section_has_content(section_name: str) -> bool:
    """Check if a workspace ## section has non-empty content."""
    try:
        content = DEFAULT_WORKSPACE.read_text(encoding="utf-8")
        pattern = rf"^## {re.escape(section_name)}\s*\n(.*?)(?=^## |\Z)"
        m = re.search(pattern, content, re.MULTILINE | re.DOTALL)
        if not m:
            return False
        section_content = m.group(1).strip()
        return len(section_content) > 0
    except (FileNotFoundError, OSError):
        return False


# ---------------------------------------------------------------------------
# BLOCK 1: Code write authorization
# ---------------------------------------------------------------------------

def check_code_write_authorization(file_path: str) -> tuple[bool, str]:
    """BLOCK Write/Edit to code files in BUILD sessions without plan-lock evidence.

    In the atomic checklist model, this replaces the phase-based authorization.
    Code writes are blocked unless the workspace contains ADR[] and IC[] entries
    (evidence that a plan was locked before implementation started).
    Infrastructure paths are always writable.
    """
    if not _is_build_session():
        return False, ""  # Not a BUILD session — no restriction

    if _workspace_has_plan_lock():
        return False, ""  # Plan is locked — code writes authorized

    # Allow infrastructure writes in any state
    for marker in INFRASTRUCTURE_PATH_MARKERS:
        if marker in file_path:
            return False, ""

    basename = os.path.basename(file_path)
    return True, (
        f"CODE WRITE BLOCKED: Write/Edit to '{basename}' denied — "
        f"workspace does not contain plan-lock evidence (ADR[] + IC[]). "
        f"Lock the plan before writing code. "
        f"Infrastructure paths (/.claude/*, /tmp/*) are always writable."
    )


# ---------------------------------------------------------------------------
# BLOCK 2: Git commit gate
# ---------------------------------------------------------------------------

def check_premature_git_operation(command: str) -> tuple[bool, str]:
    """BLOCK git commit/push unless chain-evaluator reports complete.

    Irreversible action protection. In the atomic checklist model, git operations
    are blocked until the chain is complete — not until specific phases finish.
    Only applies during active sigma sessions (workspace has ## task or ## mode).
    """
    if not re.search(r'\bgit\s+(commit|push)\b', command):
        return False, ""

    # Only enforce during active sigma sessions
    if not _is_sigma_session():
        return False, ""

    if _chain_is_complete():
        return False, ""

    return True, (
        "GIT OPERATION BLOCKED: Cannot run git commit/push — "
        "chain evaluation is not complete. Run 'python3 ~/.claude/teams/sigma-review/bin/chain-evaluator.py evaluate' "
        "to check status. Complete all chain items before committing."
    )


# ---------------------------------------------------------------------------
# BLOCK 3: Pre-shutdown promotion gate
# ---------------------------------------------------------------------------

def check_premature_shutdown(tool_input: dict) -> tuple[bool, str]:
    """BLOCK SendMessage shutdown_request unless promotion round is complete.

    Prevents the recipe skip where lead sends shutdown before chain closure
    (promotion, compilation, sync) is done. The visible deliverable (synthesis)
    is not the full deliverable — the completed chain is.
    """
    # Only check SendMessage with shutdown_request
    message = tool_input.get("message", "")
    if isinstance(message, str):
        return False, ""  # Plain text message, not a shutdown request
    if not isinstance(message, dict):
        return False, ""
    if message.get("type") != "shutdown_request":
        return False, ""  # Not a shutdown request

    # Only enforce during active sigma sessions
    if not _is_sigma_session():
        return False, ""

    missing = []
    if not _workspace_section_has_content("promotion"):
        missing.append("## promotion (run promotion round)")
    if not _workspace_section_has_content("contamination-check"):
        missing.append("## contamination-check (run pre-synthesis checks)")
    if not _workspace_section_has_content("sycophancy-check"):
        missing.append("## sycophancy-check (run pre-synthesis checks)")

    if missing:
        return True, (
            "SHUTDOWN BLOCKED: Chain closure incomplete. "
            f"Missing sections: {', '.join(missing)}. "
            "Complete the full recipe (promotion, pre-synthesis checks) "
            "before sending shutdown requests. The synthesis document is "
            "one step in the recipe, not the deliverable."
        )

    return False, ""


# ---------------------------------------------------------------------------
# BLOCK 4: sed -i on workspace + /.claude/hooks/ (ADR[SS-1] + IC[1] + CAL[4])
# ---------------------------------------------------------------------------

# Path substrings that trigger the sed-i block. Match is substring-based
# so relative paths, absolute paths, and ~ expansions all hit the gate.
SED_I_PROTECTED_PATHS = [
    "workspace.md",
    "/.claude/teams/sigma-review/shared/",
    "/.claude/teams/sigma-optimize/shared/",
    "/.claude/hooks/",
    "/.claude/plugins/",
    "/sigma-review/shared/",  # catches non-absolute path forms
    "/sigma-optimize/shared/",
]


def _sed_i_flag_has_backup(flag_token: str, next_token: str | None) -> bool:
    """Decide whether a sed -i invocation uses a backup-extension form.

    Conservative: only the ``-i<SUFFIX>`` joined form with a non-empty
    suffix is treated as a backup form. The separated ``-i '' file`` form
    is equivalent to in-place-no-backup on BSD sed (the empty string is
    the suffix) and is BLOCKED to stay safe across platforms. Likewise
    the bare ``-i`` flag (GNU form without suffix) is BLOCKED.

    CAL[4] note: backup-extension forms pass. We read that narrowly —
    the backup must be a real suffix, not an empty string, to count.
    """
    # Joined form: -i.bak, -iBACKUP
    if flag_token.startswith("-i") and len(flag_token) > 2:
        return True
    # Any other shape (-i alone, --in-place alone) is blocked
    return False


def check_sed_in_place(command: str) -> tuple[bool, str]:
    """BLOCK sed -i on workspace paths or /.claude/hooks/.

    Uses shlex.split() to tokenize argv — resistant to raw-regex bypass
    via env wrappers, shell quoting, and variable expansion within the
    argument list that resolves at parse time.

    Backup-extension forms (``sed -i.bak``) pass per CAL[4] rationale:
    a real suffix produces a recoverable .bak copy on both GNU and BSD
    sed. In-place-no-backup forms (``sed -i``, ``sed -i ''``, ``sed
    --in-place``) are blocked — those are the R19 silent-overwrite
    shapes that cause data loss under concurrent workspace writes.

    Scope (CAL[4]): workspace.md, teams/sigma-review/shared/, teams/
    sigma-optimize/shared/, and /.claude/hooks/. Tool calls outside
    these scopes are never blocked.

    KNOWN LIMITATION (ADR[SS-1] shlex.split argv scope):
    Paths supplied to sed via stdin — e.g. ``echo PATH | xargs sed -i
    'pattern'`` — are NOT visible to an argv scanner. They exist only
    at runtime, after this hook has decided. The following forms
    therefore bypass this check and could overwrite a protected path:

      - ``echo ~/.claude/teams/.../workspace.md | xargs sed -i 's/a/b/'``
      - ``find . -name '*.md' | xargs sed -i 's/a/b/'``
      - ``cat filelist.txt | xargs -n1 sed -i 's/a/b/'``

    Forms where the path IS in argv — including ``xargs -I{}`` with a
    literal operand after sed, ``env FOO=bar sed -i path``, and
    ``/abs/path/to/sed -i workspace.md`` — remain covered.

    Closing the stdin-piped gap requires runtime interception (a sed
    shim, a PreToolUse that re-parses stdin at exec time, or an OS
    monitor), all of which were explicitly out of ADR[SS-1] scope.
    If empirical incidents surface, a new SQ with ADR can address it.
    The CQA evasion-matrix test suite documents the bypass forms
    against this docstring (see ``test_phase_gate.py`` — xargs-stdin
    cases are marked as known-gap rather than removed so the contract
    is inspectable from the test side as well).
    """
    # Fast-path: no sed in the command at all
    if "sed" not in command:
        return False, ""

    # Tokenize. Raw regex can be fooled by quoting tricks — shlex
    # matches shell argv parsing (IC[1]).
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        # Malformed command (unbalanced quotes). Don't block on parse
        # error — let the shell fail naturally.
        return False, ""

    # Walk tokens looking for a sed invocation. Covers wrappers like
    # `env FOO=bar sed ...` and `xargs -I{} sed ... {}` where the sed
    # token appears literally in argv. Does NOT cover stdin-piped
    # forms (`echo path | xargs sed -i ...`) — those paths aren't in
    # argv, so the scanner cannot see them. See docstring KNOWN
    # LIMITATION block.
    n = len(tokens)
    for i, tok in enumerate(tokens):
        if tok != "sed" and not tok.endswith("/sed"):
            continue

        # Collect flags + operands for this sed invocation. Stop at
        # shell separators — they terminate the current command.
        invocation = []
        j = i + 1
        while j < n and tokens[j] not in (";", "&&", "||", "|", "&"):
            invocation.append(tokens[j])
            j += 1

        # Find the -i flag (if any)
        i_flag_idx = None
        for k, t in enumerate(invocation):
            if t == "-i" or t.startswith("-i") or t == "--in-place":
                # Must be a real flag, not a file that happens to start
                # with "-i" (unlikely but shlex.split preserves it).
                # Only treat tokens starting with "-" as flags.
                if t.startswith("-"):
                    i_flag_idx = k
                    break

        if i_flag_idx is None:
            continue  # no -i flag on this sed call — not our concern

        flag_tok = invocation[i_flag_idx]
        next_tok = invocation[i_flag_idx + 1] if i_flag_idx + 1 < len(invocation) else None

        if _sed_i_flag_has_backup(flag_tok, next_tok):
            continue  # backup form — permitted per CAL[4]

        # Check operand paths against protected scope. Operands are
        # all non-flag tokens after the -i flag.
        operands = [t for t in invocation[i_flag_idx + 1 :] if not t.startswith("-")]
        for path in operands:
            for marker in SED_I_PROTECTED_PATHS:
                if marker in path:
                    return True, (
                        f"SED IN-PLACE BLOCKED: 'sed -i' (no backup suffix) on "
                        f"protected path '{path}' denied. In-place edits without a "
                        f"backup extension cause silent overwrites under concurrent "
                        f"workspace writes (R19 data-loss incident). Use one of:\n"
                        f"  - sed -i.bak 'pattern' <file>  (creates backup, recoverable)\n"
                        f"  - Edit tool (atomic, no concurrency race)\n"
                        f"  - workspace_write() helper (atomic Python replace, IC[6])\n"
                        f"Protected scope: workspace.md, teams/sigma-*/shared/, /.claude/hooks/."
                    )

    return False, ""


# ---------------------------------------------------------------------------
# BLOCK 5: 06b pre-archive compilation gate (ADR[6] / IC[6])
#
# Per plan §P2.A row 119 (BLOCK day-1, ¬WARN). Blocks archive operations
# unless the workspace contains `## compilation-complete: [R-{review-id}]`
# header. Manual-override recovery form is also accepted.
# ---------------------------------------------------------------------------

# IC[6]: header detection regex
_COMPILATION_COMPLETE_RE = re.compile(
    r"^## compilation-complete: \[R-([^,\]]+)(?:, manual-override, reason: ([^\]]+))?\]$",
    re.MULTILINE,
)

# Archive operations to intercept. Bash commands matching these patterns
# are pre-archive moves; Write/Edit to paths under archive/ are also gated.
_ARCHIVE_PATH_MARKERS = [
    "/.claude/teams/sigma-review/shared/archive/",
    "/.claude/teams/sigma-build/shared/archive/",
    "/.claude/teams/sigma-optimize/shared/archive/",
    "/sigma-review/shared/archive/",
    "/sigma-build/shared/archive/",
]
_ARCHIVE_BASH_RE = re.compile(
    r"\b(?:cp|mv|cat\s+>>|tee)\b.*?(?:" + "|".join(re.escape(m) for m in _ARCHIVE_PATH_MARKERS) + ")",
    re.IGNORECASE,
)


def _scan_for_compilation_header(path: Path) -> tuple[bool, str | None, bool]:
    """Scan a single file for the compilation-complete header.

    Returns (has_header, review_id, is_manual_override).
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return False, None, False
    m = _COMPILATION_COMPLETE_RE.search(content)
    if not m:
        return False, None, False
    return True, m.group(1).strip(), m.group(2) is not None


def _has_compilation_complete(archive_path: str | None = None) -> tuple[bool, str | None, bool]:
    """Check if any active workspace has `## compilation-complete: [R-{id}]`.

    R2 multi-path fix (2026-05-02): scans DEFAULT_WORKSPACE first (preserves
    prior behavior), then build scratch files. When ``archive_path`` is
    supplied and shaped like ``shared/archive/{build-id}-{suffix}.md``, the
    matching ``builds/{build-id}/c*-scratch.md`` files are preferred —
    closing the directive↔hook gap where BUILD-track sessions wrote the
    override header to scratch files the hook never read.

    R2 micro-fix (TA CONCERN-1, 2026-05-02): when ``archive_path`` yields a
    derivable preferred build-id AND that build's directory exists, the
    answer is the preferred build's verdict — pass or fail. We do NOT
    fall through to a broad-glob scan over OTHER builds' scratches in
    that case, because doing so allows build A's compilation-complete
    header to authorize an archive write targeting build B (cross-build
    authorization bypass). The broad-glob fallback only fires when
    preferred-build derivation FAILED (no archive_path, or archive_path
    doesn't fit the ``{build-id}-{suffix}.md`` shape, or BUILDS_DIR/
    {build-id}/ doesn't exist).

    Returns (has_header, review_id, is_manual_override). The first match
    wins; later matches are not consulted.
    """
    # 1) DEFAULT_WORKSPACE (canonical location for ANALYZE-track sessions).
    found, rid, mo = _scan_for_compilation_header(DEFAULT_WORKSPACE)
    if found:
        return True, rid, mo

    # 2) Prefer the build that matches the archive path being written, if
    #    we can derive a build-id from it.
    preferred_build = _build_id_from_archive_path(archive_path) if archive_path else None
    if preferred_build:
        preferred_dir = BUILDS_DIR / preferred_build
        if preferred_dir.is_dir():
            try:
                preferred_scratches = sorted(preferred_dir.glob("c*-scratch.md"))
            except OSError:
                preferred_scratches = []
            for scratch in preferred_scratches:
                found, rid, mo = _scan_for_compilation_header(scratch)
                if found:
                    return True, rid, mo
            # R2 micro-fix: preferred build resolved AND directory exists,
            # but no override header found in any of its scratches — the
            # answer is False. Do NOT fall through to broad-glob over
            # other builds (cross-build authorization bypass guard).
            return False, None, False

    # 3) Fallback: scan every active build scratch. Only reached when
    #    preferred-build derivation failed (no archive_path, unrecognized
    #    archive name shape, or BUILDS_DIR/{build-id}/ does not exist).
    for scratch in _iter_active_build_scratches():
        found, rid, mo = _scan_for_compilation_header(scratch)
        if found:
            return True, rid, mo

    return False, None, False


def _path_is_archive(path: str) -> bool:
    """Return True if ``path`` resolves to a sigma-review archive directory.

    KNOWN LIMITATION (DA[#5] accept-with-documentation, C3-r1):
    This is a substring match against ``_ARCHIVE_PATH_MARKERS``. Forms
    that yield the same on-disk destination but a different argv string
    bypass this check and the surrounding BLOCK 5 gate:

      - **Symlinks**: ``ln -s archive/ /tmp/a`` then ``cp x /tmp/a/y``.
        The argv path ``/tmp/a/y`` doesn't contain any marker; the
        kernel resolves the symlink at write time, after the hook.
      - **Relative ``..`` traversal**: ``cd archive/.. && cp x archive/y``
        IS visible (marker still in argv). But ``cd archive/sub && cp x ../y``
        canonicalizes to an archive path while the argv ``../y`` does not.
      - **Case differences**: ``/SIGMA-REVIEW/SHARED/ARCHIVE/`` on a
        case-insensitive filesystem (default macOS HFS+/APFS) resolves
        to the same directory as the lowercase marker but fails the
        substring test (markers are lowercase). Unix and Linux are
        case-sensitive, so this is a macOS-specific bypass.

    Closing this gap requires path canonicalization (``os.path.realpath``
    + case-folding on macOS) before the marker check, plus a write-path
    check at exec time for symlink/cwd-relative forms. Both were out of
    ADR[6]/IC[6] day-1 scope. The day-1 BLOCK is plan-faithful per plan
    §P2.A row 119 and accepts this residual surface as documented.

    If empirical bypasses surface (operator reports an archive write that
    skipped the BLOCK), open a follow-up SQ for path canonicalization.
    """
    return any(marker in path for marker in _ARCHIVE_PATH_MARKERS)


def _is_synthesis_archive_write(path: str) -> bool:
    """Return True iff path is a synthesis-archive write: filename ends with
    `-synthesis.md` AND path is under a known archive directory.

    Fail-safe: returns False for any ambiguity (non-string, empty, BOM-prefixed,
    whitespace-only, non-archive dir, wrong suffix). Gate fires on doubt.

    Consequence note (ADR[1] r3): a false positive here removes the
    compilation-complete precondition entirely for the matched path
    (gate-removal), which has stronger downstream consequence than a false
    positive in _path_is_archive (archive-classification only). The
    compilation-complete header is an integrity boundary. This is accepted
    residual risk in the single-user hook context — see ADR[1] AMENDMENT r3.
    Known limitations: symlinks, HFS+ case-fold, relative `..` — inherited
    from _path_is_archive, deferred per ADR[6].
    """
    if not isinstance(path, str):
        return False
    stripped = path.lstrip("﻿").strip()
    if not stripped:
        return False
    if not os.path.basename(stripped).endswith("-synthesis.md"):
        return False
    return any(marker in stripped for marker in _ARCHIVE_PATH_MARKERS)


def check_pre_archive_gate(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    """BLOCK 5: 06b pre-archive — workspace must have compilation-complete header.

    Stale-workspace FP guard: only fires inside an active sigma session
    (per _is_sigma_session()). Manual-override form unblocks with reason.
    """
    # FP guard per PM[5]: never fire outside a sigma session
    if not _is_sigma_session():
        return False, ""

    is_archive_op = False
    archive_path: str | None = None

    if tool_name in ("Write", "Edit"):
        path = tool_input.get("file_path", "")
        if _path_is_archive(path):
            is_archive_op = True
            archive_path = path
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "")
        if _ARCHIVE_BASH_RE.search(cmd):
            is_archive_op = True
            # Best-effort extract first archive-marker-bearing token; on
            # failure leave archive_path None and fall back to
            # broad-glob scan in _has_compilation_complete.
            for marker in _ARCHIVE_PATH_MARKERS:
                idx = cmd.find(marker)
                if idx >= 0:
                    tail = cmd[idx:].split()[0] if cmd[idx:].split() else ""
                    archive_path = tail or None
                    break

    if not is_archive_op:
        return False, ""

    # BLOCK 5 carve-out (ADR[1]): synthesis-archive writes structurally precede
    # compilation (Step 13f → Step 14); gating them is a logical cycle.
    if archive_path and _is_synthesis_archive_write(archive_path):
        return False, ""

    has_header, review_id, manual_override = _has_compilation_complete(archive_path)
    if has_header:
        return False, ""

    # BLOCK with recovery instructions per IC[6]
    return True, (
        "PRE-ARCHIVE BLOCKED: workspace does not contain the required "
        "`## compilation-complete: [R-{review-id}]` header. Run the 06b "
        "compilation step (compile findings to wiki/memory) before archiving.\n\n"
        "Recovery options:\n"
        "  1. Run compilation: spawn compilation-agent (sigma-lead.md:207) and "
        "wait for it to write `## compilation-complete: [R-{review-id}]`.\n"
        "  2. Manual override: append "
        "`## compilation-complete: [R-{review-id}, manual-override, "
        "reason: {reason}]` to workspace, then retry. Reason is required "
        "and will be audited.\n\n"
        "Per ADR[6]/IC[6] (plan §P2.A row 119): BLOCK day-1 prevents "
        "archive-without-compilation, which loses analytical provenance."
    )


# ---------------------------------------------------------------------------
# WARN 6: Context firewall
# ---------------------------------------------------------------------------

def detect_context_firewall_leak(file_path: str, content: str) -> str | None:
    """WARN if personal context markers detected in workspace writes."""
    if "workspace" not in file_path.lower():
        return None

    for pattern in CONTEXT_FIREWALL_KEYWORDS:
        if re.search(pattern, content, re.IGNORECASE):
            return (
                "CONTEXT FIREWALL: Possible personal context leak detected in workspace "
                "write. Personal context (career, role, family, salary) must not appear "
                "in analytical workspace — it contaminates agent analysis. Review and "
                "strip before writing."
            )
    return None


# ---------------------------------------------------------------------------
# WARN 7: ΣComm Tier-2 tag check (workspace findings + agent inbox messages)
# ---------------------------------------------------------------------------

def _is_sigmacomm_tier2_path(file_path: str) -> bool:
    """Return True if path is a Tier-2 ΣComm surface (workspace/scratch/plan)."""
    if not file_path:
        return False
    return any(rx.search(file_path) for rx in _TIER2_PATH_RES)


def _split_into_blocks(content: str) -> list:
    """Split content into blocks separated by blank lines."""
    if not content:
        return []
    return [b for b in re.split(r"\n\s*\n", content) if b.strip()]


def _log_sigmacomm_calibration(event_type: str, surface: str, snippet: str) -> None:
    """Append a calibration event to JSONL log. Best-effort, never raises."""
    try:
        import time
        record = {
            "ts": time.time(),
            "event_type": event_type,  # "warn" | "write"
            "surface": surface,
            "snippet": (snippet or "")[:200],
        }
        SIGMACOMM_CALIBRATION_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SIGMACOMM_CALIBRATION_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except (OSError, TypeError):
        pass  # Never break the hook on log write failure


def detect_missing_sigmacomm_tags(content: str, surface: str) -> str | None:
    """WARN if a finding block lacks |source:| AND status verb tags.

    Identifier-gated: only blocks containing a finding identifier
    (DA[#N], IC[N], ADR[N], etc.) trigger the check. Pure-prose narrative
    blocks without identifiers are exempt.

    Caller pre-filters: only invoke for known Tier-2 surfaces (workspace
    paths, agent inbox messages).
    """
    if not content:
        return None
    blocks = _split_into_blocks(content)
    for block in blocks:
        if FINDING_ID_RE.search(block):
            if not (SOURCE_RE.search(block) or STATUS_VERB_RE.search(block)):
                _log_sigmacomm_calibration("warn", surface, block)
                return (
                    "ΣComm Tier-2: finding block contains an identifier "
                    "(DA[#N]/IC[N]/ADR[N]/etc.) but no |source:...| or status "
                    "verb (VERIFIED/PASS/PENDING/etc.). Tag with severity "
                    "(HIGH/MEDIUM/LOW), status, and source. See "
                    "~/.claude/teams/sigma-review/agent-defs/sigma-comm.md."
                )
    _log_sigmacomm_calibration("write", surface, "")
    return None


def compute_sigmacomm_fp_rate() -> None:
    """Read calibration log; print stats for Tier-2→Tier-1 promotion gating.

    Eligibility: fp_rate ≤ 0.05 AND writes ≥ 20. Operator marks WARN events
    as `"is_fp": true` in the JSONL log; this command tallies them.
    """
    if not SIGMACOMM_CALIBRATION_LOG.exists():
        print(json.dumps({
            "fires": 0, "writes": 0, "fp_rate": 0.0,
            "false_positives": 0, "eligible_for_block": False,
            "msg": "calibration log empty",
        }, indent=2))
        return
    fires = writes = fps = 0
    try:
        with SIGMACOMM_CALIBRATION_LOG.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event_type = record.get("event_type")
                if event_type == "warn":
                    fires += 1
                    writes += 1
                    if record.get("is_fp"):
                        fps += 1
                elif event_type == "write":
                    writes += 1
    except OSError as exc:
        print(json.dumps({"error": f"could not read log: {exc}"}))
        return
    fp_rate = (fps / fires) if fires else 0.0
    eligible = (fp_rate <= 0.05) and (writes >= 20)
    print(json.dumps({
        "fires": fires,
        "writes": writes,
        "false_positives": fps,
        "fp_rate": round(fp_rate, 4),
        "eligible_for_block": eligible,
        "criterion": "fp_rate <= 0.05 AND writes >= 20",
    }, indent=2))


# ---------------------------------------------------------------------------
# Hook dispatch
# ---------------------------------------------------------------------------

def enforce_pre_tool_use(data: dict) -> tuple[int, dict]:
    """PreToolUse enforcement. Returns (exit_code, output_dict)."""
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")
        should_block, reason = check_code_write_authorization(file_path)
        if should_block:
            return 2, {"reason": reason}
        should_block, reason = check_pre_archive_gate(tool_name, tool_input)
        if should_block:
            return 2, {"reason": reason}

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        should_block, reason = check_premature_git_operation(command)
        if should_block:
            return 2, {"reason": reason}
        should_block, reason = check_sed_in_place(command)
        if should_block:
            return 2, {"reason": reason}
        should_block, reason = check_pre_archive_gate(tool_name, tool_input)
        if should_block:
            return 2, {"reason": reason}

    elif tool_name == "SendMessage":
        should_block, reason = check_premature_shutdown(tool_input)
        if should_block:
            return 2, {"reason": reason}

    return 0, {}


def enforce_post_tool_use(data: dict) -> dict:
    """PostToolUse enforcement. Returns output_dict with optional systemMessage."""
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    if tool_name in ("Write", "Edit"):
        file_path = tool_input.get("file_path", "")
        content = tool_input.get("content", "") if tool_name == "Write" else tool_input.get("new_string", "")

        warn = detect_context_firewall_leak(file_path, content)
        if warn:
            return {"systemMessage": warn}

        if _is_sigmacomm_tier2_path(file_path):
            warn = detect_missing_sigmacomm_tags(content, file_path)
            if warn:
                return {"systemMessage": warn}

    elif tool_name == "SendMessage":
        # Tier-2: agent-to-agent inbox messages
        message = tool_input.get("message", "")
        # Skip protocol JSON (shutdown_request/_response, plan_approval_*)
        if not isinstance(message, str) or len(message) < 100:
            return {}
        recipient = tool_input.get("to", "unknown")
        surface = f"inbox:{recipient}"
        warn = detect_missing_sigmacomm_tags(message, surface)
        if warn:
            return {"systemMessage": warn}

    return {}


def main():
    # CLI mode: --sigmacomm-fp-rate prints calibration stats for promotion gate
    if len(sys.argv) > 1 and sys.argv[1] == "--sigmacomm-fp-rate":
        compute_sigmacomm_fp_rate()
        sys.exit(0)

    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    event = data.get("hook_event_name", "")

    if event == "PreToolUse":
        exit_code, output = enforce_pre_tool_use(data)
        if output:
            print(json.dumps(output))
        sys.exit(exit_code)

    elif event == "PostToolUse":
        output = enforce_post_tool_use(data)
        if output:
            print(json.dumps(output))
        sys.exit(0)

    # No Stop handler — chain-evaluator.py handles Stop
    sys.exit(0)


if __name__ == "__main__":
    main()
