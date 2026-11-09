# Handover
<!-- Overwrite, do not append. History lives in git and CHANGELOG. Max 60 lines. -->

## Goal
Agent system (from Bankaifan/agent-template) ported into this repository: PR `infra/agent-system`.

## Current state
- Released version: 0.18.0 (2026-11-09). No release is part of the agent-system PR.
- Accepted into the HACS default catalog (stated by Daniel). PR #69 (installation docs lead with the HACS catalog)
  is merged and sits under `[Unreleased]` in the CHANGELOG.
- Agent workflows are in place but inert until Daniel sets secrets/variables and imports the ruleset
  (see `docs/decisions/0001-agent-setup.md` and the PR description).
- pymodbus floor (issue #76, option b): manifest, test requirements and CI use pymodbus 3.9 (`>=3.9.0`). The
  tests-min-ha job runs on pymodbus 3.9.2 (what HA 2025.8 ships). The 3.9 API fallbacks in `modbus_client.py` are
  covered by fake-client tests in `tests/test_client.py`. Dependabot ignores pymodbus in the pip group.

## Open
- Entity IDs still carry old names for entities whose keys were renamed; the entity IDs should be renamed to the
  current names (needs a decision on how: registry migration vs. documented manual rename). Not started.
- Agent setup not verified end to end: app permissions, `workflow_run` events from app-created runs, gitleaks licence.
- Dependabot PRs: the `hacs` job needs `pull-requests: write`, which Dependabot runs lack; if it fails there,
  Dependabot PRs need a manual look.
- pymodbus 3.9.2 CI job not yet run on GitHub: the real-library behaviour on 3.9.2 is unmeasured until Validate runs.

## Next 3 steps
1. Daniel merges the agent-system PR, sets secrets/variables, imports `.github/rulesets/main.json`, runs `setup`.
2. Keep `ORCHESTRATOR_ENABLED=false` until one manual issue with label `agent:dev` ran through dev -> review -> merge.
3. Decide the entity ID rename (see Open).

## Known traps
- The ruleset file is not applied automatically; re-import it when `.github/rulesets/main.json` changes.
- Required checks are the job ids of `Validate`; renaming a job needs a ruleset update.
