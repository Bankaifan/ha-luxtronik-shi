"""Review rounds count only findings (issue #469): refunds for approved heads, form failures, settled silent runs.
Fix rounds go on while they resolve findings (decision 0021): the progress rule of tools/review_rounds.py."""
import importlib.util
import json
import os
import pathlib
import re
import subprocess
import sys

import agent_guard as g
import pytest
import review_rounds as rr
from agent_guard import STOP

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

APPROVER = "ap[bot]"
A, B, C = "a" * 40, "b" * 40, "c" * 40


class FakePr:
    """A PR as gh shows it: labels and reviews; `pr edit` flags change the labels."""

    def __init__(self):
        self.labels, self.reviews, self.comments = set(), [], []

    def review(self, sha, state, body="", login=APPROVER):
        self.reviews.append({"commit_id": sha, "state": state, "body": body, "user": {"login": login}})

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


def review_head(pr, sha, state, body=""):
    """What agent-review does for one head: count, review, give the round back on an approval."""
    result = g.count_round(5, sha, pr)
    pr.review(sha, state, body)
    return result, g.refund_round(5, sha, APPROVER, pr)


def sha(i):
    return f"{i:07x}".ljust(40, "0")


def changes(*ids):
    return "\n".join(f"changes[{i}]: tools/x.py:{n} reason" for n, i in enumerate(ids, 1)) + "\nreviewers: code-reviewer"


def test_approved_heads_cost_no_round_even_after_rebases():
    # recorded shape of #456 / #464: the head is approved, then rebased (new SHA, approval dismissed), approved again
    pr = FakePr()
    assert review_head(pr, A, "APPROVED") == ("counted", "refunded")
    assert pr.rounds() == [] and not any(n.startswith("round:") for n in pr.labels)
    assert review_head(pr, B, "APPROVED") == ("counted", "refunded")
    assert review_head(pr, C, "APPROVED") == ("counted", "refunded")
    assert pr.rounds() == [] and "parked" not in pr.labels


def test_reviews_without_finding_ids_still_stop_after_two_fix_rounds():
    pr = FakePr()
    assert review_head(pr, A, "CHANGES_REQUESTED") == ("counted", "kept")
    assert rr.verdict(5, APPROVER, pr) == "fix"
    assert review_head(pr, B, "CHANGES_REQUESTED") == ("counted", "kept")
    assert pr.rounds() == ["review:1", "review:2"] and rr.verdict(5, APPROVER, pr) == "fix"
    assert g.count_round(5, C, pr) == "counted"  # the third review of the same (unnamed) finding: the old limit
    pr.review(C, "CHANGES_REQUESTED")
    assert rr.verdict(5, APPROVER, pr) == "stuck"


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
    block = text[text.index('guard form-failure "$RUN_ID"'):text.index('tools/review_rounds.py red "$pr"')]
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


# --- progress rule (decision 0021) -------------------------------------------------------------

def rev(commit, state="CHANGES_REQUESTED", body="", login=APPROVER):
    return {"commit_id": commit, "state": state, "body": body, "user": {"login": login}}


def test_finding_ids_are_the_ids_of_the_changes_points():
    body = "changes[F1]: a.py:3 x\nchanges[F12]: b.py:9 y\ncarry: note\nchanges[sec.1-a]: c.py:1 z\nchanges[F1]: a.py:7 again"
    assert rr.finding_ids(body) == {"F1", "F12", "sec.1-a"}
    for none in ("", None, "changes: a.py:3 no id", "changes[]: empty", "changes[-x]: bad start", "scope[F1]: other class"):
        assert rr.finding_ids(none) == set()


def test_security_prefix_is_the_one_post_verdict_writes():
    spec = importlib.util.spec_from_file_location("post_verdict", ROOT / "tools" / "ci" / "post_verdict.py")
    pv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pv)
    assert rr.SECURITY_PREFIX == pv.REQUEST_PREFIX


def test_history_takes_the_latest_code_review_of_each_head():
    reviews = [rev(A, body=changes("F1", "F2")), rev(B, body=changes("F2")), rev(A, body=changes("F3")),
               rev(B, "APPROVED", "fine"), rev(C, body="please fix the parser"), rev(C, "COMMENTED", changes("F9")),
               rev(C, "DISMISSED", changes("F8"))]
    assert rr.history(reviews, APPROVER) == [{"F3"}, set(), {"?"}]  # heads in the order they were first reviewed
    assert rr.history([], APPROVER) == []


def test_history_adds_security_while_its_request_stands_on_the_head():
    sec = rr.SECURITY_PREFIX + " at aaaaaaa: see the `security-review: changes` comment."
    assert rr.history([rev(A, "APPROVED"), rev(A, body=sec)], APPROVER) == [{"security"}]
    assert rr.history([rev(A, body=sec), rev(A, body=changes("F1"))], APPROVER) == [{"F1", "security"}]
    assert rr.history([rev(A, body=changes("F1")), rev(A, "DISMISSED", sec)], APPROVER) == [{"F1"}]  # dismissed on approve
    assert rr.history([rev(A, body=sec), rev(B, "APPROVED")], APPROVER) == [{"security"}, set()]


def test_history_ignores_reviews_of_other_users():
    reviews = [rev(A, body=changes("F1"), login="someone"), rev(B, body=changes("F1")),
               rev(B, "APPROVED", login="owner"), rev(C, body=changes("F2"), login="app/ap")]
    assert rr.history(reviews, APPROVER) == [{"F1"}, {"F2"}]  # login forms x, app/x, x[bot] are the same app


@pytest.mark.parametrize("hist, expected", [
    ([{"F1"}, {"F1"}, {"F1"}], True),
    ([{"F1", "F2"}, {"F2", "F3"}, {"F2", "F4"}], True),
    ([set(), {"F1"}, {"F1", "F2"}, {"F1"}], True),
    ([{"?"}, {"?"}, {"?"}], True),  # reviews without ids: the old limit, never an endless loop
    ([{"security"}, {"F1", "security"}, {"security"}], True),
    ([{"F1"}, {"F2"}, {"F3"}], False),
    ([{"F1"}, {"F1", "F2"}, {"F2"}], False),  # each finding survived one fix round only
    ([{"F1"}, {"F1"}, set(), {"F1"}], False),  # an approval in between resets
    ([{"F1"}, {"F1"}, {"F1"}, {"F2"}], False),  # only the last three heads count
    ([{"F1"}, {"F1"}], False),
    ([{"F1"}], False),
    ([], False),
])
def test_stuck_is_one_finding_on_three_reviewed_heads_in_a_row(hist, expected):
    assert rr.stuck(hist) is expected and rr.STUCK_AFTER == 2


def test_verdict_is_none_before_a_round_and_fix_while_findings_get_resolved():
    pr = FakePr()
    assert rr.verdict(5, APPROVER, pr) == "none"
    assert review_head(pr, A, "APPROVED") == ("counted", "refunded")
    assert rr.verdict(5, APPROVER, pr) == "none"  # the round of an approved head was given back
    review_head(pr, B, "CHANGES_REQUESTED", changes("F1"))
    assert rr.verdict(5, APPROVER, pr) == "fix"
    review_head(pr, C, "CHANGES_REQUESTED", changes("F1", "F2"))
    assert rr.verdict(5, APPROVER, pr) == "fix"  # F1 has one more fix round
    review_head(pr, sha(4), "CHANGES_REQUESTED", changes("F2"))
    assert rr.verdict(5, APPROVER, pr) == "fix"  # F1 resolved, F2 open for one round only
    assert pr.rounds() == ["review:1", "review:2", "review:3"]


def test_verdict_is_stuck_when_a_finding_survives_two_fix_rounds_in_a_row():
    pr = FakePr()
    for i, ids in enumerate([("F1",), ("F1", "F2"), ("F3", "F1")], 1):
        review_head(pr, sha(i), "CHANGES_REQUESTED", changes(*ids))
    assert rr.verdict(5, APPROVER, pr) == "stuck"
    assert STOP not in pr.labels  # the verdict only reads; agent-fix sets the label


def test_an_approved_head_in_between_gives_the_finding_two_new_rounds():
    pr = FakePr()
    review_head(pr, sha(1), "CHANGES_REQUESTED", changes("F1"))
    review_head(pr, sha(2), "CHANGES_REQUESTED", changes("F1"))
    review_head(pr, sha(3), "APPROVED", "ok")
    review_head(pr, sha(4), "CHANGES_REQUESTED", changes("F1"))
    assert rr.verdict(5, APPROVER, pr) == "fix"


def test_verdict_is_limit_after_review_stop_or_at_the_brake():
    pr = FakePr()
    review_head(pr, A, "CHANGES_REQUESTED", changes("F1"))
    pr.labels.add(STOP)
    assert rr.verdict(5, APPROVER, pr) == "limit"
    assert rr.verdict(5, APPROVER, lambda *a: "review:stop\n") == "limit"  # even without a counted round
    assert rr.verdict(5, APPROVER, lambda *a: "review:8\n") == "limit"  # no look at the reviews needed


def test_a_new_finding_every_round_runs_to_the_brake_and_stops_there():
    pr, verdicts = FakePr(), []
    for i in range(1, g.MAX_ROUNDS + 1):
        assert review_head(pr, sha(i), "CHANGES_REQUESTED", changes(f"F{i}")) == ("counted", "kept")
        verdicts.append(rr.verdict(5, APPROVER, pr))
    assert verdicts == ["fix"] * 7 + ["limit"]  # 8 reviews, 7 fix rounds
    assert g.count_round(5, sha(9), pr) == "limit" and pr.rounds()[-1] == "review:8" and len(pr.rounds()) == 8


def test_red_heads_get_two_fixes_in_a_row_and_the_third_is_stuck():
    pr = FakePr()
    assert rr.red(5, sha(1), pr) == "fix" and pr.labels == {"review:1", "ci-red:1", "red:0000001"}
    assert rr.red(5, sha(2), pr) == "fix"
    assert pr.labels == {"review:1", "review:2", "ci-red:1", "ci-red:2", "red:0000002"}  # one head marker at a time
    before = set(pr.labels)
    assert rr.red(5, sha(3), pr) == "stuck" and pr.labels == before


def test_a_second_red_run_on_the_same_head_counts_nothing():
    pr = FakePr()
    assert rr.red(5, sha(1), pr) == "fix"
    before = set(pr.labels)
    assert rr.red(5, sha(1), pr) == "fix" and rr.red(5, sha(1), pr) == "fix" and pr.labels == before
    assert rr.red(5, sha(2), pr) == "fix" and rr.red(5, sha(2), pr) == "fix"  # also on the second head of a streak
    assert pr.rounds() == ["review:1", "review:2"] and rr.red_streak(pr.labels) == 2
    assert rr.red(5, sha(3), pr) == "stuck"


def test_a_green_head_ends_the_red_streak():
    pr = FakePr()
    rr.red(5, sha(1), pr)
    rr.red(5, sha(2), pr)
    pr.labels.add("round:abc1234")
    assert rr.green(5, pr) == ["ci-red:1", "ci-red:2", "red:0000002"]
    assert pr.labels == {"review:1", "review:2", "round:abc1234"}  # the rounds stay counted
    assert rr.red(5, sha(3), pr) == "fix" and pr.labels >= {"review:3", "ci-red:1"} and "ci-red:2" not in pr.labels
    calls = []
    assert rr.green(5, lambda *a: calls.append(a) or "review:1\nparked\n") == []
    assert [c[:2] for c in calls] == [("pr", "view")]  # nothing to remove: no edit


def test_a_head_that_went_green_and_red_again_is_a_new_round():
    pr = FakePr()
    rr.red(5, sha(1), pr)
    rr.green(5, pr)
    assert rr.red(5, sha(1), pr) == "fix" and pr.rounds() == ["review:1", "review:2"]


def test_red_stops_one_round_before_the_brake_so_the_last_round_is_a_review():
    pr = FakePr()
    pr.labels = {f"review:{i}" for i in range(1, g.MAX_ROUNDS - 1)}  # 6 rounds
    assert rr.red(5, sha(1), pr) == "fix" and g.round_no(pr.labels) == g.MAX_ROUNDS - 1
    rr.green(5, pr)
    before = set(pr.labels)
    assert rr.red(5, sha(2), pr) == "limit" and pr.labels == before  # round 8 would be a red head
    assert g.count_round(5, A, pr) == "counted" and g.round_no(pr.labels) == g.MAX_ROUNDS  # a review may still take it


def test_red_changes_nothing_after_review_stop():
    pr = FakePr()
    pr.labels = {"review:1", STOP, "red:0000001"}
    for head in (sha(1), sha(2)):  # the stop label wins over the marker of a counted head
        assert rr.red(5, head, pr) == "limit" and pr.labels == {"review:1", STOP, "red:0000001"}


def test_red_and_reviewed_heads_share_the_round_counter():
    pr = FakePr()
    review_head(pr, A, "CHANGES_REQUESTED", changes("F1"))
    assert rr.red(5, B, pr) == "fix" and pr.rounds() == ["review:1", "review:2"]
    assert rr.verdict(5, APPROVER, pr) == "fix"


def test_after_an_un_park_the_old_reviews_are_not_this_attempts_history():
    pr = FakePr()
    for i in (1, 2, 3):
        review_head(pr, sha(i), "CHANGES_REQUESTED", changes("F1"))
    assert rr.verdict(5, APPROVER, pr) == "stuck"
    pr.labels.clear()  # un-park: the counters are cleared, the reviews stay
    assert rr.verdict(5, APPROVER, pr) == "none"
    review_head(pr, sha(4), "CHANGES_REQUESTED", changes("F1"))
    assert rr.verdict(5, APPROVER, pr) == "fix"
    review_head(pr, sha(5), "CHANGES_REQUESTED", changes("F1"))
    assert rr.verdict(5, APPROVER, pr) == "fix"
    review_head(pr, sha(6), "CHANGES_REQUESTED", changes("F1"))
    assert rr.verdict(5, APPROVER, pr) == "stuck"  # three heads of the new attempt


def cli(tmp_path, *args, fail=False):
    """Run the CLI against a fake `gh` that logs its arguments and prints LABELS for `pr view`."""
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\necho "$*" >> "$GH_LOG"\n[ -n "$GH_FAIL" ] && exit 1\n'
                  '[ "$1 $2" = "pr view" ] && printf "%s" "$LABELS"\nexit 0\n', encoding="utf-8")
    gh.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}", "GH_LOG": str(tmp_path / "log"),
           "GH_FAIL": "1" if fail else "", "LABELS": "review:1\nci-red:1\n", "GH_REPO": "o/r", "APPROVER_BOT": APPROVER}
    done = subprocess.run([sys.executable, str(ROOT / "tools" / "review_rounds.py"), *args],
                          capture_output=True, text=True, env=env, check=False)
    log = tmp_path / "log"
    return done, log.read_text(encoding="utf-8") if log.exists() else ""


def test_cli_stop_sets_the_label_and_green_clears_the_streak(tmp_path):
    done, log = cli(tmp_path, "stop", "5")
    assert done.returncode == 0 and "pr edit 5 --add-label review:stop" in log
    done, log = cli(tmp_path, "green", "5")
    assert done.returncode == 0 and done.stdout.strip() == "ci-red:1" and "pr edit 5 --remove-label ci-red:1" in log
    done, log = cli(tmp_path, "red", "5", "c" * 40)
    assert done.stdout.strip() == "fix"
    assert "pr edit 5 --add-label review:2 --add-label ci-red:2 --add-label red:ccccccc" in log


@pytest.mark.parametrize("cmd", [["verdict", "5"], ["red", "5", A], ["green", "5"], ["stop", "5"]])
def test_cli_gives_no_fallback_verdict_when_gh_fails(tmp_path, cmd):
    done, _ = cli(tmp_path, *cmd, fail=True)
    assert done.returncode != 0 and done.stdout.strip() == ""


def test_cli_refuses_an_unknown_command_or_pr(tmp_path):
    for args in (["park", "5"], ["verdict", "x"], ["verdict"], ["red", "5"], ["red", "5", "abc1234"], ["green", "5", A]):
        done, log = cli(tmp_path, *args)
        assert done.returncode != 0 and done.stdout.strip() == "" and log == ""


def test_agent_fix_sets_review_stop_before_the_hand_over():
    text = (ROOT / ".github/workflows/agent-fix.yml").read_text(encoding="utf-8")
    body = text[text.index("limit() {"):text.index("\n          }\n", text.index("limit() {"))]
    assert body.index('python3 tools/review_rounds.py stop "$pr"') < body.index('python3 tools/restart.py limit "$pr"')


def test_agent_fix_lets_the_script_decide_and_fails_on_its_error():
    text = (ROOT / ".github/workflows/agent-fix.yml").read_text(encoding="utf-8")
    step = text[text.index("limit() {"):text.index("\n  fix:\n")]
    # a plain assignment under `set -e`: a failing script fails the step, no default branch; red gets the run's head
    for cmd in ('red "$pr" "$RUN_SHA"', 'verdict "$pr"'):
        assert f'\n            verdict=$(python3 tools/review_rounds.py {cmd})\n' in step
    assert "RUN_SHA: ${{ github.event.workflow_run.head_sha }}" in text
    assert "set -euo pipefail" in text[text.index("- id: round"):text.index("limit() {")]
    assert not re.search(r"review:\d", step)  # no round label is decided in the shell any more


@pytest.mark.parametrize("stop_rc, restart_rc, code, parked", [(0, 0, 0, False), (1, 0, 1, False), (1, 1, 1, True), (0, 1, 0, True)])
def test_agent_fix_hands_over_even_when_review_stop_cannot_be_set(tmp_path, stop_rc, restart_rc, code, parked):
    """Runs the limit() function of the workflow with stubbed commands: the hand-over and fix=false always happen."""
    text = (ROOT / ".github/workflows/agent-fix.yml").read_text(encoding="utf-8")
    start = text.index("          limit() {")
    func = text[start:text.index("\n          }\n", start) + len("\n          }\n")]
    script = ("set -euo pipefail\n"
              'python3() { echo "$2 $3" >> "$LOG"; case "$2" in stop) return "$STOP_RC" ;; limit) return "$RESTART_RC" ;; esac; }\n'
              'guard() { echo "guard $1" >> "$LOG"; }\n' + func + "pr=5\nlimit\n")
    env = {**os.environ, "LOG": str(tmp_path / "log"), "GITHUB_OUTPUT": str(tmp_path / "out"),
           "STOP_RC": str(stop_rc), "RESTART_RC": str(restart_rc)}
    done = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True, check=False)
    assert done.returncode == code, done.stderr
    log = (tmp_path / "log").read_text(encoding="utf-8").splitlines()
    assert log[:2] == ["stop 5", "limit 5"] and (log[2:] == ["guard park"]) is parked
    assert (tmp_path / "out").read_text(encoding="utf-8") == "fix=false\n"
