"""Model-free status run: keeps the issue "Agent status" up to date and un-sticks agent work.

1. Status issue (pinned, updated in place): running agent jobs, PRs and their state, agent:dev issues and
   their age, last orchestrator run, open ideas.
2. Orphans: an agent:dev issue with no running job and no open PR for more than 30 min, or an agent PR whose head
   has no validate run for more than 10 min. First time: re-trigger and label `status:retriggered`;
   second time: needs-human, review request for OWNER, comment.
3. Held runs: runs in `action_required` are approved only if the head belongs to an open same-repo PR of the author app.
4. Merge conflicts: an agent PR with mergeStateStatus DIRTY gets one fix round (label review:N, then agent-fix is
   dispatched with the PR number). After round 2 the PR gets needs-human instead.
5. Exhausted rounds: an open agent PR with `review:3`, not approved, no needs-human, no agent job running and an
   idle head for more than 30 min was never handed over (the limit step failed): restart.py limit hands it over
   (issue restart once, else needs-human + review request). A failure is escalated with needs-human.
6. Red main: an own agent PR (one commit, author OWNER, behind main) whose last validate failed while main was red
   is rebased onto main via the update-branch API once main is green again, so CI runs again. Never merges.
Read-only except: the status issue, re-triggers, run approvals, the fix dispatch and these labels:
agent:dev (re-add), status:retriggered, review:N, needs-human, restart:1 (via restart.py). Needs the gh CLI (GH_TOKEN, GH_REPO).

CLI: status.py gate   write run=true|false to $GITHUB_OUTPUT (schedule ticks honour STATUS_INTERVAL)
     status.py        do the run
7. Failure watch (tools/failure_watch.py, design 0008): after the overdue block; FAILURE_WATCH=off skips it; the
   anchor is kept in the status issue line `Failure watch since:`. An error in it never stops the status issue.
8. Design parents (tools/design_parents.py, issue #335): an open design parent whose split issues are all closed as
   completed by a merged PR is closed (prio:* and agent:dev removed, one comment). Nothing else is touched.
Environment: OWNER (default Bankaifan), AUTHOR_BOT, FAILURE_WATCH (off = skip the failure watch), STATUS_INTERVAL (minutes, default 30 public / 60 private repos;
rounded up to a multiple of 30), EVENT, PRIVATE ("true" for a private repo).
Prints numbers and titles, never tokens.
"""
import datetime
import json
import os
import re
import subprocess
import sys

import design_parents
import failure_watch
import liveness
import owner_hold
from agent_guard import add_labels, same_login, tail_text
from approval import effective_approval
from restart import close_superseded, handle_limit, superseded

TITLE = "Agent status"
OWNER_DEFAULT = "Bankaifan"
ISSUE_ORPHAN_MIN = 30
PR_ORPHAN_MIN = 10
LIMIT_IDLE_MIN = 30
RETRIGGER = "status:retriggered"
AGENT_WORKFLOWS = {"agent-dev", "agent-fix", "agent-review", "orchestrator", "scout", "rule-keeper"}
TICK_MIN = 30
SINCE_LABEL = "Failure watch since:"
PR_LIMIT = 20  # 50 made the GraphQL query exceed 500,000 nodes (statusCheckRollup x commits)


def gh(*args):
    """Run gh; on failure print the (masked, capped) stderr first so the log explains the exit status."""
    try:
        return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout
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
    return pr.get("headRefName", "").startswith("agent/") and not pr.get("isCrossRepository")


def ci_state(rollup):
    states = [(c.get("conclusion") or c.get("state") or c.get("status") or "").upper() for c in rollup or []]
    if any(s in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "STARTUP_FAILURE") for s in states):
        return "red"
    if any(s in ("", "PENDING", "QUEUED", "IN_PROGRESS", "WAITING", "EXPECTED", "REQUESTED") for s in states):
        return "running"
    return "green" if states else "none"


def waits_for(pr, owner):
    if "needs-human" in names(pr):
        return "needs-human"
    if any(same_login(r.get("login"), owner) for r in pr.get("reviewRequests", [])):
        return "waiting for Daniel"
    if pr.get("reviewDecision") == "REVIEW_REQUIRED" and ci_state(pr.get("statusCheckRollup")) == "green":
        return "waiting for code owner review"
    return ""


def pr_line(pr, owner):
    bits = [f"CI {ci_state(pr.get('statusCheckRollup'))}", f"review {(pr.get('reviewDecision') or 'none').lower()}"]
    if pr.get("mergeStateStatus") == "DIRTY":
        bits.append("merge conflict")
    w = waits_for(pr, owner)
    if w:
        bits.append(w)
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
        if "needs-human" in names(i) or run_for_issue(runs, i):
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
        if not is_agent_pr(p) or "needs-human" in names(p) or p.get("mergeStateStatus") == "DIRTY":
            continue
        if minutes_since(head_date(p), now) > PR_ORPHAN_MIN and validate_runs(p["headRefOid"]) == 0:
            out.append(p)
    return out


def held_run_ids(held, prs, author_bot):
    ids = []
    for r in held:
        if any(is_agent_pr(p) and same_login(p["author"]["login"], author_bot)
               and p["headRefOid"] == r.get("headSha") for p in prs):
            ids.append(r["databaseId"])
    return ids


def fix_round(labels):
    """Mirror of agent-fix: (new round label or None, limit reached)."""
    if "review:3" in labels:
        return None, True
    if "review:2" in labels:
        return "review:3", True
    return ("review:2" if "review:1" in labels else "review:1"), False


def limit_prs(prs, runs, now, approver="", is_held=None):
    """Agent PRs at review:3 that nobody took over: open, not effectively approved (a security `changes` verdict for
    the head counts as not approved), no needs-human, no agent job, idle head, no OWNER label removal (`is_held`)."""
    if any(r["workflowName"] in ("agent-fix", "agent-review") for r in runs):
        return []
    return [p for p in prs if is_agent_pr(p) and "review:3" in names(p) and "needs-human" not in names(p)
            and not effective_approval(p.get("reviewDecision"), names(p), p.get("comments"), p.get("headRefOid"), approver)
            and minutes_since(head_date(p), now) > LIMIT_IDLE_MIN and not (is_held and is_held(p))]


def handle_stuck_limit(pr, owner, run=gh):
    """Hand the PR over like agent-fix does at the limit; if that fails too, needs-human (never silent)."""
    try:
        return f"handed over ({handle_limit(str(pr['number']), owner, run)})"
    except (subprocess.CalledProcessError, KeyError, ValueError, OSError):
        escalate("pr", pr["number"], "the PR is at review:3 and the hand-over failed.", owner, run)
        return "escalated"


def conflict_prs(prs):
    return [p for p in prs if is_agent_pr(p) and p.get("mergeStateStatus") == "DIRTY" and "needs-human" not in names(p)]


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
    """Own agent PRs, one commit by owner, not conflicting, whose newest validate failed while main was red."""
    if not main_is_green(main_runs):
        return []
    out = []
    for p in prs:
        commits = p.get("commits") or []
        if not is_agent_pr(p) or "needs-human" in names(p) or p.get("mergeStateStatus") not in ("BEHIND", "BLOCKED"):
            continue
        if len(commits) != 1 or not all(same_login(a.get("login"), owner) for a in commits[0].get("authors", [])):
            continue
        runs = [r for r in pr_runs(p["headRefOid"]) if r.get("conclusion")]
        if runs and runs[0]["conclusion"] == "failure" and main_was_red(main_runs, runs[0]["createdAt"]):
            out.append(p)
    return out


# --- actions ----------------------------------------------------------------------------------

def escalate(kind, number, why, owner, run=gh):
    thing = "pr" if kind == "pr" else "issue"
    safe_labels(thing, number, ["needs-human"], run)
    liveness.post_comment(thing, number, f"Status run: {why} Labelled needs-human; Daniel is asked to look at it.", run)
    if kind == "pr":
        author = safe(run, "pr", "view", str(number), "--json", "author")
        if author and not same_login(json.loads(author)["author"]["login"], owner):  # nobody reviews their own PR
            safe(run, "pr", "edit", str(number), "--add-reviewer", owner)
    else:
        safe(run, "issue", "edit", str(number), "--add-assignee", owner)


def handle_orphan(kind, item, owner, run=gh):
    thing = "pr" if kind == "pr" else "issue"
    if RETRIGGER in names(item):
        escalate(kind, item["number"], "re-triggered once and still stuck.", owner, run)
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
    label, limit = fix_round(names(pr))
    if label:
        safe_labels("pr", pr["number"], [label], run)
    if limit:
        escalate("pr", pr["number"], "the PR conflicts with main and the fix rounds are used up.", owner, run)
        return "escalated"
    safe(run, "workflow", "run", "agent-fix.yml", "-f", f"pr={pr['number']}")
    return "fix dispatched"


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
               merged=None, watch_since=None):
    run_rows = [f"- [{r['workflowName']}]({r['url']}) {r.get('displayTitle', '')} ({r['status']}, "
                f"{age(r['createdAt'], now)})" for r in runs]
    pr_rows = [pr_line(p, owner) for p in prs]
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
    if scheduled is not None:
        parts.append(section("Last successful scheduled runs", scheduled_rows(scheduled, now, added)))
    parts.append(section("Actions of this run", [f"- {a}" for a in actions]))
    if watch_since is not None:
        parts.append(f"{SINCE_LABEL} {watch_since:%Y-%m-%dT%H:%M:%SZ}")
    return "\n\n".join(parts) + "\n"


def update_issue(body, run=gh, bot=""):
    found = json.loads(run("issue", "list", "--state", "open", "--search", f'"{TITLE}" in:title',
                           "--json", "number,title,author"))
    found = [i for i in found if i["title"] == TITLE and own_issue(i, bot)]
    if found:
        number = str(found[0]["number"])
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
        done, since = failure_watch.watch(since, now, late, None, run)
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


def run_status(env, now, run=gh):
    repo, owner, bot = env["GH_REPO"], env.get("OWNER", OWNER_DEFAULT), env.get("AUTHOR_BOT", "")
    runs = []
    for st in ("in_progress", "queued"):
        runs += jlist(run, "run", "list", "--status", st, "--limit", "50", "--json",
                      "databaseId,workflowName,displayTitle,url,status,createdAt")
    runs = [r for r in runs if r["workflowName"] in AGENT_WORKFLOWS]
    prs = jlist(run, "pr", "list", "--state", "open", "--limit", str(PR_LIMIT), "--json",
                "number,title,url,headRefName,headRefOid,labels,reviewDecision,reviewRequests,statusCheckRollup,"
                "mergeStateStatus,isCrossRepository,author,commits,createdAt,body,comments")
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
        done = safe(run, "api", "-X", "PUT", f"repos/{repo}/pulls/{p['number']}/update-branch",
                    "-f", "update_method=rebase")
        actions.append(f"rebased PR #{p['number']} onto green main" if done is not None
                       else f"rebase of PR #{p['number']} failed")

    for old, new in safe(close_superseded, prs, run) or []:  # a newer agent PR for the same issue replaces the older
        actions.append(f"closed PR #{old}: superseded by #{new}")
    prs = [p for p in prs if p["number"] not in {o for o, _ in superseded(prs)}]

    for rid in held_run_ids(held, prs, bot):
        if safe(run, "api", "-X", "POST", f"repos/{repo}/actions/runs/{rid}/approve") is not None:
            actions.append(f"approved held run {rid}")
    stuck_i = orphan_issues(issues, prs, runs, labeled_at, now)
    stuck_p = orphan_prs(prs, validate_runs, now)
    for kind, items in (("issue", stuck_i), ("pr", stuck_p)):
        for it in items:
            actions.append(f"orphan {kind} #{it['number']}: {handle_orphan(kind, it, owner, run)}")
    for i in issues:  # recovered items lose the mark, so a later stall starts at "re-trigger" again
        if i not in stuck_i:
            clear_retrigger("issue", i, run)
    for p in prs:
        if p not in stuck_p:
            clear_retrigger("pr", p, run)
    def is_held(p):
        return owner_hold.pr_held(p["number"], run, owner)

    for p in limit_prs(prs, runs, now, env.get("APPROVER_BOT", ""), is_held):
        actions.append(f"review:3 PR #{p['number']}: {handle_stuck_limit(p, owner, run)}")
    if not any(r["workflowName"] == "agent-fix" for r in runs):  # one fix job at a time
        for p in [c for c in conflict_prs(prs) if not is_held(c)][:1]:
            actions.append(f"conflict PR #{p['number']}: {handle_conflict(p, owner, run)}")
    actions += safe(design_parents.close_done_parents, run, owner, bot) or []
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
    number = update_issue(build_body(runs, prs, issues, ages, orch, ideas, actions, now, owner, successes, added,
                                     merged, watch_since), run, bot)
    print(f"status issue #{number}; actions: {len(actions)}")
    for a in actions:
        print(a)
    return 0


def main(argv):
    now = datetime.datetime.now(datetime.UTC)
    if argv[1:] == ["gate"]:
        return gate(os.environ, now)
    if len(argv) == 1:
        try:
            return run_status(os.environ, now)
        except liveness.ReadbackError as e:
            print(f"read-back failed: {e}", file=sys.stderr)
            return 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
