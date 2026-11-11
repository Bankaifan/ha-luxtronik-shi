# Handover
<!-- Overwrite, do not append. History lives in git and CHANGELOG. Max 60 lines. -->

## Goal
Keep the integration stable for production use and let the agent system (from Bankaifan/agent-template) carry
routine work: issue -> dev -> review -> merge, with Daniel deciding only what needs a human.

## Current state
- Released version: 0.18.0 (2026-11-09). `[Unreleased]` holds the entity ID rename (#101/#102, with an
  `### Action required` entry), the 0.1 K step for writable temperatures (#83), the HACS install docs (#69) and agent/CI
  changes. Accepted into the HACS default catalog (stated by Daniel).
- Agent system is live: agent-system PR (#70) merged, orchestrator and scout run on schedule, status issue #89 is
  updated by the status run. Template sync with `Bankaifan/agent-template` is connected (`.agents/template.json`).
- Entity ID rename done (#101, PR #102, follow-up PR #106): generated IDs of `heating_available` and
  `hot_water_available` are migrated at setup; user-chosen IDs are kept. Decision recorded in
  `docs/decisions/0003-entity-id-rename.md`.
- pymodbus floor (#76, PR #79): manifest and CI use pymodbus 3.9 (`>=3.9.0`); `tests-min-ha` runs on 3.9.2. Closed.
- hassfest and HACS actions are pinned to commit SHAs (#77, PR #80); `tests/test_workflow_pins.py` guards it. Closed.
- Orchestrator runs no longer end silently: CI tools are installed first, plain `git commit` is required (#104, PR #107).

- Issue #118 (orchestrator runs ending silently after denied tool calls) is merged (commit 6b95a3d): never delete files,
  body files go to git-ignored `.agent-out`.
- 2026-11-11: slip written for #129 (README/CHANGELOG note: Novelan-SICV 12.2H3 reported working), `agent:dev` set.
  No open PRs; no red run in the last 10 runs (two status runs were still in progress). #130 (prio:2, `idea`,
  failure_class digit handling) is not approved and not startable.

## Open
- #129: PR not opened yet; open.
- ADR 0003 (entity ID rename): Daniel's approval is still marked open in the file.
- Next release not cut yet; it carries the entity ID rename, so the release notes must lead with *Action required*.
- Agent setup not verified for everything: rule keeper and weekly summary have never run (status issue #89).
- Dependabot PRs: the `hacs` job needs `pull-requests: write`, which Dependabot runs lack; if it fails there,
  Dependabot PRs need a manual look.

## Next 3 steps
1. Daniel approves ADR 0003 (or asks for changes); then mark the status line in the file as approved.
2. Cut the next release (minor, because of the entity ID rename) once Daniel gives the OK.
3. Watch the first scheduled rule keeper and weekly summary runs; open an issue if they fail.

## Known traps
- The ruleset file is not applied automatically; re-import it when `.github/rulesets/main.json` changes.
- Required checks are the job ids of `Validate`; renaming a job needs a ruleset update.
- HANDOVER.md is rewritten by the orchestrator only; developer runs that are asked to change it must refuse and say so
  (this is why #103 needed a human).
- `RENAMED_KEY_OLD_NAMES` must keep the old display names as long as the migration that uses them exists (ADR 0003).
- Expected, not yet measured: Dependabot proposes bumps for the SHA pins only when upstream publishes newer tags
  (it follows tags, not branches). Until then, check the upstream repos by hand.
