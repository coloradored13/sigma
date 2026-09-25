# sigma-review directives

## scope: ANALYZE mode only (BUILD mode → see build-directives.md and /sigma-build skill)
> BUILD mode directives extracted to: ~/.claude/teams/sigma-review/shared/build-directives.md
> BUILD orchestration skill: the /sigma-build skill
> DA agent (serves both modes): ~/.claude/teams/sigma-review/agent-defs/devils-advocate.md

## adversarial-layer v2.0 (26.3.11)

scope: sigma-review ANALYZE operations — review, research, analysis
modes: ANALYZE (BUILD mode → /sigma-build skill)

### round structure

#### ANALYZE mode
rounds: min 3, max 5
r1: research (mandatory)
r2: challenge+integration (mandatory)
r3→r5: DA-gated exit (see below)

r1: domain agents research independently | DA observes ¬participates
  → DA reads all workspace findings at r1 convergence
  → DA prepares challenges before r2 begins

#### zero-dissent circuit breaker (v1.0, 26.3.14)

!trigger: lead detects ZERO divergence across all agents at r1 convergence
  zero divergence = no agent challenged, nuanced, or disagreed with any peer finding
  detection: lead reads convergence section + workspace findings for ANY tension, disagreement, or counter-estimate

!purpose: 7 consecutive reviews produced zero r1 dissent (confirmed pattern 26.3.13). Independent domain experts producing 0 disagreements across 50-70+ findings = herding signal. Self-challenge BEFORE DA pressure produces more genuine analytical tension than waiting for external challenge

!when: after all agents ✓ r1, BEFORE spawning DA for r2. MANDATORY — lead MUST run zero-dissent check
  IF any agent produced genuine divergence in r1 → log divergence found, skip circuit breaker → proceed to r2
  IF zero divergence → circuit breaker fires → then proceed to r2
  !hard gate: lead ¬advances to r2 without either (a) logging detected divergence OR (b) completing circuit breaker

!execution: lead sends targeted self-challenge to each agent (via SendMessage or re-spawn):
  "zero-dissent circuit breaker: your R1 finding on [{agent's highest-conviction finding}] agrees with all peers.
   (1) Name the strongest argument AGAINST your own position.
   (2) If that argument is correct, would you change your conclusion?
   (3) Identify ONE peer finding you would challenge, quantify differently, or add a caveat to.
   Respond in workspace — append to your findings section. This is NOT a full re-analysis — 3 focused responses only."

!agent response format (workspace):
  "CB[1]: strongest counter to [{finding}]: {argument} |would-change: yes→{revision}|no→{why-it-holds-despite-counter}
   CB[2]: peer challenge: [{agent}:{finding}] — {challenge/nuance/different-quantification}
   CB[3]: self-assessed blind spot: {what I might be missing}"

!constraints:
  - ¬full re-analysis. 3 targeted responses per agent. Brief
  - ¬delays r2 significantly. Agents respond in single turn
  - DA reads CB responses alongside r1 findings when preparing r2 challenges
  - DA evaluates CB quality: genuine self-challenge vs performative. Weak CB = grade modifier in r2
  - DA checks: were CB responses rooted in [independent-research] or still echoing [prompt-claim]? agents unified around prompt hypothesis ≠ consensus — note as herding-on-prompt (§2d, §7)
  - if CB produces genuine revision → agent updates finding before r2
  - if CB surfaces new disagreement → logged, DA incorporates into r2 challenges

!success criteria:
  - ≥1 genuine revision from CB (finding actually changed)
  - ≥2 peer challenges surfaced (analytical tensions for DA to work with)
  - DA reports CB quality in exit-gate assessment

r2: DA delivers challenges to all inboxes FIRST
  → agents integrate peers + address DA challenges simultaneously
  → each agent workspace write MUST include DA response section
  → format: "DA[#N]: concede|defend|compromise — [evidence]"
  → DA evaluates responses → issues synthesis-ready verdict

r3: IF DA confirms synthesis-ready → lead synthesizes (3-round review)
    ELSE → deepening/debate: agents address DA gaps, resolve disagreements, model specifics
    → DA observes, prepares second challenges

r4: IF DA confirms synthesis-ready → lead synthesizes (4-round review)
    ELSE → final DA challenge round: challenges r3 deepening (¬repeat r2 challenges)
    → focus: new consensus formed in r3, remaining gaps, refined estimates
    → !pattern: teams replace old consensus with new consensus under DA pressure → stress-test NEW consensus

r5: synthesis (hard cap — no further rounds)
  → DA final assessment: cumulative bias-check + gaps + grade
  → debate protocol available for remaining high-stakes disagreements
  → unresolved items logged as deliberate divergence in decisions.md

#### DA exit-gate
!exit-gate: DA decides synthesis-ready, ¬agents, ¬lead
!DA criteria for synthesis-ready (ALL must hold):
  1→ engagement quality ≥ B across all agents
  2→ no material disagreements unresolved (or logged as deliberate divergence in decisions.md)
  3→ no new consensus formed in latest round without stress-test
  4→ analytical hygiene checks (§2a/§2b/§2c/§2e) produced substantive outcome ¬perfunctory
!DA verdict format in workspace: "exit-gate: PASS|FAIL |engagement:[grade] |unresolved:[list|none] |untested-consensus:[list|none] |hygiene:[pass|fail-{section}]"
!FAIL → DA must specify which criteria failed + what next round must address

#### shared rules (ANALYZE mode — BUILD mode rules in build-directives.md)
!rule: DA challenges PRECEDE work ¬follow it (plans in BUILD, integration in ANALYZE)
!rule: agents cannot declare convergence without addressing ALL DA challenges
!rule: lead does NOT advance to synthesis until DA exit-gate PASS

### analytical hygiene — forcing function protocol (26.3.11)

!purpose: prevent checks from being checkboxes. check result MUST visibly alter analysis or agent MUST explain why it doesn't.
!observed failure mode: agents complete checks, write "positioning: consensus", then recommend consensus anyway without addressing implication. Check exists but doesn't bite.

#### the rule — every check produces one of three outcomes (no fourth option)

1→ CHECK CHANGES THE ANALYSIS
  check revealed something that alters recommendation, estimate, or framing
  action: revise finding BEFORE writing to workspace
  format: "[finding] — revised from [original] because §2[a/b/c] found [evidence] |source:{type}"

2→ CHECK CONFIRMS THE ANALYSIS (with acknowledged risk)
  check found concern but agent has SPECIFIC EVIDENCE for why position holds
  action: write finding WITH counterweight explicitly attached
  format: "[finding] — §2[a/b/c] flag: [concern]. Maintained because: [specific evidence, ¬reassurance] |source:{type}"
  !test: would DA accept your "maintained because" reasoning? if not, you're rationalizing

3→ CHECK REVEALS A GAP YOU CANNOT RESOLVE
  check surfaced something material that agent lacks expertise or data to evaluate
  action: flag for DA review or dynamic agent request
  format: "[finding] — §2[a/b/c] gap: [what you can't assess]. Flagged for: [DA/lead/specialist] |source:{type}"

#### what is NOT acceptable

!NEVER: complete check, note result, proceed unchanged without explanation
  bad: "§2a positioning: consensus — 5+ competitors building similar" [then recommends building same thing with no crowding discussion]
!NEVER: use check to validate rather than challenge
  bad: "§2b calibration: industry reports confirm our estimate" [cherry-picked confirming source, ignored disconfirming]
!NEVER: treat check as section to fill rather than question to answer
  bad: "§2c cost: moderate complexity, justified by current requirements" [no comparison to simpler alternative, no reversal cost, no maintenance burden]

#### §2a positioning & consensus

!applies-to: recommendations involving markets,adoption,competition,resource allocation
1→ who else is recommending this?
2→ is this already the consensus?
3→ what happens if everyone acts simultaneously?
4→ workspace: outcome 1/2/3 format (see above) — ¬just "positioning: [label]"

> BUILD variant → see build-directives.md §2a

#### §2b external calibration / precedent

!applies-to: probability estimates,forecasts,timeline predictions,severity assessments
1→ search prediction markets,base rates,historical data
2→ if divergence >15pp → MUST be outcome 1 or 2 with specific justification
3→ workspace: outcome 1/2/3 format — ¬just "calibration: [source] says [X]"

> BUILD variant → see build-directives.md §2b

#### §2c cost & complexity

!applies-to: "highest conviction" or "top priority" or equivalent superlatives
1→ what does recommendation COST?
2→ is cost already elevated?
3→ consensus view on this cost?
4→ workspace: outcome 1/2/3 format — ¬just "valuation: [level]"

> BUILD variant → see build-directives.md §2c

#### §2d source provenance (26.3.17)

!purpose: prevent prompt laundering — user's assumptions entering as input, passing through research, returning as "findings." Source tags make provenance visible so DA can audit contamination
!observed failure mode: user states hypothesis in prompt → agents treat as constraint ¬claim → findings echo prompt language with research authority → user reads own assumptions back as validated conclusions

source types (every finding MUST carry one):
  [independent-research] → found via web search, database, document, filing — agent can cite specific source
  [prompt-claim] → restates, confirms, or directly derives from user's prompt claims (see workspace ## prompt-decomposition)
  [cross-agent] → corroborates another agent's independent finding — cite which agent+finding
  [agent-inference] → derived from reasoning across multiple inputs — ¬independently sourced

!rules:
  - every finding in workspace MUST include |source:{type} tag
  - [prompt-claim] findings MUST be paired with independent corroboration OR explicitly marked as unverified
  - [agent-inference] ¬substitutes for [independent-research] — inference is hypothesis ¬evidence
  - source tag missing → process violation (same as missing hygiene check)

!DA audit: during r2, DA checks source distribution across all agent findings:
  - >30% [prompt-claim] without independent corroboration → structural contamination flag
  - cluster of agents producing [prompt-claim] on same hypothesis → echo chamber flag
  - [independent-research] that uses near-identical language to prompt → reclassify as [prompt-claim], challenge

#### §2d+ source quality tiers (26.3.22)

!purpose: distinguish source QUALITY within source TYPE. [independent-research] from Wikipedia ≠ [independent-research] from peer-reviewed journal. Agents tag quality tier alongside source type.

quality tiers:
  T1-verified: peer-reviewed journal, regulatory filing, audited financial statement, official government data
  T2-corroborated: preprint (arxiv), industry report (Gartner/McKinsey), company-reported with independent corroboration
  T3-unverified: company PR, blog, advocacy source, derivative media, commentary

!rules:
  - load-bearing findings (>70% confidence or superlative) MUST carry a quality tier tag
  - non-load-bearing findings SHOULD carry a quality tier tag (pragmatic — tag when tier matters for claim strength)
  - load-bearing findings resting on T3 sources → DA challenge in r2
  - T3-only findings ¬sufficient for high-conviction conclusions (>70% confidence)
  - DA audits tier distribution: >50% T3 on load-bearing claims → quality flag
  - missing quality tier on load-bearing finding → DA flags as process violation (same as missing source tag)

format extension: |source:[independent-research:T1] or |source:[independent-research:T2]

#### §2e premise viability (26.3.18)

!purpose: prevent R1 premise anchoring — agents unconsciously validate user's proposed approach instead of genuinely testing it. Observed: an early game-design review 26.3.18, 4/4 agents confirmed premise, DA caught in R2 (DA#1 crowding). This check forces explicit premise evaluation before convergence.

!applies-to: every major recommendation or conclusion
1→ what must be true for the proposed approach to be the right one? (list load-bearing premises)
2→ is any required premise unverified, contested, or historically unreliable?
3→ what is the strongest alternative approach? (¬strawman — genuinely competitive)
4→ if the user had not specified this approach, would you have independently recommended it?
5→ workspace: outcome 1/2/3 format — ¬just "premises: valid"

> BUILD variant → see build-directives.md §2e

#### §2f hypothesis matrix (26.3.22)

!purpose: when ≥3 hypotheses in prompt-decomposition, force systematic evidence evaluation against ALL hypotheses ¬just confirmatory search for preferred hypothesis. Based on ACH (Heuer) structure validated for LLM multi-agent by AgentCDM (arxiv:2508.11995).

!applies-to: ANALYZE reviews where prompt-decomposition ## H[] count ≥ 3
!does-NOT-apply: reviews with <3 hypotheses, BUILD mode

!rule: agents completing R1 MUST populate evidence rows for their domain findings against all H[]
!rule: lead integrates agent evidence rows at R1 convergence into unified matrix
!rule: DA checks for confirmation bias: evidence items that only confirm ¬test

workspace format:
```
## hypothesis-matrix
H1:{text} | H2:{text} | H3:{text}
E[1]:{evidence} |H1:{+/-/0} |H2:{+/-/0} |H3:{+/-/0} |weight:{H/M/L} |src:{type}
E[2]:{evidence} |H1:{+/-/0} |H2:{+/-/0} |H3:{+/-/0} |weight:{H/M/L} |src:{type}
Inconsistency-scores: H1={sum-negatives} H2={sum} H3={sum}
→ least-inconsistent: {Hn} — lead synthesis must begin here
```

!constraint: structure-only. Do NOT implement diagnosticity weighting (Dhami 2019: only 11% of trained analysts utilized diagnosticity effectively). Agents evaluate evidence as +supporting/-inconsistent/0-neutral per hypothesis. Lead/DA compute inconsistency scores.

!DA enforcement: DA checks hypothesis matrix for:
  - evidence rows that are +/+/+ across all hypotheses → non-diagnostic, challenge
  - hypotheses with zero negative evidence → likely under-tested, challenge
  - evidence concentrated from single source type → diversity gap

#### §2g dialectical bootstrapping — R1 self-challenge (26.3.22)

!purpose: reduce herding and overconfidence in R1 by forcing agents to self-challenge BEFORE writing workspace findings. Based on Herzog & Hertwig (2009): "crowd within" technique improved accuracy 75% in humans. LLM transfer rate: MODERATE (55-65%) — mechanism is self-consistency via structured prompt variation ¬genuine cognitive reframing.

!applies-to: ALL agent R1 findings (ANALYZE and BUILD)
!when: BEFORE writing finding to workspace, AFTER completing analysis
!scoping: REQUIRED for findings with confidence estimates, severity judgments, or probability claims. OPTIONAL for deterministic code observations (unused import, dead code, missing method) where assume-wrong produces no meaningful revision. AUDIT[26.3.25]: code-focused agents (TA, CQA, TW) consistently skip DB on deterministic findings — acceptable when finding is binary (present/absent).

!execution: each agent applies to their top 2-3 highest-conviction findings:
  "DB[{finding}]: (1) initial: {assessment} (2) assume-wrong: {what changes?} (3) strongest-counter: {reason you could be wrong} (4) re-estimate: {revised from opposite perspective} (5) reconciled: {final position integrating both}"

!rules:
  - ¬full re-analysis. Brief self-challenge per finding. ~3-5 sentences per DB[]
  - reconciled position goes to workspace ¬initial assessment
  - if assume-wrong produces genuine revision → revise finding before workspace write (outcome 1)
  - if assume-wrong confirms original → note strongest counter in finding (outcome 2)
  - DA evaluates DB[] quality in r2: genuine self-challenge vs performative
  - performative DB[] (initial and reconciled are identical with no real engagement) → grade modifier

!cost: ~10-15% per-agent processing increase. Zero additional agents.

#### §2h cross-model verification — ΣVerify protocol (26.3.22)

!purpose: reduce single-model blind spots by verifying findings against external AI models (OpenAI, Google AI) via sigma-verify MCP server. Different training data → different confabulation patterns → genuinely independent signal (complementary to DA's independent information-state challenge).

!when: MANDATORY when ΣVerify available (workspace ## infrastructure confirms). Each agent MUST verify their top 1 load-bearing finding. Use additionally when:
  - high-conviction finding (>70% confidence) that is load-bearing for conclusions
  - finding relies heavily on [agent-inference] without strong [independent-research] backing
  - DA requests cross-model check during r2 challenge
  - cross_verify particularly valuable when agents converge unanimously (zero-dissent signal)
!when-unavailable: if pre-flight confirms ΣVerify unavailable (no API keys), all findings carry no-tag — neutral, ¬penalized

!tools (via sigma-verify MCP):
  init → check provider availability (call once per session)
!rule[per-session-unlock]: init unlocks verify_finding/cross_verify/challenge ONLY in the session that calls it — HATEOAS gateway state is per-session, lead's preflight init ¬propagates to teammate sessions. EVERY agent calls mcp__sigma-verify__init in its OWN session (Boot final step) before first XVERIFY attempt. ToolSearch-not-found without own-init = expected behavior, ¬infra gap — call init, retry ToolSearch once. Root cause of 5-review XVERIFY-FAIL recurrence (26.4.22→26.8.31); verified live both directions 26.9.5.
  verify_finding(finding, context, provider?) → single-model verification
  cross_verify(finding, context) → all-model comparison
  challenge(claim, evidence, provider?) → external devil's advocate

!source provenance: results carry |source:external-{provider}-{model}| tag
  these are a NEW source type alongside existing §2d types
  [external-verification] → cross-model corroboration or challenge from non-Claude model
  weight: advisory (different model ¬domain expert) — informs confidence ¬overrides domain analysis

#### three verification states — every load-bearing finding MUST carry exactly one when ΣVerify available

1→ XVERIFY[{provider}:{model}]: {assessment}({confidence}) |{reasoning} |source:external-{provider}-{model}|
  verification SUCCEEDED. result is evidence. write to workspace findings.

2→ XVERIFY-FAIL[{provider}:{model}]: {error-class} |attempted:{tool} |finding:{brief} |→ verification-gap
  verification ATTEMPTED but FAILED for technical reasons (rate-limit, timeout, auth-error, token-limit, network-error).
  this is a GAP (analytical hygiene outcome 3). write to workspace findings.
  !rule: XVERIFY-FAIL ¬invisible. agent MUST report failed attempts in workspace.
  !rule: downstream agents and DA MUST NOT assume verification occurred when XVERIFY-FAIL is present.
  !rule: cross_verify returning partial results (1-of-N providers) → flag as partial coverage.

3→ no XVERIFY tag
  verification was never attempted. permitted ONLY for non-load-bearing findings when ΣVerify available.
  when ΣVerify unavailable → all findings carry no-tag, neutral, ¬penalized.

!failure handling:
  sigma-verify classifies errors automatically: auth-error|rate-limit|timeout|token-limit|network-error|parse-error
  agent receives structured error with error_class, sigma notation, and "status": "failed"
  agent writes XVERIFY-FAIL to workspace findings section
  if ALL providers fail → agent notes "external verification unavailable" and proceeds without it
  ¬retry: if provider fails, do NOT retry in same round (budget protection). flag gap and move on.

!DA audit of verification:
  - ΣVerify available (per workspace ## infrastructure) but agent has zero XVERIFY/XVERIFY-FAIL on load-bearing findings → process violation (verification skipped)
  - XVERIFY-FAIL present but not flagged as gap → process violation
  - agent claims "externally verified" but no XVERIFY tag in workspace → challenge
  - cross_verify with partial coverage treated as full validation → challenge
  - unanimous XVERIFY agreement ¬sufficient to override domain expertise (advisory weight)

!cost: per-call API cost to external providers. Agents should be selective — verify load-bearing findings ¬every data point.

#### §2i precision gate (26.4.23)

!purpose: prevent false-precision in load-bearing quantitative claims — R19 eval B/3.14 calibration(3/4)+accuracy(3/4) failed on 4 distinct false-precision cases (F[TA-C2] withdrawn FTE range, F[TA-A2] $200K-$2M no driver breakdown, H2 10-13mo no CI, PM 35/20/25% no Bayesian). Quantification preceded justification.
!observed failure mode: agents attach numbers to claims without derivation, CI, reference class, or qualitative qualifier. Reader cannot distinguish calibrated estimate from anchoring artifact.

!applies-to: quantitative claims (numeric point estimates, ranges, percentages, timelines) in ANALYZE findings

gate fires when BOTH conditions met:
  CONDITION 1 (no uncertainty justification): numeric claim lacks ALL of — (a) explicit driver breakdown showing derivation | (b) CI or reference class cited | (c) qualitative qualifier ("order-of-magnitude", "illustrative", "approximately")
  CONDITION 2 (load-bearing): ANY one of — (i) >70% confidence tag | (ii) HIGH/CRITICAL-severity tag | (iii) cited in primary recommendation/conclusion

both fire → agent MUST produce ONE of:
  [a] driver breakdown: "derives from: [C1: X%] + [C2: Y%]..."
  [b] CI+RC: "80% CI [lo, hi] based on RC[{class}]={rate}"
  [c] qualitative restatement: "approximately [magnitude], precise estimate ¬supportable"

over-fire prevention (per C5 — defend each invocation, ¬create exceptions):
  - explicit qualitative qualifier satisfies CONDITION 1 → no fire
  - deterministic code/fact findings → CONDITION 2 won't trigger → no fire
  - "order-of-magnitude"/"illustrative"/"approximately" stated → CONDITION 1 satisfied → no fire

chain-evaluator enforcement (A20):
  CONDITION 2 = code-detected (text pattern matching): >70% confidence tag, HIGH/CRITICAL-severity tag, primary-recommendation marker
  CONDITION 1 suppression heuristic = keyword presence: driver-breakdown keywords, CI notation, "approximately"/"illustrative"/"order-of-magnitude" qualifiers
  A20 fires WARN + emits CAL-EMIT record to calibration-log.md (not BLOCK at plan-lock)
  CONDITION 1 full-semantic detection DEFERRED — calibration build required after ≥3-review evidence on CONDITION 2 (DA[#5] concession)
  CONDITION 1 enforcement in current build = DIRECTIVE (agents comply) + DA r2 challenge via existing "§2i check perfunctory" format

!path β+ audit-monitored calibration (ADR[β+]):
  §2i fires WARN until audit-calibration-gate.py outputs PROMOTE signal.
  promotion thresholds: ≥3 distinct reviews with fires AND ≤20% false-positive rate AND ≥5 DA-verdicted fires (not-reviewed ≠ legitimate).
  lead updates chain-evaluator mode WARN→BLOCK on PROMOTE.
  rationale: 20% FP threshold = C5-compatible ("80%+ hit rate = each invocation defensible on average"). >20% FP after 3 reviews → gate recalibration, ¬promotion.

!CAL-EMIT record format (emitted per A20 WARN firing):
  CAL-EMIT[A20]: review-id:{session-date-slug} |finding-ref:{F[agent-finding-id]} |fire-reason:{CONDITION-2-marker-matched} |workspace-context:{agent}:{finding-text-excerpt-50-chars} |da-verdict:PENDING

> BUILD variant → see build-directives.md §2i

#### §2p premise-audit pre-dispatch (26.4.23)

!purpose: prevent frame-anchoring — R19 evaluator flagged premises (tier-structure necessity, firm-size floor, data-readiness baseline, adoption likelihood) "accepted as frame" before H[] dispatch; DA in r2 did work that initial framing should have done. FORMAT-level intervention transfers 70-85% per CDS R[format-cognitive-REVISED].
!observed failure mode: lead reads user prompt → anchors on proposed tier/framework → writes H[] that test surface hypotheses while leaving structural premises unchallenged → agents confirm surface claims, premises uninvestigated.

!when: WORKFLOW STEP 7a — AFTER §7 prompt-decomposition, BEFORE H-level agent spawn
!applies-to: ANALYZE mode | BUILD mode → see build-directives.md §2p
!sequence-constraint: lead answers PA[1-4] INDEPENDENTLY before re-reading user's proposed H-space. order-is-load-bearing — reversing sequence recreates the anchoring.
!scope: STRUCTURAL premises ¬domain-depth (domain premises → §2e+DA)

4 structural premise tests:
  PA[1]: tier-necessity — is proposed tier/framework NECESSARY or is simpler structure adequate?
  PA[2]: firm-size-floor — minimum viable org? (state explicitly)
  PA[3]: data-readiness — what data must exist for findings to be actionable? (gap? yes/no)
  PA[4]: adoption-baseline — RC[{class}]={rate} | above/at/below base-rate?

!workspace format (lead writes to ## premise-audit-results in scratch/workspace BEFORE spawning agents):
  PREMISE-AUDIT[pre-dispatch]:
  PA[1]: tier-necessity: {CONFIRMED|CHALLENGED|GAP} — {one-sentence rationale}
  PA[2]: firm-size-floor: {minimum-org} | {assumption}
  PA[3]: data-readiness: {preconditions} | gap:{yes/no}
  PA[4]: adoption-baseline: RC[{class}]={rate} | above/at/below base-rate
  → proceed-with-H | revise-H-space({N}) | flag-premise({N})

!rules:
  - CHALLENGED/GAP on PA[1] or PA[2] → revise H-space BEFORE dispatch
  - CHALLENGED on PA[3] or PA[4] → convert to explicit H[] for agents to test
  - DA receives PREMISE-AUDIT in r2 — checks agents ¬re-anchored on challenged premises
  - ## premise-audit-results section MUST exist in workspace before agent spawn — chain-eval presence check BLOCK day-one (per PM[3] mitigation)

!cross-references:
  §8f DC[3]: post-exit-gate workspace-headers — ANALYZE post-DA-exit-gate sibling. §2p header (## premise-audit-results) is written BEFORE H[] dispatch; §8f headers (## promotion, ## sync, ## archive-complete, ## synthesis-complete) are written AFTER DA exit-gate PASS. Common pattern: workspace-header presence = phase-ran, ¬just-claimed.
  sigma-review/SKILL.md Step 1 sub-step: ANALYZE-side workflow placement (premise-audit pre-dispatch as Prepare sub-step; "Step 7a" label dropped per H7 r2 — structure survives, label dropped to avoid SKILL.md renumber-cascade).
  sigma-lead.md Step 1: ANALYZE-side workflow execution sub-step (mirrors c1-plan.md:62 Step 7a HARD GATE structure).

> BUILD variant → see build-directives.md §2p (Step 7a inserted in c1-plan.md between Step 7 and Step 8)

#### §2d-severity provenance (26.4.23, extension of §2d)

!purpose: distinguish finding-provenance from severity-provenance. R19 example: SR-11-7 exam findings (T1 banking-regulator source) extrapolated as severity for AI-agent review context. Transfer assumption itself unchecked. finding-claim and severity-claim are SEPARABLE epistemic objects — §2d tracks one, §2d-severity tracks the other.
!observed failure mode: agent cites T1 source for claim-provenance → inherits T1-quality aura for severity rating despite severity extrapolated across domain boundary. ECE compounded by extrapolation layer (CDS R[LLM-calibration]).

!applies-to: severity rating (LOW/MEDIUM/HIGH/CRITICAL) extrapolated from:
  - different-sector regulatory doc (banking→AI, pharma→fintech, etc.)
  - different-population base rate (exam-taker failure rate → review-error rate)
  - analogical cross-technology reasoning
!when ¬applies: severity from document being reviewed OR primary source covering exact domain → standard §2d tagging sufficient

!rule: severity by extrapolation MUST carry severity-basis tag alongside finding source tag
!format (3 required fields):
  |severity-basis:[extrapolation:{from-context}→{to-context} |assumption:{transfer-claim} |confidence-delta:{source-tier}→{extrapolation-tier}]

R19 example:
  F[RL-F1] HIGH-severity |source:[independent-research:T1(OCC SR-11-7)] |severity-basis:[extrapolation:SR-11-7-exam-findings→AI-agent-review-context |assumption:SR exam failure rates transfer to AI-agent error rates in comparable review scope |confidence-delta:T1→agent-inference]

!consequence: severity-basis:extrapolation → DA r2 explicit audit
  DA format: "ARTIFACT-AUDIT[§2d-severity|{finding-id}]: severity extrapolated {from}→{to}. State the assumption that makes transfer valid. Evidence disconfirming transfer?"
!rule: absence of |severity-basis:| tag on HIGH/CRITICAL extrapolated severity = process violation (same class as missing source tag)
!chain-evaluator: A23 detects HIGH/CRITICAL severity markers in findings + checks for |severity-basis:| presence when cross-domain indicators present. WARN + CAL-EMIT per path β+.

> BUILD variant → see build-directives.md §2d-severity

#### §2d++ source-bias probe (26.4.29, extension of §2d/§2d+)

!purpose: catch capture/conflict/framing bias modes that §2d+ authority-tier scoring and convergence rules miss. §2d+ rewards primary sources (5/5) regardless of whether they're the creator describing their own creation. Convergence (3+ sources) rewards interconnected peer-promotion ecosystems where convergence ≠ independent corroboration. §2d+ assigns one tier per source; the same source can be high-quality in descriptive register and low-quality in predictive register.
!observed failure mode (single-agent research pipeline, 26.4.29): plan-build cited Cat Wu Anthropic essay [creator-on-creation], Lenny's Newsletter recap [peer-promotion within VC-PM-podcast ecosystem], Pragmatic Engineer [commercial substack same ecosystem]. All scored 4-5/5 authority. Cross-source convergence reinforced rather than challenged the framing. Hype-anchoring on predictive claims survived §2d+ checks.
!observed-in: a single-agent research pipeline. NOT yet observed in sigma-review post-26.4.23 protocol. Added preemptively — capture/framing bias is independent of single-vs-multi-instance architecture, expected to apply equally.

!applies-to: load-bearing findings citing external commentary, founder/creator essays, podcast/newsletter/blog outlets, "thought leadership" content, or sources where the source benefits commercially or socially from the claim being true
!when ¬applies: regulatory primary sources, academic peer-reviewed sources, technical specifications — §2d+ T1 sufficient

bias types:
  [creator-on-creation] → source is head/founder/lead of system being discussed
  [framing-capture] → source sits within interconnected ecosystem (peer-cross-promotion); convergence with peers ≠ independent
  [register-predictive-load] → source's load-bearing claims are predictive/evaluative not descriptive
  [format-constraint] → softball-interview/product-demo format; adversarial pushback structurally absent
  [none] → bias-prone source vetted, no flag (explicit ¬omission)

!format extension: |source:[independent-research:T1] |source-bias:[creator-on-creation,framing-capture]

!rule: load-bearing predictive claim resting on [creator-on-creation] source → independent corroboration from outside creator's organization/ecosystem REQUIRED
!rule: convergence built from ≥2 [framing-capture] sources within same ecosystem → reclassify as single-source for §2d+ convergence; DA r2 challenge
!rule: missing |source-bias: tag on bias-prone source → process violation (same class as missing §2d source tag)

!DA audit (extension of §2d/§2d+ audit):
  - cluster of [creator-on-creation] sources supporting same predictive claim → echo chamber flag
  - convergence from peer-promoted sources within single ecosystem → independent-corroboration flag
  - load-bearing finding resting solely on [creator-on-creation] predictive claims with no out-of-ecosystem corroboration → bias-anchoring flag

!skill-reference: source-validation skill provides the underlying lens (capture patterns, descriptive-vs-predictive register split, third-party validation heuristics). Agents may invoke /source-validation as a research probe; this directive enforces the tagging.

#### §2j HIGH-severity governance minimum artifact (26.4.23)

!purpose: actionability floor for governance/compliance findings. R19 F[CDS-A1]+F[CDS-B1] scored Actionability 3/4 because recommendations stopped at gap-identification without templates, specimen crosswalks, or decision trees. Sherman Kent+SATs: receiver must be able to act without further consultation. Gap-ID alone fails.
!observed failure mode: Zeigarnik completion bias — naming the gap creates false closure. Recommendation "implement X governance" without artifact structure → adoption drops 30-40% vs artifact-bearing recommendation (Speier et al. 2003, MIS Quarterly).

!applies-to: HIGH-severity OR CRITICAL-severity findings in governance/compliance domain ONLY
  scope markers: committee structure | approval process | oversight role | compliance requirement | audit function
  ¬applies-to: technical findings, market findings, MEDIUM/LOW severity (anti-gold-plating scope)

!rule: qualifying finding MUST include minimum artifact (agent chooses one TIER) OR explicit "ARTIFACT-GAP: {reason}" tag

minimum artifact taxonomy:
  TIER-A: Template stub — fill-in-blank structure for recommended gate artifact (~20-30 min, minimum viable)
  TIER-B: Decision tree — binary branching logic operationalizing governance control
  TIER-C: Specimen artifact — completed example for context (most actionable, highest effort)

!DA exit-gate quality check (ADR[3]):
  format: "ARTIFACT-REVIEW[§2j|{finding-id}]: TIER-{A/B/C} |quality:{substantive|nominal} |→ accept|revise"
  nominal artifact (3-field placeholder satisfies letter ¬spirit) → DA challenges as perfunctory per §2 DA challenge template
  substantive = receiver could enact the governance control from the artifact alone
!rule: ARTIFACT-GAP tag without concrete reason ("deferred to next phase" insufficient) → DA challenge
!chain-evaluator: A22 detects HIGH/CRITICAL+governance markers + checks for TIER-A/B/C artifact presence OR ARTIFACT-GAP tag. WARN + CAL-EMIT per path β+.

> BUILD variant → see build-directives.md §3b actionability criterion extension

#### DA enforcement of hygiene checks

DA evaluates checks during challenge round:
grade modifiers:
  - check + visibly altered analysis (outcome 1) → no modifier (expected)
  - check + concern noted + specific justification (outcome 2) → no modifier (acceptable)
  - check + concern noted + NO justification → grade penalty, challenge issued
  - check missing entirely → process violation, mandatory re-do before convergence
  - check completed perfunctorily (filled section, didn't engage) → challenge issued

DA challenge format for weak checks:
  "DA[#N] process: §2[a/b/c/e/i/p/j/d-severity] check on [finding] is perfunctory.
   You wrote '[what they wrote]' but then [what they did that contradicts it].
   |→ revise finding to reflect check result, or provide specific evidence
   for why concern doesn't apply. 'It's still the right approach' is ¬specific evidence."

#### DA verdict on CAL-EMIT records (26.4.23, path β+)

!purpose: close the calibration loop for WARN-first gates (§2i/§2j/§2d-severity + A24 sigma-verify pre-flight — all four path-β+ gates). audit-calibration-gate.py gates BLOCK-promotion on ≥3 reviews + ≤20% FP rate — this requires DA verdicts on each firing to classify legitimate vs false-positive.

!when: DA r2 exit-gate — DA processes every CAL-EMIT[PENDING] record written to workspace by chain-evaluator this session

!rule: for each CAL-EMIT[{gate-id}] record in workspace with da-verdict:PENDING:
  DA appends: da-verdict:{legitimate|false-positive|not-reviewed}
    legitimate: gate correctly flagged a real §2i/§2j/§2d-severity/A24 violation — agent should revise
    false-positive: gate fired on well-formed finding; heuristic mismatch — record for gate recalibration
    not-reviewed: DA examined workspace but could not adjudicate this firing (time-boxed, out-of-domain) — record as missing data

!DA exit-gate format extension:
  exit-gate: PASS|FAIL |engagement:[grade] |unresolved:[...] |hygiene:[...] |cal-emit-verdicts:{N-total}/{N-legitimate}/{N-false-positive}/{N-not-reviewed}

!rule: CAL-EMIT[PENDING] records left in workspace at DA exit-gate = process violation (same class as missing DA challenges). DA MUST verdict all PENDING records before PASS.
!rule: not-reviewed >30% after 3 reviews → lead flags calibration stall, sigma-audit runs audit-calibration-gate.py manually.

> build-mode guardrails (§4a-d: scope creep, assumption conflicts, gold-plating, test integrity) → see build-directives.md

### success criteria (ANALYZE mode)

1→ zero rounds with zero-dissent convergence
2→ positioning/calibration/valuation/premise-viability checks in r1 findings — each produces outcome 1/2/3 (¬perfunctory)
3→ DA challenges before integration
4→ DA challenge held ratio 40-70%
5→ DA exit-gate exercised (synthesis-ready verdict issued, ¬skipped)
6→ debate produces clear rulings on ≤2 contested claims per cycle
7→ deliverable includes ruling AND dissent

> BUILD mode success criteria → see build-directives.md

### review clause
after 3 cycles (≥1 ANALYZE + ≥1 BUILD) → DA assesses adversarial layer value vs overhead → patterns.md

→ actions:
→ new directive → append with version+date
→ directive revision → update version, note change in ctx

## superforecasting protocol v1.1 (26.3.15)

scope: sigma-review ANALYZE operations requiring estimates, forecasts, or probability assessments
modes: ANALYZE (market/domain forecasts) — BUILD variant → see build-directives.md
companion: adversarial-layer v2.0, analytical-hygiene forcing function

### §3 superforecasting methodology (Tetlock)

!purpose: ground analysis in base rates and historical precedent. Superforecasters outperform professional analysts by 30% (Good Judgment Project). Key insight: experts overweight inside-view narrative reasoning; outside-view (base rates + analogues) is more reliable.

#### decomposition mandate

!rule: complex questions MUST be decomposed into 3-7 independent sub-questions before analysis
format per sub-question:
  "SQ[{N}]: {sub-question} |estimable: {yes/no} |method: {base-rate/analogue/data} |→ {which-agent-best-answers}"
!purpose: prevents anchoring on a single narrative. Each sub-question gets independent analysis.

> BUILD variant → see build-directives.md §3 decomposition

#### reference class forecasting

!rule: before ANY original analysis, identify the reference class
format:
  "RC[{question}]: reference-class={category} |base-rate={frequency} |sample-size={N} |src:{source} |confidence:{H/M/L}"
!rule: team estimates that deviate >15pp from reference class base rate MUST justify deviation with specific evidence (outcome 1 or 2 from §2 hygiene)

> BUILD variant → see build-directives.md §3 reference class forecasting

#### historical analogues
!rule: identify 3-5 historical analogues for each major analysis question
format:
  "ANA[{N}]: {description} |outcome:{what-happened} |similarity:{H/M/L} |key-difference:{what's-different} |src:{source}"
!purpose: forces pattern-matching against real precedent, ¬theoretical reasoning

#### calibrated probability estimates

!rule: key estimates must include calibrated ranges, ¬point estimates only
format:
  "CAL[{estimate}]: point={best} |80%=[{low},{high}] |90%=[{lower},{higher}] |assumptions:{what-must-be-true} |breaks-if:{condition}"
!enforcement: DA checks calibration quality. Overconfident ranges (80% band < 20% of point estimate) → challenge

> BUILD variant → see build-directives.md §3 calibrated probability estimates

#### pre-mortem analysis

!rule: every ANALYZE review must include pre-mortem: "It's 3 years later and this failed. What happened?"
format:
  "PM[{N}]: {failure-scenario} |probability:{%} |early-warning:{signal} |mitigation:{prevention}"
!minimum: 3 failure scenarios, each with probability estimate

> BUILD variant → see build-directives.md §3 pre-mortem

#### outside-view reconciliation
!rule: AFTER all agents complete inside-view analysis, reference-class-analyst produces reconciliation
format:
  "OV-RECONCILIATION: inside-view={team-estimate} |outside-view={base-rate-estimate} |gap={difference} |→ {reconcile: which is more trustworthy and why}"
!rule: if gap >15pp → DA must challenge the divergence in R2
!rule: team may choose inside-view BUT must document specific evidence for deviation

### §3a adaptive agent count v1.1 (26.3.15)

!purpose: right-size team to task complexity. Research shows (AgentDropout 2025) not all agents needed for all questions. Reduces 15-26x cost multiplier to 3-5x for simple analyses.
modes: ANALYZE (analysis complexity) — BUILD complexity tiers → see build-directives.md §3a

#### ANALYZE complexity tiers

TIER-1 (simple, 3+DA agents):
  criteria: single-domain question, well-defined scope, existing precedent available
  team: primary-domain-agent + reference-class-analyst + synthesist + DA(from-r2)
  cost: ~3-5x single-agent

TIER-2 (moderate, 4-5+DA agents):
  criteria: multi-domain question, some ambiguity, limited precedent
  team: 2-3 domain agents + reference-class-analyst + DA(from-r2)
  cost: ~8-12x single-agent

TIER-3 (complex, 5-8+DA agents):
  criteria: novel domain, high uncertainty, multi-stakeholder, high-stakes decision
  team: 3-5 domain agents + reference-class-analyst + dynamic specialists + DA(from-r2)
  cost: ~15-26x single-agent

> BUILD complexity tiers → see build-directives.md §3a

#### complexity detection (ANALYZE)
lead evaluates at task creation:
  1→ domain count: how many expertise areas touched?
  2→ precedent availability: well-trodden or novel?
  3→ decision stakes: cost of being wrong?
  4→ ambiguity level: is the question well-defined?
  5→ uncertainty: how much is unknown?

scoring: 1-5 per factor. Sum < 12 → TIER-1 | 12-18 → TIER-2 | >18 → TIER-3

#### dynamic escalation
!rule: if TIER-1 review surfaces unexpected complexity during R1 → lead escalates to TIER-2 (adds agents)
!rule: if TIER-2 DA identifies domain gap → escalate to TIER-3 (dynamic agent creation)
!rule: never DE-escalate mid-review (removing agents loses context)

#### lead reports tier selection
format: "complexity-assessment: {tier} |scores: domain({N}),precedent({N}),stakes({N}),ambiguity({N}),uncertainty({N}) |total:{sum} |team-size:{N}"
user may override tier selection

### §3c implementation triage — when to use sigma-review (26.3.22)

!purpose: formalize decision boundary for sigma-review vs enhanced single-instance. Research confirms enhanced single-instance achieves ~85-88% of sigma-review quality at ~4-5% cost. Sigma-review justified only when its irreducible advantages (DA context firewall + cross-session calibration) are load-bearing.

!decision-rule: ALL three conditions must hold for sigma-review:
  1→ stakes: ≥$1M financial impact OR regulatory consequence OR 12+ month strategic decision
  2→ herding-risk: contested claims, multiple plausible hypotheses, confirmation bias danger
  3→ calibration-matters: decision depends on probability estimates being accurate ¬just directionally correct

!fail-any → use enhanced single-instance with cognitive frameworks (calibration protocol + Toulmin warrants + dialectical self-challenge + source tiers + pre-mortem)

!sigma-review NOT justified when:
  - question is fact-verifiable (correct answer exists — look it up)
  - domain has zero accumulated sigma-review calibration history
  - zero functional diversity needed (single domain, single perspective sufficient)

!lead reports triage decision:
  format: "TRIAGE: sigma-review|single-instance |stakes:{met/not-met} |herding:{met/not-met} |calibration:{met/not-met}"
  user may override triage

### §3b evaluation protocol v1.1 (26.3.15)

!purpose: measure quality systematically. Replaces ad-hoc "was it good?" with rubric-based evaluation.
!when: after synthesis complete (post-DA-exit-gate), before promotion phase
!optional: lead or user can invoke /sigma-evaluate at any time
modes: ANALYZE (analysis quality) — BUILD rubric → see build-directives.md §3b

#### ANALYZE rubric (8 criteria, 4-point scale)
1→ accuracy: factual claims correct, citations verified, numbers from reliable sources (4=all verified, 1=significant errors)
2→ completeness: all major perspectives covered, no strawmanning, stakeholders represented (4=comprehensive, 1=one-sided)
3→ logic: reasoning chains sound, conclusions follow from premises, no fallacies (4=rigorous, 1=significant flaws)
4→ evidence-quality: authoritative sources, base rates applied, counter-evidence addressed (4=primary sources+base rates, 1=weak/absent)
5→ calibration: confidence appropriate to uncertainty, assumptions explicit, ranges provided (4=explicit uncertainty, 1=false precision)
6→ actionability: recommendations concrete, decision-relevant, implementation path clear (4=specific actions+criteria, 1=purely descriptive)
7→ scope-integrity: analysis stays within stated scope, zero external contamination (4=perfectly scoped, 1=significant contamination)
8→ source-provenance: findings properly tagged with source types (§2d), prompt claims independently verified, no echo clusters (4=all findings independently sourced with provenance, 3=≤10% [prompt-claim] without corroboration, 2=>10% unverified prompt-derived, 1=>30% or echo clusters detected)

> BUILD rubric → see build-directives.md §3b

#### grading
A: 3.5-4.0 avg | B: 2.8-3.4 | C: 2.0-2.7 | D: 1.5-1.9 | F: <1.5

#### pipeline
see /sigma-evaluate skill for full evaluation pipeline (3 evaluator agents + judge)

#### calibration feedback loop
!rule: when predictions from past reviews resolve (outcomes known), update agent calibration data
format: "OUTCOME[{review}:{prediction}]: predicted={X} |actual={Y} |error={delta} |→ calibration-update"
!purpose: each review makes future reviews more accurate through tracked calibration

#### log score tracking (26.3.22)

!purpose: formally track agent calibration across reviews using log scoring (preferred over Brier for sigma-review's use case — log scoring penalizes confident-wrong more heavily, which is the identified failure mode). Only ~30-40% of estimates have resolvable outcomes; value compounds cross-session.

!workspace format (added at review close for resolvable estimates):
```
## calibration-tracking
LS-TRACK[{review}:{agent}:{estimate-id}]: predicted:{point} |range:{80%=[lo,hi]} |resolution-date:{date|none} |outcome:PENDING |log-score:PENDING
```

!agent memory extension:
  agents with resolved estimates update: LS-avg:{score}|n:{count}|trend:{improving|stable|declining}

!lead usage at synthesis:
  read agent LS-avg from memory → weight agent probability claims by historical calibration quality
  agents with declining trend + high confidence → DA flag

!resolution protocol:
  when estimate outcome becomes known → lead updates LS-TRACK with outcome + log-score
  lead stores OUTCOME[{review}:{prediction}] per existing §3b format
  log-score = -log2(predicted probability of actual outcome)
  lower score = better calibration

## bayesian-consensus-tracking v1.1 (26.3.15)

scope: sigma-review ANALYZE operations — replaces fixed round-count heuristic with evidence-based stopping
modes: ANALYZE → P(consensus) — BUILD → P(plan-ready)|P(build-quality) (two-phase dynamic) → see build-directives.md §4
companion: adversarial-layer v2.0, superforecasting protocol

### §4 belief-state round management

!purpose: determine when to stop analyzing based on evidence quality, ¬arbitrary round count. Fixed "min 3, max 5" replaced by P(synthesis-ready | evidence). Inspired by ECON framework (ICML 2025) and sequential Bayesian consensus building.

#### belief state computation (lead computes post-each-round)

after each round, lead computes:
```
BELIEF-STATE[r{N}]:
  P(consensus) = prior × L(evidence) / normalizer
  prior: base-rate-consensus-for-task-type
    simple-task: 0.7 | moderate: 0.5 | complex: 0.3 | novel: 0.2
  L(evidence) = f(agreement-ratio, revision-quality, gap-count, DA-grade)
    agreement-ratio: {agents-aligned}/{total-agents} (0-1)
    revision-quality: how much did findings improve this round? (none=0.5, minor=0.7, material=0.9)
    gap-count: unresolved gaps flagged by agents (each gap × 0.9 penalty)
    DA-grade: DA engagement assessment (A=1.0, B=0.85, C=0.7, D=0.5, F=0.3)
  posterior: P(consensus | r{N} evidence)
```

#### stopping rules
!rule: P(consensus) > 0.85 → synthesis-ready (propose to DA for exit-gate)
!rule: P(consensus) 0.6-0.85 → another round (targeted, address specific gaps)
!rule: P(consensus) < 0.6 → deep disagreement (trigger Toulmin debate or escalate to user)
!rule: DA exit-gate STILL required even if P(consensus) > 0.85 (Bayesian = proposal, DA = gate)
!rule: hard cap remains at r5 regardless of P(consensus)

#### workspace format
lead writes after each round:
```
BELIEF[r{N}]: P={posterior} |prior={X} |agreement={ratio} |revisions={quality} |gaps={count} |DA={grade}
  |→ {synthesis-ready|continue(target:{gaps})|deep-disagreement(trigger:{action})}
```

> BUILD belief states P(plan-ready)|P(build-quality) (two-phase dynamic, 26.3.27) → see build-directives.md §4

#### why this matters (ANALYZE)
- r1 with 9 tensions and 0.3 prior → P(consensus)≈0.25 → clearly needs r2 (correct)
- r2 with 14/14 DA challenges addressed, all agents B+ → P≈0.88 → synthesis-ready (correct)
- prevents wasted rounds when consensus is genuine
- prevents premature synthesis when disagreements are unresolved
- gives DA objective data for exit-gate decision

### §4a agentic retrieval protocol v1.1 (26.3.15)

scope: structured data retrieval during sigma-review ANALYZE operations
modes: ANALYZE (market research) — BUILD retrieval strategies → see build-directives.md §4a
companion: superforecasting protocol (base rate retrieval), analytical hygiene (evidence quality)

!purpose: replace ad-hoc web search with quality-scored retrieval. Inspired by MAIN-RAG (ACL 2025) multi-agent filtering and Corrective RAG patterns.

#### when to use agentic retrieval
- reference-class-analyst needs base rate data or historical analogues
- DA needs counter-evidence for challenges
- any agent flags §2b calibration gap (outcome-3: can't resolve with existing data)
- lead identifies research gap in workspace
- user requests deep research on specific topic

#### retrieval quality scoring
every retrieved document scored on 3 dimensions (0-5 each):
  relevance: how directly does this answer the question? (5=directly, 0=tangential)
  authority: primary source(5) > academic(4) > industry report(3) > news(2) > blog/marketing(1) > unverifiable(0)
  recency: <6mo(5) | 6-12mo(4) | 12-18mo(3) | 18-24mo(2) | 24-36mo(1) | >36mo(0)

filter threshold: total ≥ 10/15 passes | <10 flagged as low-confidence

#### cross-document validation
!rule: claims supported by 3+ independent sources → CONVERGENT (high confidence)
!rule: claims from single source → UNVERIFIED (flag, ¬discard)
!rule: sources that contradict majority → COUNTER-EVIDENCE (valuable, preserve)
!rule: counter-evidence search is MANDATORY for every retrieval (¬optional)

#### integration with review
- agents can invoke /sigma-retrieve {query} during analysis
- results written to workspace as research package
- reference-class-analyst uses retrieval for base rates and analogues
- DA uses retrieval for counter-evidence

> BUILD retrieval strategies → see build-directives.md §4a

see /sigma-retrieve skill for full pipeline (query decomposition → parallel retrieval → validation → synthesis)

### §4b knowledge graph protocol v1.1 (26.3.15)

scope: structured domain knowledge for sigma-review ANALYZE operations
modes: ANALYZE (market entities) — BUILD codebase graph → see build-directives.md §4b
location: agent-infrastructure/knowledge-graphs/{domain}/

!purpose: provide structured entity-relationship data that enables multi-hop reasoning. Web search finds text; knowledge graphs find connections.

#### graph structure
each domain graph contains:
  entities.md — entity type definitions (fields, examples)
  relationships.md — relationship type definitions (direction, properties)
  graph.md — actual graph data (entities + relationships, ΣComm-compressed)

#### entity format
```
E[{name}|type:{entity-type}|{field1}:{value}|{field2}:{value}|src:{source}|date:{date}]
```

#### relationship format
```
R[{entity-A}|{relationship-type}|{entity-B}|{property1}:{value}|{property2}:{value}]
```

#### agent usage
agents read graph files during boot or analysis:
  1→ identify relevant domain graph for current task
  2→ read graph.md → extract relevant entities and relationships
  3→ use relationships for multi-hop reasoning (A→B→C)
  4→ cite graph data in findings: "per KG[{domain}]: {entity} {relationship} {entity}"

#### graph maintenance
- seeded from review findings (post-review, agents contribute new entities/relationships)
- lead validates new entries against existing graph (¬duplicate, ¬contradict)
- graphs grow across reviews — each review adds domain knowledge
- format: "KG-UPDATE[{domain}]: +E[{entity}] |+R[{relationship}] |src:{review-name} |date:{date}"

> BUILD codebase graph → see build-directives.md §4b

#### available graphs
(none shipped — each graph is created by the first review that needs it)
→ additional domains created as reviews warrant

## dynamic-agent-orchestration v1.0 (26.3.11)

scope: sigma-review operations requiring adaptive team composition
companion: adversarial-layer v2.0

### §1 dynamic agent creation protocol

#### when to create
trigger: active agent identifies domain gap meeting ALL:
  1→ gap is MATERIAL to task (¬tangential curiosity)
  2→ no existing agent covers domain (check roster before requesting)
  3→ gap requires DEPTH web search alone cannot provide
     (single search answers question → just search ¬spin up agent)
  4→ requesting agent articulates WHAT new agent investigates + WHY existing agents can't cover

!do-NOT-create for:
  - questions answerable by single web search
  - domains covered by existing agent (message them instead)
  - "nice to have" perspectives ¬changing deliverable
  - more than 3 dynamic agents per task (token budget — see §3)

#### how to request
any agent → lead inbox:
  "agent-request: [proposed-role] |domain: [expertise needed] |gap: [uncovered question/domain] |trigger: [workspace entry citation] |impact: [deliverable change if unaddressed] |→ lead: approve|deny|merge-with-existing"

lead evaluates:
  1→ gap real? (workspace — requesting agent cited specific evidence?)
  2→ gap material? (deliverable meaningfully weaker without domain?)
  3→ existing agent can absorb? (broadening scope > new agent sometimes)
  4→ token budget? (see §3 — hard cap on dynamic agents)

lead response:
  approve → create agent per §2
  deny → explain why, suggest alternative
  merge → assign domain to existing agent with expanded scope directive

#### DA role in dynamic creation
DA reviews ALL agent-request proposals before lead approves:
  1→ filling real gap or reinforcing existing consensus?
     (!failure-mode: team requests "specialist" who will agree with them)
  2→ contrarian specialist more valuable than confirmatory?
  3→ DA may counter-propose alternative agent framing

DA ¬veto power — lead decides | DA objections recorded in decisions.md

### §2 new agent lifecycle

#### creation sequence

phase-1 DEFINE (lead):
  !MUST use ~/.claude/teams/sigma-review/agent-defs/_template.md as base — copy template, fill in role-specific sections
  template provides: boot sequence, comms, persistence, promotion, research, convergence,
    analytical hygiene (§2a-e), source provenance (§2d/§2d+), cross-model verification (§2h),
    dialectical bootstrapping (§2g) — all non-negotiable standards
  lead fills in: Role, Expertise, Review steps, Weight, Domain Gap Reporting
  !include: current task context + GAP that triggered creation

  !rule: pick the name FIRST — it is the identity key everywhere (see sigma-lead.md Spawn rules).
    lowercase-with-hyphens, unique against the roster, ¬a prefix-collision with an existing entry.
  !rule: create ALL FIVE name-keyed locations before phase-2, in this order:
    1→ `~/.claude/teams/sigma-review/agent-defs/{name}.md`            (from _template.md)
    2→ `T/agents/{name}/`                      (DIRECTORY — see below, load-bearing)
    3→ `T/inboxes/{name}.md`                   (empty inbox, so peers can reach it in phase-3)
    4→ roster.md entry: `{name} |domain: … |wake-for: … |dynamic: created {date} per {trigger}`
    5→ workspace `### {name}` section
  !rule: step 2 is the one that silently breaks. sigma-mem's `_detect_agent_identity()` enumerates the
    `T/agents/*/` DIRECTORY NAMES and matches them against the agent's `"I'm {name}"` self-declaration.
    ¬directory → ¬identity match → no `agent_boot`, and the new agent researches memoryless through
    phase-2 with no error raised. `setup.sh` creates these dirs at install time from the agent-def
    filenames, so only mid-task agents hit this.
  !rule: `dynamic:`/`added:` roster markers are provenance for humans — sigma-mem's roster parser reads
    only `domain:` and `wake-for:`. Write them anyway: they are how a later audit reconstructs WHY the
    agent exists (cf. regulatory-licensing-specialist 26.3.11, cognitive-decision-scientist 26.3.21,
    security-specialist 26.4.5).

phase-2 RESEARCH (new agent, solo):
  reads: workspace, roster, decisions.md, patterns.md
  conducts: independent domain research (web search, build memory)
  writes: initial findings to own workspace section + initial memory
  !does NOT message other agents yet — research first, communicate after
  duration: equivalent to 1 full round for existing agents

phase-3 INTEGRATE (new agent joins team):
  joins NEXT scheduled round
  sends intro findings to all peer inboxes (ΣComm):
    "new-agent:[role] |domain:[areas] |gap:[what I cover] |initial-findings: [top 3-5 ΣComm] |¬[investigated+ruled-out] |→[contribution to current task] |#[count]"
  receives peer inbox messages normally from this point
  DA includes new agent in challenge cycle
  must complete analytical hygiene checks (adversarial §2a-c,§2e) before first convergence

phase-4 PERSIST (memory retained):
  memory: ~/.claude/teams/sigma-review/agents/{agent-name}/memory.md
  available for future tasks IF domain relevant
  lead decides at task creation whether to wake dormant agents

#### integration timing

!rule: new agent NEVER joins mid-round
  current round completes → new agent researches → joins next round

ANALYZE mode:
  gap in r1 → agent created → researches during r1→r2 transition → joins r2
  gap in r2 → agent created → researches during r2→r3 transition → joins r3 (late ¬absent)
  gap in r3 (if DA FAIL → more rounds) → agent created → researches during r3→r4 transition → joins r4
  gap in r4+ → ¬create (too late — note in patterns.md for future tasks)
  !rule: dynamic agent creation does NOT extend round cap beyond 5

BUILD mode:
  gap in r1 → agent created → researches during r1→r2 transition → joins r2 (ideal)
  gap in r2 → agent created → researches during r2→r3 transition → joins r3 as reviewer/advisor ¬builder
    !new agent does NOT build code in r3 (no plan approved, joining mid-build = chaos)
  gap in r3+ → ¬create (too late — note for next cycle)

### §3 token budget management

#### ΣComm three-tier model

!directive: notation form follows audience+frequency, mechanically enforced

Tier 1 (full ΣComm, BLOCK enforcement):
  - memory writes (sigma-mem store_*)
  - agent spawn prompts (Boot/Work/Comms/Weight/Review sections)
  - MCP tool descriptions

Tier 2 (tagged English, WARN→BLOCK after calibration):
  - workspace findings (workspace.md, c*-scratch.md)
  - agent-to-agent inbox messages (SendMessage payload)
  - convergence declarations, DA challenges+responses, debate exchanges
  - required tags on finding blocks: |source:|, severity (HIGH/MEDIUM/LOW), status verb (VERIFIED/CONVERGED/RESTATE/WITHDRAWN/PASS/FAIL/PENDING)
  - identifier-gated: blocks without DA[#N]/IC[N]/ADR[N]/etc. are exempt

Tier 3 (plain English, no enforcement):
  - agent Role/Expertise (identity), open-questions (user reads)
  - user-facing deliverables, debate judge rulings, format specs

!enforcement: phase-gate.py PostToolUse on Write/Edit + SendMessage detects Tier-2 finding blocks missing required tags (WARN); BLOCK promotion gated on ≤5% FP-rate over ≥20 workspace writes. Tier-1 BLOCK on sigma-mem store_* tools (PreToolUse).

#### dynamic agent token caps

hard caps:
  - max 3 dynamically created agents per task
  - total team size: max 8 agents (roster + dynamic) per task
  - new agent research phase: budget ≡ 1 existing-agent round

prioritization (approaching token limits):
  1→ lead declares "token conservation mode"
  2→ agents compress further (findings only, ¬extended reasoning)
  3→ DA challenges limited to top 3 (¬comprehensive sweep)
  4→ debate rounds reduced 3→2 (opening + synthesis, skip rebuttal)
  5→ new agent creation suspended for remainder

!monitoring: lead tracks per round
  workspace: "token-status: [round] [agent-count] [estimated-usage] [budget-remaining]"

#### memory compression for persistence

!pattern: research notes → compressed references ¬full prose
  good: "R[26.3.11] EU-AI-Act: enforcement Aug-2026 |extraterritorial |fines 7%revenue/€35M |national-varies |open-source-exemption-contested |#5"
!pattern: calibration entries → terse
  good: "C[26.3.11] regulatory-timelines: announced→enforced 6-18mo lag |member-state +3-12mo |lobbying-delays-common"
!pattern: findings reference workspace ¬duplicate
  good: "F[26.3.11] r1: 7 findings(3H,2M,2L) |see workspace |key: extraterritorial-scope-underestimated"

compression target: memory ≤ 200 lines per agent after any round
  exceeding: summarize older entries, preserve calibration + active patterns

## context-contamination-protocol v1.1 (26.3.15)

scope: sigma-review ANALYZE operations — protects analysis integrity from context bleed
BUILD scope boundary → see build-directives.md §6f
companion: adversarial-layer v2.0, evaluation protocol, §7 prompt-decomposition-protocol (input-side prevention), §2d source provenance (tagging mechanism)

!purpose: LLM context windows don't have scope boundaries. Topics discussed in the same session
contaminate each other's outputs via salience bias (recency + emotional relevance + specificity).
Observed 26.3.14: casual career discussion contaminated system documentation.

### §6a scope declaration
!rule: workspace MUST include ## scope-boundary listing what review IS and IS NOT about
!rule: lead populates "NOT about" list from current conversation topics outside the review
!rule: lead re-reads scope-boundary before writing synthesis or documents

### §6b agent context firewall
!rule: agent spawn prompts include explicit context firewall section
!rule: agents told they have NO knowledge of conversation outside their task
!rule: agents note any out-of-scope signals encountered: "out-of-scope signal ignored: {description}"

### §6c lead self-check
!rule: before writing synthesis/documents, lead identifies out-of-scope session topics
!rule: after generating, lead greps output for contamination terms
!rule: contamination found → revise before presenting
!format: "CONTAMINATION-CHECK: session-topics-outside-scope: {list} |scan-result: clean|contaminated({terms})"

### §6d document isolation
!rule: shareable documents generated via spawned agents (isolated context)
!rule: document agents receive workspace data ONLY, ¬conversation context
!rule: document agent prompt includes ONLY: task description, workspace findings, review data
!rule: document agent prompt does NOT include: user conversation, casual remarks, career goals, unrelated topics

### §6e evaluation
!rule: /sigma-evaluate includes scope-integrity criterion (7th ANALYZE rubric item)
!rule: scope-integrity scores: 4=zero contamination | 3=minor tangential | 2=noticeable out-of-scope | 1=significant contamination
!rule: when §6g active, scope-integrity ALSO evaluates temporal contamination:
  4=zero post-cutoff sources, no hindsight markers, all claims have pre-cutoff provenance
  3=minor: 1-2 post-cutoff sources caught+replaced, no outcome-revealing language
  2=noticeable: post-cutoff framing present, some claims lack pre-cutoff sourcing
  1=significant: confidential-then-public data used, outcome knowledge shapes analysis, sources mostly post-cutoff

> §6f BUILD scope boundary → see build-directives.md §6f

### §6g temporal scope boundary (26.3.15)

!trigger: task includes temporal framing — "as of {date}", "using data available before {date}",
  retrospective analysis, historical scenario, or any explicit information cutoff.
  lead detects temporal framing during workspace initialization → activates §6g

!purpose: LLMs trained on post-event data cannot naturally respect temporal information boundaries.
  Web search returns post-event analysis when querying pre-event topics. Model training knowledge
  includes outcomes the analysis persona would not know. Three contamination vectors:
  (1) web search results contain post-cutoff sources + summaries
  (2) model training knowledge includes post-cutoff outcomes
  (3) confidential information made public only after cutoff (e.g. regulatory post-mortems)
  Observed 26.3.15: SVB stress test — all 14 non-filing sources post-dated the Jan 2023 cutoff,
  confidential CAMELS ratings appeared as "findings," probability estimates showed hindsight anchoring.

#### §6g-1 temporal boundary declaration
!rule: workspace ## scope-boundary MUST include temporal-boundary field when §6g triggers
!format:
  "temporal-boundary: {YYYY-MM-DD}
   information-regime: only sources published + publicly available before {date}
   model-knowledge: post-cutoff knowledge of outcomes is OUT OF SCOPE
   confidential-to-public: information that was confidential at cutoff but later made public = OUT OF SCOPE"
!rule: lead extracts cutoff date from task description. If ambiguous → ask user before proceeding

#### §6g-2 agent temporal firewall
!rule: agent spawn prompts include temporal firewall section when §6g active
!format in spawn prompt:
  "## temporal-boundary: {YYYY-MM-DD}
   You are analyzing as of this date. You do NOT know what happened after this date.
   - Do NOT reference events, publications, or outcomes after {date}
   - Do NOT use knowledge of what subsequently happened to inform your analysis
   - ALL claims must cite a specific source with publication date before {date}
   - If you cannot find a pre-cutoff source for a claim, flag: UNSOURCED-CLAIM: {claim} |basis: model-knowledge
   - If web search returns post-cutoff sources, extract only data points that existed pre-cutoff
     and cite the ORIGINAL pre-cutoff source, not the post-cutoff summary"

#### §6g-3 source-date audit
!rule: MANDATORY before synthesis when §6g active
!rule: every cited source must include publication date or filing date
!rule: lead audits all sources against temporal-boundary:
  source published BEFORE cutoff → ✓ valid
  source published AFTER cutoff citing pre-cutoff data → extract original source, cite that instead
  source published AFTER cutoff with no pre-cutoff equivalent → ✗ reject, flag for removal
  confidential material released publicly AFTER cutoff → ✗ reject (even if material predates cutoff)
!format: "SOURCE-AUDIT[§6g]: {N} sources checked |{valid}✓ |{rejected}✗ |{replaced}↻"
!rule: if >25% sources rejected → lead re-examines findings that relied on rejected sources
  findings without valid pre-cutoff sourcing → downgrade confidence or remove

#### §6g-4 temporal contamination scan
!rule: extends §6c — lead greps output for temporal contamination markers IN ADDITION TO topic markers
!scan-targets:
  - dates/years after cutoff (e.g. if cutoff=2023-01-31, scan for "March 2023", "April 2023", "2024", etc.)
  - outcome-revealing terms: "collapse", "failure", "failed", "shutdown", "receivership", "post-mortem",
    "lessons learned", "in hindsight", "we now know", "subsequently", "ultimately"
  - post-event report titles or authors known to be post-cutoff
  - regulatory confidential terms that only became public post-cutoff
!format: "TEMPORAL-SCAN[§6g]: cutoff={date} |post-cutoff-refs: {list|none} |outcome-terms: {list|none} |result: clean|contaminated"
!rule: contamination found → revise. Do NOT present contaminated output to user

#### §6g-5 hindsight-bias check (DA responsibility)
!rule: when §6g active, DA receives additional directive in spawn prompt:
  "TEMPORAL REVIEW: This analysis has a temporal boundary of {date}. In addition to your standard
   adversarial role, specifically check for:
   - Findings that are correct but suspiciously precise (hindsight anchoring)
   - Probability estimates that are too narrow or too confident for the stated information regime
   - Claims sourced to post-cutoff publications or confidential-then-public materials
   - Narrative framing that reflects post-event consensus rather than pre-event uncertainty
   Flag each as: HINDSIGHT-BIAS[{finding}]: {why suspicious} |pre-cutoff basis: {exists|missing}"
!rule: DA hindsight flags treated same as standard DA challenges — agents must concede|defend|compromise

#### §6g-6 provenance requirements
!rule: when §6g active, agent findings format adds provenance field:
  standard: "F[date] finding-name: {content} |confidence:H/M/L"
  temporal: "F[date] finding-name: {content} |confidence:H/M/L |src:{source-name}({pub-date}) |provenance:filing|public-data|pre-cutoff-research|model-knowledge"
!rule: provenance=model-knowledge → confidence capped at M (cannot be H without external source)
!rule: provenance=filing or provenance=public-data → confidence can be H if data is unambiguous
!rule: lead tallies provenance distribution in synthesis:
  "PROVENANCE[§6g]: filing:{N} |public-data:{N} |pre-cutoff-research:{N} |model-knowledge:{N}"
  model-knowledge >30% of findings → flag review as potentially contaminated, note in output

## tiered-model-strategy v1.0 (26.3.15)

scope: all sigma-review operations — reduces cost by matching model capability to task
companion: adaptive agent count (§3a)

!purpose: reduce 15-26x cost multiplier to 3-8x. Not all agents need same capability.
Opus for adversarial + calibration-critical. Sonnet for domain analysis + standard synthesis.
Haiku for evaluation scoring + simple retrieval.

### §5a model tiers
TIER-A (opus): adversarial challenge, calibration-critical, low-consensus synthesis
TIER-B (sonnet): domain analysis, standard synthesis, most R1 work
TIER-C (haiku): evaluation scoring, simple retrieval, routine checks

### §5b assignment rules
DA: always TIER-A (adversarial quality directly correlates with model capability)
reference-class-analyst: TIER-A (calibration accuracy critical)
domain agents R1: TIER-B (breadth over depth in research round)
domain agents R2 (DA response): TIER-B (concede/defend decisions are straightforward)
synthesist/lead synthesis: TIER-B default, TIER-A if P(consensus) < 0.7
evaluators (/sigma-evaluate): TIER-C for scoring, TIER-B for judge
retrievers (/sigma-retrieve): TIER-C for search, TIER-B for validation

### §5c override rules
!rule: user can override: "use opus for all" or "use sonnet for all"
!rule: lead can escalate: if TIER-B agent produces low-quality output, re-run as TIER-A
!rule: lead reports model selection: "MODEL[{agent}]: {tier}({model}) |reason: {why}"

### §5d effort tier (second dial, orthogonal to §5a)
!purpose: model tier is no longer the only cost lever. Effort (`low|medium|high|xhigh|max`) trades thoroughness
  against token spend WITHIN one model. Lower effort on a current-generation model often beats a prior-generation
  model at high effort, and staying on one model keeps ONE prompt-cache namespace — a model cascade forfeits
  cache reuse across its tiers, so §5a's cost math must be read against §5d, ¬in isolation.

EFFORT-A (max):   correctness > cost — exit-gate disputes, Toulmin debate, plan-lock validation
EFFORT-B (xhigh): default for lead orchestration + adversarial challenge (settings.json `effortLevel`)
EFFORT-C (high):  domain analysis, standard synthesis
EFFORT-D (low):   mechanical checks — gate scoring, retrieval, routine promotion sweeps

!rule: teammates INHERIT the lead's effort level — it is a session-level dial (`/effort`), ¬a per-teammate one.
  To run a cheap round, lower the lead's effort before the spawn; to run an expensive one, raise it first.
!rule: there is no `effort` parameter on the Agent tool. The only per-agent effort control is `effort:` in a
  subagent definition's frontmatter, and that applies to Agent-tool subagents — ¬to named teammates, which
  follow the lead regardless. Sigma's agent defs carry no frontmatter today (see sigma-lead.md), so in
  practice effort is a session-level dial only.
!rule: an effort change mid-conversation invalidates the messages prompt cache — batch effort changes at
  round boundaries, ¬mid-round.
!rule: prefer §5d before §5a when cutting cost. Drop effort first; drop model tier only if effort alone
  misses the budget, and record which lever moved: "MODEL[{agent}]: {tier}({model}) |effort:{level} |reason: {why}"

## prompt-decomposition-protocol v1.0 (26.3.17)

scope: sigma-review ANALYZE operations — executed by lead before agent spawn
modes: ANALYZE — BUILD decomposition → see build-directives.md §7
companion: §2d source provenance, §6 context-contamination-protocol, adversarial-layer v2.0

!purpose: prevent user's hypotheses from entering agent research as assumed facts. Contamination is cheapest to catch at input — by the time DA reviews in r2, prompt claims are already laundered through 3-8 agents' findings. Decompose prompt BEFORE spawn → agents receive claims as testable hypotheses ¬background assumptions
!observed failure mode (26.3.17): user prompt contains implicit claims ("market is underserved", "no major competitors") → agents absorb as context → research confirms via selective evidence → findings echo prompt with research authority → user reads own assumptions back as validated. Undetectable without provenance tracking

### §7a decomposition — lead extracts three categories from user prompt

1→ QUESTIONS: what user wants to learn
  these define research scope — agents answer these
  examples: "what is the competitive landscape?" | "what are adoption trends?" | "what risks exist?"

2→ CLAIMS: what user asserts or assumes (often implicit)
  ANALYZE detection heuristics:
    - statements of fact without citation ("the market is underserved")
    - framing language that presupposes outcome ("given the opportunity")
    - comparative claims without evidence ("better than alternatives")
    - causal assertions ("this will drive adoption")
    - quantitative claims without source ("$500M market")
  these become HYPOTHESES for agents to test — ¬context, ¬constraints, ¬facts

  > BUILD detection heuristics → see build-directives.md §7a

3→ CONSTRAINTS: scope, timeline, market, methodology boundaries
  these narrow the search — agents operate within these
  examples: "US market only" | "2024-2026 timeframe" | "private credit" | "publicly available data"

### §7b user confirmation — structured, scoped, ¬open-ended

!rule: lead presents decomposition to user BEFORE spawning agents
!rule: confirmation format is STRUCTURED — ¬open text, ¬"tell me more"
!purpose: catch misunderstandings (lead misread prompt) without reinjecting bias

format:
```
PROMPT-DECOMPOSITION:

Questions (confirm — are these what you want answered?):
  Q1: {question} — ✓/✗/revise
  Q2: {question} — ✓/✗/revise

Constraints (confirm — are these the right boundaries?):
  C1: {constraint} — ✓/✗/revise
  C2: {constraint} — ✓/✗/revise

Claims extracted (awareness — agents will test these as hypotheses):
  H1: {claim from prompt} → will test
  H2: {claim from prompt} → will test
  ↳ Recategorize only: should any of these be a constraint or question instead?
```

!rules:
  - questions: user confirms scope (✓/✗/revise) — low bias risk
  - constraints: user confirms boundaries (✓/✗/revise) — low bias risk
  - claims: shown for AWARENESS ¬confirmation — user ¬asked "is this true?"
  - user may RECATEGORIZE (move claim→constraint or claim→question) but ¬confirm/deny claims
  - if user volunteers justification for claims → lead notes but does ¬pass to agents
  - !anti-pattern: user says "H2 is definitely true" → lead responds: "noted — agents will still test it. If true, research will confirm independently"

### §7c workspace integration

!rule: decomposition written to workspace ## prompt-decomposition section (see workspace template)
!rule: agents receive prompt-decomposition in spawn context — claims labeled as hypotheses
!rule: agent spawn prompt includes: "Claims H1-HN are user hypotheses extracted from the prompt. Test these — find evidence FOR and AGAINST. Do ¬assume they are true. Tag findings that address claims with |source: and reference the hypothesis number"

### §7d DA prompt audit (extends DA r2 responsibilities)

!rule: DA receives original user prompt + decomposition in r2
!rule: DA checks:
  1→ which findings use language from user prompt (near-verbatim echo)
  2→ which findings confirm prompt claims without independent sourcing ([prompt-claim] without corroboration)
  3→ whether any implicit claims were MISSED in decomposition (lead failed to extract)
  4→ whether research methodology COULD have produced contradictory result — if not, methodology was confirmatory ¬investigative
!rule: DA reports prompt-audit in exit-gate assessment (see DA exit-gate criterion 5)

## workspace-archiving-protocol v1.0 (26.3.17)

scope: all sigma-review operations — lead archives workspace before shutdown
companion: /sigma-audit skill (independent process verification)

!purpose: preserve workspace state for post-review auditing. Workspace is overwritten by next review — archive ensures past reviews remain auditable in fresh context windows via /sigma-audit

### §8a when to archive
!rule: MANDATORY before shutdown for all completed reviews (ANALYZE or BUILD)
!rule: lead copies workspace to archive BEFORE overwriting or clearing

### §8b archive format
!rule: archive path: `~/.claude/teams/sigma-review/shared/archive/{task-slug}-{YYYY-MM-DD}.md`
!rule: archive = exact copy of workspace.md at time of synthesis completion
!rule: lead prepends archive header:
```markdown
# ARCHIVED WORKSPACE — {task title}
archived: {date} | mode: {ANALYZE|BUILD} | rounds: {N} | verdict: {from DA exit-gate}
original: ~/.claude/teams/sigma-review/shared/workspace.md
agents: {list of agents who participated}
directives-version: {version from directives.md header}
audit: run `/sigma-audit {this-file-path}` in a fresh context to verify process compliance
```
!rule: archive includes full workspace content unchanged — ¬summarize, ¬redact

### §8c archive index
!rule: lead maintains `~/.claude/teams/sigma-review/shared/archive/INDEX.md`:
```markdown
# Workspace Archive Index
| date | task | mode | rounds | agents | verdict | path |
|------|------|------|--------|--------|---------|------|
| {date} | {task-slug} | {mode} | {N} | {agent-list} | {DA verdict} | {relative path} |
```
!rule: append new row per archived review

### §8d /sigma-audit integration
!rule: archived workspace is the primary input to /sigma-audit
!rule: /sigma-audit reads archived workspace independently in fresh context — no exposure to review conversation
!rule: /sigma-audit produces verdict (GREEN/YELLOW/RED), flagged findings, remediation plan, calibration patterns
!rule: calibration patterns stored to team patterns (store_team_pattern) for cross-review tracking

### §8e workspace corruption recovery (26.4.23, formalized from R19 Pattern A)

!purpose: formalize R19 exemplary recovery as reusable template. Auditor flagged R19 recovery-log as "exemplary" — Scope Integrity 4/4 earned via transparency, not absence-of-incident. Future corruptions are inevitable (sed -i cross-session + concurrent-write races); preserved pattern keeps response structured rather than improvised.
!observed trigger: R19 #1 `sed -i ''` silent corruption → 4 agent sections lost mid-R1 | also: tool-call failure mid-write, filesystem error, concurrent-write race overwriting anchor.
!cross-ref: this section is the operational complement to IC[7] (security contract on hook ↔ tool-call validation, sed-i BLOCK enforcement). IC[7] establishes the mechanical contract; §8e formalizes the recovery template when the contract holds but external corruption occurs (filesystem, concurrent-write, MCP failure).

!trigger-conditions: workspace.md or scratch/*-workspace.md contains partial content, lost agent sections, phantom scaffolding, or any detectable state divergence from expected post-write outcome.

!lead workflow (7 steps, sequential, ¬skip-ahead):

  §8e-1 PRESERVE corrupted-state:
    cp {workspace} {workspace}.corrupted.{YYYY-MM-DD-HHMM}
    !purpose: corrupted artifact preserved for forensics + audit trail. ¬delete even after recovery.

  §8e-2 EXTRACT preserved-sections (read-only tools ONLY):
    !allowed: Read | cat | awk (without -i) | sed (without -i) | grep
    !forbidden: sed -i | any tool modifying the corrupted file
    !purpose: avoid compounding damage. R19 initial corruption was sed -i; second sed -i during recovery would propagate.

  §8e-3 REBUILD scaffolding from lead-conversation-context:
    admin work: restore ## section headers, ordering, workspace-template structure.
    ¬analytical: lead ¬re-derives agent findings — scaffolding only.
    !purpose: separate admin rebuild (lead role) from analytical restoration (agent role).

  §8e-4 COORDINATE re-paste with strict-Edit-tool + write-window-freeze:
    lead SendMessages each affected agent: "! workspace-corrupted |section:{agent} |→ re-paste your {round} findings via Edit tool ONLY |¬sed-i |workspace write-window freezes until your re-paste ✓"
    agents re-paste via Edit tool (single-writer atomic, OR workspace_write() helper per IC[6]).
    write-window freeze = other agents pause writes until affected re-pastes complete.

  §8e-5 ATTEST restored-section provenance:
    each restored section carries attestation line at section top:
    `<!-- RECOVERY[§8e]: restored {YYYY-MM-DD-HHMM} |verbatim-from-pre-corruption:{true|approximate|partial-reconstruction} |source:{agent-memory|conversation-context|corrupted-artifact-salvage} -->`
    !purpose: audit trail — future /sigma-audit distinguishes restored from original content.

  §8e-6 DOCUMENT recovery in ## recovery-log:
    lead writes to workspace ## recovery-log (new section if absent):
    `RECOVERY[§8e|{YYYY-MM-DD-HHMM}]: trigger:{what-corrupted-it} |lost:{sections-unrecoverable} |preserved:{sections-salvaged} |re-pasted:{sections-agent-restored} |attestation-status:{all-verbatim|some-approximate|partial} |duration:{minutes}`
    !purpose: one-line incident summary for /sigma-audit consumption + cross-session pattern detection.

  §8e-7 TRANSPARENCY — ¬silent-restore:
    !rule: lead MUST report recovery to user in final synthesis.
    !rule: Scope Integrity criterion (§6e) credits transparent recovery (4/4 earnable via §8e compliance) — silent restore = Scope Integrity ≤2/4 (contamination flag).
    audit consequence: /sigma-audit reads ## recovery-log and restoration attestations — absent documentation with detectable content changes = RED verdict.

!cross-references:
  §8a: when to archive — §8e applies DURING review (live corruption) vs §8a's post-review archival. ¬conflated.
  §8d: /sigma-audit reads ## recovery-log + attestations as primary recovery-compliance signal.
  sigma-lead.md ## Recovery section: lead workflow pointer to §8e.
  §6e: Scope Integrity scoring credits transparent recovery.

### §8f post-exit-gate workspace-headers (26.4.29)

!purpose: enforce post-exit-gate phase completion via workspace-header presence. R19 #21 + B 3.14 weakness profile: lead declares chain-closed without writing ## sync (template snapshot) → next review imports stale templates → calibration drift compounds. Header presence is the mechanical signal that the post-exit-gate phase actually ran ¬just-was-claimed.

!when: AFTER DA exit-gate PASS, BEFORE workspace archive (§8a). Order: synthesis → promotion → sync → archive. Each phase writes its workspace header on completion.

!applies-to: ANALYZE mode (sigma-review) | BUILD mode → see build-directives.md §8f (post c3-review chain-closure).

!workspace-header mandate (lead writes after each phase completes):
  ## synthesis-complete: [{date}|{synthesis-agent-id}] — written when synthesis-agent declares ✓
  ## promotion: [{auto-stored:N}|{user-approve:M}|{date}] — written when promotion phase exits (existing; A13 already gates presence)
  ## sync: [{templates-hashed:N}|{drift-detected:Y/N}|{date}] — NEW MANDATE (this directive)
  ## archive-complete: [{archive-path}|{INDEX-row-N}|{date}] — written after §8a copy + §8c index append

!chain-evaluator enforcement:
  ## promotion: A13 (existing) — presence-checked, evidence-required.
  ## sync: A27 (new gate, WARN-first per path β+ ADR[β+]) — presence-checked. Promotion threshold per ADR[10]: ≥3 reviews where ## sync absent + ≤20% false-positive rate (precedent-aligned with A20 §2i, ¬"2+" provisional). audit-calibration-gate.py issues PROMOTE on threshold met → lead updates A27 mode WARN→BLOCK.
  ## synthesis-complete + ## archive-complete: directive-only this cycle (no chain-evaluator gate yet; promotion deferred until A27 path β+ data lands).

!header format (machine-parseable, single-line):
  `## sync: [templates-hashed:{N}|drift-detected:{Y|N}|date:{YYYY-MM-DD}]`
  template-hash baseline: shared/templates/.templates-hash-baseline.json (optional; A25 is silent when absent). drift-detected:Y → triggers re-sync workflow (§8a archive PROCEEDS but flagged for next-session reconciliation).

!recovery / manual-override form:
  `## sync: [templates-hashed:0|skipped|reason:{reason}|date:{YYYY-MM-DD}]`
  audit-trail mandate: skipped form requires reason text; A27 chain-eval accepts the skipped form but logs to calibration-log.md (DC[A27-SKIP]) for post-session review. Skipped without reason → BUILD-CONCERN raised by /sigma-audit.

!recovery / manual-override form (BUILD §8f variant — post-c3 phase chain-closure for compilation):
  `## compilation-complete: [R-{review-id}, manual-override, reason: {reason}]`
  authority: lead-with-user-approval ONLY. ¬lead-only, ¬user-only.
  preconditions (ALL must hold — AND, ¬OR):
    (a) compilation agent spawned per sigma-lead.md:207 Step 7b AND either failed to return
        `## compilation-complete: [R-{review-id}]` header OR returned explicit failure signal
        (compilation-agent error, MCP unrecoverable, wiki-write blocked).
    (b) ≥1 retry attempted (re-spawn or equivalent recovery path) AND retry outcome documented
        in workspace ## review-findings or scratch with timestamp + failure-mode + retry-attempt evidence.
    (c) user approval recorded in conversation; reason field captures user-supplied justification
        (NOT lead self-justification); retry evidence referenced verbatim (timestamp or workspace section).
  enforcement-model: HONOR-SYSTEM. _COMPILATION_COMPLETE_RE in phase-gate.py cannot mechanically
    verify user approval — authority is honor-system reinforced by audit (reason-field text +
    /sigma-audit BUILD-CONCERN on generic reasons). Mechanical enforcement of authority
    (cryptographic approval, separate user-write file, role-based ACL) is OUT-OF-SCOPE this build.
    Closes addressable portion of openai-gpt-5.4 GAP[#5] from C2 XREVIEW; unaddressable portion
    (mechanical enforcement of authority) is documented and accepted as residual.
  audit-trail expectation: A27 chain-eval logs override invocation to calibration-log.md
    (DC[A27-OVERRIDE]) for post-session review. Generic reason text ("skipped", "ran out of time",
    "couldn't finish") fails audit → BUILD-CONCERN raised by /sigma-audit.
  cross-references: sigma-lead.md:207 (operational instruction for lead); CLAUDE.md "Executing
    actions with care" (destructive-operations / shared-state confirmation rail — joint authority
    precedent); §8f line 1284-1286 (ANALYZE-track ## sync recovery form, structurally parallel
    pattern); §8e (workspace corruption recovery, shares attestation pattern); §2p DC[3]
    (premise-audit-results pre-dispatch sibling — header-presence=phase-ran shared with §8f).
  !synthesis-archive-carveout: synthesis-archive writes (path matches `*-synthesis.md` under `shared/archive/`) are EXEMPT from the BLOCK 5 compilation-complete precondition by design — Step 13f→14 dependency order makes gating synthesis on compilation a logical cycle. Predicate: `_is_synthesis_archive_write` @ phase-gate.py (Cond A: basename endswith `-synthesis.md` AND Cond B: any `_ARCHIVE_PATH_MARKERS` substring; both required). Source: ADR[1] of build 2026-05-05-block-5-synthesis-carveout.

!cross-references:
  DC[1]: §8a — ## archive-complete header is the §8a post-write attestation (existing archival rule re-anchored to header).
  DC[2]: §8c — ## archive-complete `INDEX-row-N` value verifies INDEX append occurred (¬just-archive-copy).
  DC[3]: §2p — premise-audit-results header (ANALYZE-mode) is the pre-dispatch sibling of §8f post-exit-gate headers; both use workspace-header presence as the mechanical phase-completion signal. §2p header written BEFORE H[] dispatch; §8f headers written AFTER DA exit-gate PASS. Common pattern: header-presence = phase-ran, ¬just-claimed. Cross-ref BUILD variant: build-directives.md §2p (Step 7a in c1-plan.md between Step 7 and Step 8) — the BUILD pre-dispatch sibling carries the "Step 7a" label; ANALYZE side does NOT (per H7 r2 falsification — structure survives, label dropped to avoid renumber-cascade in sigma-review/SKILL.md).
  DC[4]: §8f BUILD-track variant above — compilation manual-override form. Same recovery-form structure as ## sync ANALYZE-track form (line 1284-1286); authority model is lead-with-user-approval (more restrictive than ## sync's lead-only because compilation skip has durable wiki-state consequence while ## sync skip is calibration-period only). Closes VP[1] (TW peer-verify of IE F[IE-7]) + addressable portion of GAP[#5] (openai gpt-5.4 XREVIEW phase-gate.py BLOCK 5). |src:shared-process-hardening-c3-2026-05-01|
  §6e: Scope Integrity credits header-presence-with-content; absent or empty header = ≤2/4.
  A27 (new): see chain-evaluator.py — WARN-first calibration period, BLOCK on PROMOTE.

## §9 post-review-calibration-protocol (26.3.23)

!purpose: close the feedback loop between user ground truth and agent calibration. Without this, calibration is self-referential — agents grade themselves. User corrections are the missing signal.

skill: /sigma-feedback
two tracks:
  datum(verifiable-factual) → pushback-once(reference-original-source)→user-confirms→accept→update
  concept(structural/interpretive) → mini-review(domain-agent+DA)→same-evidentiary-standards-as-review→accept|reject|synthesize

### §9a classification boundary
datum: specific number|date|name|fact | binary right/wrong | source-checkable
concept: how-something-works|why-something-happens|framework|mechanism | multiple valid framings
!rule: lead classifies, user confirms|overrides
!rule: mixed corrections → split into separate tracks (datums first, then concepts)
!escalation: datum pushback reveals structural implication → reclassify as concept (user confirms)

### §9b datum rigor
!rule: exactly one pushback round — reference original source ¬restate finding
!rule: if lead can verify inline → verify before pushback (skip if verified-correct)
!rule: user confirms → accept immediately ¬second pushback
!rule: cascade check mandatory — scan workspace for references to corrected value

### §9c concept rigor
!rule: user's correction formulated as H[user-correction] — tested ¬assumed
!rule: mini-review: domain-agent(research independently) + DA(steelman original, challenge correction)
!rule: same evidentiary standards as full review: §2d source provenance, §2d+ quality tiers
!rule: rejection requires specific evidence presented to user ¬"the team disagrees"
!rule: user may provide additional evidence → one more round max
!rule: domain-agent + DA disagree → user decides (has domain context agents may lack)
!rule: user-override after 2 rejections → accepted with flag (legitimate — domain context)

### §9d calibration tracking
correction entry: `C[{track}|{date}]: F[{agent}:{finding}] ...` in agent memory
error classes:
  datum: factual-error | source-misread | stale-data | transcription
  concept: framing-error | omission | oversimplification | domain-gap
pattern detection: same agent+error-class ≥3 → SYSTEMIC[agent] | same error-class across agents ≥3 → SYSTEMIC[process]
workspace: corrections appended to archive ## post-review-calibration (DC[] for datum, CC[] for concept)

→ actions:
→ new directive → append with version+date
→ directive revision → update version, note change
