"""Single source of filesystem paths for the sigma hooks.

SIGMA_HOME is the runtime home (workspace, archive, wiki, agent memory, roster).
It defaults to ~/.claude/teams/sigma-review, which is also sigma-mem's default
teams directory — if you move it, point sigma-mem at the parent with
SIGMA_TEAMS_DIR so both agree.

Hook state (chain status, compliance counters) lives under SIGMA_HOME/.state so
the Stop hook and a manual `chain-evaluator.py status` run read the same file.
"""
from __future__ import annotations

import os
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

SIGMA_HOME = Path(
    os.environ.get("SIGMA_HOME", str(Path.home() / ".claude" / "teams" / "sigma-review"))
).expanduser()
SHARED = SIGMA_HOME / "shared"
STATE_DIR = SIGMA_HOME / ".state"
AGENT_DEFS = SIGMA_HOME / "agent-defs"

WORKSPACE = SHARED / "workspace.md"
BUILDS_DIR = SHARED / "builds"
ARCHIVE_DIR = SHARED / "archive"
WIKI_DIR = SHARED / "wiki"
TEMPLATES_DIR = SHARED / "templates"
CALIBRATION_LOG = SHARED / "calibration-log.md"


def archive_repo() -> str | None:
    """Repo checked by the A14 git-clean gate, or None to skip it.

    SIGMA_ARCHIVE_REPO wins. Otherwise, if SIGMA_HOME sits inside a git work
    tree, that repo is used. Otherwise A14 reports N/A.
    """
    explicit = os.environ.get("SIGMA_ARCHIVE_REPO")
    if explicit:
        return str(Path(explicit).expanduser())
    probe = SIGMA_HOME
    for parent in [probe, *probe.parents]:
        if (parent / ".git").exists():
            return str(parent)
    return None
