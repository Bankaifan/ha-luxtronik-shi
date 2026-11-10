import json

import agent_guard as g
import owner_hold as oh
import restart
import status

OWNER = "Bankaifan"
BOT = "bankaifan-agent-author[bot]"


def ev(kind, label, actor, at):
    return {"event": kind, "label": {"name": label}, "actor": {"login": actor}, "created_at": at}


# Shape of the #184 timeline: the agent set needs-human, Daniel removed it, the next run set it again.
TIMELINE_184 = [
    ev("labeled", "needs-human", BOT, "2026-11-08T10:00:00Z"),
    ev("labeled", "review:1", BOT, "2026-11-08T10:01:00Z"),
    ev("unlabeled", "needs-human", OWNER, "2026-11-08T11:00:00Z"),
    ev("unlabeled", "review:1", OWNER, "2026-11-08T11:00:05Z"),
]
HEAD_OLD = "2026-11-08T09:00:00Z"
HEAD_NEW = "2026-11-08T12:00:00Z"


def test_owner_unlabel_holds_and_184_timeline_is_the_case():
    assert oh.owner_removed(TIMELINE_184, "needs-human", OWNER, HEAD_OLD)
    assert oh.owner_removed(TIMELINE_184, "review:1", OWNER, HEAD_OLD)
    assert not oh.owner_removed(TIMELINE_184, "review:2", OWNER, HEAD_OLD)  # never set


def test_new_head_ends_the_hold():
    assert not oh.owner_removed(TIMELINE_184, "needs-human", OWNER, HEAD_NEW)


def test_bot_unlabel_does_not_hold():
    evs = [ev("labeled", "needs-human", BOT, "2026-11-08T10:00:00Z"),
           ev("unlabeled", "needs-human", BOT, "2026-11-08T11:00:00Z")]
    assert not oh.owner_removed(evs, "needs-human", OWNER, HEAD_OLD)


def test_label_set_again_or_other_owner_label_ends_the_hold():
    again = TIMELINE_184 + [ev("labeled", "needs-human", BOT, "2026-11-08T11:30:00Z")]
    assert not oh.owner_removed(again, "needs-human", OWNER, HEAD_OLD)
    decision = TIMELINE_184 + [ev("labeled", "agent:dev", OWNER, "2026-11-08T11:30:00Z")]
    assert not oh.owner_removed(decision, "needs-human", OWNER, HEAD_OLD)


def test_only_guarded_labels_are_held():
    evs = [ev("unlabeled", "agent:dev", OWNER, "2026-11-08T11:00:00Z")]
    assert oh.held_labels(evs, ["agent:dev"], OWNER) == []
    assert oh.held_labels(TIMELINE_184, ["needs-human", "agent:dev"], OWNER, HEAD_OLD) == ["needs-human"]


def make_run(events, head=HEAD_OLD, labels=""):
    calls = []

    def run(*a):
        calls.append(a)
        if a[0] == "api":
            return json.dumps([events])
        if a[:2] == ("pr", "view") and "commits" in a:
            return json.dumps({"commits": [{"committedDate": head}]})
        if a[1:2] == ("view",) and "comments" in a:
            return json.dumps({"comments": [{"body": c[-1]} for c in calls if c[1:2] == ("comment",)]})
        if a[:2] == ("pr", "view"):
            return labels
        return ""

    return calls, run


def added(calls):
    return [c for c in calls if "--add-label" in c]


def test_add_labels_refuses_a_held_label_and_comments(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")
    calls, run = make_run(TIMELINE_184)
    g.add_labels("pr", 5, ["needs-human"], run)
    assert not added(calls)
    assert any(c[:3] == ("pr", "comment", "5") and "Daniel removed needs-human" in c[-1] for c in calls)


def test_add_labels_still_adds_the_other_labels(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")
    calls, run = make_run(TIMELINE_184)
    g.add_labels("pr", 5, ["needs-human", "agent:review"], run)
    assert added(calls) == [("pr", "edit", "5", "--add-label", "agent:review")]


def test_add_labels_adds_after_a_new_head_or_a_bot_removal(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")
    calls, run = make_run(TIMELINE_184, head=HEAD_NEW)
    g.add_labels("pr", 5, ["needs-human"], run)
    assert added(calls) == [("pr", "edit", "5", "--add-label", "needs-human")]
    bot = [ev("unlabeled", "needs-human", BOT, "2026-11-08T11:00:00Z")]
    calls, run = make_run(bot)
    g.add_labels("pr", 5, ["needs-human"], run)
    assert added(calls)


def test_add_labels_for_an_issue_has_no_head_check(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")
    calls, run = make_run(TIMELINE_184)
    g.add_labels("issue", 5, ["needs-human"], run)
    assert not added(calls)
    assert not any(c[:2] == ("pr", "view") and "commits" in c for c in calls)


def test_lookup_failure_fails_open(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")
    calls = []

    def run(*a):
        calls.append(a)
        return "not json" if a[0] == "api" else ""

    g.add_labels("pr", 5, ["needs-human"], run)
    assert added(calls)


def test_count_round_is_blocked_when_owner_removed_the_review_label(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")
    calls, run = make_run(TIMELINE_184, labels="")
    assert g.count_round(5, "a" * 40, run) == "held"
    assert not added(calls)


def test_count_round_counts_without_a_hold(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")
    calls, run = make_run([], labels="")
    assert g.count_round(5, "a" * 40, run) == "counted"
    assert added(calls) == [("pr", "edit", "5", "--add-label", "review:1", "--add-label", "round:aaaaaaa")]


def test_escalate_after_owner_removal_comments_without_review_request(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")
    calls, base = make_run(TIMELINE_184)

    def run(*a):
        if a[:2] == ("pr", "view") and "author" in a:
            return json.dumps({"author": {"login": BOT}})
        return base(*a)

    g.escalate("review", 5, True, "x", OWNER, run)
    assert not added(calls)
    assert not any("--add-reviewer" in c for c in calls)


def test_restart_limit_is_held_and_closes_nothing(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")
    calls, base = make_run(TIMELINE_184)

    def run(*a):
        if a[:2] == ("pr", "view") and "body,state,labels" in a:
            return json.dumps({"state": "OPEN", "body": "Refs #9", "labels": []})
        return base(*a)

    assert restart.handle_limit("5", OWNER, run) == "held"
    assert not any(c[:2] == ("pr", "close") for c in calls)


def test_status_limit_prs_skips_held_items():
    import datetime
    now = datetime.datetime(2026, 11, 9, tzinfo=datetime.UTC)
    pr = {"number": 5, "headRefName": "agent/9-x", "labels": [{"name": "review:3"}], "createdAt": "2026-11-01T00:00:00Z",
          "reviewDecision": "REVIEW_REQUIRED", "headRefOid": "a" * 40, "comments": []}
    assert status.limit_prs([pr], [], now) == [pr]
    assert status.limit_prs([pr], [], now, "", lambda p: True) == []
