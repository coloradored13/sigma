# Changelog

## [0.1.0] — first public release

- Claude Code plugin packaging for sigma-review (ANALYZE) and sigma-build (BUILD).
- `/sigma-setup` skill: prerequisites, agent-teams flag, MCP registration (sigma-mem required, sigma-verify optional), health check.
- SessionStart hook keeps the runtime home (`~/.claude/teams/sigma-review`) in step with the plugin: seeds user state once, refreshes managed framework files on upgrade (backing up local edits), records the plugin path for the stable `bin/chain-evaluator.py` launcher.
- All hook paths resolve through `hooks/sigma_paths.py` (`SIGMA_HOME`, `SIGMA_ARCHIVE_REPO`); hook state lives in `SIGMA_HOME/.state`.
- Chain gate A14 (git clean) reports N/A when no archive repo is configured.
- New compilation-agent definition (required by the lead's Step 7b and phase-gate BLOCK 5).
- Lead instructions: initialize sigma-mem and sigma-verify, end the turn, then spawn — teammates' tool lists are fixed at spawn.
