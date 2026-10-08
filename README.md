# Sigma — public rebuild (alpha)

An independent alpha successor to Sigma, built around resource-bound workflows,
project-scoped memory, explicit verification policy, and durable execution receipts.
The public components have separate package names, entry points, and runtime stores.
They do not discover or import an existing Sigma installation or personal memory.

This rebuild lives in the existing `coloradored13/sigma` public repository. It keeps
that repository's history while replacing its implementation. The new package and
MCP names stay distinct from private installations. See [REBUILD.md](docs/REBUILD.md)
for compatibility, review, and recovery details.

This initial release is a working foundation and thin end-to-end workflow. It does
not yet implement an autonomous team of model agents or demonstrate superior
analysis/build outcomes. Analysis completion means evidence was recorded; quotation
presence does not establish factual truth. Build completion means the declared
commands passed against the recorded source inputs, not that all relevant behavior
was tested.

## Components

| Directory | Distribution | Purpose |
|---|---|---|
| `packages/workflow-core` | `sigma-public-core` | Target-bound SQLite state transitions and retry receipts |
| `packages/memory-mcp` | `sigma-public-memory` | Explicit project memory and static stdio MCP tools |
| `packages/verification-mcp` | `sigma-public-verify` | Quotation checks and optional policy-controlled model assessments |
| `packages/sigma` | `sigma-public` | Durable analysis/build runs, blockers, and execution receipts |

All four are independently packaged. `uv.lock` pins the tested workspace dependency
set. Package names are provisional and have not been reserved or published to PyPI.
The supported development platform for this alpha is Linux with Python 3.11+ and uv.

## Run locally

From the repository root:

```sh
uv --version # CI pins 0.12.19
uv sync --frozen --all-packages
uv run --frozen --all-packages pytest -q
uv run --frozen --all-packages python examples/offline_demo.py
```

The demo uses a temporary synthetic project and no model providers. It exercises
valid lateral order actions, rejects invalid actions on another order, records an
analysis with evidence, and executes a behavioral build check. Its temporary stores
are removed on exit.

If the host's default uv cache is read-only, select a writable location using
`UV_CACHE_DIR`. No tool activation modifies shell profiles or personal settings.

## Run a build check

Choose an explicit database outside the project directory. The following commands
use a new public-only store; replace the workspace with the intended public project.
Activate the workspace environment first (`. .venv/bin/activate`), or prefix each
command with `uv run --frozen --all-packages` from this repository root:

```sh
sigma-public --db /tmp/sigma-public-example.sqlite --tenant demo --project sample --actor operator \
  start --mode build --workspace /path/to/public/project --require tests

# Use the returned id for RUN_ID; keep all scope flags the same.
sigma-public --db /tmp/sigma-public-example.sqlite --tenant demo --project sample --actor operator \
  check RUN_ID tests -- python -m pytest -q

sigma-public --db /tmp/sigma-public-example.sqlite --tenant demo --project sample --actor operator \
  finish RUN_ID
```

Commands are explicit argv with no implicit shell. They execute with the host's
permissions and are **not sandboxed by this library**. Select authorized commands
and use a restricted worker when evaluating untrusted repositories. A zero exit code
is only meaningful when the command tests intended behavior; declare appropriate
checks instead of substituting a trivial command.

Missing checks and unresolved blockers keep a run open and incomplete. `finish
RUN_ID --stop` closes it as incomplete; exhausted check budgets never become a pass.
Inspection after a source change marks old completion stale. A lost executor leaves
an unfinished receipt; stop/reap that executor before using `abandon-check RUN_ID
CHECK_ID --executor-stopped`, then rerun the check within its original budget.
This is explicit operator-assisted recovery, not automatic distributed recovery.

## Record an analysis

With the same activated environment and scope arguments, this synthetic example
records a claim, its explicit source text, an exact quote, and limitations:

```sh
sigma-public --db /tmp/sigma-public-example.sqlite --tenant demo --project sample --actor operator \
  start --mode analysis --workspace /path/to/public/project

sigma-public --db /tmp/sigma-public-example.sqlite --tenant demo --project sample --actor operator \
  finding RUN_ID --claim 'The sample returns 42.' --source-id synthetic-manual \
  --source synthetic://manual --evidence 'The sample returns 42.' \
  --quote 'returns 42' --limitations 'Synthetic illustration; no independent truth check.'

sigma-public --db /tmp/sigma-public-example.sqlite --tenant demo --project sample --actor operator \
  finish RUN_ID
```

The result explicitly reports `evidence_recorded_not_truth_verified`. CLI arguments
may appear in shell history or process listings; use only public inputs here. Use
the Python API for structured host integration. This does not change the privacy
limits of storage or the host itself.

## MCP servers

Configure these as separate stdio servers in the chosen client. Names and storage
must remain separate from legacy Sigma registrations. For an MCP client, set its
command to the absolute `.venv/bin/sigma-public-memory` or
`.venv/bin/sigma-public-verify` path and pass the arguments below separately;
clients do not automatically activate this repository's environment:

```sh
sigma-public-memory --db /path/to/public-runtime/memory.sqlite \
  --tenant public --project example --actor operator

sigma-public-verify
```

Memory scope is fixed at startup. Tools do not accept a replacement tenant, project,
database path, or identity. Verification is offline by default, even when ordinary
provider credentials exist. `check_quote` establishes exact quotation presence;
`assess_claim` returns `offline` until explicitly enabled.

External assessment requires the operator to supply `--allow-external --provider
NAME --model MODEL --endpoint https://HOST/v1/chat/completions --export-classification
public` and set the dedicated `SIGMA_PUBLIC_VERIFY_TOKEN` securely in the server's
environment. No other credential variable is discovered. The endpoint is the full
OpenAI-compatible chat-completions URL. HTTPS verification remains enabled;
redirects, automatic provider fallback, ambient proxy discovery, and model-supplied
policy overrides are disabled. Only public, explicitly selected evidence should
reach this server. The public classification is a host decision, not a data-loss
prevention classifier. Live provider compatibility and reasoning quality have not
been validated in this alpha.

## Privacy and guarantees

Read [the security and privacy boundaries](SECURITY.md) before using real data.
Separate source repositories do not isolate processes: the primary model or a shell
can still access personal files if the host permits it. Use a distinct restricted
workspace/process identity with no private mounts. A local MCP server does not make
the primary model local, and a localhost inference endpoint may forward to a cloud.

The public repo, tests, and examples contain synthetic material. Configure explicit
runtime stores outside the checkout; the controller enforces this for its selected
project, while standalone memory/core libraries rely on host configuration.
Output and command arguments are not retained
in command receipts; only executable basename, command/output digests, timestamps,
exit code, source digests, and fixed status codes are stored. Explicitly supplied
findings and evidence are retained in the scoped runtime database.

The workflow contracts and limits are in [CONTRACTS.md](docs/CONTRACTS.md), the
release gates in [RELEASE.md](docs/RELEASE.md), and the research plan in
[EVALUATION.md](docs/EVALUATION.md). Observed checks and untested areas are recorded
in [VALIDATION.md](docs/VALIDATION.md). An optional client skill is under
`plugins/sigma-public`; it guides this thin workflow and does not enforce permissions.

## Build distributions

```sh
uv build --all-packages --out-dir dist
uv run --frozen --all-packages python tools/check_distributions.py dist
uv run --frozen --all-packages python tools/smoke_wheels.py dist
```

Build and install the complete set of four wheels together until distributions
are published. `release-manifest.json` records their intended compatible versions.
The release workflow contains no package or GitHub publication credentials.

Apache-2.0. See [CONTRIBUTING.md](CONTRIBUTING.md) for development and review rules.
