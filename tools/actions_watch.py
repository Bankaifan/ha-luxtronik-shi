"""Actions watcher entry (design 0012, sections 4.1-4.2): one failed workflow run -> rerun once or one signed issue.

`actions_watch.py` handles the run in RUN_ID (a `workflow_run` event); without RUN_ID it sweeps the runs of the last
SWEEP_HOURS hours (schedule / workflow_dispatch, for events GitHub did not deliver). Everything is idempotent, so a
replaced pending run loses nothing. A startup failure, or a cancelled run whose job never started, is rerun once (only
while run_attempt is 1, no state); anything else opens or updates the signed `Failing workflow:` issue through
tools/failure_watch.py. Bodies are fixed script text. DRY_RUN=1 prints the actions and writes nothing.
The sweep also self-heals (section 4.4): fallback `agent:dev` while the orchestrator is unhealthy and MAX_DEV has room,
one restart of failed agent work, a `Kicked: n` counter for unstarted approved issues. It only touches issues signed
with GUARD_KEY and authored by AUTHOR_BOT (env AUTHOR_BOT, OWNER, MAX_DEV).
FAILURE_WATCH=off skips it. Needs the gh CLI (GH_TOKEN, GH_REPO) and GUARD_KEY (script step only).
"""
import datetime
import json
import os
import re
import subprocess
import sys

import budget
import decision
import failure_watch as fw
import guard_mark
import liveness
import stalled_dev
import trusted_issues
from agent_guard import add_labels

SELF_WF = "watch.yml"  # the watcher never watches its own runs (no loop)
SWEEP_HOURS = 2
RERUN_CONCLUSIONS = ("startup_failure", "cancelled")
WRITES = ("create", "edit", "comment", "close", "reopen", "rerun")  # gh subcommands that change state

# Self-healing (design 0012 section 4.4), sweep only. Everything is bounded: one fallback label per issue,
# stalled:1 then needs-human, Kicked: 2 then needs-human.
ORCHESTRATOR = "orchestrator.yml"
UNHEALTHY = ("cancelled", "failure", "timed_out")  # conclusion of the newest orchestrator run in the last HEAL_HOURS
HEAL_HOURS = 2
FAILED_AGENT = ("failure", "timed_out", "cancelled")
RESTART_HOURS = 4  # a failed agent run older than this is history, not a restart trigger
UNSTARTED_MIN = 15
KICK_TITLE = "Unstarted run: orchestrator"
KICK_MAX = 2
DEFAULT_MAX_DEV = 4
_KICKED = re.compile(r"^Kicked: (\d+)$", re.MULTILINE)
NOTE_FAILED = (
    "Hallo Daniel, @Bankaifan, die Aufgabe in diesem Issue ist nach dem einen automatischen Neustart (stalled:1) "
    "wieder fehlgeschlagen und es gibt keinen offenen PR dazu. Schlimmster Fall: die Aufgabe bleibt liegen, "
    "sonst passiert nichts. Frage: Soll die Aufgabe noch einmal gestartet werden (ja) oder das Issue "
    "geschlossen werden (nein)?\n" + decision.build(yes="restart-issue", no="close-issue")
)
NOTE_KICKED = (
    "Hallo Daniel, @Bankaifan, freigegebene Issues bekamen keinen Orchestrator-Lauf, auch nicht nach zwei "
    "automatischen Starts (Kicked: 2). Schlimmster Fall: freigegebene Aufgaben bleiben liegen, sonst passiert "
    "nichts. Frage: Soll der Orchestrator noch einmal gestartet werden (ja) oder soll dieses Issue "
    "geschlossen werden (nein)?\n" + decision.build(yes="restart-issue", no="close-issue")
)


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


def _park(number, note, owner, run):
    """needs-human, owner as assignee (issues get no review request), the German note as the last comment."""
    add_labels("issue", number, ["needs-human"], run)
    try:
        run("issue", "edit", str(number), "--add-assignee", owner)
    except subprocess.CalledProcessError:
        print(f"assignee {owner} on issue #{number} failed")
    liveness.post_comment("issue", number, note, run)


def fallback(trusted, issues, closed, unhealthy, cap, dry, run):
    """Section 4.4.2: set agent:dev on open signed watch issues, only while the orchestrator is unhealthy and
    fewer than MAX_DEV issues carry agent:dev. A healthy orchestrator decides itself: nothing happens."""
    if not unhealthy:
        return []
    dev = sum("agent:dev" in stalled_dev.names(i) and "needs-human" not in stalled_dev.names(i) for i in issues)
    out = []
    for i in sorted(trusted, key=lambda x: x["number"]):
        labels = stalled_dev.names(i)
        if not i["title"].startswith(fw.TITLE_PREFIX) or labels & {"agent:dev", "needs-human"} or i["number"] in closed:
            continue
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


def restart_failed(now, trusted, closed, runs, owner, dry, run):
    """Section 4.4.3: the newest agent run of an agent:dev issue without a closing PR failed -> agent:dev again
    once (stalled:1, the restart of stalled_dev); failed again -> needs-human with the German note. A failed run
    older than the stalled:1 mark is the one that caused the restart: the issue waits for the restart's run."""
    out = []
    for i in trusted:
        n, labels = i["number"], stalled_dev.names(i)
        if "agent:dev" not in labels or "needs-human" in labels or n in closed:
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
            _park(n, NOTE_FAILED, owner, run)
        elif not dry:
            stalled_dev.restart(i, run)
        out.append(f"restart: {'would ' if dry else ''}{'park #' if parked else 'agent:dev again on #'}{n}")
    return out


def kicked(issue):
    m = _KICKED.search(guard_mark.split(issue["body"])[0])
    return int(m.group(1)) if m else 0


def kick_body(count):
    return f"An approved issue got no orchestrator run, so the watcher started it.\nKicked: {count}"


def unstarted(now, issues, owner, orch_runs, run):
    """Open issues whose approved/auto-ok label (set by OWNER) is older than UNSTARTED_MIN and that no orchestrator
    run followed (a skipped or cancelled run does not count)."""
    out = []
    for i in issues:
        gated = stalled_dev.names(i) & set(trusted_issues.GATED)
        if not gated or "needs-human" in stalled_dev.names(i):
            continue
        events = fw._api(f"repos/{{owner}}/{{repo}}/issues/{i['number']}/timeline?per_page=100", run)
        times = [e["created_at"] for e in events if e.get("event") == "labeled"
                 and (e.get("label") or {}).get("name") in gated
                 and trusted_issues.label_set_by(events, e["label"]["name"], owner)]
        if not times or (now - _at(max(times))).total_seconds() < UNSTARTED_MIN * 60:
            continue
        if not any(r["createdAt"] >= max(times) and r.get("conclusion") not in ("skipped", "cancelled")
                   for r in orch_runs):
            out.append(i["number"])
    return out


def kick(now, issues, trusted, key, owner, orch_runs, dry, run):
    """Section 4.4.4: dispatch the orchestrator for unstarted approved issues, counted as `Kicked: n` in the signed
    issue `Unstarted run: orchestrator`; at KICK_MAX the issue gets needs-human and the German note."""
    late = unstarted(now, issues, owner, orch_runs, run)
    if not late:
        return []
    state = next((i for i in trusted if i["title"] == KICK_TITLE), None)
    count = kicked(state) if state else 0
    if count >= KICK_MAX:
        return [f"kick: already kicked {count} times, waiting for Daniel (#{state['number']})"]
    if dry:
        return [f"kick: would dispatch {ORCHESTRATOR} (Kicked: {count + 1}) for #{late[0]}"]
    run("workflow", "run", ORCHESTRATOR)
    if state is None:
        body = guard_mark.sign(KICK_TITLE, kick_body(1), key)
        run("issue", "create", "--title", KICK_TITLE, "--label", liveness.OVERDUE_LABEL, "--body", body)
        return [f"kick: dispatched {ORCHESTRATOR} (Kicked: 1) for #{late[0]}"]
    fw._write(state, kick_body(count + 1), key, run)
    if count + 1 >= KICK_MAX:
        _park(state["number"], NOTE_KICKED, owner, run)
    return [f"kick: dispatched {ORCHESTRATOR} (Kicked: {count + 1}) for #{late[0]}"]


def heal(now, key, env, dry=False, run=liveness.gh):
    """One self-healing tick. Only signed issues authored by AUTHOR_BOT are changed; without AUTHOR_BOT nothing is."""
    bot = (env.get("AUTHOR_BOT") or "").strip()
    if not bot:
        return ["self-healing: AUTHOR_BOT is not set, skipped"]
    owner = (env.get("OWNER") or "Bankaifan").strip()
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
    out += restart_failed(now, trusted, closed, agent_runs, owner, dry, run)
    return out + kick(now, issues, trusted, key, owner, orch_runs, dry, run)


def main(env=None, run=liveness.gh, now=None):
    env = os.environ if env is None else env
    if env.get("FAILURE_WATCH", "").strip().lower() == "off":
        return ["failure watch is off"]
    if reason := budget.low(budget.BACKGROUND, run):
        return [reason]
    key = guard_mark.key_from_env()
    if not key:
        raise SystemExit("GUARD_KEY is not set: nothing can be signed")
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
    for line in main():
        print(line)
    sys.exit(0)
