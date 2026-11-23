"""Close the issues whose agent PR is merged (no model). The merge train (tools/train.py) runs it after every push to main.

GitHub closes an issue only for a closing keyword in the body of a PR merged into the default branch. An agent PR
whose body names its issue any other way (a bare `#N`), or whose keyword was lost in a body edit, leaves the issue
open and the dispatcher would start it again. Per run, for the last MERGED_LIMIT merged same-repo `agent/` PRs into main:
- its issues = the numbers of its closing keywords, plus the N of its branch `agent/<N>-...`;
- an issue the body names with `Refs #N` is left open (partial work, a design, a split step: decided by the developer);
- an issue that was reopened after it had been closed is left open (someone wants more work on it);
- every other one that is still open is closed as completed with one comment, and loses `agent:dev`.
The train's batch PR (`agent/batch`) counts with the `Closes #N` lines the train wrote into its body.
Needs the gh CLI (GH_TOKEN with issues write, GH_REPO). Prints nothing; returns the lines for the train's log.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "check"))
from check_pr_form import AGENT_BRANCH, BARE_NUMBER, CLOSING, REFS

MERGED_LIMIT = 30
OPEN_LIMIT = 200


def issues_of(pr):
    """Issue numbers a merged PR completed, in order: closing keywords and its agent branch, minus its `Refs #N`."""
    body = pr.get("body") or ""
    nums = [int(n) for c in CLOSING.finditer(body) for n in BARE_NUMBER.findall(c.group(0))]
    m = AGENT_BRANCH.match(pr.get("headRefName") or "")
    if m and m.group(1) not in REFS.findall(body):  # a closing keyword wins over `Refs`, the branch number does not
        nums.append(int(m.group(1)))
    return list(dict.fromkeys(nums))


def landed(merged, open_issues):
    """[(issue, pr)] to close: open, not reopened issues of merged same-repo agent PRs into main; first PR wins."""
    waiting = {i["number"]: i for i in open_issues if (i.get("stateReason") or "").upper() != "REOPENED"}
    out = {}
    for p in merged:
        if (not (p.get("headRefName") or "").startswith("agent/") or p.get("isCrossRepository")
                or p.get("baseRefName") != "main" or not p.get("mergedAt")):
            continue
        for n in issues_of(p):
            if n in waiting and n != p["number"]:
                out.setdefault(n, p["number"])
    return sorted(out.items())


def close_landed(run):
    merged = json.loads(run("pr", "list", "--state", "merged", "--limit", str(MERGED_LIMIT), "--json",
                            "number,body,headRefName,baseRefName,isCrossRepository,mergedAt"))
    if not merged:
        return []
    open_issues = json.loads(run("issue", "list", "--state", "open", "--limit", str(OPEN_LIMIT), "--json",
                                 "number,labels,stateReason"))
    labels = {i["number"]: {x["name"] for x in i.get("labels") or []} for i in open_issues}
    lines = []
    for issue, pr in landed(merged, open_issues):
        try:
            run("issue", "close", str(issue), "--reason", "completed", "--comment", f"Completed by #{pr} (merged).")
            if "agent:dev" in labels.get(issue, ()):
                run("issue", "edit", str(issue), "--remove-label", "agent:dev")
            lines.append(f"closed issue #{issue}: PR #{pr} is merged")
        except (subprocess.CalledProcessError, OSError) as e:
            lines.append(f"closing issue #{issue} failed ({type(e).__name__})")
    return lines

