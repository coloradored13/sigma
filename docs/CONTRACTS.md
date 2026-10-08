# Public successor contracts — initial implementation

This is an independent alpha implementation in the existing public Sigma repository,
with distinct package names, MCP registrations, and runtime storage. Public Git
history is retained. No legacy memory, settings, credentials,
or plugin directories are discovered or imported. Repository contents and tests
use synthetic data. The separate legacy dependency repositories are unchanged.

## Trusted host boundary

`sigma_public_core.scope.Scope(tenant_id, project_id, actor_id)` is immutable and
constructed by the host. MCP servers bind it once at startup; tools cannot change
scope. Actor identifies the configured host principal, not a user identity accepted
from model text. A stdio process is the initial deployment boundary. Host filesystem
and network isolation remain necessary: these libraries do not sandbox shell tools,
authenticate remote users, or protect files from another process with the same OS
permissions. A local MCP response may enter a hosted primary model's context.

## Workflow core

`WorkflowStore(path, scope, definition)` manages entities in SQLite. A definition
has an initial state and named transitions with permitted source states, target
state, and an optional pure guard on the actual target entity's data. Define actions
in trusted host code. Create/get/allowed-actions/transition operate within the bound
tenant and project. Unknown and out-of-scope IDs are indistinguishable.

Every transition loads the target, checks expected version, action eligibility,
and guard, changes state, and appends its receipt in ONE transaction. Idempotency
keys are scoped and bind actor, entity, action, expected version, and payload;
reuse for different requests is rejected. Cached discovery never authorizes an
action. The first implementation performs state changes only: arbitrary external
side effects and distributed exactly-once claims are out of scope.

## Memory

`MemoryStore(path, scope)` stores project records in SQLite. It provides add/get/
search/revise/retract/delete with record versions, source IDs, and optional expiry.
No personal or cross-project default, automatic import, repetition-based promotion,
or inference that stored text is true. Concurrent additions survive. Updates use
expected versions. Read/search exclude expired or retracted records by default.
Deletion removes content from the logical store; backups, provider copies and
filesystem forensic erasure are outside that guarantee. Errors do not echo content.

Static MCP tools bind scope in the server, never in model-supplied parameters.

## Verification

The verifier receives a claim and explicitly supplied evidence (ID, quotation/text,
provenance). The library does not read memory, files, environment credentials, or
fetch URLs. The server launcher reads its dedicated token only when external
assessment is explicitly enabled by the host.
Default operation is offline. Deterministic checks may establish quotation presence
but must not claim semantic truth. Optional model assessment is explicitly labeled
as such, requires host-configured provider/model/endpoint policy and bounded timeouts,
and has no automatic provider fallback. A localhost URL is not proof of local inference.

Malformed response, provider error, abstention, and supported/contradicted assessment
are distinct. Evidence IDs must resolve to the supplied evidence. A singleton is not
cross-model consensus. The tool cannot weaken policy, reclassify content as public,
or override provider URLs/models. The host must exclude private data at the input
boundary; free-text redaction is not a reliable confidentiality boundary.

## Sigma controller

The thin workflow records a run, scoped findings with source references, unresolved
blockers, and command receipts. Commands are explicit argv (no implicit shell), run
in an explicitly selected directory, and record exit code and pre/post source digests.
Receipts are invalidated by changed inputs. Full output is not persisted by default.
Completion means checks actually passed and blockers are resolved; budget exhaustion
means incomplete. Evaluation completion and result correctness are distinct.

Initial delivery includes synthetic order-flow, privacy and state tests, an offline
analysis/build example, actual stdio MCP tests, reproducible workspace installation,
distribution builds, and clear limitations. Autonomous model teams, live-provider
quality claims, and publication require additional evidence and configuration.

## Acceptance scenarios

- Viewing shipped A does not prevent approving pending B; viewing pending B never
  authorizes approving shipped A. Guard evaluates the target's value, not a prior query.
- Wrong project/tenant IDs, stale versions, conflicting retries, and concurrent state
  changes cannot mutate another resource or duplicate transitions.
- Concurrent memory writers retain their distinct records; personal/project canaries
  are absent from other scopes and from default verifier requests and error output.
- Malformed provider JSON cannot produce successful coverage; no cloud request occurs
  by default, even when environment credentials exist.
- Failed/unrun checks, unresolved blockers, expired budgets, or changed source cannot
  become a successful build. Interrupted runs can be inspected and resumed.
- Installed distributions and MCP servers work in fresh environments without legacy
  files; all public examples and package artifacts contain synthetic data only.
