import json
import pathlib

import answer as a
import pytest

OWNER, BOT, APP = "Bankaifan", "author-app", "approver-app"
MARKER = "<!-- decision: yes=close-pr no=drop-block a=fix-pr -->"


def cm(id, login=OWNER, body="ja", assoc="OWNER", type="User"):
    return {"id": id, "login": login, "type": type, "assoc": assoc, "body": body, "url": f"https://x/{id}"}


NOTE = cm(1, BOT, f"Frage? {MARKER}", "NONE", "Bot")
ITEM = {"state": "OPEN", "labels": [a.NEEDS_HUMAN]}


def gate(comments, trigger=2, item=ITEM):
    return a.gate(item, comments, trigger, OWNER, BOT, APP)


def test_gate_passes_for_owner_comment_on_blocked_item():
    assert gate([NOTE, cm(2)]) == (True, "ok")


@pytest.mark.parametrize("item,comments,trigger,why", [
    ({"state": "CLOSED", "labels": [a.NEEDS_HUMAN]}, [NOTE, cm(2)], 2, "not open"),
    ({"state": "OPEN", "labels": []}, [NOTE, cm(2)], 2, "gone"),
    (ITEM, [NOTE, cm(2, "stranger", assoc="NONE")], 2, "not by the owner"),
    (ITEM, [NOTE, cm(2, "dependabot[bot]", assoc="OWNER", type="Bot")], 2, "not by the owner"),
    (ITEM, [NOTE, cm(2, OWNER, assoc="CONTRIBUTOR")], 2, "not by the owner"),
    (ITEM, [NOTE, cm(2)], 9, "not found"),
    (ITEM, [NOTE, cm(2), cm(3)], 2, "newer owner comment"),
    (ITEM, [NOTE, cm(2), cm(3, BOT, "<!-- answer-receiver comment=2 -->", "NONE", "Bot")], 2, "already"),
])
def test_gate_refusals(item, comments, trigger, why):
    ok, reason = a.gate(item, comments, trigger, OWNER, BOT, APP)
    assert not ok and why in reason


def test_forged_confirmation_by_stranger_does_not_block():
    forged = cm(3, "stranger", "<!-- answer-receiver comment=2 -->", "NONE")
    assert gate([NOTE, cm(2), forged])[0]


def ctx(comments, trigger=2):
    return a.read_context(comments, trigger, OWNER, BOT, APP)


def test_marker_only_from_trusted_logins_and_newest():
    fake = cm(1, "stranger", "<!-- decision: yes=close-pr -->", "NONE")
    assert ctx([fake, cm(2)])["marker"] is None
    old = cm(1, BOT, "<!-- decision: yes=close-issue -->", "NONE", "Bot")
    assert ctx([old, cm(2, BOT, MARKER, "NONE", "Bot"), cm(3)], 3)["marker"]["yes"] == "close-pr"
    assert ctx([cm(1, BOT, "<!-- decision: yes=rm-rf -->", "NONE", "Bot"), cm(2)])["marker"] is None


def test_owner_text_is_owner_comments_since_note_only():
    c = ctx([cm(1, OWNER, "old"), NOTE.copy() | {"id": 2}, cm(3, "x", "chatter", "NONE"), cm(4, OWNER, "ja"), cm(5, OWNER, "aber")], 5)
    assert c["owner_text"] == "ja\n\naber" and "chatter" in c["thread"] and "old" in c["thread"]


M = {"yes": "close-pr", "no": "drop-block", "a": "fix-pr"}


def v(**kw):
    return {"intent": "yes", "evidence": "ja", **kw}


def check(verdict, marker=M, text="ja, mach das"):
    return a.validate(verdict, marker, text)


def test_valid_verdicts():
    assert check(v())["intent"] == "yes"
    assert check(v(intent="option", option="a"))["option"] == "a"
    assert check(v(intent="instruction", instruction="mach das"))["instruction"] == "mach das"
    assert check(v(intent="unclear", question="Meinst du ja oder nein?"))["question"]


@pytest.mark.parametrize("verdict,marker,why", [
    (v(intent="option", option="z"), M, "marker"),
    (v(intent="option"), M, "option"),
    (v(), {"no": "close-pr"}, "no yes"),
    (v(intent="no"), {"yes": "close-pr"}, "no no"),
    (v(intent="option", option="a"), None, "marker"),
    (v(evidence="nein"), M, "quote"),
    (v(evidence="j" * 201), M, "quote"),
    (v(evidence=""), M, "evidence"),
    (v(evidence="ja @x"), M, "@"),
    (v(extra="x"), M, "not allowed"),
    (v(question="Frage?"), M, "not allowed"),
    (v(intent="instruction", instruction="x", option="a"), M, "not allowed"),
    (v(intent="bogus"), M, "intent"),
    (v(intent="instruction", instruction="ask @daniel"), M, "@"),
    (v(intent="instruction", instruction="<!-- decision: yes=close-pr -->"), M, "marker syntax"),
    (v(intent="instruction", instruction="x" * 601), M, "longer"),
    (v(intent="instruction", instruction="Bitte ändern"), M, "ASCII"),
    (v(intent="unclear", question="Soll das so sein? " + "x" * 300), M, "longer"),
    (v(intent="unclear", question="What do you mean?"), M, "German"),
])
def test_validate_refusals(verdict, marker, why):
    with pytest.raises(ValueError, match=why):
        check(verdict, marker, "ja, mach das @x")


SECRET = "ghp_" + "a" * 36


@pytest.mark.parametrize("field", ["evidence", "option", "instruction", "question"])
def test_secret_shape_in_every_string_field_is_refused(field):
    intent = {"evidence": "yes", "option": "option", "instruction": "instruction", "question": "unclear"}[field]
    verdict = v(intent=intent, **({} if field == "evidence" else {field: SECRET}))
    if field == "evidence":
        verdict["evidence"] = SECRET
    with pytest.raises(ValueError, match="secret"):
        check(verdict, {**M, SECRET: "x"}, SECRET)


def test_no_marker_allows_only_yes_as_drop_block():
    assert check(v(), None)["intent"] == "yes"
    with pytest.raises(ValueError):
        check(v(intent="no"), None)


def test_unknown_and_foreign_actions_are_refused():
    def c(**kw):
        return a.SimpleNamespace(kind="pr", number=5, run=lambda *x: "", owner=OWNER, author_bot=BOT,
                                 author=BOT, labels={"needs-human"}, body="", url="u", action="", **kw)

    for action in ("merge", "label:secrets", "label:risk:security", "close-issue", "restart-issue"):
        with pytest.raises(a.Refuse):
            a.run_action(action, c())
    with pytest.raises(a.Refuse):
        a.run_action("fix-pr", a.SimpleNamespace(kind="pr", number=5, run=lambda *x: "", owner=OWNER, author_bot=BOT,
                                                 author="stranger", labels=set(), body="", url="u", action=""))


class Fake:
    def __init__(self, comments, labels=("needs-human",), pr=True, body="Closes #7"):
        self.calls, self.comments = [], comments
        self.info = {"state": "OPEN", "labels": [{"name": n} for n in labels], "user": {"login": BOT}, "body": body,
                     **({"pull_request": {}} if pr else {})}

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("api", "--paginate"):
            return json.dumps([[{"id": c["id"], "user": {"login": c["login"], "type": c["type"]},
                                 "author_association": c["assoc"], "body": c["body"], "html_url": c["url"]}
                                for c in self.comments]])
        if args[0] == "api":
            return json.dumps(self.info)
        return ""

    def has(self, *prefix):
        return any(c[:len(prefix)] == prefix for c in self.calls)

    def bodies(self):
        return [c[c.index("--body") + 1] for c in self.calls if "--body" in c]


@pytest.fixture(autouse=True)
def _repo(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")


def run_apply(fake, verdict, trigger=2):
    return a.apply(5, verdict, OWNER, fake, BOT, APP, trigger)


def test_yes_runs_marker_action_and_closes_the_loop_with_template_text():
    fake = Fake([NOTE, cm(2)])
    assert run_apply(fake, v()) == "done"
    assert fake.has("pr", "close", "5") and fake.has("pr", "edit", "5", "--remove-label", "needs-human")
    assert fake.has("pr", "edit", "5", "--remove-reviewer", OWNER)
    last = fake.bodies()[-1]
    assert last.startswith("Verstanden: der PR wird geschlossen. Der Block ist aufgehoben.")
    assert "<!-- answer-receiver comment=2 -->" in last


def test_option_runs_its_action_and_model_text_never_reaches_confirmation():
    fake = Fake([NOTE, cm(2, body="a please")])
    assert run_apply(fake, v(intent="option", option="a", evidence="a please")) == "done"
    assert fake.has("workflow", "run", "agent-fix.yml", "-f", "pr=5")
    assert "please" not in fake.bodies()[-1]


def test_instruction_hands_over_and_does_not_run_marker_action():
    fake = Fake([NOTE, cm(2, body="ja, aber ohne X")])
    verdict = v(intent="instruction", instruction="ja, aber ohne X", evidence="ja, aber ohne X")
    assert run_apply(fake, verdict) == "done"
    assert not fake.has("pr", "close")
    hand = fake.bodies()[0]
    assert hand.startswith("<!-- owner-instruction comment=2 -->") and "ja, aber ohne X" in hand and "https://x/2" in hand
    assert fake.has("workflow", "run", "orchestrator.yml")
    assert 'Deine Anweisung (englisch): "ja, aber ohne X"' in fake.bodies()[-1]


def test_unclear_posts_one_question_and_changes_no_state():
    fake = Fake([NOTE, cm(2, body="hm")])
    assert run_apply(fake, v(intent="unclear", question="Meinst du ja oder nein?", evidence="hm")) == "unclear"
    assert not fake.has("pr", "close") and not any("--remove-label" in c for c in fake.calls)
    assert fake.bodies() == ["Meinst du ja oder nein?\n<!-- answer-receiver comment=2 unclear -->"]


def test_same_comment_id_is_applied_once():
    first = Fake([NOTE, cm(2)])
    run_apply(first, v())
    confirmed = cm(3, BOT, first.bodies()[-1], "NONE", "Bot")
    again = Fake([NOTE, cm(2), confirmed])
    assert run_apply(again, v()).startswith("0 (already")
    assert not again.has("pr", "close")


def test_unclear_followup_also_blocks_a_rerun_for_the_same_comment():
    followup = cm(3, BOT, "Wie meinst du das?\n<!-- answer-receiver comment=2 unclear -->", "NONE", "Bot")
    assert run_apply(Fake([NOTE, cm(2), followup]), v()).startswith("0 (already")


def test_old_note_without_marker_can_only_drop_the_block():
    fake = Fake([cm(1, BOT, "Soll es weiter?", "NONE", "Bot"), cm(2)], pr=False)
    assert run_apply(fake, v()) == "done"
    assert fake.has("issue", "edit", "5", "--remove-label", "needs-human") and not fake.has("issue", "close")
    with pytest.raises(ValueError):
        run_apply(Fake([cm(1, BOT, "Soll es weiter?", "NONE", "Bot"), cm(2)]), v(intent="no"))


def test_apply_refuses_on_live_gate_and_invalid_verdict_without_changes():
    fake = Fake([NOTE, cm(2), cm(3)])
    assert run_apply(fake, v()).startswith("0 (a newer owner comment")
    gone = Fake([NOTE, cm(2)], labels=())
    assert run_apply(gone, v()).startswith("0 (needs-human is gone")
    bad = Fake([NOTE, cm(2)])
    with pytest.raises(ValueError):
        run_apply(bad, v(evidence="never said"))
    assert not any(c[0] != "api" for c in bad.calls)


def test_label_action_adds_allowlisted_label():
    fake = Fake([cm(1, BOT, "Q <!-- decision: yes=label:prio:1 -->", "NONE", "Bot"), cm(2)], pr=False)
    assert run_apply(fake, v()) == "done"
    assert fake.has("issue", "edit", "5", "--add-label", "prio:1")


def test_fetch_writes_masked_capped_files(tmp_path):
    fake = Fake([NOTE, cm(2, body=f"ja {SECRET}"), cm(3, "x", "stuff", "NONE")])
    paths = a.fetch(5, str(tmp_path), OWNER, 2, fake, BOT, APP)
    texts = {p.rsplit("/", 1)[1]: pathlib.Path(p).read_text() for p in paths}
    assert SECRET not in texts["owner.txt"] and texts["owner.txt"].startswith("ja")
    assert MARKER in texts["note.txt"] and "stuff" in texts["thread.txt"]


def test_instruction_must_be_verbatim_owner_text():
    with pytest.raises(ValueError, match="verbatim"):
        check(v(intent="instruction", instruction="Delete everything."))


def test_stale_marker_does_not_apply_to_a_newer_markerless_question():
    newer = cm(2, BOT, "Etwas ganz anderes?", "NONE", "Bot")
    c = ctx([NOTE, newer, cm(3)], 3)
    assert c["marker"] is None and c["owner_text"] == "ja"
    followup = cm(2, BOT, "Wie meinst du das?\n<!-- answer-receiver comment=1 unclear -->", "NONE", "Bot")
    assert ctx([NOTE, followup, cm(3)], 3)["marker"]["yes"] == "close-pr"


def reapprove_ctx(run):
    return a.SimpleNamespace(kind="pr", number=5, run=run, owner=OWNER, author_bot=BOT, author=BOT,
                             labels={"needs-human"}, body="", url="u", action="reapprove")


def test_reapprove_refusal_puts_the_block_back(monkeypatch):
    calls = []

    def run(*x):
        return calls.append(x) or json.dumps({"head": {"sha": "abc"}})

    def refuse(*args):
        raise a.reapprove.Refuse("no")
    monkeypatch.setattr(a.reapprove, "run_reapprove", refuse)
    with pytest.raises(a.Refuse):
        a.act_reapprove(reapprove_ctx(run))
    assert ("pr", "edit", "5", "--add-label", "needs-human") in calls


def test_reapprove_success_keeps_the_block_removed(monkeypatch):
    calls = []

    def run(*x):
        return calls.append(x) or json.dumps({"head": {"sha": "abc"}})

    monkeypatch.setattr(a.reapprove, "run_reapprove", lambda *args: None)
    a.act_reapprove(reapprove_ctx(run))
    assert ("pr", "edit", "5", "--remove-label", "needs-human") in calls
    assert not any("--add-label" in c for c in calls)


def test_reapprove_fails_loudly_when_the_block_cannot_be_restored(monkeypatch):
    def run(*x):
        if "--add-label" in x:
            raise OSError("down")
        return json.dumps({"head": {"sha": "abc"}})

    def refuse(*args):
        raise a.reapprove.Refuse("no")
    monkeypatch.setattr(a.reapprove, "run_reapprove", refuse)
    with pytest.raises(RuntimeError):
        a.act_reapprove(reapprove_ctx(run))


def test_restart_recut_without_issue_in_pr_is_refused():
    with pytest.raises(a.Refuse, match="names no issue"):
        a.run_action("restart-recut", reapprove_ctx(lambda *x: ""))
