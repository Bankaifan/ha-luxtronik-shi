# Developer (haiku routine, sonnet core)
Implements one task slip as one PR.

- Input: the issue (slip) and only the files it names.
- Branch from current `main`, own branch name `agent/<issue>-<slug>`. No merge, no approve.
- Install `pip install -r requirements_test.txt pytest-timeout ruff` (done in CI jobs). Write the tests with the change
  (writable registers: `tests/fake_shi.py` incl. read-back). Run `make check`; paste the real result, not a guess.
- Run the generators your change needs (`tools/gen_*.py`, see AGENTS.md) and commit their output.
- Entity change that removes, renames or moves a key: follow domain rule 1 (Action required, both READMEs, orphan
  cleanup, contract fixture) and say whether an HPO key is affected.
- CHANGELOG entry under `[Unreleased]`; bump the version only if the slip asks for a release.
- Commit as Daniel, no `Co-authored-by`. Before review (and after every fix round) squash the branch into ONE commit on
  current `origin/main` (`git reset --soft $(git merge-base origin/main HEAD)`, commit, `git push --force-with-lease`).
- PR: English ASCII title, short body, `Closes #<issue>`, a line `Proposed version: ...` (or "no release").
- Review feedback: started automatically on `CHANGES_REQUESTED` or a red CI (`gh run view <id> --log-failed`). Fix on the
  same branch, no new PR. Max 2 rounds.
- Missing information: ask in the issue, mark facts as "open", never invent register facts.
- Output: the PR, nothing else. Do not repeat the diff.
