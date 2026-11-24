"""Count work for a model run with no model; write `work=true|false` to $GITHUB_OUTPUT.

Usage: python3 prefilter.py orchestrator|scout
Needs the gh CLI (GH_TOKEN, GH_REPO) and git history. Environment: OWNER (default Bankaifan),
IDEAS (scout, issues per run), STALE_DAYS (default 7), TRUSTED (orchestrator, JSON from trusted_issues.py),
MAX_DEV (agent:dev issues at once, default 4), MAX_PRS (open agent PRs, default 5) and DISPATCH (`on`: the model only
gets issues without a slip (`needs_slip`) and a handover that is due; design 0015). An empty or non-numeric
MAX_DEV/MAX_PRS falls back to the default (a warning goes to stderr).
Slots: an open agent:dev issue holds one unless it is parked, done (a merged PR names it) or waits
only for the owner. Output `start` = the issues to start now: unblocked candidates (`deps.py`), at most `free_dev`.
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

import deps
import overlap
import slip
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


MAX_DEV = env_cap("MAX_DEV", 4)  # open agent:dev issues (agent jobs at once)
MAX_PRS = env_cap("MAX_PRS", 5)  # open agent PRs
MAX_OPEN_IDEAS = 10


def closing_issues(body):
    return {int(n) for n in re.findall(r"(?:Closes|Refs) #(\d+)\b", body or "")}


def free_slots(dev, waiting, stuck, open_prs, waiting_prs):
    """(free agent:dev slots, free PR slots). DEV, WAITING, STUCK are sets of issue numbers: an open agent:dev issue
    holds a slot unless its PR waits only for the owner or it is stuck (`stuck_slots`). PRs waiting only for the
    owner do not count against MAX_PRS."""
    return (max(0, MAX_DEV - len(set(dev) - set(waiting) - set(stuck))), max(0, MAX_PRS - (open_prs - waiting_prs)))


def startable(trusted, free_dev, waiting_prs=0, blocked=()):
    """Trusted issues the orchestrator could start, in list order: no agent:dev yet, never an `idea` (intake turns it into a slip),
    not in BLOCKED (an open `Depends on:` issue). At MAX_WAITING waiting PRs (`waiting_prs`) new risk:security slips wait."""
    if free_dev <= 0:
        return []
    out = []
    for item in trusted:
        if waiting_prs >= train.MAX_WAITING and "risk:security" in item["labels"]:
            continue
        labels = set(item["labels"])
        if "agent:dev" in labels or "parked" in labels or item["number"] in blocked:
            continue
        if "idea" in labels:
            continue
        out.append(item["number"])
    return out


def start_candidates(trusted, free_dev, free_prs, waiting_prs=0, blocked=()):
    """What the orchestrator starts in this run: the startable issues that fit the free agent:dev and PR slots. No free PR
    slot means nothing (the prompt says so), and the guard reads STARTABLE=true with no visible action as a silent
    run: the same rule as `event_facts`, not only the dev slots."""
    if free_prs <= 0:
        return []
    return startable(trusted, free_dev, waiting_prs, blocked)[:min(free_dev, free_prs)]


def handover_stale(age_days, newer_commits, stale_days):
    """HANDOVER.md is stale if it is old and main moved on since."""
    return age_days >= stale_days and newer_commits > 0


def orchestrator_work(candidates, stale, needs_slip=None):
    """Does the model have a job? NEEDS_SLIP None = dispatcher off: any start candidate is a job. A list (DISPATCH=on,
    design 0015): only candidates without a slip are, the script starts the rest. Parked items are no job: the
    unblocker and the un-park of status.py handle them without the orchestrator."""
    if needs_slip is not None:
        return bool(needs_slip) or stale
    return bool(candidates) or stale


def event_reason(event, action, f):
    """(work, reason) for one event, per design 0007 section 4.3; None for events without a row (schedule, dispatch,
    validate on main): those keep the count rule. F is a dict of facts, see `event_facts`. No row fits -> (False, "no-match").
    The train's batch (decision 0018) is script work: its PR until it merges, and a member closed as landed, wake nobody."""
    row = (event, action)
    if f.get("batched") and not f["merged"]:
        return False, "batch"
    if event == "issues" and action in ("opened", "edited", "labeled"):
        if f["startable"]:
            return True, "startable-issue"
    elif row == ("issues", "closed"):
        if f["agent_dev"] or f["linked_open_pr"]:
            return True, "cleanup-closed-issue"
    elif row == ("issue_comment", "created"):
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
        if f["merged"] and (f["design_pr"] or (f["closing_agent_dev"] and not f.get("dispatch"))):  # dispatch.py removes the label
            return True, "merged-pr"
        if not f["merged"] and f["closing"]:
            return True, "closed-unmerged-pr"
    elif row == ("pull_request_review", "submitted"):
        if f["review_state"] in ("CHANGES_REQUESTED", "APPROVED") and f["reviewer_ok"] and f["agent_pr"]:
            return True, "review"
    else:
        return None
    return False, "no-match"


def event_facts(event, number, free_prs, trusted_numbers, owner, approver, start=()):
    """Facts for `event_reason`, read live for NUMBER (issue or PR) with the gh CLI. Environment: EVENT_SENDER,
    EVENT_MERGED (true|false), REVIEW_STATE and REVIEWER (pull_request_review). Nothing here comes from comment text."""
    sender, reviewer = os.environ.get("EVENT_SENDER", ""), os.environ.get("REVIEWER", "")
    f = {"startable": False, "agent_dev": False, "linked_open_pr": False, "trusted": False, "agent_pr": False, "design_pr": False, "closing": set(), "closing_agent_dev": False,
         "merged": os.environ.get("EVENT_MERGED", "").lower() == "true", "free_prs": free_prs,
         "review_state": os.environ.get("REVIEW_STATE", ""), "sender_is_owner": sender.lower() == owner.lower(),
         "reviewer_ok": bool(reviewer) and reviewer.lower() in (owner.lower(), approver.lower())}
    if not number:
        return f
    if event.startswith("pull_request"):
        pr = json.loads(gh("pr", "view", str(number), "--json", "labels,body,title,headRefName,comments,state,isCrossRepository"))
        f["batched"] = (pr["headRefName"] == train.BATCH_BRANCH and not pr.get("isCrossRepository")) or landed_in_batch(pr)
        names = {lab["name"] for lab in pr["labels"]}
        f["agent_pr"] = pr["headRefName"].startswith("agent/")
        f["design_pr"] = "design" in names or pr["title"].lower().startswith("design")
        f["closing"] = closing_issues(pr["body"])
        for n in f["closing"]:
            issue = json.loads(gh("issue", "view", str(n), "--json", "labels"))
            f["closing_agent_dev"] |= any(lab["name"] == "agent:dev" for lab in issue["labels"])
        return f
    issue = json.loads(gh("issue", "view", str(number), "--json", "labels"))
    f["agent_dev"] = any(lab["name"] == "agent:dev" for lab in issue["labels"])
    f["trusted"] = number in trusted_numbers
    f["startable"] = number in start  # the start list of this run: trusted, unblocked, within the free slots
    prs = json.loads(gh("pr", "list", "--state", "open", "--search", f"#{number} in:body", "--json", "number,body"))
    f["linked_open_pr"] = any(number in closing_issues(p.get("body")) for p in prs)
    return f


def scout_work(open_ideas, ideas_per_run):
    return ideas_per_run > 0 and open_ideas < MAX_OPEN_IDEAS


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def stuck_slots(dev):
    """Numbers of the open agent:dev issues in DEV (number, labels) that are stuck: parked, or a merged PR
    mentions them. They hold no slot. Only same-repo `agent/` PRs count: anyone can write `Refs #N` into a PR body."""
    out = set()
    for i in dev:
        if any(lab["name"] == "parked" for lab in i["labels"]):
            out.add(i["number"])
            continue
        merged = json.loads(gh("pr", "list", "--state", "merged", "--search", f"#{i['number']} in:body",
                               "--limit", "5", "--json", "number,body,headRefName,isCrossRepository"))
        if any(i["number"] in closing_issues(p.get("body")) for p in merged
               if p.get("headRefName", "").startswith("agent/") and not p.get("isCrossRepository")):
            out.add(i["number"])
    return out


def waiting_blocker(comments, authors=overlap.DEFAULT_TRUSTED):
    """N when the last comment by a trusted author is `Waiting for #N` (a run parked on a denied tool call), else None."""
    mine = [c for c in comments or [] if (c.get("author") or {}).get("login") in authors]
    m = re.match(r"Waiting for #(\d+)\b", (mine[-1].get("body") or "") if mine else "")
    return int(m.group(1)) if m else None


def batched(comments, authors=overlap.DEFAULT_TRUSTED):
    """N when the last comment by a trusted author is the train's `Merged with #N.` (tools/train.py, decision 0018),
    else None. The developer model posts as the same app, so the text alone proves nothing: see `landed_in_batch`."""
    mine = [c for c in comments or [] if (c.get("author") or {}).get("login") in authors]
    m = re.fullmatch(r"Merged with #(\d+)\.", (mine[-1].get("body") or "").strip()) if mine else None
    return int(m.group(1)) if m else None


def landed_in_batch(pr, gh=gh):
    """True when PR (state, comments) was closed because its change landed in a batch: it is closed, its last trusted
    comment is `Merged with #N.` and #N really is a merged same-repo PR from the batch branch."""
    n = batched(pr.get("comments")) if pr.get("state") == "CLOSED" else None
    if not n:
        return False
    batch = json.loads(gh("pr", "view", str(n), "--json", "state,headRefName,isCrossRepository"))
    return (batch.get("state") == "MERGED" and batch.get("headRefName") == train.BATCH_BRANCH
            and not batch.get("isCrossRepository"))


def parked_waiting(dev, gh=gh):
    """(parked, ready) for the open agent:dev issues in DEV (number, labels, comments) that wait for a blocker.
    PARKED: numbers whose blocker is still open, they hold no slot. READY: {number: blocker} with the blocker closed,
    the dispatcher restarts them (`dispatch.restart_waiting`)."""
    parked, ready = set(), {}
    for i in dev:
        blocker = waiting_blocker(i.get("comments"))
        if blocker is None:
            continue
        if json.loads(gh("issue", "view", str(blocker), "--json", "state"))["state"] == "OPEN":
            parked.add(i["number"])
        else:
            ready[i["number"]] = blocker
    return parked, ready


def waiting_for_owner(owner, approver):
    """(issue numbers, PR count) of PRs waiting only for the owner; see train.waiting_for_owner."""
    prs = json.loads(gh("pr", "list", "--state", "open", "--limit", "20", "--json", train.LIST_FIELDS))
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


def pipeline_prs(owner=None):
    """Open PRs that hold a slot of MAX_PRS: same-repo `agent/` PRs the agents opened. Not counted: the owner's own
    PRs (also on an `agent/` branch), the train's batch and release PRs, template sync and dependabot PRs. Seven PRs
    opened by hand filled the cap and the dispatcher started nothing for a night."""
    owner = os.environ.get("OWNER", "Bankaifan") if owner is None else owner
    prs = json.loads(gh("pr", "list", "--state", "open", "--limit", "200", "--json",
                        "number,headRefName,isCrossRepository,author"))
    return sum(1 for p in prs if train.status.is_agent_pr(p)
               and not train.status.same_login((p.get("author") or {}).get("login"), owner))


def count(*args):
    return len(json.loads(gh(*args, "--limit", "200", "--json", "number")))


def handover_state():
    sha = git("log", "-1", "--format=%H %ct", "--", "HANDOVER.md")
    if not sha:
        return 9999, 1
    commit, ts = sha.split()
    newer = int(git("rev-list", "--count", f"{commit}..HEAD"))
    return (time.time() - int(ts)) / 86400, newer


def slip_time(issue, authors):
    """ISO time of the newest trusted slip of ISSUE: the newest trusted comment with a `Files:` line, else the body."""
    times = [c.get("createdAt", "") for c in issue.get("comments", [])
             if overlap.trusted(c, authors) and overlap.parse_files(c.get("body") or "")]
    return max(times) if times else issue.get("createdAt", "")


NOTHING_MARK = "<!-- nothing-to-build -->"  # tools/no_build.py: a developer run found the slip already done


def nothing_to_build(issue, authors):
    """A trusted `nothing-to-build` comment is newer than the newest slip: that slip leads to an empty run."""
    since = slip_time(issue, authors)
    return any(NOTHING_MARK in (c.get("body") or "") and overlap.trusted(c, authors) and c.get("createdAt", "") > since
               for c in issue.get("comments", []))


def step_landed(n, issue, authors, gh=None):
    """True when a same-repo `agent/` PR naming issue N merged after its newest slip (issue #661), or a developer
    run said after that slip that there is nothing to build (`nothing_to_build`): the slip's step is done and a
    restart from it would only produce an empty run."""
    if nothing_to_build(issue, authors):
        return True
    run = gh or globals()["gh"]  # the module's gh at call time, so a test can replace it
    out = run("pr", "list", "--state", "merged", "--search", f"#{n} in:body", "--limit", "20",
              "--json", "body,headRefName,isCrossRepository,mergedAt")
    since = slip_time(issue, authors)
    return any(p.get("mergedAt", "") > since and n in closing_issues(p.get("body"))
               for p in json.loads(out or "[]")
               if p.get("headRefName", "").startswith("agent/") and not p.get("isCrossRepository"))


def needs_slip(start, authors=overlap.DEFAULT_TRUSTED):
    """The issues of START only the model can move: they carry no slip yet (`slip.py`), or the step of their newest
    slip is merged (`step_landed`) and the issue is still open. The dispatcher passes both kinds over; without the
    second kind such an issue stayed in the start list for ever and every orchestrator run ended silently (#743)."""
    out = []
    for n in start:
        issue = json.loads(gh("issue", "view", str(n), "--json", "body,author,comments,createdAt"))
        if not slip.has_slip(issue, authors) or step_landed(n, issue, authors):
            out.append(n)
    return out


def handover_done_today():
    """True when a handover PR (open or merged) for today's UTC date exists: at most one per day."""
    day = time.strftime("%F", time.gmtime())
    prs = json.loads(gh("pr", "list", "--state", "all", "--search", f"head:agent/orchestrator-handover-{day}",
                        "--json", "number"))
    return bool(prs)


def first_failure(issue):
    """A `Failing workflow:` issue after ONE failed run (tools/failure_watch.py writes `Failures: 1`): often a blip such
    as the API rate limit. It starts no developer; a second failure does, a green run closes it. `prio:1` is exempt:
    a red main or a rarely scheduled workflow may never get its second run."""
    labels = {lab.get("name") for lab in issue.get("labels") or []}
    return ((issue.get("title") or "").startswith("Failing workflow: ") and "prio:1" not in labels
            and bool(re.search(r"^Failures: 1$", issue.get("body") or "", re.MULTILINE)))


def start_state():
    """Slots and start list, read live (one definition for prefilter and dispatch): a dict with dev, stuck, waiting_prs,
    free_dev, free_prs, trusted (JSON of trusted_issues.py), blocked, restart ({issue: closed blocker} of parked
    agent:dev issues) and start (the issues to start now)."""
    dev = json.loads(gh("issue", "list", "--state", "open", "--label", "agent:dev", "--limit", "200",
                        "--json", "number,labels,comments"))
    w_issues, w_prs = waiting_for_owner(os.environ.get("OWNER", "Bankaifan"), os.environ.get("APPROVER_BOT", ""))
    parked, restart = parked_waiting(dev)
    stuck = stuck_slots(dev) | parked  # an issue waiting for an open blocker holds no slot
    free_dev, free_prs = free_slots({i["number"] for i in dev}, w_issues, stuck, pipeline_prs(), w_prs)
    trusted = json.loads(os.environ.get("TRUSTED") or subprocess.run(
        [sys.executable, "tools/trusted_issues.py"], check=True, capture_output=True, text=True).stdout)
    issues = json.loads(gh("issue", "list", "--state", "open", "--limit", "200", "--json", "number,body,title,labels"))
    open_numbers = {i["number"] for i in issues}
    blocked = {i["number"] for i in issues if deps.blocked(i["number"], i.get("body"), open_numbers)}
    blocked |= {i["number"] for i in issues if first_failure(i)}
    return {"dev": dev, "stuck": stuck, "restart": restart, "waiting_prs": w_prs, "free_dev": free_dev, "free_prs": free_prs,
            "trusted": trusted, "blocked": blocked,
            "start": start_candidates(trusted, free_dev, free_prs, w_prs, blocked),
            # the dispatcher walks the whole startable list (slip check first) and stops at LIMIT starts
            "startable": startable(trusted, free_dev, w_prs, blocked) if free_prs > 0 else [],
            "limit": min(free_dev, free_prs)}


def main(mode) -> int:
    if mode == "orchestrator":
        st = start_state()
        dev, stuck, w_prs, free_dev, free_prs = st["dev"], st["stuck"], st["waiting_prs"], st["free_dev"], st["free_prs"]
        trusted, blocked, cands = st["trusted"], st["blocked"], st["start"]
        age, newer = handover_state()
        stale = handover_stale(age, newer, float(os.environ.get("STALE_DAYS", "7")))
        dispatch = os.environ.get("DISPATCH") == "on"  # design 0015: dispatch.py starts issues that hold a slip
        slipless = needs_slip(cands) if dispatch else None
        handover_due = stale and not (dispatch and handover_done_today())
        work, reason = orchestrator_work(cands, handover_due, slipless), "counts"
        event, action = os.environ.get("EVENT", ""), os.environ.get("EVENT_ACTION", "")
        verdict = None
        if event:
            facts = event_facts(event, env_cap("EVENT_NUMBER", 0), free_prs, {t["number"] for t in trusted},
                                os.environ.get("OWNER", "Bankaifan"), os.environ.get("APPROVER_BOT", ""),
                                cands if slipless is None else slipless)
            facts["dispatch"] = dispatch
            verdict = event_reason(event, action, facts)
        if verdict:
            work, reason = verdict
        print(f"dev_open={len(dev)} stuck={sorted(stuck)} waiting_prs={w_prs} free_dev={free_dev} free_prs={free_prs} "
              f"blocked={sorted(blocked)} start={cands} "
              f"handover_age_days={age:.1f} commits_since={newer} stale={stale} event={event or '-'}/{action or '-'} "
              f"needs_slip={slipless} handover_due={handover_due} reason={reason} work={work}")
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
                # What the silent-run guard expects an action for. Dispatcher on: the model starts nothing, its only
                # visible job is a slip comment, so an issue the dispatcher will start by itself is not "startable".
                mine = cands if slipless is None else slipless
                f.write(f"startable={str(bool(mine)).lower()}\nstart={','.join(map(str, cands))}\nreason={reason}\n")
                f.write(f"needs_slip={','.join(map(str, slipless or []))}\nhandover_due={str(handover_due).lower()}\n")
                f.write(f"free_dev={free_dev}\nfree_prs={free_prs}\nwaiting_prs={w_prs}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
