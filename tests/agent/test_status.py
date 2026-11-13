import datetime
import importlib.util
import json
import pathlib
import subprocess

import pytest

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "status.py"
_spec = importlib.util.spec_from_file_location("status", _path)
st = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(st)

NOW = datetime.datetime(2026, 11, 9, 12, 0, tzinfo=datetime.UTC)
UTC = datetime.UTC


def ago(minutes):
    return (NOW - datetime.timedelta(minutes=minutes)).isoformat()


def at(h, m):
    return datetime.datetime(2026, 1, 1, h, m, tzinfo=UTC)


def pr(number=1, branch="agent/1-x", labels=(), **kw):
    base = {"number": number, "title": "T", "url": f"u/{number}", "headRefName": branch, "headRefOid": f"sha{number}",
            "labels": [{"name": n} for n in labels], "reviewRequests": [], "statusCheckRollup": [],
            "author": {"login": "app/author"}, "createdAt": ago(60), "mergeStateStatus": "CLEAN",
            "isCrossRepository": False, "commits": [{"committedDate": ago(60)}]}
    base.update(kw)
    return base


def issue(number=1, labels=("agent:dev",), title="Do it"):
    return {"number": number, "title": title, "labels": [{"name": n} for n in labels], "createdAt": ago(500)}


class Recorder:
    def __init__(self):
        self.calls = []
        self.comments = []

    def __call__(self, *args):
        self.calls.append(args)
        if args[1] == "comment":
            self.comments.append({"body": args[args.index("--body") + 1]})
        if args[:1] in (("pr",), ("issue",)) and args[1] == "view" and "comments" in args:
            return json.dumps({"comments": self.comments})
        return json.dumps({"author": {"login": "app/author"}})


def test_interval_defaults_and_rounding():
    assert st.interval_minutes("", False) == 30
    assert st.interval_minutes("", True) == 60
    assert st.interval_minutes("45", False) == 60
    assert st.interval_minutes("junk", True) == 60


def test_should_run_gate():
    assert st.should_run("workflow_dispatch", True, "", at(10, 37))
    assert st.should_run("workflow_run", True, "", at(10, 37))
    assert st.should_run("schedule", False, "", at(10, 37))
    assert st.should_run("schedule", True, "", at(10, 7))
    assert not st.should_run("schedule", True, "", at(10, 37))


def test_ci_state():
    assert st.ci_state([]) == "none"
    assert st.ci_state([{"conclusion": "SUCCESS"}]) == "green"
    assert st.ci_state([{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}]) == "red"
    assert st.ci_state([{"status": "IN_PROGRESS", "conclusion": ""}]) == "running"


REQUIRED = {"validate", "risk"}


def test_ci_state_counts_only_required_checks():
    ok = {"name": "validate", "conclusion": "SUCCESS"}
    risk_ok = {"name": "risk", "conclusion": "SUCCESS"}
    orch = {"name": "orchestrate", "conclusion": "CANCELLED"}
    assert st.ci_state([ok, risk_ok, orch], REQUIRED) == "green"
    assert st.ci_state([ok, {"name": "risk", "conclusion": "FAILURE"}], REQUIRED) == "red"
    assert st.ci_state([ok, {"name": "risk", "status": "IN_PROGRESS", "conclusion": ""}], REQUIRED) == "running"
    assert st.ci_state([ok, risk_ok, {"name": "orchestrate", "status": "IN_PROGRESS", "conclusion": ""}],
                       REQUIRED) == "green"
    assert st.ci_state([ok, {"context": "risk", "state": "FAILURE"}], REQUIRED) == "red"


def test_required_check_not_reported_yet_is_running():
    assert st.ci_state([{"name": "validate", "conclusion": "SUCCESS"}], REQUIRED) == "running"
    assert st.ci_state([], REQUIRED) == "running"


def test_ci_state_without_required_set_counts_every_check():
    ok = {"name": "validate", "conclusion": "SUCCESS"}
    orch = {"name": "orchestrate", "conclusion": "CANCELLED"}
    for null in (None, set()):  # unreadable or empty ruleset: as before
        assert st.ci_state([ok, orch], null) == "red"
        assert st.ci_state([ok], null) == "green"
        assert st.ci_state([], null) == "none"


def test_non_required_reds_are_listed_not_blocking():
    ok = {"name": "validate", "conclusion": "SUCCESS"}
    rollup = [ok, {"name": "orchestrate", "conclusion": "CANCELLED"}, {"name": "risk", "conclusion": "FAILURE"}]
    assert st.non_required_reds(rollup, REQUIRED) == ["orchestrate"]
    assert st.non_required_reds(rollup, None) == []
    green = [ok, {"name": "risk", "conclusion": "SUCCESS"}, rollup[1]]
    line = st.pr_line(pr(7, statusCheckRollup=green), "Bankaifan", REQUIRED)
    assert "CI green" in line and "red but not required: orchestrate" in line
    assert "red but not required" not in st.pr_line(pr(7, statusCheckRollup=green), "Bankaifan")


def test_required_contexts_reads_ruleset(tmp_path):
    path = tmp_path / "main.json"
    rules = [{"type": "deletion"},
             {"type": "required_status_checks",
              "parameters": {"required_status_checks": [{"context": "validate"}, {"context": "risk"}]}}]
    path.write_text(json.dumps({"rules": rules}), encoding="utf-8")
    assert st.required_contexts(str(path)) == {"validate", "risk"}


def test_required_contexts_null_cases(tmp_path):
    assert st.required_contexts(str(tmp_path / "missing.json")) is None
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert st.required_contexts(str(broken)) is None
    none_required = tmp_path / "none.json"
    none_required.write_text(json.dumps({"rules": [{"type": "deletion"}]}), encoding="utf-8")
    assert st.required_contexts(str(none_required)) is None


def test_waits_for_daniel():
    assert st.waits_for(pr(labels=["needs-human"]), "Bankaifan") == "needs-human"
    assert st.waits_for(pr(reviewRequests=[{"login": "Bankaifan"}]), "Bankaifan") == "waiting for Daniel"
    ready = pr(reviewDecision="REVIEW_REQUIRED", statusCheckRollup=[{"conclusion": "SUCCESS"}])
    assert st.waits_for(ready, "Bankaifan") == "waiting for code owner review"


def test_orphan_issue_needs_age_no_job_no_pr():
    def old(i):
        return ago(31)

    def young(i):
        return ago(5)

    i = issue(7)
    assert st.orphan_issues([i], [], [], old, NOW) == [i]
    assert st.orphan_issues([i], [], [], young, NOW) == []
    assert st.orphan_issues([i], [pr(branch="agent/7-x")], [], old, NOW) == []
    job = {"workflowName": "agent-dev", "displayTitle": "Do it"}
    assert st.orphan_issues([i], [], [job], old, NOW) == []
    assert st.orphan_issues([issue(7, ("agent:dev", "needs-human"))], [], [], old, NOW) == []


def test_orphan_pr_needs_age_and_no_validate_run():
    p = pr(commits=[{"committedDate": ago(11)}])
    assert st.orphan_prs([p], lambda sha: 0, NOW) == [p]
    assert st.orphan_prs([p], lambda sha: 1, NOW) == []
    assert st.orphan_prs([pr(commits=[{"committedDate": ago(5)}])], lambda sha: 0, NOW) == []
    assert st.orphan_prs([pr(branch="dependabot/x", commits=[{"committedDate": ago(30)}])], lambda s: 0, NOW) == []
    assert st.orphan_prs([pr(mergeStateStatus="DIRTY", commits=[{"committedDate": ago(30)}])], lambda s: 0, NOW) == []


def test_handle_orphan_first_retriggers_second_escalates():
    run = Recorder()
    assert st.handle_orphan("pr", pr(7, "agent/7-x"), "Bankaifan", run) == "retriggered"
    assert ("workflow", "run", "validate.yml", "--ref", "agent/7-x") in run.calls
    run = Recorder()
    assert st.handle_orphan("pr", pr(7, labels=[st.RETRIGGER]), "Bankaifan", run) == "escalated"
    assert ("pr", "edit", "7", "--add-reviewer", "Bankaifan") in run.calls
    assert any(c[:3] == ("pr", "comment", "7") for c in run.calls)
    assert any("needs-human" in c for c in run.calls)


def test_handle_orphan_issue_readds_label():
    run = Recorder()
    assert st.handle_orphan("issue", issue(4), "Bankaifan", run) == "retriggered"
    assert ("issue", "edit", "4", "--remove-label", "agent:dev") in run.calls
    assert ("issue", "edit", "4", "--add-label", "agent:dev") in run.calls


def test_held_runs_only_author_app_head():
    prs = [pr(1, "agent/1-x"), pr(2, "agent/2-x", author={"login": "someone"}),
           pr(3, "agent/3-x", isCrossRepository=True)]
    held = [{"databaseId": 10, "headSha": "sha1"}, {"databaseId": 11, "headSha": "sha2"},
            {"databaseId": 12, "headSha": "sha3"}, {"databaseId": 13, "headSha": "other"}]
    assert st.held_run_ids(held, prs, "author[bot]") == [10]


def test_fix_round_mirrors_agent_fix():
    assert st.fix_round(set()) == ("review:1", False)
    assert st.fix_round({"review:1"}) == ("review:2", False)
    assert st.fix_round({"review:2"}) == ("review:3", True)
    assert st.fix_round({"review:3"}) == (None, True)


def test_conflict_dispatches_fix_then_escalates():
    run = Recorder()
    assert st.handle_conflict(pr(9, mergeStateStatus="DIRTY"), "Bankaifan", run) == "fix dispatched"
    assert ("workflow", "run", "agent-fix.yml", "-f", "pr=9") in run.calls
    assert ("pr", "edit", "9", "--add-label", "review:1") in run.calls
    run = Recorder()
    assert st.handle_conflict(pr(9, labels=["review:2"]), "Bankaifan", run) == "escalated"
    assert not any(c[:2] == ("workflow", "run") for c in run.calls)


def test_limit_prs_picks_only_unhandled_review3():
    stuck = pr(1, labels=["review:3"])
    others = [pr(2, labels=["review:3", "needs-human"]), pr(3, labels=["review:2"]),
              pr(4, labels=["review:3"], reviewDecision="APPROVED"),
              pr(5, labels=["review:3"], commits=[{"committedDate": ago(5)}]),
              pr(6, labels=["review:3"], isCrossRepository=True)]
    assert st.limit_prs([stuck, *others], [], NOW) == [stuck]
    assert st.limit_prs([stuck], [{"workflowName": "agent-fix"}], NOW) == []


def test_limit_hand_over_when_code_approved_but_security_changes():
    sha = "abcdef1234567"
    verdict = [{"author": {"login": "approver"}, "body": f"security-review: changes {sha}"}]
    masked = pr(1, labels=["review:3", "risk:security"], reviewDecision="APPROVED", headRefOid=sha, comments=verdict)
    assert st.limit_prs([masked], [], NOW, "app/approver") == [masked]
    # an approval of a risk:security head without a `changes` verdict still counts as approved
    clean = pr(2, labels=["review:3", "risk:security"], reviewDecision="APPROVED", headRefOid=sha, comments=[])
    assert st.limit_prs([clean], [], NOW, "app/approver") == []


def test_stuck_limit_hands_over_or_escalates(monkeypatch):
    monkeypatch.setattr(st, "handle_limit", lambda n, o, run: "restarted")
    assert st.handle_stuck_limit(pr(7), "Bankaifan", Recorder()) == "handed over (restarted)"

    def boom(n, o, run):
        raise subprocess.CalledProcessError(1, "gh")
    monkeypatch.setattr(st, "handle_limit", boom)
    run = Recorder()
    assert st.handle_stuck_limit(pr(7), "Bankaifan", run) == "escalated"
    assert ("pr", "edit", "7", "--add-label", "needs-human") in run.calls


def test_workflows_never_ignore_limit_or_dev_on_pr():
    root = pathlib.Path(__file__).parent.parent.parent / ".github" / "workflows"
    assert "|| guard label pr" in (root / "agent-fix.yml").read_text()
    dev = (root / "agent-dev.yml").read_text()
    assert "dev-on-pr:" in dev and "github.event.issue.pull_request &&" in dev


def test_conflict_prs_skip_needs_human_and_clean():
    dirty = pr(1, mergeStateStatus="DIRTY")
    assert st.conflict_prs([dirty, pr(2), pr(3, mergeStateStatus="DIRTY", labels=["needs-human"])]) == [dirty]


def test_build_body_sections():
    job = {"workflowName": "agent-dev", "url": "r", "displayTitle": "Do it", "status": "in_progress",
           "createdAt": ago(5)}
    body = st.build_body([job], [pr(5, mergeStateStatus="DIRTY")], [issue(7)], {7: "40 min"}, None, [], [], NOW,
                         "Bankaifan")
    assert "[agent-dev](r)" in body
    assert "merge conflict" in body
    assert "- #7 Do it (agent:dev for 40 min)" in body
    assert "no run yet" in body
    assert body.count("- none") == 2


def test_update_issue_creates_or_edits():
    calls = []
    found = []

    def run(*args):
        calls.append(args)
        if args[:2] == ("issue", "list"):
            return json.dumps(found)
        if args[:2] == ("issue", "view"):
            return json.dumps({"body": "b"})
        return "https://github.com/o/r/issues/12\n"

    assert st.update_issue("b", run) == "12"
    assert calls[1][:2] == ("issue", "create")
    found.append({"number": 3, "title": st.TITLE})
    assert st.update_issue("b", run) == "3"
    assert ("issue", "edit", "3", "--body", "b") in calls
    assert ("issue", "pin", "3") in calls


def test_gate_writes_output(tmp_path):
    out = tmp_path / "o"
    st.gate({"EVENT": "schedule", "PRIVATE": "true", "GITHUB_OUTPUT": str(out)}, at(10, 37))
    assert out.read_text() == "run=false\n"


def test_gh_prints_stderr_before_raising(monkeypatch, capsys):
    def fake_run(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd, output="", stderr='Unknown JSON field: "bogus"\n')

    monkeypatch.setattr(st.subprocess, "run", fake_run)
    try:
        st.gh("pr", "list", "--json", "bogus")
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("expected CalledProcessError")
    err = capsys.readouterr().err
    assert "gh pr list exited 1" in err and "Unknown JSON field" in err


def _main_runs(*items):
    return [{"conclusion": c, "createdAt": ago(m)} for c, m in items]  # newest first


def _agent_pr(**kw):
    c = [{"authors": [{"login": "Bankaifan"}], "committedDate": ago(60)}]
    return pr(7, "agent/7-x", mergeStateStatus="BEHIND", commits=c, **kw)


def _failed(sha):
    return [{"conclusion": "failure", "createdAt": ago(50)}]


def test_pr_limit_keeps_graphql_query_small():
    assert st.PR_LIMIT <= 20


def test_pr_red_on_old_red_main_is_rebased():
    main = _main_runs(("success", 10), ("failure", 90))
    assert st.rebase_candidates([_agent_pr()], main, _failed, "Bankaifan") != []


def test_pr_red_on_green_main_is_left_alone():
    main = _main_runs(("success", 10), ("success", 90))
    assert st.rebase_candidates([_agent_pr()], main, _failed, "Bankaifan") == []


def test_no_rebase_while_main_is_red_or_for_foreign_prs():
    assert st.rebase_candidates([_agent_pr()], _main_runs(("failure", 10)), _failed, "Bankaifan") == []
    main = _main_runs(("success", 10), ("failure", 90))
    assert st.rebase_candidates([_agent_pr(isCrossRepository=True)], main, _failed, "Bankaifan") == []
    dependabot = pr(8, "dependabot/x", mergeStateStatus="BEHIND")
    assert st.rebase_candidates([dependabot], main, _failed, "Bankaifan") == []
    two = _agent_pr()
    two["commits"] = two["commits"] * 2
    assert st.rebase_candidates([two], main, _failed, "Bankaifan") == []


# --- liveness (issue #74) ----------------------------------------------------------------------

def test_escalate_fails_loudly_when_comment_missing():
    class Lossy(Recorder):
        def __call__(self, *args):
            if args[1] == "comment":
                self.calls.append(args)
                return ""  # posted "successfully" but never shows up
            return super().__call__(*args)

    with pytest.raises(st.liveness.ReadbackError):
        st.escalate("pr", 7, "stuck.", "Bankaifan", Lossy())


def test_update_issue_fails_when_body_missing():
    def run(*args):
        if args[:2] == ("issue", "list"):
            return json.dumps([{"number": 3, "title": st.TITLE}])
        if args[:2] == ("issue", "view"):
            return json.dumps({"body": "old"})
        return ""

    with pytest.raises(st.liveness.ReadbackError):
        st.update_issue("new", run)


def test_main_exits_nonzero_on_readback_failure(monkeypatch):
    def boom(env, now):
        raise st.liveness.ReadbackError("comment missing")

    monkeypatch.setattr(st, "run_status", boom)
    assert st.main(["status.py"]) == 1


def fresh():
    return {wf: {"createdAt": ago(60), "url": "u"} for wf in st.liveness.SCHEDULED}


def test_all_fresh_flags_nothing():
    run = Recorder()
    assert st.liveness.flag_overdue(fresh(), NOW, run) == ([], [])
    assert run.calls == []


def test_overdue_run_opens_one_issue_then_no_second():
    succ = fresh()
    succ["scout.yml"] = {"createdAt": ago(3 * 30 * 24 * 60), "url": "u"}
    issues = []

    def run(*args):
        if args[:2] == ("issue", "list"):
            return json.dumps(issues)
        issues.append({"number": 5, "title": args[args.index("--title") + 1]})
        assert "prio:1" in args
        return "https://github.com/o/r/issues/5\n"

    assert st.liveness.flag_overdue(succ, NOW, run) == (["scout"], ["5"])
    assert st.liveness.flag_overdue(succ, NOW, run) == (["scout"], [])
    assert len(issues) == 1


def test_never_run_is_overdue_and_listed_in_body():
    succ = fresh()
    succ["rule-keeper.yml"] = None
    assert st.liveness.overdue_runs(succ, NOW) == ["rule keeper"]
    body = st.build_body([], [], [], {}, None, [], [], NOW, "Bankaifan", succ)
    assert "- rule keeper: never OVERDUE" in body
    assert "- orchestrator: [60 min ago](u)" in body


def test_never_run_new_workflow_gets_grace_from_add_date():
    succ = fresh()
    succ["scout.yml"] = None
    # added 3 days ago, monthly interval: not overdue yet
    assert st.liveness.overdue_runs(succ, NOW, {"scout.yml": ago(3 * 24 * 60)}) == []
    # added 61 days ago: overdue
    assert st.liveness.overdue_runs(succ, NOW, {"scout.yml": ago(61 * 24 * 60)}) == ["scout"]
    body = st.build_body([], [], [], {}, None, [], [], NOW, "Bankaifan", succ, {"scout.yml": ago(60)})
    assert "- scout: never\n" in body


def test_added_dates_only_for_never_run_workflows():
    succ = fresh()
    succ["scout.yml"] = None
    calls = []

    def run(*args):
        calls.append(args)
        return "2026-11-09T10:00:00Z\n"

    assert st.liveness.added_dates(succ, run) == {"scout.yml": "2026-11-09T10:00:00Z"}
    assert len(calls) == 1 and "actions/workflows/scout.yml" in calls[0][1]


def test_merged_rows_last_24h_with_risk_label():
    now = datetime.datetime(2026, 11, 10, 12, 0, tzinfo=datetime.UTC)
    merged = [{"number": 1, "title": "new", "mergedAt": "2026-11-10T08:00:00Z", "labels": [{"name": "risk:security"}]},
              {"number": 2, "title": "old", "mergedAt": "2026-11-08T08:00:00Z", "labels": []}]
    assert st.merged_rows(merged, now) == ["- #1 new (risk:security)"]


# --- failure watch wiring (design 0008, 4.8) -------------------------------------------------------

def ago_dt(minutes):
    return NOW - datetime.timedelta(minutes=minutes)


def wire(monkeypatch, watch):
    """Prepare run_status so every gh call answers `[]`; returns (order, bodies)."""
    order, bodies = [], []
    monkeypatch.setattr(st.liveness, "last_successes", lambda run: fresh())
    monkeypatch.setattr(st.liveness, "added_dates", lambda s, run: {})
    monkeypatch.setattr(st.liveness, "flag_overdue", lambda *a: order.append("overdue") or ([], []))
    monkeypatch.setattr(st.failure_watch, "watch", lambda *a: order.append("watch") or watch(*a))
    monkeypatch.setattr(st, "previous_since", lambda run, now, bot="": ago_dt(90))
    monkeypatch.setattr(st, "update_issue", lambda body, run=None, bot="": bodies.append(body) or "1")
    return order, bodies


def empty(*args):
    return "[]"


def test_watch_runs_after_overdue_and_writes_since_line(monkeypatch):
    order, bodies = wire(monkeypatch, lambda since, now, late, key, run: (["opened failure issue #9"], ago_dt(10)))
    assert st.run_status({"GH_REPO": "o/r"}, NOW, empty) == 0
    assert order == ["overdue", "watch"]
    assert "- opened failure issue #9" in bodies[0]
    assert "Failure watch since: 2026-11-09T11:50:00Z" in bodies[0]


def test_watch_off_switch_skips_the_watch(monkeypatch):
    order, bodies = wire(monkeypatch, lambda *a: ([], NOW))
    st.run_status({"GH_REPO": "o/r", "FAILURE_WATCH": "off"}, NOW, empty)
    assert order == ["overdue"]
    assert "Failure watch since" not in bodies[0]


def test_watch_exception_does_not_stop_the_status_issue(monkeypatch, capsys):
    def boom(*a):
        raise st.liveness.ReadbackError("comment missing")

    order, bodies = wire(monkeypatch, boom)
    assert st.run_status({"GH_REPO": "o/r"}, NOW, empty) == 0
    assert order == ["overdue", "watch"] and len(bodies) == 1
    assert "failure watch failed: ReadbackError" in capsys.readouterr().out
    assert "Failure watch since: 2026-11-09T10:30:00Z" in bodies[0]  # anchor kept, nothing lost


def test_watch_skipped_when_overdue_state_unknown(monkeypatch):
    order, _ = wire(monkeypatch, lambda *a: ([], NOW))
    monkeypatch.setattr(st.liveness, "last_successes", lambda run: None)
    st.run_status({"GH_REPO": "o/r"}, NOW, empty)
    assert order == []


def test_previous_since_reads_the_status_issue_line():
    def with_line(*a):
        return json.dumps([{"title": st.TITLE, "body": f"x\n\n{st.SINCE_LABEL} 2026-11-09T09:15:00Z\n"}])

    def without_line(*a):
        return json.dumps([{"title": st.TITLE, "body": "no line"}])

    assert st.previous_since(with_line, NOW) == datetime.datetime(2026, 11, 9, 9, 15, tzinfo=UTC)
    assert st.previous_since(without_line, NOW) == NOW - datetime.timedelta(hours=24)


def test_previous_since_ignores_forged_anchors():
    def issues(author, ts):
        return lambda *a: json.dumps([{"title": st.TITLE, "author": {"login": author},
                                       "body": f"{st.SINCE_LABEL} {ts}\n"}])

    default = NOW - datetime.timedelta(hours=24)
    assert st.previous_since(issues("mallory", "2026-11-09T09:15:00Z"), NOW, "bot") == default  # foreign author
    assert st.previous_since(issues("bot", "9999-01-01T00:00:00Z"), NOW, "bot") == NOW  # future: clamped
    assert st.previous_since(issues("bot", "2000-01-01T00:00:00Z"), NOW, "bot") == default  # too old: clamped
    assert st.previous_since(issues("bot", "2026-11-09T09:15:00Z"), NOW, "bot") == datetime.datetime(
        2026, 11, 9, 9, 15, tzinfo=UTC)


def test_update_issue_ignores_foreign_status_issue():
    calls = []

    def run(*args):
        calls.append(args)
        if args[:2] == ("issue", "list"):
            return json.dumps([{"number": 5, "title": st.TITLE, "author": {"login": "mallory"}}])
        if args[:2] == ("issue", "view"):
            return json.dumps({"body": "b"})
        return "https://github.com/o/r/issues/12\n"

    assert st.update_issue("b", run, "bot") == "12"


def test_status_workflow_passes_failure_watch_switch_in_script_step():
    text = (pathlib.Path(__file__).parent.parent.parent / ".github/workflows/status.yml").read_text(encoding="utf-8")
    assert "FAILURE_WATCH: ${{ vars.FAILURE_WATCH }}" in text
