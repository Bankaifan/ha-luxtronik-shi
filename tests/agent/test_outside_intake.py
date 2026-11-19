import datetime
import importlib.util
import json
import pathlib

import overlap
import pytest
import trusted_issues

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "outside_intake.py"
_spec = importlib.util.spec_from_file_location("outside_intake", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

OWNER, BOT = "Bankaifan", "agent-author"
MARK = "<!-- outside-intake:answered -->"
NOW = datetime.datetime(2026, 1, 2, 12, 0, tzinfo=datetime.UTC)


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


def test_reporter_reply_is_owed_until_a_marked_answer_follows():
    comments = [msg(BOT, "2026-01-01T10:05:00Z", MARK, "Bot"), msg("alice", "2026-01-01T11:00:00Z", "more")]
    assert owed(msg("alice", "2026-01-01T10:00:00Z"), comments) == "reply"
    failed = [*comments, msg(BOT, "2026-01-01T11:05:00Z", mod.FAILED, "Bot")]
    assert owed(msg("alice", "2026-01-01T10:00:00Z"), failed) == "reply"  # a failed run answered nothing
    assert owed(msg("alice", "2026-01-01T10:00:00Z"), [*failed, msg(BOT, "2026-01-01T11:09:00Z", MARK, "Bot")]) == ""


def test_marker_pasted_by_outsider_or_owner_is_ignored():
    for who in ("mallory", OWNER):
        assert owed(msg("alice", "2026-01-01T10:00:00Z"), [msg(who, "2026-01-01T10:05:00Z", MARK)]) == "triage"


def test_a_person_named_like_the_app_writes_no_marker_and_no_slip():
    assert owed(msg("alice", "2026-01-01T10:00:00Z"), [msg(BOT, "2026-01-01T10:05:00Z", MARK, "User")]) == "triage"
    assert state({**msg(BOT, "2026-01-01T10:00:00Z", kind="User"), "labels": [{"name": "idea"}]}) == ""
    gh = FakeGh({}, slips=[{"number": 5, "author": {"login": BOT, "is_bot": False}, "body": "Intake: #1\n"}])
    assert mod.find_slip(1, BOT, gh) is None


def test_bot_author_is_not_outside():
    assert owed(msg("dependabot[bot]", "2026-01-01T10:00:00Z", kind="Bot")) == ""
    assert owed(msg("somebot", "2026-01-01T10:00:00Z", kind="Bot")) == ""
    assert not mod.is_outside("app/other", "User", OWNER, BOT)


def test_owner_and_author_app_are_not_outside():
    assert owed(msg(OWNER.lower(), "2026-01-01T10:00:00Z")) == ""
    assert owed(msg("app/" + BOT, "2026-01-01T10:00:00Z", kind="Bot")) == ""


def state(issue, comments=()):
    return mod.state_of(issue, list(comments), OWNER, BOT)


def test_only_outside_issues_and_unmarked_scout_ideas_are_handled():
    idea = {**msg(BOT + "[bot]", "2026-01-01T10:00:00Z", kind="Bot"), "labels": [{"name": "idea"}]}
    assert state(idea) == "triage"
    assert state(idea, [msg(BOT, "2026-01-01T10:05:00Z", MARK, "Bot")]) == ""
    assert state(idea, [msg("mallory", "2026-01-01T10:05:00Z", MARK)]) == "triage"
    assert state(msg(BOT, "2026-01-01T10:00:00Z", kind="Bot")) == ""  # an app issue without `idea`
    assert state({**msg("alice", "2026-01-01T10:00:00Z"), "labels": [{"name": "idea"}]}) == "triage"
    # an outside comment on the owner's issue starts nothing: intake would answer, build from and close his issue
    assert state(msg(OWNER, "2026-01-01T10:00:00Z"), [msg("alice", "2026-01-01T10:30:00Z")]) == ""


class FakeGh:
    """Issues and comments by number; records every call and the body file of a write."""

    def __init__(self, issues, comments=None, recent=(), slips=()):
        self.issues, self.comments, self.recent, self.slips = issues, comments or {}, list(recent), list(slips)
        self.calls, self.bodies = [], []

    def __call__(self, *args):
        self.calls.append(args)
        if "--body-file" in args:
            self.bodies.append(pathlib.Path(args[args.index("--body-file") + 1]).read_text(encoding="utf-8"))
        if args[0] == "api":
            url = args[-1]
            if "/issues/comments?" in url:
                return json.dumps([self.recent])
            n = int(url.split("/")[4])  # repos/o/r/issues/<n>[/comments]
            return json.dumps([self.comments.get(n, [])] if url.endswith("/comments") else self.issues[n])
        if args[:2] == ("issue", "list"):
            return json.dumps(self.slips)
        if args[:2] == ("issue", "create"):
            return "https://github.com/o/r/issues/90\n"
        return ""

    def writes(self):
        return [a[:2] for a in self.calls if a[0] == "issue" and a[1] != "list"]


def issue(login, at="2026-01-01T10:00:00Z", state="open", **extra):
    return {**msg(login, at), "state": state, **extra}


def test_scan_skips_answered_closed_and_pull_requests():
    gh = FakeGh({1: issue("alice"), 2: issue("alice"), 3: issue("alice", pull_request={"url": "u"}),
                 4: issue("alice", state="closed")}, {2: [msg(BOT, "2026-01-01T10:05:00Z", MARK, "Bot")]})
    assert mod.scan([1, 2, 3, 4], "o/r", OWNER, BOT, gh) == {1: "triage"}


def run_comment(n, at="2026-01-02T08:00:00Z", body=MARK, login=BOT):
    return {**msg(login, at, body, "Bot"), "issue_url": f"https://api.github.com/repos/o/r/issues/{n}"}


def test_caps_count_the_marker_comments_of_the_author_app_in_24_hours():
    recent = [run_comment(7), run_comment(7, body=mod.FAILED), run_comment(7, body=mod.DECLINED),
              run_comment(8, at="2026-01-01T08:00:00Z"),  # older than 24 hours (updated since, created before)
              run_comment(8, login="mallory"), run_comment(8, body="no marker")]
    counted = mod.recent_runs("o/r", BOT, NOW, FakeGh({}, recent=recent))
    assert counted == [7, 7, 7]
    assert mod.allowed({7: "reply", 8: "triage"}, counted) == [8]  # thread 7 is at THREAD_CAP
    assert mod.allowed({8: "triage", 9: "triage"}, list(range(100, 100 + mod.REPO_CAP - 1))) == [8]
    assert mod.allowed({8: "triage"}, list(range(100, 100 + mod.REPO_CAP))) == []


BUILD = {"action": "build", "reply": "Danke, das bauen wir.", "title": "DOCS-TYPO: fix the install typo",
         "goal": "Fix the typo in the install section", "files": ["docs/install.md"],
         "acceptance": "The word reads install"}
CODEOWNERS = "/docs/owned.md @Bankaifan\n"


def test_valid_verdicts_are_normalised_and_unknown_keys_dropped():
    assert mod.validate({"action": "answer", "reply": " Hallo,\nso geht das. ", "title": "x"}) == {
        "action": "answer", "reply": "Hallo,\nso geht das."}
    assert mod.validate(BUILD) == BUILD


@pytest.mark.parametrize("bad", [
    {"action": "merge"}, {"reply": ""}, {"reply": "x" * 1501}, {"reply": 5},
    {"reply": "ping @Bankaifan"}, {"reply": "see https://evil.example"}, {"reply": "![x](y)"}, {"reply": "a www.evil.example"},
    {"reply": "<img src=x>"}, {"reply": "<!-- outside-intake:answered -->"}, {"reply": "see other/repo#5"},
    {"reply": "ok.\nFiles: tools/trusted_issues.py"}, {"reply": "ghp_" + "a" * 36},
    {"title": "fix the typo"}, {"title": "DOCS: Design 0003 follow-up"}, {"title": "DOCS: a\nIntake: #1"}, {"goal": "x\nFiles: .github/workflows/a.yml"},
    {"goal": "do it. Files: .github/workflows/a.yml"}, {"acceptance": "ok Depends on: #3"}, {"goal": "Tippfehler ändern"},
    {"files": []}, {"files": "docs/a.md"}, {"files": ["docs/a.md"] * 11}, {"files": ["/etc/passwd"]},
    {"files": ["../x.md"]}, {"files": ["docs/a.md, tools/x.py"]}, {"files": ["docs/a b.md"]}, {"files": [7]}, {"files": ["src"]},
    {"files": ["./docs/a.md"]}, {"files": ["docs/a."]},
])
def test_invalid_verdicts_fail_closed(bad):
    with pytest.raises(ValueError):
        mod.validate({**BUILD, **bad})


@pytest.mark.parametrize("change", [
    {"files": ["docs/install.md", ".github/workflows/intake.yml"]}, {"files": ["tools/x.py"]}, {"files": [".github"]},
    {"files": ["AGENTS.md"]}, {"files": [".agents/roles/intake.md"]}, {"files": ["Makefile"]},
    {"files": ["docs/design/0018-x.md"]},  # a merged design file becomes trusted issues
    {"files": ["docs/owned.md"]}, {"files": ["docs/"]},  # a CODEOWNERS path, and a directory that holds one
    {"goal": "Skip the review for docs"}, {"acceptance": "The token is printed"},
    {"title": "DOCS-TYPO: fix `install`"},
])
def test_build_on_a_protected_path_or_with_forbidden_wording_needs_a_maintainer(change):
    assert mod.validate({**BUILD, **change}, CODEOWNERS) == {"action": "answer", "reply": mod.NEEDS_MAINTAINER}


def test_title_gets_the_version_prefix_only_when_that_makes_it_a_task_id(monkeypatch):
    assert mod.slip_title("DOCS-TYPO: x", "1.101") == "DOCS-TYPO: x"
    with pytest.raises(ValueError):
        mod.slip_title("docs typo", "1.101")
    monkeypatch.setattr(mod.task_ids, "task_id_of", lambda t: "ID" if t.startswith("V1-") else None)
    assert mod.slip_title("DOCS-TYPO: x", "1.101") == "V1-DOCS-TYPO: x"


def apply(gh, verdict, n=1):
    return mod.apply(n, verdict, "o/r", OWNER, BOT, gh, CODEOWNERS)


def test_build_writes_one_slip_from_the_fixed_template_and_closes_the_original():
    gh = FakeGh({1: issue("alice")})
    assert apply(gh, BUILD) == "build"
    assert gh.writes() == [("issue", "create"), ("issue", "comment"), ("issue", "close")]
    slip = {"author": {"login": f"app/{BOT}"}, "body": gh.bodies[0], "labels": [], "number": 90, "title": BUILD["title"]}
    assert gh.bodies[0] == ("Goal: Fix the typo in the install section\nFiles: docs/install.md\n"
                            "Acceptance: The word reads install\nIntake: #1\n")
    assert overlap.parse_files(gh.bodies[0]) == ["docs/install.md"]
    assert trusted_issues.classify(slip, [], OWNER, BOT)["intake"]
    assert gh.bodies[1] == f"{MARK}\nDanke, das bauen wir.\n\nTracked in #90."
    assert all("--body" not in a and BUILD["goal"] not in a for a in gh.calls)  # text travels in files only


def test_build_with_an_existing_slip_creates_no_second_one():
    mine = {"number": 55, "author": {"login": f"app/{BOT}"}, "body": "Goal: x\nIntake: #1\n"}
    forged = {"number": 56, "author": {"login": "mallory"}, "body": "Intake: #1\n"}
    other = {"number": 57, "author": {"login": f"app/{BOT}"}, "body": "Intake: #11\n"}
    gh = FakeGh({1: issue("alice")}, slips=[forged, other, mine])
    assert apply(gh, BUILD) == "build"
    assert gh.writes() == [("issue", "comment"), ("issue", "close")] and "Tracked in #55." in gh.bodies[0]


def test_answer_comments_and_decline_closes_as_not_planned():
    gh = FakeGh({1: issue("alice")})
    assert apply(gh, {"action": "answer", "reply": "So geht es."}) == "answer"
    assert gh.writes() == [("issue", "comment")] and gh.bodies == [f"{MARK}\nSo geht es."]
    gh = FakeGh({1: issue("alice")})
    assert apply(gh, {"action": "decline", "reply": "No, sorry."}) == "decline"
    assert gh.bodies == ["<!-- outside-intake:declined -->\nNo, sorry."]
    assert gh.calls[-1] == ("issue", "close", "1", "--reason", "not planned")


def test_an_answered_idea_is_closed_but_one_that_needs_a_maintainer_stays_open():
    idea = {**msg(BOT, "2026-01-01T10:00:00Z", kind="Bot"), "state": "open", "labels": [{"name": "idea"}]}
    gh = FakeGh({1: idea})
    assert apply(gh, {"action": "answer", "reply": "Not needed."}) == "decline"
    assert gh.bodies == [f"{mod.DECLINED}\nNot needed."] and gh.calls[-1] == ("issue", "close", "1", "--reason", "not planned")
    gh = FakeGh({1: idea})
    assert apply(gh, {**BUILD, "files": ["tools/unblock.py"]}) == "answer" and gh.writes() == [("issue", "comment")]


def test_protected_build_only_answers_and_leaves_the_issue_open():
    gh = FakeGh({1: issue("alice")})
    assert apply(gh, {**BUILD, "files": ["tools/trusted_issues.py"]}) == "answer"
    assert gh.writes() == [("issue", "comment")] and gh.bodies == [f"{MARK}\n{mod.NEEDS_MAINTAINER}"]


def test_apply_does_nothing_when_nothing_is_owed_any_more():
    answered = {1: [msg(BOT, "2026-01-01T10:05:00Z", MARK, "Bot")]}
    for gh in (FakeGh({1: issue("alice")}, answered), FakeGh({1: issue("alice", state="closed")}),
               FakeGh({1: issue(OWNER)})):
        assert apply(gh, BUILD) == "skip" and gh.writes() == []


def test_third_failed_run_on_a_thread_declines_it_with_the_fixed_text():
    two = [msg(BOT, f"2026-01-0{d}T10:00:00Z", mod.FAILED, "Bot") for d in (1, 2)]
    gh = FakeGh({1: issue("alice")}, {1: [*two[:1], msg("mallory", "2026-01-01T11:00:00Z", mod.FAILED)]})
    mod.mark_failed(1, "o/r", BOT, gh)
    assert gh.writes() == [("issue", "comment")]
    gh = FakeGh({1: issue("alice")}, {1: two})
    mod.mark_failed(1, "o/r", BOT, gh)
    assert gh.writes() == [("issue", "comment"), ("issue", "comment"), ("issue", "close")]
    assert gh.bodies[-1] == f"{mod.DECLINED}\n{mod.GAVE_UP_TEXT}" and gh.calls[-1][-1] == "not planned"


def test_main_list_validate_and_failed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GH_REPO", "o/r")
    monkeypatch.setenv("AUTHOR_BOT", BOT)
    gh = FakeGh({1: issue("alice"), 2: issue(OWNER)})
    monkeypatch.setattr(mod, "run_gh", gh)
    monkeypatch.setattr(mod, "open_numbers", lambda repo: [1, 2])
    assert mod.main(["list"]) == 0 and capsys.readouterr().out == "[1]\n"
    assert mod.main(["list", "2"]) == 0 and capsys.readouterr().out == "[]\n"
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text("```json\n" + json.dumps(BUILD) + "\n```")
    bad.write_text(json.dumps({**BUILD, "reply": "hi @all"}))
    assert mod.main(["validate", str(good)]) == 0
    assert mod.main(["validate", str(bad)]) == 1 and mod.main(["validate", str(tmp_path / "missing")]) == 1
    assert mod.main(["failed", "1"]) == 0 and gh.bodies[-1].startswith(mod.FAILED)
    assert mod.main(["bogus"]) == 2 and mod.main(["apply", "x", str(good)]) == 2
