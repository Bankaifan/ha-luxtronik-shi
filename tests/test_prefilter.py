import importlib.util
import pathlib

_path = pathlib.Path(__file__).parent.parent / "tools" / "prefilter.py"
_spec = importlib.util.spec_from_file_location("prefilter", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def item(number, labels=(), approved=False, auto_ok=False):
    return {"number": number, "labels": list(labels), "approved": approved, "auto_ok": auto_ok}


def test_startable_skips_started_and_unapproved_ideas():
    trusted = [item(1), item(2, ["agent:dev"]), item(3, ["idea"]), item(4, ["idea"], approved=True)]
    assert mod.startable(trusted, 0) == [1, 4]


def test_startable_empty_when_dev_slots_full():
    assert mod.startable([item(1)], 2) == []


def test_no_free_pr_slot_means_nothing_to_start():
    # Issue #313: candidates existed but MAX_PRS was full; the model started nothing, and STARTABLE=true with no
    # visible action made the guard fail the run.
    assert mod.start_candidates([item(1)], 0, 0) == []
    assert mod.start_candidates([item(1)], 0, 1) == [1]
    assert mod.start_candidates([item(1)], 2, 1) == []


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


def test_prio1_may_start_when_a_slot_is_stuck():
    p1 = dict(item(7, ["prio:1"]), prio=1)
    p3 = dict(item(8), prio=3)
    assert mod.startable([p1, p3], 2) == []
    assert mod.startable([p1, p3], 2, stuck=1) == [7]
    assert mod.startable([p1, p3], 2, stuck=2) == [7]


def test_waiting_issue_frees_its_dev_slot():
    assert mod.startable([item(1)], 2) == []
    assert mod.startable([item(1)], 2, waiting=1) == [1]
    assert mod.free_slots(2, 3, 1, 1) == (1, 1)
    assert mod.free_slots(2, 3, 0, 0) == (0, 0)


def test_five_waiting_prs_hold_new_security_slips_only():
    sec, plain = item(1, ["risk:security"]), item(2)
    assert mod.startable([sec, plain], 0, waiting_prs=4) == [1, 2]
    assert mod.startable([sec, plain], 0, waiting_prs=5) == [2]


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
    assert (fresh.MAX_DEV, fresh.MAX_PRS) == (2, 3)


def test_caps_default_when_empty_or_blank(monkeypatch):
    fresh = load_with_env(monkeypatch, MAX_DEV="", MAX_PRS="  ")
    assert (fresh.MAX_DEV, fresh.MAX_PRS) == (2, 3)


def test_caps_override_and_slot_arithmetic_follows(monkeypatch):
    fresh = load_with_env(monkeypatch, MAX_DEV="4", MAX_PRS="5")
    assert (fresh.MAX_DEV, fresh.MAX_PRS) == (4, 5)
    assert fresh.free_slots(3, 5, 0, 0) == (1, 0)
    assert fresh.free_slots(3, 4, 0, 0) == (1, 1)
    assert fresh.startable([item(1)], 3) == [1]
    assert mod.startable([item(1)], 3) == []


def test_non_numeric_cap_falls_back_with_warning(monkeypatch, capsys):
    fresh = load_with_env(monkeypatch, MAX_DEV="four", MAX_PRS="3.5")
    assert (fresh.MAX_DEV, fresh.MAX_PRS) == (2, 3)
    err = capsys.readouterr().err
    assert "MAX_DEV" in err and "MAX_PRS" in err


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
