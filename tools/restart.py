"""Round limit: restart the task once automatically, close superseded PRs.

CLI (needs the gh CLI with GH_TOKEN and GH_REPO):
  restart.py limit PR        agent PR hit the round limit: first time restart the issue (label restart:1, slip comment,
                             agent:dev re-added, PR closed), otherwise needs-human + review request + German note
  restart.py supersede       close every open agent PR that a newer open agent PR for the same issue replaces
Environment: OWNER (default Bankaifan).
"""
import json
import os
import re
import subprocess
import sys

import liveness
from agent_guard import add_labels, same_login

OWNER_DEFAULT = "Bankaifan"
RESTART = "restart:1"
_REFS = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?|refs?)\s+#(\d+)", re.IGNORECASE)
_BLOCKING = 1500  # chars of review text per review in the slip

NOTE_RESTARTED = (
    "Hallo Daniel, dieser PR haengt fest, auch der automatische Neustart des Auftrags hat nicht gereicht "
    "(ein Neustart ist schon gelaufen). Schlimmster Fall: nichts passiert, der PR wird nur nicht gemergt. "
    "Frage: Soll der Orchestrator den Auftrag noch einmal anders schneiden (ja) oder der PR geschlossen werden (nein)?"
)


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def issue_refs(body):
    """Issue numbers named by closing keywords or `Refs` in a PR body, in order, without duplicates."""
    seen = []
    for n in _REFS.findall(body or ""):
        if int(n) not in seen:
            seen.append(int(n))
    return seen


def is_agent_branch(pr):
    return (pr.get("headRefName") or "").startswith("agent/") and not pr.get("isCrossRepository")


def superseded(prs):
    """[(old, new)] for open agent PRs whose issue is also referenced by a newer open agent PR."""
    newest = {}
    for p in prs:
        if not is_agent_branch(p):
            continue
        for n in issue_refs(p.get("body")):
            newest[n] = max(newest.get(n, 0), p["number"])
    out = {}
    for p in prs:
        if not is_agent_branch(p):
            continue
        newer = [newest[n] for n in issue_refs(p.get("body")) if newest[n] > p["number"]]
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


def slip_comment(pr, findings):
    lines = [
        f"Restart 1/1: PR #{pr} hit the limit of 2 fix rounds. Start fresh on a new branch from main; do not patch #{pr}.",
        "",
        "What failed: the developer and the reviewers did not converge in 3 reviews.",
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


def restart_issue(pr, issue, reviews, run=gh):
    """Restart the task once: restart:1, slip comment, agent:dev re-added (removed first so the label event fires)."""
    add_labels("issue", issue, [RESTART], run)
    liveness.post_comment("issue", issue, slip_comment(pr, blocking_findings(reviews)), run)
    run("issue", "edit", str(issue), "--remove-label", "agent:dev")
    add_labels("issue", issue, ["agent:dev"], run)
    run("pr", "close", str(pr), "--comment", f"Superseded: round limit reached, task restarted, see #{issue}")


def park_with_owner(pr, owner, restarted, run=gh):
    """Today's path: needs-human, review request to the owner (unless author), limit comment with the German note."""
    add_labels("pr", pr, ["needs-human"], run)
    author = json.loads(run("pr", "view", str(pr), "--json", "author"))["author"]["login"]
    if not same_login(author, owner):
        try:
            run("pr", "edit", str(pr), "--add-reviewer", owner)
        except subprocess.CalledProcessError:
            print("review request failed")
    text = "Review limit of 2 fix rounds reached. Needs the orchestrator or Daniel."
    if restarted:
        text += "\n\nThe automatic restart (restart:1) already failed too.\n\n" + NOTE_RESTARTED
    liveness.post_comment("pr", pr, text, run)


def handle_limit(pr, owner, run=gh):
    """Returns 'restarted' or 'parked'."""
    info = json.loads(run("pr", "view", str(pr), "--json", "body,state,labels"))
    if info.get("state") != "OPEN":
        return "closed"
    issues = issue_refs(info.get("body"))
    issue = None
    restarted = False
    for n in issues:
        labels = {x["name"] for x in json.loads(run("issue", "view", str(n), "--json", "labels"))["labels"]}
        if RESTART in labels:
            restarted = True
        elif issue is None:
            issue = n
    if issue is None or restarted:
        park_with_owner(pr, owner, restarted, run)
        return "parked"
    pages = json.loads(run("api", "--paginate", "--slurp", f"repos/{_repo()}/pulls/{pr}/reviews"))
    restart_issue(pr, issue, [r for page in pages for r in page], run)
    return "restarted"


def _repo():
    return os.environ["GH_REPO"]


def main(argv):
    owner = os.environ.get("OWNER", OWNER_DEFAULT)
    args = argv[1:]
    if len(args) == 2 and args[0] == "limit" and args[1].isdigit():
        print(handle_limit(args[1], owner))
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
