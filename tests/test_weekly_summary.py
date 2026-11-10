import datetime
import importlib.util
import json
import pathlib
import subprocess

import guard_mark

_path =pathlib.Path(__file__).parent.parent / "tools" / "weekly_summary.py"
_spec = importlib.util.spec_from_file_location("weekly_summary", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

NOW = datetime.datetime(2026, 11, 9, 12, 0, tzinfo=datetime.UTC)


def status_runs(created_at):
    """Fake gh: `gh run list` returns the given status run (or none)."""
    def run(*args):
        assert args[:2] == ("run", "list")
        return json.dumps([{"createdAt": created_at, "url": "u"}] if created_at else [])
    return run


def test_build_body_lists_rows_and_none():
    body = mod.build_body([{"number": 5, "title": "Fix x"}], [], [], [{"number": 9, "title": "Idea"}], "2026-11-09")
    assert "- #5 Fix x" in body
    assert "- #9 Idea" in body
    assert body.count("- none") == 2
    assert "Updated 2026-11-09." in body


def test_count_code_skips_generated_and_unknown():
    files = ["a.py", "tools/b.py", "x.sh", "package-lock.json", "dist/c.js", "app.min.js", "README.md", "vendor/d.py"]
    lines, modules = mod.count_code(files, lambda p: 10)
    assert lines == {"python": 20, "shell": 10}
    assert modules == {"python": 2, "shell": 1}


def test_max_parallel_counts_overlap_and_ignores_non_agent():
    prs = [
        {"headRefName": "agent/1-a", "createdAt": "2026-11-03T10:00:00Z", "closedAt": "2026-11-04T10:00:00Z"},
        {"headRefName": "agent/2-b", "createdAt": "2026-11-03T12:00:00Z", "closedAt": None},
        {"headRefName": "agent/3-c", "createdAt": "2026-11-04T10:00:00Z", "closedAt": "2026-11-05T10:00:00Z"},
        {"headRefName": "feature/x", "createdAt": "2026-11-03T10:00:00Z", "closedAt": None},
        {"headRefName": "agent/4-d", "createdAt": "2026-10-01T10:00:00Z", "closedAt": "2026-10-02T10:00:00Z"},
    ]
    assert mod.max_parallel(prs, "2026-11-02T00:00:00Z", "2026-11-09T23:59:59Z") == 2


def test_avg_review_rounds():
    merged = [{"headRefName": "agent/1", "reviews": [{"state": "CHANGES_REQUESTED"}, {"state": "APPROVED"}]},
              {"headRefName": "agent/2", "reviews": [{"state": "APPROVED"}]},
              {"headRefName": "other", "reviews": [{"state": "CHANGES_REQUESTED"}] * 5}]
    assert mod.avg_review_rounds(merged) == 1.5
    assert mod.avg_review_rounds([]) is None


def test_median_ci_minutes():
    def run(minutes, conclusion="success"):
        return {"startedAt": "2026-11-03T10:00:00Z", "updatedAt": f"2026-11-03T10:{minutes:02d}:00Z",
                "conclusion": conclusion}
    assert mod.median_ci_minutes([run(2), run(4), run(9), run(50, "")]) == 4.0
    assert mod.median_ci_minutes([]) is None


def test_metrics_row_and_append_idempotent(tmp_path):
    row = mod.metrics_row("2026-11-09", {"python": 30}, {"python": 3}, 2, None, 4.0, None)
    assert row["code_lines"] == 30 and row["lines_by_lang"] == "python=30"
    assert row["avg_review_rounds"] == "" and row["actions_minutes"] == "" and row["conflicts_rebuilt"] == ""
    path = tmp_path / "docs" / "metrics.csv"
    assert mod.append_metrics(path, row) is True
    assert mod.append_metrics(path, row) is False
    lines = path.read_text().splitlines()
    assert lines[0] == ",".join(mod.COLUMNS) and len(lines) == 2


def test_status_run_stale_fresh_stale_and_none():
    liveness = mod.liveness
    assert liveness.status_run_stale(status_runs("2026-11-09T11:00:00+00:00"), NOW) is False
    assert liveness.status_run_stale(status_runs("2026-11-09T08:00:00+00:00"), NOW) is True
    assert liveness.status_run_stale(status_runs(None), NOW) is True


def test_status_stale_safe_skips_warning_when_gh_fails():
    def failing(*args):
        raise subprocess.CalledProcessError(1, "gh")

    assert mod.status_stale_safe(failing) is False


def test_friction_issues_creates_and_survives_gh_failure(monkeypatch):
    item = {"title": "Friction: x", "template_only": False, "count": 2}
    monkeypatch.setattr(mod.friction, "collect", lambda: [item])
    calls = []
    assert mod.friction_issues(lambda *a: calls.append(a)) == ["Friction: x"]
    assert calls[0][:2] == ("issue", "create")

    def failing():
        raise subprocess.CalledProcessError(1, "gh")

    monkeypatch.setattr(mod.friction, "collect", failing)
    assert mod.friction_issues(lambda *a: None) == []


def test_build_body_warns_when_status_stale():
    body = mod.build_body([], [], [], [], "2026-11-09", status_stale=True)
    assert "## Warning" in body and "last 3 hours" in body
    assert "## Warning" not in mod.build_body([], [], [], [], "2026-11-09", status_stale=False)


def test_run_main_exits_nonzero_on_readback_failure(monkeypatch):
    def boom():
        raise mod.liveness.ReadbackError("issue #1: body not as written after update")

    monkeypatch.setattr(mod, "main", boom)
    assert mod.run_main() == 1


TODAY = datetime.date(2026, 11, 9)  # week window: 2026-11-02 .. 2026-11-09
KEY = "test-guard-key"


def failure_issue(number, state, closed_at=None, updated="2026-11-08T10:00:00Z", reopened=None,
                  title=None, signed=True):
    """A failure issue as `gh issue list` returns it; signed like failure_watch writes it (guard_mark.sign).
    One title per signature, as failure_watch creates them (load_issues is keyed by title)."""
    title = title or f"Failing workflow: ci.yml / test / step{number}"
    body = "Failures: 1\nLast run: https://example.test/run\n" + (f"Reopened: {reopened}\n" if reopened else "")
    if signed:
        body = guard_mark.sign(title, body, KEY)
    return {"number": number, "title": title, "state": state, "closedAt": closed_at, "updatedAt": updated,
            "body": body}


def fake_issue_list(issues):
    """Fake gh: `gh issue list` returns the given issues."""
    def run(*args):
        assert args[:2] == ("issue", "list")
        return json.dumps(issues)
    return run


def test_failure_watch_summary_open_closed_reopened():
    issues = [
        failure_issue(1, "OPEN", reopened=1),                                     # open and reopened this week
        failure_issue(2, "CLOSED", closed_at="2026-11-07T10:00:00Z", updated="2026-11-07T10:00:00Z"),
        failure_issue(3, "CLOSED", closed_at="2026-10-01T10:00:00Z", updated="2026-10-01T10:00:00Z"),  # too old
        failure_issue(4, "OPEN", title="Overdue scheduled run: ci"),              # not a failure issue
        failure_issue(5, "CLOSED", closed_at="2026-11-06T10:00:00Z", updated="2026-11-06T10:00:00Z"),
    ]
    watch = mod.failure_watch_summary(fake_issue_list(issues), TODAY, KEY)
    assert [i["number"] for i in watch["open"]] == [1]
    assert [i["number"] for i in watch["closed"]] == [2, 5]
    assert [i["number"] for i in watch["reopened"]] == [1]


def test_reopened_counts_only_updated_this_week_with_counter():
    issues = [
        failure_issue(1, "OPEN", reopened=1, updated="2026-10-20T10:00:00Z"),  # reopened long ago, not updated since
        failure_issue(2, "OPEN", reopened=1, updated="2026-11-05T10:00:00Z"),  # counter >= 1, updated this week
        failure_issue(3, "OPEN", updated="2026-11-05T10:00:00Z"),              # no Reopened line
    ]
    watch = mod.failure_watch_summary(fake_issue_list(issues), TODAY, KEY)
    assert [i["number"] for i in watch["reopened"]] == [2]


def test_unsigned_failure_issue_is_ignored():
    issues = [
        failure_issue(1, "OPEN"),
        failure_issue(2, "OPEN", reopened=9, signed=False),  # forged counter, no signature
        failure_issue(3, "CLOSED", closed_at="2026-11-07T10:00:00Z", updated="2026-11-07T10:00:00Z", signed=False),
    ]
    watch = mod.failure_watch_summary(fake_issue_list(issues), TODAY, KEY)
    assert [i["number"] for i in watch["open"]] == [1]
    assert watch["closed"] == [] and watch["reopened"] == []
    body = mod.build_body([], [], [], [], "2026-11-09", failures=watch)
    assert "#2" not in body and "#3" not in body


def test_failure_section_lists_counts_and_titles():
    issues = [failure_issue(1, "OPEN", reopened=2), failure_issue(2, "CLOSED", closed_at="2026-11-07T10:00:00Z")]
    body = mod.build_body([], [], [], [], "2026-11-09", failures=mod.failure_watch_summary(fake_issue_list(issues),
                                                                                         TODAY, KEY))
    section = body.split("## Failure watch\n", 1)[1]
    assert section.startswith("- open: 1\n  - #1 Failing workflow: ci.yml / test / step1\n")
    assert "- closed this week: 1\n  - #2 Failing workflow: ci.yml / test / step2" in section
    assert "- reopened at least once, updated this week: 1\n  - #1 Failing workflow: ci.yml / test / step1" in section


def test_failure_section_prints_unknown_without_key_or_when_gh_fails():
    def failing(*args):
        raise subprocess.CalledProcessError(1, "gh")

    assert mod.failure_watch_summary(failing, TODAY, KEY) is None
    assert mod.failure_watch_summary(lambda *a: "not json", TODAY, KEY) is None
    assert mod.failure_watch_summary(fake_issue_list([failure_issue(1, "OPEN")]), TODAY, "") is None
    body = mod.build_body([], [], [], [], "2026-11-09", failures=None)
    assert "## Failure watch\n- unknown" in body
