"""Stalled agent:dev issues (issue #366): restart once, then park with Daniel. Model-free, called by status.py.

An open issue with agent:dev is stalled when no open PR closes it (closing keywords only, `Refs` does not count), no
queued or in-progress agent-dev run covers it, and the agent:dev label is older than STALL_MIN minutes.
  first stall:  stalled:1 is set, agent:dev is removed and set again (the restart of restart.restart_issue, no slip)
  second stall: needs-human, OWNER as assignee, German yes/no note with the decision marker (yes restarts, no closes)
A run covers an issue if its title names the issue or the issue title, or names no issue at all (in doubt: no restart).
Issues in `skip` were handled by the orphan step of status.py in the same run and are left alone.
Reads: open PRs, queued and in-progress agent-dev runs. Writes: the labels and comments above, and the stalled:1 mark
removed when an open PR closes the issue. Never raises: a failing query or write only ends the check.
"""
import datetime
import json
import re
import subprocess

import decision
import liveness
from agent_guard import add_labels

STALL_MIN = 60
STALLED = "stalled:1"
_CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.IGNORECASE)
_NUMBER = re.compile(r"#\d+\b")

NOTE_RESTART = (
    f"Status run: agent:dev for more than {STALL_MIN} min with no queued or running agent-dev run and no open PR "
    "that closes this issue. Restarting once (stalled:1): agent:dev is set again."
)
NOTE_PARKED = (
    "Hallo Daniel, @Bankaifan, dieses Issue haengt fest: agent:dev steht, aber seit mehr als "
    f"{STALL_MIN} min laeuft dafuer kein Agent-Lauf und kein offener PR schliesst es, auch nach dem einen "
    "automatischen Neustart (stalled:1) nicht. Schlimmster Fall: die Aufgabe bleibt liegen, sonst passiert nichts. "
    "Frage: Soll die Aufgabe neu gestartet werden (ja) oder das Issue geschlossen werden (nein)?\n"
    + decision.build(yes="restart-issue", no="close-issue")
)


def jlist(run, *args):
    return json.loads(run(*args))


def names(item):
    return {lab["name"] for lab in item.get("labels") or []}


def minutes_since(ts, now):
    return (now - datetime.datetime.fromisoformat(ts)).total_seconds() / 60


def closed_by(prs):
    """Issue numbers that an open PR closes with a closing keyword."""
    out = set()
    for p in prs:
        out.update(int(n) for n in _CLOSES.findall(p.get("body") or ""))
    return out


def covers(run, issue):
    """True if this agent-dev run may be working on the issue: its title names the issue, or it names no issue."""
    title = run.get("displayTitle") or ""
    return (bool(re.search(rf"#{issue['number']}\b", title)) or title == issue["title"]
            or not _NUMBER.search(title))


def stalled(issues, closed, runs, labeled_at, now):
    out = []
    for i in issues:
        if "needs-human" in names(i) or i["number"] in closed or any(covers(r, i) for r in runs):
            continue
        if minutes_since(labeled_at(i), now) > STALL_MIN:
            out.append(i)
    return out


def restart(issue, run):
    """First stall: mark, comment, agent:dev removed and set again so the labeled event fires."""
    n = issue["number"]
    add_labels("issue", n, [STALLED], run)
    liveness.post_comment("issue", n, NOTE_RESTART, run)
    run("issue", "edit", str(n), "--remove-label", "agent:dev")
    add_labels("issue", n, ["agent:dev"], run)


def park(issue, owner, run):
    """Second stall: needs-human, owner as assignee (issues get no review request), the German note once."""
    n = issue["number"]
    add_labels("issue", n, ["needs-human"], run)
    try:
        run("issue", "edit", str(n), "--add-assignee", owner)
    except subprocess.CalledProcessError:
        print(f"assignee {owner} on issue #{n} failed")
    liveness.post_comment("issue", n, NOTE_PARKED, run)


def check(issues, labeled_at, now, run, owner, skip=()):
    """Actions taken, as text for the status run. Never raises: a failing query or write only ends the check."""
    actions = []
    try:
        prs = jlist(run, "pr", "list", "--state", "open", "--limit", "100", "--json", "number,body")
        runs = []
        for st in ("queued", "in_progress"):
            runs += jlist(run, "run", "list", "--workflow", "agent-dev.yml", "--status", st, "--limit", "50",
                          "--json", "displayTitle")
        closed = closed_by(prs)
        for i in issues:
            if STALLED in names(i) and i["number"] in closed:  # real progress: the next stall gets one restart again
                run("issue", "edit", str(i["number"]), "--remove-label", STALLED)
                actions.append(f"stalled mark removed from #{i['number']}: an open PR closes it")
        for i in stalled(issues, closed, runs, labeled_at, now):
            n = i["number"]
            if n in skip:
                continue
            try:
                if STALLED in names(i):
                    park(i, owner, run)
                    actions.append(f"stalled issue #{n}: parked with Daniel")
                else:
                    restart(i, run)
                    actions.append(f"stalled issue #{n}: agent:dev set again (once)")
            except (subprocess.CalledProcessError, OSError, ValueError, liveness.ReadbackError) as e:
                actions.append(f"stalled issue #{n}: failed ({type(e).__name__})")
    except Exception as e:  # noqa: BLE001 - the status issue must always be written
        print(f"stalled check failed: {type(e).__name__}")
    return actions
