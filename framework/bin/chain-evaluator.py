#!/usr/bin/env python3
"""Stable launcher for the sigma chain evaluator.

Installed to ~/.claude/teams/sigma-review/bin/ by the plugin's SessionStart hook.
Runs the chain evaluator from the currently installed plugin version (recorded in
../.plugin-root on every session start), so skill instructions can use one fixed
path across plugin updates.

Usage: python3 ~/.claude/teams/sigma-review/bin/chain-evaluator.py {status|evaluate}
"""
import os
import sys
from pathlib import Path

home = Path(__file__).resolve().parent.parent
try:
    root = (home / ".plugin-root").read_text().strip()
except OSError:
    sys.exit("sigma: plugin root unknown — start a new Claude Code session or run /sigma-setup")
target = os.path.join(root, "hooks", "chain-evaluator.py")
if not os.path.isfile(target):
    sys.exit(f"sigma: {target} not found — start a new Claude Code session to refresh the plugin path")
os.execv(sys.executable, [sys.executable, target, *sys.argv[1:]])
