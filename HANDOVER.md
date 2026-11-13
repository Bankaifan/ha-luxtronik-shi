# Handover
<!-- Overwrite, do not append. History lives in git and CHANGELOG. Max 60 lines. -->

## Goal
Keep the integration stable for production use and let the agent system (from Bankaifan/agent-template) carry
routine work: issue -> dev -> review -> merge, with Daniel deciding only what needs a human.

## Current state (2026-11-13)
- Released version: 1.1.0 (follows the published v1.0.0). Entity IDs are English (0.19.0), VBO and FP are documented.
  Accepted into the HACS default catalog (stated by Daniel).
- Agent system is live: orchestrator, scout, status runs, template sync (`.agents/template.json`).
- Open PRs: none. Main CI: no red run in the last 10 runs; one agent-dev run was still in progress.
- #129 (Novelan-SICV note) is closed.
- #154 Template sync 09335eb (template 1.7 -> 1.88): Part 1 (reviewer pipeline) is on main (4164f70). Part 2 (about 200 files)
  was too big for one PR; Daniel answered "Ja" on 2026-11-13, the block was dropped. Slip rewritten: step 2a only
  (move existing tests to tests/agent/ plus conftest); 2b (new tools and tests) and 2c (workflows, rulesets, roles)
  follow as separate slips after 2a merges. `synced_sha` moves only with the last part.
- #130 (prio:2, `idea`, failure_class digit handling) is not approved and not startable.

## Open
- #154 step 2a: PR not opened yet; open. 2b and 2c slips not written.
- ADR 0003 (entity ID rename): Daniel's approval is marked open in the file; open.
- Rule keeper and weekly summary: first scheduled runs not verified; open.
- Dependabot PRs: the `hacs` job needs `pull-requests: write`, which Dependabot runs lack; manual look if it fails.

## Next 3 steps
1. Watch the #154 step 2a PR; after merge write the 2b slip (overlap check first), then 2c.
2. Daniel approves ADR 0003 or asks for changes.
3. Watch rule keeper and weekly summary runs; open an issue if they fail.

## Known traps
- The ruleset file is not applied automatically; re-import it when `.github/rulesets/main.json` changes.
- Required checks are the job ids of `Validate`; renaming a job needs a ruleset update.
- HANDOVER.md is rewritten by the orchestrator only; developer runs asked to change it must refuse.
- `RENAMED_KEY_OLD_NAMES` must keep the old display names as long as the migration exists (ADR 0003).
- Template sync Part 2 overridden files (conftest, Makefile, validate.yml, test_ruleset, ...) need hand edits, see #154.
- Orchestrator never deletes files; body files go to git-ignored `.agent-out` (#118).
