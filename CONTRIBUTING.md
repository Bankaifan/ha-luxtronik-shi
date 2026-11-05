# Contributing

Read [CLAUDE.md](CLAUDE.md) first: it holds the working rules (entity contract, branches, versioning, language).

## Publishing a beta

To publish a beta, bump `version` in `custom_components/luxtronik_shi/manifest.json` to `X.Y.Z-beta.N`
(for example `0.8.0-beta.1`), add a `## [X.Y.Z-beta.N] – YYYY-MM-DD` section to `CHANGELOG.md` and open a PR.
On merge, the release workflow tags `vX.Y.Z-beta.N` and publishes a GitHub pre-release. The final release later
uses the plain `X.Y.Z` version and its own CHANGELOG section.
