# Rebuilding the existing public Sigma repository

The maintainer selected `coloradored13/sigma` as the public home for this rebuild.
A new GitHub repository is unnecessary. The four public Python distributions live
in this monorepo; existing private installations and the three separate legacy
dependency repositories are not migrated automatically.

The rebuild is prepared on `rebuild/public-alpha`, based on public commit
`7f3c3e4ee9a45744fdcb20ea6c7f98ec46843a42` (the v0.3.1 implementation). It replaces
tracked implementation files while preserving public Git history and the existing
NOTICE. A verified Git bundle of that complete base history was saved outside the
checkout during preparation. Neither a history rewrite nor a force push is needed.

## Compatibility

This alpha is not a drop-in replacement for the existing Claude Code plugin.
The old `/sigma-review`, `/sigma-build`, hooks, and agent-team orchestration are
not implemented by the new thin controller. The marketplace points to the distinctly
named `sigma-public` guidance plugin, whose installation in a real client remains
untested. Python packages and MCP registrations retain their new names so private
registrations are not silently reused.

The demonstrated workflow records evidence, enforces target-specific transitions,
and executes declared build checks. General workflow MCP discovery/navigation,
autonomous model orchestration, and outcome-quality evaluations remain on the
release roadmap. Review those gaps before promoting this branch to the default
branch. Users requiring the previous plugin should retain their existing version
until an appropriate migration is available.

## Existing history and privacy

The base checkout was not shallow. Its four reachable commits contained 102 unique
file blobs (about 1.3 MB); remote main matched the inspected base. A limited pattern
scan found no private-key/provider-token patterns or tracked credential/database
filenames. The only flagged absolute home paths were synthetic `/home/dev` test
fixtures, reviewed in context.

That scan is not a general personal-data audit and does not cover unavailable remote
refs, issue attachments, releases, forks, caches, or arbitrary sensitive prose.
Retaining this public history does not import personal runtime memory, but replacing
the current files also cannot erase anything previously published. If sensitive
historical material is discovered, assess and remediate it separately.
