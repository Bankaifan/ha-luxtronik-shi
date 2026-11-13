import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "tools"))

import dispatch
import prefilter

BOT = {"login": "bankaifan-agent-author"}


class FakeGh:
    """Records every call; ISSUES maps number -> issue JSON, PRS maps number -> PR JSON."""

    def __init__(self, issues=None, prs=None, fail_label=()):
        self.issues, self.prs, self.fail_label, self.calls = issues or {}, prs or {}, set(fail_label), []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("issue", "view"):
            return json.dumps(self.issues[int(args[2])])
        if args[:2] == ("pr", "view"):
            return json.dumps(self.prs[int(args[2])])
        if args[:2] == ("label", "create") and args[2] in self.fail_label:
            raise subprocess.CalledProcessError(1, "gh")
        return ""

    def edits(self):
        return [c for c in self.calls if c[:2] == ("issue", "edit")]


def slip_issue(files="tools/a.py", extra="", author=BOT):
    return {"body": f"Files: {files}\n{extra}", "author": author, "comments": [], "labels": []}


def ok(_argv):
    return 0


def state(numbers, limit=None):
    """A start_state() dict: NUMBERS is the whole startable list, LIMIT the min of free dev and PR slots."""
    return {"startable": list(numbers), "limit": len(numbers) if limit is None else limit}


def test_design_split_issue_with_slip_gets_model_then_agent_dev():
    gh = FakeGh({7: slip_issue(files="tools/ci/risk.py")})
    assert dispatch.start(state([7]), gh, ok) == [7]
    assert [c[4] for c in gh.edits()] == ["model:sonnet", "agent:dev"]  # agent:dev last


def test_n_free_slots_n_ready_issues_start_n():
    gh = FakeGh({n: slip_issue(f"tools/f{n}.py") for n in (1, 2, 3)})
    assert dispatch.start(state([1, 2, 3]), gh, ok) == [1, 2, 3]


def test_slipless_issues_ahead_do_not_take_the_free_slots():
    # 2 free slots; the first two startable issues have no slip, so the slots go to C and D (issue #552)
    issues = {1: {"body": "idea", "author": BOT, "comments": [], "labels": []},
              2: {"body": "idea", "author": BOT, "comments": [], "labels": []}}
    issues.update({n: slip_issue(f"tools/f{n}.py") for n in (3, 4, 5)})
    gh = FakeGh(issues)
    assert dispatch.start(state([1, 2, 3, 4, 5], limit=2), gh, ok) == [3, 4]
    assert not any(c[2] in ("1", "2", "5") for c in gh.edits())


def test_issue_without_slip_or_with_stranger_slip_is_not_started():
    gh = FakeGh({1: {"body": "idea", "author": BOT, "comments": [], "labels": []},
                 2: slip_issue(author={"login": "mallory"})})
    assert dispatch.start(state([1, 2]), gh, ok) == []
    assert gh.edits() == []


def test_overlap_defers_and_second_issue_on_same_files_waits():
    gh = FakeGh({1: slip_issue(), 2: slip_issue(), 3: slip_issue("tools/c.py")})
    seen = []

    def overlap_main(argv):  # the first start makes the second overlap, as the live agent:dev label would
        seen.append(argv)
        return 1 if len(seen) > 1 and "tools/a.py" in argv[1] else 0

    assert dispatch.start(state([1, 2, 3], limit=2), gh, overlap_main) == [1, 3]
    assert not any(c[2] == "2" for c in gh.edits())
    assert dispatch.start(state([1]), FakeGh({1: slip_issue()}), lambda a: 2) == []  # unreadable: defer


def test_only_listed_issues_are_touched():
    gh = FakeGh({1: slip_issue(), 9: slip_issue()})
    dispatch.start(state([1]), gh, ok)
    assert all("9" not in c for c in gh.calls)


def test_failing_label_create_does_not_stop_the_others():
    gh = FakeGh({1: slip_issue("tools/ci/x.py"), 2: slip_issue("tools/y.py")},
                fail_label={"model:sonnet"})
    assert dispatch.start(state([1, 2]), gh, ok) == [2]
    assert not any(c[2] == "1" for c in gh.edits())


def test_after_merge_removes_agent_dev_of_referenced_issues():
    pr = {"state": "MERGED", "body": "Refs #5\nCloses #6", "headRefName": "agent/5-x", "isCrossRepository": False}
    gh = FakeGh(prs={1: pr})
    assert dispatch.after_merge(1, gh) == [5, 6]
    assert [c[2] for c in gh.edits()] == ["5", "6"] and all(c[3:] == ("--remove-label", "agent:dev") for c in gh.edits())


def test_after_merge_ignores_cross_repo_foreign_branch_and_unmerged():
    base = {"state": "MERGED", "body": "Refs #5", "headRefName": "agent/5-x", "isCrossRepository": False}
    for change in ({"isCrossRepository": True}, {"headRefName": "feature/x"}, {"state": "OPEN"}):
        gh = FakeGh(prs={1: {**base, **change}})
        assert dispatch.after_merge(1, gh) == []
        assert gh.edits() == []


def waiting(body="Waiting for #9, the template issue for a denied tool call.", login=BOT["login"]):
    return {"author": {"login": login}, "body": body}


def test_waiting_blocker_reads_last_trusted_comment_only():
    assert prefilter.waiting_blocker([waiting()]) == 9
    assert prefilter.waiting_blocker([waiting(), waiting("thanks", "bob")]) == 9  # stranger comment ignored
    assert prefilter.waiting_blocker([waiting(), waiting("Restarted")]) is None
    assert prefilter.waiting_blocker([waiting(login="mallory")]) is None


def test_parked_waiting_splits_open_and_closed_blocker():
    states = {9: "OPEN", 8: "CLOSED"}

    def gh(*a):
        return json.dumps({"state": states[int(a[2])]})

    dev = [{"number": 1, "comments": [waiting()]}, {"number": 2, "comments": [waiting("Waiting for #8")]},
           {"number": 3, "comments": []}]
    assert prefilter.parked_waiting(dev, gh) == ({1}, {2: 8})


class RunGh(FakeGh):
    def __init__(self, runs=(), **kw):
        super().__init__(**kw)
        self.runs = list(runs)

    def __call__(self, *args):
        if args[:2] == ("run", "list"):
            self.calls.append(args)
            return json.dumps([{"displayTitle": t} for t in self.runs])
        return super().__call__(*args)


def test_closed_blocker_restarts_by_removing_and_re_adding_agent_dev():
    gh = RunGh(issues={5: {"title": "Fix x"}})
    assert dispatch.restart_waiting({"restart": {5: 9}}, gh) == [5]
    assert [c[3:] for c in gh.edits()] == [("--remove-label", "agent:dev"), ("--add-label", "agent:dev")]


def test_restart_posts_a_marker_so_a_second_dispatch_does_not_restart_again():
    gh = RunGh(issues={5: {"title": "Fix x"}})
    comments = [waiting("Waiting for #9, the template issue for a denied tool call.")]
    assert prefilter.waiting_blocker(comments) == 9
    assert dispatch.restart_waiting({"restart": {5: 9}}, gh) == [5]
    posted = [c for c in gh.calls if c[:2] == ("issue", "comment")]
    assert posted == [("issue", "comment", "5", "--body", "Restarted: #9 is closed.")]
    comments.append(waiting(posted[0][4]))  # the marker is now the last trusted comment
    assert prefilter.waiting_blocker(comments) is None  # the next start_state() does not list #5 for restart


def test_no_restart_while_a_run_is_in_progress_or_without_closed_blocker():
    gh = RunGh(runs=["Fix x"], issues={5: {"title": "Fix x"}})
    assert dispatch.restart_waiting({"restart": {5: 9}}, gh) == []
    assert gh.edits() == []
    gh = RunGh()
    assert dispatch.restart_waiting({"restart": {}}, gh) == [] and dispatch.restart_waiting({}, gh) == []
    assert gh.calls == []  # an open blocker puts nothing into "restart"
