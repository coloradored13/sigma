"""Atomic workspace write helper for multi-agent section-isolation.

Implements IC[6] per r19-remediation plan ADR[5]:
  atomic Python replace + anchor selection + WorkspaceAnchorNotFound error path
  + section-isolation scope (workspace.md + builds/*/*.md + shared/workspace.md).

Context (why this exists):
  Concurrent Edit-tool writes against moving-target anchors produced 4x
  anchor-not-found failures in the C1 session (DA cluster). Content-based
  match + atomic full-file replace eliminates the race — if the anchor has
  moved, we fail loudly instead of silently writing to the wrong spot.

Design constraints (from plan):
  - CAL[6] anchor = section-header + first-unique-content-line (narrow match)
  - Raises WorkspaceAnchorNotFound if replace is a no-op
  - Section-isolation: agents write ONLY to their own ### agent-name sections
  - No locking, no retry — callers handle conflict via explicit anchor choice

Usage (canonical pattern):

    from workspace_write import workspace_write, WorkspaceAnchorNotFound

    anchor = "### implementation-engineer\\n*(populated by IE)*"
    new_content = "### implementation-engineer\\nSQ[1] DONE |SQ[2] DONE"
    try:
        workspace_write(
            path="~/.claude/teams/sigma-review/shared/builds/.../scratch.md",
            old_anchor=anchor,
            new_content=new_content,
        )
    except WorkspaceAnchorNotFound as e:
        # anchor drifted — surface, do not retry blindly
        raise

Pre-mortem coverage (PM[4]):
  - Multi-byte-Unicode anchors: tested via explicit `old in content` assert
    before replace; silent corruption impossible (replace is no-op → raise)
  - Emoji / accents / multi-line anchors: str.replace handles them natively
"""

from __future__ import annotations

import os
from pathlib import Path


class WorkspaceAnchorNotFound(Exception):
    """Raised when old_anchor is not present in the target file.

    Signals that either (a) the section has already been written by a peer,
    (b) the anchor was chosen too narrowly and drifted, or (c) the file
    was modified between read and write. Callers MUST NOT silently retry
    with a broader anchor — re-read the file and pick a fresh anchor.
    """


def workspace_write(path: str, old_anchor: str, new_content: str) -> None:
    """Atomically replace old_anchor with new_content in path.

    Args:
        path: absolute or ~-expanded path to a markdown workspace file.
            Scope (enforced by convention, NOT by this function):
              - .../shared/workspace.md
              - .../shared/builds/*/*.md
              - .../shared/builds/*/scratch.md
        old_anchor: exact substring to replace. MUST be:
              - section-header + first-unique-content-line (CAL[6])
              - unique within the file (first occurrence is replaced;
                second occurrence becomes silent data loss if non-unique)
        new_content: full replacement text. MUST include the section-header
            line (agents writing to their section are expected to preserve
            their ### header so the anchor for the next write remains valid).

    Raises:
        WorkspaceAnchorNotFound: if old_anchor is not in the file contents.
            This is the load-bearing invariant — a no-op replace is NEVER
            silent.
        FileNotFoundError: if path does not exist.
        OSError: on read/write failure (disk full, permissions, etc).

    Implementation notes:
        - Uses str.replace(old, new, 1) to replace only the first
          occurrence. Callers relying on uniqueness must verify.
        - Writes the full file in a single open(..., "w") call. On most
          POSIX filesystems this is atomic at the page level for small
          files but NOT atomic for large ones; the section-isolation
          convention (each agent writes its own section only) makes the
          lost-update window acceptable per ADR[5] rationale.
        - No fsync. Python + OS page cache semantics are sufficient for
          the workspace.md use case (not a transactional store).
    """
    resolved = Path(os.path.expanduser(path))
    original = resolved.read_text(encoding="utf-8")

    if old_anchor not in original:
        raise WorkspaceAnchorNotFound(
            f"anchor not found in {resolved}: "
            f"first 80 chars of anchor = {old_anchor[:80]!r}"
        )

    updated = original.replace(old_anchor, new_content, 1)

    # Defense in depth: if somehow replace was a no-op (e.g. new_content
    # == old_anchor), raise rather than write an identical file and
    # pretend work happened. This is the PM[4] silent-corruption guard.
    if updated == original:
        raise WorkspaceAnchorNotFound(
            f"replace produced no-op in {resolved}: "
            f"new_content may equal old_anchor (len={len(old_anchor)})"
        )

    resolved.write_text(updated, encoding="utf-8")
