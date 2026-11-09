from datetime import UTC, datetime, timedelta

import orchestrator_gate as g

T0 = datetime(2026, 11, 9, 10, 0, 0, tzinfo=UTC)


def run(run_id, at):
    return {"databaseId": run_id, "createdAt": at.strftime("%Y-%m-%dT%H:%M:%SZ")}


def decide(label="approved", sender="Bankaifan", event="issues", runs=(), run_id=100, now=T0):
    return g.decide(event, label, sender, "Bankaifan", run_id, list(runs), now)


def test_owner_label_runs_when_no_recent_run():
    assert decide()[0]


def test_auto_ok_by_owner_runs():
    assert decide(label="auto-ok")[0]


def test_other_labels_do_not_start_the_orchestrator():
    for label in ("agent:dev", "prio:1", "idea", ""):
        assert not decide(label=label)[0]


def test_label_by_stranger_is_refused():
    assert not decide(sender="mallory")[0]


def test_owner_in_any_login_form_runs():
    for form in ("app/Bankaifan", "Bankaifan[bot]", "bankaifan"):
        assert decide(sender=form)[0]


def test_empty_sender_is_refused():
    assert not decide(sender="")[0]


def test_non_label_events_pass_through():
    for event in ("schedule", "workflow_dispatch", "workflow_run"):
        assert decide(event=event, label="", sender="")[0]


def test_burst_of_labels_gives_one_run():
    # Run 100 started first; 101 and 102 were created within three minutes after it.
    runs = [run(100, T0), run(101, T0 + timedelta(seconds=40)), run(102, T0 + timedelta(seconds=90))]
    assert decide(run_id=100, runs=runs, now=T0)[0]
    assert not decide(run_id=101, runs=runs, now=T0 + timedelta(seconds=40))[0]
    assert not decide(run_id=102, runs=runs, now=T0 + timedelta(seconds=90))[0]


def test_run_after_the_window_passes():
    runs = [run(100, T0), run(101, T0 + timedelta(minutes=4))]
    assert decide(run_id=101, runs=runs, now=T0 + timedelta(minutes=4))[0]


def test_window_edge_is_inclusive():
    runs = [run(100, T0), run(101, T0 + timedelta(seconds=g.WINDOW))]
    assert not decide(run_id=101, runs=runs)[0]


def test_later_run_does_not_debounce_an_earlier_one():
    runs = [run(100, T0), run(101, T0 + timedelta(seconds=10))]
    assert decide(run_id=100, runs=runs)[0]


def test_schedule_run_within_window_debounces_a_label_run():
    # A scheduled run is an earlier run too: it already read the candidate list.
    runs = [run(99, T0 - timedelta(seconds=30)), run(100, T0)]
    assert not decide(run_id=100, runs=runs)[0]


def test_missing_own_run_falls_back_to_now():
    runs = [run(90, T0 - timedelta(minutes=10))]
    assert decide(run_id=100, runs=runs, now=T0)[0]
