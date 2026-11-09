import importlib.util
import pathlib

_path = pathlib.Path(__file__).parent.parent / "tools" / "trusted_issues.py"
_spec = importlib.util.spec_from_file_location("trusted_issues", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def ev(kind, label, actor):
    return {"event": kind, "label": {"name": label}, "actor": {"login": actor}}


def issue(author, *labels):
    return {"number": 1, "title": "t", "author": {"login": author}, "labels": [{"name": n} for n in labels]}


def test_label_set_by_owner():
    assert mod.label_set_by([ev("labeled", "approved", "Bankaifan")], "approved", "Bankaifan")


def test_label_set_by_other_is_rejected():
    assert not mod.label_set_by([ev("labeled", "approved", "mallory")], "approved", "Bankaifan")


def test_latest_event_wins():
    events = [ev("labeled", "approved", "Bankaifan"), ev("unlabeled", "approved", "Bankaifan"),
              ev("labeled", "approved", "mallory")]
    assert not mod.label_set_by(events, "approved", "Bankaifan")


def test_other_label_events_ignored():
    assert not mod.label_set_by([ev("labeled", "idea", "Bankaifan")], "approved", "Bankaifan")


def test_owner_issue_is_trusted():
    r = mod.classify(issue("Bankaifan", "agent:dev"), [], "Bankaifan")
    assert r["authored_by_owner"] and r["labels"] == ["agent:dev"]


def test_stranger_issue_is_dropped():
    assert mod.classify(issue("mallory", "idea"), [], "Bankaifan") is None


def test_stranger_issue_forged_label_is_dropped():
    events = [ev("labeled", "approved", "mallory")]
    assert mod.classify(issue("mallory", "approved"), events, "Bankaifan") is None


def test_idea_approved_by_owner():
    events = [ev("labeled", "approved", "Bankaifan")]
    r = mod.classify(issue("author-app[bot]", "idea", "approved"), events, "Bankaifan")
    assert r["approved"] and not r["auto_ok"] and "approved" in r["labels"]


def test_auto_ok_only_counts_from_owner():
    scout = [ev("labeled", "auto-ok", "author-app[bot]")]
    assert mod.classify(issue("author-app[bot]", "idea", "auto-ok"), scout, "Bankaifan") is None
    owner = [ev("labeled", "auto-ok", "Bankaifan")]
    assert mod.classify(issue("author-app[bot]", "idea", "auto-ok"), owner, "Bankaifan")["auto_ok"]
