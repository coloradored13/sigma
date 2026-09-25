# Conversation 3: REVIEW

**Every step below is mandatory. Skipping any step = process failure. This is the longest conversation because it covers both review and close-out.**

**Plan file location:** skill passes `{plan_file}` path. Format: `~/.claude/teams/sigma-review/shared/builds/{date}-{task-slug}.plan.md`
**Scratch workspace:** `builds/{build-id}/c3-scratch.md` — ephemeral coordination, archived at end.

---

## BOOT

### Step 1: Read Plan File + Validate Status
```bash
cat {plan_file}
```
Verify:
- `status: built` (if not → refuse, report: "Plan file status is {status}, expected 'built'. Run `/sigma-build {task}` to complete prior phase.")
- `build-exit-gate: PENDING` (C3 has not run yet)
- `plan-exit-gate: PASS` (C1 completed)
- ## Build Status section exists and is populated (C2 completed)
- ## Architecture Decisions section is populated (locked from C1)
- ## Plan Challenge Summary section exists (DA settled issues from C1)

!gate: ALL conditions must pass. If ANY fail → stop, report missing prerequisites to user.

### Step 2: sigma-mem Recall
```
recall: "{task-slug} build review calibration patterns"
```
Load: agent calibration, past review patterns, team history. sigma-mem bridges institutional memory across conversation boundaries.

### Step 3: Initialize Scratch Workspace
Create `builds/{build-id}/c3-scratch.md` with sections:
```markdown
# C3 Scratch: {task-slug}
## plan-file
path: {plan_file}

## agents
{populated during spawn}

## scope-boundary
{copied from plan file ## Scope Boundary}

## review-findings
{DA + plan-track findings go here}

## belief-tracking
{BELIEF[] entries per round}

## contamination-check
{written before close-out}

## promotion
{agent promotion candidates}

## convergence
{agent completion signals}
```

### Step 4: sigma-verify Pre-flight
```
sigma-verify init
```
Write availability to scratch ## infrastructure. Not blocking — advisory for XVERIFY decisions.

---

## PART A: BUILD REVIEW

### Step 5: Spawn Review Agents

Spawn as NAMED `Agent` calls (`TeamCreate` no longer exists — see sigma-lead.md):

**DA (fresh, model=opus):**
- DA has NO memory of C1's plan challenge (conversation boundary wiped it)
- DA reads plan file ## Plan Challenge Summary to know what was settled — does NOT re-litigate settled decisions
- sigma-mem carries institutional calibration (patterns, grades from past builds)
- DA reviews: code quality, test integrity, scope compliance, source provenance

**Plan-track agents (for fidelity review):**
- tech-architect: do implementations match ADRs? interface contracts correct? tech stack as designed?
- product-designer: does UI follow design system? tokens correct? interaction patterns match IX[]? accessibility?
- product-strategist: does build address priority sequencing? success criteria achievable?

**Build-track agents (for fixes — spawn now, activate after review):**
- implementation-engineer: applies code fixes from review findings
- ui-ux-engineer: applies UI fixes from review findings (if UI in scope)
- code-quality-analyst: validates fixes meet standards

Write agent roster to scratch ## agents.

### Step 6: DA + Plan-Track Review (execute full cycle per round)

#### 6a: DA Review
DA reviews the shipped code against:
- Code quality: correctness, security, maintainability
- Test integrity (build-directives §4d): behavior vs runs, requirements vs implementation, failure cases, hardcoded values, real infra vs mocks
- Scope compliance (§4a): built only what's in scope
- Gold-plating detection (§4c)
- XREVIEW findings (advisory, from C2 ## Build Status checkpoints)
- §2d source provenance audit — ALL agents (plan-track AND build-track). Not just those DA challenged.
  !rule: DA must verify |source:{type}| tags on build-track findings, not just plan-track.

#### 6b: Plan-Track Review (intent fidelity)
Plan-track agents review build for compliance with their C1 designs:
- tech-architect: implementations match ADRs? interface contracts correct? tech stack as designed?
- product-designer: UI follows design system? tokens correct? interaction patterns match IX[]? accessibility implemented?
- product-strategist: build addresses priority sequencing? success criteria achievable?
- Format: `"PLAN-REVIEW[{agent}]: {component} |compliance:{full|partial|drift} |issue:{description} |-> {accept|fix:{specific-change}}"`

#### 6c: §2h Cross-Model Verification (when sigma-verify available)
- Plan-track agents verify top 1 load-bearing compliance finding
- This is IN ADDITION to the code review (quality vs compliance are separate)
- !XVERIFY-mandatory-security-critical: sigma-verify available + security-critical ADR → XVERIFY MANDATORY on top-1

#### 6d: Build-Track Responds + Fixes
Build-track agents respond to review findings:
- DA challenges: `"DA[#N]: concede|defend|compromise — [evidence]"`
- Plan-track findings: `"PR[#N]: fixed|justified|deferred — [evidence]"`
- Implement agreed changes → run tests → re-submit for review

All findings written to scratch ## review-findings.

### Step 7: Validate Review Round
Verify all agents responded to DA challenges with concede/defend/compromise. Address any missing responses before proceeding.

### Step 8: Compute Belief State (HARD GATE)
Compute and write BELIEF state: `BELIEF[review-rN]: P={posterior} |-> {action}`

Write to scratch ## belief-tracking:
`"BELIEF[build-r{N}]: P={posterior} |plan-compliance={score} |test-coverage={score} |design-fidelity={score} |code-quality={score} |scope={clean|creep} |DA={grade} |-> {done|another-round({issues})|escalate}"`

!gate: BELIEF[] MUST be written to scratch workspace before advancing. Not optional. DA exit-gate grades are NOT a substitute. Hook will BLOCK advancement without BELIEF[] in workspace.

### Step 9: Check Exit Condition
- **P > 0.85 + DA PASS** → proceed to Step 10 (pre-synthesis validation)
- **P 0.6-0.85 or DA FAIL** + round < 5 → loop back to Step 6
- **P < 0.6** → activate Toulmin Debate (Step 9b), then loop back to Step 6
- **Round >= 5 (hard cap)** → proceed to Step 10 regardless

BUILD success criteria (check on exit):
- Zero architectural decisions during build that should have been in plan
- Plan-track confirms intent preserved (no silent drift)
- Scope creep caught at checkpoint, not at final review
- Test integrity catches >= 1 weak test pattern

#### Step 9b: Toulmin Debate (only if belief < 0.6)

Deep disagreement resolution via structured debate on contested decisions.

1. **Identify disagreement**: Read scratch for the specific decision(s) that drove belief below 0.6. Identify which agents are on opposing sides.

2. **Structure debate**: SendMessage to opposing agents with BUILD Toulmin format:
   ```
   Toulmin structured debate on: {specific decision}
   Present your position using:
   - CLAIM: your position
   - GROUNDS: evidence supporting it (benchmarks, precedent, constraints)
   - WARRANT: reasoning connecting evidence to claim
   - BACKING: additional support for warrant
   - QUALIFIER: degree of certainty (always, usually, possibly)
   - REBUTTAL: conditions under which your claim would be wrong
   ```
   BUILD-specific: DA attacks WARRANT ("is this tech really needed at this scale?") + QUALIFIER ("is the scale projection realistic or aspirational?")

3. **Monitor debate**: Wait for both sides to present. Facilitate one round of response to each other's rebuttals.

4. **Record resolution** to scratch:
   - If resolved: which position prevailed and why
   - If narrowed: what the remaining disagreement is
   - If unresolved: record both positions as open tension

5. Return to Step 6 for re-evaluation with debate resolution in context.

### Step 10: Pre-Synthesis Validation (only when exiting review loop)
Pre-synthesis checks: write CONTAMINATION-CHECK and SYCOPHANCY-CHECK to workspace.
This covers V13+V14+V15+V16. Address failures.

#### 10a: Anti-Contamination Check (HARD GATE)
1. Re-read scratch ## scope-boundary
2. Identify topics in this conversation OUTSIDE build scope
3. Write to scratch ## contamination-check:
   `CONTAMINATION-CHECK: session-topics-outside-scope: {list} |scan-result: clean|contaminated({terms})`
4. Write to scratch ## contamination-check:
   `SYCOPHANCY-CHECK: softened:{list|none} |selective-emphasis:{list|none} |dissent-reframed:{list|none} |process-issues:{list|none}`

!gate: BOTH checks MUST be written to scratch workspace. Not optional. Skipping = audit YELLOW.

#### 10b: BUILD Rubric Evaluation (final round only)
build-directives §3b:
1 → correctness | 2 → test-coverage | 3 → maintainability | 4 → performance | 5 → security | 6 → api-design

Write scores to scratch ## review-findings.

#### 10c: Build-Track Final Fixes
After DA + plan-track have issued all findings:
- Build-track agents apply agreed fixes
- Run full test suite — tests MUST pass before close-out
- If tests fail → fix and re-run. Do NOT proceed to Part B with failing tests.

Write final fix summary to scratch ## review-findings.

### Step 11: Write Build Review Summary to Plan File
Write to plan file ## Build Review Summary:
```markdown
## Build Review Summary (written by C3)
- DA challenges: {N} | DA grade: {grade}
- Plan compliance: {full|partial|drift}
- Test integrity findings: {count}
- BUILD rubric: correctness={score}/4 test-coverage={score}/4 maintainability={score}/4 performance={score}/4 security={score}/4 api-design={score}/4
- Contamination check: {clean|contaminated}
- Sycophancy check: {clean|findings}
- Review rounds: {N} | Final belief: P={X.XX}
- Fixes applied: {N} | Tests: {pass|fail}
```

### Step 12: Advance Out of Review

Update plan file: `build-exit-gate: PASS`, `build-belief: P={X.XX}`, `status: closing`.

---

## PART B: CLOSE-OUT

### Step 13: Synthesis (MANDATORY — lead MUST NOT write synthesis content)

#### Why This Gate Exists
You (the lead) have full conversation context — the user's goals, sidebar discussions, career concerns, everything outside the review scope. Agents analyzed with washed prompts behind a context firewall. If you write synthesis, you re-inject that context into output that appears "independently analyzed." This is provenance contamination. The user trusts washed-prompt output. Do not break that trust.

#### 13a: Gather Cross-Agent Intelligence
```
search_team_memory(team:sigma-review, query:{task-topic})
get_team_decisions(team:sigma-review)
get_team_patterns(team:sigma-review)
```

#### 13b: Identify Convergence and Tensions
Read scratch findings across all agents:
- Multi-agent same finding → convergence signal
- Conflicting findings → record both sides as tension
- New cross-agent patterns → store_team_pattern(agents:[names])

#### 13c: Spawn Synthesis Agent (MANDATORY)
Spawn a separate agent for synthesis. This agent has a separate context = separate context firewall.

Provide ONLY:
- Scratch workspace path (agent reads workspace directly)
- Plan file path (for context on scope, ADRs, etc.)
- Output format requirements from user

Do NOT provide:
- Conversation context
- User remarks or casual discussion
- Lead's interpretations
- Anything not in the workspace or plan file

#### 13d: Receive and Deliver Synthesis
When synthesis agent returns:
- Deliver document to user WITHOUT analytical modification
- Formatting adjustments OK (headers, tables)
- Analytical edits NOT OK (changing conclusions, adding probability estimates)

#### 13e: Handle Synthesis Agent Failure
If synthesis agent spawn fails:
1. Report: `"SYNTHESIS AGENT FAILED -- delivering raw agent findings without synthesized report."`
2. Deliver scratch workspace findings organized by section (formatting only)
3. Do NOT silently write synthesis yourself
4. Still save raw findings as synthesis artifact in Step 13f

#### 13f: Save Synthesis Artifact (V23 -- MANDATORY)
Write synthesis to: `shared/archive/{date}-{task-slug}-synthesis.md`

Required content:
- Prompt decomposition (Q/H/C from plan file ## Prompt Understanding)
- Findings organized by domain
- Cross-agent convergence and tensions
- DA challenges and resolutions
- BUILD rubric scores
- Pre-mortem failure modes (from plan file ## Pre-mortem)
- Open questions and unresolved gaps

This is the durable reference document. Session-end validation (V23) checks it exists.

#### 13g: Confirm Synthesis Complete
Verify synthesis artifact exists at `shared/archive/{date}-{task-slug}-synthesis.md` before proceeding to compilation.

### Step 14: Compilation (wiki integration — lead MUST NOT write wiki content)

Same provenance rule as synthesis — lead does NOT write wiki content. The wiki is the compounding asset. Individual reviews are snapshots; the wiki is the living picture.

#### 14a: Read Synthesis Artifact
Read the synthesis artifact saved in Step 13f:
`shared/archive/{date}-{task-slug}-synthesis.md`

#### 14b: Scan Existing Wiki
```bash
ls ~/.claude/teams/sigma-review/shared/wiki/
```
Read `shared/wiki/INDEX.md` to understand current wiki structure.

#### 14c: Spawn Compilation Agent (MANDATORY)
Spawn a compilation agent with:
- The synthesis artifact path
- The wiki directory path
- INDEX.md

Compilation agent instructions:
```
You are the sigma-review compilation agent. Your job: integrate new review findings into the persistent knowledge wiki.

## Inputs
- Synthesis artifact: {path} (this review's compiled findings)
- Wiki directory: ~/.claude/teams/sigma-review/shared/wiki/
- Wiki index: shared/wiki/INDEX.md

## Process
1. Read the synthesis artifact fully
2. Read INDEX.md to understand existing pages
3. For each significant finding, entity, or domain in the synthesis:
   a. Matching wiki page exists -> read it, update with new intelligence
   b. No matching page -> create one
4. Update INDEX.md with any new pages

## Page Update Rules
- ADD new findings with source attribution: [R{review-number}, {date}]
- If new finding CONTRADICTS existing content:
  flag both: "! CONFLICT: [R12] found X, but [R8] found Y. Unresolved."
  Do NOT silently overwrite -- contradictions are signal
- If new finding STRENGTHENS existing content:
  note convergence: "Confirmed [R12]: {finding} (also [R8])"
- PRESERVE all source attributions. Never strip review provenance.
- Write in plain prose. Wiki pages are reference documents, not SigmaComm.

## Page Structure Template
# {Page Title}
Last updated: {date} | Reviews: R8, R12

## Summary
{2-3 sentence overview -- updated with each review}

## Key Findings
{Organized by subtopic, each finding attributed to source review}

## Open Questions
{Unresolved from any review}

## Contradictions
{Where reviews disagree -- both positions preserved}

## Sources
{List of review artifacts that contributed to this page}

## What NOT to do
- Do not editorialize beyond what agents found
- Do not merge contradictions into a false consensus
- Do not create pages for process observations (those go in patterns.md)
- Do not duplicate patterns.md content -- this wiki is domain knowledge, not process knowledge
```

#### 14d: Review Compilation Output
Read what the compilation agent wrote/updated. Quick sanity check:
- Pages make sense as standalone reference documents
- Source attributions present
- No lead context leaked in

#### 14e: Update INDEX.md
Confirm INDEX.md reflects any new pages added.

#### 14f: Validate Compilation Integrity
Verify: wiki entries have `[R{N}, {date}]` attribution, no contradictions silently resolved, INDEX.md matches actual files.

This covers V24+V25+V26:
- V24: Source attribution on all wiki entries (`[R{number}, {date}]`)
- V25: No contradiction silently resolved (multi-source pages must have CONFLICT or Confirmed flags)
- V26: No wiki pages deleted (INDEX.md references match actual files)

If validation FAILS:
- V24 failure: compilation agent added unattributed findings → re-run compilation with explicit attribution instruction
- V25 failure: contradiction was silently merged → restore both positions with CONFLICT flag
- V26 failure: pages were deleted → investigate and restore from prior state

#### 14g: Confirm Compilation Complete
Verify all wiki pages pass integrity checks from 14f before proceeding to promotion.

### Step 15: Promotion (agents remain alive — do NOT shut them down)

Agents classify and submit generalizable learnings for persistent memory. This is how the team gets smarter across builds. Skipping this phase means the same mistakes repeat.

#### 15a: MCP Health Check
Before promotion (which writes to sigma-mem), verify MCP is still connected:
```
recall: "health check before promotion"
```
If this fails (MCP server disconnected): ask user to restart (`! claude mcp restart sigma-mem`).
Do NOT proceed with promotion until sigma-mem is responsive — promotion writes silently fail without it.

#### 15b: Trigger Promotion Round
SendMessage to each teammate:
```
promotion-round: classify+submit generalizable learnings for global memory
```

#### 15c: Wait for Responses
Each agent will:
- Auto-promote low-risk learnings directly to global memory
- Submit user-approve candidates to scratch ## promotion

Wait for all agents to respond with their promotion status.

#### 15d: Read Candidates
Read scratch `## promotion` section. Look for P-candidate[] entries with class:user-approve.

#### 15e: Present to User (if any user-approve candidates)
Present candidates in plain English:
```
## Promotion Candidates (require approval)
[CLASS] {agent}: {distilled finding} | Source: {project}
-> Approve / Reject

Also auto-promoted (informational):
{list of auto-promoted items}
```

**WAIT for user to approve/reject each candidate.**

#### 15f: Store Approved
For each approved candidate:
- Agent-domain → `store_agent_memory(tier:global, agent:{name}, team:sigma-review)`
- Team-level → `store_team_decision(tier:global)` or `store_team_pattern(tier:global)`

#### 15g: Portfolio Entry
Write {project-name} record to `shared/portfolio.md` (global tier).

#### 15h: Confirm Promotion Complete
Verify all promotion candidates have been resolved (approved/rejected/auto-promoted) before proceeding to sync.

### Step 16: Sync (optional backup)

The runtime home (`~/.claude/teams/sigma-review`) holds agent memory, shared decisions/patterns, the wiki and the archive. If it is a git repo (or `SIGMA_ARCHIVE_REPO` points at one), offer to commit it:

```
Commit this build's memory/archive changes? I can stage and commit, or you can review first.
```
Wait for the user → git add + commit if approved. Framework files (agent-defs/, shared/directives.md, shared/build-directives.md, shared/protocols.md, bin/) are managed by the plugin and refreshed on upgrade — do not hand-edit them.

Write `## sync: [templates-hashed:0|drift-detected:N|date:{YYYY-MM-DD}]` when done, or `## sync: [templates-hashed:0|skipped|reason:no-archive-repo|date:{YYYY-MM-DD}]` when there is no repo.

### Step 17: Archive

#### 17a: Archive Scratch Workspace
Copy scratch workspace to: `shared/archive/{date}-{task-slug}-c3-scratch.md`

Add header with review metadata:
```markdown
---
date: {date}
build-id: {build-id}
tier: BUILD TIER-{N}
agents: {list}
review-rounds: {N}
final-belief: P={X.XX}
build-exit-gate: {PASS|FAIL}
da-grade: {grade}
---
```

#### 17b: Verify Archive
Confirm:
- Archive file exists at expected path
- Archive contains scratch workspace content
- Archive is non-empty

#### 17c: Session End Validation
Verify: archive exists, synthesis artifact exists, git clean.

This covers V22+V23:
- V22: Archive exists + git repo has no uncommitted changes
- V23: Synthesis artifact exists

If validation fails:
- If uncommitted changes: offer to commit
- If synthesis artifact missing: this is a serious error — go back to Step 13f
- Re-run validation until it passes

#### 17d: Pre-Close Verification
Run `python3 ~/.claude/teams/sigma-review/bin/chain-evaluator.py evaluate` as formal pre-close verification. Address any FAIL items before committing.

### Step 18: Shutdown

**Only execute Step 18 after the chain evaluator reports all items complete. Run `python3 ~/.claude/teams/sigma-review/bin/chain-evaluator.py status` to verify.**

#### 18a: Verify Terminal State
```bash
python3 ~/.claude/teams/sigma-review/bin/chain-evaluator.py status
```
Confirm all chain components are complete. If any are incomplete, go back and complete whatever phase is current.

#### 18b: Write Close Status to Plan File
Write to plan file ## Close Status:
```markdown
## Close Status (written by C3)
- synthesis-artifact: {path}
- wiki-pages-updated: {list}
- promotions: {N approved}/{N candidates}
- sync: {status}
- archive: {path}
- status: complete
```

Update plan file: `status: complete`.

#### 18c: Shutdown Agents
SendMessage to each teammate:
```
shutdown_request
```
Wait for `shutdown_response` from each agent.

#### 18d: Handle Stragglers
If any agent does not respond within reasonable time:
- Check their scratch workspace section — did they complete their work?
- If yes: note forced shutdown in scratch convergence
- If no: flag incomplete work to user

#### 18e: Final Chain Evaluation
Run `python3 ~/.claude/teams/sigma-review/bin/chain-evaluator.py evaluate` -- chain must be complete before closing. Address any FAIL items before committing.

#### 18f: Final Report
Report to user in plain English. Include:
- Build summary (task, tier, agents, review rounds, final belief)
- DA summary (challenges, grade, key findings)
- Plan compliance (full/partial/drift, notable deviations)
- BUILD rubric scores
- Fix summary (what was fixed during review)
- Promotion summary (what was promoted, what was approved)
- Wiki compilation summary (pages updated/created)
- Sync summary (what was synced, commit status)
- Any open items or anomalies

```
Build review complete. Plan file: {plan_file} | Status: complete | Archive: {archive_path}
```

---

## C3 VERIFICATION (every item must be true before ending conversation)

### Part A: Review
- [ ] Plan file validated (status: built, all sections present)
- [ ] sigma-mem recalled
- [ ] DA + plan-track spawned and reviewed build
- [ ] Build-track responded to all findings
- [ ] All review rounds validated
- [ ] BELIEF[] written to scratch for EVERY round
- [ ] Exit condition met (P > 0.85 + DA PASS, or hard cap at 5 rounds)
- [ ] Pre-synthesis validation passed (V13+V14+V15+V16)
- [ ] Contamination + sycophancy checks written to scratch
- [ ] BUILD rubric evaluated (final round)
- [ ] Build-track applied fixes, tests pass
- [ ] Build Review Summary written to plan file
- [ ] Plan file updated: build-exit-gate PASS, status closing

### Part B: Close-out
- [ ] Synthesis agent spawned (NOT lead-written)
- [ ] Synthesis delivered to user
- [ ] Synthesis artifact saved to archive (V23)
- [ ] Compilation agent spawned (NOT lead-written)
- [ ] Wiki pages updated with source attribution [R{N}, {date}]
- [ ] Compilation validated (V24+V25+V26)
- [ ] MCP health check passed before promotion
- [ ] Promotion round triggered, all agents responded
- [ ] User approved/rejected promotion candidates (or none existed)
- [ ] Approved items stored to global memory
- [ ] Portfolio entry written
- [ ] Infrastructure drift detected and synced
- [ ] Commit offered and resolved
- [ ] Scratch workspace archived with metadata header
- [ ] Session-end validation passed (V22+V23)
- [ ] Chain evaluator passed (all components complete)
- [ ] Close Status written to plan file, status set to complete
- [ ] All agents shut down (or stragglers handled)
- [ ] Final report delivered to user
- [ ] Chain evaluator evaluate passed

**All items verified → cross-check against SKILL.md C3 Deliverables. Build is complete ONLY when the C3 Deliverables checklist is fully verified.**
