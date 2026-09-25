---
name: sigma-review
description: Run a full sigma-review team review. Spawns specialist agents to analyze a codebase or task from multiple expert perspectives. ANALYZE mode only — BUILD mode has been separated into /sigma-build.
argument-hint: "[task description]"
allowed-tools: Read, Grep, Glob, Bash, Agent, SendMessage, TaskCreate, TaskGet, TaskList, TaskUpdate
---

# Sigma Review — ANALYZE Mode

You are the sigma-review lead. Orchestrate a multi-agent ANALYZE review of: **$ARGUMENTS**

## How This Works

This review is a **recipe**. Follow the steps in order — each step produces output that the next step consumes. The chain evaluator (`~/.claude/teams/sigma-review/bin/chain-evaluator.py`) verifies the final result at session end: did you follow the steps, is the chain complete, and is the output quality?

**Success = followed steps + completed chain + quality output.** Skip a step and the result degrades even if every item is technically present.

## The Chain (all required)

Run `python3 ~/.claude/teams/sigma-review/bin/chain-evaluator.py status` at any time to see what's passing and what's missing.

**Agent work:**
- A1: Agent findings (non-empty workspace sections)
- A2: Source provenance (|source: tags on all findings)
- A3: Dialectical bootstrapping (DB[] with 5-step structure)
- A4: Circuit breaker evidence (divergence or CB[] entries)
- A5: DA challenges + agent responses (concede/defend/compromise)
- A6: BELIEF state (BELIEF[rN] with P= value)
- A7: Exit-gate (PASS/FAIL with >=3 criteria)
- A8: Contamination check | A9: Source provenance audit | A10: Anti-sycophancy check
- A15: XVERIFY coverage (if sigma-verify available)

**Peer verification:**
- A16: Each agent has a Peer Verification section verifying another agent
- A17: Verifications reference >=3 specific artifact IDs (not generic confirmations)
- A18: Every agent verified by at least 2 others (1 ring peer + DA)

**Chain closure:**
- A11: Synthesis artifact (*-synthesis.md in archive/)
- A12: Workspace archive | A13: Promotion evidence | A14: Git clean
- A19: Chain evaluation output (written by Stop hook — its absence = incomplete)

## Lead Instructions

Read `~/.claude/teams/sigma-review/agent-defs/sigma-lead.md` for the full workflow. Key steps:

1. **Prepare:** Complexity assessment, model selection, prompt decomposition (Q/H/C), **premise-audit pre-dispatch (HARD GATE — §2p)**
   - Premise-audit pre-dispatch is a sub-step of Prepare, run AFTER prompt decomposition and BEFORE Step 2 spawn. Sequence is load-bearing — reversing recreates the frame-anchoring §2p prevents (R19 evaluator: premises "accepted as frame" before H[] dispatch). Per directives.md §2p, lead answers PA[1-4] from user prompt ALONE — do NOT re-read user's proposed tiers/frameworks/H-space until premise-audit is complete.
   - Four structural premise tests (ANALYZE-scoped per directives.md §2p):
     - PA[1] tier-necessity — is proposed tier/framework NECESSARY or is simpler structure adequate?
     - PA[2] firm-size-floor — minimum viable org? (state explicitly)
     - PA[3] data-readiness — what data must exist for findings to be actionable? (gap? yes/no)
     - PA[4] adoption-baseline — RC[{class}]={rate} | above/at/below base-rate?
   - Lead writes PREMISE-AUDIT result to workspace `## premise-audit-results` section BEFORE spawning agents (Step 2). Format per directives.md §2p `!workspace format`. Decision line (`→ proceed-with-H | revise-H-space({N}) | flag-premise({N})`) is REQUIRED — chain-evaluator §2p presence-check BLOCKs on missing `## premise-audit-results` section (PM[3] mitigation).
   - Rules: CHALLENGED/GAP on PA[1] or PA[2] → revise H-space BEFORE Step 2 spawn. CHALLENGED on PA[3] or PA[4] → convert to explicit H[] for agents to test. DA receives PREMISE-AUDIT in r2 — checks agents ¬re-anchored on challenged premises.
   - Cross-ref: BUILD variant carries the "Step 7a" label (sigma-build c1-plan.md:62 Step 7a HARD GATE); ANALYZE side keeps the structure but drops the label to avoid renumber-cascade across the workflow steps.
2. **Spawn:** Initialize workspace, assign peer verification ring, spawn agents as NAMED `Agent` calls (`TeamCreate` no longer exists — see sigma-lead.md)
3. **R1:** Agents research independently, write findings with source provenance + DB[]
4. **Circuit breaker:** Check for zero-dissent after R1
5. **R2+:** DA challenges, agent responses, BELIEF computation, exit-gate
6. **Peer verification:** Each agent verifies assigned peer's workspace section
7. **Chain closure:** Synthesis, compilation, promotion, sync (optional backup), archive, git commit (if an archive repo is configured)
8. **Report:** Translate to plain English, deliver to user

## Lead Role Boundary

You manage agents and coordinate. You do NOT:
- Call analytical tools directly (sigma-verify, WebSearch). Agents do the work.
- Write synthesis content. Spawn a synthesis agent. If it fails, deliver raw findings with a gap flag.
- Skip chain closure items. The evaluator will flag them.

## Paths

```
T=~/.claude/teams/sigma-review        # global tier
P={project}/.claude/teams/sigma-review # project tier (if exists)
```

## Begin

Read `~/.claude/teams/sigma-review/agent-defs/sigma-lead.md` and start with step 1 (Prepare).
