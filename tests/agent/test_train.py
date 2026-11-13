import json
import subprocess

import pytest
import train

ENV = {"GH_REPO": "o/r", "APPROVER_BOT": "app/approver", "OWNER": "Bankaifan"}
REQUIRED = {"validate", "risk"}
release_main = train.release_main  # the autouse fixture stubs train.release_main for the run_train tests


@pytest.fixture(autouse=True)
def ruleset(monkeypatch):
    """Pins the ruleset's required checks; run_train reads them from main.json."""
    monkeypatch.setattr(train.status, "required_contexts", lambda: set(REQUIRED))
    monkeypatch.setattr(train, "release_main", lambda *a, **k: [])  # run_train never touches the network


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
    p = pr(n, labels=["risk:security"], checks=[{"name": c, "conclusion": "SUCCESS"} for c in REQUIRED], **kw)
    p["reviewRequests"] = [{"login": "Bankaifan"}]
    return p


def test_non_required_check_does_not_hold_the_train():
    running_other = [{"name": "validate", "conclusion": "SUCCESS"}, {"name": "risk", "conclusion": "SUCCESS"},
                     {"name": "orchestrate", "status": "IN_PROGRESS", "conclusion": ""}]
    assert not train.in_flight(pr(1, merge="BLOCKED", checks=running_other), REQUIRED)
    assert train.in_flight(pr(1, merge="BLOCKED", checks=running_other), None)  # null case: every check counts
    running_required = [{"name": "risk", "status": "IN_PROGRESS", "conclusion": ""}]
    assert train.in_flight(pr(1, merge="BLOCKED", checks=running_required), REQUIRED)


def test_non_required_red_does_not_stop_the_next_pr():
    checks = [{"name": "validate", "conclusion": "SUCCESS"}, {"name": "risk", "conclusion": "SUCCESS"},
              {"name": "orchestrate", "conclusion": "CANCELLED"}]
    prs = [pr(1, merge="BLOCKED", checks=checks), pr(2, merge="BEHIND")]
    run = Gh(prs, approved(*prs))
    assert train.run_train(ENV, run) == 0
    assert ("api", "-X", "PUT", "repos/o/r/pulls/2/update-branch", "-f", "update_method=rebase") in run.calls


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


def test_train_runs_the_release_first_and_reports_it(capsys):
    calls = []
    assert train.run_train(ENV, Gh([]), releaser=lambda: calls.append(1) or ["1.20", "1.21"]) == 0
    assert calls == [1]
    assert "opened release PR Release 1.20, 1.21" in capsys.readouterr().out


def test_long_release_title_is_shortened_to_100_characters(capsys):
    versions = [f"1.{n}" for n in range(21, 61)]
    assert train.run_train(ENV, Gh([]), releaser=lambda: versions) == 0
    assert "opened release PR Release 1.21 to 1.60 (40 versions)" in capsys.readouterr().out


def test_failed_release_does_not_stop_the_train(capsys):
    prs = [pr(5, merge="DIRTY")]
    run = Gh(prs, approved(*prs))
    assert train.run_train(ENV, run, releaser=lambda: None) == 0
    out = capsys.readouterr().out
    assert "release: failed" in out
    assert ("workflow", "run", "agent-fix.yml", "-f", "pr=5") in run.calls


def test_train_has_no_rebump_path():
    assert not hasattr(train, "rebump_branch")
    assert not (train.Path(train.__file__).parent / "rebump.py").exists()


def g(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, env=train.git_env(), check=True, capture_output=True,
                          text=True).stdout.strip()


CL = "# Changelog\n\n## [Unreleased]\n\n## [1.4] - 2026-01-01\n- old\n"


def origin_repo(tmp_path):
    """A bare origin whose main is at 1.4 with no fragments; returns (origin, work clone on main)."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    g(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    g(tmp_path, "clone", "-q", str(origin), str(work))
    g(work, "checkout", "-q", "-b", "main")
    (work / "VERSION").write_text("1.4\n")
    (work / "CHANGELOG.md").write_text(CL)
    g(work, "add", "-A")
    g(work, "commit", "-q", "-m", "base")
    g(work, "push", "-q", "origin", "main")
    return origin, work


def merge_fragment(work, name, text):
    """What a merged PR does to main: it adds one fragment and nothing else touches VERSION or CHANGELOG.md."""
    (work / "changelog.d").mkdir(exist_ok=True)
    (work / "changelog.d" / name).write_text(text)
    g(work, "add", "-A")
    g(work, "commit", "-q", "-m", f"merge {name}")
    g(work, "push", "-q", "origin", "main")


def test_release_main_two_merges_in_a_row_give_two_versions_and_sections(tmp_path):
    origin, work = origin_repo(tmp_path)
    merge_fragment(work, "10.md", "first change\n")
    main_before = g(origin, "rev-parse", "main")
    folded = []
    assert release_main(str(origin), fragments=folded) == ["1.5"]
    assert folded == ["10.md"]
    assert g(origin, "rev-parse", "main") == main_before  # never a push to main
    assert g(origin, "show", "release/next:VERSION") == "1.5"
    g(origin, "update-ref", "refs/heads/main", "refs/heads/release/next")  # the release PR merges
    g(work, "pull", "-q", "--rebase", "origin", "main")  # the second PR was never rebased for VERSION or CHANGELOG
    merge_fragment(work, "11.md", "second change\nstep: x\n")
    assert release_main(str(origin)) == ["2.0"]
    assert g(origin, "show", "release/next:VERSION") == "2.0"
    log = g(origin, "show", "release/next:CHANGELOG.md")
    assert log.index("## [2.0]") < log.index("## [1.5]") < log.index("## [1.4]")
    assert "- first change" in log and "- second change" in log
    assert "changelog.d" not in g(origin, "ls-tree", "-r", "--name-only", "release/next")
    assert g(origin, "log", "-1", "--format=%an <%ae>|%B", "release/next").startswith("Daniel <476059+")
    assert "Co-authored-by" not in g(origin, "log", "-1", "--format=%B", "release/next")


def test_release_main_unchanged_result_is_not_pushed_again(tmp_path):
    origin, work = origin_repo(tmp_path)
    merge_fragment(work, "10.md", "first change\n")
    assert release_main(str(origin)) == ["1.5"]
    first = g(origin, "rev-parse", "release/next")
    assert release_main(str(origin)) == ["1.5"]
    assert g(origin, "rev-parse", "release/next") == first
    merge_fragment(work, "11.md", "more\nstep: x\n")
    assert release_main(str(origin)) == ["1.5", "2.0"]
    assert g(origin, "rev-parse", "release/next") != first


def test_release_main_without_fragments_pushes_nothing(tmp_path):
    origin, _ = origin_repo(tmp_path)
    before = g(origin, "rev-parse", "main")
    assert release_main(str(origin)) == []
    assert g(origin, "rev-parse", "main") == before
    assert g(origin, "branch", "--list", "release/next") == ""


def test_release_main_refuses_a_bad_fragment_and_pushes_nothing(tmp_path):
    origin, work = origin_repo(tmp_path)
    merge_fragment(work, "10.md", "step: y\n")
    before = g(origin, "rev-parse", "main")
    assert release_main(str(origin)) is None
    assert g(origin, "rev-parse", "main") == before
    assert g(origin, "branch", "--list", "release/next") == ""


def test_release_main_refuses_a_commit_touching_other_paths(tmp_path, monkeypatch):
    origin, work = origin_repo(tmp_path)
    merge_fragment(work, "10.md", "first change\n")
    monkeypatch.setattr(train, "RELEASE_PATHS", {"VERSION"})  # CHANGELOG.md is now a foreign path
    assert release_main(str(origin)) is None
    assert g(origin, "branch", "--list", "release/next") == ""


def test_fragments_on_main_open_one_release_pr_and_a_second_run_updates_it(tmp_path, capsys, monkeypatch):
    origin, work = origin_repo(tmp_path)
    merge_fragment(work, "10.md", "first change\n")
    main_before = g(origin, "rev-parse", "main")
    monkeypatch.setattr(train, "release_main",
                        lambda remote, token="", base="main", fragments=None: release_main(str(origin), fragments=fragments))
    run = Gh([])
    assert train.run_train(ENV, run) == 0
    creates = [c for c in run.calls if c[:2] == ("pr", "create")]
    assert len(creates) == 1 and "Release 1.5" in creates[0] and "--head" in creates[0]
    assert "release/next" in creates[0] and "10.md" in creates[0][-1]
    assert g(origin, "rev-parse", "main") == main_before
    run.prs = [{"number": 77, "headRefName": "release/next"}]
    assert train.run_train(ENV, run) == 0
    assert len([c for c in run.calls if c[:2] == ("pr", "create")]) == 1
    assert [c for c in run.calls if c[:3] == ("pr", "edit", "77")]
    assert g(origin, "rev-parse", "main") == main_before


def test_nothing_to_release_closes_an_open_release_pr():
    run = Gh([{"number": 77, "headRefName": "release/next"}])
    assert train.run_train(ENV, run, releaser=list) == 0
    assert ("pr", "close", "77", "--comment", "Nothing left to release.") in run.calls
    quiet = Gh([])
    assert train.run_train(ENV, quiet, releaser=list) == 0
    assert not [c for c in quiet.calls if c[:2] in (("pr", "close"), ("pr", "create"))]


def test_git_token_goes_through_the_environment_only():
    env = train.git_env("s3cret")
    assert env["GIT_CONFIG_KEY_0"] == "http.extraheader"
    assert "s3cret" not in "".join(v for k, v in env.items() if k != "GIT_CONFIG_VALUE_0")
    assert "GIT_CONFIG_COUNT" not in train.git_env()


def test_main_usage_error():
    assert train.main(["train.py", "extra"]) == 2
