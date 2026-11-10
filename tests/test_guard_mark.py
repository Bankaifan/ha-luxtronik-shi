"""Signed guard marker (issue #139): trust for script-written issues, and GUARD_KEY never in a model step."""
import json
import pathlib
import re

import guard_mark
import liveness
import pytest
import trusted_issues as ti

ROOT = pathlib.Path(__file__).resolve().parent.parent
KEY = "k" * 32
BOT = "author-app[bot]"
TITLE = liveness.overdue_title("scout")


def signed(title=TITLE, body="The scheduled run failed.", key=KEY):
    return guard_mark.sign(title, body, key)


def issue(author=BOT, title=TITLE, body=None, labels=()):
    return {"number": 7, "title": title, "author": {"login": author}, "body": signed() if body is None else body,
            "labels": [{"name": n} for n in labels]}


def classify(i, key=KEY):
    return ti.classify(i, [], "Bankaifan", BOT, guard_key=key)


def test_valid_signature_by_bot_is_trusted():
    r = classify(issue())
    assert r and r["guard"] and not r["authored_by_owner"]


def test_signature_survives_github_whitespace_changes():
    assert classify(issue(body=signed().replace("\n", "\r\n") + "\n"))


@pytest.mark.parametrize("body", [
    "The scheduled run failed.",  # unsigned
    "The scheduled run failed.\n\n<!-- guard-sig: " + "0" * 64 + " -->",  # wrong signature
    "<!-- guard-sig: " + "0" * 64 + " -->\nmore text after it",  # marker not at the end
])
def test_missing_or_wrong_signature_untrusted(body):
    assert classify(issue(body=body)) is None


def test_edited_body_or_title_untrusted():
    assert classify(issue(body=signed().replace("failed", "FAILED"))) is None
    assert classify(issue(title="Overdue scheduled run: other")) is None


def test_signature_of_other_key_untrusted():
    assert classify(issue(body=signed(key="x" * 32))) is None


def test_other_author_untrusted():
    assert classify(issue(author="mallory")) is None


def test_idea_label_untrusted():
    assert classify(issue(labels=["idea"])) is None


def test_missing_secret_untrusted():
    assert classify(issue(), key="") is None
    assert guard_mark.sign(TITLE, "body", "") == "body"  # nothing is signed without a key
    assert not guard_mark.verify(TITLE, signed(key=""), "")


def test_unsigned_bot_issue_untrusted():
    assert classify(issue(body="plain")) is None


def test_liveness_creates_signed_issue():
    calls = []

    def run(*a):
        calls.append(a)
        return "[]" if a[1] == "list" else "https://github.com/o/r/issues/9\n"

    assert liveness.ensure_overdue_issue("scout", KEY, run) == "9"
    create = next(a for a in calls if a[1] == "create")
    title, body = create[3], create[create.index("--body") + 1]
    assert guard_mark.verify(title, body, KEY)


def test_liveness_without_key_is_unsigned():
    calls = []

    def run(*a):
        calls.append(a)
        return "[]" if a[1] == "list" else "https://github.com/o/r/issues/9\n"

    liveness.ensure_overdue_issue("scout", "", run)
    create = next(a for a in calls if a[1] == "create")
    assert "guard-sig" not in create[create.index("--body") + 1]


def test_signed_text_is_fixed_script_text():
    """Only the label from SCHEDULED and constants reach the signed body: no log, exception or model text."""
    for label, _ in liveness.SCHEDULED.values():
        assert liveness.overdue_body(label) == (
            f"The scheduled run of the {label} has no successful run within {liveness.OVERDUE_FACTOR} intervals. "
            "Check the workflow runs.")
    assert liveness.OVERDUE_DETAIL == "Check the workflow runs."


def test_flag_overdue_passes_no_free_text():
    import inspect
    assert "detail" not in inspect.signature(liveness.ensure_overdue_issue).parameters


# --- GUARD_KEY never reaches a model step ---------------------------------------------------------

WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def _blocks(text):
    """(header before the first step, [step blocks]); steps start with `      - ` at the job-step indent."""
    parts = re.split(r"\n(?=      - )", text)
    return parts[0], parts[1:]


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_guard_key_only_in_script_steps(path):
    text = path.read_text(encoding="utf-8")
    header, steps = _blocks(text)
    assert "GUARD_KEY" not in header, "workflow- or job-level env would reach every step"
    for step in steps:
        if "GUARD_KEY" in step:
            assert "claude-code-action" not in step
            assert "uses:" not in step, "pass the key to run: steps only"


def test_guard_key_used_where_expected():
    users = {p.name for p in WORKFLOWS if "GUARD_KEY" in p.read_text(encoding="utf-8")}
    assert users == {"orchestrator.yml", "status.yml", "setup.yml", "rule-keeper.yml", "scout.yml"}


def test_setup_requires_guard_key():
    assert "GUARD_KEY" in (ROOT / ".github/workflows/setup.yml").read_text(encoding="utf-8")


def test_codeowners_covers_guard_mark():
    assert "/tools/guard_mark.py @Bankaifan" in (ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8")


def test_trusted_output_is_json_with_guard_flag():
    assert json.loads(json.dumps(classify(issue())))["guard"] is True
