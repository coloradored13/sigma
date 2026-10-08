"""Install the four built wheels into a disposable environment and exercise them.

Runtime dependencies come from uv.lock with hash verification. Workspace packages
are installed only from explicit local wheels. No editable install or provider call.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run(argv: list[str], cwd: Path, *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, check=True, text=True, capture_output=capture)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    dist = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / "dist"
    names = ["sigma_public", "sigma_public_core", "sigma_public_memory", "sigma_public_verify"]
    wheels = [dist / f"{name}-0.1.0a1-py3-none-any.whl" for name in names]
    if not all(path.is_file() for path in wheels):
        raise SystemExit("Build all four wheels before running the installation smoke check.")
    with tempfile.TemporaryDirectory(prefix="sigma-public-wheel-smoke-") as temporary:
        work = Path(temporary)
        venv = work / "venv"
        requirements = work / "runtime-requirements.txt"
        run([
            "uv", "export", "--frozen", "--all-packages", "--no-dev", "--no-emit-workspace",
            "--no-header", "--no-annotate", "--output-file", str(requirements),
        ], root, capture=True)
        run(["uv", "venv", "--python", sys.executable, str(venv)], work)
        python = str(venv / "bin" / "python")
        run(["uv", "pip", "sync", "--python", python, "--require-hashes", str(requirements)], work)
        run(["uv", "pip", "install", "--python", python, "--no-deps", "--no-index", *map(str, wheels)], work)
        run(["uv", "pip", "check", "--python", python], work)
        check_install = (
            "import importlib, pathlib, sys; "
            f"names={names!r}; "
            "modules=[importlib.import_module(name) for name in names]; "
            "assert all(pathlib.Path(m.__file__).is_relative_to(sys.prefix) for m in modules)"
        )
        run([python, "-I", "-c", check_install], work)
        for command in ("sigma-public", "sigma-public-memory", "sigma-public-verify"):
            run([str(venv / "bin" / command), "--help"], work, capture=True)
        run([python, "-I", str(root / "examples" / "offline_demo.py")], work)

        project = work / "synthetic-project"
        project.mkdir()
        (project / "app.py").write_text("answer = 42\n")
        cli = [
            str(venv / "bin" / "sigma-public"), "--db", str(work / "public.sqlite"),
            "--tenant", "synthetic", "--project", "wheel-smoke", "--actor", "operator",
        ]
        started = run([
            *cli, "start", "--mode", "build", "--workspace", str(project), "--require", "behavior",
        ], work, capture=True)
        run_id = json.loads(started.stdout)["id"]
        checked = run([
            *cli, "check", run_id, "behavior", "--", python, "-B", "-c", "import app; assert app.answer == 42",
        ], work, capture=True)
        assert json.loads(checked.stdout)["reason"] == "passed"
        finished = run([*cli, "finish", run_id], work, capture=True)
        assert json.loads(finished.stdout)["completion_current"] is True
        started = run([
            *cli, "start", "--mode", "analysis", "--workspace", str(project),
        ], work, capture=True)
        run_id = json.loads(started.stdout)["id"]
        finding = run([
            *cli, "finding", run_id, "--claim", "The sample returns 42.",
            "--source-id", "synthetic-manual", "--source", "synthetic://manual",
            "--evidence", "The sample returns 42.", "--quote", "returns 42",
            "--limitations", "Synthetic illustration; no independent truth check.",
        ], work, capture=True)
        assert json.loads(finding.stdout)["verification"]["status"] == "offline"
        finished = run([*cli, "finish", run_id], work, capture=True)
        assert json.loads(finished.stdout)["reason"] == "evidence_recorded_not_truth_verified"
    print("Fresh non-editable wheels: imports, console entry points, offline integration and CLI flows passed.")


if __name__ == "__main__":
    main()
