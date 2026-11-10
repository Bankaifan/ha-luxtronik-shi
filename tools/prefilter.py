"""Count work for a model run with no model; write `work=true|false` to $GITHUB_OUTPUT.

Usage: python3 prefilter.py orchestrator|scout
Needs the gh CLI (GH_TOKEN, GH_REPO) and git history. Environment: OWNER (default Bankaifan),
IDEAS (scout, issues per run), STALE_DAYS (default 7), TRUSTED (orchestrator, JSON from trusted_issues.py),
MAX_DEV (agent:dev issues at once, default 2) and MAX_PRS (open agent PRs, default 3). An empty or non-numeric
MAX_DEV/MAX_PRS falls back to the default (a warning goes to stderr).
Orchestrator events (design 0007 4.3): EVENT, EVENT_ACTION, EVENT_NUMBER (issue or PR), EVENT_SENDER, EVENT_MERGED,
REVIEW_STATE, REVIEWER. With an EVENT the table row decides `work`; without a row (schedule, dispatch) the counts do.
The Claude step runs only when `work=true`; the counts and `reason` are printed to the log.
"""
import json
import os
import re
import subprocess
import sys
import time

import train


def env_cap(name, default):
    """Integer from the environment; empty or non-numeric falls back to the default (warning on stderr)."""
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"{name}={raw!r} is not a number, using {default}", file=sys.stderr)
        return default


MAX_DEV = env_cap("MAX_DEV", 2)  # open agent:dev issues (agent jobs at once)
MAX_PRS = env_cap("MAX_PRS", 3)  # open agent PRs
MAX_OPEN_IDEAS = 10


def closing_issues(body):
    return {int(n) for n in re.findall(r"(?:Closes|Refs) #(\d+)\b", body or "")}


def free_slots(dev_open, open_prs, waiting_issues, waiting_prs):
    """(free agent:dev slots, free PR slots). Issues and PRs waiting only for the owner do not count against the caps."""
    return (max(0, MAX_DEV - (dev_open - waiting_issues)), max(0, MAX_PRS - (open_prs - waiting_prs)))


def startable(trusted, dev_open, stuck=0, waiting=0, waiting_prs=0):
    """Trusted issues the orchestrator could start: no agent:dev yet, ideas only when approved/auto-ok.
    `stuck` = open agent:dev issues with a merged PR or needs-human; they must not block a prio:1 issue.
    `waiting` = open agent:dev issues whose PR waits only for the owner: they free their slot (not for prio:1 beyond
    the existing stuck rule). At MAX_WAITING waiting PRs (`waiting_prs`) new risk:security slips wait."""
    dev_open = max(0, dev_open - waiting)
    out = []
    for item in trusted:
        if waiting_prs >= train.MAX_WAITING and "risk:security" in item["labels"]:
            continue
        if dev_open >= MAX_DEV and not (item.get("prio") == 1 and dev_open - stuck < MAX_DEV):
            continue
        labels = set(item["labels"])
        if "agent:dev" in labels or "needs-human" in labels:
            continue
        if "idea" in labels and not (item["approved"] or item["auto_ok"]):
            continue
        out.append(item["number"])
    return out


def start_candidates(trusted, dev_open, free_prs, stuck=0, waiting=0, waiting_prs=0):
    """What the orchestrator may start. No free PR slot means nothing (the prompt says so), and the guard reads
    STARTABLE=true with no visible action as a silent run: the same rule as `event_facts`, not only the dev slots."""
    if free_prs <= 0:
        return []
    return startable(trusted, dev_open, stuck, waiting, waiting_prs)


def handover_stale(age_days, newer_commits, stale_days):
    """HANDOVER.md is stale if it is old and main moved on since."""
    return age_days >= stale_days and newer_commits > 0


def orchestrator_work(candidates, needs_human, stale):
    return bool(candidates) or needs_human > 0 or stale


def event_reason(event, action, f):
    """(work, reason) for one event, per design 0007 section 4.3; None for events without a row (schedule, dispatch,
    validate on main): those keep the count rule. F is a dict of facts, see `event_facts`. No row fits -> (False, "no-match")."""
    row = (event, action)
    if event == "issues" and action in ("opened", "edited", "labeled"):
        if f["startable"]:
            return True, "startable-issue"
        if f["needs_human"] and f["sender_is_owner"]:
            return True, "owner-reply"
    elif row == ("issues", "closed"):
        if f["agent_dev"] or f["linked_open_pr"]:
            return True, "cleanup-closed-issue"
    elif row == ("issue_comment", "created"):
        if f["needs_human"] and f["sender_is_owner"] and not f["receiver_marker"]:
            return True, "owner-answer"
        if f["trusted"] and f["sender_is_owner"]:
            return True, "owner-comment-trusted"
    elif row == ("pull_request", "opened"):
        if f["agent_pr"] and f["free_prs"] <= 0:
            return True, "pr-over-cap"
        if f["design_pr"]:
            return True, "design-pr"
        if not f["agent_pr"] and not f["closing"]:
            return True, "unlinked-pr"
    elif row == ("pull_request", "closed"):
        if f["merged"] and (f["design_pr"] or f["closing_agent_dev"]):
            return True, "merged-pr"
        if not f["merged"] and f["closing"]:
            return True, "closed-unmerged-pr"
    elif row == ("pull_request_review", "submitted"):
        if f["review_state"] in ("CHANGES_REQUESTED", "APPROVED") and f["reviewer_ok"] and f["agent_pr"]:
            return True, "review"
    else:
        return None
    return False, "no-match"


def event_facts(event, number, free_prs, trusted_numbers, owner, approver):
    """Facts for `event_reason`, read live for NUMBER (issue or PR) with the gh CLI. Environment: EVENT_SENDER,
    EVENT_MERGED (true|false), REVIEW_STATE and REVIEWER (pull_request_review). Nothing here comes from comment text."""
    sender, reviewer = os.environ.get("EVENT_SENDER", ""), os.environ.get("REVIEWER", "")
    f = {"startable": False, "needs_human": False, "agent_dev": False, "linked_open_pr": False, "trusted": False,
         "receiver_marker": False, "agent_pr": False, "design_pr": False, "closing": set(), "closing_agent_dev": False,
         "merged": os.environ.get("EVENT_MERGED", "").lower() == "true", "free_prs": free_prs,
         "review_state": os.environ.get("REVIEW_STATE", ""), "sender_is_owner": sender.lower() == owner.lower(),
         "reviewer_ok": bool(reviewer) and reviewer.lower() in (owner.lower(), approver.lower())}
    if not number:
        return f
    if event.startswith("pull_request"):
        pr = json.loads(gh("pr", "view", str(number), "--json", "labels,body,title,headRefName"))
        names = {lab["name"] for lab in pr["labels"]}
        f["agent_pr"] = pr["headRefName"].startswith("agent/")
        f["design_pr"] = "design" in names or pr["title"].lower().startswith("design")
        f["closing"] = closing_issues(pr["body"])
        for n in f["closing"]:
            issue = json.loads(gh("issue", "view", str(n), "--json", "labels"))
            f["closing_agent_dev"] |= any(lab["name"] == "agent:dev" for lab in issue["labels"])
        return f
    issue = json.loads(gh("issue", "view", str(number), "--json", "labels,comments"))
    names = {lab["name"] for lab in issue["labels"]}
    f["needs_human"], f["agent_dev"] = "needs-human" in names, "agent:dev" in names
    f["trusted"] = number in trusted_numbers
    f["startable"] = number in trusted_numbers and free_prs > 0 and not (names & {"agent:dev", "needs-human"})
    comments = issue["comments"]
    f["receiver_marker"] = bool(comments) and "<!-- answer-receiver" in (comments[-1].get("body") or "")
    prs = json.loads(gh("pr", "list", "--state", "open", "--search", f"#{number} in:body", "--json", "number,body"))
    f["linked_open_pr"] = any(number in closing_issues(p.get("body")) for p in prs)
    return f


def scout_work(open_ideas, ideas_per_run):
    return ideas_per_run > 0 and open_ideas < MAX_OPEN_IDEAS


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def stuck_slots():
    """Open agent:dev issues that are stuck: needs-human, or a merged PR mentions them."""
    n = 0
    for i in json.loads(gh("issue", "list", "--state", "open", "--label", "agent:dev", "--limit", "50",
                           "--json", "number,labels")):
        if any(lab["name"] == "needs-human" for lab in i["labels"]):
            n += 1
            continue
        merged = json.loads(gh("pr", "list", "--state", "merged", "--search", f"#{i['number']} in:body",
                               "--limit", "5", "--json", "number,body"))
        if any(re.search(rf"(?:Closes|Refs) #{i['number']}\b", p.get("body") or "") for p in merged):
            n += 1
    return n


def waiting_for_owner(owner, approver):
    """(issue numbers, PR count) of PRs waiting only for the owner; see train.waiting_for_owner."""
    prs = json.loads(gh("pr", "list", "--state", "open", "--limit", "20", "--json", train.LIST_FIELDS + ",body"))
    repo = os.environ["GH_REPO"]
    issues, n = set(), 0
    for p in prs:
        if not (train.status.is_agent_pr(p) and "risk:security" in train.status.names(p)):
            continue
        pages = json.loads(gh("api", "--paginate", "--slurp", f"repos/{repo}/pulls/{p['number']}/reviews"))
        if train.waiting_for_owner(p, [r for page in pages for r in page], approver, owner):
            n += 1
            issues |= closing_issues(p.get("body"))
    return issues, n


def count(*args):
    return len(json.loads(gh(*args, "--limit", "200", "--json", "number")))


def handover_state():
    sha = git("log", "-1", "--format=%H %ct", "--", "HANDOVER.md")
    if not sha:
        return 9999, 1
    commit, ts = sha.split()
    newer = int(git("rev-list", "--count", f"{commit}..HEAD"))
    return (time.time() - int(ts)) / 86400, newer


def main(mode) -> int:
    if mode == "orchestrator":
        dev_open = count("issue", "list", "--state", "open", "--label", "agent:dev")
        w_issues, w_prs = waiting_for_owner(os.environ.get("OWNER", "Bankaifan"), os.environ.get("APPROVER_BOT", ""))
        w_dev = sum(1 for i in json.loads(gh("issue", "list", "--state", "open", "--label", "agent:dev",
                                             "--limit", "50", "--json", "number")) if i["number"] in w_issues)
        free_dev, free_prs = free_slots(dev_open, count("pr", "list", "--state", "open"), w_dev, w_prs)
        trusted = json.loads(os.environ.get("TRUSTED") or subprocess.run(
            [sys.executable, "tools/trusted_issues.py"], check=True, capture_output=True, text=True).stdout)
        cands = start_candidates(trusted, dev_open, free_prs, stuck_slots() if dev_open - w_dev >= MAX_DEV else 0,
                                 w_dev, w_prs)
        human = count("pr", "list", "--state", "open", "--label", "needs-human")
        age, newer = handover_state()
        stale = handover_stale(age, newer, float(os.environ.get("STALE_DAYS", "7")))
        work, reason = orchestrator_work(cands, human, stale), "counts"
        event, action = os.environ.get("EVENT", ""), os.environ.get("EVENT_ACTION", "")
        verdict = None
        if event:
            facts = event_facts(event, env_cap("EVENT_NUMBER", 0), free_prs, {t["number"] for t in trusted},
                                os.environ.get("OWNER", "Bankaifan"), os.environ.get("APPROVER_BOT", ""))
            verdict = event_reason(event, action, facts)
        if verdict:
            work, reason = verdict
        print(f"dev_open={dev_open} waiting_prs={w_prs} free_dev={free_dev} free_prs={free_prs} candidates={cands} needs_human_prs={human} "
              f"handover_age_days={age:.1f} commits_since={newer} stale={stale} event={event or '-'}/{action or '-'} "
              f"reason={reason} work={work}")
    elif mode == "scout":
        ideas = count("issue", "list", "--state", "open", "--label", "idea")
        work = scout_work(ideas, int(os.environ.get("IDEAS", "3")))
        print(f"open_ideas={ideas} work={work}")
    else:
        print(__doc__, file=sys.stderr)
        return 2
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"work={str(work).lower()}\n")
            if mode == "orchestrator":
                f.write(f"startable={str(bool(cands)).lower()}\nreason={reason}\n")
                f.write(f"free_dev={free_dev}\nfree_prs={free_prs}\nwaiting_prs={w_prs}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
