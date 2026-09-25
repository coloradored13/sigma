# C2: BUILD (Pure Execution)

**Every step below is mandatory. Complete them in order. No DA, no plan-track, no review. Execute the locked plan.**

## Boot

### Step 0: Read Plan File
!gate: C2 cannot proceed without a valid plan file.

1. Read plan file at path provided by SKILL.md routing
2. Verify `plan-exit-gate: PASS` — if not PASS, STOP and report: "Plan file exit-gate is {value}, not PASS. Cannot build. Run `/sigma-build {task}` to complete planning."
3. Verify `status: plan-locked` — if not plan-locked, STOP and report status mismatch
4. Extract from plan file: ## Architecture Decisions (ADRs), ## Interface Contracts (ICs), ## Sub-task Decomposition (SQs), ## Pre-mortem (PMs), ## Files
5. sigma-mem recall: builder-specific calibration, past execution patterns
6. Create scratch workspace: `builds/{build-id}/c2-scratch.md`

### Step 1: Parallel Engineer Check
Evaluate SQ[] independence per build-directives §3a.1:
1. Map SQ[] items to primary files (from plan file ## Files table)
2. Identify independent clusters (zero shared files)
3. If >=2 clusters: spawn additional implementation-engineer-N with `isolation: "worktree"`
4. Write file ownership to scratch ## build-assignments
5. If 1 cluster: single engineer (skip this step)

### Step 2: Spawn Build-Track Agents
Agents: implementation-engineer, ui-ux-engineer (if plan file contains UI work), code-quality-analyst
!rule: NAMED `Agent({name: ..., model: ..., prompt: ...})` calls only — a named call spawns a teammate you
  can SendMessage. An UNNAMED Agent call is an isolated subagent: it returns once and cannot be messaged,
  so checkpoints (Step 4) and merge coordination break. `TeamCreate` no longer exists.
!rule: NO plan-track agents. NO DA. C2 is pure execution.

SendMessage each agent:
- Plan file path (they read it directly)
- Their SQ[] assignments from scratch ## build-assignments
- Checkpoint format (Step 4 below)
- Reminder: ADRs, ICs, SQs are BUILD CONSTRAINTS — implement against them, do not redesign
- Peer-verify assignment (if used this build) with canonical header format:
  `### Peer Verification: {verifier} verifying {verified}`
  !rule: 3-hash, "verifying" between names, lowercase. ¬4-hash, ¬"verifies". Chain-evaluator A16/A17/A18 match exactly this format (IC[5], regex unchanged).
  !rule: reference ≥3 specific artifact IDs (SQ[], CHECKPOINT[], F[]) — generic "looks good" fails A17.
- Section-isolation convention (UP[TA-B2]): agents write ONLY to their own ### {agent-name} section in scratch workspace; lead writes ## sections. Cross-section writes require lead authorization. Canonical method: workspace_write() helper per IC[6] for workspace files; Edit tool acceptable for out-of-workspace files.
- ¬sed -i rule: phase-gate enforces the sed-i BLOCK ban against workspace files and sigma hook files (SS ADR[1]).

## Build

### Step 3: Monitor Build Progress
Track agent status via scratch ## build-status:
- building → wait
- ? (needs clarification) → answer from plan file context. If plan file is ambiguous, make a conservative interpretation and note it in scratch.
- ! (blocked) → surface to user immediately

### Step 4: Enforce Checkpoint at ~50%
Each build-track agent MUST write a checkpoint:
```
CHECKPOINT[{agent}]: {files-created} |{functions-done} |{interfaces-matched: yes/no} |drift: {none|{description}} |surprises: {none|{description}}
```

If any agent reports drift or surprises at checkpoint:
- Minor drift → note in scratch, continue
- Scope creep → flag immediately, discuss with user before continuing
- Architectural drift → STOP. Report to user: "Architectural drift detected at checkpoint. Plan file may need revision. Cannot resolve in C2."

### Step 5: Wait for Build Complete
All build-track agents (including parallel engineers) must:
- Write findings to scratch ## findings (prefixed with agent name)
- Write final checkpoint to scratch ## build-status
- Persist memory (execution patterns, code debt findings)
- Declare completion in scratch

If parallel engineers: after all engineers complete, run merge step:
1. Code-quality-analyst or lead merges worktrees
2. Run FULL test suite on merged result (individual passes do not guarantee combined)
3. If merge conflicts → route to owning engineer, re-merge, re-test
4. Write to scratch ## build-status:
   `MERGE-VERIFIED: {test-count} passed |conflicts:{none|resolved({files})} |worktrees-merged:{list}`
   !gate: MERGE-VERIFIED MUST be in scratch before advancing. No merge verification = no advancement.

### Step 6: Cross-Model Code Review (when ΣVerify available)
!rule: advisory weight — informs C3 review, does not block C2 exit
!skip if ΣVerify unavailable (check at boot or via sigma-verify init)

1. Select review targets: key files (max 8-10), priority: cross-agent integration, complex logic, security
2. Run XREVIEW prompts: correctness, maintainability, performance, security
3. Write results to scratch ## cross-model-code-review:
   `XREVIEW[{provider}:{model}][{file}]: {assessment} |issues:{count} |severity:{H/M/L}`

## Exit

### Step 7: Write Build Status to Plan File
Write to plan file ## Build Status:

```markdown
## Build Status (written by C2)
### Test Results
- total: {N} | passed: {N} | failed: {N} | new: {N}
- regressions: {N}

### Checkpoints
CHECKPOINT[{agent}]: {files-created} |{functions-done} |{interfaces-matched: yes/no} |drift: {status}

### Cross-Model Code Review
XREVIEW[{provider}:{model}][{file}]: {assessment} |issues:{count}

### SQ Status
SQ[1]: {DONE|PARTIAL|BLOCKED} — {summary}
SQ[2]: ...
```

### Step 8: Verify and Close
1. Verify ALL SQ[] items have build status (DONE, PARTIAL, or BLOCKED) — no items missing
2. Verify tests pass + zero regressions
3. If any SQ[] is BLOCKED: note in plan file, C3 review will address
4. Set plan file `status: built`
5. Mini-promotion: build-track agents persist to sigma-mem (execution patterns, code debt, checkpoint cadence)
6. Archive scratch: copy `builds/{build-id}/c2-scratch.md` to `builds/{build-id}/c2-scratch-archive.md`
7. Report: "Build verified. Run `/sigma-build {task}` for review (C3)."

### C2 Verification

Before ending this conversation, verify ALL items. Any unchecked item is a failed delivery.

- [ ] Plan file validated at boot (status: plan-locked, plan-exit-gate: PASS)
- [ ] Scratch workspace created with build-assignments
- [ ] Parallel engineer check completed (independence clusters evaluated)
- [ ] All build-track agents spawned as NAMED `Agent` calls (messageable teammates)
- [ ] All agents wrote checkpoint at ~50% (drift addressed if found)
- [ ] All SQ[] items have build status (DONE, PARTIAL, or BLOCKED)
- [ ] Tests pass with zero regressions
- [ ] If parallel engineers: MERGE-VERIFIED written to scratch
- [ ] Cross-model code review completed (or ΣVerify unavailable noted)
- [ ] Build Status section written to plan file with test results + SQ status
- [ ] Plan file status set to "built"
- [ ] Build-track agents persisted memory to sigma-mem
- [ ] Scratch workspace archived (c2-scratch-archive.md)
- [ ] Report delivered to user

**C2 is complete ONLY when every item above is verified. Cross-check against SKILL.md C2 Deliverables before ending this conversation.**

## Rules

- Plan file is READ + APPEND ONLY in C2. Never modify locked sections (ADR, IC, SQ, PM, Context, Plan Challenge Summary). Only write to ## Build Status.
- If the plan is wrong, C2 does not fix it. Flag to user, let C3 or a new C1 handle it.
- No adversarial rounds. No Bayesian exit-gates. No BELIEF scores. Those belong to C1 and C3.
- Agent questions about plan interpretation get conservative answers from the plan file. When genuinely ambiguous, flag in scratch and pick the simpler implementation.
