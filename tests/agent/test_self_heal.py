"""#624: a silent dev/fix run retries once, then becomes one signed prio:1 issue for the agents; never needs-human."""
import json

import agent_guard as ag
import pytest

BOT = "author[bot]"


class Gh:
    def __init__(self, comments=(), labels=(), body="Closes #5"):
        self.comments, self.labels, self.body, self.calls = list(comments), list(labels), body, []

    def __call__(self, *a):
        self.calls.append(a)
        if a[0] == "api":
            return json.dumps([[{"body": c, "user": {"login": BOT}} for c in self.comments]])
        if a[1] == "comment":
            self.comments.append(a[-1])
            return ""
        if a[1] == "view" and "comments" in a:
            return json.dumps({"comments": [{"body": c} for c in self.comments]})
        if a[:2] == ("pr", "view"):
            return json.dumps({"body": self.body})
        if a[:2] == ("issue", "view"):
            return json.dumps({"labels": [{"name": n} for n in self.labels]})
        if a[:2] == ("issue", "list"):
            return "[]"
        if a[:2] == ("issue", "create"):
            return "https://github.com/o/r/issues/77\n"
        return ""

    def did(self, *prefix):
        return [c for c in self.calls if c[:len(prefix)] == prefix]


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GUARD_KEY", "k")
    monkeypatch.setenv("AUTHOR_BOT", BOT)
    monkeypatch.setenv("GH_REPO", "o/r")


def test_dev_retries_once_then_opens_a_signed_issue():
    g = Gh()
    assert ag.self_heal("dev", "9", False, "no PR", g)
    assert g.did("issue", "edit", "9", "--remove-label", "agent:dev") and not g.did("issue", "create")
    assert ag.self_heal("dev", "9", False, "no PR", g)
    create = g.did("issue", "create")[0]
    assert "Agent dev runs end silently on #9" in create and "prio:1" in create and "guard-sig" in create[-1]
    assert "Handed to #77" in g.comments[-1]


def test_fix_restarts_the_task_unless_already_restarted():
    g = Gh()
    assert ag.self_heal("fix", "12", True, "no fix", g)
    assert g.did("pr", "close", "12") and g.did("issue", "edit", "5", "--remove-label", "agent:dev")
    h = Gh(labels=["restart:1"])
    assert ag.self_heal("fix", "12", True, "no fix", h)
    assert h.did("issue", "create") and not h.did("pr", "close")


def test_without_key_or_for_review_the_old_path_stays(monkeypatch):
    assert not ag.self_heal("review", "3", True, "x", Gh())
    monkeypatch.delenv("GUARD_KEY")
    assert not ag.self_heal("dev", "3", False, "x", Gh())


def merged_gh(prs):
    g = Gh()
    base = g.__call__

    def call(*a):
        if a[:3] == ("pr", "list", "--state"):
            g.calls.append(a)
            return json.dumps(prs)
        return base(*a)

    g.__call__ = call
    return call, g


def test_dev_run_on_an_issue_with_a_merged_pr_is_settled_not_retried():
    call, g = merged_gh([{"headRefName": "agent/9-thing", "mergedAt": "2026-11-12T10:00:00Z"}])
    assert ag.settle_if_done("9", "", call)
    assert g.did("issue", "edit", "9", "--remove-label", "agent:dev") and g.did("issue", "close", "9")
    assert "<!-- settled -->" in g.comments[-1] and not g.did("issue", "create")


def test_settle_needs_a_merged_pr_and_no_denied_call():
    call, g = merged_gh([{"headRefName": "agent/19-other", "mergedAt": "2026-11-12T10:00:00Z"}])
    assert not ag.settle_if_done("9", "", call) and not g.did("issue", "edit")
    call, g = merged_gh([{"headRefName": "agent/9-thing", "mergedAt": "2026-11-12T10:00:00Z"}])
    denied = json.dumps({"type": "result", "permission_denials": [{"tool_name": "Bash"}]})
    assert not ag.settle_if_done("9", denied, call) and not g.did("issue", "edit")
