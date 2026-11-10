"""Count work for a model run with no model; write `work=true|false` to $GITHUB_OUTPUT.

Usage: python3 prefilter.py orchestrator|scout
Needs the gh CLI (GH_TOKEN, GH_REPO) and git history. Environment: OWNER (default Bankaifan),
IDEAS (scout, issues per run), STALE_DAYS (default 7), TRUSTED (orchestrator, JSON from trusted_issues.py).
The Claude step runs only when `work=true`; the counts are printed to the log.
"""
import json
import os
import re
import subprocess
import sys
import time

import train

MAX_DEV = 2
MAX_PRS = 3
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


def handover_stale(age_days, newer_commits, stale_days):
    """HANDOVER.md is stale if it is old and main moved on since."""
    return age_days >= stale_days and newer_commits > 0


def orchestrator_work(candidates, needs_human, stale):
    return bool(candidates) or needs_human > 0 or stale


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
        cands = startable(trusted, dev_open, stuck_slots() if dev_open - w_dev >= MAX_DEV else 0, w_dev, w_prs)
        human = count("pr", "list", "--state", "open", "--label", "needs-human")
        age, newer = handover_state()
        stale = handover_stale(age, newer, float(os.environ.get("STALE_DAYS", "7")))
        work = orchestrator_work(cands, human, stale)
        print(f"dev_open={dev_open} waiting_prs={w_prs} free_dev={free_dev} free_prs={free_prs} candidates={cands} needs_human_prs={human} "
              f"handover_age_days={age:.1f} commits_since={newer} stale={stale} work={work}")
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
                f.write(f"startable={str(bool(cands)).lower()}\n")
                f.write(f"free_dev={free_dev}\nfree_prs={free_prs}\nwaiting_prs={w_prs}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
