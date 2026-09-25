# sigma

Multi-agent analysis and build teams for [Claude Code](https://code.claude.com), with adversarial quality gates.

- **`/sigma-review <question>`** runs an analysis. A lead assembles a team of specialist agents who research independently, get challenged by a devil's advocate, verify each other's work, and hand off to a context-firewalled synthesis agent.
- **`/sigma-build <task>`** runs an implementation across three conversations: plan → build → review. The plan is locked before any code is written.

The process is a recipe, and hooks check that it was followed. A **chain evaluator** runs when the session ends and scores the workspace against about 25 checks, including source tags on findings, devil's-advocate challenges and responses, belief tracking, exit gate, peer verification, synthesis and archive. A **phase gate** blocks the specific shortcuts that past runs took, such as the lead writing its own synthesis, archiving before compilation, or `sed -i` on shared files.

## What you get

| | |
|---|---|
| Skills | `sigma-review`, `sigma-build`, `sigma-setup` |
| Agents | lead, devil's advocate, synthesis, compilation, plus 11 specialists: reference-class analyst, cognitive/decision scientist, tech architect, implementation engineer, code-quality analyst, security specialist, product strategist, product designer, UI/UX engineer, UX researcher, technical writer |
| Hooks | chain evaluator and retrospective (Stop), phase gate (Pre/PostToolUse), MCP compliance monitor, per-agent calibration tracker, prompt-echo detector, code-debt watcher (sigma-build), session-start sync |
| Memory | [sigma-mem](https://github.com/coloradored13/sigma-mem) MCP server: agent memory, team decisions and patterns that persist across reviews |
| Cross-model checks | [sigma-verify](https://github.com/coloradored13/sigma-verify) MCP server (optional): findings get checked by non-Anthropic models |

Both MCP servers are built on [hateoas-agent](https://github.com/coloradored13/hateoas-agent).

## Requirements

- Claude Code, with agent teams enabled: `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`. `/sigma-setup` adds this to `~/.claude/settings.json` with your OK. A plugin can't set it for you.
- Python 3.11+
- [uv](https://docs.astral.sh/uv/). `uvx` runs the MCP servers.
- Optional, for cross-model verification: [Ollama](https://ollama.com) (local models or free-tier cloud models), or OpenAI / Google AI API keys.

## Install

In Claude Code:

```
/plugin marketplace add coloradored13/sigma
/plugin install sigma@sigma
```

Start a new session, then run:

```
/sigma-setup
```

Setup checks the prerequisites, turns on agent teams, registers the `sigma-mem` and `sigma-verify` MCP servers, and confirms the runtime folder exists. Restart Claude Code once more when it's done, then run `/sigma-setup check`.

The MCP servers are registered at user scope with `claude mcp add` rather than bundled in the plugin. That keeps their tool names (`mcp__sigma-mem__*`, `mcp__sigma-verify__*`) the same as the names the agent instructions and hooks refer to.

## Use

```
/sigma-review Should we move our job queue from Redis to Postgres, given our current load and team size?
/sigma-build Add rate limiting to the public API with per-key quotas and tests
```

The lead sizes the team to the question, asks you to confirm how it has broken the question down, and reports progress as it goes. The deliverable is a synthesis document saved under `~/.claude/teams/sigma-review/shared/archive/`, and findings also accumulate in a wiki at `shared/wiki/`.

Run `python3 ~/.claude/teams/sigma-review/bin/chain-evaluator.py status` at any time to see which checks pass.

## Where things live

| Path | Contents |
|---|---|
| `~/.claude/teams/sigma-review/shared/` | workspace, archive, wiki, roster, decisions, patterns (including one retrospective per finished review), calibration log |
| `~/.claude/teams/sigma-review/agents/<name>/` | each agent's persistent memory (`memory.md`) and track record (`calibration.md`) |
| `~/.claude/teams/sigma-review/agent-defs/`, `shared/directives.md`, `shared/build-directives.md`, `shared/protocols.md`, `bin/` | framework files, managed by the plugin |
| `~/.claude/memory/` | sigma-mem's personal (non-team) memory |

Framework files are refreshed each time the plugin version changes. If you edited one, your copy is saved beside it as `*.user-modified-<timestamp>`. Your own state (workspace, archive, wiki, memory, roster, decisions, patterns) is created once and never overwritten.

To keep a history of your reviews, make `~/.claude/teams/sigma-review` a git repo, or set `SIGMA_ARCHIVE_REPO`. The evaluator's git-clean check (A14) then applies. Without a repo it reports N/A.

Set `SIGMA_HOME` to move the runtime folder. If you do, re-register sigma-mem with `-e SIGMA_TEAMS_DIR=<parent folder>` so both agree.

## Cost

The lead and teammates run on your Claude Code plan. A review typically uses 4–7 agents, so expect several times the usage of a single conversation.

Only sigma-verify's API providers bill separately, per token: OpenAI and Google, if you add keys. Ollama local models are free, and Ollama's free tier includes cloud models such as `gpt-oss:120b`. Anthropic models are excluded from verification by default, because Claude checking Claude isn't a cross-model check.

## Troubleshooting

- **Teammates say they don't have `store_agent_memory` or `verify_finding`.** Claude Code fixes a teammate's tool list when it spawns, and these HATEOAS servers only advertise their full tool set after a first call. The lead instructions handle this: the lead calls `recall` and `init`, ends its turn, then spawns. If you drive a review by hand, do the same.
- **`plugin root unknown`.** Start a new session. The SessionStart hook records the plugin location.
- **A check fails that you think shouldn't.** Run `chain-evaluator.py status`. Each item says what it looked for. The rules behind every gate are in `shared/directives.md`.

## Development

```bash
uv venv .venv && uv pip install -p .venv pytest
.venv/bin/python -m pytest tests -q
```

## License

Apache-2.0
