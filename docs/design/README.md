# Design studies

Big work (architectural, breaking, release-relevant, multi-PR) starts with a design PR that adds
`docs/design/NNNN-<slug>.md` (next free four-digit number). No implementation in that PR.

Sections, in this order:
1. Goal
2. Current state (file references)
3. Options with trade-offs
4. Chosen approach
5. Migration and compatibility
6. Test and verification plan (must be able to fail on today's code; proves it works before rollout)
7. Rollback
8. Split into PR-sized implementation issues (title, files, order)
9. **Owner decisions**: only what Daniel must decide (user-facing breaking changes, publishing outside the repo
   such as a first PyPI release, costs). Write `none` if there is nothing.

Flow: developer writes it, the design reviewer approves it (see `.agents/roles/design-reviewer.md`). With `none` it
merges without Daniel. Otherwise the PR gets `needs-human`, a review request to Daniel and a German summary.
After the merge the orchestrator creates the implementation issues, each with a line `Design: docs/design/NNNN-<slug>.md`.
