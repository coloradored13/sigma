# sigma-build directives

> Extracted from directives.md on 2026-03-19.
> BUILD mode operates independently from sigma-review ANALYZE mode.
> ANALYZE mode directives → ~/.claude/teams/sigma-review/shared/directives.md
> BUILD orchestration → /sigma-build skill 
> DA agent definition → ~/.claude/teams/sigma-review/agent-defs/devils-advocate.md (serves both modes)

## adversarial-layer BUILD mode (26.3.11, extracted 26.3.19)

### BUILD round structure

Two-phase dynamic model with cross-track review. Each phase iterates until Bayesian confidence.

plan-track agents: tech-architect(primary), product-designer(primary), product-strategist(advisory)
build-track agents: implementation-engineer(primary), ui-ux-engineer(primary), code-quality-analyst(primary)
DA: spans both phases (challenges in plan phase, reviews in build phase)
cross-track: build-track challenges plan feasibility | plan-track reviews build fidelity

PHASE 1 — PLAN (iterates until P(plan-ready) > 0.85, max 5 rounds):
  plan round: plan-track agents design (tech arch + UX/UI arch + strategy)
    → ADRs, interface contracts, design system, priority sequencing
    → SQ[] decomposition, CAL[] estimates, PM[] pre-mortem, prompt-understanding mapping
    → DA observes ¬participates
  challenge round: DA + build-track evaluate plan together
    → DA: over-engineering, spec drift, assumption conflicts, prompt-understanding alignment
    → build-track: feasibility, framework constraints, effort reality
    → plan-track responds to both, refines
    → lead computes P(plan-ready) → iterate or lock
  architect exit: plan locked → plan-track exits, re-spawns for build review

PHASE 2 — BUILD (iterates until P(build-quality) > 0.85, max 5 rounds):
  build round: build-track implements against locked plan
    → CHECKPOINT at ~50%: status/drift/surprises to workspace
  cross-model review: ΣVerify code review (advisory, when available)
  review round: DA + plan-track evaluate build together
    → DA: code quality, test integrity, scope compliance, gold-plating
    → plan-track: intent fidelity, contract compliance, design system adherence
    → build-track fixes agreed issues → re-submit → iterate
    → lead computes P(build-quality) → iterate or done

### HYBRID mode
lead declares mode transitions explicitly
example: r1-r2 ANALYZE → r3-r5 BUILD
!rule: findings from ANALYZE rounds become constraints in BUILD rounds
!rule: DA adjusts challenge framework at each transition

### shared rules (both modes)
!rule: DA challenges PRECEDE work ¬follow it (plans in BUILD, integration in ANALYZE)
!rule: agents cannot declare convergence without addressing ALL DA challenges
!rule: lead does NOT advance to synthesis until DA exit-gate PASS

## analytical hygiene — BUILD variants (26.3.11, extracted 26.3.19)

All hygiene checks use the same forcing function protocol as ANALYZE mode.
Every check produces one of three outcomes — no fourth option:
  1→ CHECK CHANGES THE ANALYSIS → revise finding. Format: "[finding] — revised from [original] because §2[x] found [evidence] |source:{type}"
  2→ CHECK CONFIRMS WITH EVIDENCE → note flag + justification. Format: "[finding] — §2[x] flag: [concern]. Maintained because: [specific evidence] |source:{type}"
  3→ CHECK REVEALS A GAP → flag for review. Format: "[finding] — §2[x] gap: [what you can't assess]. Flagged for: [DA/lead/specialist] |source:{type}"

### §2a BUILD: positioning & approach

!applies-to: any agent proposing architecture, framework, library, pattern
1→ is this the default/popular approach?
2→ ecosystem trajectory? (growing, stable, declining, abandoned)
3→ migration cost if wrong? (lock-in assessment)
4→ simpler alternative that solves 80%?
5→ workspace: outcome 1/2/3 format — ¬just "approach: [label]"

### §2b BUILD: external calibration / precedent

!applies-to: effort estimates, complexity assessments, timeline predictions
1→ precedent: has this team/codebase done similar? (check project memory)
2→ industry norm for this type of work in this stack?
3→ where did prior estimates go wrong? (calibration data)
4→ no precedent → outcome 3 (gap) — explicitly flag for DA review+checkpoint scrutiny
5→ workspace: outcome 1/2/3 format — ¬just "estimate: [X]"

### §2c BUILD: cost & complexity

!applies-to: architecture, abstractions, patterns that persist beyond current phase
1→ maintenance cost? (who maintains after build? their capability?)
2→ justified by CURRENT or FUTURE requirements? (confirmed or speculative?)
3→ simplest version that works? how does proposal compare?
4→ cost of being wrong? (reversal: day, week, month?)
5→ workspace: outcome 1/2/3 format — ¬just "complexity: [label]"

### §2d source provenance (26.3.17)

All §2d rules from directives.md apply equally to BUILD.
BUILD-specific note: code patterns citing [agent-inference] without [independent-research] (docs, benchmarks) → DA challenge
BUILD-specific note: scale/performance claims from prompt echoed as requirements without validation → flag [prompt-claim]
source types: [independent-research] | [prompt-claim] | [cross-agent] | [agent-inference]
every finding in workspace MUST include |source:{type} tag

#### §2d+ BUILD: source quality tiers (26.3.22)

All §2d+ rules from directives.md apply equally to BUILD.
quality tiers: T1-verified(official-docs,peer-reviewed,benchmarks) | T2-corroborated(tutorials-with-tests,industry-reports,GitHub-production-examples) | T3-unverified(untested-snippets,blog-posts,marketing-pages,AI-generated-examples)
!rule: architecture decisions resting on T3 sources (e.g., "use X pattern" from a blog post) → DA challenge in r2
!rule: performance claims from T3 sources ¬sufficient for architecture decisions — require T1/T2 benchmark data
!rule: DA audits tier distribution: library/framework choices backed only by T3 → quality flag

### §2e BUILD: premise viability (26.3.18)

!applies-to: every architectural choice or implementation plan
1→ what assumptions must hold for this approach to succeed?
2→ are assumptions about scale, usage patterns, or requirements verified or speculative?
3→ what is the strongest alternative architecture? (cite precedent)
4→ if the most speculative assumption is wrong, what's the fallback?
5→ workspace: outcome 1/2/3 format — ¬just "assumptions: reasonable"

### §2f BUILD: hypothesis matrix (26.3.22)

All §2f rules from directives.md apply when BUILD prompt-decomposition has ≥3 H[].
BUILD-specific: evidence rows evaluate architecture/implementation hypotheses ¬market hypotheses.
BUILD example:
  H1: microservices | H2: modular-monolith | H3: serverless
  E[1]: team-size=3 |H1:-/L |H2:+/H |H3:0/M — small team favors monolith
  E[2]: scale-req=10K-concurrent |H1:+/M |H2:0/M |H3:+/H — high scale favors distributed
!rule: architecture decisions with ≥3 competing approaches MUST use hypothesis matrix before selection

### §2g BUILD: dialectical bootstrapping (26.3.22)

All §2g rules from directives.md apply to BUILD. Agents self-challenge top 2-3 architecture decisions before writing to workspace.
BUILD-specific focus:
  DB[{decision}]: (1) initial: {chosen approach} (2) assume-wrong: {what fails?} (3) strongest-counter: {best alternative and why} (4) re-estimate: {would you still choose this?} (5) reconciled: {final with acknowledged tradeoffs}
!purpose: reduces anchoring on first-considered architecture. Forces explicit tradeoff acknowledgment before plan submission.

### §2i BUILD: precision gate (26.4.23)

All §2i rules from directives.md §2i apply equally to BUILD.
BUILD-specific applicability: effort estimates (CAL[] ranges), timeline predictions, performance claims, scale projections, resource counts.
BUILD-specific examples that MUST carry justification:
  - CAL[{task}]: point=5h (without driver breakdown OR precedent cite OR "approximate" qualifier) → §2i fires if load-bearing
  - "handles 10K concurrent users" (without benchmark OR similar-system reference) → §2i fires if architecture-decision-driving
  - "3x faster than X" (without measurement methodology) → §2i fires if primary recommendation
BUILD-specific suppression: CAL[] entries that already carry |80%=[lo,hi]| + |breaks-if:{condition}| satisfy CONDITION 1 automatically.
chain-evaluator A20 fires identically on ANALYZE and BUILD workspace content. CAL-EMIT records distinguish mode via review-id slug prefix.

### §2p BUILD: premise-audit pre-dispatch (26.4.23)

All §2p rules from directives.md §2p apply to BUILD with workflow-step location difference.
BUILD-specific placement: c1-plan.md Step 7a (between Step 7 semantic-route and Step 8 prompt-understanding-gate).
BUILD-specific premise tests (override PA[1-4] from ANALYZE with BUILD-scoped variants):
  PA[1]: tech-tier-necessity — is proposed architecture tier NECESSARY or is simpler stack adequate? (monolith vs microservices vs serverless)
  PA[2]: scale-floor — minimum viable user/request volume? (state explicitly, ¬assume 10K+)
  PA[3]: data-readiness — what integration points must exist for build to deploy? (gap? yes/no)
  PA[4]: precedent-baseline — RC[{similar-build-in-stack}]={typical-duration} | above/at/below base-rate?
!rule: CHALLENGED/GAP on PA[1] or PA[2] → revise scope-boundary + Q[] BEFORE plan-track spawn
!rule: c1-plan.md Step 7a workspace template MUST include `## premise-audit-results` section with PREMISE-AUDIT[pre-dispatch] populated before Step 12 spawn.

### §2d-severity BUILD: severity provenance (26.4.23)

All §2d-severity rules from directives.md apply equally to BUILD.
BUILD-specific applicability: severity ratings on security findings (CVE severity extrapolated from different-sector context), performance findings (bottleneck severity extrapolated from different-scale precedent), test-gap findings (criticality extrapolated from different-stack test-pyramid).
BUILD example: security-specialist rates HIGH-severity on BUILD input-validation gap based on OWASP top-10 reference — if OWASP stats are from different application class (e.g. public-facing web vs internal API), |severity-basis:[extrapolation:OWASP-public-web→internal-API |assumption:exposure-model-comparable |confidence-delta:T1→agent-inference]| required.

### DA enforcement of hygiene checks (BUILD)

Same grade modifiers and challenge format as ANALYZE mode:
  check + visibly altered analysis (outcome 1) → no modifier
  check + concern noted + specific justification (outcome 2) → no modifier
  check + concern noted + NO justification → grade penalty, challenge issued
  check missing entirely → process violation, mandatory re-do before convergence
  check completed perfunctorily → challenge issued

DA challenge format for weak checks:
  "DA[#N] process: §2[a/b/c/e] check on [finding] is perfunctory.
   You wrote '[what they wrote]' but then [what they did that contradicts it].
   |→ revise finding to reflect check result, or provide specific evidence
   for why concern doesn't apply. 'It's still the right approach' is ¬specific evidence."

### BUILD Toulmin warrant checks (26.3.22)

DA applies Toulmin warrant checks to architecture decisions in r2 and r4:
  CQoT-6 falsifiability: architecture decision states "IF [{evidence}] THEN [{would-reconsider}]" — DA checks: is the reversal condition reachable or is it "if everything fails simultaneously"?
  CQoT-7 steelman: agent states best alternative architecture and why it was rejected with evidence — DA checks: genuine comparison or strawman?
  CQoT-8 confidence-gap: agent states what would need to be true to be 90% confident in the choice — DA checks: obtainable evidence or unfalsifiable claim?

BUILD-specific emphasis: architecture warrants are often implicit ("use X because it's industry standard" — WARRANT: industry standard → right for us. But is it? At our scale? With our team?). Making warrants explicit catches misapplied patterns.

verdict format: existing DA engagement assessment + |cqot:[pass|fail-{criterion-N}]

## build-mode guardrails (DA-specific, BUILD only)

### §4a scope creep detection
at checkpoint (~50%): files+functions planned vs actual, TODO density, test-to-code ratio
severity: INFO|LOW|MEDIUM(affects interfaces)|HIGH(solving other agent's problem or future phase)

### §4b assumption conflict detection
at plan challenge (r2) AND checkpoint (r3): interface mismatches, data model disagreements, dependency ordering, naming conflicts, error handling divergence
!BUILD equivalent of herding — agents assume compatibility without verifying

### §4c gold-plating detection
flag: abstractions for speculative requirements, optimizing before measuring, configuring single-value settings, admin features not in phase, refactoring out-of-scope code
question: does DESIGN DOCUMENT or CURRENT PHASE require this?

### §4d test integrity check
at review (r4): behavior vs runs, requirements vs implementation, failure cases, hardcoded-value test, real infra vs mocks
cross-reference project CLAUDE.md test requirements | Tier 1 without test = CRITICAL

## superforecasting — BUILD variants (26.3.15, extracted 26.3.19)

### §3 BUILD decomposition mandate

!rule: build scope MUST be decomposed into estimable sub-tasks before implementation
format per sub-task:
  "SQ[{N}]: {sub-task} |estimable: {yes/no} |method: {precedent/analogue/decompose} |→ {which-agent-owns}"
!purpose: prevents anchoring on optimistic single-estimate. Each sub-task gets independent estimation.

### §3 BUILD reference class forecasting

!rule: before effort estimation, identify reference class for build scope
format:
  "RC[{task}]: reference-class={similar-builds-in-stack} |base-rate={typical-duration} |sample-size={N} |src:{source} |confidence:{H/M/L}"
!rule: "How long do similar builds take in this stack?" Apply base rates to timeline estimates.
!rule: team estimates that deviate >30% from reference class MUST justify with specific evidence

### §3 BUILD calibrated probability estimates

!rule: effort estimates must include calibrated ranges, ¬point estimates only
format:
  "CAL[{task}]: point={best-estimate} |80%=[{low},{high}] |90%=[{lower},{higher}] |breaks-if:{dependency-delays}"
!enforcement: DA checks: is 80% band realistic? Does it account for integration risk?

### §3 BUILD pre-mortem

!rule: every BUILD plan must include pre-mortem: "It's 6 months later and this codebase is unmaintainable. What happened?"
format:
  "PM[{N}]: {failure-scenario} |probability:{%} |early-warning:{signal} |mitigation:{prevention}"
!minimum: 3 failure scenarios focused on: technical debt, scaling bottlenecks, integration failures

### §3 BUILD log score tracking (26.3.22)

!purpose: track effort estimation accuracy across BUILD reviews using log scoring. Applies to CAL[] effort estimates that have verifiable outcomes (actual build time vs estimated).

workspace format (added at build completion):
  "LS-TRACK[{review}:{agent}:{estimate-id}]: predicted:{effort-range} |actual:{actual-effort} |log-score:{score}"

agent memory extension: LS-avg:{score}|n:{count}|trend:{direction}
lead reads agent LS-avg at plan phase → agents with poor estimation history get DA scrutiny on effort claims

### §3a BUILD complexity tiers (v1.1, 26.3.15)

TIER-1 (single module, 2+DA):
  criteria: small feature, well-defined scope, existing patterns
  team: primary builder + reviewer + DA
  factors: module-count(1-2), interface-changes(0-1), test-complexity(low)

TIER-2 (multi-module, 3-4+DA):
  criteria: multi-module feature, interface changes, new patterns
  team: 2-3 builders + reviewer + DA
  factors: module-count(3-5), interface-changes(2+), test-complexity(moderate)

TIER-3 (system build, 5-8+DA):
  criteria: new system, multiple services, cross-cutting concerns
  team: 3-5 builders + integration specialist + DA
  factors: module-count(5+), interface-changes(many), test-complexity(high), dependency-risk(high)

BUILD complexity scoring: module-count(1-5) + interface-changes(1-5) + test-complexity(1-5) + dependency-risk(1-5) + team-familiarity(1-5)
sum < 12 → TIER-1 | 12-18 → TIER-2 | >18 → TIER-3

#### complexity detection (BUILD)
lead evaluates at task creation:
  1→ module count: how many modules/services being built or changed?
  2→ interface changes: how many API/contract boundaries are affected?
  3→ test complexity: unit only, or integration+end-to-end?
  4→ dependency risk: does build depend on other agents' unfinished outputs?
  5→ team familiarity: how well does team know this codebase/stack?

#### dynamic escalation
!rule: if TIER-1 build surfaces unexpected complexity during r1 → lead escalates to TIER-2 (adds agents)
!rule: if TIER-2 DA identifies domain gap → escalate to TIER-3 (dynamic agent creation)
!rule: never DE-escalate mid-build (removing agents loses context)

lead reports tier selection:
format: "complexity-assessment: BUILD {tier} |scores: module-count({N}),interface-changes({N}),test-complexity({N}),dependency-risk({N}),team-familiarity({N}) |total:{sum} |team-size:{N}"
user may override tier selection

#### §3a.1 parallel implementation engineers (v1.0, 26.4.8)

!when: any build where SQ[] items form ≥2 file-independent clusters (not tier-gated)
!purpose: parallelize build phase — N engineers build simultaneously in isolated worktrees

##### eligibility check (lead runs at plan-lock)
1→ map SQ[] items to primary files they modify
2→ build dependency graph: SQ[A]→{types.py,loop.py} | SQ[B]→{security.py} | SQ[C]→{adapters.py}
3→ identify independent clusters: SQ[] groups with zero shared files
4→ ≥2 independent clusters → eligible for parallel engineers
5→ shared files between clusters → assign to one engineer OR define sequential merge order
!rule: 1 cluster = 1 engineer. ¬split a cluster across engineers (shared file = merge conflict)

##### roster + spawning
- roster: ONE `implementation-engineer` (primary). Additional instances are DYNAMIC.
- naming: `implementation-engineer` (primary), `implementation-engineer-2`, `-3`, ..., `-N`
- agent definition: all instances use `~/.claude/teams/sigma-review/agent-defs/implementation-engineer.md` (shared Role/Expertise)
- primary spawns in Phase 01 (participates in plan challenge)
- additional engineers spawn at plan-lock (Phase 03 exit → Phase 04 entry)
- additional engineers get: their SQ[] subset + relevant ADRs + relevant ICs + primary's feasibility notes
- additional engineers do NOT participate in plan challenge (primary already covered feasibility)

##### memory model
```
T/agents/implementation-engineer/memory.md        ← shared domain knowledge (read by all instances)
T/agents/implementation-engineer-2/memory.md       ← instance-specific findings (created at spawn)
T/agents/implementation-engineer-3/memory.md       ← instance-specific findings (created at spawn)
```
shared memory = read-only during build (Python patterns, past build learnings)
instance memory = captures what each engineer built this session
promotion: instance findings merge back into shared memory

##### worktree isolation
- primary: works in main worktree (or own worktree if preferred)
- additional engineers: `isolation: "worktree"` on Agent spawn → separate git branch per engineer
- each engineer runs tests in their worktree independently
- merge step AFTER all engineers complete individual builds

##### file ownership (CRITICAL — prevents merge conflicts)
lead assigns at spawn time based on SQ[] clustering:
```
format in workspace ## build-assignments:
  "engineer-1: SQ[1,7,8] |files: types.py(fields), loop.py, bridge.py |worktree: main"
  "engineer-2: SQ[4,5]   |files: types.py(normalize), adapters.py |worktree: f1-ip-hardening"
  "engineer-3: SQ[6]     |files: security.py |worktree: f1-hardened"
```
!rule: if two engineers MUST touch the same file → define ownership by section (top/mid/bottom) or sequential merge order. Never concurrent edits to same file region.

##### build phase workflow
1→ all engineers read locked plan from workspace (same as single-engineer)
2→ each engineer builds ONLY their SQ[] subset
3→ each engineer writes CHECKPOINT at ~50% (same format, scoped to their SQ[])
4→ each engineer runs tests in their worktree (individual pass required)
5→ code-quality-analyst reviews ACROSS all worktrees (integration eye)
6→ merge step: code-quality-analyst or lead merges worktrees after all engineers pass
7→ integration tests run AFTER merge — individual tests passing ¬guarantees combined correctness
8→ if merge conflicts → route to engineer who owns the conflicting file

##### build review with multiple engineers
- all N engineers stay alive for Phase 05
- DA/plan-track issues route to the engineer who owns that SQ[]
- engineer fixes in their worktree → re-merge → re-test
- each engineer's workspace ## findings section is prefixed with their name

##### when NOT to parallelize
- SQ[] items share >50% of files → sequential is safer
- only 1 SQ[] cluster exists → single engineer (nothing to parallelize)
- high dependency-risk score (4-5) → shared state likely, sequential safer
- team's first build in a new codebase → single engineer builds shared understanding first

### §3b BUILD evaluation rubric (v1.1, 26.3.15)

!when: after review complete (post-r4), before promotion phase
!optional: lead or user can invoke /sigma-evaluate at any time

BUILD rubric (6 criteria, 4-point scale):
1→ correctness: does it work? edge cases handled? error paths covered? (4=all cases handled, 1=fundamental bugs)
2→ test-coverage: behavior tested (¬just runs)? failure cases? integration tests? (4=comprehensive behavioral, 1=minimal/absent)
3→ maintainability: clear naming? reasonable complexity? future developer can understand? (4=self-documenting, 1=opaque)
4→ performance: appropriate for scale? no obvious bottlenecks? measured ¬assumed? (4=measured+optimized, 1=unmeasured+bottlenecked)
5→ security: input validation? auth/authz? OWASP top 10 addressed? (4=defense-in-depth, 1=no validation)
6→ api-design: consistent? self-documenting? backward compatible? error responses clear? (4=exemplary contract, 1=inconsistent+undocumented)

BUILD evaluator assignment:
  Evaluator 1: Correctness + Security (code review perspective)
  Evaluator 2: Test Coverage + Maintainability (quality perspective)
  Evaluator 3: Performance + API Design (architecture perspective)

grading: A: 3.5-4.0 avg | B: 2.8-3.4 | C: 2.0-2.7 | D: 1.5-1.9 | F: <1.5
pipeline: see /sigma-evaluate skill for full evaluation pipeline (3 evaluator agents + judge)

## bayesian-consensus-tracking — BUILD variant (26.3.15, extracted 26.3.19)

### §4 BUILD belief states (two-phase)

!purpose: separate belief states for plan quality and build quality

#### P(plan-ready) — plan phase exit
weighted components:
  builder-feasibility: build-track confirms plan is implementable (weight 0.25)
  interface-agreement: plan-track agents agree on API contracts (weight 0.20)
  design-arch-coherence: design system aligns with technical architecture (weight 0.15)
  no-assumption-conflicts: §4b cross-checked by DA + build-track (weight 0.15)
  prompt-understanding-coverage: plan addresses prompt understanding Q[]/H[]/C[] (weight 0.10)
  DA-exit-gate: plan quality (weight 0.15)

plan stopping rules:
  P > 0.85 → lock plan, advance to build phase
  P 0.6-0.85 → plan-track refines, another challenge round
  P < 0.6 → Toulmin debate on contested architecture decisions
  max 5 rounds

workspace format:
  "BELIEF[plan-r{N}]: P={posterior} |builder-feasibility={score} |interface-agree={score} |design-arch={score} |conflicts={none|count} |review-coverage={score} |DA={grade} |→ {lock-plan|another-round({gaps})|Toulmin-debate}"

#### P(build-quality) — build phase exit
weighted components:
  plan-compliance: build matches locked architecture decisions, assessed by plan-track (weight 0.25)
  test-coverage: behavioral tests, failure cases, integration (weight 0.20)
  design-fidelity: build matches design system specs, assessed by product-designer (weight 0.15)
  code-quality: DA assessment of correctness, security, maintainability (weight 0.20)
  no-scope-creep: built only what was in scope (weight 0.10)
  DA-exit-gate: build quality (weight 0.10)

build stopping rules:
  P > 0.85 → done, proceed to synthesis
  P 0.6-0.85 → build-track fixes agreed issues, another review round
  P < 0.6 → escalate to user (fundamental plan-build mismatch)
  max 5 rounds

workspace format:
  "BELIEF[build-r{N}]: P={posterior} |plan-compliance={score} |test-coverage={score} |design-fidelity={score} |code-quality={score} |scope={clean|creep} |DA={grade} |→ {done|another-round({issues})|escalate}"

### §4a BUILD retrieval strategies (26.3.15)

!rule: BUILD mode retrieves code patterns, ¬market research
strategies:
  CODE-PATTERN: search for implementations of specific patterns in production codebases (GitHub, docs, technical blogs)
  LIBRARY-EVAL: compare libraries/frameworks (features, maintenance, community, license)
  API-REFERENCE: fetch current API docs for dependencies being integrated
  FAILURE-SEARCH: "What goes wrong when you build X this way?" (Stack Overflow, post-mortems, retrospectives)

BUILD authority scoring:
  official docs=5 | GitHub production examples=4 | tutorial with tests=3 | untested snippet=1

see /sigma-retrieve skill for full pipeline (query decomposition → parallel retrieval → validation → synthesis)

### §4b BUILD codebase graph (26.3.15)

!purpose: map codebase structure for impact analysis, dependency visualization, test gap identification

BUILD entity types: module, service, function, class, API-endpoint, database-table, config, dependency
BUILD relationship types: depends-on, calls, implements, extends, reads-from, writes-to, integrates-with, tested-by

enables:
  impact analysis: "if I change this interface, what breaks?"
  dependency visualization: module coupling map
  test gap identification: untested integration points
  dead code detection: unreferenced entities

seeded from: codebase analysis during BUILD r1 (agents read code and populate graph)
format: same E[]/R[] format as ANALYZE graphs
location: agent-infrastructure/knowledge-graphs/{domain}/

## context-contamination — BUILD scope boundary (26.3.15, extracted 26.3.19)

### §6f BUILD scope boundary
!rule: BUILD scope-boundary prevents scope creep (aligns with §4a scope creep detection)
BUILD format:
  "## scope-boundary
   This build implements: {phase description, specific features}
   This build does NOT implement: {future phases, nice-to-haves, features not in spec}
   Lead: before accepting agent output, verify it builds ONLY what's in scope."
!rule: same contamination mechanism that prevents topic bleed in analysis prevents scope creep in build

## prompt-decomposition — BUILD variant (26.3.17, extracted 26.3.19)

### §7a BUILD claim detection heuristics

BUILD-specific claims to extract from user prompt (become hypotheses, ¬requirements):
  - scale assumptions without evidence ("needs to handle 10K concurrent users")
  - technology assertions ("we need microservices for this")
  - user behavior claims ("users will primarily access via mobile")
  - performance requirements without measurement ("must be real-time")
  - architecture claims ("monolith won't scale for this")

### §7c BUILD workspace integration

!rule: agent spawn prompt includes: "Claims H1-HN are user hypotheses extracted from the prompt. Test these — find evidence FOR and AGAINST. Do ¬assume they are true. If a claim drives an architectural decision, flag: 'H[N] assumption used — ¬independently validated' and cite the specific choice."

### §7d BUILD DA prompt audit

!rule: DA checks in r2:
  1→ which plans use language from user prompt (near-verbatim echo on scale/tech/architecture)
  2→ which plans confirm prompt architecture claims without independent sourcing ([prompt-claim] without corroboration)
  3→ whether BUILD claims were MISSED in decomposition (architecture claims that became untagged requirements)
  4→ whether plan methodology COULD have produced contradictory result — if not, methodology was confirmatory ¬investigative

## success criteria — BUILD mode

5→ zero architectural decisions during build that should have been in plan
6→ assumption conflicts detected at plan challenge (r2), ¬after build
7→ scope creep caught at checkpoint (r3), ¬at review (r4)
8→ gold-plating flagged with design doc citation
9→ test integrity catches ≥1 weak test pattern per cycle
10→ zero agents building organizational infrastructure instead of product

both modes:
11→ debate produces clear rulings on ≤2 contested claims per cycle
12→ deliverable includes ruling AND dissent
13→ losing positions become test cases or reversal triggers

## Toulmin debate — BUILD architecture decisions

same structure as ANALYZE, applied to architecture choices:
```
DEBATE[event-streaming]:
  tech-architect: CLAIM=Use Kafka |GROUNDS=5K-50K events/sec projected |WARRANT=industry standard for high-throughput |BACKING=Manhattan Active uses it, 400+ LangGraph companies |QUALIFIER=appropriate IF >1K events/sec |REBUTTAL=below 1K, overkill
  DA: ATTACK-WARRANT=is Kafka needed at THIS scale? |COUNTER-REBUTTAL=Redis Streams suffices <5K/sec |QUALIFIER-CHECK=is 5K-50K realistic or aspirational?
  RESOLUTION: {concede|defend|compromise}
```
DA attacks: WARRANT (is this tech really needed at this scale?) + QUALIFIER (is the scale projection realistic or aspirational?)

!when: DA identifies material architecture disagreement that survived plan challenge
P(plan-ready) < 0.6 → trigger Toulmin debate on contested architecture decisions

## dynamic agent creation — BUILD timing

gap in r1 → agent created → researches during r1→r2 transition → joins r2 (ideal)
gap in r2 → agent created → researches during r2→r3 transition → joins r3 as reviewer/advisor ¬builder
  !new agent does NOT build code in r3 (no plan approved, joining mid-build = chaos)
gap in r3+ → ¬create (too late — note for next cycle)

→ actions:
→ new directive → append with version+date
→ directive revision → update version, note change in ctx
