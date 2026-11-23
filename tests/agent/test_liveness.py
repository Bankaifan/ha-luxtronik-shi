"""End-to-end check of the overdue-run flagging in the status run (issue #98).

A scheduled workflow that never succeeded is measured from the date it was added. These tests run the whole
status run with a fake gh, so the wiring between run_status and the grace baseline is covered, not only the helpers.
"""
import datetime
import json

import liveness
import status as st

NOW = datetime.datetime(2026, 11, 10, 12, 0, tzinfo=datetime.UTC)
ENV = {"GH_REPO": "Bankaifan/agent-template", "OWNER": "Bankaifan", "AUTHOR_BOT": ""}
ISSUE_URL = "https://github.com/Bankaifan/agent-template/issues/7\n"


def fake_gh(added, log, recent=None):
    """Quiet repo: no runs, PRs or issues; never-run workflows return `added[file]` as their created_at.
    `recent`: {workflow file: its newest run}, as `catch_up` reads it."""
    stored = {}

    def run(*args):
        log.append(args)
        if args[:2] == ("run", "list") and args[-1] == "createdAt,status":
            last = (recent or {}).get(args[args.index("--workflow") + 1])
            return json.dumps([last] if last else [])
        if args[0] == "api" and "actions/workflows/" in args[1]:
            return f"{added[args[1].rsplit('/', 1)[-1]]}\n"
        if args[:2] == ("issue", "create"):
            if args[args.index("--title") + 1] == st.TITLE:
                stored["body"] = args[args.index("--body") + 1]
            return ISSUE_URL
        if args[:2] == ("issue", "view"):
            return json.dumps({"body": stored.get("body")})
        return "[]"
    return run


def overdue_creates(log):
    return [a for a in log if a[:2] == ("issue", "create") and a[a.index("--title") + 1].startswith("Overdue")]


def test_status_run_does_not_flag_recently_added_never_run_workflows():
    # All scheduled workflows were added yesterday and none has succeeded yet: nothing is overdue.
    log = []
    added = {wf: "2026-11-09T10:00:39Z" for wf in st.liveness.SCHEDULED}
    added["watch.yml"] = "2026-11-10T11:30:00Z"  # hourly workflow: "yesterday" would already be overdue
    assert st.run_status(ENV, NOW, fake_gh(added, log)) == 0
    assert overdue_creates(log) == []
    body = next(a[a.index("--body") + 1] for a in log
                if a[:2] == ("issue", "create") and a[a.index("--title") + 1] == st.TITLE)
    assert "- scout: never\n" in body
    assert "OVERDUE" not in body


def test_status_run_flags_never_run_workflow_added_long_ago():
    # Control: the same run flags a monthly workflow that was added 61 days ago and never succeeded.
    log = []
    added = {wf: "2026-11-09T10:00:39Z" for wf in st.liveness.SCHEDULED}
    added["scout.yml"] = "2026-09-10T10:00:00Z"
    added["watch.yml"] = "2026-11-10T11:30:00Z"
    ended = {"scout.yml": {"createdAt": "2026-11-10T09:00:00Z", "status": "completed"}}  # started 3 h ago, no success
    assert st.run_status(ENV, NOW, fake_gh(added, log, ended)) == 0
    creates = overdue_creates(log)
    assert [a[a.index("--title") + 1] for a in creates] == ["Overdue scheduled run: scout"]
    assert creates[0][creates[0].index("--label") + 1] == "prio:1"
    assert ("workflow", "run", "scout.yml") not in log


def test_an_overdue_workflow_is_started_by_the_script_before_any_issue_is_opened():
    """agent-template #741/#745: the weekly summary had no run to succeed in; the issue was closed as "nothing to do"
    and opened again on every status tick. Starting the workflow is what makes it not overdue."""
    added = {wf: "2026-11-09T10:00:39Z" for wf in st.liveness.SCHEDULED}
    added["weekly-summary.yml"] = "2026-09-10T10:00:00Z"
    added["watch.yml"] = "2026-11-10T11:30:00Z"
    log = []
    assert st.run_status(ENV, NOW, fake_gh(added, log)) == 0
    assert ("workflow", "run", "weekly-summary.yml") in log and overdue_creates(log) == []
    old = {"weekly-summary.yml": {"createdAt": "2026-11-03T06:17:00Z", "status": "completed"}}  # last week's cancelled run
    log = []
    assert st.run_status(ENV, NOW, fake_gh(added, log, old)) == 0
    assert ("workflow", "run", "weekly-summary.yml") in log and overdue_creates(log) == []
    running = {"weekly-summary.yml": {"createdAt": "2026-11-10T11:50:00Z", "status": "in_progress"}}
    log = []
    assert st.run_status(ENV, NOW, fake_gh(added, log, running)) == 0
    assert ("workflow", "run", "weekly-summary.yml") not in log and overdue_creates(log) == []


def test_catch_up_falls_back_to_the_issue_when_the_start_fails_and_respects_a_short_interval():
    def refused(*args):
        if args[:2] == ("workflow", "run"):
            raise liveness.subprocess.CalledProcessError(1, "gh")
        return "[]"

    assert liveness.catch_up("scout.yml", 43200, NOW, refused) == ""
    half_hour_ago = json.dumps([{"createdAt": "2026-11-10T11:30:00Z", "status": "completed"}])
    two_hours_ago = json.dumps([{"createdAt": "2026-11-10T10:00:00Z", "status": "completed"}])
    assert liveness.catch_up("watch.yml", 60, NOW, lambda *a: half_hour_ago if a[0] == "run" else "") == ""
    assert liveness.catch_up("watch.yml", 60, NOW, lambda *a: two_hours_ago if a[0] == "run" else "") == "started"
    assert liveness.catch_up("scout.yml", 43200, NOW, lambda *a: two_hours_ago if a[0] == "run" else "") == ""


def test_dead_watcher_is_flagged_by_the_status_run():
    # Mutual watch: watch.yml (60 min) is scheduled; no success for 3 h is overdue, 90 min is not.
    assert liveness.SCHEDULED["watch.yml"] == ("actions watcher", 60)
    stale = {"watch.yml": {"createdAt": "2026-11-10T09:00:00+00:00", "url": "u"}}
    assert liveness.overdue_runs(stale, NOW, {"scout.yml": "2026-11-09T10:00:00Z"}).count("actions watcher") == 1
    fresh = {"watch.yml": {"createdAt": "2026-11-10T10:30:00+00:00", "url": "u"}}
    assert "actions watcher" not in liveness.overdue_runs(fresh, NOW)
    log = []
    added = {wf: "2026-11-09T10:00:39Z" for wf in st.liveness.SCHEDULED}
    added["watch.yml"] = "2026-11-01T10:00:00Z"  # added long ago, never succeeded
    ended = {"watch.yml": {"createdAt": "2026-11-10T11:40:00Z", "status": "completed"}}  # ran 20 min ago, no success
    assert st.run_status(ENV, NOW, fake_gh(added, log, ended)) == 0
    creates = overdue_creates(log)
    assert [a[a.index("--title") + 1] for a in creates] == ["Overdue scheduled run: actions watcher"]
    assert "GUARD" not in creates[0][creates[0].index("--body") + 1]


def stale_successes():
    """Every scheduled workflow last succeeded a year ago, so all would be overdue if expected."""
    old = {"createdAt": "2025-10-06T12:00:00+00:00", "url": "u"}
    return {wf: old for wf in liveness.SCHEDULED}


def test_gated_workflow_is_not_overdue_while_its_variable_is_off():
    for variables in ({}, {"NIGHTLY_HEAVY_TESTS": "false"}, {"NIGHTLY_HEAVY_TESTS": ""}, {"NIGHTLY_HEAVY_TESTS": "TRUE"}):
        late = liveness.overdue_runs(stale_successes(), NOW, variables=variables)
        assert "nightly heavy tests" not in late, variables
        assert "scout" in late  # ungated workflows are unchanged


def test_gated_workflow_is_overdue_when_enabled_and_nothing_ran():
    late = liveness.overdue_runs({}, NOW, {"nightly.yml": "2025-10-06T12:00:00Z"}, {"NIGHTLY_HEAVY_TESTS": "true"})
    assert "nightly heavy tests" in late
    fresh = {"nightly.yml": {"createdAt": "2026-11-10T03:23:00+00:00", "url": "u"}}
    assert "nightly heavy tests" not in liveness.overdue_runs(fresh, NOW, variables={"NIGHTLY_HEAVY_TESTS": "true"})


def test_gate_reads_the_environment_by_default(monkeypatch):
    monkeypatch.delenv("NIGHTLY_HEAVY_TESTS", raising=False)
    assert not liveness.gate_open("nightly.yml")
    monkeypatch.setenv("NIGHTLY_HEAVY_TESTS", "true")
    assert liveness.gate_open("nightly.yml")
    assert liveness.gate_open("scout.yml", {})


def test_nightly_issue_is_signed_prio1_and_not_duplicated():
    calls = []
    found = []

    def run(*args):
        calls.append(args)
        if args[:2] == ("issue", "list"):
            return json.dumps(found)
        return "https://github.com/Bankaifan/agent-template/issues/9\n"

    assert liveness.ensure_nightly_issue("k", run) == "9"
    create = next(a for a in calls if a[:2] == ("issue", "create"))
    assert create[create.index("--title") + 1] == "Nightly heavy tests failed"
    assert create[create.index("--label") + 1] == "prio:1"
    assert liveness.NIGHTLY_BODY in create[create.index("--body") + 1]
    found.append({"number": 9, "title": "Nightly heavy tests failed"})
    calls.clear()
    assert liveness.ensure_nightly_issue("k", run) is None
    assert not any(a[:2] == ("issue", "create") for a in calls)
