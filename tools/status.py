"""Model-free status run: keeps the issue "Agent status" up to date and un-sticks agent work.

1. Status issue (pinned, updated in place): running agent jobs, PRs and their state, agent:dev issues and
   their age, last orchestrator run, open ideas.
2. Orphans: an agent:dev issue with no running job and no open PR for more than 30 min, or an agent PR whose head
   has no validate run for more than 10 min. First time: re-trigger and label `status:retriggered`;
   second time: parked (label and one comment).
3. Held runs: runs in `action_required` are approved only if the head belongs to an open same-repo PR of the author app.
4. Merge conflicts: an agent PR with mergeStateStatus DIRTY gets one fix run per head (marker conflict:<sha7>, then
   agent-fix is dispatched with the PR number). A conflict is no review round. A parked PR that is green and
   approved at its head and touches no CODEOWNERS path loses the label.
5. Exhausted rounds: an open agent PR with `review:stop` or 8 rounds (`review:8`), not approved, not parked, no agent job running and an
   idle head for more than 30 min was never handed over (the limit step failed): restart.py limit hands it over
   (issue restart once, else parked). A failure parks the PR.
6. Red main: an own agent PR (one commit, author OWNER, behind main) whose last validate failed while main was red
   is rebased onto main (`gh pr update-branch --rebase`) once main is green again, so CI runs again. Never merges.
Read-only except: the status issue, re-triggers, run approvals, the fix dispatch and these labels:
agent:dev (re-add), status:retriggered, review:N, parked, restart:1 (via restart.py), stalled:1 (via stalled_dev.py). Needs the gh CLI (GH_TOKEN, GH_REPO).

CLI: status.py gate   write run=true|false to $GITHUB_OUTPUT (schedule ticks honour STATUS_INTERVAL)
     status.py        do the run
7. Failure watch (tools/failure_watch.py, design 0008): after the overdue block; FAILURE_WATCH=off skips it; the
   anchor is kept in the status issue line `Failure watch since:`. An error in it never stops the status issue.
8. Design parents (tools/design_parents.py, issue #335): an open design parent whose split issues are all closed as
   completed by a merged PR is closed (prio:* and agent:dev removed, one comment). Nothing else is touched.
9. Stalled agent:dev issues (tools/stalled_dev.py, issue #366): no open PR closes it, no agent-dev run covers it, label
   older than 60 min: agent:dev set again once (stalled:1); a second stall is parked.
10. Un-park: an open issue or agent PR whose `parked` label is older than its cool-down (24 h, doubled per park
   comment, at most 7 days) gets a fresh start: `parked` and every counter label removed; an issue gets agent:dev
   again, an agent PR is closed and its issue restarted from current main. Nobody is asked, ever.
Environment: REPORT_ISSUES (off = no status issue: the text goes to the run summary, an open issue is closed; the
failure watch then anchors on the last successful status run), OWNER (default Bankaifan), AUTHOR_BOT, FAILURE_WATCH (off = skip the failure watch), STATUS_INTERVAL (minutes, default 30 public / 60 private repos;
rounded up to a multiple of 30), EVENT, PRIVATE ("true" for a private repo).
Prints numbers and titles, never tokens.
"""
import datetime
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci"))
import budget
import design_parents
import failure_watch
import flow
import ghcall
import liveness
import restart
import risk
import ruleset
import stalled_dev
from agent_guard import (
    MAX_ROUNDS,
    PARK_MARK,
    STATUS_TITLE,
    STOP,
    add_labels,
    park,
    round_no,
    same_login,
    status_issue,
    tail_text,
)
from approval import effective_approval, security_verdict
from restart import close_superseded, handle_limit, superseded

TITLE = STATUS_TITLE
OWNER_DEFAULT = "Bankaifan"
PARKED = "parked"  # set aside after failed approaches; retried later with fresh context, never handed to the owner
ISSUE_ORPHAN_MIN = 30
PR_ORPHAN_MIN = 10
LIMIT_IDLE_MIN = 30
RETRIGGER = "status:retriggered"
AGENT_WORKFLOWS = {"agent-dev", "agent-fix", "agent-review", "orchestrator", "scout", "rule-keeper"}
TICK_MIN = 30
SELF_WORKFLOW = "status.yml"  # the failure watch of this run skips its own workflow
SINCE_LABEL = "Failure watch since:"
PR_LIMIT = 20  # 50 made the GraphQL query exceed 500,000 nodes (statusCheckRollup x commits)


def gh(*args):
    """Run gh; on failure print the (masked, capped) stderr first so the log explains the exit status."""
    try:
        return ghcall.gh(*args)
    except subprocess.CalledProcessError as e:
        shown = " ".join(str(a) for a in args[:2])
        print(f"gh {shown} exited {e.returncode}: {tail_text(e.stderr or '(no stderr)')}", file=sys.stderr)
        raise


def safe(run, *args):
    """Run a command; a failure is reported without secrets and never aborts the status run."""
    try:
        return run(*args)
    except subprocess.CalledProcessError as e:
        first = tail_text(e.stderr or "", lines=1, chars=200)
        print(f"gh {' '.join(str(a) for a in args[:2])} failed: {first}")
    except OSError as e:
        print(f"gh {' '.join(str(a) for a in args[:2])} failed: {type(e).__name__}")
    return None


def safe_labels(kind, number, labels, run):
    try:
        add_labels(kind, number, labels, run)
    except subprocess.CalledProcessError:
        print(f"label {','.join(labels)} on {kind} #{number} failed")


def parse_ts(s):
    return datetime.datetime.fromisoformat(s)


def minutes_since(ts, now):
    return (now - parse_ts(ts)).total_seconds() / 60


def age(ts, now):
    m = int(minutes_since(ts, now))
    return f"{m} min" if m < 120 else f"{m // 60} h" if m < 2880 else f"{m // 1440} d"


# --- schedule ---------------------------------------------------------------------------------

def interval_minutes(var, private):
    """STATUS_INTERVAL in minutes, rounded up to a multiple of 30 (the cron tick). Default: 30 public, 60 private."""
    try:
        v = int(str(var).strip())
    except ValueError:
        v = 0
    if v <= 0:
        v = 60 if private else 30
    return -(-v // TICK_MIN) * TICK_MIN


def should_run(event, private, var, now):
    """Dispatch and workflow_run always run; a schedule tick runs when its half hour is a multiple of the interval."""
    if event != "schedule":
        return True
    ticks = interval_minutes(var, private) // TICK_MIN
    return (now.hour * 60 + now.minute) // TICK_MIN % ticks == 0


# --- classification ---------------------------------------------------------------------------

def names(item):
    return {lab["name"] for lab in item.get("labels", [])}


def is_agent_pr(pr):
    """Same-repo agent/* PR that agents work on. The train's batch (agent/batch, decision 0018 rule 6) is a script
    product and is not one: no re-trigger, no round limit, no conflict fix, no rebase, no park and no fresh start."""
    head = pr.get("headRefName", "")
    return head.startswith("agent/") and head != restart.BATCH_BRANCH and not pr.get("isCrossRepository")


FAILED_STATES = ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "STARTUP_FAILURE")
PENDING_STATES = ("", "PENDING", "QUEUED", "IN_PROGRESS", "WAITING", "EXPECTED", "REQUESTED")
def check_name(check):
    """Name of a check run (CheckRun) or a commit status (StatusContext): the context the ruleset lists."""
    return check.get("name") or check.get("context") or ""


def check_state(check):
    return (check.get("conclusion") or check.get("state") or check.get("status") or "").upper()


def required_contexts(path=ruleset.RULESET_PATH, checks_path=ruleset.CHECKS_PATH):
    """Context names that main requires: the template ruleset plus `.agents/checks.json` (tools/ruleset.py, the same set
    the build writes). None if a file is unreadable or malformed, or nothing is required: then every check counts, as
    it did before the ruleset was read."""
    try:
        names = ruleset.contexts(path, checks_path)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return names or None


def ci_state(rollup, required=None):
    """red / running / green / none. With `required` (the ruleset's contexts) only those checks count; a required
    context that has not reported yet is running, as GitHub treats it."""
    checks = rollup or []
    if required:
        checks = [c for c in checks if check_name(c) in required]
    states = [check_state(c) for c in checks]
    if required and not required <= {check_name(c) for c in checks}:
        states.append("")
    if any(s in FAILED_STATES for s in states):
        return "red"
    if any(s in PENDING_STATES for s in states):
        return "running"
    return "green" if states else "none"


def non_required_reds(rollup, required):
    """Failing checks that the ruleset does not require: listed in the status, never blocking."""
    if not required:
        return []
    return sorted({check_name(c) for c in rollup or []
                   if check_name(c) not in required and check_state(c) in FAILED_STATES})


def waits_for(pr, owner, required=None):
    if PARKED in names(pr):
        return PARKED
    if any(same_login(r.get("login"), owner) for r in pr.get("reviewRequests", [])):
        return "waiting for Daniel"
    if pr.get("reviewDecision") == "REVIEW_REQUIRED" and ci_state(pr.get("statusCheckRollup"), required) == "green":
        return "waiting for code owner review"
    return ""


def pr_line(pr, owner, required=None):
    rollup = pr.get("statusCheckRollup")
    bits = [f"CI {ci_state(rollup, required)}", f"review {(pr.get('reviewDecision') or 'none').lower()}"]
    if pr.get("mergeStateStatus") == "DIRTY":
        bits.append("merge conflict")
    w = waits_for(pr, owner, required)
    if w:
        bits.append(w)
    extra = non_required_reds(rollup, required)
    if extra:
        bits.append(f"red but not required: {', '.join(extra)}")
    return f"- [#{pr['number']}]({pr['url']}) {pr['title']}: " + ", ".join(bits)


def run_for_issue(runs, issue):
    """A running agent-dev job whose title is the issue title or names it as #N."""
    tag = re.compile(rf"#{issue['number']}\b")
    return [r for r in runs if r.get("workflowName") == "agent-dev"
            and (r.get("displayTitle") == issue["title"] or tag.search(r.get("displayTitle", "")))]


def orphan_issues(issues, prs, runs, labeled_at, now):
    """agent:dev issues without a running job and without an open agent/N-* PR for more than 30 min."""
    out = []
    for i in issues:
        if PARKED in names(i) or run_for_issue(runs, i):
            continue
        if any(p.get("headRefName", "").startswith(f"agent/{i['number']}-") for p in prs):
            continue
        if minutes_since(labeled_at(i), now) > ISSUE_ORPHAN_MIN:
            out.append(i)
    return out


def head_date(pr):
    commits = pr.get("commits") or []
    return commits[-1]["committedDate"] if commits else pr["createdAt"]


def orphan_prs(prs, validate_runs, now):
    """Agent PRs (no conflict: pull_request runs do not start then) whose head has no validate run after 10 min."""
    out = []
    for p in prs:
        if not is_agent_pr(p) or PARKED in names(p) or p.get("mergeStateStatus") == "DIRTY":
            continue
        if minutes_since(head_date(p), now) > PR_ORPHAN_MIN and validate_runs(p["headRefOid"]) == 0:
            out.append(p)
    return out


def held_run_ids(held, prs, author_bot):
    ids = []
    for r in held:
        if any(p.get("headRefName", "").startswith("agent/") and not p.get("isCrossRepository")  # the batch too
               and same_login(p["author"]["login"], author_bot)
               and p["headRefOid"] == r.get("headSha") for p in prs):
            ids.append(r["databaseId"])
    return ids


def at_limit(labels):
    return STOP in labels or round_no(labels) >= MAX_ROUNDS


def limit_prs(prs, runs, now, approver=""):
    """Agent PRs at the round limit (`review:stop`, or MAX_ROUNDS rounds) that nobody took over: open, not effectively approved (a security `changes` verdict for
    the head counts as not approved), not parked, no agent job, idle head."""
    if any(r["workflowName"] in ("agent-fix", "agent-review") for r in runs):
        return []
    return [p for p in prs if is_agent_pr(p) and at_limit(names(p)) and PARKED not in names(p)
            and not effective_approval(p.get("reviewDecision"), names(p), p.get("comments"), p.get("headRefOid"), approver)
            and minutes_since(head_date(p), now) > LIMIT_IDLE_MIN]


def handle_stuck_limit(pr, run=gh):
    """Hand the PR over like agent-fix does at the limit; if that fails too, park it (never silent)."""
    try:
        return f"handed over ({handle_limit(str(pr['number']), run)})"
    except (subprocess.CalledProcessError, KeyError, ValueError, OSError):
        escalate("pr", pr["number"], "the PR is at the round limit and the hand-over failed.", run)
        return "escalated"


def conflict_mark(pr):
    return f"conflict:{pr.get('headRefOid', '')[:7]}"


def conflict_prs(prs):
    """DIRTY agent PRs whose head has not had its conflict fix yet (marker conflict:<sha7>)."""
    return [p for p in prs if is_agent_pr(p) and p.get("mergeStateStatus") == "DIRTY" and PARKED not in names(p)
            and conflict_mark(p) not in names(p)]


def parked_but_settled(prs, approver, required, codeowners, owner, files_of):
    """Parked agent PRs that are green and approved at their head (a risk:security PR also needs the security
    `approve`) and touch no CODEOWNERS path of OWNER: the label is stale."""
    out = []
    for p in prs:
        if not is_agent_pr(p) or PARKED not in names(p) or ci_state(p.get("statusCheckRollup"), required) != "green":
            continue
        sha, comments = p.get("headRefOid"), p.get("comments")
        if not effective_approval(p.get("reviewDecision"), names(p), comments, sha, approver):
            continue
        if "risk:security" in names(p) and security_verdict(comments, sha, approver) != "approve":
            continue
        try:
            files = files_of(p)
        except (ValueError, KeyError, TypeError, subprocess.CalledProcessError, OSError):  # files unknown: keep the label
            continue
        if not any(risk.owned_by(f, codeowners, owner) for f in files):
            out.append(p)
    return out


def main_was_red(main_runs, at):
    """True if the newest completed validate run on main created before `at` failed (main_runs: newest first)."""
    for r in main_runs:
        if r.get("conclusion") and parse_ts(r["createdAt"]) <= parse_ts(at):
            return r["conclusion"] == "failure"
    return False


def main_is_green(main_runs):
    done = [r for r in main_runs if r.get("conclusion")]
    return bool(done) and done[0]["conclusion"] == "success"


def rebase_candidates(prs, main_runs, pr_runs, owner):
    """Own agent PRs, every commit by owner, not conflicting, whose newest validate failed while main was red."""
    if not main_is_green(main_runs):
        return []
    out = []
    for p in prs:
        commits = p.get("commits") or []
        if not is_agent_pr(p) or PARKED in names(p) or p.get("mergeStateStatus") not in ("BEHIND", "BLOCKED"):
            continue
        if not commits or not all(same_login(a.get("login"), owner) for c in commits for a in c.get("authors", [])):
            continue
        runs = [r for r in pr_runs(p["headRefOid"]) if r.get("conclusion")]
        if runs and runs[0]["conclusion"] == "failure" and main_was_red(main_runs, runs[0]["createdAt"]):
            out.append(p)
    return out


# --- actions ----------------------------------------------------------------------------------

def escalate(kind, number, why, run=gh):
    """Park the item (label and one comment). Nobody is asked: un_park gives it a fresh start after the cool-down."""
    safe(park, "pr" if kind == "pr" else "issue", number, f"status run: {why}", run)


def handle_orphan(kind, item, run=gh):
    thing = "pr" if kind == "pr" else "issue"
    if RETRIGGER in names(item):
        escalate(kind, item["number"], "re-triggered once and still stuck.", run)
        return "escalated"
    if kind == "pr":
        safe(run, "workflow", "run", "validate.yml", "--ref", item["headRefName"])
    else:  # a new labeled event starts agent-dev again
        safe(run, "issue", "edit", str(item["number"]), "--remove-label", "agent:dev")
        safe_labels("issue", item["number"], ["agent:dev"], run)
    safe_labels(thing, item["number"], [RETRIGGER], run)
    return "retriggered"


def clear_retrigger(kind, item, run=gh):
    if RETRIGGER in names(item):
        safe(run, "pr" if kind == "pr" else "issue", "edit", str(item["number"]), "--remove-label", RETRIGGER)


def handle_conflict(pr, owner, run=gh):
    """A conflict with main is no finding: no review round. One fix run per head (marker conflict:<sha7>); a run that
    pushes nothing is parked by agent-fix itself."""
    safe_labels("pr", pr["number"], [conflict_mark(pr)], run)
    safe(run, "workflow", "run", "agent-fix.yml", "-f", f"pr={pr['number']}")
    return "fix dispatched"


FILES_CAP = 3000  # GitHub's limit for pulls/N/files


def release_settled(prs, approver, owner, run=gh):
    """Remove `parked` from PRs that are green and approved at their head and touch no CODEOWNERS path."""
    def files_of(p):
        """Paginated `pulls/N/files` with old names of renames (risk.pr_paths). GitHub lists at most 3000 files:
        a list that may be cut off raises, and the caller keeps the label."""
        pages = json.loads(run("api", "--paginate", "--slurp", f"repos/{os.environ['GH_REPO']}/pulls/{p['number']}/files"))
        if sum(len(page) for page in pages) >= FILES_CAP:
            raise ValueError("file list may be incomplete")
        return risk.pr_paths(pages)

    out = []
    for p in parked_but_settled(prs, approver, required_contexts(), risk.read_text(".github/CODEOWNERS"), owner, files_of):
        if safe(run, "pr", "edit", str(p["number"]), "--remove-label", PARKED) is not None:
            p["labels"] = [lab for lab in p["labels"] if lab["name"] != PARKED]  # the later steps of this run see it
            out.append(f"parked removed from PR #{p['number']}: green and approved at its head")
    return out


# --- un-park ----------------------------------------------------------------------------------

COOL_H, COOL_MAX_H = 24, 7 * 24
COUNTER = re.compile(r"review:(?:\d+|stop)|ci-red:\d+|red:.*|round:.*|formfix|conflict:.*|silent:.*|restart:1|stalled:1|status:retriggered")


def cool_down_hours(n):
    """Hours a parked item rests before its fresh start: 24 h, doubled per park (n = park comments), at most 7 days."""
    return min(COOL_H * 2 ** (max(n, 1) - 1), COOL_MAX_H)


def park_count(comments, bots):
    """Comments with the hidden park marker written by one of BOTS (`gh ... --json comments`). Others' text is data."""
    return sum(PARK_MARK in (c.get("body") or "") and any(same_login((c.get("author") or {}).get("login"), b) for b in bots)
               for c in comments or [])


def clear_labels(kind, item, run):
    """Remove `parked` and every counter label the item carries, so the next try counts from zero."""
    gone = sorted(n for n in names(item) if n == PARKED or COUNTER.fullmatch(n))
    if gone:
        run(kind, "edit", str(item["number"]), *[a for n in gone for a in ("--remove-label", n)])


def fresh_start(kind, item, run=gh):
    """Issue: labels cleared, agent:dev removed and set again (the label event starts a developer). Agent PR: its issue
    gets one park comment (the issue keeps the count across PRs), the PR is closed and the issue restarts the same way
    from current main. A PR that names no issue only loses the labels, so its review rounds start again."""
    issue = item
    if kind == "pr":
        refs = restart.own_issues(item.get("body"))
        clear_labels("pr", item, run)  # first: a later failure must not leave the PR parked and due again every tick
        if not refs:
            return
        run("pr", "close", str(item["number"]))
        liveness.post_comment("issue", refs[0], f"Fresh start: PR #{item['number']} was parked and is closed. Start on "
                              f"a new branch from main with a different approach.\n{PARK_MARK}", run)
        issue = {"number": refs[0], **jlist(run, "issue", "view", str(refs[0]), "--json", "labels")}
    clear_labels("issue", issue, run)
    if "agent:dev" in names(issue):
        run("issue", "edit", str(issue["number"]), "--remove-label", "agent:dev")
    add_labels("issue", issue["number"], ["agent:dev"], run)


REVIEW_WORKFLOW = ".github/workflows/agent-review.yml"


def unpark_silent(prs, repo, run=gh):
    """An agent PR parked as silent (label silent:<sha7> of its current head) gets `parked` and that label removed and
    validate dispatched once agent-review.yml on main has a commit newer than the newest `parked` event. A second
    silent park on the same head has a newer event, so the normal cool-down applies. Other labels stay. Validate is
    dispatched before the labels go: if either call fails the PR stays parked and silent and the next tick tries again."""
    out, workflow_at = [], None
    for p in prs:
        mark = f"silent:{(p.get('headRefOid') or '')[:7]}"
        if PARKED not in names(p) or mark not in names(p) or p.get("isCrossRepository") or not is_agent_pr(p):
            continue
        try:
            if workflow_at is None:
                commits = jlist(run, "api", f"repos/{repo}/commits?path={REVIEW_WORKFLOW}&sha=main&per_page=1")
                workflow_at = commits[0]["commit"]["committer"]["date"] if commits else ""
            if not workflow_at:
                continue
            pages = jlist(run, "api", "--paginate", "--slurp", f"repos/{repo}/issues/{p['number']}/events")
            since = max(e["created_at"] for page in pages for e in page
                        if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == PARKED)
            if parse_ts(workflow_at) <= parse_ts(since):
                continue
            run("workflow", "run", "validate.yml", "--ref", p["headRefName"])  # first: a failed dispatch keeps the labels
            run("pr", "edit", str(p["number"]), "--remove-label", PARKED, "--remove-label", mark)
            p["labels"] = [lab for lab in p["labels"] if lab["name"] not in (PARKED, mark)]
            out.append(f"un-parked pr #{p['number']}: silent review, {REVIEW_WORKFLOW} changed on main")
        except (subprocess.CalledProcessError, OSError, ValueError, KeyError, IndexError, TypeError) as e:
            out.append(f"silent un-park of pr #{p['number']} failed ({type(e).__name__})")
    return out


def un_park(prs, repo, bots, now, run=gh):
    """Fresh start for every open issue and agent PR whose newest `parked` label event is older than its cool-down;
    a parked PR of this repo on another branch (template-sync/x.y) only loses its labels, nothing is closed.
    A PR also counts the park comments on its issue. Returns the actions; one failing item never stops the others."""
    issues = jlist(run, "issue", "list", "--state", "open", "--label", PARKED, "--limit", "50", "--json",
                   "number,labels,comments")
    out, started = [], set()
    parked = [("pr", p) for p in prs if PARKED in names(p) and not p.get("isCrossRepository")]
    for kind, item in parked + [("issue", i) for i in issues]:
        n = item["number"]
        agent = kind == "issue" or is_agent_pr(item)  # any other PR (template-sync/x.y) only loses the labels
        if kind == "issue" and n in started:  # its parked PR just restarted it
            continue
        try:
            count = park_count(item.get("comments"), bots)
            for ref in restart.own_issues(item.get("body"))[:1] if kind == "pr" else []:
                count += park_count(jlist(run, "issue", "view", str(ref), "--json", "comments")["comments"], bots)
            pages = jlist(run, "api", "--paginate", "--slurp", f"repos/{repo}/issues/{n}/events")
            since = max(e["created_at"] for page in pages for e in page
                        if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == PARKED)
            if minutes_since(since, now) < cool_down_hours(count) * 60:
                continue
            if not agent:
                clear_labels("pr", item, run)
                out.append(f"un-parked pr #{n}: labels cleared after {cool_down_hours(count)} h")
                continue
            fresh_start(kind, item, run)
            started.update(restart.own_issues(item.get("body"))[:1] if kind == "pr" else ())
            out.append(f"un-parked {kind} #{n}: fresh start after {cool_down_hours(count)} h")
        except (subprocess.CalledProcessError, OSError, ValueError, KeyError, TypeError, liveness.ReadbackError) as e:
            out.append(f"un-park of {kind} #{n} failed ({type(e).__name__})")
    return out


# --- status issue -----------------------------------------------------------------------------

def section(heading, rows):
    return "\n".join([f"## {heading}", *(rows or ["- none"])])


def scheduled_rows(successes, now, added=None):
    late = set(liveness.overdue_runs(successes, now, added))
    rows = []
    for wf, (label, _) in liveness.SCHEDULED.items():
        last = successes.get(wf)
        when = f"[{age(last['createdAt'], now)} ago]({last['url']})" if last else "never"
        rows.append(f"- {label}: {when}" + (" OVERDUE" if label in late else ""))
    return rows


def merged_rows(merged, now, hours=24):
    """PRs merged in the last `hours`: what landed without Daniel, so he can revert it (button on the PR page)."""
    rows = []
    for p in merged or []:
        at = p.get("mergedAt")
        if at and minutes_since(at, now) <= hours * 60:
            risk = [n for n in names(p) if n.startswith("risk:")]
            rows.append(f"- #{p['number']} {p['title']}" + (f" ({', '.join(risk)})" if risk else ""))
    return rows


def build_body(runs, prs, issues, ages, orchestrator, ideas, actions, now, owner, scheduled=None, added=None,
               merged=None, watch_since=None, required=None, flow_lines=None):
    run_rows = [f"- [{r['workflowName']}]({r['url']}) {r.get('displayTitle', '')} ({r['status']}, "
                f"{age(r['createdAt'], now)})" for r in runs]
    pr_rows = [pr_line(p, owner, required) for p in prs]
    issue_rows = [f"- #{i['number']} {i['title']} (agent:dev for {ages[i['number']]})" for i in issues]
    if orchestrator:
        state = f"{orchestrator['status']} {orchestrator.get('conclusion') or ''}".strip()
        orch = f"- [{state}]({orchestrator['url']}) {age(orchestrator['createdAt'], now)} ago"
    else:
        orch = "- no run yet"
    idea_rows = [f"- #{i['number']} {i['title']}" for i in ideas]
    parts = [f"Updated {now.strftime('%Y-%m-%d %H:%M')} UTC by the status run (no model).",
             section("Running agent jobs", run_rows), section("Pull requests", pr_rows),
             section("Issues with agent:dev", issue_rows), section("Last orchestrator run", [orch]),
             section("Open ideas", idea_rows)]
    if merged is not None:
        parts.append(section("Merged in the last 24 h (undo: Revert button on the PR)", merged_rows(merged, now)))
    if flow_lines is not None:
        parts.append(section("Flow, last 24 h", flow_lines))
    if scheduled is not None:
        parts.append(section("Last successful scheduled runs", scheduled_rows(scheduled, now, added)))
    parts.append(section("Actions of this run", [f"- {a}" for a in actions]))
    if watch_since is not None:
        parts.append(f"{SINCE_LABEL} {watch_since:%Y-%m-%dT%H:%M:%SZ}")
    return "\n\n".join(parts) + "\n"


def update_issue(body, run=gh, bot=""):
    number = status_issue(run, bot)
    if number:
        run("issue", "edit", number, "--body", body)
    else:
        number = run("issue", "create", "--title", TITLE, "--body", body).strip().rsplit("/", 1)[-1]
    liveness.verify_body("issue", number, body, run)
    safe(run, "issue", "pin", number)  # already pinned or no permission: not fatal
    return number


# --- main -------------------------------------------------------------------------------------

def jlist(run, *args):
    return json.loads(run(*args))


def label_time(run, repo):
    """When agent:dev was last added to the issue; falls back to the creation time."""
    def f(issue):
        try:
            pages = jlist(run, "api", "--paginate", "--slurp", f"repos/{repo}/issues/{issue['number']}/events")
            times = [e["created_at"] for page in pages for e in page
                     if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == "agent:dev"]
            if times:
                return max(times)
        except (subprocess.CalledProcessError, ValueError, KeyError):
            pass
        return issue["createdAt"]
    return f


def own_issue(issue, bot):
    """Status issue written by our bot. Without a configured bot login the author is not checked."""
    return not bot or same_login((issue.get("author") or {}).get("login"), bot)


def previous_since(run, now, bot=""):
    """Anchor of the failure watch: the `Failure watch since:` line of the open status issue (bot-authored only,
    clamped to [now - MAX_BACK, now] because the body is editable input), else 24 h back."""
    oldest = now - failure_watch.MAX_BACK
    found = jlist(run, "issue", "list", "--state", "open", "--search", f'"{TITLE}" in:title', "--json",
                  "title,body,author")
    for i in found:
        if i["title"] != TITLE or not own_issue(i, bot):
            continue
        m = re.search(rf"^{re.escape(SINCE_LABEL)} (\S+)$", i.get("body") or "", re.MULTILINE)
        if m:
            try:
                return min(max(parse_ts(m.group(1)), oldest), now)
            except (ValueError, TypeError):
                break
    # No status issue (REPORT_ISSUES=off, or the first run): the start of the last successful status run is the
    # anchor, so a failed run is not counted again on every tick.
    last = safe(liveness.last_success, SELF_WORKFLOW, run)
    try:
        return min(max(parse_ts(last["createdAt"]), oldest), now) if last else oldest
    except (ValueError, TypeError, KeyError):
        return oldest


def watch_failures(env, now, successes, added, actions, run):
    """Failure watch after the overdue block (design 0008, 4.8). Never stops the status run; returns the new anchor.
    FAILURE_WATCH=off skips it. Without a successes list the overdue state is unknown, so nothing is closed."""
    bot = env.get("AUTHOR_BOT", "")
    if env.get("FAILURE_WATCH", "").strip().lower() == "off" or successes is None:
        return None
    since = None
    try:
        since = previous_since(run, now, bot)
        late = liveness.overdue_runs(successes, now, added)
        done, since = failure_watch.watch(since, now, late, None, run, SELF_WORKFLOW)
        actions += done
    except Exception as e:  # noqa: BLE001 - the status issue must always be written
        print(f"failure watch failed: {type(e).__name__}")
    return since


def gate(env, now):
    private = env.get("PRIVATE", "").lower() == "true"
    go = should_run(env.get("EVENT", ""), private, env.get("STATUS_INTERVAL", ""), now)
    line = f"run={'true' if go else 'false'}"
    if env.get("GITHUB_OUTPUT"):
        with open(env["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(line + "\n")
    print(line)
    return 0


def flow_lines_for(env, repo, now, run=gh):
    """Lines of the "Flow, last 24 h" block (tools/flow.py); the CSV goes to FLOW_CSV if set (workflow artifact).
    A failure leaves the block out and never stops the status run."""
    try:
        rows, flow_runs = flow.collect(repo, run)
        if env.get("FLOW_CSV"):
            flow.write_csv(rows, env["FLOW_CSV"])
        return flow.flow_block(rows, flow_runs, now)
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError) as e:
        print(f"flow metrics failed: {type(e).__name__}")
        return None


def run_status(env, now, run=gh):
    repo, owner, bot = env["GH_REPO"], env.get("OWNER", OWNER_DEFAULT), env.get("AUTHOR_BOT", "")
    runs = []
    for st in ("in_progress", "queued"):
        runs += jlist(run, "run", "list", "--status", st, "--limit", "50", "--json",
                      "databaseId,workflowName,displayTitle,url,status,createdAt")
    runs = [r for r in runs if r["workflowName"] in AGENT_WORKFLOWS]
    prs = jlist(run, "pr", "list", "--state", "open", "--limit", str(PR_LIMIT), "--json",
                "number,title,url,headRefName,headRefOid,labels,reviewDecision,reviewRequests,statusCheckRollup,"
                "mergeStateStatus,isCrossRepository,author,commits,createdAt,body,comments,files")
    issues = jlist(run, "issue", "list", "--state", "open", "--label", "agent:dev", "--limit", "50",
                   "--json", "number,title,labels,createdAt")
    ideas = jlist(run, "issue", "list", "--state", "open", "--label", "idea", "--limit", "50",
                  "--json", "number,title")
    orch = (jlist(run, "run", "list", "--workflow", "orchestrator.yml", "--limit", "1", "--json",
                  "status,conclusion,createdAt,url") or [None])[0]
    held = jlist(run, "run", "list", "--status", "action_required", "--limit", "50", "--json",
                 "databaseId,headSha,workflowName")
    labeled_at = label_time(run, repo)
    actions = []

    def validate_runs(sha):
        return len(jlist(run, "run", "list", "--workflow", "validate.yml", "--commit", sha, "--json", "databaseId"))

    def pr_validate_runs(sha):
        return jlist(run, "run", "list", "--workflow", "validate.yml", "--commit", sha, "--json",
                     "conclusion,createdAt")

    main_runs = safe(jlist, run, "run", "list", "--workflow", "validate.yml", "--branch", "main", "--limit", "20",
                     "--json", "conclusion,createdAt") or []
    for p in rebase_candidates(prs, main_runs, pr_validate_runs, owner):
        done = safe(run, "pr", "update-branch", str(p["number"]), "--rebase")  # REST update-branch only merges
        actions.append(f"rebased PR #{p['number']} onto green main" if done is not None
                       else f"rebase of PR #{p['number']} failed")

    for old, new in safe(close_superseded, prs, run) or []:  # a newer agent PR with the same work (restart.replaces)
        actions.append(f"closed PR #{old}: superseded by #{new}")
    prs = [p for p in prs if p["number"] not in {o for o, _ in superseded(prs)}]

    for rid in held_run_ids(held, prs, bot):
        if safe(run, "api", "-X", "POST", f"repos/{repo}/actions/runs/{rid}/approve") is not None:
            actions.append(f"approved held run {rid}")
    stuck_i = orphan_issues(issues, prs, runs, labeled_at, now)
    stuck_p = orphan_prs(prs, validate_runs, now)
    for kind, items in (("issue", stuck_i), ("pr", stuck_p)):
        for it in items:
            actions.append(f"orphan {kind} #{it['number']}: {handle_orphan(kind, it, run)}")
    for i in issues:  # recovered items lose the mark, so a later stall starts at "re-trigger" again
        if i not in stuck_i:
            clear_retrigger("issue", i, run)
    for p in prs:
        if p not in stuck_p:
            clear_retrigger("pr", p, run)
    for p in limit_prs(prs, runs, now, env.get("APPROVER_BOT", "")):
        actions.append(f"round limit PR #{p['number']}: {handle_stuck_limit(p, run)}")
    actions += release_settled(prs, env.get("APPROVER_BOT", ""), owner, run)
    actions += safe(unpark_silent, prs, repo, run) or []
    actions += safe(un_park, prs, repo, [b for b in (bot, env.get("APPROVER_BOT", "")) if b], now, run) or []
    if not any(r["workflowName"] == "agent-fix" for r in runs):  # one fix job at a time
        for p in conflict_prs(prs)[:1]:
            actions.append(f"conflict PR #{p['number']}: {handle_conflict(p, owner, run)}")
    actions += safe(design_parents.close_done_parents, run, owner, bot) or []
    actions += stalled_dev.check(issues, labeled_at, now, run, {i["number"] for i in stuck_i})
    ages = {i["number"]: age(labeled_at(i), now) for i in issues}
    successes = safe(liveness.last_successes, run)
    added = {}
    if successes is not None:
        added = safe(liveness.added_dates, successes, run) or {}
        late, new = liveness.flag_overdue(successes, now, run, added)
        actions += [f"overdue run: {label}" for label in late] + [f"opened overdue issue #{n}" for n in new]
    watch_since = watch_failures(env, now, successes, added, actions, run)
    merged = safe(jlist, run, "pr", "list", "--state", "merged", "--limit", "30", "--json",
                  "number,title,mergedAt,labels")
    flow_lines = flow_lines_for(env, repo, now, run)
    body = build_body(runs, prs, issues, ages, orch, ideas, actions, now, owner, successes, added,
                      merged, watch_since, required_contexts(), flow_lines)
    if liveness.reports_off(env):
        liveness.write_summary(TITLE, body, env)
        closed = liveness.retire_issue(TITLE, run, bot)
        print(f"status in the run summary{f', closed issue #{closed}' if closed else ''}; actions: {len(actions)}")
    else:
        number = update_issue(body, run, bot)
        print(f"status issue #{number}; actions: {len(actions)}")
    for a in actions:
        print(a)
    return 0


def main(argv):
    now = datetime.datetime.now(datetime.UTC)
    if argv[1:] == ["gate"]:
        return gate(os.environ, now)
    if len(argv) == 1:
        if reason := budget.low(budget.BACKGROUND):
            print(reason)
            return 0
        try:
            return run_status(os.environ, now)
        except liveness.ReadbackError as e:
            print(f"read-back failed: {e}", file=sys.stderr)
            return 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
