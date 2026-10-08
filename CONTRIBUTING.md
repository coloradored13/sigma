# Contributing

Use Linux, Python 3.11+, and the checked-in uv lockfile. Run `uv sync --frozen
--all-packages`, `uv run --frozen --all-packages ruff check .`, and
`uv run --frozen --all-packages pytest -q` from the repository root.

Keep the existing private/legacy installations separate. Never import personal
memory into a test, benchmark, example, issue, snapshot, or recorded provider reply.
Use distinctly synthetic canaries and temporary stores. Tests of public defaults
must perform no external model calls. Hostile-content tests must inspect logs and
errors as well as final results.

Change the contract and its acceptance tests before changing a shared interface.
Reproduce defects, make small patches, and have another reviewer challenge the
patch and tests. Exercise actual stdio MCP behavior when changing server boundaries.
Run the full four-component suite for compatibility changes. Declare remaining
limits honestly; a passing format or model agreement is not proof of truth.

The MCP SDK is pinned to the version tested by the privacy adapters. Updating that
pin requires review of SDK validation and logging paths, plus malformed-protocol,
unknown-tool, transport, and synthetic-canary regressions over actual stdio.

Do not disable TLS/checksum verification, assertions, or failed checks to make a
release green. Do not publish packages, activate cloud providers, or install the
plugin into a personal client as part of routine tests. Independent package releases
must preserve the tested compatible set or update `release-manifest.json` together.
