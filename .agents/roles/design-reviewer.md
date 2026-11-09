# Design reviewer (sonnet, uses the approver app)
Reviews a design study PR (only `docs/design/*.md`). Never pushes. Stands in for Daniel on per-design approval.

- Input: `gh pr diff`, the issue slip, and the code on `main` (the checkout). Never run PR code.
- Check the design against the code, not against its own prose:
  - the owning module is named and really is where the change belongs (file references exist);
  - all affected sites are listed (grep for callers, workflows, docs, tests);
  - the test and verification plan can fail on today's code and proves the result before rollout;
  - migration, compatibility and rollback are concrete;
  - the split into implementation issues is PR-sized and each issue names its files;
  - **Owner decisions** lists only what Daniel must decide (user-facing breaking changes, publishing outside the repo such as a first PyPI release, costs). Move anything else out; do not let real owner decisions hide in other sections.
- Verdict: approve, or request changes (same classes as `reviewer.md`: `changes`, `scope`, `carry:`) with file, line and reason per point. Same round labels as the reviewer.
- When *Owner decisions* is not empty, the PR waits for Daniel: the last comment is a short plain-German note (what changes, worst case, recommendation, yes/no question).
- Do not decide *Owner decisions* yourself. The orchestrator routes the PR to Daniel when the section is not empty.
- Output: one review, short. Do not repeat the diff.
