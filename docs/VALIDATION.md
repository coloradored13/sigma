# Initial alpha validation — 2026-10-08

Validated locally on Linux, CPython 3.12.14, uv 0.12.19, and the checked-in lockfile
(MCP SDK 1.30.0). This records engineering acceptance, not superior analysis/build
outcomes or an assurance that every privacy failure has been excluded.

| Check | Observed result |
|---|---|
| Frozen workspace installation | Passed |
| Complete pytest suite | 189 passed; no skipped or expected-failure tests |
| Ruff | Passed |
| Actual stdio MCP behavior | Covered by the passing suite, including malformed requests and errors |
| Offline integration example | Valid lateral order action, invalid target/guard rejection, analysis and build completion |
| Distributions | Four wheels and four sdists built successfully |
| Release allowlist scan | All eight passed; metadata, paths, license, source equality and wheel records checked |
| Fresh wheel installation | Hash-checked locked dependencies; four non-editable wheels; dependency check passed |
| Installed behavior | Imports from the fresh environment, three console entry points, offline integration, CLI analysis/build flows passed |

Independent review and regression tests addressed target confusion, concurrent
writes, stale or failed completion, interrupted check recovery, expired-memory
mutation responses, SDK log reflection, and unsupported prompt/resource errors.
Synthetic hostile fixtures are used throughout. Tests of verifier transport use
mocks; no live model provider was called.

Source packaging uses explicit allowlists and a reviewed package-local `.gitignore`
because Hatch includes that file automatically. The scanner rejects unexpected
contents and metadata; it is not a general personal-data detector. The rebuild was
initially validated separately, then moved onto a branch in the existing public
Sigma repository at the maintainer's request. Existing public history is retained;
runtime stores, personal settings and credentials were not imported. The three
separate legacy dependency repositories remain unchanged.

Not validated: the GitHub Python 3.11/3.12/3.13 CI matrix, real Claude Code plugin
installation, live providers, remote multi-user authorization, autonomous model
orchestration, outcome benchmarks, or restoration in a newly published cloud task.
General workflow MCP discovery/navigation remains future work.

The rebuild branch is `rebuild/public-alpha` in `coloradored13/sigma`, based on
`7f3c3e4ee9a45744fdcb20ea6c7f98ec46843a42`. Native Git access to this existing
repository works; the GitHub API route separately returns `Forbidden`. An API
denial does not imply that native Git is unavailable. See `REBUILD.md` for the
limited existing-history review and the distinction between this branch and a
complete replacement ready for the default branch.

Cloud setup/start instructions target the rebuilt checkout. Saving their draft
does not publish a snapshot or prove future restoration.
See `RELEASE.md` for the remaining alpha and complete-successor gates.
