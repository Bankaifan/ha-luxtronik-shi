"""Pipeline canary (issue #423): create and check with a fake gh, the 6 h limit, stage names, the exemptions."""
import datetime
import json

import canary
import guard_mark
import pytest
import trusted_issues
from check.check_version_bump import errors
from template_sync import is_managed

KEY = "k" * 32
NOW = datetime.datetime(2026, 11, 12, 12, 0, tzinfo=datetime.UTC)


def ago(minutes):
    return (NOW - datetime.timedelta(minutes=minutes)).isoformat()


class FakeGh:
    def __init__(self, issues=(), prs=(), events=(), runs=()):
        self.issues, self.prs, self.events, self.runs = list(issues), list(prs), list(events), list(runs)
        self.created = []

    def __call__(self, *a):
        if a[:2] == ("issue", "list"):
            return json.dumps(self.issues)
        if a[:2] == ("issue", "create"):
            self.created.append(a)
            return "https://github.com/o/r/issues/99\n"
        if a[:2] == ("pr", "list"):
            return json.dumps(self.prs)
        if a[0] == "api":
            return json.dumps([self.events])
        if a[:2] == ("run", "list"):
            return json.dumps(self.runs)
        raise AssertionError(a)


@pytest.fixture(autouse=True)
def author_bot(monkeypatch):
    monkeypatch.setenv("AUTHOR_BOT", "bot")


def canary_issue(age_min, state="OPEN", number=50, author="bot[bot]", signed=True):
    title = canary.PREFIX + "x"
    body = guard_mark.sign(title, "slip", KEY) if signed else "slip"
    return {"number": number, "title": title, "state": state, "createdAt": ago(age_min),
            "author": {"login": author}, "body": body, "labels": []}


def label_event(name, minutes_ago):
    return {"event": "labeled", "label": {"name": name}, "created_at": ago(minutes_ago)}


def pr(merged=False, reviews=(), created=40):
    return {"number": 7, "createdAt": ago(created), "mergedAt": ago(1) if merged else None,
            "headRefName": "agent/50-canary", "labels": [], "reviews": list(reviews)}


def green(minutes_ago=30):
    return {"workflowName": "validate", "conclusion": "success", "updatedAt": ago(minutes_ago),
            "createdAt": ago(minutes_ago + 2)}


def review(state, minutes_ago):
    return {"state": state, "submittedAt": ago(minutes_ago)}


def failing(gh):
    """Created issues whose title is the failure title."""
    return [c for c in gh.created if c[3] == canary.FAIL_TITLE]


# --- create -----------------------------------------------------------------------------------------

def test_create_opens_signed_haiku_issue():
    gh = FakeGh()
    assert canary.create(NOW, KEY, gh) == "99"
    c = gh.created[0]
    title, body = c[3], c[c.index("--body") + 1]
    assert title == "Canary: 2026-11-12T12:00Z"
    assert c[c.index("--label") + 1] == "model:haiku"
    assert "docs/canary.md" in body and guard_mark.verify(title, body, KEY)


def test_create_respects_the_6h_limit():
    gh = FakeGh(issues=[canary_issue(5 * 60 + 59)])
    assert canary.create(NOW, KEY, gh) is None and not gh.created
    gh = FakeGh(issues=[canary_issue(6 * 60 + 1, state="CLOSED")])
    assert canary.create(NOW, KEY, gh) == "99"


def test_create_ignores_other_issues_in_the_search():
    gh = FakeGh(issues=[{"number": 3, "title": "Something with Canary: in it", "state": "OPEN", "createdAt": ago(1)}])
    assert canary.create(NOW, KEY, gh) == "99"


def test_foreign_canary_issue_does_not_block_create():
    for forged in (canary_issue(1, author="stranger"), canary_issue(1, signed=False)):
        gh = FakeGh(issues=[forged])
        assert canary.create(NOW, KEY, gh) == "99"


def test_foreign_canary_issue_is_not_judged_by_check():
    real = canary_issue(50, state="CLOSED", number=50)
    gh = FakeGh(issues=[real, canary_issue(1, number=77, author="stranger")], prs=[pr(merged=True)])
    assert canary.check(NOW, "o/r", KEY, gh) == ("pass", None)
    assert not gh.created
    assert canary.check(NOW, "o/r", KEY, FakeGh(issues=[canary_issue(50, signed=False)])) == ("none", None)


def test_dry_run_writes_nothing():
    gh = FakeGh()
    wrapped = canary.dry_run(gh)
    wrapped("issue", "create", "--title", "t")
    assert not gh.created
    assert json.loads(wrapped("issue", "list")) == []


# --- check ------------------------------------------------------------------------------------------

def test_check_waits_before_45_min_and_ignores_old_canaries():
    assert canary.check(NOW, "o/r", KEY, FakeGh(issues=[canary_issue(44)])) == ("wait", None)
    assert canary.check(NOW, "o/r", KEY, FakeGh(issues=[canary_issue(121)])) == ("none", None)
    assert canary.check(NOW, "o/r", KEY, FakeGh()) == ("none", None)


def test_check_pass_when_pr_merged_and_issue_closed():
    gh = FakeGh(issues=[canary_issue(50, state="CLOSED")], prs=[pr(merged=True)])
    assert canary.check(NOW, "o/r", KEY, gh) == ("pass", None)
    assert not gh.created


def check_stage(prs=(), events=(), runs=(), state="OPEN", issues_extra=()):
    gh = FakeGh(issues=[canary_issue(50, state=state), *issues_extra], prs=prs, events=events, runs=runs)
    status, stage = canary.check(NOW, "o/r", KEY, gh)
    assert status == "fail"
    (issue,) = failing(gh)
    body = issue[issue.index("--body") + 1]
    assert guard_mark.verify(canary.FAIL_TITLE, body, KEY) and f"stage: {stage}." in body and "#50" in body
    assert issue[issue.index("--label") + 1] == "prio:1"
    return stage


def test_stops_at_dispatch_without_dev_label():
    assert check_stage() == "dispatch"


def test_stops_at_develop_without_pr():
    assert check_stage(events=[label_event("agent:dev", 45)]) == "develop"


def test_stops_at_ci_without_green_run():
    assert check_stage(prs=[pr()], events=[label_event("agent:dev", 45)]) == "ci"


def test_stops_at_review_without_review():
    assert check_stage(prs=[pr()], events=[label_event("agent:dev", 45)], runs=[green()]) == "review"


def test_stops_at_fix_without_approval():
    p = pr(reviews=[review("CHANGES_REQUESTED", 20)])
    assert check_stage(prs=[p], events=[label_event("agent:dev", 45)], runs=[green()]) == "fix"


def test_stops_at_train_when_approved_not_merged():
    p = pr(reviews=[review("APPROVED", 10)])
    assert check_stage(prs=[p], events=[label_event("agent:dev", 45)], runs=[green()]) == "train"


def test_stops_at_close_when_merged_but_issue_open():
    assert check_stage(prs=[pr(merged=True)], events=[label_event("agent:dev", 45)]) == "close"


def test_failure_issue_is_not_duplicated():
    gh = FakeGh(issues=[canary_issue(50), {"number": 60, "title": canary.FAIL_TITLE, "state": "OPEN",
                                           "createdAt": ago(1)}])
    assert canary.check(NOW, "o/r", KEY, gh) == ("fail", "dispatch") and not gh.created


def test_stage_names_follow_flow_and_texts_are_fixed():
    assert set(canary.STAGE_NAMES) == {"dispatch", "develop", "ci", "review", "fix", "train", "close"}
    assert canary.fail_body(5, "ci") == ("The pipeline canary issue #5 did not finish within 45 min. "
                                         "It stopped at stage: ci. Check that stage and the workflow runs.")


# --- trust and exemptions -----------------------------------------------------------------------------

def test_signed_canary_issue_is_trusted_but_unsigned_is_not():
    title = "Canary: 2026-11-12T12:00Z"
    body = guard_mark.sign(title, canary.slip("2026-11-12T12:00Z"), KEY)
    i = {"number": 1, "title": title, "author": {"login": "bot[bot]"}, "body": body, "labels": []}
    assert trusted_issues.classify(i, [], "Bankaifan", "bot[bot]", guard_key=KEY)["guard"]
    assert trusted_issues.classify({**i, "body": canary.slip("x")}, [], "Bankaifan", "bot[bot]", guard_key=KEY) is None


def test_canary_file_is_not_managed_and_needs_no_fragment():
    managed = [".github/workflows/", "tools/", "AGENTS.md"]
    assert not is_managed(canary.FILE, managed)
    assert errors([canary.FILE], managed, read=lambda p: None) == []
