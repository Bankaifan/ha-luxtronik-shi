import importlib.util
import json
import pathlib

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "outside_intake.py"
_spec = importlib.util.spec_from_file_location("outside_intake", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

OWNER, BOT = "Bankaifan", "agent-author"
MARK = "<!-- outside-intake:answered -->"


def msg(login, at, body="", kind="User"):
    return {"user": {"login": login, "type": kind}, "created_at": at, "body": body}


def owed(issue, comments=()):
    return mod.owed(issue, list(comments), OWNER, BOT)


def test_new_outside_issue_needs_triage():
    assert owed(msg("alice", "2026-01-01T10:00:00Z")) == "triage"


def test_answered_issue_owes_nothing():
    comments = [msg(BOT + "[bot]", "2026-01-01T10:05:00Z", "text " + MARK, "Bot")]
    assert owed(msg("alice", "2026-01-01T10:00:00Z"), comments) == ""


def test_declined_marker_counts():
    comments = [msg(BOT, "2026-01-01T10:05:00Z", "<!-- outside-intake:declined -->", "Bot")]
    assert owed(msg("alice", "2026-01-01T10:00:00Z"), comments) == ""


def test_reporter_reply_is_owed():
    comments = [msg(BOT, "2026-01-01T10:05:00Z", MARK, "Bot"), msg("alice", "2026-01-01T11:00:00Z", "more")]
    assert owed(msg("alice", "2026-01-01T10:00:00Z"), comments) == "reply"


def test_reply_answered_again_owes_nothing():
    comments = [msg(BOT, "2026-01-01T10:05:00Z", MARK, "Bot"), msg("alice", "2026-01-01T11:00:00Z"),
                msg(BOT, "2026-01-01T11:05:00Z", "second answer", "Bot")]
    assert owed(msg("alice", "2026-01-01T10:00:00Z"), comments) == ""


def test_marker_pasted_by_outsider_is_ignored():
    comments = [msg("mallory", "2026-01-01T10:05:00Z", MARK)]
    assert owed(msg("alice", "2026-01-01T10:00:00Z"), comments) == "triage"


def test_marker_by_owner_is_ignored():
    comments = [msg(OWNER, "2026-01-01T10:05:00Z", MARK)]
    assert owed(msg("alice", "2026-01-01T10:00:00Z"), comments) == "triage"


def test_bot_author_is_not_outside():
    assert owed(msg("dependabot[bot]", "2026-01-01T10:00:00Z", kind="Bot")) == ""
    assert owed(msg("somebot", "2026-01-01T10:00:00Z", kind="Bot")) == ""
    assert not mod.is_outside("app/other", "User", OWNER, BOT)


def test_owner_and_author_app_are_not_outside():
    assert owed(msg(OWNER.lower(), "2026-01-01T10:00:00Z")) == ""
    assert owed(msg("app/" + BOT, "2026-01-01T10:00:00Z", kind="Bot")) == ""


def test_outside_comment_on_owner_issue_needs_triage():
    assert owed(msg(OWNER, "2026-01-01T10:00:00Z"), [msg("alice", "2026-01-01T10:30:00Z")]) == "triage"


def test_caps():
    state = {}
    for _ in range(mod.THREAD_CAP):
        assert mod.can_run(state, 7, "2026-01-01")
        mod.count_run(state, 7, "2026-01-01")
    assert not mod.can_run(state, 7, "2026-01-01")
    assert mod.can_run(state, 8, "2026-01-01")
    assert mod.can_run(state, 7, "2026-01-02")  # a new day resets
    for n in range(100, 100 + mod.REPO_CAP - mod.THREAD_CAP):
        mod.count_run(state, n, "2026-01-01")
    assert not mod.can_run(state, 8, "2026-01-01")


class FakeGh:
    def __init__(self, issues, comments):
        self.issues, self.comments = issues, comments

    def __call__(self, *args):
        url = args[-1]
        n = int(url.split("/")[4])  # repos/o/r/issues/<n>[/comments]
        if url.endswith("/comments"):
            return json.dumps([self.comments.get(n, [])])
        return json.dumps(self.issues[n])


def issue(login, at, state="open", **extra):
    return {**msg(login, at), "state": state, **extra}


def test_scan_and_cursor_keeps_thread_listed():
    gh = FakeGh({1: issue("alice", "2026-01-01T10:00:00Z"), 2: issue("alice", "2026-01-01T10:00:00Z"),
                 3: issue("alice", "2026-01-01T10:00:00Z", pull_request={"url": "u"}),
                 4: issue("alice", "2026-01-01T10:00:00Z", state="closed")},
                {2: [msg(BOT, "2026-01-01T10:05:00Z", MARK, "Bot")]})
    state = {"owed": {"4": "triage"}}
    found = mod.listing(state, [1, 2, 3], "o/r", OWNER, BOT, gh)
    assert found == {1: "triage"}
    assert state["owed"] == {"1": "triage"}  # the closed thread leaves the cursor, the answered one never enters


def test_cursor_lists_thread_missing_from_open_list():
    gh = FakeGh({5: issue("alice", "2026-01-01T10:00:00Z")}, {})
    state = {"owed": {"5": "triage"}}
    assert mod.listing(state, [], "o/r", OWNER, BOT, gh) == {5: "triage"}


def test_main_list_and_record(tmp_path, monkeypatch, capsys):
    cursor = tmp_path / "c.json"
    monkeypatch.setenv("GH_REPO", "o/r")
    monkeypatch.setenv("AUTHOR_BOT", BOT)
    monkeypatch.setenv("OUTSIDE_CURSOR", str(cursor))
    gh = FakeGh({1: issue("alice", "2026-01-01T10:00:00Z")}, {})
    monkeypatch.setattr(mod, "run_gh", gh)
    monkeypatch.setattr(mod, "open_numbers", lambda repo: [1])
    assert mod.main(["list"]) == 0
    assert capsys.readouterr().out == "1 triage\n"
    for _ in range(mod.THREAD_CAP):
        assert mod.main(["record", "1"]) == 0
    assert mod.main(["record", "1"]) == 1
    assert mod.main(["bogus"]) == 2
