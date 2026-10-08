# Security and privacy boundaries

This alpha is a fresh implementation, not a formal clean-room provenance claim or
an assurance that every failure mode has been tested. Report a suspected vulnerability
privately to the repository maintainer using GitHub private vulnerability reporting
when enabled. Until a private reporting route is documented, use the maintainer's
existing private channel. Do not post credentials, real memories, or private traces.

## Enforced in the component APIs

- Workflow state/version/guard checks use the actual target in one SQLite transaction.
- Scope is bound by host configuration; a tool argument cannot change it.
- Existing records from other scopes are indistinguishable from unavailable records.
- New database files use owner-only permissions. Hosts must secure existing files,
  parent directories, backups and access by other processes.
- Memory has no automatic personal/global import or truth promotion by repetition.
- Expired/retracted data is omitted from active retrieval; mutation results do not
  recover hidden plaintext. Deletion clears logical content and references.
- Verification is offline by default, and model input cannot select a new endpoint,
  model, token, or export policy. Typed results distinguish malformed/error/abstention
  from a model assessment. No result is called cross-model consensus.
- MCP validation responses and SDK diagnostic logs are sanitized. Raw error payloads
  and provider replies are not reflected through these adapters.
- Unrun/failed/stale checks and unresolved blockers cannot satisfy completion.

## Host responsibilities and limits

Scope is a data partition, not authentication. The initial servers use local stdio;
remote multi-user authentication and authorization are not implemented. Use trusted
configuration and separate process identities/databases where stronger isolation is
needed. Filesystem symlink races or malicious same-identity processes require host
filesystem controls; library path checks are not a substitute.

The components do not protect their databases, policies or receipts from an agent
with unrestricted shell/file access. They do not sandbox executed commands, hide
environment variables from child processes, or enforce global network egress. Use
restricted workers with no private filesystem mounts, minimal environment bindings,
and host-managed egress rules. Process-group cleanup handles ordinary descendants;
detached descendants and abrupt controller termination need host supervision.

Personal data can leave through the primary hosted model as soon as it receives an
MCP response. Verification policy only controls this verifier's extra provider call.
Never enable public export for a project containing personal data. Classification
is not inferred from text, and redaction is not a complete privacy guarantee.

Stored evidence, memory text and source URLs are untrusted data. They do not grant
permission, configure tools, or authorize publishing. The verifier never fetches a
source URL. Host-configured HTTPS endpoints may themselves relay traffic; strong
locality guarantees require deployment controls. Prompts cannot establish that
source text is free of prompt injection.

Source receipts hash regular files, directory structure, and executable bits,
including untracked files. `.git`, `.venv`, `__pycache__`, `.pytest_cache`, and
`.ruff_cache` are excluded. The selected source must have no symlinks/special files.
These receipts do not attest the OS, installed toolchain, dependencies outside the
tree, external services, nondeterminism, or tamper resistance. A transient mutation
reverted between snapshots is outside the guarantee. Lockfiles aid reproducibility;
controlled build workers remain necessary for stronger claims.

Memory deletion is logical; WAL pages, backups and external provider copies need
separate retention/erasure handling. Finding creation writes memory before its run
link, compensates ordinary failures, and can leave an unlinked record after abrupt
process death. It cannot falsely complete the run, but garbage collection and a
fully atomic multi-component write API are future work. Receipt recovery requires
the operator to confirm the old executor has stopped.

## Publication checks

Only new source, documentation and synthetic fixtures enter this rebuild. The
existing public repository history remains; replacing files does not erase earlier
commits. Do not import private Git history, runtime stores, personal settings,
transcripts or archives.
Check actual wheels, sdists, release archives and CI logs, not only the working tree.
Secret-pattern scans supplement manual review and synthetic-canary tests; they do not
prove arbitrary text contains no personal information. Publication remains a separate
step after the maintainer contact and privacy review are established.
