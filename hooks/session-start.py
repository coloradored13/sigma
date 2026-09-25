#!/usr/bin/env python3
"""SessionStart hook — keeps the sigma runtime home in step with the plugin.

Every session:
  1. Records the plugin root in SIGMA_HOME/.plugin-root, so the stable launcher
     SIGMA_HOME/bin/chain-evaluator.py always runs the installed plugin version.
  2. Creates the runtime layout if missing and seeds user-state files once
     (roster, workspace, decisions, patterns, portfolio, calibration log, wiki
     index). Seeded files are never overwritten afterwards.
  3. Syncs framework-managed files (agent definitions, directives, launcher)
     when the plugin version changes. A managed file the user edited since the
     last sync is backed up to <file>.user-modified-<timestamp> first.

Never blocks the session: any error is reported as a systemMessage and the
hook exits 0.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sigma_paths as sp  # noqa: E402

FRAMEWORK = sp.PLUGIN_ROOT / "framework"
MANIFEST = sp.SIGMA_HOME / ".managed.json"

# (source under framework/, destination under SIGMA_HOME)
MANAGED_DIRS = [("agents", "agent-defs"), ("shared", "shared"), ("bin", "bin")]
SEED_DIR = FRAMEWORK / "seed"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _plugin_version() -> str:
    try:
        data = json.loads((sp.PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
        return str(data.get("version", "0"))
    except (OSError, json.JSONDecodeError):
        return "0"


def _seed() -> int:
    created = 0
    for src in SEED_DIR.rglob("*"):
        if not src.is_file():
            continue
        dest = sp.SIGMA_HOME / src.relative_to(SEED_DIR)
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        created += 1
    for sub in ("agents", "inboxes", "shared/archive", "shared/builds", "shared/wiki", ".state"):
        (sp.SIGMA_HOME / sub).mkdir(parents=True, exist_ok=True)
    return created


def _sync_managed(version: str) -> tuple[int, list[str]]:
    try:
        manifest = json.loads(MANIFEST.read_text())
    except (OSError, json.JSONDecodeError):
        manifest = {}
    if manifest.get("version") == version and manifest.get("files"):
        return 0, []

    recorded: dict[str, str] = manifest.get("files", {})
    new_files: dict[str, str] = {}
    backed_up: list[str] = []
    copied = 0
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for src_sub, dest_sub in MANAGED_DIRS:
        src_dir = FRAMEWORK / src_sub
        if not src_dir.is_dir():
            continue
        for src in src_dir.rglob("*"):
            if not src.is_file():
                continue
            rel = str(Path(dest_sub) / src.relative_to(src_dir))
            dest = sp.SIGMA_HOME / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                current = _sha(dest)
                if rel in recorded and current != recorded[rel] and current != _sha(src):
                    backup = dest.with_name(f"{dest.name}.user-modified-{stamp}")
                    shutil.copy2(dest, backup)
                    backed_up.append(str(backup))
            shutil.copy2(src, dest)
            new_files[rel] = _sha(dest)
            copied += 1
    MANIFEST.write_text(json.dumps({"version": version, "files": new_files}, indent=2))
    return copied, backed_up


def main() -> None:
    messages: list[str] = []
    try:
        sp.SIGMA_HOME.mkdir(parents=True, exist_ok=True)
        (sp.SIGMA_HOME / ".plugin-root").write_text(str(sp.PLUGIN_ROOT) + "\n")
        seeded = _seed()
        copied, backed_up = _sync_managed(_plugin_version())
        if seeded:
            messages.append(f"sigma: initialized runtime home at {sp.SIGMA_HOME} — run /sigma-setup to finish setup.")
        if copied and not seeded:
            messages.append(f"sigma: framework files updated to plugin v{_plugin_version()}.")
        if backed_up:
            messages.append("sigma: your edits to managed files were backed up: " + ", ".join(backed_up))
    except Exception as e:  # never block a session
        messages.append(f"sigma: session-start sync failed ({e}); run /sigma-setup.")
    if messages:
        print(json.dumps({"systemMessage": " ".join(messages)}))
    sys.exit(0)


if __name__ == "__main__":
    main()
