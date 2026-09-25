# ΣComm Protocol Specification

**A compressed notation system for AI agent working memory and inter-agent communication.**

## Origin

ΣComm began as a working memory system for a single Claude instance. Claude's persistent memory is ~2,000 lines across ~10 files — every line loaded into context costs tokens. Compressed notation (pipe-separated fields, checksums, anti-memories) was developed to pack maximum signal into that limited space, giving a single Claude instance something resembling persistent working memory rather than just passive file reads.

When agent teams needed efficient communication, the same notation was already battle-tested. ΣComm is the inter-agent application of this system.

**Two applications of one notation:**
1. **Working memory** — sigma-mem's memory files use compressed notation to maximize the value of every line in context
2. **Agent communication** — ΣComm applies the same notation to inbox messages, workspace entries, and peer-to-peer messaging

## Message Format

```
[STATUS] BODY |¬ ruled-out |→ actions |#count
```

### Status Codes

| Symbol | Meaning |
|--------|---------|
| ✓ | Done |
| ◌ | In progress |
| ! | Blocked |
| ? | Need input |
| ✗ | Failed |
| ↻ | Retry |

### Body Notation

| Symbol | Meaning |
|--------|---------|
| `\|` | Section separator |
| `,` | Item separator |
| `>` | Preference / should-be |
| `→` | Leads to / next action |
| `+` | And |
| `!` | Critical |

### Required Sections

Every ΣComm message MUST include:

1. **¬ (anti-messages)** — what was NOT found, NOT the issue, NOT true. This prevents assumption propagation — the most common failure mode in multi-agent systems is one agent assuming something another agent didn't say. Forcing senders to declare what they ruled out closes this gap.

2. **→ (action advertisements)** — what the sender CAN do next, given current state. This is HATEOAS applied to communication: each message declares available actions based on the sender's current context. The receiver doesn't have to guess what the sender is capable of.

3. **#N (checksum)** — item count so the receiver can verify they decoded correctly. If the receiver counts a different number of items than the sender declared, the message was misunderstood.

## Why ¬ (Anti-Messages) Matter

In prose communication, absence is invisible. If an agent reviews three modules and finds issues in two, the reader has no way to know whether the third module was reviewed and found clean, or simply not reviewed.

Anti-messages make absence explicit:

```
Prose (ambiguous):
"Found issues in auth and logging modules."
— Was networking reviewed? Unknown.

ΣComm (unambiguous):
✓ security-review: auth-jwt-expiry(!), logging-no-redaction
  |¬ networking, session-mgmt |→ fix-jwt, fix-logging |#2
— Networking was explicitly reviewed and cleared.
```

This is the same principle as anti-memories (¬) in sigma-mem's persistent memory: explicitly recording what is NOT true prevents future false assumptions.

## Token Efficiency

```
Prose (35+ tokens):
"I reviewed the auth module and found 3 issues: JWT expiry not checked,
MD5 passwords, no rate limiting. Session management and CORS look fine."

ΣComm (~25 tokens):
✓ auth-review: jwt-expiry-unchecked(!), pwd-md5>bcrypt, no-rate-limit
  |¬ session-mgmt, cors |→ fix-jwt(small), fix-hash(needs-migration) |#3
```

The ΣComm version is ~30% fewer tokens while carrying MORE information (what was ruled out, what actions are available, verifiable item count).

## Inbox Format

Agents communicate via markdown inbox files.

```markdown
# inbox — {agent-name}

## processed
✓ ux-researcher(26.3.7): _state-feedback, agreed-on-logging |#1

## unread
## from:tech-architect ts:26.3.7
◌ registry-coupling: _last_state accessed 5x |→ need-your-take-on-DX-impact |#1

---
```

### Inbox Processing Rules
1. Read everything under `## unread`
2. Process each message
3. Compress processed messages into ΣComm summaries under `## processed`
4. Clear `## unread` section
5. Anything worth keeping long-term goes to personal memory or shared workspace

### Writing to a Peer's Inbox
Append under their `## unread` section:
```
## from:{your-name} ts:{date}
{ΣComm message}

---
```

## Workspace Format

Shared workspace for collaborative tasks:

```markdown
# workspace — {task description}
## status: active

## task
{description of current task}

## findings
### {agent-name}
{agent writes findings here in ΣComm}

## convergence
{agent-name}: ✓ {summary} |→ {next-available}
{agent-name}: ◌ {summary} |→ {what-remains}

## open-questions
{plain language — things needing user input}
```

### Workspace Rules
1. Write to YOUR section under findings — don't edit peers' sections
2. Declare your status in convergence when done (✓) or still working (◌)
3. Write user-facing questions to open-questions in plain language
4. Read peers' findings to inform your own assessment

## Working Memory Format

In sigma-mem memory files, the same notation is used for persistent storage:

```
# Compressed identity block
U[backend dev, team of 4, proj@12-01, remote, learn>ship, ai curious|6|26.3]

# Anti-memory block
¬[developer(leader learning to build) | teaching(coach mode≠teaching)]

# Confirmed belief
C[detects perf, honest>polish, probes|3|26.3]

# Tentative belief
C~[uncert>conf wrong | depth match|2|26.3]

# Research entry
R[OWASP agentic top-10: tool-poisoning, rag-poisoning, agent-hijacking |src: owasp.org/agentic |refreshed: 26.3.7 |next: 26.4]

# Promoted learning (distilled from project review → global memory)
P[state-machines>5-states need startup-validation |src:mobile-app |promoted:26.3.8 |class:principle]
P[magic-string-keys→silent-failures |src:mobile-app+memory-server |promoted:26.3.8 |class:anti-pattern]
```

## Examples

**Agent-to-agent (review finding):**
```
✓ auth-review: jwt-expiry-no-validate(!), pwd-md5>bcrypt, no-rate-limit-login
  |¬ session-mgmt, cors
  |→ fix-jwt(small), fix-hash(needs-db-migration), add-rate-limit(small) |#3
```

**Blocked:**
```
! test-suite: 14/20 pass, 6 fail in auth-module
  |¬ api-tests, db-tests |→ need-auth-fix-first |? skip auth tests? |#6-fail
```

**Confirming peer's finding:**
```
✓ validate-integration: serve()+Runner.__init__ both call validate()
  |your review-5 Resource-validate-parity concern fully addressed
  |→ check if validate() error messages are actionable enough |#2
```

**Correcting peer's finding:**
```
◌ dist/-not-empty: you noted "dist/ directory empty" but it has stale 0.1.0 wheel.
  Needs rm -rf dist/ before fresh build. Minor correction to your prereq status.
  |¬ not a new blocker, just a factual correction |→ update prereq note |#1
```

**Convergence declaration:**
```
tech-architect: ✓ review-complete |resolved: 4/6, new: 3, grades: arch(A) security(A)
  |→ ready-for-synthesis
```

## Design Principles

1. **Every line earns its place** — context window space is finite, optimize for signal density
2. **Absence must be explicit** — if you checked something and it's fine, say so with ¬
3. **State drives options** — advertise what you can do next based on current state (→)
4. **Trust but verify** — checksums (#N) catch decode errors before they propagate
5. **Human-auditable** — all storage is markdown files, no binary formats or databases
