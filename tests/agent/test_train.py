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
    monkeypatch.setattr(train, "release_main", lambda *a, **k: "")  # run_train never touches the network


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
        self.calls, self.parked = [], []

    def __call__(self, *args):
        self.calls.append(args)
        if self.fail and tuple(args[:len(self.fail)]) == self.fail:
            raise subprocess.CalledProcessError(1, ["gh", *args], stderr="HTTP 500")
        if args[:2] == ("pr", "list"):
            return json.dumps(self.prs)
        if args[:2] == ("issue", "list"):
            return json.dumps(self.parked)
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
    prs = [pr(1), pr(2), pr(3, branch="dependabot/x"), pr(4, labels=["parked"]),
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
    assert not train.waiting_for_owner(dict(p, labels=[{"name": "risk:security"}, {"name": "parked"}]),
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
    assert train.run_train(ENV, Gh([]), releaser=lambda: calls.append(1) or "1.20") == 0
    assert calls == [1]
    assert "opened release PR Release 1.20" in capsys.readouterr().out


def test_release_pr_is_the_owners_task_notes_as_body_parked_items_in_one_line():
    run = Gh([])
    run.parked = [{"number": 9}, {"number": 4}]
    train.release_pr(run, "1.20", ["- Neu: A", "- Fix: B"], "Bankaifan")
    create = next(c for c in run.calls if c[:2] == ("pr", "create"))
    assert create[create.index("--reviewer") + 1] == "Bankaifan"
    assert create[create.index("--body") + 1] == "- Neu: A\n- Fix: B\n\nNoch ungelöst: #4, #9"
    quiet = Gh([])
    train.release_pr(quiet, "1.20", [], "Bankaifan", "English")
    assert "Internal changes only." in next(c for c in quiet.calls if c[:2] == ("pr", "create"))


def test_release_pr_notes_mention_nobody_close_nothing_and_parked_prs_are_listed():
    run = Gh([pr(7)])
    run.parked = [{"number": 9}]
    notes = ["- Neu: A @Bankaifan closes closes #57 #58", "- Fix: B fixes https://github.com/o/r/issues/3 <!-- x -->"]
    train.release_pr(run, "1.20", notes, "Bankaifan")
    create = next(c for c in run.calls if c[:2] == ("pr", "create"))
    body = create[create.index("--body") + 1]
    assert body == "- Neu: A Bankaifan closes closes\n- Fix: B fixes &lt;!-- x -->\n\nNoch ungelöst: #7, #9"
    assert ("pr", "list", "--state", "open", "--label", "parked", "--json", "number") in run.calls


def test_failed_release_does_not_stop_the_train(capsys):
    prs = [pr(5, merge="DIRTY")]
    run = Gh(prs, approved(*prs))
    assert train.run_train(ENV, run, releaser=lambda: None) == 1  # red, so the stall is seen; the train still ran
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


def test_release_main_two_releases_in_a_row_give_two_versions_and_sections(tmp_path):
    origin, work = origin_repo(tmp_path)
    merge_fragment(work, "10.md", "first change\n")
    main_before = g(origin, "rev-parse", "main")
    folded = []
    assert release_main(str(origin), notes=folded) == "1.5"
    assert folded == ["- first change"]
    assert g(origin, "rev-parse", "main") == main_before  # never a push to main
    assert g(origin, "show", "release/next:VERSION") == "1.5"
    g(origin, "update-ref", "refs/heads/main", "refs/heads/release/next")  # the release PR merges
    g(work, "pull", "-q", "--rebase", "origin", "main")  # the second PR was never rebased for VERSION or CHANGELOG
    merge_fragment(work, "11.md", "second change\nstep: x\n")
    assert release_main(str(origin)) == "2.0"
    assert g(origin, "show", "release/next:VERSION") == "2.0"
    log = g(origin, "show", "release/next:CHANGELOG.md")
    assert log.index("## [2.0]") < log.index("## [1.5]") < log.index("## [1.4]")
    assert g(origin, "log", "-1", "--format=%s", "release/next") == "V1.5-RELEASE: version 2.0"
    assert "- first change" in log and "- second change" in log
    assert "changelog.d" not in g(origin, "ls-tree", "-r", "--name-only", "release/next")
    assert g(origin, "log", "-1", "--format=%an <%ae>|%B", "release/next").startswith("Daniel <476059+")
    assert "Co-authored-by" not in g(origin, "log", "-1", "--format=%B", "release/next")


def test_release_main_unchanged_result_is_not_pushed_again(tmp_path):
    origin, work = origin_repo(tmp_path)
    merge_fragment(work, "10.md", "first change\n")
    assert release_main(str(origin)) == "1.5"
    first = g(origin, "rev-parse", "release/next")
    assert release_main(str(origin)) == "1.5"
    assert g(origin, "rev-parse", "release/next") == first
    merge_fragment(work, "11.md", "more\nstep: x\n")
    assert release_main(str(origin)) == "2.0"  # two fragments, still one release and one step
    assert g(origin, "rev-parse", "release/next") != first


def test_release_main_without_fragments_pushes_nothing(tmp_path):
    origin, _ = origin_repo(tmp_path)
    before = g(origin, "rev-parse", "main")
    assert release_main(str(origin)) == ""
    assert g(origin, "rev-parse", "main") == before
    assert g(origin, "branch", "--list", "release/next") == ""


def test_release_main_in_a_project_without_a_version_file_is_no_failure(tmp_path):
    origin, work = origin_repo(tmp_path)
    g(work, "rm", "-q", "VERSION")
    merge_fragment(work, "10.md", "a change\n")
    assert release_main(str(origin)) == ""  # "" = nothing to release; None would turn every train run red
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
                        lambda remote, token="", base="main", notes=None: release_main(str(origin), notes=notes))
    run = Gh([])
    assert train.run_train(ENV, run) == 0
    creates = [c for c in run.calls if c[:2] == ("pr", "create")]
    assert len(creates) == 1 and "Release 1.5" in creates[0] and "--head" in creates[0]
    assert "release/next" in creates[0] and "- first change" in creates[0]
    assert g(origin, "rev-parse", "main") == main_before
    run.prs = [{"number": 77, "headRefName": "release/next"}]
    assert train.run_train(ENV, run) == 0
    assert len([c for c in run.calls if c[:2] == ("pr", "create")]) == 1
    assert [c for c in run.calls if c[:3] == ("pr", "edit", "77")]
    assert g(origin, "rev-parse", "main") == main_before


def test_nothing_to_release_closes_an_open_release_pr():
    run = Gh([{"number": 77, "headRefName": "release/next"}])
    assert train.run_train(ENV, run, releaser=str) == 0
    assert ("pr", "close", "77") in run.calls
    quiet = Gh([])
    assert train.run_train(ENV, quiet, releaser=str) == 0
    assert not [c for c in quiet.calls if c[:2] in (("pr", "close"), ("pr", "create"))]


def test_git_token_goes_through_the_environment_only():
    env = train.git_env("s3cret")
    assert env["GIT_CONFIG_KEY_0"] == "http.extraheader"
    assert "s3cret" not in "".join(v for k, v in env.items() if k != "GIT_CONFIG_VALUE_0")
    assert "GIT_CONFIG_COUNT" not in train.git_env()


# --- batch (decision 0018) --------------------------------------------------------------------

GREEN = [{"name": c, "conclusion": "SUCCESS"} for c in sorted(REQUIRED)]
NOW = train.datetime.datetime(2026, 11, 19, 12, 0, tzinfo=train.datetime.UTC)


def ready(n, files=None, **kw):
    """An approved, green PR that is behind main: what the serial train would rebase."""
    p = pr(n, files=files or (f"src/f{n}.py",), **{"merge": "BEHIND", "checks": GREEN, **kw})
    return {**p, "headRefOid": str(n) * 40, "body": f"Does it.\n\nCloses #{n + 100}"}


def batch_pr(members, number=50, state="OPEN", merge="BLOCKED", checks=(), base="main", author="app/author"):
    title, body = train.batch_text(members)
    return {"number": number, "state": state, "title": title, "body": body, "headRefName": train.BATCH_BRANCH,
            "baseRefName": base, "author": {"login": author},
            "approved": train.agent_guard.body_hash(body),  # not a gh field: the body hash tools/reapprove.py vouched for
            "headRefOid": "b" * 40, "isCrossRepository": False, "mergeStateStatus": merge,
            "statusCheckRollup": list(checks), "labels": []}


class BatchGh(Gh):
    """Gh plus the batch PRs (newest first) and the commit date of the open batch's head."""

    def __init__(self, prs, batches=(), built="2026-11-19T11:55:00Z", **kw):
        super().__init__(prs, approved(*prs), **kw)
        self.batches, self.built, self.builds, self.state_now = list(batches), built, [], "OPEN"
        for b in self.batches:  # what tools/reapprove.py left on the batch it approved
            self.reviews[b["number"]] = [{**review(b["headRefOid"]), "body": f"ok\n\nbody-hash: {b['approved']}"}]

    def __call__(self, *args):
        if args[:2] == ("pr", "list") and train.BATCH_BRANCH in args:
            self.calls.append(args)
            return json.dumps(self.batches)
        if args[0] == "api" and "/commits/" in args[1]:
            return self.built + "\n"
        if args[:2] == ("pr", "view"):
            return json.dumps({"state": self.state_now})
        return super().__call__(*args)

    def builder(self, members, avoid):
        self.builds.append(([p["number"] for p in members], set(avoid)))
        return members

    def go(self, env=ENV, builder=None):
        assert train.run_train(env, self, now=NOW, builder=builder or self.builder) == 0
        return [c for c in self.calls if c[:2] in (("pr", "create"), ("pr", "close"), ("pr", "edit"), ("api", "-X"))]


REBASE_1 = ("api", "-X", "PUT", "repos/o/r/pulls/1/update-branch", "-f", "update_method=rebase")


def test_batch_members_are_green_riskless_disjoint_and_at_most_eight():
    out = [ready(2, labels=["risk:infra"]), ready(3, checks=RUNNING), ready(4, merge="DIRTY"),
           ready(5, files=("src/f1.py", "src/z.py")), ready(6, files=("docs/design/0019-x.md", "src/y.py")),
           ready(7, branch="agent/cleaner-x"), {**ready(8), "files": []}]
    assert [p["number"] for p in train.batchable([ready(1), *out, ready(9)], REQUIRED)] == [1, 9]
    assert train.batchable([ready(1), *out], REQUIRED) == []  # fewer than two: the serial path
    assert [p["number"] for p in train.batchable([ready(n) for n in range(1, 12)], REQUIRED)] == list(range(1, 9))
    parked = train.candidates([ready(1), ready(2, labels=["parked"])], lambda n: [review(str(n) * 40)], "app/approver")
    assert train.batchable(parked, REQUIRED) == []


def test_two_ready_prs_become_one_batch_pr_and_are_not_rebased(capsys):
    run = BatchGh([ready(2), ready(1)])
    (create,) = run.go()
    assert create[:8] == ("pr", "create", "--base", "main", "--head", "agent/batch", "--title", "Batch: #1, #2")
    assert create[-1] == f"Batch: #1@{'1' * 7} #2@{'2' * 7}\n{train.EVIDENCE}\nCloses #101\nCloses #102"
    assert run.builds == [([1, 2], set())]
    assert "batch: opened Batch: #1, #2" in capsys.readouterr().out


def test_batch_body_copies_numbers_only_and_keeps_refs_apart():
    a = {**ready(1), "body": "@someone <!-- x --> fixes #7, refs #8 and Closes #7\nBatch: #9@abcdef0 #8@abcdef0"}
    assert train.batch_text([a, ready(2)])[1] == f"Batch: #1@{'1' * 7} #2@{'2' * 7}\n{train.EVIDENCE}\nCloses #7\nRefs #8\nCloses #102"


def test_a_failed_batch_is_not_built_again_from_the_same_members():
    prs = [ready(1), ready(2)]
    run = BatchGh(prs, [batch_pr(prs, state="CLOSED")])
    assert run.go(builder=lambda members, avoid: [] if {p["number"] for p in members} == avoid else members) == [REBASE_1]
    run = BatchGh(prs, [batch_pr(prs, state="CLOSED")])
    run.go()
    assert run.builds == [([1, 2], {1, 2})]  # build_batch gets the failed set and builds nothing for it


def test_no_batch_when_switched_off_or_while_a_pr_is_about_to_merge():
    run = BatchGh([ready(1), ready(2)])
    assert run.go({**ENV, "TRAIN_BATCH": "off"}) == [REBASE_1] and run.builds == []
    run = BatchGh([ready(1), ready(2), ready(3, merge="CLEAN")])
    assert run.go() == [] and run.builds == []


def test_members_are_closed_once_their_batch_is_merged():
    moved = {**ready(2), "headRefOid": "c" * 40}  # pushed after the batch was built: it stays open
    prs = [ready(1), moved, ready(3)]
    run = BatchGh(prs, [batch_pr([ready(1), ready(2), ready(3)], state="MERGED")])
    assert run.go() == [("pr", "close", "1", "--comment", "Merged with #50."),
                        ("pr", "close", "3", "--comment", "Merged with #50."),
                        ("api", "-X", "PUT", "repos/o/r/pulls/2/update-branch", "-f", "update_method=rebase")]


def test_a_merged_batch_closes_only_what_the_approval_of_its_body_vouches_for():
    edited = batch_pr([ready(1), ready(2)], state="MERGED")  # approved as #1 #2, the body rewritten afterwards
    prs = [{**ready(7), "headRefName": "feature/owner-work"}, ready(8), ready(9)]
    edited["body"] = f"Batch: #7@{'7' * 7} #8@{'8' * 7}"
    assert not any(c[:2] == ("pr", "close") for c in BatchGh(prs, [edited]).go())
    honest = batch_pr([prs[0], ready(8)], state="MERGED")  # even a vouched line closes agent/<N>- PRs only
    assert [c for c in BatchGh(prs, [honest]).go() if c[:2] == ("pr", "close")] == [("pr", "close", "8", "--comment", "Merged with #50.")]
    for bad in ({"state": "COMMENTED"}, {"commit_id": "c" * 40}, {"user": {"login": "app/author"}}, {"body": "ok"}):
        run = BatchGh(prs, [honest])
        run.reviews[50] = [{**run.reviews[50][0], **bad}]
        assert not any(c[:2] == ("pr", "close") for c in run.go())


def test_the_body_of_a_batch_that_is_no_longer_open_is_never_edited(capsys):
    run = BatchGh([ready(1), {**ready(2), "headRefOid": "c" * 40}, ready(3)], [batch_pr([ready(1), ready(2)])])
    run.state_now = "MERGED"  # merged while the train built it again
    assert run.go() == [] and "merged or closed meanwhile" in capsys.readouterr().out


def test_a_pr_from_the_batch_branch_into_another_base_or_by_another_author_is_not_the_batch():
    prs = [ready(1), ready(2)]
    for other in (batch_pr(prs, number=60, base="dev"), batch_pr(prs, number=60, author="someone")):
        run = BatchGh(prs, [other, batch_pr(prs, checks=RUNNING)])  # the newer one would shadow the real batch
        assert run.go({**ENV, "AUTHOR_BOT": "app/author"}) == [] and run.builds == [([1, 2], set())]
        (listing,) = [c for c in run.calls if c[:2] == ("pr", "list") and "agent/batch" in c]
        assert listing[listing.index("--base") + 1] == "main"
        (create,) = BatchGh(prs, [{**other, "state": "MERGED"}]).go({**ENV, "AUTHOR_BOT": "app/author"})
        assert create[:2] == ("pr", "create")  # nothing is closed as landed with it


def test_an_open_batch_with_ready_members_holds_the_train(capsys):
    prs = [ready(1), ready(2), ready(3, labels=["risk:infra"])]
    run = BatchGh(prs, [batch_pr(prs[:2], checks=RUNNING)])
    assert run.go() == [] and run.builds == [([1, 2], set())]  # built again: pushed only if main moved
    assert "waiting: batch PR #50" in capsys.readouterr().out


@pytest.mark.parametrize("kw, built, reviews", [
    ({"checks": [{"name": "validate", "conclusion": "FAILURE"}]}, "", []),
    ({"merge": "DIRTY"}, "", []),
    ({}, "", [review("b" * 40, state="CHANGES_REQUESTED", login="Bankaifan")]),
    ({"checks": GREEN}, "2026-11-19T11:29:00Z", []),  # green and still open after BATCH_WAIT_MIN: refused or stuck
])
def test_a_red_conflicting_refused_or_stuck_batch_is_closed_and_the_serial_train_goes_on(kw, built, reviews):
    prs = [ready(1), ready(2)]
    run = BatchGh(prs, [batch_pr(prs, **kw)], built=built)
    run.reviews[50] = reviews
    assert run.go() == [("pr", "close", "50"), REBASE_1] and run.builds == []


def test_an_open_batch_out_of_date_with_its_members_is_built_again_or_closed():
    old = batch_pr([ready(1), ready(2)])
    pushed = {**ready(2), "headRefOid": "c" * 40}
    run = BatchGh([ready(1), pushed, ready(3)], [old])
    (edit,) = run.go()
    assert edit[:5] == ("pr", "edit", "50", "--title", "Batch: #1, #2, #3") and "#2@ccccccc" in edit[-1]
    run = BatchGh([ready(1), {**pushed, "statusCheckRollup": RUNNING}], [old])
    assert run.go() == [("pr", "close", "50"), REBASE_1]


def pr_branch(work, origin, n, path, text, base="main"):
    """Push a one-commit branch as refs/pull/N/head, as GitHub keeps it; returns the member the train lists."""
    g(work, "checkout", "-q", "-B", f"b{n}", base)
    (work / path).write_text(text)
    g(work, "add", "-A")
    g(work, "commit", "-q", "-m", f"change {n}")
    g(work, "push", "-q", "origin", f"HEAD:refs/pull/{n}/head")
    return {"number": n, "headRefOid": g(work, "rev-parse", "HEAD")}


def test_build_batch_picks_disjoint_members_onto_main_and_drops_a_conflicting_one(tmp_path):
    origin, work = origin_repo(tmp_path)
    one, two = pr_branch(work, origin, 1, "a.txt", "a\n"), pr_branch(work, origin, 2, "b.txt", "b\n")
    clash = pr_branch(work, origin, 3, "VERSION", "9.9\n")
    g(work, "checkout", "-q", "main")
    (work / "VERSION").write_text("1.5\n")  # main moved under all three; only #3 touches what it changed
    g(work, "commit", "-q", "-am", "main moves")
    g(work, "push", "-q", "origin", "main")
    kept = train.build_batch(str(origin), [one, two, clash])
    assert [p["number"] for p in kept] == [1, 2]
    assert g(origin, "log", "--format=%s", "main..agent/batch").split("\n") == ["change 2", "change 1"]
    assert g(origin, "show", "agent/batch:a.txt") == "a" and g(origin, "show", "agent/batch:VERSION") == "1.5"
    first = g(origin, "rev-parse", "agent/batch")
    assert train.build_batch(str(origin), [one, two]) == [one, two]
    assert g(origin, "rev-parse", "agent/batch") == first  # same tree on the same main: not pushed again
    (work / "c.txt").write_text("c\n")
    g(work, "add", "-A")
    g(work, "commit", "-q", "-m", "main moves again")
    g(work, "push", "-q", "origin", "main")
    assert train.build_batch(str(origin), [one, two]) == [one, two]
    assert g(origin, "rev-parse", "agent/batch") != first and g(origin, "show", "agent/batch:c.txt") == "c"
    second = g(origin, "rev-parse", "agent/batch")
    assert train.build_batch(str(origin), [one, {**two, "headRefOid": "0" * 40}]) == []  # a head that moved is dropped
    assert train.build_batch(str(origin), [one, two, clash], avoid={1, 2}) == []  # the set that just failed
    assert train.build_batch(str(tmp_path / "missing.git"), [one, two]) is None
    assert train.build_batch(str(tmp_path / "missing.git"), [one, two], avoid={1, 2}) == []  # decided before any clone
    assert g(origin, "rev-parse", "agent/batch") == second and g(origin, "rev-parse", "main") != second


def test_what_the_train_builds_is_what_reapprove_accepts(tmp_path, monkeypatch):
    """The two halves of decision 0018 agree on real git output, also when main moved (not in a member's file)."""
    origin, work = origin_repo(tmp_path)
    (work / "a.txt").write_text("".join(f"line {i}\n" for i in range(40)))
    g(work, "add", "-A")
    g(work, "commit", "-q", "-m", "a")
    g(work, "push", "-q", "origin", "main")
    text = (work / "a.txt").read_text()
    one = pr_branch(work, origin, 1, "a.txt", text.replace("line 30\n", "line 30 changed\n"))
    two = pr_branch(work, origin, 2, "b.txt", "b\n")
    g(work, "checkout", "-q", "main")
    three = pr_branch(work, origin, 3, "c.txt", "c\n")
    g(work, "checkout", "-q", "main")
    (work / "VERSION").write_text("1.5\n")
    g(work, "commit", "-q", "-am", "main moves")
    g(work, "push", "-q", "origin", "main")
    assert train.build_batch(str(origin), [one, two]) == [one, two]
    first = g(origin, "rev-parse", "agent/batch")
    (work / "a.txt").write_text("top\n" + text)  # picks cleanly, but reapprove would refuse the moved hunk
    g(work, "commit", "-q", "-am", "main moves in a.txt")
    g(work, "push", "-q", "origin", "main")
    assert train.build_batch(str(origin), [one, two]) == [] and g(origin, "rev-parse", "agent/batch") == first
    assert train.build_batch(str(origin), [one, two, three]) == [two, three]
    g(work, "revert", "--no-edit", "HEAD")
    g(work, "push", "-q", "origin", "main")
    assert train.build_batch(str(origin), [one, two]) == [one, two]
    shas = {9: g(origin, "rev-parse", "agent/batch"), 1: one["headRefOid"], 2: two["headRefOid"]}

    def gh(*args):
        path = args[-1] if "--slurp" in args else args[1]
        if "-X" in args:
            return posted.append(args) or ""
        if "/compare/" in path:
            return g(origin, "diff", "main..." + path.rsplit("...", 1)[1]) + "\n"
        if "/commits/" in path:  # a member's own gates
            return json.dumps({"check_runs": [{"name": "risk", "conclusion": "success"}]} if "check-runs" in path
                              else [{"context": "security-review", "state": "success"}])
        n = int(path.split("/pulls/")[1].split("/")[0])
        if path.endswith("/reviews"):
            return json.dumps([[review(shas[n])] if n != 9 else []])
        if path.endswith("/files"):
            return json.dumps([[{"filename": "a.txt"}, {"filename": "b.txt"}]])
        if path.endswith("/commits"):
            return json.dumps([[{"parents": [{}]}] * 2])
        return json.dumps({"state": "open", "labels": [], "changed_files": 2 if n == 9 else 1, "base": {"ref": "main"},
                           "commits": 2,
                           "user": {"login": "app/author"}, "body": train.batch_text([one, two])[1],
                           "head": {"sha": shas[n], "ref": "agent/batch" if n == 9 else f"agent/{n}-x",
                                    "repo": {"full_name": "o/r"}}})

    monkeypatch.chdir(tmp_path)  # no CODEOWNERS, no AGENTS.md of the real checkout
    posted = []
    assert train.reapprove.run_reapprove("9", shas[9], {**ENV, "AUTHOR_BOT": "app/author"}, gh) == 0
    assert f"commit_id={shas[9]}" in posted[0] and "event=APPROVE" in posted[0]


def test_main_usage_error():
    assert train.main(["train.py", "extra"]) == 2
