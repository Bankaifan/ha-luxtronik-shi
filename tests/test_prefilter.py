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
