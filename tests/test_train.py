import json
import subprocess

import train

ENV = {"GH_REPO": "o/r", "APPROVER_BOT": "app/approver", "OWNER": "Bankaifan"}


def pr(n, *, branch=None, merge="CLEAN", labels=(), files=("tools/x.py",), auto=True, checks=(), cross=False):
    return {
        "number": n, "title": f"T{n}", "url": f"u/{n}", "headRefName": branch or f"agent/{n}-x",
        "headRefOid": f"sha{n}", "labels": [{"name": x} for x in labels], "mergeStateStatus": merge,
        "statusCheckRollup": list(checks), "isCrossRepository": cross,
        "files": [{"path": f} for f in files],
        "autoMergeRequest": {"enabledBy": {"login": "Bankaifan"}} if auto else None,
    }


def review(sha, state="APPROVED", login="app/approver"):
    return {"commit_id": sha, "state": state, "user": {"login": login}, "body": ""}


def approved(*prs):
    return {p["number"]: [review(p["headRefOid"])] for p in prs}


RUNNING = [{"status": "IN_PROGRESS", "conclusion": ""}]


class Gh:
    """Fake gh: answers the calls train makes; `fail` is an argument prefix that raises CalledProcessError."""

    def __init__(self, prs, reviews=None, fix_runs=(), fail=None):
        self.prs, self.reviews, self.fix_runs, self.fail = prs, reviews or {}, list(fix_runs), fail
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        if self.fail and tuple(args[:len(self.fail)]) == self.fail:
            raise subprocess.CalledProcessError(1, ["gh", *args], stderr="HTTP 500")
        if args[:2] == ("pr", "list"):
            return json.dumps(self.prs)
        if args[:2] == ("run", "list"):
            return json.dumps(self.fix_runs)
        if args[0] == "api" and "--slurp" in args:
            number = int(args[-1].split("/pulls/")[1].split("/")[0])
            return json.dumps([self.reviews.get(number, [])])
        return ""

    def mutations(self):
        return [c for c in self.calls if c[:2] in (("api", "-X"), ("workflow", "run"), ("pr", "edit"))]


def test_design_pr_is_only_docs_design_files():
    assert train.is_design_pr(pr(1, files=("docs/design/0003-x.md",)))
    assert not train.is_design_pr(pr(1, files=("docs/design/0003-x.md", "tools/x.py")))
    assert not train.is_design_pr(pr(1, files=()))


def test_candidates_need_approval_on_current_head_from_approver():
    prs = [pr(1), pr(2), pr(3, branch="dependabot/x"), pr(4, labels=["needs-human"]),
           pr(5, files=("docs/design/0009-x.md",)), pr(6, cross=True), pr(7), pr(8)]
    reviews = {
        1: [review("sha1")],
        2: [review("sha2", state="CHANGES_REQUESTED")],
        3: [review("sha3")],
        4: [review("sha4")],
        5: [review("sha5")],
        6: [review("sha6")],
        7: [review("old")],                       # approval of an older head
        8: [review("sha8", login="someone-else")],  # not the approver app
    }
    cands = train.candidates(prs, lambda n: reviews.get(n, []), "app/approver")
    assert [p["number"] for p in cands] == [1]


def test_dismissed_or_changes_requested_review_does_not_count():
    p = pr(2)
    assert not train.approved_on_head(p, [review("sha2", state="DISMISSED")], "app/approver")
    assert not train.approved_on_head(p, [review("sha2", state="CHANGES_REQUESTED")], "app/approver")
    assert train.approved_on_head(p, [review("sha2", state="COMMENTED"), review("sha2")], "app/approver") is True


def test_candidates_are_oldest_first():
    prs = [pr(9), pr(3)]
    cands = train.candidates(prs, lambda n: [review(f"sha{n}")], "app/approver")
    assert [p["number"] for p in cands] == [3, 9]


def test_in_flight_states():
    assert train.in_flight(pr(1, merge="CLEAN"))
    assert train.in_flight(pr(1, merge="UNSTABLE"))
    assert train.in_flight(pr(1, merge="HAS_HOOKS"))
    assert train.in_flight(pr(1, merge="BLOCKED", checks=RUNNING))
    assert not train.in_flight(pr(1, merge="BLOCKED"))
    assert not train.in_flight(pr(1, merge="BEHIND"))
    assert not train.in_flight(pr(1, merge="DIRTY"))


def test_clean_candidate_blocks_rebase_of_others():
    prs = [pr(1, merge="CLEAN"), pr(2, merge="BEHIND")]
    run = Gh(prs, approved(*prs))
    assert train.run_train(ENV, run) == 0
    assert run.mutations() == []


def test_oldest_behind_with_auto_merge_is_rebased_only():
    prs = [pr(4, merge="BEHIND"), pr(2, merge="BEHIND"), pr(3, merge="BEHIND", auto=False)]
    run = Gh(prs, approved(*prs))
    assert train.run_train(ENV, run) == 0
    updates = [c for c in run.calls if c[:2] == ("api", "-X")]
    assert updates == [("api", "-X", "PUT", "repos/o/r/pulls/2/update-branch", "-f", "update_method=rebase")]


def test_behind_without_auto_merge_is_left_alone():
    prs = [pr(3, merge="BEHIND", auto=False)]
    run = Gh(prs, approved(*prs))
    assert train.run_train(ENV, run) == 0
    assert run.mutations() == []


def test_dirty_candidate_dispatches_fix_for_oldest_only():
    prs = [pr(6, merge="DIRTY"), pr(5, merge="DIRTY")]
    run = Gh(prs, approved(*prs))
    assert train.run_train(ENV, run) == 0
    assert [c for c in run.mutations() if c[:2] == ("workflow", "run")] == [
        ("workflow", "run", "agent-fix.yml", "-f", "pr=5")]


def test_unapproved_dirty_pr_is_not_probed():
    prs = [pr(5, merge="DIRTY")]
    run = Gh(prs, reviews={})
    assert train.run_train(ENV, run) == 0
    assert run.mutations() == []


def test_running_fix_job_blocks_conflict_dispatch():
    prs = [pr(5, merge="DIRTY")]
    run = Gh(prs, approved(*prs), fix_runs=[{"status": "queued"}])
    assert train.run_train(ENV, run) == 0
    assert not any(c[:2] == ("workflow", "run") for c in run.calls)


def test_rebase_and_conflict_in_one_run():
    prs = [pr(2, merge="BEHIND"), pr(3, merge="DIRTY")]
    run = Gh(prs, approved(*prs))
    assert train.run_train(ENV, run) == 0
    assert ("api", "-X", "PUT", "repos/o/r/pulls/2/update-branch", "-f", "update_method=rebase") in run.calls
    assert ("workflow", "run", "agent-fix.yml", "-f", "pr=3") in run.calls


def sec(n, **kw):
    p = pr(n, labels=["risk:security"], checks=[{"conclusion": "SUCCESS"}], **kw)
    p["reviewRequests"] = [{"login": "Bankaifan"}]
    return p


def test_waiting_for_owner_needs_everything_but_owner_approval():
    p = sec(1)
    ok = [review("sha1")]
    assert train.waiting_for_owner(p, ok, "app/approver", "Bankaifan")
    assert not train.waiting_for_owner(p, [review("old")], "app/approver", "Bankaifan")
    assert not train.waiting_for_owner(pr(1, labels=["risk:security"]), ok, "app/approver", "Bankaifan")
    assert not train.waiting_for_owner(dict(p, labels=[{"name": "risk:security"}, {"name": "needs-human"}]),
                                       ok, "app/approver", "Bankaifan")
    assert not train.waiting_for_owner(dict(p, statusCheckRollup=RUNNING), ok, "app/approver", "Bankaifan")


def test_train_skips_waiting_pr_and_next_ready_pr_lands():
    prs = [sec(1, merge="BLOCKED"), pr(2, merge="BEHIND")]
    run = Gh(prs, approved(*prs))
    assert train.run_train(ENV, run) == 0
    assert ("api", "-X", "PUT", "repos/o/r/pulls/2/update-branch", "-f", "update_method=rebase") in run.calls


def test_waiting_pr_never_counts_as_in_flight():
    p = sec(1, merge="UNSTABLE")
    assert train.plan([p], False, waiting=set())[0] is p
    assert train.plan([p], False, waiting={1})[0] is None


def test_waiting_pr_is_rebased_without_auto_merge_when_main_moves():
    prs = [sec(1, merge="BEHIND", auto=False)]
    run = Gh(prs, approved(*prs))
    assert train.run_train(ENV, run) == 0
    assert ("api", "-X", "PUT", "repos/o/r/pulls/1/update-branch", "-f", "update_method=rebase") in run.calls


def test_waiting_pr_with_conflict_goes_to_fix():
    prs = [sec(1, merge="DIRTY")]
    run = Gh(prs, approved(*prs))
    assert train.run_train(ENV, run) == 0
    assert ("workflow", "run", "agent-fix.yml", "-f", "pr=1") in run.calls


def test_waiting_bound_is_five():
    assert train.MAX_WAITING == 5


def test_failed_rebase_is_reported_and_no_label_changes():
    prs = [pr(2, merge="BEHIND"), pr(3, merge="DIRTY")]
    run = Gh(prs, approved(*prs), fail=("api", "-X", "PUT"))
    assert train.run_train(ENV, run) == 1
    assert not any(c[:2] == ("pr", "edit") or "--add-label" in c for c in run.calls)
    assert not any(c[:2] == ("workflow", "run") for c in run.calls)


def test_failed_pr_list_is_reported_and_changes_nothing():
    run = Gh([], fail=("pr", "list"))
    assert train.run_train(ENV, run) == 1
    assert run.mutations() == []


def test_nothing_is_approved_without_approver_name():
    prs = [pr(2, merge="BEHIND")]
    run = Gh(prs, approved(*prs))
    env = {**ENV, "APPROVER_BOT": ""}
    assert train.run_train(env, run) == 0
    assert run.mutations() == []


def test_empty_queue_does_nothing(capsys):
    run = Gh([])
    assert train.run_train(ENV, run) == 0
    assert run.mutations() == []
    assert "nothing to do; approved candidates: 0" in capsys.readouterr().out


def test_main_usage_error():
    assert train.main(["train.py", "extra"]) == 2
