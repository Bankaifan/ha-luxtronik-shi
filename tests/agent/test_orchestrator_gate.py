from datetime import UTC, datetime, timedelta

import orchestrator_gate as g

T0 = datetime(2026, 11, 9, 10, 0, 0, tzinfo=UTC)


def test_non_repo_events_pass_through():
    for event in ("schedule", "workflow_dispatch", "workflow_run"):
        assert g.decide(event, "", "Bankaifan", 100, [], T0)[0]


def test_a_label_event_gets_no_rule_of_its_own():
    assert not g.decide("issues", "Bankaifan", "Bankaifan", 100, [], T0)[0]  # ORCHESTRATOR_EVENTS is not on


# --- all events (design 0007) ---

AUTHOR, APPROVER = "author-app[bot]", "approver-app[bot]"
EVENT_NAMES = ("issues", "issue_comment", "pull_request", "pull_request_target", "pull_request_review")


def ev(event="issue_comment", sender="Bankaifan", live="Bankaifan", runs=(), run_id=100, **kw):
    kw.setdefault("enabled", True)
    return g.decide(event, sender, "Bankaifan", run_id, list(runs), T0,
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


def test_main_skips_softly_when_the_run_list_is_rate_limited(monkeypatch, capsys):
    def limited(repo):
        raise g.subprocess.CalledProcessError(1, "gh", stderr="API rate limit exceeded")

    monkeypatch.setattr(g.budget, "low", lambda *a: "")
    monkeypatch.setattr(g, "fetch_runs", limited)
    for k, v in {"EVENT": "pull_request_review", "SENDER": "Bankaifan", "RUN_ID": "5", "GH_REPO": "o/r"}.items():
        monkeypatch.setenv(k, v)
    assert g.main() == 0
    assert capsys.readouterr().out.strip() == "false"


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


def test_a_guard_signed_issue_opened_inside_a_run_window_is_no_echo():
    """agent-template #745: the status run opened it under the author app while another orchestrator run was near; the
    gate dropped the event as an echo and the issue waited for the next scheduled run."""
    busy = [erun(99, T0 - timedelta(minutes=5), "in_progress")]
    assert not ev("issues", sender=AUTHOR, live=AUTHOR, runs=busy)[0]
    assert ev("issues", sender=AUTHOR, live=AUTHOR, runs=busy, signed=True)[0]
    pending = [*busy, erun(101, T0, "queued")]
    assert not ev("issues", sender=AUTHOR, live=AUTHOR, runs=pending, signed=True)[0]  # the debounce still holds
    three = [erun(n, T0 + timedelta(seconds=60 * (n - 98)), sender=AUTHOR) for n in (98, 99, 100)]
    assert ev("issues", sender=AUTHOR, live=AUTHOR, runs=three, signed=True)[1].startswith("brake")  # and the brake


def test_signed_issue_needs_the_opened_event_the_key_and_a_signature_that_verifies():
    title, key = "Overdue scheduled run: weekly summary", "k3y"
    body = g.guard_mark.sign(title, "The scheduled run has no successful run.", key)
    env = {"EVENT": "issues", "EVENT_ACTION": "opened", "GH_REPO": "o/r", "NUMBER": "745", "GUARD_KEY": key}

    def issue(text):
        return lambda *a: g.json.dumps({"number": 745, "title": title, "body": text})

    assert g.signed_issue(env, issue(body))
    assert not g.signed_issue(env, issue(body.replace("no successful", "one successful")))
    assert not g.signed_issue(env, issue("plain text"))
    assert not g.signed_issue({**env, "GUARD_KEY": ""}, issue(body))
    assert not g.signed_issue({**env, "GUARD_KEY": "other"}, issue(body))
    assert not g.signed_issue({**env, "EVENT_ACTION": "edited"}, issue(body))
    assert not g.signed_issue({**env, "EVENT": "issue_comment"}, issue(body))

    def gone(*a):
        raise g.subprocess.CalledProcessError(1, "gh")

    assert not g.signed_issue(env, gone)


def test_main_reads_the_signed_flag_only_for_an_opened_issue(monkeypatch, capsys):
    busy = [{"databaseId": 4, "createdAt": "2020-01-01T00:00:00Z", "updatedAt": "2020-01-01T00:00:00Z",
             "status": "in_progress", "event": "issues", "sender": AUTHOR}]
    monkeypatch.setattr(g.budget, "low", lambda *a: "")
    monkeypatch.setattr(g, "fetch_runs", lambda repo: busy)
    monkeypatch.setattr(g, "live_login", lambda *a: AUTHOR)
    base = {"EVENT": "issues", "SENDER": AUTHOR, "AUTHOR_BOT": AUTHOR, "RUN_ID": "5", "GH_REPO": "o/r",
            "ORCHESTRATOR_EVENTS": "on", "SIGNED": "true"}
    for action, want in (("opened", "true"), ("edited", "false")):
        for k, v in {**base, "EVENT_ACTION": action}.items():
            monkeypatch.setenv(k, v)
        assert g.main() == 0
        assert capsys.readouterr().out.strip() == want, action
    monkeypatch.setenv("EVENT_ACTION", "opened")
    monkeypatch.setenv("SIGNED", "")
    assert g.main() == 0 and capsys.readouterr().out.strip() == "false"
