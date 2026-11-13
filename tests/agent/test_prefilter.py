import importlib.util
import json
import pathlib

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "prefilter.py"
_spec = importlib.util.spec_from_file_location("prefilter", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def item(number, labels=(), approved=False, auto_ok=False):
    return {"number": number, "labels": list(labels), "approved": approved, "auto_ok": auto_ok}


def test_startable_skips_started_and_unapproved_ideas():
    trusted = [item(1), item(2, ["agent:dev"]), item(3, ["idea"]), item(4, ["idea"], approved=True)]
    assert mod.startable(trusted, 4) == [1, 4]


def test_startable_empty_when_dev_slots_full():
    assert mod.startable([item(1)], 0) == []


def test_no_free_pr_slot_means_nothing_to_start():
    # Issue #313: candidates existed but MAX_PRS was full; the model started nothing, and STARTABLE=true with no
    # visible action made the guard fail the run.
    assert mod.start_candidates([item(1)], 1, 0) == []
    assert mod.start_candidates([item(1)], 1, 1) == [1]
    assert mod.start_candidates([item(1)], 0, 1) == []


def test_handover_stale():
    assert mod.handover_stale(8, 3, 7)
    assert not mod.handover_stale(8, 0, 7)
    assert not mod.handover_stale(2, 5, 7)


def test_orchestrator_work():
    assert not mod.orchestrator_work([], 0, False)
    assert mod.orchestrator_work([1], 0, False)
    assert mod.orchestrator_work([], 1, False)
    assert mod.orchestrator_work([], 0, True)


def test_scout_work():
    assert mod.scout_work(0, 3)
    assert not mod.scout_work(0, 0)
    assert not mod.scout_work(mod.MAX_OPEN_IDEAS, 3)


def test_parked_or_done_issue_frees_its_slot_for_every_priority():
    # Downstream: two parked agent:dev issues ate both slots (dev_open=3, MAX_DEV=2) and nothing below prio:1 started.
    p3 = dict(item(8, ["prio:3"]), prio=3)
    free_dev, _ = mod.free_slots({1, 2, 3, 4, 5}, set(), {1, 2}, 0, 0)
    assert free_dev == 1
    assert mod.start_candidates([p3], free_dev, 1) == [8]
    assert mod.free_slots({1, 2, 3, 4, 5}, set(), set(), 0, 0)[0] == 0


def test_waiting_issue_frees_its_dev_slot():
    assert mod.free_slots({1, 2, 3, 4}, {1}, set(), 5, 1) == (1, 1)
    assert mod.free_slots({1, 2, 3, 4}, set(), set(), 5, 0) == (0, 0)


def test_waiting_and_stuck_overlap_is_not_counted_twice():
    assert mod.free_slots({1, 2, 3, 4, 5}, {1}, {1, 2}, 0, 0)[0] == 1
    assert mod.free_slots({1, 2}, {1, 9}, {1, 8}, 0, 0)[0] == 3


def test_blocked_issue_is_no_candidate():
    assert mod.startable([item(1), item(2)], 4, blocked={1}) == [2]
    assert mod.startable([item(1), item(2)], 4) == [1, 2]


def test_start_is_cut_to_the_free_slots_in_list_order():
    trusted = [item(7), item(3), item(9)]
    assert mod.start_candidates(trusted, 2, 5) == [7, 3]
    assert mod.start_candidates(trusted, 4, 5) == [7, 3, 9]
    assert mod.start_candidates(trusted, 4, 1) == [7]  # the PR cap bounds the starts too


def test_five_waiting_prs_hold_new_security_slips_only():
    sec, plain = item(1, ["risk:security"]), item(2)
    assert mod.startable([sec, plain], 4, waiting_prs=4) == [1, 2]
    assert mod.startable([sec, plain], 4, waiting_prs=5) == [2]


def test_closing_issues():
    assert mod.closing_issues("Closes #172\nRefs #5") == {172, 5}


def load_with_env(monkeypatch, **env):
    """Import prefilter fresh with MAX_DEV/MAX_PRS set as given (unset when not passed)."""
    for name in ("MAX_DEV", "MAX_PRS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    spec = importlib.util.spec_from_file_location("prefilter_env", _path)
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)
    return fresh


def test_caps_default_when_unset(monkeypatch):
    fresh = load_with_env(monkeypatch)
    assert (fresh.MAX_DEV, fresh.MAX_PRS) == (4, 5)


def test_caps_default_when_empty_or_blank(monkeypatch):
    fresh = load_with_env(monkeypatch, MAX_DEV="", MAX_PRS="  ")
    assert (fresh.MAX_DEV, fresh.MAX_PRS) == (4, 5)


def test_caps_override_and_slot_arithmetic_follows(monkeypatch):
    fresh = load_with_env(monkeypatch, MAX_DEV="2", MAX_PRS="3")
    assert (fresh.MAX_DEV, fresh.MAX_PRS) == (2, 3)
    assert fresh.free_slots({1}, set(), set(), 3, 0) == (1, 0)
    assert fresh.free_slots({1}, set(), set(), 2, 0) == (1, 1)
    assert mod.free_slots({1}, set(), set(), 3, 0) == (3, 2)


def test_non_numeric_cap_falls_back_with_warning(monkeypatch, capsys):
    fresh = load_with_env(monkeypatch, MAX_DEV="four", MAX_PRS="3.5")
    assert (fresh.MAX_DEV, fresh.MAX_PRS) == (4, 5)
    err = capsys.readouterr().err
    assert "MAX_DEV" in err and "MAX_PRS" in err


def run_main(monkeypatch, tmp_path, dev, bodies, trusted, merged=(), waiting=(), max_dev="2"):
    """Run main('orchestrator') with a fake gh. DEV: {number: labels} of open agent:dev issues, BODIES: {number: body}
    of all open issues, MERGED: issue numbers a merged PR refers to. Returns the GITHUB_OUTPUT lines as a dict."""
    fresh = load_with_env(monkeypatch, MAX_DEV=max_dev)

    def gh(*args):
        if args[:2] == ("issue", "list") and "agent:dev" in args:
            return json.dumps([{"number": n, "labels": [{"name": x} for x in labs]} for n, labs in dev.items()])
        if args[:2] == ("issue", "list"):
            assert args[-1] == "number,body"
            return json.dumps([{"number": n, "body": b} for n, b in bodies.items()])
        if "merged" in args:
            n = int(args[args.index("--search") + 1].split()[0][1:])
            return json.dumps([{"number": 90, "body": f"Refs #{n}", "headRefName": "agent/9-x"}] if n in merged else [])
        return "[]"

    out = tmp_path / "out"
    monkeypatch.setattr(fresh, "gh", gh)
    monkeypatch.setattr(fresh, "waiting_for_owner", lambda owner, approver: (set(waiting), len(waiting)))
    monkeypatch.setattr(fresh, "handover_state", lambda: (0, 0))
    monkeypatch.setenv("TRUSTED", json.dumps(trusted))
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.delenv("EVENT", raising=False)
    assert fresh.main("orchestrator") == 0
    return dict(line.split("=", 1) for line in out.read_text().splitlines())


def test_main_parked_and_done_issues_free_slots_for_prio3(monkeypatch, tmp_path):
    dev = {10: ["agent:dev", "needs-human"], 11: ["agent:dev"], 12: ["agent:dev"]}
    trusted = [dict(item(20, ["prio:3"]), prio=3), dict(item(21, ["prio:3"]), prio=3)]
    bodies = dict.fromkeys((10, 11, 12, 20, 21), "")
    out = run_main(monkeypatch, tmp_path, dev, bodies, trusted, merged={11})
    assert (out["free_dev"], out["start"], out["startable"], out["work"]) == ("1", "20", "true", "true")
    out = run_main(monkeypatch, tmp_path, dev, bodies, trusted, merged={11}, waiting={10})
    assert out["free_dev"] == "1"


def test_main_no_free_slot_writes_empty_start(monkeypatch, tmp_path):
    dev = {11: ["agent:dev"], 12: ["agent:dev"]}
    out = run_main(monkeypatch, tmp_path, dev, dict.fromkeys((11, 12, 20), ""), [item(20)])
    assert (out["free_dev"], out["start"], out["startable"]) == ("0", "", "false")


def test_main_holds_back_an_issue_until_its_dependency_closes(monkeypatch, tmp_path, capsys):
    trusted = [item(20), item(21), item(22), item(23)]
    bodies = {19: "", 20: "Design: docs/design/0001-x.md\nDepends on: #19, #21\n\nSlip", 21: "Depends on: #21",
              22: "", 23: ""}
    out = run_main(monkeypatch, tmp_path, {}, bodies, trusted, max_dev="4")
    assert out["start"] == "21,22,23"
    assert "blocked=[20]" in capsys.readouterr().out
    del bodies[19], bodies[21]
    out = run_main(monkeypatch, tmp_path, {}, bodies, trusted[:1] + trusted[2:], max_dev="2")
    assert out["start"] == "20,22"


def facts(**over):
    base = {"startable": False, "needs_human": False, "agent_dev": False, "linked_open_pr": False, "trusted": False,
            "receiver_marker": False, "agent_pr": False, "design_pr": False, "closing": set(),
            "closing_agent_dev": False, "merged": False, "free_prs": 2, "review_state": "", "sender_is_owner": False,
            "reviewer_ok": False}
    return dict(base, **over)


def reason(event, action, **over):
    return mod.event_reason(event, action, facts(**over))


def test_event_without_row_keeps_count_rule():
    for ev, act in (("schedule", ""), ("workflow_dispatch", ""), ("workflow_run", "completed")):
        assert reason(ev, act) is None


def test_event_issue_opened_edited_labeled():
    for act in ("opened", "edited", "labeled"):
        assert reason("issues", act, startable=True) == (True, "startable-issue")
        assert reason("issues", act, needs_human=True, sender_is_owner=True) == (True, "owner-reply")
        assert reason("issues", act, needs_human=True) == (False, "no-match")


def test_event_issue_closed():
    assert reason("issues", "closed", agent_dev=True) == (True, "cleanup-closed-issue")
    assert reason("issues", "closed", linked_open_pr=True) == (True, "cleanup-closed-issue")
    assert reason("issues", "closed") == (False, "no-match")


def test_event_comment_created():
    assert reason("issue_comment", "created", sender_is_owner=True, needs_human=True) == (True, "owner-answer")
    assert reason("issue_comment", "created", sender_is_owner=True, trusted=True) == (True, "owner-comment-trusted")
    assert reason("issue_comment", "created", sender_is_owner=True, needs_human=True,
                  receiver_marker=True) == (False, "no-match")
    assert reason("issue_comment", "created", needs_human=True, trusted=True) == (False, "no-match")


def test_event_pr_opened():
    assert reason("pull_request", "opened", agent_pr=True, free_prs=0) == (True, "pr-over-cap")
    assert reason("pull_request", "opened", agent_pr=True, design_pr=True) == (True, "design-pr")
    assert reason("pull_request", "opened") == (True, "unlinked-pr")
    assert reason("pull_request", "opened", agent_pr=True) == (False, "no-match")


def test_event_pr_closed():
    assert reason("pull_request", "closed", merged=True, closing_agent_dev=True) == (True, "merged-pr")
    assert reason("pull_request", "closed", merged=True, design_pr=True) == (True, "merged-pr")
    assert reason("pull_request", "closed", closing={5}) == (True, "closed-unmerged-pr")
    assert reason("pull_request", "closed", merged=True) == (False, "no-match")
    assert reason("pull_request", "closed") == (False, "no-match")


def test_event_review_submitted():
    ok = {"agent_pr": True, "reviewer_ok": True}
    assert reason("pull_request_review", "submitted", review_state="APPROVED", **ok) == (True, "review")
    assert reason("pull_request_review", "submitted", review_state="CHANGES_REQUESTED", **ok) == (True, "review")
    assert reason("pull_request_review", "submitted", review_state="COMMENTED", **ok) == (False, "no-match")
    assert reason("pull_request_review", "submitted", review_state="APPROVED", agent_pr=True) == (False, "no-match")
    assert reason("pull_request_review", "submitted", review_state="APPROVED", reviewer_ok=True) == (False, "no-match")


def test_only_agent_prs_mark_an_issue_done(monkeypatch):
    """Anyone can write `Refs #N` into a PR body: a foreign or fork PR must not free a slot."""
    prs = [{"number": 1, "body": "Refs #7", "headRefName": "patch-1"},
           {"number": 2, "body": "Refs #7", "headRefName": "agent/7-x", "isCrossRepository": True}]
    monkeypatch.setattr(mod, "gh", lambda *a: json.dumps(prs))
    assert mod.stuck_slots([{"number": 7, "labels": []}]) == set()
    prs.append({"number": 3, "body": "Refs #7", "headRefName": "agent/7-x"})
    assert mod.stuck_slots([{"number": 7, "labels": []}]) == {7}


def test_dispatch_model_work_is_only_slipless_issues_needs_human_or_handover():
    assert mod.orchestrator_work([1, 2], 0, False)  # dispatcher off: any candidate is model work
    assert not mod.orchestrator_work([1, 2], 0, False, needs_slip=[])
    assert mod.orchestrator_work([1, 2], 0, False, needs_slip=[2])
    assert mod.orchestrator_work([1], 1, False, needs_slip=[])
    assert mod.orchestrator_work([1], 0, True, needs_slip=[])


def test_dispatch_merged_pr_event_does_not_wake_the_model_except_designs():
    assert reason("pull_request", "closed", merged=True, closing_agent_dev=True, dispatch=True) == (False, "no-match")
    assert reason("pull_request", "closed", merged=True, design_pr=True, dispatch=True) == (True, "merged-pr")
    assert reason("pull_request", "closed", merged=True, closing_agent_dev=True) == (True, "merged-pr")


def test_needs_slip_counts_issues_without_a_trusted_slip(monkeypatch):
    issues = {
        1: {"body": "Files: a.py", "author": {"login": "Bankaifan"}, "comments": []},
        2: {"body": "do it", "author": {"login": "Bankaifan"}, "comments": []},
        3: {"body": "Files: b.py", "author": {"login": "stranger"}, "comments": []},
    }
    monkeypatch.setattr(mod, "gh", lambda *a: json.dumps(issues[int(a[2])]))
    assert mod.needs_slip([1, 2, 3]) == [2, 3]


def test_handover_done_today(monkeypatch):
    calls = []
    monkeypatch.setattr(mod, "gh", lambda *a: calls.append(a) or json.dumps([{"number": 5}]))
    assert mod.handover_done_today()
    assert "head:agent/orchestrator-handover-" in calls[0][calls[0].index("--search") + 1]
    monkeypatch.setattr(mod, "gh", lambda *a: "[]")
    assert not mod.handover_done_today()
