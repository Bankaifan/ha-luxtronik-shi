"""End-to-end check of the overdue-run flagging in the status run (issue #98).

A scheduled workflow that never succeeded is measured from the date it was added. These tests run the whole
status run with a fake gh, so the wiring between run_status and the grace baseline is covered, not only the helpers.
"""
import datetime
import json

import status as st

NOW = datetime.datetime(2026, 11, 10, 12, 0, tzinfo=datetime.UTC)
ENV = {"GH_REPO": "Bankaifan/agent-template", "OWNER": "Bankaifan", "AUTHOR_BOT": ""}
ISSUE_URL = "https://github.com/Bankaifan/agent-template/issues/7\n"


def fake_gh(added, log):
    """Quiet repo: no runs, PRs or issues; never-run workflows return `added[file]` as their created_at."""
    stored = {}

    def run(*args):
        log.append(args)
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
    assert st.run_status(ENV, NOW, fake_gh(added, log)) == 0
    creates = overdue_creates(log)
    assert [a[a.index("--title") + 1] for a in creates] == ["Overdue scheduled run: scout"]
    assert creates[0][creates[0].index("--label") + 1] == "prio:1"
