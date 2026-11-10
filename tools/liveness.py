"""Shared helpers: read back comments after posting, and flag overdue scheduled runs.

- post_comment / verify_body: a comment or issue body Daniel depends on is read back; a missing one raises ReadbackError.
- overdue_runs / ensure_overdue_issue: a scheduled workflow whose last successful run is older than 2 intervals
  gets exactly one open `prio:1` issue (found by its title, so the next tick creates no second one).
Needs the gh CLI (GH_TOKEN, GH_REPO). Prints numbers and titles, never tokens.
"""
import datetime
import json
import os
import subprocess

import guard_mark

# workflow file -> (label, expected interval in minutes)
SCHEDULED = {
    "orchestrator.yml": ("orchestrator", 24 * 60),
    "scout.yml": ("scout", 30 * 24 * 60),
    "rule-keeper.yml": ("rule keeper", 7 * 24 * 60),
    "weekly-summary.yml": ("weekly summary", 7 * 24 * 60),
    "nightly.yml": ("nightly heavy tests", 24 * 60),
}
# workflow file -> repo variable that must be exactly "true" for the workflow to be expected to run
GATED = {"nightly.yml": "NIGHTLY_HEAVY_TESTS"}
OVERDUE_FACTOR = 2
OVERDUE_LABEL = "prio:1"
STATUS_MAX_AGE_MIN = 180  # the weekly summary flags a status run older than 3 hours


class ReadbackError(RuntimeError):
    pass


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def _norm(text):
    return " ".join((text or "").split())


def verify_body(kind, number, body, run=gh):
    """Read the issue/PR body back; raise ReadbackError unless it matches what was written."""
    got = json.loads(run(kind, "view", str(number), "--json", "body")).get("body")
    if _norm(got) != _norm(body):
        raise ReadbackError(f"{kind} #{number}: body not as written after update")


def post_comment(kind, number, body, run=gh):
    """Post a comment and read the comments back; raise ReadbackError if it is not there."""
    run(kind, "comment", str(number), "--body", body)
    comments = json.loads(run(kind, "view", str(number), "--json", "comments")).get("comments") or []
    if not any(_norm(c.get("body")) == _norm(body) for c in comments):
        raise ReadbackError(f"{kind} #{number}: comment missing after posting")


def _ts(s):
    return datetime.datetime.fromisoformat(s)


def last_success(workflow, run=gh):
    """createdAt of the newest successful run of a workflow, or None."""
    runs = json.loads(run("run", "list", "--workflow", workflow, "--status", "success", "--limit", "1",
                          "--json", "createdAt,url"))
    return runs[0] if runs else None


def last_successes(run=gh):
    """{workflow: run or None} for the scheduled workflows."""
    return {wf: last_success(wf, run) for wf in SCHEDULED}


def added_at(workflow, run=gh):
    """When the workflow file was added to the repo (GitHub's created_at), or None if unknown."""
    try:
        return run("api", f"repos/{{owner}}/{{repo}}/actions/workflows/{workflow}", "--jq", ".created_at").strip() or None
    except (subprocess.CalledProcessError, OSError):
        return None


def added_dates(successes, run=gh):
    """{workflow: created_at} for the scheduled workflows that never succeeded (the grace baseline)."""
    return {wf: added_at(wf, run) for wf in SCHEDULED if not successes.get(wf)}


def is_overdue(created_at, interval_min, now, since=None):
    """Last success (or, if there is none, the date the workflow was added) older than OVERDUE_FACTOR intervals.
    No success and no known add date counts as overdue."""
    ref = created_at or since
    if not ref:
        return True
    return (now - _ts(ref)).total_seconds() / 60 > OVERDUE_FACTOR * interval_min


def gate_open(workflow, variables=None):
    """False for a gated workflow whose repo variable is not exactly "true" (its job is skipped, so nothing is due).
    `variables` defaults to the environment; an ungated workflow is always open."""
    var = GATED.get(workflow)
    if var is None:
        return True
    return (os.environ if variables is None else variables).get(var) == "true"


def overdue_runs(successes, now, added=None, variables=None):
    """Labels of scheduled workflows that are overdue. `added`: {workflow: created_at} for never-run workflows,
    so a new monthly workflow is not flagged before its first chance to run. Gated workflows are skipped while
    their variable is off (see GATED)."""
    added = added or {}
    return [label for wf, (label, interval) in SCHEDULED.items()
            if gate_open(wf, variables)
            and is_overdue((successes.get(wf) or {}).get("createdAt"), interval, now, added.get(wf))]


def overdue_title(label):
    return f"Overdue scheduled run: {label}"


OVERDUE_DETAIL = "Check the workflow runs."  # fixed script text: the body is signed, so no log or model text in it


def overdue_body(label):
    return f"The scheduled run of the {label} has no successful run within {OVERDUE_FACTOR} intervals. {OVERDUE_DETAIL}"


def ensure_signed_issue(title, body, key=None, run=gh):
    """Create a prio:1 issue unless an open one with this title exists. Returns its number or None.
    The body is signed with GUARD_KEY (guard_mark.py) so the orchestrator trusts it; no key, no signature.
    `body` must be fixed script text, never log or model text."""
    key = guard_mark.key_from_env() if key is None else key
    found = json.loads(run("issue", "list", "--state", "open", "--search", f'"{title}" in:title',
                           "--json", "number,title"))
    if any(i["title"] == title for i in found):
        return None
    out = run("issue", "create", "--title", title, "--label", OVERDUE_LABEL, "--body",
              guard_mark.sign(title, body, key))
    return out.strip().rsplit("/", 1)[-1]


def ensure_overdue_issue(label, key=None, run=gh):
    """Create the prio:1 issue for an overdue run unless an open one exists. Returns its number or None."""
    return ensure_signed_issue(overdue_title(label), overdue_body(label), key, run)


NIGHTLY_TITLE = "Nightly heavy tests failed"
NIGHTLY_BODY = "The nightly run of the slow-marked tests failed on main. Check the nightly workflow runs."


def ensure_nightly_issue(key=None, run=gh):
    """The one open prio:1 issue for a failed nightly heavy-test run (fixed text, no log text)."""
    return ensure_signed_issue(NIGHTLY_TITLE, NIGHTLY_BODY, key, run)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] != ["nightly-failed"]:
        sys.exit("usage: liveness.py nightly-failed")
    print(ensure_nightly_issue() or "open issue exists")


def flag_overdue(successes, now, run=gh, added=None):
    """One issue per overdue run, none for runs that already have one. Returns (overdue labels, new issue numbers)."""
    late = overdue_runs(successes, now, added)
    new = [n for n in (ensure_overdue_issue(label, run=run) for label in late) if n]
    return late, new


def status_run_stale(run=gh, now=None):
    """True if the newest successful status run is older than STATUS_MAX_AGE_MIN (or there is none)."""
    now = now or datetime.datetime.now(datetime.UTC)
    last = last_success("status.yml", run)
    return last is None or (now - _ts(last["createdAt"])).total_seconds() / 60 > STATUS_MAX_AGE_MIN
