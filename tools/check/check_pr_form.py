"""Check PR form: title is printable ASCII (English), body is not empty.

Reads PR_TITLE and PR_BODY from the environment (pull_request events). On workflow_dispatch it reads
title and body of the open PR for GITHUB_REF_NAME via `gh pr view` (needs GH_TOKEN); no PR means skipped.
Also fails an `agent/<N>-*` PR whose body does not mention `#<N>`. Also fails (when the PR file list is known): a design PR (only `docs/design/`) with a closing keyword
(use `Refs #N`), and a PR touching HANDOVER.md that is not an orchestrator PR (`agent/orchestrator-handover-*`).
Also fails a body or commit message with a tool footer (`Generated with`, `claude.ai/code/session`, `Claude-Session:`).
An optional `## Friction` section (see tools/friction.py) is accepted, never required.
Skipped for local runs and pushes to main. Whether the title is really English cannot be verified.
"""
import json
import os
import re
import subprocess
import sys

# One pattern for every GitHub closing form: `Closes #N`, `Closes owner/repo#N`, `Closes https://github.com/owner/repo/issues/N`.
# agent-fix.yml runs `check_pr_form.py closing FILE` (from main) instead of keeping its own copy.
CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b\s*:?\s+"
    r"(?:(?:[\w.-]+/[\w.-]+)?#\d+|(?:https?://)?(?:www\.)?github\.com/[\w.-]+/[\w.-]+/issues/\d+)",
    re.IGNORECASE,
)
# Tool/AI attribution footers are banned in PR bodies and commit messages (AGENTS.md, Commits and PRs).
ATTRIBUTION = re.compile(r"Generated with|claude\.ai/code/session|Claude-Session:", re.IGNORECASE)
AGENT_BRANCH = re.compile(r"^agent/(\d+)-")
ORCHESTRATOR_BRANCH = "agent/orchestrator-handover"


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
    if ATTRIBUTION.search(body) or ATTRIBUTION.search(commits):
        errors.append("no tool/AI attribution in the PR body or commit messages (`Generated with`, `claude.ai/code/session`, `Claude-Session:`)")
    if files and all(f.startswith("docs/design/") for f in files) and CLOSING.search(body):
        errors.append("design PRs must use `Refs #N`, not a closing keyword (only the PR that completes an issue closes it)")
    if "HANDOVER.md" in files and not head_ref.startswith(ORCHESTRATOR_BRANCH):
        errors.append("HANDOVER.md belongs to the orchestrator; put your notes in the PR body")
    m = AGENT_BRANCH.match(head_ref)
    if m and not re.search(rf"#{m.group(1)}(?!\d)", body):
        errors.append(f"branch {head_ref} works on issue #{m.group(1)}: the body must reference it (`Closes #{m.group(1)}` or `Refs #{m.group(1)}`)")
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
    for e in errors:
        print(f"check_pr_form: {e}")
    if not errors:
        print("check_pr_form: ok")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
