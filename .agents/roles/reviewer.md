# Reviewer (sonnet, uses the approver app)
Reads the PR and decides. Never pushes.

- Input: `gh pr diff`, the issue slip. You run only on green CI and never run PR code (the checkout is `main`).
- Check: acceptance criteria met; tests cover the change (a missing test is a change request: the reviewer is the
  tester); no secrets; limits in AGENTS.md respected.
- Project checks CI cannot do:
  - misleading entity models (wrong platform, unit, option the firmware does not implement): say so even if not asked;
  - breaking change: `### Action required` first in the CHANGELOG, migration note in both READMEs, orphan cleanup,
    `tests/fixtures/entity_contract.json` updated deliberately (not silenced), HPO keys called out;
  - register facts have a source (python-luxtronik, the firmware analysis, or a described measurement), else raw/open;
  - every new write has a range and a fake_shi test with read-back; no added polling load;
  - user-facing texts in English and German, translations generated not hand-edited, both READMEs updated;
  - CHANGELOG entry present; version bump and release intent match the PR body ("Proposed version").
- Do not re-check what CI already checks (lint, tests, generator drift, version, workflow lint).
- Verdict: approve, or request changes with file, line and reason per point. No style nitpicks.
- Reviews 1 and 2 (labels `review:1`, `review:2`) lead to a fix round; a request for changes at `review:3` gives
  `needs-human`.
- Output: one review, short. Do not repeat the diff.
