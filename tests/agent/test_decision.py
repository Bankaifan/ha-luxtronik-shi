import agent_guard
import decision
import pytest
import restart
import unblock


def test_build_and_parse_roundtrip():
    line = decision.build(yes="restart-recut", no="close-pr")
    assert line == "<!-- decision: yes=restart-recut no=close-pr -->"
    assert decision.parse(f"Frage?\n{line}") == {"yes": "restart-recut", "no": "close-pr"}


def test_option_keys_and_label_actions():
    assert decision.parse("<!-- decision: a=label:prio:1 b=drop-block -->") == {"a": "label:prio:1", "b": "drop-block"}


@pytest.mark.parametrize("text", [
    "<!-- decision: yes=merge no=close-pr -->",  # merge is never in the list
    "<!-- decision: yes=label:secrets -->",  # label outside the list
    "<!-- decision: yes=close-pr yes=drop-block -->",  # duplicate key
    "<!-- decision: maybe=close-pr -->",  # bad key
    "<!-- decision: yes -->",  # no action
    "<!-- decision: -->",
    "no marker at all",
    None,
])
def test_malformed_marker_is_refused(text):
    assert decision.parse(text) is None


def test_build_refuses_unknown_action():
    with pytest.raises(ValueError):
        decision.build(yes="merge")
    with pytest.raises(ValueError):
        decision.build()


def test_newest_marker_by_trusted_login_only():
    comments = [
        {"login": "bot", "body": "<!-- decision: yes=close-pr -->"},
        {"login": "bot", "body": "<!-- decision: yes=drop-block -->"},
        {"login": "stranger", "body": "<!-- decision: yes=close-issue -->"},
    ]
    assert decision.newest(comments, {"bot"}) == {"yes": "drop-block"}
    assert decision.newest(comments, {"nobody"}) is None


def test_restart_note_has_marker_and_names_answers():
    assert decision.parse(restart.NOTE_RESTARTED) == {"yes": "restart-recut", "no": "close-pr"}
    assert "(ja)" in restart.NOTE_RESTARTED and "(nein)" in restart.NOTE_RESTARTED


def test_escalate_note_carries_marker(monkeypatch):
    posted = []
    monkeypatch.setattr(agent_guard.liveness, "post_comment", lambda kind, n, body, run: posted.append(body))
    monkeypatch.setattr(agent_guard, "add_labels", lambda *a, **k: None)
    monkeypatch.setattr(agent_guard.owner_hold, "held", lambda *a, **k: True)
    monkeypatch.setenv("AUTHOR_BOT", "author-bot")  # known history (empty): the first denial may offer a retrigger
    agent_guard.escalate("dev", 5, True, "silent", "Bankaifan", run=lambda *a: "[[]]" if "--paginate" in a else "")
    assert decision.parse(posted[0]) == {"yes": "drop-block", "no": "close-pr"}
    assert "(ja)" in posted[0] and "(nein)" in posted[0]


@pytest.mark.parametrize("kind,no", [("pr", "close-pr"), ("issue", "close-issue")])
def test_unblock_owner_note_carries_marker_and_effect(monkeypatch, kind, no):
    posted = []
    monkeypatch.setattr(unblock, "_comment", lambda run, k, n, body: posted.append(body))
    monkeypatch.setattr(unblock, "_last_comment_is", lambda *a: True)
    unblock._owner_note(lambda *a: "", kind, 7, "Bankaifan", {}, "Hallo Daniel, Frage: weiter?")
    assert decision.parse(posted[0]) == {"yes": "drop-block", "no": no}
    assert "Ja hebt den Block auf, nein schliesst" in posted[0]
