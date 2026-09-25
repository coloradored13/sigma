"""Shared fixtures for the sigma plugin test suite.

The suite is hermetic: before any hook module is imported, HOME is
pointed at a throwaway directory, SIGMA_HOME and SIGMA_ARCHIVE_REPO are cleared, and
outbound network connections are refused. Nothing reads or writes the real
~/.claude.

Two testing strategies:
1. Unit tests: import modules, monkeypatch Path constants to tmp dirs
2. Integration tests: set HOME to a tmp dir, run scripts via subprocess
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = PLUGIN_ROOT / "hooks"
FRAMEWORK_DIR = PLUGIN_ROOT / "framework"
SKILLS_DIR = PLUGIN_ROOT / "skills"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

# --- hermetic environment (must run before hooks/ modules are imported) ---
_SESSION_HOME = Path(tempfile.mkdtemp(prefix="sigma-test-home-"))
os.environ["HOME"] = str(_SESSION_HOME)
# Keep the plugin tree free of __pycache__ (in-process and in subprocesses).
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
# SIGMA_HOME is left unset so every process derives it from HOME; tests that
# run a hook with a different HOME then see a consistent runtime home.
os.environ.pop("SIGMA_HOME", None)
os.environ.pop("SIGMA_ARCHIVE_REPO", None)
os.environ.pop("CLAUDE_PLUGIN_ROOT", None)
SESSION_SIGMA_HOME = _SESSION_HOME / ".claude" / "teams" / "sigma-review"
(SESSION_SIGMA_HOME / "shared").mkdir(parents=True)
# Seed the runtime home the way session-start.py does on first run, so gates
# that read the roster see the shipped one.
shutil.copytree(FRAMEWORK_DIR / "seed", SESSION_SIGMA_HOME, dirs_exist_ok=True)

if str(HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(HOOKS_DIR))


def get_infra_dir() -> Path:
    """Root of the shipped plugin tree, for structural tests."""
    return PLUGIN_ROOT


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Refuse outbound network connections from in-process code."""
    def _blocked(*args, **kwargs):
        raise RuntimeError("network access is disabled in the sigma test suite")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


def subprocess_env(home: Path | None = None, **extra: str) -> dict:
    """Environment for running a hook script as a subprocess.

    With `home`, HOME points at it; SIGMA_HOME is unset, so the child
    resolves every sigma path under the fake home.
    """
    env = os.environ.copy()
    if home is not None:
        env["HOME"] = str(home)
    env.update(extra)
    return env


@pytest.fixture
def tmp_home(tmp_path):
    """Create a fake HOME with the sigma runtime layout for integration tests."""
    home = tmp_path / "home"
    sigma_home = home / ".claude" / "teams" / "sigma-review"
    (sigma_home / "shared").mkdir(parents=True)
    (sigma_home / ".state").mkdir(parents=True)
    return home


@pytest.fixture
def sigma_home(tmp_home):
    """SIGMA_HOME inside the fake HOME."""
    return tmp_home / ".claude" / "teams" / "sigma-review"


@pytest.fixture
def review_workspace(sigma_home):
    """Create a sigma-review workspace with content."""
    ws = sigma_home / "shared" / "workspace.md"

    def _write(content):
        ws.write_text(content, encoding="utf-8")
        return ws

    return _write


@pytest.fixture
def patterns_file(sigma_home):
    """Path to patterns.md (may or may not exist)."""
    return sigma_home / "shared" / "patterns.md"


# --- Sample workspace content for testing ---

SAMPLE_WORKSPACE_COMPLETE = """\
## task
Analyze competitive landscape for payments-API developer platforms

## infrastructure
ΣVerify: openai:gpt-4o available

## prompt-decomposition
Q1: Who are the real competitors?
Q2: What technology capabilities create durable advantage?
H1: Technology is the primary differentiator
H2: Mid-market SaaS is the entry point
H3: Incumbents have aging tech stacks
C1: Scope is embedded payments APIs

## convergence
product-strategist: ✓ competitive landscape mapped |4 findings |→ ready
security-specialist: ✓ compliance depth reviewed |3 findings |→ ready
tech-architect: ✓ architecture patterns compared |2 findings |→ ready
reference-class-analyst: ✓ base rates calibrated |2 findings |→ ready
devils-advocate: ✓ challenges complete |→ synthesis

## findings
F[market-size]: $2.8-3.4B TAM |source:independent-research(WebSearch):T2(analyst-report)|
F[tech-moat]: API-first architecture enables 3x faster integration |source:independent-research(code-read):T1|
F[entry-barrier]: PCI-DSS certification creates 18-month compliance moat |source:independent-research(WebSearch):T1|
Revised from initial assessment after DA challenge — outcome 1
CHECK CONFIRMS with acknowledged risk — outcome 2
gap: card-network interchange mechanics not covered — outcome 3
XVERIFY[openai:gpt-4o] market size corroborated
concede DA point on regulatory timeline
TIER-2 complexity assessment
"""

SAMPLE_WORKSPACE_NO_CONVERGENCE = """\
## task
Early research phase

## findings
Some preliminary findings
"""


def run_hook(script_name, stdin_data, tmp_home=None, extra_env=None):
    """Run a hook script via subprocess with JSON on stdin.

    Returns (exit_code, stdout, stderr).
    """
    script_path = HOOKS_DIR / script_name
    env = subprocess_env(tmp_home, **(extra_env or {}))
    result = subprocess.run(
        [sys.executable, str(script_path)],
        input=json.dumps(stdin_data),
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    return result.returncode, result.stdout, result.stderr
