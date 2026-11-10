import importlib.util
import pathlib

import guard_mark
import pytest

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


BOT = "author-app[bot]"
DESIGN = "Part 1 of 3.\n\nDesign: docs/design/0001-big-thing.md\n"


def derived(author=BOT, body=DESIGN, labels=("agent:dev",)):
    d = issue(author, *labels)
    d["body"] = body
    return d


def exists(path):
    return path == "docs/design/0001-big-thing.md"


def test_design_derived_issue_is_trusted():
    r = mod.classify(derived(), [], "Bankaifan", BOT, exists)
    assert r["design"] == "docs/design/0001-big-thing.md"
    assert not r["authored_by_owner"] and not r["approved"] and not r["auto_ok"]


def test_design_ref_from_stranger_is_dropped():
    assert mod.classify(derived(author="mallory"), [], "Bankaifan", BOT, exists) is None


def test_design_ref_without_configured_bot_is_dropped():
    assert mod.classify(derived(), [], "Bankaifan", "", exists) is None


def test_design_ref_to_missing_file_is_dropped():
    body = "Design: docs/design/0002-other.md\n"
    assert mod.classify(derived(body=body), [], "Bankaifan", BOT, exists) is None


def test_design_ref_must_be_its_own_line_in_docs_design():
    for body in ("see Design: docs/design/0001-big-thing.md", "Design: ../docs/design/0001-big-thing.md",
                 "Design: docs/design/0001-big-thing.md/../../x.md", "no ref"):
        assert mod.classify(derived(body=body), [], "Bankaifan", BOT, lambda p: True) is None


def test_bot_idea_with_design_line_is_not_trusted():
    assert mod.classify(derived(labels=("idea",)), [], "Bankaifan", BOT, exists) is None


def test_missing_body_is_dropped():
    d = derived()
    d["body"] = None
    assert mod.classify(d, [], "Bankaifan", BOT, exists) is None


@pytest.mark.parametrize("form", ["author-app", "app/author-app", "author-app[bot]"])
def test_design_issue_author_in_any_login_form(form):
    assert mod.classify(derived(author=form), [], "Bankaifan", BOT, exists)["design"]


@pytest.mark.parametrize("form", ["Bankaifan", "app/Bankaifan", "Bankaifan[bot]"])
def test_owner_in_any_login_form(form):
    assert mod.classify(issue(form), [], "Bankaifan")["authored_by_owner"]
    assert mod.label_set_by([ev("labeled", "approved", form)], "approved", "Bankaifan")


def test_auto_ok_only_counts_from_owner():
    scout = [ev("labeled", "auto-ok", "author-app[bot]")]
    assert mod.classify(issue("author-app[bot]", "idea", "auto-ok"), scout, "Bankaifan") is None
    owner = [ev("labeled", "auto-ok", "Bankaifan")]
    assert mod.classify(issue("author-app[bot]", "idea", "auto-ok"), owner, "Bankaifan")["auto_ok"]


SHA = "a" * 40


def sync_issue(author=BOT, title="Template sync aaaaaaa", body="Changes.\n\nTemplate-Sync: " + SHA + "\n"):
    d = issue(author, "agent:dev", "model:sonnet")
    d["title"], d["body"] = title, body
    return d


def test_sync_issue_is_trusted():
    r = mod.classify(sync_issue(), [], "Bankaifan", BOT, exists)
    assert r["template_sync"] and not r["authored_by_owner"] and not r["approved"]


@pytest.mark.parametrize("form", ["author-app", "app/author-app", "author-app[bot]"])
def test_sync_issue_author_in_any_login_form(form):
    assert mod.classify(sync_issue(author=form), [], "Bankaifan", BOT, exists)["template_sync"]


def test_sync_issue_from_stranger_is_dropped():
    assert mod.classify(sync_issue(author="mallory"), [], "Bankaifan", BOT, exists) is None


def test_sync_issue_without_configured_bot_is_dropped():
    assert mod.classify(sync_issue(), [], "Bankaifan", "", exists) is None


def test_sync_issue_needs_title_prefix():
    assert mod.classify(sync_issue(title="Please sync"), [], "Bankaifan", BOT, exists) is None


@pytest.mark.parametrize("body", [
    "no marker", "Template-Sync: " + "a" * 39, "Template-Sync: " + "A" * 40, "Template-Sync: " + "a" * 41,
    "see Template-Sync: " + SHA, None])
def test_sync_issue_needs_valid_sha_line(body):
    assert mod.classify(sync_issue(body=body), [], "Bankaifan", BOT, exists) is None


def _mk(n, prio=None):
    i = issue("Bankaifan", *(["prio:" + str(prio)] if prio else []))
    i["number"] = n
    evs = [ev("labeled", "prio:" + str(prio), "Bankaifan")] if prio else []
    return mod.classify(i, evs, "Bankaifan")


def test_prio_sort_order_then_oldest():
    out = [_mk(1), _mk(2, 3), _mk(3, 1), _mk(4, 2), _mk(5, 1)]
    out.sort(key=lambda r: (r["prio"], r["number"]))
    assert [r["number"] for r in out] == [3, 5, 4, 2, 1]
    assert out[-1]["prio"] == 4


def test_prio_label_by_stranger_is_ignored():
    r = mod.classify(issue("Bankaifan", "prio:1"), [ev("labeled", "prio:1", "mallory")], "Bankaifan", BOT)
    assert r["prio"] == 4


def test_prio_label_by_author_app_counts():
    r = mod.classify(issue("Bankaifan", "prio:2"), [ev("labeled", "prio:2", BOT)], "Bankaifan", BOT)
    assert r["prio"] == 2


KEY = "k" * 32
FAILING = "Failing workflow: ci.yml"


def guard(title=FAILING, author=BOT, signed=True):
    d = issue(author, "agent:dev")
    d["title"] = title
    d["body"] = guard_mark.sign(title, "The workflow failed.", KEY) if signed else "The workflow failed."
    return d


def test_signed_failing_workflow_issue_is_trusted():
    assert mod.classify(guard(), [], "Bankaifan", BOT, guard_key=KEY)["guard"]


def test_signed_issue_with_other_title_is_not_trusted():
    assert mod.classify(guard(title="Something else"), [], "Bankaifan", BOT, guard_key=KEY) is None


def test_failing_workflow_issue_needs_signature_and_bot_author():
    assert mod.classify(guard(signed=False), [], "Bankaifan", BOT, guard_key=KEY) is None
    assert mod.classify(guard(author="mallory"), [], "Bankaifan", BOT, guard_key=KEY) is None
