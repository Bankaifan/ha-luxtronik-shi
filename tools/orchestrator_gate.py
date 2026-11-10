"""Decide whether this orchestrator run may start (design 0007, sections 4.2, 4.4, 4.5).

`issues: labeled` keeps its rule: label `approved`/`auto-ok`, labeller is OWNER (checked here, the event alone is not
trusted) and no earlier orchestrator run was created at most WINDOW seconds before this one.
The other event types (issues opened/edited/closed, issue_comment, pull_request(_target), pull_request_review) need:
1. ORCHESTRATOR_EVENTS=on (unset or anything else: skip),
2. a sender that is OWNER, the author app or the approver app,
3. a live check: the object is re-read and its author login equals the sender (payload fields are not trusted),
4. no author-app event inside an orchestrator run window (self-loop rule G: run start .. run end + LOOP_GRACE),
5. no newer pending orchestrator run (debounce rule E: a burst gives one run, on the last event),
6. the brake: 3 runs in a row started by the author app, each at most BRAKE_GAP after the previous, refuse and
   comment once in STATUS_ISSUE.
Other events (schedule, workflow_dispatch, workflow_run) pass here; their own `if` in orchestrator.yml decides.
Prints `true` or `false` on stdout, the reason on stderr.

Needs the gh CLI (GH_TOKEN, GH_REPO). Environment: EVENT, EVENT_ACTION, LABEL, SENDER, RUN_ID, OWNER (default
Bankaifan), AUTHOR_BOT, APPROVER_BOT, NUMBER, COMMENT_ID, REVIEW_ID, EVENT_AT (ISO time), STATUS_ISSUE,
ORCHESTRATOR_EVENTS.
"""
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from itertools import pairwise

from agent_guard import gh, same_login

GATED = ("approved", "auto-ok")
WINDOW = 180  # seconds, label events
LOOP_GRACE = 60  # seconds after a run ended in which its own echo is still ignored
BRAKE_RUNS = 3
BRAKE_GAP = 300  # seconds
EVENTS = ("issues", "issue_comment", "pull_request", "pull_request_target", "pull_request_review")
PENDING = ("queued", "pending", "waiting", "requested")
BRAKE_MARK = "<!-- orchestrator-brake -->"


def parse(ts):
    return datetime.fromisoformat(ts)  # accepts the trailing Z of gh's createdAt (Python 3.11+)


def debounced(run_id, created, runs):
    """True if an earlier run (lower id) was created at most WINDOW seconds before `created` (a datetime)."""
    return any(r["databaseId"] < run_id and 0 <= (created - parse(r["createdAt"])).total_seconds() <= WINDOW
               for r in runs)


def in_run_window(at, run_id, runs):
    """True if `at` lies in [start, end + LOOP_GRACE] of another orchestrator run (running ones have no end)."""
    for r in runs:
        if r["databaseId"] == run_id or r.get("status") in PENDING:
            continue
        end = (parse(r["updatedAt"]).timestamp() + LOOP_GRACE) if r.get("status") == "completed" else float("inf")
        if parse(r["createdAt"]).timestamp() <= at.timestamp() <= end:
            return True
    return False


def newer_pending(run_id, runs):
    return any(r["databaseId"] > run_id and r.get("status") in PENDING for r in runs)


def braking(run_id, runs, author_bot):
    """True if the last BRAKE_RUNS runs (this one included) came from the author app, each close after the previous."""
    last = sorted((r for r in runs if r["databaseId"] <= run_id), key=lambda r: r["databaseId"])[-BRAKE_RUNS:]
    if len(last) < BRAKE_RUNS or not all(same_login(r.get("sender", ""), author_bot) for r in last):
        return False
    times = [parse(r["createdAt"]).timestamp() for r in last]
    return all(0 <= b - a <= BRAKE_GAP for a, b in pairwise(times))


def decide_event(sender, owner, run_id, runs, now, *, author_bot="", approver_bot="", live=None, event_at=None,
                 enabled=False):
    """Rules 1-6 for the non-label events. `live`: author login read live from the object, or None."""
    if not enabled:
        return False, "ORCHESTRATOR_EVENTS is not on"
    if not any(same_login(sender, who) for who in (owner, author_bot, approver_bot)):
        return False, f"sender {sender!r} is not the owner or an agent app"
    if not live or not same_login(live, sender):
        return False, f"live check failed: object author {live!r}, sender {sender!r}"
    if same_login(sender, author_bot) and in_run_window(event_at or now, run_id, runs):
        return False, "author app event inside an orchestrator run window (own echo)"
    if newer_pending(run_id, runs):
        return False, "a newer orchestrator run is pending and sees this event too"
    if braking(run_id, runs, author_bot):
        return False, "brake: 3 orchestrator runs in a row started by the author app"
    return True, "accepted event, last of its burst"


def decide(event, label, sender, owner, run_id, runs, now, *, action="labeled", **kw):
    """Return (run, reason). `runs`: recent orchestrator runs as {databaseId, createdAt, ...}; `now`: a datetime."""
    if event in EVENTS and not (event == "issues" and action == "labeled"):
        return decide_event(sender, owner, run_id, runs, now, **kw)
    if event != "issues":
        return True, f"{event} is not a label event"
    if label not in GATED:
        return False, f"label {label!r} does not start the orchestrator"
    if not same_login(sender, owner):
        return False, f"labelled by {sender!r}, not by the owner"
    own = next((r for r in runs if r["databaseId"] == run_id), None)
    created = parse(own["createdAt"]) if own else now
    if debounced(run_id, created, runs):
        return False, f"an earlier orchestrator run was created within {WINDOW} seconds"
    return True, "owner label, no recent run"


def live_login(event, action, env, run=gh):
    """Read the object live; return the login that must equal the sender, or None if it is gone or unknown."""
    repo, number = env.get("GH_REPO", ""), env.get("NUMBER", "")
    sender = env.get("SENDER", "")
    try:
        if event == "issue_comment":
            path, key = f"repos/{repo}/issues/comments/{env.get('COMMENT_ID', '')}", "user"
        elif event == "pull_request_review":
            path, key = f"repos/{repo}/pulls/{number}/reviews/{env.get('REVIEW_ID', '')}", "user"
        elif event == "issues":
            path, key = f"repos/{repo}/issues/{number}", "user"
        else:
            path, key = f"repos/{repo}/pulls/{number}", "user"
        obj = json.loads(run("api", path))
    except (subprocess.CalledProcessError, ValueError, OSError):
        return None
    if not isinstance(obj, dict) or not obj.get("number", obj.get("id")):
        return None
    if event in ("issues", "pull_request", "pull_request_target") and action != "opened":
        return sender  # edited/closed: the item exists; who acted is the (already filtered) sender
    return (obj.get(key) or {}).get("login")


def fetch_runs(repo, run=gh):
    out = run("api", f"repos/{repo}/actions/workflows/orchestrator.yml/runs?per_page=30", "--jq",
              "[.workflow_runs[] | {databaseId: .id, createdAt: .created_at, updatedAt: .updated_at, status,"
              " event, sender: .triggering_actor.login}]")
    return json.loads(out)


def announce_brake(issue, run=gh):
    """Comment once in the status issue (no second comment while our marker is the latest one)."""
    if not issue:
        return
    comments = json.loads(run("issue", "view", issue, "--json", "comments"))["comments"]
    if comments and BRAKE_MARK in comments[-1]["body"]:
        return
    run("issue", "comment", issue, "--body", f"{BRAKE_MARK}\nOrchestrator brake: 3 runs in a row were started by "
        "the author app within 5 minutes each. Refusing event runs until a run starts from another sender.")


def main() -> int:
    env = os.environ
    event, action = env.get("EVENT", ""), env.get("EVENT_ACTION", "labeled" if env.get("EVENT") == "issues" else "")
    run_id = int(env.get("RUN_ID", "0"))
    now = datetime.now(UTC)
    kw = {}
    runs = []
    if event in EVENTS and not (event == "issues" and action == "labeled"):
        runs = fetch_runs(env.get("GH_REPO", ""))
        kw = {"author_bot": env.get("AUTHOR_BOT", ""), "approver_bot": env.get("APPROVER_BOT", ""),
              "enabled": env.get("ORCHESTRATOR_EVENTS") == "on",
              "event_at": parse(env["EVENT_AT"]) if env.get("EVENT_AT") else None,
              "live": live_login(event, action, env)}
    elif event == "issues":
        runs = json.loads(gh("run", "list", "--workflow", "orchestrator.yml", "--limit", "20",
                             "--json", "databaseId,createdAt"))
    run, reason = decide(event, env.get("LABEL", ""), env.get("SENDER", ""), env.get("OWNER", "Bankaifan"),
                         run_id, runs, now, action=action, **kw)
    if reason.startswith("brake"):
        announce_brake(env.get("STATUS_ISSUE", ""))
    print(reason, file=sys.stderr)
    print("true" if run else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
