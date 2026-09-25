---
name: sigma-build
description: Run a sigma-build team review for code implementation tasks. Orchestrates specialist agents through plan→challenge→build→review across 3 separate conversations. Use when the user says "sigma-build", "build review", or asks for multi-agent implementation with adversarial quality gates. BUILD mode only — for analysis use /sigma-review.
argument-hint: "[build task description]"
allowed-tools: Read, Grep, Glob, Bash, Agent, SendMessage, TaskCreate, TaskGet, TaskList, TaskUpdate
---

# Sigma Build — 3-Conversation BUILD Orchestration

> BUILD mode separated from sigma-review on 2026-03-19.
> Restructured from 13-phase monolith to 3-conversation model on 2026-04-13.
> ANALYZE mode → /sigma-review skill.
> BUILD-specific directives → ~/.claude/teams/sigma-review/shared/build-directives.md
> DA agent definition → ~/.claude/teams/sigma-review/agent-defs/devils-advocate.md (serves both modes)

You are the sigma-build lead. Orchestrate a multi-agent BUILD of: **$ARGUMENTS**

## Architecture

Each build runs across 3 separate conversations. Each conversation is a recipe — follow the steps in order, each step uses the output of the previous one. The conversation boundary enforces scope isolation. The **chain evaluator** (`~/.claude/teams/sigma-review/bin/chain-evaluator.py`) verifies the final result: followed steps + completed chain + quality output.

```
Conversation 1: PLAN    →  preflight, spawn, plan design, DA + build-track challenge → locked plan file
Conversation 2: BUILD   →  pure execution against locked plan → code + tests
Conversation 3: REVIEW  →  DA + plan-track review build, code fixes, synthesis, close-out
```

**Plan file** bridges conversations: `~/.claude/teams/sigma-review/shared/builds/{date}-{task-slug}.plan.md`
**sigma-mem** bridges institutional memory (calibration, patterns, lessons)
**Scratch workspace** is ephemeral per conversation: `builds/{build-id}/c{N}-scratch.md`
**Chain evaluator** runs at session end (Stop hook) and can be invoked mid-session: `python3 ~/.claude/teams/sigma-review/bin/chain-evaluator.py status`

## Routing

Determine which conversation to run based on the plan file state.

### Step 1: Search for existing plan file

```
Search: ~/.claude/teams/sigma-review/shared/builds/*.plan.md
Match: $ARGUMENTS against plan file ## Meta build-id and ## Context
```

### Step 2: Route based on plan file status

```
No matching plan file found
  → This is a NEW build. Run Conversation 1 (PLAN).
  → Read phases/c1-plan.md now.

Match found — read ## Meta section:

  status: plan
    → C1 in progress or interrupted. Resume Conversation 1 (PLAN).
    → Read phases/c1-plan.md now.

  status: plan-locked AND plan-exit-gate: PASS
    → Plan approved. Run Conversation 2 (BUILD).
    → Read phases/c2-build.md now.

  status: built
    → Build complete. Run Conversation 3 (REVIEW).
    → Read phases/c3-review.md now.

  status: closing
    → C3 in progress or interrupted. Resume Conversation 3 (REVIEW).
    → Read phases/c3-review.md now.

  status: complete
    → Build already finished.
    → Report: "Build {build-id} complete. Archive at {archive-path}."
    → Offer: "Run /sigma-build {new task} to start a new build."
```

### Step 3: Handle multiple matches

If multiple plan files match $ARGUMENTS:
```
Multiple builds match "$ARGUMENTS":
1. {build-id-1} (status: {status}, plan-exit-gate: {gate})
2. {build-id-2} (status: {status}, plan-exit-gate: {gate})
Select build [1-N] or "new" to start fresh:
```

### Step 4: Handle --phase override (optional)

User can force a specific phase: `/sigma-build --phase plan {task}` or `/sigma-build --phase build {task}` or `/sigma-build --phase review {task}`.

## Why Every Step Matters

This build system produces code that humans ship to production. Every step exists because skipping it previously caused a specific failure:

- Skipped gate checks → herding went undetected for 7 reviews
- Skipped convergence verification → empty findings passed as complete
- Skipped prompt understanding → agents built the wrong thing
- Skipped plan challenge → scope creep discovered at build review instead of plan phase
- Skipped checkpoint → architectural drift caught too late to fix cheaply
- Skipped anti-contamination → lead bias leaked into "independent" analysis
- Skipped promotion → agent learnings lost, same mistakes repeated
- Skipped sync → 12 agent memories drifted undetected
- **Ran all phases in one conversation → context degraded, DA never spawned, build shipped unchallenged (B7 RED audit)**

**Skipping a step is not efficiency. It is a failure.** The user trusts this system because every step runs, every check fires, every gate validates. An incomplete build that ran every step is more valuable than a polished build that skipped checks. Completeness IS the product.

**The analysis/build is the OUTPUT. Promotion, archive, synthesis are the OUTCOME. Output without outcome is worthless.** The output is a one-time artifact. The outcome is what compounds — agents that get better across sessions, calibration data that improves future reviews, archives that enable audit and recreation. An experiment that can't be recreated is garbage. A review whose learnings aren't persisted is a one-shot that never compounds. The "outcome delivery" steps are not cleanup after the real work — they ARE the durable value. The plan file is the LAST artifact written, not the first. It cannot exist until promotion and archive are complete.

## Lead Role Boundary

You manage agents and phases. You do NOT:
- Call analytical tools directly (sigma-verify, WebSearch for research). Agents research, you organize.
- Write synthesis content. A separate synthesis agent does this (C3 only). Lead-written synthesis is provenance contamination.
- Skip outcome delivery. Every conversation has a formal outcome chain: promotion → archive → plan file. The plan file is the LAST artifact. Shutdown before promotion and archive is an incomplete delivery — log it as a failure.
- Dispatch implementation work before the plan is locked. The plan file with exit-gate: PASS is the build authorization.

## Paths

```
T=~/.claude/teams/sigma-review        # global tier
P={project}/.claude/teams/sigma-review # project tier (if exists)
B=T/shared/builds                     # plan files and scratch workspaces
```

project tier exists → use P/ for decisions,patterns,project-memory | T/ for global-memory,roster,agent-defs
¬project tier → all→T/

## Build Deliverables

Each conversation (C1/C2/C3) has its own deliverable checklist below. A conversation is not complete until every item in its checklist is true. The build is not complete until C3's checklist is fully verified.

### C1 (PLAN) Deliverables
- [ ] Preflight verified (system, roster, complexity, prompt understanding, user confirmation)
- [ ] Scratch workspace initialized with all required sections
- [ ] All plan-track agents wrote non-empty plans with required outputs per role
- [ ] All build-track agents completed feasibility challenge
- [ ] DA spawned and completed plan challenge with agent responses
- [ ] Circuit breaker checked (mandatory after first challenge round)
- [ ] Belief state computed and written to scratch for every round
- [ ] Plan exit gate evaluated (PASS or hard cap)
- [ ] Plan locked, plan-lock validation passed
- [ ] Agent memories persisted to sigma-mem (promotion)
- [ ] Scratch workspace archived + copied to archive directory
- [ ] Archive INDEX.md updated
- [ ] Plan file written with all sections populated and validated
- [ ] User report delivered with outcome chain status

### C2 (BUILD) Deliverables
- [ ] Plan file validated (status: plan-locked, plan-exit-gate: PASS)
- [ ] Scratch workspace initialized with build-assignments
- [ ] Parallel engineer check completed (clusters evaluated)
- [ ] Build-track agents spawned with SQ[] assignments
- [ ] All agents wrote checkpoints at ~50% (drift evaluated)
- [ ] All SQ[] items have build status (DONE, PARTIAL, or BLOCKED)
- [ ] Tests pass with zero regressions
- [ ] If parallel engineers: merge verified with full test suite
- [ ] Cross-model code review completed (or ΣVerify unavailable noted)
- [ ] Build Status section written to plan file
- [ ] Plan file status set to "built"
- [ ] Build-track agents persisted memory to sigma-mem
- [ ] Scratch workspace archived
- [ ] Report delivered to user

### C3 (REVIEW) Deliverables
- [ ] Plan file validated (status: built, all sections present)
- [ ] DA + plan-track review completed with build-track responses
- [ ] All review rounds validated with BELIEF[] written to scratch
- [ ] Contamination + sycophancy checks written to scratch
- [ ] BUILD rubric evaluated
- [ ] Build-track applied fixes, tests pass
- [ ] Build Review Summary written to plan file
- [ ] Synthesis agent spawned and synthesis delivered to user
- [ ] Synthesis artifact saved to archive
- [ ] Wiki compilation agent spawned, pages updated with attribution
- [ ] Compilation validated (V24+V25+V26)
- [ ] Promotion round completed — all agents responded, candidates resolved
- [ ] Infrastructure drift detected and synced, commit resolved
- [ ] Scratch workspace archived with metadata header
- [ ] Session-end validation passed (V22+V23)
- [ ] Close Status written to plan file, status set to complete
- [ ] All agents shut down (or stragglers handled)
- [ ] Final report delivered to user

**Individual phase checklists within each conversation are progress markers. These checklists are the delivery contracts.**

**Chain evaluator:** Before ending each conversation, run `python3 ~/.claude/teams/sigma-review/bin/chain-evaluator.py evaluate`. The Stop hook runs it automatically, but checking before you declare done catches gaps while you can still address them. BUILD-specific chain items (B1-B4) are checked alongside the ANALYZE items (A1-A19).

## Begin

Execute the routing logic above. Read the phase file for the determined conversation.
