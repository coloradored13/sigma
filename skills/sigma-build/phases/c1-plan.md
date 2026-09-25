# Conversation 1: PLAN
**Every step below is mandatory. Complete them in order. A lead reading ONLY this file must know exactly what to do.**

C1 produces a locked plan file. No code is written. The plan file is the contract between conversations.

**Plan file location:** `~/.claude/teams/sigma-review/shared/builds/{date}-{task-slug}.plan.md`
**Scratch workspace:** `~/.claude/teams/sigma-review/shared/builds/{date}-{task-slug}/c1-scratch.md`

---

## PREFLIGHT (Steps 1-9)

### Step 1: Memory Recall
```
recall: "sigma-build task: $ARGUMENTS"
```
Ground context with team history, past patterns, relevant decisions.

### Step 2: System Validation
```
validate_system(team:sigma-review) → confirm defs+memory+inboxes
```
Verify agent definitions, memory files, and inbox files exist and are readable.

### Step 3: Sigma-Verify Availability
```
sigma-verify init → check cross-model verification availability
```
- Log available providers (e.g. openai:gpt-5.4)
- Report: `"ΣVerify: {providers} available"` or `"ΣVerify: unavailable (no API keys)"`
- ¬blocking: build proceeds without cross-model verification if unavailable
- Record availability — write to scratch workspace in Step 11

### Step 4: Read Roster
```
read: ~/.claude/teams/sigma-review/shared/roster.md
```

### Step 5: Complexity Assessment
Per build-directives §3a BUILD complexity tiers:
```
evaluate: module-count(1-5), interface-changes(1-5), test-complexity(1-5), dependency-risk(1-5), team-familiarity(1-5)
sum < 12 → TIER-1 (3+DA)
12-18    → TIER-2 (4-5+DA)
>18      → TIER-3 (6-9+DA)
```
Tier composition:
- TIER-1: plan-track(tech-architect) + build-track(primary-builder + reviewer) + DA
- TIER-2: plan-track(tech-architect + product-designer) + build-track(2-3 builders) + DA
- TIER-3: plan-track(tech-architect + product-designer + product-strategist) + build-track(3-5 builders + integration-specialist) + DA

### Step 6: Semantic Route
Match task → agent domains from roster.

### Step 7: Report + User Confirmation
Report to user:
```
"Complexity: BUILD TIER-{N} (score:{sum}/25). Waking {agents}: {reasons}"
```
**WAIT for user confirmation before proceeding.** Do not spawn agents without approval.

### Step 7a: Premise-Audit Pre-Dispatch (HARD GATE — §2p)

Per directives.md §2p (build-directives.md §2p BUILD variant), lead answers PA[1-4] BEFORE re-reading user's proposed H-space in Step 8. **Sequence is load-bearing** — reversing recreates the frame-anchoring that §2p prevents (R19 evaluator: premises "accepted as frame" before H[] dispatch).

!applies-to: ALL sigma-build tasks (TIER-1/2/3)
!sequence-constraint: PA[1-4] answered from user prompt ALONE — do NOT re-read user's proposed tiers/frameworks/H-space until Step 7a is complete
!scope: STRUCTURAL premises ¬domain-depth (domain → §2e+DA in agent analysis)

4 structural premise tests (BUILD-scoped per build-directives.md §2p):
- PA[1]: tech-tier-necessity — is proposed architecture tier NECESSARY or is simpler stack adequate? (monolith vs microservices vs serverless vs event-driven)
- PA[2]: scale-floor — minimum viable user/request volume? State explicitly — ¬assume 10K+ from prompt framing.
- PA[3]: data-readiness — what integration points/datasets must exist for build to deploy usefully? Gap? yes/no.
- PA[4]: precedent-baseline — RC[{similar-build-in-stack}]={typical-duration} | above/at/below base-rate?

Write PREMISE-AUDIT result to scratch workspace `## premise-audit-results` section (populated in Step 10 template) using workspace_write() helper per IC[6]:
```
PREMISE-AUDIT[pre-dispatch]:
  PA[1]: tech-tier-necessity: {CONFIRMED|CHALLENGED|GAP} — {one-sentence rationale}
  PA[2]: scale-floor: {minimum-volume} | {assumption-stated}
  PA[3]: data-readiness: {required-preconditions} | gap:{yes/no}
  PA[4]: precedent-baseline: RC[{class}]={rate} | above/at/below base-rate
  → proceed-with-H | revise-H-space({N}) | flag-premise({N})
```

!rule: CHALLENGED/GAP on PA[1] or PA[2] → revise scope-boundary + Q[] BEFORE advancing to Step 8 (¬spawn agents with contested structural premise)
!rule: CHALLENGED on PA[3] or PA[4] → convert to explicit H[] for agents to test in Step 8
!rule: decision line (→ proceed|revise|flag) is REQUIRED — chain-evaluator presence check BLOCKs on missing `## premise-audit-results` section (PM[3] mitigation, BLOCK day-one per DA[#6]-b resolution)
!rule: DA receives PREMISE-AUDIT in r2 (Step 18) — checks agents ¬re-anchored on CHALLENGED premises

Report: `"PREMISE-AUDIT: PA[1]:{status} |PA[2]:{status} |PA[3]:{status} |PA[4]:{status} |→ {decision}"`

### Step 8: Prompt Understanding (HARD GATE)
sigma-build is self-contained. Any prompt enters here and gets broken down before agents see it.

a) EXTRACT from user prompt:
   - Q[]: what needs to be built (define build scope)
   - H[]: claims/assumptions about scale, tech, architecture (become hypotheses to test ¬requirements)
   - C[]: constraints/boundaries (stack, timeline, scope limits)
   - BUILD detection heuristics for H[]:
     - scale assumptions without evidence
     - technology assertions ("we need microservices")
     - user behavior claims ("primarily mobile")
     - performance requirements without measurement
     - architecture claims ("monolith won't scale")

b) CHALLENGE (lead pushes back before agents spawn):
   - Each H[]: "You assume X — validated or aspirational? What evidence?"
   - Scope: "X, Y, Z — all in scope, or should we phase?"
   - Feasibility: "Obvious blockers? Does the codebase support this?"
   - Prior art: if prompt references existing code, read it to verify claims match reality

c) CLARIFY (lead asks for missing info):
   - Ambiguous terms, missing context, success criteria, users

d) USER CONFIRMS refined Q[]/H[]/C[]
   !gate: user confirms BEFORE spawning agents
   !gate: confirmed understanding written to scratch workspace ## prompt-understanding BEFORE spawn

Report: `"PROMPT-UNDERSTANDING: Q:{count} |H:{count}(challenged:{count}) |C:{count} |clarifications:{count} |user-confirmed: {yes/pending}"`

### Step 9: Cost Estimate
- Anthropic: {agent-count} agents x ~{rounds} rounds x ~2K tokens/round x pricing
- sigma-verify (if available): {agent-count} x {providers} XVERIFY calls x ~1K tokens each
- Estimated total: report to user
- If estimated > $10: warn user, get confirmation

### Preflight Phase Verification

- [ ] Memory recall completed
- [ ] System validation passed
- [ ] Sigma-verify status recorded
- [ ] Roster read
- [ ] Complexity tier assessed and reported
- [ ] Agent selection reported to user
- [ ] User confirmed agent selection
- [ ] **Step 7a premise-audit (§2p): PA[1-4] answered BEFORE Step 8 H-space re-read** — sequence-constraint enforced
- [ ] **Step 7a decision line recorded** (→ proceed | revise | flag) — chain-evaluator BLOCKs on missing `## premise-audit-results` section
- [ ] Prompt understanding (Q/H/C) completed with challenge + clarify
- [ ] User confirmed prompt understanding
- [ ] Cost estimate reported (and confirmed if > $10)

**All items verified → continue to SPAWN (C1 not complete — see SKILL.md C1 Deliverables)**
**Any item not verified → resolve it before continuing**

---

## SPAWN (Steps 10-12)

### Step 10: Initialize Scratch Workspace
Create directory and scratch file at `~/.claude/teams/sigma-review/shared/builds/{date}-{task-slug}/c1-scratch.md`:

```markdown
# C1 scratch — BUILD: {task-slug}
## status: active
## mode: BUILD

## task
{task description}

## infrastructure
ΣVerify: {status from preflight step 3}

## prompt-understanding
{Q/H/C from preflight step 8 — copy exactly as user confirmed}

## premise-audit-results
PREMISE-AUDIT[pre-dispatch]:
  PA[1]: tech-tier-necessity: {CONFIRMED|CHALLENGED|GAP} — {one-sentence rationale}
  PA[2]: scale-floor: {minimum-volume} | {assumption-stated}
  PA[3]: data-readiness: {required-preconditions} | gap:{yes/no}
  PA[4]: precedent-baseline: RC[{class}]={rate} | above/at/below base-rate
  → proceed-with-H | revise-H-space({N}) | flag-premise({N})
(populated by lead in Step 7a BEFORE agent spawn — chain-evaluator BLOCKs on missing decision line)

## scope-boundary
This build implements: {phase description, specific features}
This build does NOT implement: {future phases, nice-to-haves, features not in spec}
Lead: before accepting agent output, verify it builds ONLY what's in scope.

## complexity-assessment
BUILD TIER-{N} |scores: module-count({N}),interface-changes({N}),test-complexity({N}),dependency-risk({N}),team-familiarity({N}) |total:{sum} |plan-track:{N} |build-track:{N}

## plans (plan-track agents)
### tech-architect
### product-designer
### product-strategist

## architecture-decisions (locked after DA approval)
{ADR[N]: decision |alternatives:{considered} |rationale:{why} |prompted-by:{Q[N]/H[N]/C[N]}}

## design-system (locked after DA approval)
{DS[]: design tokens, component hierarchy, interaction patterns, responsive strategy}

## interface-contracts (build-track implements against these)
{IC[]: typed contracts between components}

## sub-task-decomposition
{SQ[N]: task |owner:{role} |est:{} |files:{}}

## pre-mortem
{PM[N]: failure mode |likelihood:{} |mitigation:{}}

## files
| File | Action | Description |

## convergence

## belief-tracking

## gate-log

## open-questions
```

### Step 11: Spawn Plan-Track + Build-Track Agents via the Agent tool
For each agent selected in preflight:

1. Read `~/.claude/teams/sigma-review/agent-defs/{name}.md` → extract Role + Expertise
2. Read `~/.claude/teams/sigma-review/agent-defs/sigma-comm.md` → extract Codebook section
3. Select model tier (per build-directives §5 / directives §5a):
   - DA: model="opus" | domain agents: model="sonnet"
   - use the family alias, ¬a pinned dated ID or `[1m]` suffix (see sigma-lead.md Model selection)
4. Compose spawn prompt using template (see below)
5. Spawn via `Agent({name: "{agent-name}", model: "{tier}", prompt: "{composed prompt}"})`

!rule: `TeamCreate`/`TeamDelete` no longer exist (removed in Claude Code v2.1.178). A NAMED `Agent` call
  launches as a teammate when `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set (settings.json env); an
  unnamed one is an ordinary subagent that returns its result and cannot be messaged. Build-track agents
  MUST be named — c2-build.md addresses them by name via SendMessage.
!rule: the idle notification carries no output. Read the agent's scratch section, ¬the notification.

**Do NOT spawn DA in this phase.** DA joins in Step 18 (plan challenge).

### Spawn Prompt Template

```
You are {name} on the sigma-build team.
Role: {from agent definition — plain English}
Expertise: {from agent definition — plain English}

## ΣComm Protocol
Messages use compressed notation. Format: [STATUS] BODY |¬ not-found |→ can-do-next |#count
Status: ✓=done ◌=progress !=blocked ?=need-input ✗=failed ↻=retry
Body: |=sep >=pref →=next +=and !=critical ,=items
¬=explicitly NOT (prevents assumptions)
→=available actions (HATEOAS: what you can do based on current state)
#N=item count (checksum: verify you decoded correctly)
Parse incoming ΣComm messages by expanding notation. Send responses in ΣComm.
If ambiguous, ask sender to clarify rather than assuming.

## Paths [T=~/.claude/teams/sigma-review P={project}/.claude/teams/sigma-review]
global: T/shared/roster.md | T/agents/{name}/memory.md
project(has_project_tier): P/shared/{workspace,decisions,patterns}.md | P/agents/{name}/memory.md
fallback(!has_project_tier): all→T/

## Boot (FIRST — before any work)
1. recall: "I am {name} on sigma-build. Task: {task-description}"
2. boot-pkg→ global_mem+project_mem+decisions+workspace | check has_project_tier
3. follow navigation_hints→ load additional context
4. read scratch workspace→ understand task+peer plans

## Task
{task description}

## Scope
{agent-specific scope — what this agent produces given the task}

## Context Firewall
You are planning ONLY: {task description}
This build does NOT implement: {future phases, out-of-scope features from workspace scope-boundary}
You have NO knowledge of: the user's career plans, other projects discussed outside this build,
prior reviews in this session, or any conversation between the user and lead that is not in
your workspace task description. If you encounter information that seems outside your build
scope, ignore it and note: "out-of-scope signal ignored: {brief description}"

## Prompt-Decomposition Context
Claims H1-HN are user hypotheses extracted from the prompt. Test these — find evidence FOR and AGAINST.
Do ¬assume they are true. If a claim (e.g. scale, tech choice) drives architectural decisions,
flag: "H[N] assumption used — ¬independently validated" and cite the specific choice it affects.

## ΣVerify Init (MANDATORY pre-ToolSearch — §2h belt-and-suspenders)
before any ToolSearch or sub-tool call: invoke mcp__sigma-verify__init {} once.
  !purpose: hateoas-agent state-gates verify_finding/cross_verify/challenge behind init transition.
    R19 #3 failure mode: 5/5 agents skipped init → 5 XVERIFY-FAIL.
  !redundant-with: machine.py auto-ready (TA ADR[1]) — spawn-prompt call is belt-and-suspenders per DA[#2] compromise + SS ADR[2].
  !if-unavailable: init returns ¬providers → proceed without XVERIFY (all findings carry no-tag, neutral per §2h).
  !do-NOT-retry: one init call per session; subsequent tool calls succeed idempotently.

## Workspace Write Rules (¬sed -i, atomic-Python-replace, section-isolation)
!rule: ¬sed -i on workspace files or sigma hook files — phase-gate enforces the sed-i BLOCK mechanically.
  observed: R19 #1 `sed -i ''` silent corruption → 4 agent sections lost mid-R1.
  canonical: Edit tool OR workspace_write() helper per IC[6].
!rule: section-isolation convention — write ONLY to your own ### {agent-name} section.
  lead writes ## sections (convergence, gate-log, open-questions, peer-verification-index).
  cross-section writes → SendMessage lead, request authorization.
!rule: workspace_write(path: str, old_anchor: str, new_content: str) -> None helper per IC[6]:
  atomic Python replace; raises WorkspaceAnchorNotFound on anchor miss (anchor = section header + first unique line).
  use for workspace.md + builds/*/*.md + shared/workspace.md writes.
  Edit tool is acceptable fallback for out-of-workspace files (directives, agent-defs, hooks).

## Rate Limits
shared API: 1K RPM + 90K output tok/min across all agents. rate-limit-error→backoff 10s, max 3 retries/60s.

## Peer Verification Assignment
After completing your findings + analytical hygiene, verify {peer-name}'s workspace section.
Write a section with this EXACT header format (chain-evaluator A16/A17/A18 regex match):
```
### Peer Verification: {your-name} verifying {peer-name}
```
!rule: 3-hash header, the word "verifying" between names, lowercase. ¬4-hash, ¬"verifies".
!rule: reference ≥3 specific artifact IDs (DB[], F[], XVERIFY[], H[]) — generic "looks good" fails A17 specificity check.
!rule: per-item PASS|FAIL|N/A verdicts with evidence — NOT a narrative summary.
See your ## Peer Verification instructions in the agent template for the full checklist protocol.
Your chain is incomplete without this verification (A16).

## Work
{select track based on agent role — lead includes ONLY the relevant section}

### PLAN-TRACK (tech-architect, product-designer, product-strategist)
1→READ: prompt understanding (scratch ## prompt-understanding) + codebase analysis
2→DESIGN: write plan to scratch ## plans section (ΣComm)
  tech-architect: ADR[N] architecture decisions, IC[N] interface contracts, tech stack
  product-designer: DS[] design system, IX[N] interaction patterns, component tree
  product-strategist: priority sequencing, user-segment constraints, success criteria
  all: SQ[] sub-task decomposition, CAL[] estimates, PM[] pre-mortem, prompt-understanding mapping
  all: §2a/§2b/§2c/§2e analytical hygiene checks (each produces outcome 1/2/3)
3→RESPOND TO CHALLENGES: DA + build-track will challenge your plan
  DA challenges: "DA[#N]: concede|defend|compromise — [evidence]"
  build challenges: "BC[#N]: concede|defend|compromise — [evidence]"
4→REFINE: if P(plan-ready) < 0.85, revise plan based on challenge outcomes → iterate
5→LOCK: when P(plan-ready) > 0.85, finalize to scratch workspace
6→PERSIST + EXIT: plan-track exits after plan locked.

### BUILD-TRACK (implementation-engineer, ui-ux-engineer, code-quality-analyst)
PLAN CHALLENGE ONLY — build-track evaluates plan for feasibility in C1:
1→READ: scratch ## plans, ## architecture-decisions, ## design-system, ## interface-contracts
2→CHALLENGE: evaluate plan for implementability
  format: "BUILD-CHALLENGE[{name}]: {plan-element} |feasibility:{H/M/L} |issue:{description} |→ {revise|clarify|accept}"
  Every finding MUST include |source:{type}| tag. Types: [code-read file:line] | [agent-inference] | [cross-agent]
3→ITERATE: plan-track refines → you re-evaluate
```

### Step 12: Verify Spawn
Confirm all agents spawned successfully. For any failed spawn: retry once, report to user if retry fails.

### Spawn Phase Verification

- [ ] Scratch workspace written with all required sections
- [ ] Prompt understanding in scratch matches user-confirmed version
- [ ] All selected plan-track agents spawned
- [ ] All selected build-track agents spawned (for feasibility challenge)
- [ ] DA NOT spawned (DA joins in plan challenge)
- [ ] Spawn failures handled

**All items verified → continue to PLAN (C1 not complete — see SKILL.md C1 Deliverables)**

---

## PLAN (Steps 13-17)

### Step 13: Monitor Agent Progress
Poll scratch workspace ## plans section. For each plan-track agent, track status:
- ◌ (in progress) → wait
- ? (needs input) → surface question to user → write answer to inbox
- ! (blocked) → surface blocker to user
- ✓ (plan written) → proceed to Step 14 verification

### Step 14: Pre-Accept Verification (per agent declaring plan complete)
Before accepting any agent's plan output:
1. Verify their scratch ## plans section is NOT empty
2. Check required outputs per agent role:
   - tech-architect: ADR[N] + IC[N] + tech stack decisions
   - product-designer: DS[] + IX[N] + component tree
   - product-strategist: priority sequencing + success criteria
   - all: SQ[] + CAL[] + PM[] (min 3) + prompt-understanding mapping
3. Check: has agent persisted memory? (`get_agent_memory`)
4. If plan incomplete: SendMessage to agent with specific missing items

### Step 15: Verify XVERIFY Coverage (mandatory-when-available for security-critical)
Each plan-track agent MUST verify top 1 load-bearing decision:
- tech-architect: top ADR (highest reversal cost)
- product-designer: top design system decision
- product-strategist: top priority sequencing assumption

Security-critical ADRs (IP normalization, permission architecture, injection defense, trust boundaries):
- ΣVerify available → XVERIFY MANDATORY on top-1 security-critical ADR. Not advisory.
- ΣVerify available + non-security ADR → advisory (recommended, not required)
- ΣVerify unavailable → neutral, no penalty

If XVERIFY missing on any agent: SendMessage reminder before advancing.
If XVERIFY missing on security-critical ADR with ΣVerify available: DO NOT advance. Hard gate.

### Step 16: Wait for All Plan-Track Agents
Do not proceed until ALL plan-track agents have:
- Written complete plan output to scratch workspace
- Persisted memory
- Declared ✓ in convergence section

### Step 17: Lead Confirms Cross-Agent Coherence
Before advancing, verify:
- Interface contracts <> design system alignment
- Data model <> UI data flow consistency
- Dependency ordering makes sense

Flag any misalignment in scratch ## open-questions for challenge phase.

### Plan Phase Verification

- [ ] All plan-track agents wrote non-empty plans
- [ ] Required outputs present per agent role
- [ ] XVERIFY coverage checked (when available)
- [ ] All agents persisted memory
- [ ] Cross-agent coherence verified

**All items verified → continue to PLAN CHALLENGE (C1 not complete — see SKILL.md C1 Deliverables)**

---

## PLAN CHALLENGE (Steps 18-26)

**This section may loop. Complete the full cycle each round.**

### Step 18: Spawn DA (first entry only)
On first entry to this phase:
1. Read `~/.claude/teams/sigma-review/agent-defs/devils-advocate.md`
2. Spawn DA via `Agent({name: "devils-advocate", model: "opus", prompt: ...})`
3. DA reads scratch workspace (plans, ADRs, design system, interface contracts)

If already in a loop (round 2+), DA is already alive — skip to Step 19.

### Step 19: DA + Build-Track Challenge Round
DA challenges:
- Over-engineering, spec drift, assumption conflicts, premature abstraction
- Prompt-understanding alignment: do plans address Q[]/H[]/C[]?
- Source-provenance audit (§2d)
- Prompt audit (§7d): were BUILD claims from prompt tested or assumed?

Build-track challenges (feasibility focus):
- "Can I actually build this?" — framework constraints, complexity
- Interface contract feasibility, design system feasibility
- Effort reality: are CAL[] estimates realistic?
- Format: `"BUILD-CHALLENGE[{agent}]: {plan-element} |feasibility:{H/M/L} |issue:{description} |→ {revise|clarify|accept}"`

### Step 20: Zero-Dissent Circuit Breaker (MANDATORY after first challenge round)
After receiving first round of challenges from DA + build-track:

**If zero pushback (all accept, no challenges):**
1. Report: `"Zero-dissent on plan: {N} reviewers, 0 challenges. Firing circuit breaker."`
2. Send targeted self-challenge to EACH reviewer:
   ```
   zero-dissent circuit breaker: your feasibility assessment of [{highest-risk plan element}] agrees with all peers.
   (1) Name the strongest reason this plan could fail in implementation.
   (2) If that failure occurs, what would you change?
   (3) Identify ONE interface contract or design spec you'd challenge.
   ```
3. Wait for responses, read additions.

**If challenges found:** Log divergence to scratch workspace, proceed to Step 21.

### Step 21: Validate Circuit Breaker
Check workspace for divergence or CB[] entries. Verify the scratch workspace ## convergence section contains either:
- CB[] entries documenting circuit breaker responses (if zero-dissent fired), or
- Logged divergence from the challenge round

Address failures before advancing.

### Step 22: Plan-Track Responds
Plan-track agents respond to both DA and build-track:
- DA challenges: `"DA[#N]: concede|defend|compromise — [evidence]"`
- Build challenges: `"BC[#N]: concede|defend|compromise — [evidence]"`

Monitor scratch workspace for updates. Allow inter-agent interaction.

### Step 23: Validate Challenge Round
Verify all agents responded with concede/defend/compromise for each challenge:
- Every DA challenge has a `DA[#N]: concede|defend|compromise` response from a plan-track agent
- Every BUILD-CHALLENGE has a `BC[#N]: concede|defend|compromise` response from a plan-track agent
- No challenges are left unaddressed in the scratch workspace

Address any failures.

### Step 24: Compute Belief State (HARD GATE — must write to scratch workspace)
Compute and write BELIEF state to scratch ## belief-tracking:
`"BELIEF[plan-r{N}]: P={posterior} |builder-feasibility={score} |interface-agree={score} |design-arch={score} |conflicts={none|count} |review-coverage={score} |DA={grade} |→ {lock-plan|another-round({gaps})|Toulmin-debate}"`

!gate: BELIEF[] MUST be written to scratch workspace before advancing. Not optional. DA exit-gate grades are NOT a substitute.
If |declared - computed| > 0.15: must justify divergence.

### Step 25: Check Exit Condition
- **P > 0.85 + DA PASS** → lock plan, proceed to Step 26
- **P 0.6-0.85 or DA FAIL** + round < 5 → loop back to Step 19
- **P < 0.6** → proceed to DEBATE (Step 27)
- **Round >= 5 (hard cap)** → lock plan, proceed to Step 26

### Step 26: Lock Plan (only when exiting to Outcome Delivery)
Lock ADRs, design system, interface contracts in scratch workspace.

Verify plan lock: confirm ADR[], IC[], SQ[] entries exist in the scratch workspace locked sections.
- At least 1 ADR[] with alternatives + rationale
- At least 1 IC[] with typed contract
- At least 1 SQ[] with owner + files
If any are missing: plan-track agents complete missing output.

!rule: plan-track and build-track agents exit after plan locked.

**Plan locked → proceed to Outcome Delivery**
**Looping → re-execute from Step 19**
**Belief < 0.6 → proceed to DEBATE**

### Plan Challenge Phase Verification (when leaving this section)

- [ ] DA spawned and participated
- [ ] Circuit breaker checked (mandatory after first round)
- [ ] All challenge rounds validated
- [ ] Belief state computed and written to scratch workspace for each round
- [ ] Exit condition met (PASS, hard cap, or debate)
- [ ] If exiting: plan locked, plan-lock validation passed

---

## DEBATE (Steps 27-31) — optional, only if belief < 0.6

**This section only activates when belief < 0.6 during plan challenge.**

### Step 27: Identify Disagreement
Read scratch workspace for the specific architecture decision(s) that drove belief below 0.6. Identify which agents are on opposing sides.

### Step 28: Structure Debate
SendMessage to opposing agents with BUILD Toulmin format:
```
Toulmin structured debate on: {specific architecture decision}
Present your position using:
- CLAIM: your architecture position
- GROUNDS: evidence supporting it (benchmarks, precedent, constraints)
- WARRANT: reasoning connecting evidence to claim
- BACKING: additional support for warrant
- QUALIFIER: degree of certainty (always, usually, possibly)
- REBUTTAL: conditions under which your claim would be wrong
```

BUILD-specific: DA attacks WARRANT ("is this tech really needed at this scale?") + QUALIFIER ("is the scale projection realistic or aspirational?")

### Step 29: Monitor Debate
Wait for both sides to present. Facilitate one round of response to each other's rebuttals.

### Step 30: Record Resolution
Write debate outcome to scratch workspace:
- If resolved: which position prevailed and why
- If narrowed: what the remaining disagreement is
- If unresolved: record both positions as open tension

### Step 31: Return to Plan Challenge
After debate, return to Step 19 (plan challenge) for re-evaluation with the debate resolution factored in.

### Debate Phase Verification

- [ ] Disagreement identified and articulated
- [ ] Both sides presented Toulmin-structured arguments
- [ ] Response round completed
- [ ] Resolution/outcome recorded in scratch workspace
- [ ] Returned to plan challenge for re-evaluation

---

## OUTCOME DELIVERY (Steps 32-38)

**The analysis is the output. This section is the outcome. Output without outcome is worthless.**

The plan file is the LAST artifact written — it cannot exist until promotion, archive, and verification are complete. The session is not done when the plan locks. The plan locking is the midpoint. The complete delivery chain is: exit-gate verification → agent memory persistence → archive → plan file → validation → report. Any missing component is a failure.

### Step 32: Verify Plan Exit Gate
Confirm:
- plan-exit-gate: PASS (P > 0.85 + DA PASS, or round >= 5 hard cap)
- BELIEF[] written to scratch workspace for every challenge round
- Plan-lock validation passed (ADR[], IC[], SQ[] entries confirmed)

### Step 33: Agent Memory Persistence (Promotion)
**This step is PRIMARY WORK, not cleanup. Agent learnings that compound across sessions are the system's durable value.**

**MCP health check (before promotion):**
```
recall: "health check before promotion"
```
If sigma-mem MCP is disconnected: ask user to restart. Do NOT proceed with promotion until sigma-mem is responsive — promotion writes silently fail without it. If MCP is unavailable and user declines restart, proceed without promotion (write note to scratch: "MCP unavailable — learnings deferred to next session").

Each agent persists to sigma-mem:
- DA: calibration data (challenge count, grade, hit rate, concession/defense ratio, process patterns)
- Plan-track: architectural patterns, decision rationale worth preserving, self-corrections
- Build-track: feasibility insights, measurement patterns, codebase state observations

Persist generalizable patterns and calibration. Build-specific details live in the plan file.

!gate: Do NOT proceed to Step 34 until every agent has completed persistence. Verify by reading sigma-mem for new entries from this session's agents. If an agent was shut down before persisting, the lead persists their key learnings from the scratch workspace (with source attribution to the agent).

### Step 34: Archive Scratch Workspace + Copy to Archive
Two actions, both required:

1. Mark scratch workspace status:
```
~/.claude/teams/sigma-review/shared/builds/{date}-{task-slug}/c1-scratch.md
→ mark ## status: archived-c1
```

2. Copy to archive directory for audit access:
```
cp {scratch} ~/.claude/teams/sigma-review/shared/archive/{date}-{task-slug}-workspace.md
```

3. Update archive INDEX.md with this session's entry.

!gate: Do NOT proceed to Step 35 until archive copy exists AND INDEX.md is updated. An analysis that can't be audited or recreated is garbage.

### Step 35: Write Plan File
**This is the LAST analytical artifact, not the first. It can only be written after promotion and archive are complete.**

Create `~/.claude/teams/sigma-review/shared/builds/{date}-{task-slug}.plan.md` with the following structure. Distill agent plans from scratch workspace into clean locked sections:

```markdown
# sigma-build plan: {task-slug}

## Meta
- created: {date}
- build-id: {date}-{task-slug}
- tier: BUILD TIER-{N}
- status: plan-locked
- plan-exit-gate: PASS
- plan-belief: P={final belief}
- build-exit-gate: PENDING
- build-belief: P=0.00

## Context
{Distilled task description — what and why, not the full prompt}

## Prompt Understanding
Q[]: ... | H[]: ... | C[]: ...

## Scope Boundary
Implements: ... | Does NOT implement: ...

## Architecture Decisions (locked)
ADR[N]: {decision} |alternatives:{considered} |rationale:{why} |source:{}

## Interface Contracts (locked)
IC[N]: {typed contract}

## Sub-task Decomposition
SQ[N]: {task} |owner:{role} |est:{} |files:{}

## Pre-mortem
PM[N]: {failure mode} |likelihood:{} |mitigation:{}

## Files
| File | Action | Description |

## Plan Challenge Summary
- DA challenges: {N} | DA grade: {grade}
- CB: {fired|not-needed} | Concessions/Defenses: {N}/{N}
- Unresolved tensions: {list or none}

## Build Status
{empty — written by C2}

## Build Review Summary
{empty — written by C3}

## Close Status
{empty — written by C3}

## Verification
{How to test the changes end-to-end}
```

### Step 36: Validate Plan File + Outcome Chain Completeness
Before proceeding, verify the COMPLETE delivery chain:

Outcome chain (must all be YES):
- [ ] Agent memories persisted to sigma-mem (Step 33 complete)
- [ ] Scratch workspace archived + copied to archive directory (Step 34 complete)
- [ ] Archive INDEX.md updated (Step 34 complete)

Plan file content (must all be present):
- [ ] All Meta fields populated (status = plan-locked, plan-exit-gate = PASS)
- [ ] Context section non-empty
- [ ] Prompt Understanding matches user-confirmed Q/H/C
- [ ] Scope Boundary has both Implements and Does NOT implement
- [ ] At least 1 ADR with alternatives + rationale
- [ ] At least 1 IC with typed contract
- [ ] At least 1 SQ with owner + files
- [ ] At least 3 PM entries
- [ ] Files table populated
- [ ] Plan Challenge Summary with DA grade + CB status
- [ ] Build Status, Build Review Summary, Close Status present (empty placeholders)

If any outcome chain item is NO: go back and complete it. Do NOT skip.
If any plan file section is missing: go back and fill it from scratch workspace content.

### Step 37: Report to User
```
"Plan locked: {task-slug}
 Tier: BUILD TIER-{N} | Belief: P={final} | DA: {grade}
 ADRs: {N} | ICs: {N} | SQs: {N} | PMs: {N}
 Challenges: {N} DA + {N} build-track | CB: {fired|not-needed}
 Plan file: ~/.claude/teams/sigma-review/shared/builds/{date}-{task-slug}.plan.md
 
 Outcome chain: promotion({status}) | archive({status}) | plan-file({status})
 
 Run `/sigma-build {task}` to start build (C2)."
```

### Step 38: C1 Delivery Verification

- [ ] Plan-exit-gate PASS confirmed
- [ ] BELIEF[] present in scratch for every round
- [ ] Agent memories persisted to sigma-mem (promotion complete)
- [ ] Scratch workspace archived + copied to archive directory
- [ ] Archive INDEX.md updated
- [ ] Plan file written with all sections populated
- [ ] Plan file validated for completeness
- [ ] User report delivered with outcome chain status

**C1 is complete ONLY when every item above is verified. Cross-check against SKILL.md C1 Deliverables before ending this conversation.**

Run `python3 ~/.claude/teams/sigma-review/bin/chain-evaluator.py status` before ending C1 to verify chain completeness.

**C1 complete. Conversation ends here. C2 starts in a new conversation.**
