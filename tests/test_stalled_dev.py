import datetime
import json
import subprocess

import pytest
import stalled_dev as s

NOW = datetime.datetime(2026, 11, 10, 12, 0, tzinfo=datetime.UTC)


def ago(minutes):
    return (NOW - datetime.timedelta(minutes=minutes)).isoformat()


def at(minutes):
    return lambda _issue: ago(minutes)


def issue(number=5, labels=("agent:dev",), title="Do it"):
    return {"number": number, "title": title, "labels": [{"name": n} for n in labels]}


class Fake:
    """Records gh calls; answers pr list, run list (by status), comments and the api used by owner_hold."""

    def __init__(self, prs=(), runs=(), fail=None):
        self.prs, self.runs, self.fail = list(prs), list(runs), fail
        self.calls, self.comments = [], []

    def __call__(self, *args):
        self.calls.append(args)
        if self.fail and args[:2] == self.fail:
            raise subprocess.CalledProcessError(1, "gh", stderr="boom")
        if args[:2] == ("pr", "list"):
            return json.dumps(self.prs)
        if args[:2] == ("run", "list"):
            status = args[args.index("--status") + 1]
            return json.dumps([r for r in self.runs if r["status"] == status])
        if args[1:2] == ("comment",):
            self.comments.append(args[args.index("--body") + 1])
            return ""
        if args[:2] == ("issue", "view"):
            return json.dumps({"comments": [{"body": b} for b in self.comments]})
        if args[0] == "api":
            return "[]"
        return ""

    def has(self, *prefix):
        return any(c[:len(prefix)] == prefix for c in self.calls)

    def flat(self):
        return [" ".join(c) for c in self.calls]


@pytest.fixture(autouse=True)
def repo(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")


def test_first_stall_restarts_once_with_mark_and_fresh_label_event():
    f = Fake()
    assert s.check([issue(5)], at(120), NOW, f, "Bankaifan") == ["stalled issue #5: agent:dev set again (once)"]
    flat = f.flat()
    assert "issue edit 5 --add-label stalled:1" in flat
    assert flat.index("issue edit 5 --remove-label agent:dev") < flat.index("issue edit 5 --add-label agent:dev")
    assert len(f.comments) == 1 and "Restarting once (stalled:1)" in f.comments[0]
    assert not f.has("issue", "edit", "5", "--add-label", "needs-human")


def test_second_stall_parks_with_daniel_once_and_does_not_restart():
    f = Fake()
    actions = s.check([issue(5, labels=("agent:dev", "stalled:1"))], at(120), NOW, f, "Bankaifan")
    assert actions == ["stalled issue #5: parked with Daniel"]
    assert "issue edit 5 --add-label needs-human" in f.flat()
    assert ("issue", "edit", "5", "--add-assignee", "Bankaifan") in f.calls
    assert not f.has("issue", "edit", "5", "--remove-label", "agent:dev")
    assert len(f.comments) == 1
    note = f.comments[0]
    assert note.count("@Bankaifan") == 1 and "Hallo Daniel" in note
    assert "<!-- decision: yes=restart-issue no=close-issue -->" in note


def test_parked_issue_is_left_alone():
    f = Fake()
    assert s.check([issue(5, labels=("agent:dev", "needs-human"))], at(120), NOW, f, "Bankaifan") == []
    assert f.calls == [("pr", "list", "--state", "open", "--limit", "100", "--json", "number,body"),
                       ("run", "list", "--workflow", "agent-dev.yml", "--status", "queued", "--limit", "50",
                        "--json", "displayTitle"),
                       ("run", "list", "--workflow", "agent-dev.yml", "--status", "in_progress", "--limit", "50",
                        "--json", "displayTitle")]


@pytest.mark.parametrize("body", ["Closes #5", "fixes #5", "Resolved #5 and more"])
def test_open_pr_with_closing_keyword_skips_the_issue(body):
    f = Fake(prs=[{"number": 9, "body": body}])
    assert s.check([issue(5)], at(120), NOW, f, "Bankaifan") == []
    assert not f.has("issue", "edit")


def test_refs_does_not_count_as_a_closing_pr():
    f = Fake(prs=[{"number": 9, "body": "Refs #5"}])
    assert s.check([issue(5)], at(120), NOW, f, "Bankaifan") == ["stalled issue #5: agent:dev set again (once)"]


@pytest.mark.parametrize("title", ["#5 Do it", "Do it", "agent-dev run without a number"])
def test_running_agent_dev_run_covering_the_issue_skips_it(title):
    f = Fake(runs=[{"status": "queued", "displayTitle": title}])
    assert s.check([issue(5)], at(120), NOW, f, "Bankaifan") == []
    assert not f.has("issue", "edit")


def test_in_progress_run_covers_the_issue():
    f = Fake(runs=[{"status": "in_progress", "displayTitle": "#5 Do it"}])
    assert s.check([issue(5)], at(120), NOW, f, "Bankaifan") == []


def test_run_for_another_issue_does_not_cover_it():
    f = Fake(runs=[{"status": "queued", "displayTitle": "#7 Other"}])
    assert s.check([issue(5)], at(120), NOW, f, "Bankaifan") == ["stalled issue #5: agent:dev set again (once)"]


def test_young_label_is_not_stalled():
    f = Fake()
    assert s.check([issue(5)], at(30), NOW, f, "Bankaifan") == []
    assert not f.has("issue", "edit")


def test_issues_handled_by_the_orphan_step_are_skipped():
    f = Fake()
    assert s.check([issue(5)], at(120), NOW, f, "Bankaifan", skip={5}) == []
    assert not f.has("issue", "edit")


def test_stall_mark_is_removed_when_an_open_pr_closes_the_issue():
    f = Fake(prs=[{"number": 9, "body": "Closes #5"}])
    actions = s.check([issue(5, labels=("agent:dev", "stalled:1"))], at(120), NOW, f, "Bankaifan")
    assert actions == ["stalled mark removed from #5: an open PR closes it"]
    assert ("issue", "edit", "5", "--remove-label", "stalled:1") in f.calls


def test_failing_query_changes_nothing_and_does_not_raise():
    f = Fake(fail=("run", "list"))
    assert s.check([issue(5)], at(120), NOW, f, "Bankaifan") == []
    assert not f.has("issue", "edit")


def test_failing_write_is_reported_and_the_rest_continues():
    class FailFirstEdit(Fake):
        def __call__(self, *args):
            if args[:2] == ("issue", "edit") and args[2] == "5":
                self.calls.append(args)
                raise subprocess.CalledProcessError(1, "gh", stderr="denied")
            return super().__call__(*args)

    f = FailFirstEdit()
    actions = s.check([issue(5), issue(6)], at(120), NOW, f, "Bankaifan")
    assert actions == ["stalled issue #5: failed (CalledProcessError)", "stalled issue #6: agent:dev set again (once)"]


def test_closing_keyword_regex_takes_numbers_only_after_the_keyword():
    assert s.closed_by([{"body": "Closes #5, refs #6, Fixes #7"}]) == {5, 7}
    assert s.closed_by([{"body": None}]) == set()
