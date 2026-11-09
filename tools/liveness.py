"""Shared helpers: read back comments after posting, and flag overdue scheduled runs.

- post_comment / verify_body: a comment or issue body Daniel depends on is read back; a missing one raises ReadbackError.
- overdue_runs / ensure_overdue_issue: a scheduled workflow whose last successful run is older than 2 intervals
  gets exactly one open `prio:1` issue (found by its title, so the next tick creates no second one).
Needs the gh CLI (GH_TOKEN, GH_REPO). Prints numbers and titles, never tokens.
"""
import datetime
import json
import subprocess

# workflow file -> (label, expected interval in minutes)
SCHEDULED = {
    "orchestrator.yml": ("orchestrator", 24 * 60),
    "scout.yml": ("scout", 30 * 24 * 60),
    "rule-keeper.yml": ("rule keeper", 7 * 24 * 60),
    "weekly-summary.yml": ("weekly summary", 7 * 24 * 60),
}
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


def is_overdue(created_at, interval_min, now):
    """No successful run at all, or older than OVERDUE_FACTOR intervals."""
    if not created_at:
        return True
    return (now - _ts(created_at)).total_seconds() / 60 > OVERDUE_FACTOR * interval_min


def overdue_runs(successes, now):
    """Labels of scheduled workflows that are overdue."""
    return [label for wf, (label, interval) in SCHEDULED.items()
            if is_overdue((successes.get(wf) or {}).get("createdAt"), interval, now)]


def overdue_title(label):
    return f"Overdue scheduled run: {label}"


def ensure_overdue_issue(label, detail, run=gh):
    """Create the prio:1 issue for an overdue run unless an open one exists. Returns its number or None."""
    title = overdue_title(label)
    found = json.loads(run("issue", "list", "--state", "open", "--search", f'"{title}" in:title',
                           "--json", "number,title"))
    if any(i["title"] == title for i in found):
        return None
    out = run("issue", "create", "--title", title, "--label", OVERDUE_LABEL, "--body",
              f"The scheduled run of the {label} has no successful run within {OVERDUE_FACTOR} intervals. {detail}")
    return out.strip().rsplit("/", 1)[-1]


def flag_overdue(successes, now, run=gh):
    """One issue per overdue run, none for runs that already have one. Returns (overdue labels, new issue numbers)."""
    late = overdue_runs(successes, now)
    new = [n for n in (ensure_overdue_issue(label, "Check the workflow runs.", run) for label in late) if n]
    return late, new


def status_run_stale(run=gh, now=None):
    """True if the newest successful status run is older than STATUS_MAX_AGE_MIN (or there is none)."""
    now = now or datetime.datetime.now(datetime.UTC)
    last = last_success("status.yml", run)
    return last is None or (now - _ts(last["createdAt"])).total_seconds() / 60 > STATUS_MAX_AGE_MIN
