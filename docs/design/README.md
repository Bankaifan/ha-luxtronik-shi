# Design studies

A design PR adds `docs/design/NNNN-<slug>.md` (next free four-digit number) only if the work changes who or what
is trusted, token or app permissions, CODEOWNERS paths, or what leaves the repo (AGENTS.md). Other big or multi-PR
work starts directly with a split in the issue. No implementation in a design PR.

Sections, in this order:
1. Goal
2. Current state (file references)
3. Options with trade-offs
4. Chosen approach
5. Migration and compatibility
6. Test and verification plan (must be able to fail on today's code; proves it works before rollout)
7. Rollback
8. Split into PR-sized implementation issues, in the fixed format below. Cut the split so that as many steps as
   possible are independent with disjoint files: independent steps run in parallel.
9. **Owner decisions**: only what Daniel must decide (user-facing breaking changes, publishing outside the repo
   such as a first PyPI release, costs). Write `none` if there is nothing.

Flow: developer writes it, the design reviewer approves it (see `.agents/roles/design-reviewer.md`). With `none` it
merges without Daniel. Otherwise the PR gets `needs-human`, a review request to Daniel and a German summary.
After the merge `tools/design_split.py` (workflow `design-split`, no model) creates the implementation issues, each with a
line `Design: docs/design/NNNN-<slug>.md` and, for a step that depends on earlier ones, a line `Depends on: #<n>[, #<m>]`
(`tools/deps.py`). The label is the prio of the issue the design PR names with `Refs #N`; that issue loses `agent:dev` and
`needs-human`. A second run creates nothing (title and `Design:` line are searched).

## Section 8 format (designs from 0016 on)

One block per step, numbered 1, 2, 3 without gaps; `make check` fails a design whose section 8 does not parse:

```
### Step 2: Title of the step
Files: `tools/a.py`, `tests/test_a.py`
Acceptance: one line, what must be true when the step is done
Depends on: 1
```

`Files:` and `Acceptance:` are required, each on one line. `Depends on:` is optional: earlier step numbers, comma
separated; leave it out for an independent step. Step titles are unique. The issue title of a step is
`<ID>-<n>: <step title>` (the ID of the design's source issue, the one the design PR names with `Refs #N`; `n` is the step
number), see `.agents/roles/orchestrator.md`.
