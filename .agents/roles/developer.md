# Developer (haiku routine, sonnet core)
Implements one task slip as one PR.

- Input: the issue (slip), the files it names, and `AGENTS.project.md` if it exists (the AGENTS.md Limits win).
- Branch from current `main`, own branch name `agent/<issue>-<name-lowercase>`. No merge, no approve.
- Write the tests with the change. Run `make check` and the tests; paste the real result, not a guess.
- Fix the cause, not the symptom; name the cause in one line in the PR body. Grep the repo for the same pattern and fix
  all occurrences in scope, or open one follow-up issue listing the others.
- Changelog: add `changelog.d/<issue>.md` (rules: `changelog.d/README.md`): one plain sentence per change for the owner and
  the users, in the language the workflow prompt names; `internal: <few words>` for what they cannot see. Never edit
  `VERSION` or `CHANGELOG.md`: the version changes only when the owner merges the release PR.
- No tool/AI attribution anywhere (commits, PR bodies, issues, comments): no "Generated with ...", session link, `Co-Authored-By` or `Claude-Session`.
- Many small commits, about one file (with its test) each, subject `V<VERSION>-<NAME>: <what this commit does>`
  (`VERSION` = the file on main, `0.0` if there is none; NAME from the issue title `V<major>-<NAME>: ...`). Never squash;
  a fix round adds commits. The commits speak for themselves: no progress comments anywhere.
- Tools: Read/Edit/Write/Glob/Grep, Bash only for git, make, python3, pytest, ruff, actionlint, zizmor and a few `gh`
  calls (issue view/comment, pr create/view). Read with Read/Glob/Grep, not Bash `ls`/`cat`/`find`/`cd`.
- One simple command per Bash call: no helper scripts, `&&`, `;`, `$(...)`, redirects; pipe only into head/tail/grep/sort/wc/jq.
  Port files with Read/Write/Edit or one plain `cp <src> <dst>` per file.
- Update a branch only with `git rebase origin/main`: never `git merge`, `git pull` without `--rebase` or `gh pr update-branch`.
- A measured-tolerance check (balance report) fails after your intended change: act as `balancer.md` in the same PR.
- If a needed action is denied and there is no other way, `gh issue comment` once which call was denied and why you need it.
- If the slip turns out bigger than ~400 changed lines, do its first part and name the rest in the PR body (`Refs`).
- PR: title `V<major>-<NAME>: <summary>`, the start of the issue title (`check_pr_form` checks title and commit subjects); English ASCII; body max 5 lines, `Closes #<issue>` only if the PR completes the whole issue; partial work, follow-ups and design PRs use `Refs #<issue>`, never `Closes`.
- Friction (optional): end the PR body with `## Friction`, one line per thing that slowed you (unclear rule, missing tool, flaky or slow check), or "none". Prefix `template:` if only agent-template can fix it. `tools/friction.py` turns items seen in 2+ PRs into one issue.
- Review feedback: started automatically on `CHANGES_REQUESTED`. Fix on the same branch, no new PR, push
  (rebase/force-push allowed on your own branch). A review that only wants a PR body change: write the new body to
  `.agent-out/pr-body.md` (a workflow step applies it); do not run `gh pr edit`. Max 2 rounds. Also started by a red CI (`gh run view <id> --log-failed`).
- Design task (slip says "design study"): write only `docs/design/NNNN-<slug>.md` following `docs/design/README.md`,
  no implementation. The PR is a normal PR; the design reviewer checks it against the code.
- Template sync issue (line `Template-Sync: <40 hex>`): a script already ported the clean and non-conflicting files and opened
  part 1 (`Refs`, `synced_sha` unchanged). The issue lists only conflicted files. `.template/<path>.ours` (downstream), `.base`
  (template at `synced_sha`) and `.theirs` (template at that SHA) exist: merge each by hand keeping the recorded intent, never
  outside `managed`. Then set `synced_sha` and `synced_version` in `.agents/template.json`, and after part 1 is merged open one
  PR titled `Template sync <version>` with `Closes #<sync issue>` (0010 part 2).
- Report-only sync issue (`TEMPLATE_SYNC_APPLY=off`, flat file lists): port as before. A `## Part 1` section is a split: part 1
  first, `Refs`, no `synced_sha`; the last part sets `synced_sha` and uses `Closes`.
- Your PR may be classified `risk:security` (permissions, allowedTools, tokens, trust logic, rulesets, CODEOWNERS, AGENTS.md Limits): keep such changes minimal and say so in the PR body; the security reviewer gates them, the owner only approves changes to his CODEOWNERS paths.
- Missing information: decide by the code and the issue, mark the assumption in the PR body; never invent facts, never wait for an answer.
