"""Review rounds count only findings (issue #469): refunds for approved heads, form failures, settled silent runs."""
import json
import re
import subprocess

import agent_guard as g
import pytest

APPROVER = "ap[bot]"
A, B, C = "a" * 40, "b" * 40, "c" * 40


class FakePr:
    """A PR as gh shows it: labels and reviews; `pr edit` flags change the labels."""

    def __init__(self):
        self.labels, self.reviews, self.comments = set(), [], []

    def review(self, sha, state):
        self.reviews.append({"commit_id": sha, "state": state, "user": {"login": APPROVER}})

    def __call__(self, *a):
        if a[:2] == ("pr", "view") and "--jq" in a:
            return "\n".join(sorted(self.labels))
        if a[:2] == ("pr", "view"):
            return json.dumps({"commits": []})
        if a[0] == "api" and a[-1].endswith("/reviews"):
            return json.dumps([self.reviews])
        if a[0] == "api" and a[-1].endswith("/comments"):
            return json.dumps([self.comments])
        if a[0] == "api":
            return "[[]]"
        if a[:2] == ("pr", "edit"):
            for flag, name in zip(a[3::2], a[4::2], strict=False):
                (self.labels.add if flag == "--add-label" else self.labels.discard)(name)
        return ""

    def rounds(self):
        return sorted(n for n in self.labels if n.startswith("review:"))


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")
    monkeypatch.setenv("APPROVER_BOT", APPROVER)


def review_head(pr, sha, state):
    """What agent-review does for one head: count, review, give the round back on an approval."""
    result = g.count_round(5, sha, pr)
    pr.review(sha, state)
    return result, g.refund_round(5, sha, APPROVER, pr)


def test_approved_heads_cost_no_round_even_after_rebases():
    # recorded shape of #456 / #464: the head is approved, then rebased (new SHA, approval dismissed), approved again
    pr = FakePr()
    assert review_head(pr, A, "APPROVED") == ("counted", "refunded")
    assert pr.rounds() == [] and not any(n.startswith("round:") for n in pr.labels)
    assert review_head(pr, B, "APPROVED") == ("counted", "refunded")
    assert review_head(pr, C, "APPROVED") == ("counted", "refunded")
    assert pr.rounds() == [] and "needs-human" not in pr.labels


def test_two_real_findings_still_stop_after_two_rounds():
    pr = FakePr()
    assert review_head(pr, A, "CHANGES_REQUESTED") == ("counted", "kept")
    assert review_head(pr, B, "CHANGES_REQUESTED") == ("counted", "kept")
    assert pr.rounds() == ["review:1", "review:2"]
    assert g.count_round(5, C, pr) == "counted"  # the third review sets review:3: agent-fix then applies the limit
    assert "review:3" in pr.rounds()
    assert g.count_round(5, "d" * 40, pr) == "limit"


def test_a_finding_then_an_approval_keeps_the_first_round_only():
    pr = FakePr()
    review_head(pr, A, "CHANGES_REQUESTED")
    assert review_head(pr, B, "APPROVED") == ("counted", "refunded")
    assert pr.rounds() == ["review:1"]


def test_refund_needs_a_counted_head_and_an_approval_of_it():
    pr = FakePr()
    assert g.refund_round(5, A, APPROVER, pr) == "none"
    g.count_round(5, A, pr)
    assert g.refund_round(5, A, APPROVER, pr) == "kept"  # no review yet
    pr.reviews.append({"commit_id": A, "state": "APPROVED", "user": {"login": "someone-else"}})
    assert g.refund_round(5, A, APPROVER, pr) == "kept"  # only the approver app counts
    assert pr.rounds() == ["review:1"]


def test_security_pr_keeps_its_round_until_the_security_reviewer_approves_the_head():
    pr = FakePr()
    pr.labels.add("risk:security")
    assert review_head(pr, A, "APPROVED") == ("counted", "kept")  # code approval alone: the security verdict may still say changes
    assert pr.rounds() == ["review:1"]
    pr.comments.append({"user": {"login": APPROVER}, "body": f"security-review: changes {A}"})
    assert g.refund_round(5, A, APPROVER, pr) == "kept"
    pr.comments.append({"user": {"login": APPROVER}, "body": f"security-review: approve {A}"})
    assert g.refund_round(5, A, APPROVER, pr) == "refunded"
    assert pr.rounds() == []


@pytest.mark.parametrize("log", [
    "validate\tChecks\t2026 check_pr_form: PR body has 7 lines (max 5)",
    "check_version_bump: VERSION not bumped",
    "make: *** [Makefile:15: check]\ncheck_version: CHANGELOG.md has no '## [1.2]' section",
])
def test_form_failures_are_not_a_round(log):
    assert g.form_failure(log)


@pytest.mark.parametrize("log", [
    "", "check_pr_form: ok", "check_version_bump: skipped (no PR_BASE_REF)", "check_version: ok (1.2)",
    "FAILED tests/test_x.py::test_y - assert 1 == 2", "tools/x.py:3:1: F401 unused import",
])
def test_other_failures_are_a_round(log):
    assert not g.form_failure(log)


def test_unreadable_log_counts_as_a_round():
    def broken(*a):
        raise subprocess.CalledProcessError(1, "gh")

    assert not g.is_form_failure(77, broken)
    assert g.is_form_failure(77, lambda *a: "check_pr_form: title is not ASCII")


def settled_view(**kw):
    view = {"headRefOid": "abc", "labels": [], "reviewDecision": "APPROVED",
            "statusCheckRollup": [{"name": "validate", "conclusion": "SUCCESS"}]}
    view.update(kw)
    return view


def test_settled_needs_green_and_approved_at_head():
    assert g.settled(settled_view(), [], APPROVER)
    assert not g.settled(settled_view(reviewDecision="REVIEW_REQUIRED"), [], APPROVER)
    assert not g.settled(settled_view(statusCheckRollup=[]), [], APPROVER)
    assert not g.settled(settled_view(statusCheckRollup=[{"name": "validate", "conclusion": "FAILURE"}]), [], APPROVER)
    sec = settled_view(labels=[{"name": "risk:security"}])
    assert not g.settled(sec, [], APPROVER)  # security approve missing


def test_agent_fix_workflow_skips_rounds_for_form_failures():
    import pathlib
    text = (pathlib.Path(__file__).parent.parent.parent / ".github/workflows/agent-fix.yml").read_text(encoding="utf-8")
    block = text[text.index('guard form-failure "$RUN_ID"'):text.index('guard label pr "$pr" review:1')]
    start = re.search(r"\n\s*\*\)\n", block).end()  # the bare `*)` branch: no formfix label yet
    first = block[start:block.index(";;", start)]
    assert 'guard label pr "$pr" formfix' in first and 'echo "fix=true"' in first  # first form red: fix runs
    assert "review:" not in first  # and no round is counted
    assert "*,formfix,*)" in block and 'echo "fix=false"' not in block  # second one falls through to a round


def test_agent_fix_workflow_conflict_dispatch_starts_a_fix_without_rounds():
    import pathlib
    text = (pathlib.Path(__file__).parent.parent.parent / ".github/workflows/agent-fix.yml").read_text(encoding="utf-8")
    start = text.index('elif [ "$EVENT" = workflow_dispatch ]; then\n            echo "fix=true"')
    branch = text[start:text.index("else", start + 20)]
    assert 'echo "fix=true"' in branch and "review:" not in branch and "guard label" not in branch
