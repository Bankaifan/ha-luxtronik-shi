import importlib.util
import json
import pathlib
import subprocess

_path = pathlib.Path(__file__).parent.parent / "tools" / "approval.py"
_spec = importlib.util.spec_from_file_location("approval", _path)
ap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ap)

SHA = "a" * 40
BOT = "app/approver"
SEC = {"risk:security"}


def comment(body, login="approver[bot]"):
    return {"user": {"login": login}, "body": body}


def test_verdict_is_per_head_and_per_approver():
    cs = [comment("security-review: changes " + SHA[:7]), comment("security-review: approve " + "b" * 7)]
    assert ap.security_verdict(cs, SHA, BOT) == "changes"
    assert ap.security_verdict(cs, "b" * 40, BOT) == "approve"
    assert ap.security_verdict(cs, "c" * 40, BOT) is None
    assert ap.security_verdict([comment("security-review: changes " + SHA, "mallory")], SHA, BOT) is None
    assert ap.security_verdict(cs, SHA, "") is None
    assert ap.security_verdict([{"author": {"login": "approver"}, "body": "security-review: changes " + SHA}],
                               SHA, BOT) == "changes"


def test_newest_verdict_for_the_head_wins():
    cs = [comment("security-review: changes " + SHA), comment("security-review: approve " + SHA)]
    assert ap.security_verdict(cs, SHA, BOT) == "approve"


def test_code_approved_plus_security_changes_is_not_approved():
    cs = [comment("security-review: changes " + SHA)]
    assert not ap.effective_approval("APPROVED", SEC, cs, SHA, BOT)
    assert ap.security_changes(SEC, cs, SHA, BOT)


def test_approved_cases():
    ok = [comment("security-review: approve " + SHA)]
    assert ap.effective_approval("APPROVED", SEC, ok, SHA, BOT)
    assert ap.effective_approval("APPROVED", set(), [comment("security-review: changes " + SHA)], SHA, BOT)  # no risk label
    assert ap.effective_approval("APPROVED", SEC, [], SHA, BOT)  # no verdict yet: the status gate decides
    assert not ap.effective_approval("CHANGES_REQUESTED", SEC, ok, SHA, BOT)
    assert not ap.effective_approval(None, set(), [], SHA, BOT)


def test_changes_for_an_older_head_does_not_block_the_new_head():
    cs = [comment("security-review: changes " + "b" * 40)]
    assert ap.effective_approval("APPROVED", SEC, cs, SHA, BOT)


def fake(decision, labels, comments, sha=SHA):
    def run(*args):
        if args[0] == "pr":
            return json.dumps({"reviewDecision": decision, "labels": [{"name": n} for n in labels], "headRefOid": sha})
        return json.dumps([comments])
    return run


def test_cli_check_and_security_changes(monkeypatch, capsys):
    monkeypatch.setenv("GH_REPO", "o/r")
    monkeypatch.setenv("APPROVER_BOT", BOT)
    run = fake("APPROVED", ["risk:security"], [comment("security-review: changes " + SHA)])
    assert ap.main(["approval.py", "check", "5"], run) == 0
    assert ap.main(["approval.py", "security-changes", "5"], run) == 0
    assert capsys.readouterr().out.split() == ["not-approved", "yes"]
    assert ap.main(["approval.py", "check", "5"], fake("APPROVED", [], [])) == 0
    assert capsys.readouterr().out.split() == ["approved"]


def test_cli_unreadable_pr_never_approves(monkeypatch, capsys):
    monkeypatch.setenv("GH_REPO", "o/r")

    def boom(*args):
        raise subprocess.CalledProcessError(1, "gh")
    ap.main(["approval.py", "check", "5"], boom)
    ap.main(["approval.py", "security-changes", "5"], boom)
    assert capsys.readouterr().out.split() == ["not-approved", "unknown"]
    assert ap.main(["approval.py", "check", "x"]) == 2
