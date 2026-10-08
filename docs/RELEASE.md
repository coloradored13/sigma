# Alpha release gates and remaining work

The local deliverable is an independent source tree with four buildable Python
distributions, a plugin skeleton, synthetic examples, and acceptance tests. The
rebuild targets the existing public `coloradored13/sigma` repository; package names
are not reserved. No automatic publication workflow or provider credential is included.

Before a public alpha:

1. Confirm package identities, maintainer contact, and private vulnerability-reporting
   route. Review the existing public history and the compatibility changes in
   `REBUILD.md` before replacing the existing default branch.
2. Run the complete test suite, Ruff, actual stdio MCP tests, the offline example,
   wheel/sdist build and artifact scan, and a fresh non-editable wheel installation.
3. Confirm synthetic-only source/history/artifacts/logs. Use an isolated workspace
   with no private mounts to validate the deployment configuration.
4. Run the CI Python matrix on GitHub; local validation of one interpreter is not
   evidence for the entire matrix. Verify installer and client behavior in the
   selected Claude Code or other MCP client with separate registrations.
5. Publish explicit alpha limitations and a compatible distribution manifest.

Before claiming a complete Sigma replacement:

- Implement and test general workflow MCP resource discovery and link navigation.
  The HATEOAS successor currently supplies a Python state/transition core; only
  memory and verification have MCP servers in this initial delivery.
- Add a real model orchestrator with bounded task routing, independently briefed
  review, persistent evidence retrieval, versioned plan amendments, and adequate
  human decision points. The initial client skill is guidance, not that orchestrator.
- Validate optional live-provider interoperability with synthetic public inputs;
  transport mocks do not establish live availability or reasoning performance.
- Introduce transactional finding/memory links, schema migration policy, definition
  identity/versioning, stronger worker isolation and crash supervision, and tested
  retention/export workflows as required by the deployment.
- Run held-out outcome evaluations and compare the simpler default to independent
  ensembles and adversarial modes. Report cost, latency, regressions and uncertainty.

No private data import, automatic migration, remote multi-user authentication, or
external side-effect execution is promised by this alpha. Each requires a separate
threat model and acceptance criteria before it is introduced.
