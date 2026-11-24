"""Give an agent PR the task ID of its issue (no model).

`check_pr_form` fails a PR on branch `agent/<N>-...` whose title does not start with the task ID of issue N
(`V0-WEATHER-SKY: `). A developer model sometimes invents its own name (`V0-WEATHER-FORECAST: ...`), and no agent
may edit a PR title: the fix rounds then run out on a form failure nobody can repair (roblox_energy PR 382, parked
nine minutes after it was opened). This script sets the title: the issue's ID, then the PR's own summary.

  python3 tools/pr_title.py fix PR    prints the new title, or `ok` when nothing was changed; never fails the step

Only a same-repo PR on `agent/<N>-...` whose issue title carries a task ID is touched; the summary text stays the
developer's, cut to the 100 characters the form check allows. The commit subjects follow through
tools/branch_repair.py (the train sets them to the new NAME). Needs the gh CLI (GH_TOKEN, GH_REPO).
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "check"))
import task_ids
from check_pr_form import AGENT_BRANCH

MAX_TITLE = 100  # check_pr_form's limit


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def fixed(title, issue_title):
    """The PR title with the issue's task ID in front, or None when it already has it or the issue has no ID."""
    tid = task_ids.task_id_of(issue_title)
    title = title or ""
    if not tid or title.startswith(f"{tid}: "):
        return None
    summary = task_ids.TASK_ID.sub("", title, count=1).strip() or "update"
    return f"{tid}: {summary}"[:MAX_TITLE].rstrip()


def issue_of(pr):
    """Issue number (string) of a same-repo `agent/<N>-...` PR, else None."""
    m = AGENT_BRANCH.match(pr.get("headRefName") or "")
    return m.group(1) if m and not pr.get("isCrossRepository") else None


def fix(pr, run=gh):
    """Set the title of PR (dict with number, title, headRefName, isCrossRepository) when it lacks the issue's task
    ID. Returns the new title, or None when nothing was changed (also on any gh error)."""
    number = issue_of(pr)
    if not number:
        return None
    try:
        new = fixed(pr.get("title"), json.loads(run("issue", "view", number, "--json", "title")).get("title"))
        if new:
            run("pr", "edit", str(pr["number"]), "--title", new)
        return new
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError, AttributeError):
        return None


def main(argv):
    if len(argv) != 3 or argv[1] != "fix" or not argv[2].isdigit():
        print(__doc__, file=sys.stderr)
        return 2
    try:
        pr = json.loads(gh("pr", "view", argv[2], "--json", "number,title,headRefName,isCrossRepository"))
    except (subprocess.CalledProcessError, OSError, ValueError):
        print("ok")
        return 0
    print(fix(pr) or "ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
