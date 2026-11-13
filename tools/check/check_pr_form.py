"""Check PR form: title is printable ASCII (English), body is not empty.

Reads PR_TITLE and PR_BODY from the environment (pull_request events). On workflow_dispatch it reads
title and body of the open PR for GITHUB_REF_NAME via `gh pr view` (needs GH_TOKEN); no PR means skipped.
Also fails an `agent/<N>-*` PR whose body does not mention `#<N>`. Also fails (when the PR file list is known): a design PR (only `docs/design/`) with a closing keyword
(use `Refs #N`), and a PR touching HANDOVER.md that is not an orchestrator PR (`agent/orchestrator-handover-*`).
Also fails a commit message or body with a tool footer (patterns: tools/attribution.py). Bodies are stripped by
strip-attribution.yml first (tools/strip_attribution.py), so the body rule only sees what the strip left or missed.
An optional `## Friction` section (see tools/friction.py) is accepted, never required.
Also fails a PR whose linked issue (agent branch, `Closes #N`, `Refs #N`) has a task ID in its title (tools/task_ids.py)
unless the PR title starts with the same `<ID>: `. Unreadable issues are not checked.
Skipped for local runs and pushes to main. Whether the title is really English cannot be verified.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import attribution  # tools/, the one pattern list shared with strip_attribution.py
import task_ids  # tools/, the task ID rule of issue #501

# One pattern for every GitHub closing form: `Closes #N`, `Closes owner/repo#N`, `Closes https://github.com/owner/repo/issues/N`.
# agent-fix.yml runs `check_pr_form.py closing FILE` (from main) instead of keeping its own copy.
CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s+"
    r"(?:(?:[\w.-]+/[\w.-]+)?#\d+|(?:https?://)?(?:www\.)?github\.com/[\w.-]+/[\w.-]+/issues/\d+)",
    re.IGNORECASE,
)
AGENT_BRANCH = re.compile(r"^agent/(\d+)-")
ORCHESTRATOR_BRANCH = "agent/orchestrator-handover"
REFS = re.compile(r"\bRefs\s+#(\d+)\b", re.IGNORECASE)
BARE_NUMBER = re.compile(r"(?<![\w./-])#(\d+)\b")  # `#N` of this repo only, not `owner/repo#N`


def gh_pr(ref):
    """Title, body (plus commit messages), head branch and changed files of a PR (number or branch) via gh, or None."""
    try:
        out = subprocess.run(["gh", "pr", "view", ref, "--json", "title,body,headRefName,files,commits"],
                             check=True, capture_output=True, text=True).stdout
        pr = json.loads(out)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return None
    files = [f.get("path", "") for f in pr.get("files") or []]
    commits = "\n".join(f"{c.get('messageHeadline') or ''}\n{c.get('messageBody') or ''}" for c in pr.get("commits") or [])
    return pr.get("title") or "", pr.get("body") or "", pr.get("headRefName") or "", files, commits


def form_errors(body, head_ref, files, commits=""):
    """Rules that need the changed files or commit messages; nothing known means nothing to check."""
    errors = []
    if attribution.found(body) or attribution.found(commits):
        errors.append("no tool/AI attribution in the PR body or commit messages (patterns: tools/attribution.py)")
    if files and all(f.startswith("docs/design/") for f in files) and CLOSING.search(body):
        errors.append("design PRs must use `Refs #N`, not a closing keyword (only the PR that completes an issue closes it)")
    if "HANDOVER.md" in files and not head_ref.startswith(ORCHESTRATOR_BRANCH):
        errors.append("HANDOVER.md belongs to the orchestrator; put your notes in the PR body")
    m = AGENT_BRANCH.match(head_ref)
    if m and not re.search(rf"#{m.group(1)}(?!\d)", body):
        errors.append(f"branch {head_ref} works on issue #{m.group(1)}: the body must reference it (`Closes #{m.group(1)}` or `Refs #{m.group(1)}`)")
    return errors


def linked_issues(body, head_ref):
    """Numbers (strings) of the issues a PR works on: its agent branch, its closing keywords and its `Refs #N`."""
    m = AGENT_BRANCH.match(head_ref)
    nums = [m.group(1)] if m else []
    nums += [n for c in CLOSING.finditer(body) for n in BARE_NUMBER.findall(c.group(0))]
    return sorted(set(nums + REFS.findall(body)), key=int)


def gh_issue_title(number):
    """Title of an issue of this repo via gh, or None when it cannot be read."""
    try:
        out = subprocess.run(["gh", "issue", "view", number, "--json", "title"],
                             check=True, capture_output=True, text=True).stdout
        return json.loads(out)["title"]
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError, TypeError):
        return None


def id_errors(title, issue_titles):
    """A PR on a task issue (title `<ID>: ...`) starts its own title with the same ID; other issues are not checked."""
    errors = []
    for it in issue_titles:
        tid = task_ids.task_id_of(it)
        if tid and not title.startswith(f"{tid}: "):
            errors.append(f"title must start with the task ID of its issue, `{tid}: ` (issue title: {it})")
    return errors


def main() -> int:
    if sys.argv[1:2] == ["closing"]:  # exit 0 on a closing keyword, 1 on none, 2 on any error
        try:
            with open(sys.argv[2], encoding="utf-8", errors="replace") as f:
                return 0 if CLOSING.search(f.read()) else 1
        except (OSError, IndexError) as e:
            print(f"check_pr_form: cannot read file: {e}", file=sys.stderr)
            return 2
    event = os.environ.get("GITHUB_EVENT_NAME", "pull_request")
    head_ref, files, commits = "", [], ""
    if event == "workflow_dispatch":
        pr = gh_pr(os.environ.get("GITHUB_REF_NAME", ""))
        title, body, head_ref, files, commits = pr if pr else (None, "", "", [], "")
    elif event == "pull_request":
        title, body = os.environ.get("PR_TITLE"), os.environ.get("PR_BODY") or ""
        head_ref = os.environ.get("PR_HEAD_REF", "")
        number = os.environ.get("PR_NUMBER")
        if title is not None and number:
            pr = gh_pr(number)
            files, commits = (pr[3], pr[4]) if pr else ([], "")
            if pr:
                body = pr[1]  # live body: strip-attribution.yml may have cleaned it after the event was queued
    else:
        title, body = None, ""
    if title is None:
        print("check_pr_form: skipped (no PR title)")
        return 0
    errors = []
    if not title.strip():
        errors.append("title is empty")
    elif not all(32 <= ord(c) < 127 for c in title):
        errors.append("title must be English, printable ASCII only")
    elif len(title) > 100:
        errors.append("title is longer than 100 characters")
    if not body.strip():
        errors.append("body is empty (what and why, link the issue)")
    errors += form_errors(body, head_ref, files, commits)
    issue_titles = [t for t in map(gh_issue_title, linked_issues(body, head_ref)) if t is not None]
    errors += id_errors(title, issue_titles)
    for e in errors:
        print(f"check_pr_form: {e}")
    if not errors:
        print("check_pr_form: ok")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
