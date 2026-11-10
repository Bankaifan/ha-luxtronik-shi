import json

import pytest
import restart as r


class Fake:
    """Records gh calls; answers pr view, issue view and the reviews api from a state dict."""

    def __init__(self, body="Closes #68", state="OPEN", issue_labels=(), author="app/x", reviews=()):
        self.calls = []
        self.body, self.state, self.issue_labels, self.author = body, state, list(issue_labels), author
        self.reviews = list(reviews)
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
            return json.dumps({"labels": [{"name": n} for n in self.issue_labels]})
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
    assert r.handle_limit("64", "Bankaifan", f) == "restarted"
    calls = f.flat()
    assert "issue edit 68 --add-label restart:1" in calls
    comment = next(c for c in f.calls if c[:3] == ("issue", "comment", "68"))
    assert "- Missing test for X" in comment[4] and "Different approach" in comment[4]
    assert "- ok" not in comment[4]  # only reviews that requested changes are quoted
    # agent:dev is removed, then added again so the label event fires
    assert calls.index("issue edit 68 --remove-label agent:dev") < calls.index("issue edit 68 --add-label agent:dev")
    assert ("pr", "close", "64", "--comment", "Superseded: round limit reached, task restarted, see #68") in f.calls
    assert not any("needs-human" in c for c in calls)
    assert not f.has("pr", "edit") and not f.has("pr", "comment")


def test_limit_with_restart_label_parks_with_daniel_once():
    f = Fake(issue_labels=["restart:1", "agent:dev"])
    assert r.handle_limit("70", "Bankaifan", f) == "parked"
    assert "pr edit 70 --add-label needs-human" in f.flat()
    assert ("pr", "edit", "70", "--add-reviewer", "Bankaifan") in f.calls
    comments = [c for c in f.calls if c[:2] == ("pr", "comment")]
    assert len(comments) == 1 and "already failed" in comments[0][4] and "Hallo Daniel" in comments[0][4]
    assert not f.has("pr", "close") and not f.has("issue", "comment")


def test_missing_slip_comment_fails_loudly_before_the_pr_is_closed():
    f = Fake()
    f.lossy = True
    with pytest.raises(r.liveness.ReadbackError):
        r.handle_limit("64", "Bankaifan", f)
    assert not f.has("pr", "close")


def test_missing_limit_comment_fails_loudly():
    f = Fake(issue_labels=["restart:1"])
    f.lossy = True
    with pytest.raises(r.liveness.ReadbackError):
        r.handle_limit("70", "Bankaifan", f)


def test_one_restart_max_second_limit_never_restarts_again():
    first = Fake()
    assert r.handle_limit("64", "Bankaifan", first) == "restarted"
    second = Fake(issue_labels=["restart:1"])  # the issue now carries the label the first restart set
    assert r.handle_limit("67", "Bankaifan", second) == "parked"
    assert not second.has("issue", "edit")


def test_no_review_request_when_daniel_is_the_author():
    f = Fake(issue_labels=["restart:1"], author="Bankaifan")
    r.handle_limit("70", "Bankaifan", f)
    assert not f.has("pr", "edit", "70", "--add-reviewer")


def test_pr_without_issue_is_parked_and_closed_pr_is_left_alone():
    assert r.handle_limit("5", "Bankaifan", Fake(body="no issue")) == "parked"
    f = Fake(state="CLOSED")
    assert r.handle_limit("5", "Bankaifan", f) == "closed"
    assert len(f.calls) == 1


def test_issue_refs_keywords_and_order():
    assert r.issue_refs("Closes #68\nRefs #5 and fixes #68, see #9") == [68, 5]
    assert r.issue_refs(None) == []


def pr(number, body, head="agent/x", cross=False):
    return {"number": number, "body": body, "headRefName": head, "isCrossRepository": cross}


def test_older_agent_pr_for_same_issue_is_closed_with_superseded_comment():
    f = Fake()
    prs = [pr(64, "Closes #62"), pr(67, "Closes #62"), pr(66, "Closes #10", "agent/10-y")]
    assert r.close_superseded(prs, f) == [(64, 67)]
    assert f.calls == [("pr", "close", "64", "--comment", "Superseded by #67")]


def test_superseded_ignores_non_agent_and_cross_repo_prs():
    prs = [pr(1, "Closes #2", "feature/z"), pr(3, "Closes #2"), pr(4, "Closes #2", cross=True)]
    assert r.superseded(prs) == []


def test_three_prs_chain_to_the_newest():
    prs = [pr(1, "Refs #2"), pr(2, "Refs #2"), pr(3, "Closes #2")]
    assert r.superseded(prs) == [(1, 3), (2, 3)]
