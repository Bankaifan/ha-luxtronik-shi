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


# --- all events (design 0007) ---

AUTHOR, APPROVER = "author-app[bot]", "approver-app[bot]"
EVENT_NAMES = ("issues", "issue_comment", "pull_request", "pull_request_target", "pull_request_review")


def ev(event="issue_comment", sender="Bankaifan", live="Bankaifan", runs=(), run_id=100, **kw):
    kw.setdefault("enabled", True)
    return g.decide(event, "", sender, "Bankaifan", run_id, list(runs), T0, action="created",
                    author_bot=AUTHOR, approver_bot=APPROVER, live=live, **kw)


def erun(run_id, at, status="completed", sender="Bankaifan", end=None):
    return {"databaseId": run_id, "createdAt": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": status,
            "updatedAt": (end or at).strftime("%Y-%m-%dT%H:%M:%SZ"), "sender": sender}


def test_owner_and_both_apps_are_accepted_for_every_event():
    for event in EVENT_NAMES:
        for who in ("Bankaifan", AUTHOR, APPROVER):
            assert ev(event, sender=who, live=who)[0], (event, who)


def test_other_senders_are_refused_for_every_event():
    for event in EVENT_NAMES:
        for who in ("mallory", "", "someone-app[bot]"):
            assert not ev(event, sender=who, live=who)[0], (event, who)


def test_events_are_off_unless_enabled():
    assert not ev(enabled=False)[0]


def test_live_author_must_equal_sender():
    assert not ev(live="mallory")[0]
    assert not ev(live=None)[0]


def test_burst_of_three_events_gives_one_run_on_the_last():
    runs = [erun(100, T0, "queued"), erun(101, T0, "queued"), erun(102, T0, "queued")]
    assert not ev(run_id=100, runs=runs)[0]
    assert not ev(run_id=101, runs=runs)[0]
    assert ev(run_id=102, runs=runs)[0]


def test_earlier_finished_run_does_not_block_the_last_event():
    assert ev(run_id=101, runs=[erun(100, T0 - timedelta(seconds=30)), erun(101, T0, "in_progress")])[0]


def test_app_event_inside_a_run_window_is_ignored():
    runs = [erun(99, T0 - timedelta(minutes=5), end=T0 - timedelta(seconds=30)), erun(100, T0, "queued")]
    assert not ev(sender=AUTHOR, live=AUTHOR, runs=runs)[0]  # ended 30 s ago, inside the 60 s grace
    assert not ev(sender=AUTHOR, live=AUTHOR, runs=[erun(99, T0 - timedelta(minutes=5), "in_progress")])[0]


def test_app_event_after_the_window_or_by_other_senders_passes():
    old = [erun(99, T0 - timedelta(minutes=5), end=T0 - timedelta(minutes=2))]
    assert ev(sender=AUTHOR, live=AUTHOR, runs=old)[0]
    busy = [erun(99, T0 - timedelta(minutes=5), "in_progress")]
    assert ev(sender="Bankaifan", runs=busy)[0]
    assert ev(sender=APPROVER, live=APPROVER, runs=busy)[0]


def test_event_time_decides_the_window_not_now():
    runs = [erun(99, T0 - timedelta(minutes=30), end=T0 - timedelta(minutes=29))]
    at = T0 - timedelta(minutes=29, seconds=-20)
    assert not ev(sender=AUTHOR, live=AUTHOR, runs=runs, event_at=at)[0]


def test_brake_refuses_three_author_runs_in_five_minutes_each():
    runs = [erun(98, T0 - timedelta(minutes=8), sender=AUTHOR), erun(99, T0 - timedelta(minutes=4), sender=AUTHOR),
            erun(100, T0, "in_progress", sender=AUTHOR)]
    ok, reason = ev(sender=AUTHOR, live=AUTHOR, runs=runs)
    assert not ok and reason.startswith("brake")


def test_brake_needs_all_three_close_and_from_the_author_app():
    far = [erun(98, T0 - timedelta(minutes=30), sender=AUTHOR), erun(99, T0 - timedelta(minutes=4), sender=AUTHOR),
           erun(100, T0, "in_progress", sender=AUTHOR)]
    assert ev(sender=AUTHOR, live=AUTHOR, runs=far)[0]
    mixed = [erun(98, T0 - timedelta(minutes=8), sender="Bankaifan"), far[1], far[2]]
    assert ev(sender=AUTHOR, live=AUTHOR, runs=mixed)[0]


def test_label_path_is_unchanged_with_event_kwargs():
    assert g.decide("issues", "approved", "Bankaifan", "Bankaifan", 100, [], T0, author_bot=AUTHOR)[0]
    assert not g.decide("issues", "approved", AUTHOR, "Bankaifan", 100, [], T0, author_bot=AUTHOR)[0]


def fake_gh(payload):
    def run(*args):
        if payload is None:
            raise g.subprocess.CalledProcessError(1, "gh")
        return g.json.dumps(payload)
    return run


ENV = {"GH_REPO": "o/r", "NUMBER": "5", "COMMENT_ID": "9", "REVIEW_ID": "7", "SENDER": "Bankaifan"}


def test_live_login_reads_the_comment_author_not_the_payload():
    assert g.live_login("issue_comment", "created", ENV, fake_gh({"id": 9, "user": {"login": "mallory"}})) == "mallory"
    assert g.live_login("pull_request_review", "submitted", ENV, fake_gh({"id": 7, "user": {"login": "x"}})) == "x"
    assert g.live_login("issues", "opened", ENV, fake_gh({"number": 5, "user": {"login": "y"}})) == "y"


def test_live_login_is_none_when_the_object_is_gone():
    assert g.live_login("issue_comment", "created", ENV, fake_gh(None)) is None
    assert g.live_login("issue_comment", "created", ENV, fake_gh({})) is None


def test_live_login_for_edited_or_closed_items_needs_only_existence():
    assert g.live_login("issues", "edited", ENV, fake_gh({"number": 5, "user": {"login": "z"}})) == "Bankaifan"
    assert g.live_login("pull_request", "closed", ENV, fake_gh(None)) is None


def test_brake_comments_once():
    calls = []

    def run(*args):
        calls.append(args)
        return g.json.dumps({"comments": [{"body": g.BRAKE_MARK + " x"}] if len(calls) > 1 else []})

    g.announce_brake("3", run)
    assert calls[-1][1] == "comment"
    calls.clear()
    calls.append(())
    g.announce_brake("3", run)
    assert all(c[:2] != ("issue", "comment") for c in calls)
    g.announce_brake("", run)
