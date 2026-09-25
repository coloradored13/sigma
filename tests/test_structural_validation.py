"""Structural validation tests.

Verify the shipped plugin tree is consistent:
- Every shipped skill has a valid SKILL.md with frontmatter
- hooks/hooks.json references real, compilable hook scripts
- Plugin manifests are valid JSON
- Orchestration files do not name removed harness tools
"""
import json
import re
from pathlib import Path

import pytest

from conftest import get_infra_dir

CLAUDE_DIR = get_infra_dir()  # plugin root
SKILLS_DIR = CLAUDE_DIR / "skills"
HOOKS_DIR = CLAUDE_DIR / "hooks"
AGENTS_DIR = CLAUDE_DIR / "framework" / "agents"


EXPECTED_SKILLS = {"sigma-review", "sigma-build", "sigma-setup"}

EXPECTED_HOOKS = {
    "chain-evaluator.py",
    "phase-gate.py",
    "mcp-compliance-monitor.py",
    "session-start.py",
}

# Modules the hooks import or run; they must ship alongside the hooks.
EXPECTED_HOOK_MODULES = {
    "gate_checks.py",
    "workspace_write.py",
    "audit-calibration-gate.py",
    "sigma_paths.py",
}


class TestSkillsInstalled:
    def test_expected_skills_present(self):
        installed = {d.name for d in SKILLS_DIR.iterdir()
                     if d.is_dir() and not d.name.startswith(".")}
        assert installed == EXPECTED_SKILLS, f"unexpected skill set: {sorted(installed)}"

    def test_sigma_build_phase_files_present(self):
        phases = SKILLS_DIR / "sigma-build" / "phases"
        for name in ("c1-plan.md", "c2-build.md", "c3-review.md"):
            assert (phases / name).is_file(), f"missing sigma-build phase file {name}"


class TestSkillMdValidity:
    @pytest.fixture(params=sorted(EXPECTED_SKILLS))
    def skill_name(self, request):
        return request.param

    def test_skill_has_skill_md(self, skill_name):
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        assert skill_md.exists(), f"{skill_name}/SKILL.md missing"

    def test_skill_md_has_frontmatter(self, skill_name):
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        assert content.startswith("---"), f"{skill_name}/SKILL.md missing frontmatter"
        # Should have closing ---
        parts = content.split("---", 2)
        assert len(parts) >= 3, f"{skill_name}/SKILL.md frontmatter not closed"

    def test_skill_md_has_name_field(self, skill_name):
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        frontmatter = content.split("---")[1]
        assert re.search(rf"^name:\s*{re.escape(skill_name)}\s*$", frontmatter, re.MULTILINE), \
            f"{skill_name}/SKILL.md name field missing or mismatched"

    def test_skill_md_has_description(self, skill_name):
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        frontmatter = content.split("---")[1]
        assert "description:" in frontmatter, f"{skill_name}/SKILL.md missing description"

    def test_skill_md_not_empty(self, skill_name):
        skill_md = SKILLS_DIR / skill_name / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        # Content after frontmatter should be substantive
        body = content.split("---", 2)[2] if len(content.split("---", 2)) > 2 else ""
        assert len(body.strip()) > 50, f"{skill_name}/SKILL.md body too short"


class TestPluginManifest:
    def test_plugin_json_valid(self):
        data = json.loads((CLAUDE_DIR / ".claude-plugin" / "plugin.json").read_text())
        assert data["name"] == "sigma"
        assert re.fullmatch(r"\d+\.\d+\.\d+", data["version"])
        assert data.get("license") == "Apache-2.0"

    def test_marketplace_json_valid(self):
        data = json.loads((CLAUDE_DIR / ".claude-plugin" / "marketplace.json").read_text())
        assert any(p["name"] == "sigma" for p in data["plugins"])

    def test_license_and_notice_ship(self):
        assert (CLAUDE_DIR / "LICENSE").is_file()
        assert (CLAUDE_DIR / "NOTICE").is_file()


class TestHooksJson:
    def _config(self):
        return json.loads((HOOKS_DIR / "hooks.json").read_text(encoding="utf-8"))

    def test_hooks_json_valid(self):
        assert "hooks" in self._config()

    def test_has_stop_hook(self):
        assert "Stop" in self._config()["hooks"]

    def test_has_session_start_hook(self):
        assert "SessionStart" in self._config()["hooks"]

    def test_has_pre_and_post_tool_use_hooks(self):
        hooks = self._config()["hooks"]
        assert "PreToolUse" in hooks
        assert "PostToolUse" in hooks

    def test_all_hook_scripts_exist(self):
        for script in EXPECTED_HOOKS | EXPECTED_HOOK_MODULES:
            assert (HOOKS_DIR / script).exists(), f"Hook script missing: {script}"

    def test_all_hook_scripts_compile(self):
        """All scripts should be syntactically valid Python."""
        for script in EXPECTED_HOOKS | EXPECTED_HOOK_MODULES:
            path = HOOKS_DIR / script
            try:
                compile(path.read_text(encoding="utf-8"), str(path), "exec")
            except SyntaxError as e:
                pytest.fail(f"{script} has syntax error: {e}")

    def test_hook_matchers_reference_valid_tools(self):
        valid_tools = {"Read", "Write", "Edit", "Bash", "Glob", "Grep",
                       "SendMessage", "Agent", "WebFetch", "WebSearch"}
        for event_name, matchers in self._config()["hooks"].items():
            for matcher_group in matchers:
                matcher = matcher_group.get("matcher", "")
                if matcher:  # Empty matcher = match all
                    for tool in matcher.split("|"):
                        # MCP tool names start with mcp__ — valid by convention
                        if tool.startswith("mcp__"):
                            continue
                        assert tool in valid_tools, \
                            f"Hook matcher references unknown tool '{tool}' in {event_name}"

    def test_hook_commands_reference_existing_scripts(self):
        for event_name, matchers in self._config()["hooks"].items():
            for matcher_group in matchers:
                for hook in matcher_group.get("hooks", []):
                    cmd = hook.get("command", "")
                    m = re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\"\s]+)", cmd)
                    assert m, f"{event_name} hook command is not plugin-root relative: {cmd}"
                    script_path = CLAUDE_DIR / m.group(1)
                    assert script_path.exists(), \
                        f"Hook command references missing script: {cmd} (resolved: {script_path})"

    def test_every_hook_has_timeout(self):
        for event_name, matchers in self._config()["hooks"].items():
            for matcher_group in matchers:
                for hook in matcher_group.get("hooks", []):
                    assert isinstance(hook.get("timeout"), int), f"{event_name} hook lacks a timeout"


# --- Harness drift: orchestration files must not name tools that no longer exist ---

# Tools Claude Code has removed or disabled. A sigma file that instructs the lead
# to call one of these produces a runtime failure, not a warning, so keep this
# list as the tripwire when the harness moves again.
#   TeamCreate / TeamDelete — removed in v2.1.178; a named Agent call spawns a
#     teammate instead, and no setup or cleanup step is needed.
#   TodoWrite — disabled by default in favor of TaskCreate/TaskGet/TaskList/TaskUpdate.
DEAD_TOOL_NAMES = ("TeamCreate", "TeamDelete", "TodoWrite")

# Files that tell the lead which tools to call.
ORCHESTRATION_FILES = (
    "framework/agents/sigma-lead.md",
    "framework/agents/_template.md",
    "skills/sigma-review/SKILL.md",
    "skills/sigma-build/SKILL.md",
    "skills/sigma-build/phases/c1-plan.md",
    "skills/sigma-build/phases/c2-build.md",
    "skills/sigma-build/phases/c3-review.md",
    "skills/sigma-setup/SKILL.md",
    "framework/shared/directives.md",
    "framework/shared/build-directives.md",
)


class TestNoDeadHarnessTools:
    """sigma-review/sigma-build must not instruct the lead to call removed tools."""

    @pytest.mark.parametrize("rel_path", ORCHESTRATION_FILES)
    def test_orchestration_file_has_no_dead_tool(self, rel_path):
        path = CLAUDE_DIR / rel_path
        assert path.exists(), f"{rel_path} does not ship"
        content = path.read_text(encoding="utf-8")
        for dead in DEAD_TOOL_NAMES:
            # A line that documents the removal is allowed; a line that tells the
            # lead to use the tool is not.
            offenders = [
                line.strip()
                for line in content.splitlines()
                if dead in line and "no longer exist" not in line and "removed in" not in line
            ]
            assert not offenders, (
                f"{rel_path} references removed tool '{dead}': {offenders[:3]}"
            )
