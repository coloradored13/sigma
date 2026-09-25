# Changelog

## [0.3.0]

- **Code-debt watcher** (PostToolUse on Write/Edit, sigma-build only): while a C2 build is in progress — a `builds/*.plan.md` with `status: plan-locked` whose `c2-scratch.md` was touched in the last 12 hours — flags fragile patterns in written code (swallowed errors, shared mutable state, mutable defaults, blanket `noqa`/`type: ignore`, sleep-based sync) into that build's scratch. At most 3 flags per build.

## [0.2.0]

- **Retrospective hook** (Stop): appends one retrospective per finished review to `shared/patterns.md` — convergence, DA effectiveness, hygiene outcomes, source tiers, XVERIFY use, and a recommendation. Fires only after chain closure (`## compilation-complete:` / `## synthesis-complete:` / `## archive-complete:` or `## status: archived`) and at most once per `review-id` / `build-id`.
- **Agent calibration tracker** (PostToolUse on SendMessage): records each roster agent's findings count, DA grade, concessions, source tiers and XVERIFY use to `agents/<name>/calibration.md`, with trends after three entries. Messages from non-roster senders are ignored.
- **Prompt-echo detector** (PostToolUse on Write/Edit): flags workspace findings that restate the prompt's own claims (H[]) instead of testing them.

## [0.1.0] — first public release

- Claude Code plugin packaging for sigma-review (ANALYZE) and sigma-build (BUILD).
- `/sigma-setup` skill: prerequisites, agent-teams flag, MCP registration (sigma-mem required, sigma-verify optional), health check.
- SessionStart hook keeps the runtime home (`~/.claude/teams/sigma-review`) in step with the plugin: seeds user state once, refreshes managed framework files on upgrade (backing up local edits), records the plugin path for the stable `bin/chain-evaluator.py` launcher.
- All hook paths resolve through `hooks/sigma_paths.py` (`SIGMA_HOME`, `SIGMA_ARCHIVE_REPO`); hook state lives in `SIGMA_HOME/.state`.
- Chain gate A14 (git clean) reports N/A when no archive repo is configured.
- New compilation-agent definition (required by the lead's Step 7b and phase-gate BLOCK 5).
- Lead instructions: initialize sigma-mem and sigma-verify, end the turn, then spawn — teammates' tool lists are fixed at spawn.
