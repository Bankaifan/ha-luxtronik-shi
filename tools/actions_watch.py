"""Actions watcher entry (design 0012, sections 4.1-4.2): one failed workflow run -> rerun once or one signed issue.

`actions_watch.py` handles the run in RUN_ID (a `workflow_run` event); without RUN_ID it sweeps the runs of the last
SWEEP_HOURS hours (schedule / workflow_dispatch, for events GitHub did not deliver). Everything is idempotent, so a
replaced pending run loses nothing. A startup failure, or a cancelled run whose job never started, is rerun once (only
while run_attempt is 1, no state); anything else opens or updates the signed `Failing workflow:` issue through
tools/failure_watch.py. Bodies are fixed script text. DRY_RUN=1 prints the actions and writes nothing.
The sweep also self-heals (section 4.4): fallback `agent:dev` while the orchestrator is unhealthy and MAX_DEV has room,
one restart of failed agent work. It only touches issues signed
with GUARD_KEY and authored by AUTHOR_BOT (env AUTHOR_BOT, OWNER, MAX_DEV).
FAILURE_WATCH=off skips it. Needs the gh CLI (GH_TOKEN, GH_REPO) and GUARD_KEY (script step only).
"""
import datetime
import json
import os
import re
import sys

import budget
import failure_watch as fw
import ghcall
import guard_mark
import liveness
import stalled_dev
import trusted_issues
from agent_guard import add_labels, park

SELF_WF = "watch.yml"  # the watcher never watches its own runs (no loop)
SWEEP_HOURS = 2
RERUN_CONCLUSIONS = ("startup_failure", "cancelled")
WRITES = ("create", "edit", "comment", "close", "reopen", "rerun")  # gh subcommands that change state

# Self-healing (design 0012 section 4.4), sweep only. Everything is bounded: one fallback label per issue,
# stalled:1 then parked.
ORCHESTRATOR = "orchestrator.yml"
UNHEALTHY = ("cancelled", "failure", "timed_out")  # conclusion of the newest orchestrator run in the last HEAL_HOURS
HEAL_HOURS = 2
FAILED_AGENT = ("failure", "timed_out", "cancelled")
RESTART_HOURS = 4  # a failed agent run older than this is history, not a restart trigger
DEFAULT_MAX_DEV = 4


def readonly(run):
    """gh wrapper for DRY_RUN: any write subcommand is a bug, not a silent no-op."""
    def guarded(*args):
        if any(a in WRITES for a in args[:2]) or args[:2] == ("workflow", "run"):
            raise RuntimeError(f"dry run must not write: gh {args[0]} {args[1]}")
        return run(*args)
    return guarded


def wants_rerun(run_obj, started):
    """Infrastructure-shaped ending, first attempt only: `gh run rerun` once, no state, no second rerun."""
    return (run_obj.get("conclusion") in RERUN_CONCLUSIONS and not started
            and int(run_obj.get("run_attempt") or 1) == 1)


def handle(r, key, dry=False, run=liveness.gh):
    """Act on one failed run R; returns a one-line action text."""
    if not fw.keep(r, SELF_WF):
        return f"run {r['id']}: not watched"
    capped = fw.turn_cap(fw.workflow_file(r), r["id"], r.get("conclusion"), run)
    if capped:
        return fw.turn_cap_line(r["id"], capped)
    if fw.rate_limited(r["id"], r.get("conclusion"), run):
        return f"run {r['id']}: GitHub API rate limit: no issue, no rerun"
    sig, started = fw.analyse(r, run)
    if fw.expected_cancel(r, started, run):
        return f"run {r['id']}: expected cancellation"
    if wants_rerun(r, started):
        if not dry:
            run("run", "rerun", str(r["id"]))
        return f"run {r['id']}: {'would rerun' if dry else 'rerun'} once ({sig})"
    issues = fw.load_issues(key, run)
    title = fw.title_for(sig)
    issue = issues.get(title)
    if issue and fw.parse_body(issue["body"])["last_id"] >= r["id"]:
        return f"run {r['id']}: already counted in #{issue['number']}"
    if dry:
        return f"run {r['id']}: would {'update #' + str(issue['number']) if issue else 'open'} {title}"
    if issue is None:
        return f"run {r['id']}: opened failure issue #{fw._create(sig, r, key, run)['number']}"
    return f"run {r['id']}: {fw._recur(issue, sig, r, key, run)} failure issue #{issue['number']}"


def sweep(now, key, dry=False, run=liveness.gh):
    """Every kept failed run of the last SWEEP_HOURS hours, oldest first, at most MAX_NEW new issues."""
    since = now - datetime.timedelta(hours=SWEEP_HOURS)
    out, new = [], 0
    for r in fw.collect(since, now, run, SELF_WF):
        if new >= fw.MAX_NEW:
            out.append("sweep: flood cap reached, rest waits for the next tick")
            break
        line = handle(r, key, dry, run)
        new += "opened" in line or "would open" in line
        out.append(line)
    if not dry:
        out += [f"closed expected-cancel issue #{n}"
                for n in fw.close_expected(fw.load_issues(key, run), set(), key, run)]
    return out


# --- self-healing (design 0012 section 4.4) ------------------------------------------------------

def _jl(run, *args):
    return json.loads(run(*args))


def _at(ts):
    return datetime.datetime.fromisoformat(ts)


def _age_h(ts, now):
    return (now - _at(ts)).total_seconds() / 3600


def max_dev(value):
    """Repo variable MAX_DEV; a missing or invalid value falls back to the default."""
    text = (value or "").strip()
    return int(text) if text.isdigit() and int(text) > 0 else DEFAULT_MAX_DEV


def orchestrator_unhealthy(now, orch_runs):
    """Its newest run of the last HEAL_HOURS hours ended cancelled, failed or timed out."""
    recent = [r for r in orch_runs if _age_h(r["createdAt"], now) <= HEAL_HOURS]
    return bool(recent) and recent[0].get("conclusion") in UNHEALTHY


def fallback(trusted, issues, closed, unhealthy, cap, dry, run):
    """Section 4.4.2: set agent:dev on open signed watch issues, only while the orchestrator is unhealthy and
    fewer than MAX_DEV issues carry agent:dev. A healthy orchestrator decides itself: nothing happens."""
    if not unhealthy:
        return []
    dev = sum("agent:dev" in stalled_dev.names(i) and "parked" not in stalled_dev.names(i) for i in issues)
    out = []
    for i in sorted(trusted, key=lambda x: x["number"]):
        labels = stalled_dev.names(i)
        if not i["title"].startswith(fw.TITLE_PREFIX) or labels & {"agent:dev", "parked"} or i["number"] in closed:
            continue
        if "prio:1" not in labels and re.search(r"^Failures: 1$", i.get("body") or "", re.MULTILINE):
            continue  # one failed run is often a blip (prefilter.first_failure): wait for the second
        if dev >= cap:
            out.append(f"fallback: MAX_DEV {cap} reached, #{i['number']} waits")
            break
        if not dry:
            add_labels("issue", i["number"], ["agent:dev"], run)
        i["labels"] = [*(i.get("labels") or []), {"name": "agent:dev"}]
        dev += 1
        out.append(f"fallback: {'would set' if dry else 'set'} agent:dev on #{i['number']} (orchestrator unhealthy)")
    return out


def _covers(r, issue):
    title = r.get("displayTitle") or ""
    return title == issue["title"] or bool(re.search(rf"#{issue['number']}\b", title))


def after_mark(issue, run_obj, run):
    """True if RUN_OBJ was created after stalled:1 was last set (issue timeline). No labeled event: False."""
    events = fw._api(f"repos/{{owner}}/{{repo}}/issues/{issue['number']}/timeline?per_page=100", run)
    marks = [_at(e["created_at"]) for e in events if e.get("event") == "labeled"
             and (e.get("label") or {}).get("name") == stalled_dev.STALLED]
    return bool(marks) and _at(run_obj["createdAt"]) > max(marks)


def restart_failed(now, trusted, closed, runs, dry, run):
    """Section 4.4.3: the newest agent run of an agent:dev issue without a closing PR failed -> agent:dev again
    once (stalled:1, the restart of stalled_dev); failed again -> parked. A failed run
    older than the stalled:1 mark is the one that caused the restart: the issue waits for the restart's run."""
    out = []
    for i in trusted:
        n, labels = i["number"], stalled_dev.names(i)
        if "agent:dev" not in labels or "parked" in labels or n in closed:
            continue
        mine = sorted((r for r in runs if _covers(r, i)), key=lambda r: r["createdAt"], reverse=True)
        if not mine or mine[0].get("conclusion") not in FAILED_AGENT or _age_h(mine[0]["createdAt"], now) > RESTART_HOURS:
            continue
        if fw.turn_cap(mine[0].get("wf"), mine[0].get("databaseId"), mine[0].get("conclusion"), run):
            continue  # the run did its work and hit the turn cap (#562): a restart would only repeat it
        parked = stalled_dev.STALLED in labels
        if parked and not after_mark(i, mine[0], run):
            continue
        if parked and not dry:
            park("issue", n, "the task failed again after the one restart (stalled:1) and no open PR closes it", run)
        elif not dry:
            stalled_dev.restart(i, run)
        out.append(f"restart: {'would ' if dry else ''}{'park #' if parked else 'agent:dev again on #'}{n}")
    return out


def heal(now, key, env, dry=False, run=liveness.gh):
    """One self-healing tick. Only signed issues authored by AUTHOR_BOT are changed; without AUTHOR_BOT nothing is."""
    bot = (env.get("AUTHOR_BOT") or "").strip()
    if not bot:
        return ["self-healing: AUTHOR_BOT is not set, skipped"]
    issues = _jl(run, "issue", "list", "--state", "open", "--limit", "200", "--json", "number,title,body,labels,author")
    trusted = [i for i in issues if trusted_issues.is_guard_issue(i, bot, key)]
    closed = stalled_dev.closed_by(_jl(run, "pr", "list", "--state", "open", "--limit", "100", "--json", "number,body"))
    orch_runs = _jl(run, "run", "list", "--workflow", ORCHESTRATOR, "--limit", "20", "--json", "conclusion,createdAt")
    out = fallback(trusted, issues, closed, orchestrator_unhealthy(now, orch_runs), max_dev(env.get("MAX_DEV")), dry, run)
    agent_runs = []
    for wf in ("agent-dev.yml", "agent-fix.yml"):
        listed = _jl(run, "run", "list", "--workflow", wf, "--limit", "20",
                     "--json", "displayTitle,conclusion,createdAt,databaseId")
        agent_runs += [{**r, "wf": wf} for r in listed]
    return out + restart_failed(now, trusted, closed, agent_runs, dry, run)


def main(env=None, run=liveness.gh, now=None):
    env = os.environ if env is None else env
    if env.get("FAILURE_WATCH", "").strip().lower() == "off":
        return ["failure watch is off"]
    if reason := budget.low(budget.BACKGROUND, run):
        return [reason]
    key = guard_mark.key_from_env()
    if not key:
        # Nothing can be signed, so no issue would be trusted: skip with a warning instead of a red run that the
        # liveness guard then reports as an overdue watcher (issue 676).
        return ["::warning::GUARD_KEY is not set: nothing can be signed, watcher skipped"]
    dry = env.get("DRY_RUN", "").strip().lower() in ("1", "true", "yes", "on")
    run = readonly(run) if dry else run
    run_id = (env.get("RUN_ID") or "").strip()
    if not run_id:
        now = now or datetime.datetime.now(datetime.UTC)
        return sweep(now, key, dry, run) + heal(now, key, env, dry, run)
    if not run_id.isdigit():
        raise SystemExit("RUN_ID must be a number")
    r = fw._api(f"repos/{{owner}}/{{repo}}/actions/runs/{run_id}", run)
    return [handle(r, key, dry, run)]


if __name__ == "__main__":
    try:
        for line in main():
            print(line)
    except ghcall.GhError as e:
        if not ghcall.rate_limited(e.stderr):
            raise
        # The budget comes back within the hour and the sweep catches up: a red watcher would only report itself.
        print("::warning::GitHub API rate limit reached: watcher skipped, the next sweep catches up")
    sys.exit(0)
