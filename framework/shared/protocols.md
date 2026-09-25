# sigma-review protocols

## structured debate protocol v2.0 (26.3.11)

### trigger conditions (ALL required)
1→ DA has identified disagreement between 2+ agents on specific claim or decision
2→ disagreement is MATERIAL — resolving one way vs other changes deliverable:

  ANALYZE thresholds:
  - investment/portfolio: >3% allocation change or >5pp probability revision
  - research: changes core conclusion or primary recommendation
  - product/strategy: changes ship/no-ship or top-3 priority ordering

  BUILD thresholds:
  - architecture: changes data model, API contract, or service boundary
  - scope: adds or removes feature from current phase
  - pattern: changes how 3+ files structured (DRY strategy, error handling, state management)
  - dependency: adds or removes external dependency
  - test strategy: changes what's tested or how

3→ disagreement CANNOT be resolved by one side having better data (share data, ¬debate)
4→ both positions defensible with evidence (ANALYZE) or technical reasoning (BUILD)

### do NOT trigger for
- sizing within margin (2% vs 3%, or 2hrs vs 4hrs)
- naming/style (use project conventions)
- resolved by domain expert weight
- one side clearly has better evidence
- BUILD: implementation details ¬affecting interfaces (let builder decide)

### debate structure

participants:
  ADVOCATE-A: agent defending position A (domain expert preferred)
  ADVOCATE-B: agent defending position B (or DA if challenging consensus)
  JUDGE: most relevant domain expert NOT already advocating
    if both domain experts are advocates → lead serves as judge
    judge scores each round, declares outcome

format: 3 rounds, structured

round-1 (opening):
  ADVOCATE-A: state position + top 3 evidence points + what would change your mind
  ADVOCATE-B: state position + top 3 evidence points + what would change your mind
  JUDGE: score round (stronger initial case, 1-10 each)

round-2 (rebuttal):
  ADVOCATE-A: directly address B's strongest point + new evidence if available
  ADVOCATE-B: directly address A's strongest point + new evidence if available
  JUDGE: score round + identify effectively countered arguments

  BUILD-mode addition:
    either advocate may produce PROTOTYPE or CODE SKETCH (pseudocode, interface definition,
    minimal implementation) demonstrating approach. Concrete > theoretical.
    "Show me the code" resolves architectural debates faster than "trust me it's simpler."

round-3 (synthesis):
  ADVOCATE-A: final position — concede|defend|compromise. specific about what changed
  ADVOCATE-B: final position — concede|defend|compromise. specific about what changed
  JUDGE: final ruling with reasoning:
    - which side's strongest argument won?
    - what should final deliverable reflect?
    - what monitoring triggers track unresolved uncertainty?

    BUILD-mode addition:
    - does loser's concern become a TEST CASE?
      (example: "go with approach A, add test that catches approach B's failure mode")
    - is this reversible? reversal trigger?
      (example: "if >3 edge cases next phase, revisit this decision")

### rules
- advocates MUST state "what would change my mind" in round-1 (prevents entrenchment)
- new evidence allowed in round-2 (incentivizes deeper research/prototyping)
- round-3 requires EXPLICIT concede|defend|compromise (¬vague "I see both sides")
- judge ruling → decisions.md as debate-resolved finding
- dissenting position recorded alongside ruling (divergence is information)
- BUILD-mode: losing position's concern becomes test case or monitoring trigger when applicable

### lead protocol for debate

after r2 convergence (ANALYZE) or plan challenge (BUILD), if DA flags material disagreement:
1→ verify trigger conditions (material + defensible + ¬data-gap)
2→ assign ADVOCATE-A, ADVOCATE-B, JUDGE
3→ deliver debate prompt with:
  - contested claim/decision (specific, falsifiable)
  - each side's current position (from workspace)
  - materiality threshold (what changes in deliverable)
4→ run 3 rounds per protocol
5→ judge ruling → decisions.md: "debate:[topic] |ruling:[position] |judge:[name] |score:[A-score,B-score] |by:debate-protocol"
6→ losing position → decisions.md: "debate:[topic] |dissent:[position] |by:[advocate] |note:recorded-for-monitoring"
7→ BUILD-mode: losing concern → test case or reversal trigger if applicable

!budget: max 2 debates per review/build cycle (prioritize by materiality)
!scope: debate replaces synthesis for contested claims ONLY — uncontested findings synthesized normally

→ actions:
→ debate record → save to shared/debates/{date}_{topic}.md
→ protocol revision → update version, note change
