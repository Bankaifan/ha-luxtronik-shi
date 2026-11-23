import json

import pytest
import restart as r


class Fake:
    """Records gh calls; answers pr view, issue view and the reviews api from a state dict."""

    def __init__(self, body="Closes #68", state="OPEN", issue_labels=(), author="app/x", reviews=(), labelled=None):
        self.calls = []
        self.body, self.state, self.issue_labels, self.author = body, state, list(issue_labels), author
        self.reviews = list(reviews)
        self.labelled = labelled or {}  # issue number -> labels, overrides issue_labels for that issue
        self.posted, self.lossy = [], False

    def __call__(self, *args):
        self.calls.append(args)
        if args[1:2] == ("comment",) and not self.lossy:
            self.posted.append({"body": args[args.index("--body") + 1]})
        if args[1:2] == ("view",) and "comments" in args:
            return json.dumps({"comments": self.posted})
        if args[:2] == ("pr", "view") and "author" in args:
            return json.dumps({"author": {"login": self.author}})
        if args[:2] == ("pr", "view"):
            return json.dumps({"body": self.body, "state": self.state, "labels": []})
        if args[:2] == ("issue", "view"):
            names = self.labelled.get(int(args[2]), self.issue_labels)
            return json.dumps({"labels": [{"name": n} for n in names]})
        if args[0] == "api":
            return json.dumps([self.reviews])
        return ""

    def has(self, *prefix):
        return any(c[:len(prefix)] == prefix for c in self.calls)

    def flat(self):
        return [" ".join(c) for c in self.calls]


@pytest.fixture(autouse=True)
def repo(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")


def test_first_limit_restarts_the_issue_and_closes_the_pr():
    f = Fake(reviews=[{"state": "CHANGES_REQUESTED", "body": "Missing test for X"}, {"state": "APPROVED", "body": "ok"}])
    assert r.handle_limit("64", f) == "restarted"
    calls = f.flat()
    assert "issue edit 68 --add-label restart:1" in calls
    comment = next(c for c in f.calls if c[:3] == ("issue", "comment", "68"))
    assert "- Missing test for X" in comment[4] and "Different approach" in comment[4]
    assert "- ok" not in comment[4]  # only reviews that requested changes are quoted
    # agent:dev is removed, then added again so the label event fires
    assert calls.index("issue edit 68 --remove-label agent:dev") < calls.index("issue edit 68 --add-label agent:dev")
    assert ("pr", "close", "64", "--comment", "Superseded: round limit reached, task restarted, see #68") in f.calls
    assert not any("parked" in c for c in calls)
    assert not f.has("pr", "edit") and not f.has("pr", "comment")


def test_limit_with_restart_label_parks_and_asks_nobody():
    f = Fake(issue_labels=["restart:1", "agent:dev"])
    assert r.handle_limit("70", f) == "parked"
    assert "pr edit 70 --add-label parked" in f.flat() and not f.has("pr", "edit", "70", "--add-reviewer")
    comments = [c for c in f.calls if c[:2] == ("pr", "comment")]
    assert len(comments) == 1 and "restart:1" in comments[0][4] and "<!-- parked -->" in comments[0][4]
    assert not f.has("pr", "close") and not f.has("issue", "comment")


def test_missing_slip_comment_fails_loudly_before_the_pr_is_closed():
    f = Fake()
    f.lossy = True
    with pytest.raises(r.liveness.ReadbackError):
        r.handle_limit("64", f)
    assert not f.has("pr", "close")


def test_missing_limit_comment_fails_loudly():
    f = Fake(issue_labels=["restart:1"])
    f.lossy = True
    with pytest.raises(r.liveness.ReadbackError):
        r.handle_limit("70", f)


def test_one_restart_max_second_limit_never_restarts_again():
    first = Fake()
    assert r.handle_limit("64", first) == "restarted"
    second = Fake(issue_labels=["restart:1"])  # the issue now carries the label the first restart set
    assert r.handle_limit("67", second) == "parked"
    assert not second.has("issue", "edit")


def test_limit_restarts_the_closed_issue_not_the_parent_ref():
    # the parent #352 already carries restart:1 (a sibling restarted it); this PR closes #357 and must still restart it
    f = Fake(body="Refs #352\n\nCloses #357", labelled={352: ["restart:1"]})
    assert r.handle_limit("364", f) == "restarted"
    assert "issue edit 357 --add-label restart:1" in f.flat()
    assert not f.has("issue", "edit", "352") and not f.has("pr", "edit")


def test_pr_without_issue_is_parked_and_closed_pr_is_left_alone():
    assert r.handle_limit("5", Fake(body="no issue")) == "parked"
    f = Fake(state="CLOSED")
    assert r.handle_limit("5", f) == "closed"
    assert len(f.calls) == 1


def test_issue_refs_keywords_and_order():
    assert r.issue_refs("Closes #68\nRefs #5 and fixes #68, see #9") == [68, 5]
    assert r.issue_refs(None) == []


def pr(number, body, head="agent/x", cross=False, files=("src/a.py",)):
    return {"number": number, "body": body, "headRefName": head, "isCrossRepository": cross,
            "files": [{"path": f} for f in files]}


def test_older_agent_pr_for_same_issue_and_the_same_files_is_closed_with_superseded_comment():
    f = Fake()
    prs = [pr(64, "Closes #62"), pr(67, "Closes #62", files=("src/a.py", "src/b.py")), pr(66, "Closes #10", "agent/10-y")]
    assert r.close_superseded(prs, f) == [(64, 67)]
    assert f.calls == [("pr", "close", "64", "--comment", "Superseded by #67")]


def test_two_prs_for_one_issue_with_different_work_both_stay_open():
    """roblox_energy #327 and #331: one issue, two pieces of work. Only the shared changelog fragment overlaps."""
    items = pr(327, "Closes #326", files=("src/Shop.luau", "tests/Shop.test.luau", "changelog.d/326.md"))
    reset = pr(331, "Closes #326", files=("src/Prestige.luau", "src/PlotService.luau", "changelog.d/326.md"))
    assert r.superseded([items, reset]) == [] and r.close_superseded([items, reset], Fake()) == []
    partly = pr(332, "Closes #326", files=("src/Shop.luau", "changelog.d/326.md"))  # not every file of #327
    assert r.superseded([items, reset, partly]) == []
    assert r.superseded([pr(1, "Closes #2", files=("changelog.d/2.md",)), pr(3, "Closes #2", files=("changelog.d/2.md",))]) == []
    assert r.superseded([pr(1, "Closes #2", files=()), pr(3, "Closes #2")]) == []  # unknown file list: nothing is closed
    unknown = {"number": 1, "body": "Closes #2", "headRefName": "agent/x", "isCrossRepository": False}
    assert r.superseded([unknown, pr(3, "Closes #2")]) == []


def test_an_explicit_supersedes_line_replaces_whatever_the_files_are():
    old, other = pr(349, "Closes #340", files=("src/a.py",)), pr(350, "Closes #341", files=("src/a.py",))
    new = pr(352, "Second try.\nCloses #351\nSupersedes #349", files=("src/z.py",))
    assert r.superseded([old, other, new]) == [(349, 352)]
    assert r.superseded([old, pr(353, "Closes #340\nSupersedes #349", "feature/z")]) == []  # agent PRs only
    assert r.superseded([pr(1, "Closes #2"), pr(3, "Closes #9")]) == []  # same files, another issue


def test_superseded_ignores_non_agent_and_cross_repo_prs():
    prs = [pr(1, "Closes #2", "feature/z"), pr(3, "Closes #2"), pr(4, "Closes #2", cross=True)]
    assert r.superseded(prs) == []


def test_the_batch_pr_replaces_none_of_its_members():
    prs = [pr(7, "Closes #2", "agent/2-x"), pr(9, "Batch: #7@abcdef0 #8@abcdef1\nCloses #2", "agent/batch")]
    assert r.superseded(prs) == []


def test_sibling_prs_sharing_only_a_parent_ref_do_not_replace_each_other():
    prs = [pr(360, "Closes #357. Refs #352"), pr(361, "Closes #358. Refs #352"), pr(362, "Closes #355. Refs #352")]
    assert r.superseded(prs) == []
    assert r.superseded(prs + [pr(363, "Closes #357")]) == [(360, 363)]


def test_three_prs_chain_to_the_newest():
    prs = [pr(1, "Refs #2"), pr(2, "Refs #2"), pr(3, "Closes #2")]
    assert r.superseded(prs) == [(1, 3), (2, 3)]
