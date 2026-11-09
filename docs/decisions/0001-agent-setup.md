# 0001 Agent setup

Status: accepted (Daniel, 2026-11-09), ported from Bankaifan/agent-template. Not yet verified end to end.

## Decision
- Agents run in GitHub Actions (`anthropics/claude-code-action`) on the Claude subscription
  (`CLAUDE_CODE_OAUTH_TOKEN`); two GitHub Apps (author pushes and opens PRs, approver reviews); roles in `.agents/roles/`.
- Roles: orchestrator (slips, off until `ORCHESTRATOR_ENABLED=true`), developer, reviewer; scout, rule keeper and
  weekly summary are scheduled; Dependabot patch/minor PRs are merged without a model.
- The existing *Validate* workflow stays the only CI. Agents react to `workflow_run` of *Validate*: green means the whole
  run (hassfest, HACS, version, tests, workflow lint) succeeded. `Validate` runs on pull requests, on `main` and
  on `workflow_dispatch` (fallback for bot-pushed heads), not on every branch push, so each head has one run.
- `main` ruleset: PR, 1 approval, code owners, the *Validate* jobs as required checks, rebase merge only, linear history.
  `release.yml` is unchanged in behaviour (reads the CHANGELOG on `main` after *Validate* passed on a push).
- Rules: AGENTS.md is the single source (CLAUDE.md imports it). Anything a script can check lives in CI (`make check`).
- Changed against the old CLAUDE.md: "stability before features" removed; read-only checks on the real installation
  allowed (writes need Daniel); rebase/force-push allowed on own agent branches; rebase merges instead of squash;
  commits by Daniel without a `Co-authored-by` trailer; firmware analysis added as a register source.

## Consequences
- Fix rounds are capped at 2 by labels; then `needs-human`.
- Paths under code owners need Daniel, so agents cannot change workflows, rules or the version check alone.
