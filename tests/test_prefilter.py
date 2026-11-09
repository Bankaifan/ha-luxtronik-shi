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
