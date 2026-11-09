"""Decide whether this orchestrator run may start. Only `issues: labeled` events are gated.

Other events (schedule, workflow_dispatch, workflow_run) pass here; their own `if` in orchestrator.yml decides.
A label event passes when the label is `approved` or `auto-ok` AND the labeller is OWNER (checked here, the event
alone is not trusted) AND no earlier orchestrator run was created at most WINDOW seconds before this one, so a
burst of labels gives one run. Prints `true` or `false` on stdout, the reason on stderr.

Needs the gh CLI (GH_TOKEN, GH_REPO). Environment: EVENT, LABEL, SENDER (labeller), RUN_ID (this run),
OWNER (default Bankaifan).
"""
import json
import os
import sys
from datetime import UTC, datetime

from agent_guard import gh, same_login

GATED = ("approved", "auto-ok")
WINDOW = 180  # seconds


def parse(ts):
    return datetime.fromisoformat(ts)  # accepts the trailing Z of gh's createdAt (Python 3.11+)


def debounced(run_id, created, runs):
    """True if an earlier run (lower id) was created at most WINDOW seconds before `created` (a datetime)."""
    return any(r["databaseId"] < run_id and 0 <= (created - parse(r["createdAt"])).total_seconds() <= WINDOW
               for r in runs)


def decide(event, label, sender, owner, run_id, runs, now):
    """Return (run, reason). `runs`: recent orchestrator runs as {databaseId, createdAt}; `now`: a datetime."""
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


def main() -> int:
    event = os.environ.get("EVENT", "")
    run_id = int(os.environ.get("RUN_ID", "0"))
    runs = []
    if event == "issues":
        runs = json.loads(gh("run", "list", "--workflow", "orchestrator.yml", "--limit", "20",
                             "--json", "databaseId,createdAt"))
    run, reason = decide(event, os.environ.get("LABEL", ""), os.environ.get("SENDER", ""),
                         os.environ.get("OWNER", "Bankaifan"), run_id, runs, datetime.now(UTC))
    print(reason, file=sys.stderr)
    print("true" if run else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
