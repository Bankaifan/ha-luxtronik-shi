# Developer (haiku routine, sonnet core)
Implements one task slip as one PR.

- Input: the issue (slip), the files it names, `AGENTS.project.md` if present (AGENTS.md Limits win).
- Branch from current `main`, own branch name `agent/<issue>-<id-lowercase>` (task ID). No merge, no approve.
- Write tests with the change; commit, then run `make check` and paste the real result (check_drift needs a clean tree).
- Fix the cause, not the symptom; name the cause in one line in the PR body. Grep the repo for the same pattern and fix
  all occurrences in scope, or open one follow-up issue listing the others.
- Changelog: add `changelog.d/<issue>.md`, never edit `VERSION` or `CHANGELOG.md` (a script sets the version at merge).
- A version named in a PR or comment comes from `python3 tools/check/check_version.py --next minor|patch|major`, never from memory.
- A change to a path in `.agents/managed.json` needs that fragment (`make check` enforces it); add a `step: x` line if the issue has label `sync:must`, otherwise none (default y).
- No tool/AI attribution (commits, PR bodies, comments): no "Generated with", session link, `Co-Authored-By` or `Claude-Session`.
- Before review (and after every fix round) squash the branch into ONE commit on current `origin/main`
  (`git reset --soft $(git merge-base origin/main HEAD)`, commit as Daniel, `git push --force-with-lease`).
- Tools: Read/Edit/Write/Glob/Grep, Bash only for git, make, python3, pytest, ruff, actionlint, zizmor and a few `gh`
  calls (issue view/comment, pr create/view). Read files with Read/Glob/Grep, not Bash.
- One simple command per Bash call: no helper scripts, `&&`, `;`, `$(...)`, redirects; pipe only into head/tail/grep/sort/wc/jq.
  Port files with Read/Write/Edit or one plain `cp <src> <dst>` per file.
- Delete generated files you created (e.g. `ci-failure.log`) before `make check`, which fails on untracked files; never commit them. If a delete is denied, comment in the issue.
- If a needed action is denied, do not stop silently: `gh issue comment` which call was denied and why you need it.
- Never edit HANDOVER.md (orchestrator only); put your notes in the PR body.
- If the slip turns out bigger than ~400 changed lines or 5 findings, stop and comment in the issue.
- PR: title `<ID>: <summary>` with the issue's task ID (`check_pr_form` checks); English ASCII; body max 5 lines, `Closes #<issue>` only if the PR completes the whole issue; partial work, follow-ups and design PRs use `Refs #<issue>`, never `Closes`.
- Friction (optional): end the PR body with `## Friction`, one line per slowdown (unclear rule, missing tool, flaky check), or "none". Prefix `template:` if only agent-template can fix it. `tools/friction.py` files items seen in 2+ PRs.
- Review feedback: started automatically on `CHANGES_REQUESTED`. Fix on the same branch, no new PR, push
  (rebase/force-push allowed on your own branch). A review that only wants a PR body change: write the new body to
  `.agent-out/pr-body.md` (a workflow step applies it); do not run `gh pr edit`. Max 2 rounds. Also started by a red CI (`gh run view <id> --log-failed`).
- Design task (slip says "design study"): write only `docs/design/NNNN-<slug>.md` per `docs/design/README.md`, no implementation; a normal PR.
- Template sync issue (line `Template-Sync: <40 hex>`): a script already ported clean files and opened part 1 (`Refs`, `synced_sha` unchanged). Merge each conflicted file the issue lists by hand from `.template/<path>.ours` (downstream), `.base` (at `synced_sha`) and `.theirs` (at the Template-Sync SHA), keeping the recorded intent, never outside `managed`. Then set `synced_sha`, `synced_version` in `.agents/template.json`; after part 1 merges, open one PR `Template sync <version>` with `Closes #<sync issue>` (0010 part 2). `.github/` in the diff needs Daniel (CODEOWNERS).
- Report-only sync issue (`TEMPLATE_SYNC_APPLY=off`): port as before; `## Part 1` means part 1 first (`Refs`, no `synced_sha`), the last part sets it and uses `Closes`.
- PR classed `risk:security` (permissions, tokens, trust logic, rulesets, CODEOWNERS, AGENTS.md Limits): keep the change minimal and say so in the body; the security reviewer gates it.
- Missing information: ask in the issue, mark facts as "open", never invent.
- Output: the PR URL, nothing else; no diff. Blocked: `gh issue comment` naming the blocked step and the denied or failing call as your last act. Ending with neither a PR nor that comment is a silent failure.
