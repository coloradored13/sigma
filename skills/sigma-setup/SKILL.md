---
name: sigma-setup
description: One-time setup and health check for the sigma plugin (sigma-review / sigma-build). Checks prerequisites, enables Claude Code agent teams, registers the sigma-mem and sigma-verify MCP servers, and verifies the runtime home. Use when the user says "sigma-setup", "set up sigma", or when a sigma skill reports missing tools.
argument-hint: "[check]"
allowed-tools: Read, Bash, Edit
---

# sigma setup

Walk the user through each step. Report what you find in plain English. Ask before changing any file or registering anything. If `$ARGUMENTS` is `check`, only report status (steps 1–5) and change nothing.

Paths used below:
- `PLUGIN` = two directories above this skill's base directory (the base directory is printed above as "Base directory for this skill").
- `HOME_DIR` = `~/.claude/teams/sigma-review` (or `$SIGMA_HOME` if set).

## 1. Prerequisites

Run and report:
```bash
python3 --version        # need 3.11+
uvx --version            # uv runs the MCP servers; install: https://docs.astral.sh/uv/
claude --version
```
If `uvx` is missing, stop and point the user to the uv install page.

## 2. Agent teams flag

sigma spawns named teammates, which needs `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. A plugin cannot set this itself.
Check `~/.claude/settings.json` → `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`. If absent, show the user the exact change and, with their OK, add it:
```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```
(merge into the existing `env` object — never overwrite other keys).

## 3. Runtime home

Check that `HOME_DIR/.plugin-root` exists and `HOME_DIR/shared/roster.md` exists. The plugin's SessionStart hook creates both. If missing, run:
```bash
python3 "$PLUGIN/hooks/session-start.py"
```
Then run `python3 ~/.claude/teams/sigma-review/bin/chain-evaluator.py status` and confirm it prints a status table (an idle workspace showing FAIL items is normal).

## 4. sigma-mem (required)

Run `claude mcp list`. If `sigma-mem` is not listed, register it (user scope, so every project sees it):
```bash
claude mcp add sigma-mem --scope user -- uvx --from git+https://github.com/coloradored13/sigma-mem sigma-mem
```
sigma-mem stores agent memory, team decisions and patterns under `~/.claude/memory` and `~/.claude/teams`.

## 5. sigma-verify (optional, recommended)

Cross-model verification (XVERIFY). Without it, reviews still run and findings are left untagged (neutral, not penalized). Anthropic models are excluded by default — Claude checking Claude is not cross-model.

Ask which providers the user wants:
- **Ollama (free options)**: needs Ollama running locally. `ollama signin` enables free-tier cloud models such as `gpt-oss:120b-cloud`; `ollama pull llama3.1:8b` gives a fully local model.
- **OpenAI** and/or **Google AI**: per-token API keys.

API keys must not pass through this conversation. Tell the user to run the registration themselves by typing it with a `!` prefix, filling in only the keys they have:
```
! claude mcp add sigma-verify --scope user -e OPENAI_API_KEY=sk-... -e GOOGLE_AI_API_KEY=... -- uvx --from "git+https://github.com/coloradored13/sigma-verify" sigma-verify
```
Ollama-only users can drop the `-e` flags. You may run the no-key form yourself if they choose Ollama only.

## 6. Restart and verify

New MCP servers and env settings load at session start. Tell the user to restart Claude Code, then run `/sigma-setup check`. In that fresh session, verify:
1. `mcp__sigma-mem__recall` with context "sigma setup check" returns without error.
2. `mcp__sigma-verify__init` lists at least one available provider (or the user chose to skip it).
3. `python3 ~/.claude/teams/sigma-review/bin/chain-evaluator.py status` runs.

Finish with a short status table (prerequisites, agent-teams flag, runtime home, sigma-mem, sigma-verify providers) and the next command: `/sigma-review <question>` or `/sigma-build <task>`.

## Troubleshooting

- **Teammates missing `store_*` or `verify_*` tools**: the lead must call `recall` and `init` and end its turn before the first spawn (sigma-lead Step 2). Tool lists are fixed when a teammate spawns.
- **`bin/chain-evaluator.py` says plugin root unknown**: start a new session (the SessionStart hook records it).
- **Moved the runtime home** with `SIGMA_HOME`: also re-register sigma-mem with `-e SIGMA_TEAMS_DIR=<parent of SIGMA_HOME>` so both agree.
- **Your edits to agent definitions or directives disappeared after an upgrade**: managed files are refreshed on each plugin version; your edited copy is saved next to the file as `*.user-modified-<timestamp>`.
