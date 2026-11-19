"""Round limit: restart the task once automatically, close superseded PRs.

CLI (needs the gh CLI with GH_TOKEN and GH_REPO):
  restart.py limit PR        agent PR hit the round limit: first time restart the issue (label restart:1, slip comment,
                             agent:dev re-added, PR closed), otherwise the PR is parked (label `parked`, one comment)
  restart.py supersede       close every open agent PR that a newer open agent PR for the same issue replaces
"""
import json
import os
import re
import subprocess
import sys

import liveness
from agent_guard import add_labels, park

RESTART = "restart:1"
_REFS = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?)\s+#(\d+)", re.IGNORECASE)
_CLOSING = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)
_BLOCKING = 1500  # chars of review text per review in the slip

def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def issue_refs(body):
    """Issue numbers named by closing keywords or `Refs` in a PR body, in order, without duplicates."""
    seen = []
    for n in _REFS.findall(body or ""):
        if int(n) not in seen:
            seen.append(int(n))
    return seen


def own_issues(body):
    """The issues a PR works on: the ones it closes. `Refs` count only when it closes none (design or partial step),
    so sibling PRs that share a parent through `Refs #parent` do not replace each other."""
    closing = list(dict.fromkeys(int(n) for n in _CLOSING.findall(body or "")))
    return closing or issue_refs(body)


def is_agent_branch(pr):
    return (pr.get("headRefName") or "").startswith("agent/") and not pr.get("isCrossRepository")


def superseded(prs):
    """[(old, new)] for open agent PRs whose issue is also referenced by a newer open agent PR."""
    newest = {}
    for p in prs:
        if not is_agent_branch(p):
            continue
        for n in own_issues(p.get("body")):
            newest[n] = max(newest.get(n, 0), p["number"])
    out = {}
    for p in prs:
        if not is_agent_branch(p):
            continue
        newer = [newest[n] for n in own_issues(p.get("body")) if newest[n] > p["number"]]
        if newer:
            out[p["number"]] = max(newer)
    return sorted(out.items())


def close_superseded(prs, run=gh):
    done = []
    for old, new in superseded(prs):
        run("pr", "close", str(old), "--comment", f"Superseded by #{new}")
        done.append((old, new))
    return done


def blocking_findings(reviews):
    """Bodies of the reviews that requested changes, capped, so the new run knows what failed."""
    texts = [(r.get("body") or "").strip() for r in reviews if r.get("state") == "CHANGES_REQUESTED"]
    return [t[:_BLOCKING].replace("```", "'''") for t in texts if t]


def slip_comment(pr, findings, why="the developer and the reviewers did not converge in 3 reviews"):
    lines = [
        f"Restart 1/1: PR #{pr} is stuck. Start fresh on a new branch from main; do not patch #{pr}.",
        "",
        f"What failed: {why}.",
        "",
        "Blocking findings from the reviews:",
    ]
    lines += [f"- {t}" for t in findings] or ["- (none recorded; read the PR comments)"]
    lines += [
        "",
        ("Different approach: pick another way to meet the acceptance criteria of the issue, not a patch of the old one. "
         "If the slip is too big, say so in the issue and stop."),
        "",
        "The orchestrator may rewrite this comment; the newest slip comment wins.",
    ]
    return "\n".join(lines)


def restart_issue(pr, issue, reviews, run=gh, why=None):
    """Restart the task once: restart:1, slip comment, agent:dev re-added (removed first so the label event fires)."""
    add_labels("issue", issue, [RESTART], run)
    findings = blocking_findings(reviews)
    liveness.post_comment("issue", issue, slip_comment(pr, findings, why) if why else slip_comment(pr, findings), run)
    run("issue", "edit", str(issue), "--remove-label", "agent:dev")
    add_labels("issue", issue, ["agent:dev"], run)
    run("pr", "close", str(pr), "--comment", f"Superseded: {why or 'round limit reached'}, task restarted, see #{issue}")


def handle_limit(pr, run=gh):
    """Returns 'restarted' or 'parked'."""
    info = json.loads(run("pr", "view", str(pr), "--json", "body,state,labels"))
    if info.get("state") != "OPEN":
        return "closed"
    issues = own_issues(info.get("body"))
    issue = None
    restarted = False
    for n in issues:
        labels = {x["name"] for x in json.loads(run("issue", "view", str(n), "--json", "labels"))["labels"]}
        if RESTART in labels:
            restarted = True
        elif issue is None:
            issue = n
    if issue is None or restarted:
        park("pr", pr, "review limit of 2 fix rounds reached" + (", the restart (restart:1) failed too" if restarted else ""), run)
        return "parked"
    pages = json.loads(run("api", "--paginate", "--slurp", f"repos/{_repo()}/pulls/{pr}/reviews"))
    restart_issue(pr, issue, [r for page in pages for r in page], run)
    return "restarted"


def _repo():
    return os.environ["GH_REPO"]


def main(argv):
    args = argv[1:]
    if len(args) == 2 and args[0] == "limit" and args[1].isdigit():
        print(handle_limit(args[1]))
        return 0
    if args == ["supersede"]:
        prs = json.loads(gh("pr", "list", "--state", "open", "--limit", "100", "--json",
                            "number,body,headRefName,isCrossRepository"))
        for old, new in close_superseded(prs):
            print(f"closed #{old}: superseded by #{new}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
