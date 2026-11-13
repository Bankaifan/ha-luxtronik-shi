import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "tools"))

import slip

BOT = {"login": "bankaifan-agent-author"}
OWNER = {"login": "Bankaifan"}
STRANGER = {"login": "mallory"}


def issue(body="", author=BOT, comments=(), labels=()):
    return {"body": body, "author": author, "comments": list(comments), "labels": [{"name": n} for n in labels]}


def test_slip_in_body_of_author_app_issue():
    assert slip.has_slip(issue("Files: tools/a.py, tests/test_a.py"))


def test_stranger_body_is_no_slip_even_when_approved():
    i = issue("Files: tools/a.py", author=STRANGER, labels=["approved"])
    assert not slip.has_slip(i)


def test_slip_in_trusted_comment_counts_stranger_comment_does_not():
    assert slip.has_slip(issue("idea", author=OWNER, comments=[{"author": BOT, "body": "Files: tools/a.py"}]))
    assert not slip.has_slip(issue("idea", author=OWNER, comments=[{"author": STRANGER, "body": "Files: tools/a.py"}]))


@pytest.mark.parametrize("path,model", [
    ("a.py", "haiku"),
    ("docs/guide.md", "haiku"),
    ("tests/agent/test_x.py", "haiku"),
    ("tools/other.py", "haiku"),
    (".github/workflows/agent-dev.yml", "sonnet"),
    ("tools/ci/risk.py", "sonnet"),
    ("tools/trusted_issues.py", "sonnet"),
    ("tools/agent_guard.py", "sonnet"),
    ("tools/dispatch.py", "sonnet"),
    ("tools/slip.py", "sonnet"),
    (".github/CODEOWNERS", "sonnet"),
    ("docs/design/0016-x.md", "sonnet"),
])
def test_path_table(path, model):
    assert slip.model_of(issue(f"Files: {path}")) == model


def test_one_core_path_among_many_is_sonnet():
    assert slip.model_of(issue("Files: a.py, tools/ci/risk.py")) == "sonnet"


def test_failed_round_escalates_to_sonnet():
    assert slip.model_of(issue("Files: a.py", labels=["restart:1"])) == "sonnet"
    assert slip.model_of(issue("Files: a.py", labels=["stalled:1"])) == "sonnet"
    assert slip.model_of(issue("Files: a.py", labels=["agent:dev"])) == "haiku"


def test_model_line_and_label_are_only_hints():
    assert slip.model_of(issue("Files: a.py\nModel: sonnet")) == "haiku"
    assert slip.model_of(issue("Files: a.py", labels=["model:sonnet"])) == "haiku"
    assert slip.model_of(issue("Files: tools/ci/x.py\nModel: haiku")) == "sonnet"


def test_opus_is_never_chosen_and_stranger_model_ignored():
    assert slip.model_of(issue("Files: a.py\nModel: opus")) == "haiku"
    assert slip.model_of(issue("Model: sonnet", author=STRANGER)) == "haiku"
