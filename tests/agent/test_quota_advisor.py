"""Quota advisor (design 0014): model runs per workflow, queue, and the Capacity proposal threshold. Fake gh only."""
import datetime
import importlib.util
import json
import pathlib
import subprocess

import run_stats as rs

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "weekly_summary.py"
_spec = importlib.util.spec_from_file_location("weekly_summary", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

NOW = datetime.datetime(2026, 11, 9, 12, 0, tzinfo=datetime.UTC)
TODAY = datetime.date(2026, 11, 9)  # window: 2026-11-02 .. 2026-11-09
MODEL = [{"steps": [{"name": "Run claude", "conclusion": "success"}]}]
WORKFLOW_YML = pathlib.Path(__file__).parent.parent.parent / ".github" / "workflows" / "weekly-summary.yml"


def run_(id_, conclusion="success", day=8):
    return {"databaseId": id_, "conclusion": conclusion, "createdAt": f"2026-11-{day:02d}T08:00:00Z",
            "startedAt": "2026-11-08T08:00:00Z", "updatedAt": "2026-11-08T08:04:00Z"}


def make_gh(runs, jobs, logs, issues, prs, found=(), created_url="https://github.com/o/r/issues/77", calls=None):
    """Fake gh. Records every call in `calls`; stores the body of the last create/edit for `issue view`."""
    state = {"body": None}
    calls = [] if calls is None else calls

    def run(*args):
        calls.append(args)
        if args[:2] == ("run", "list"):
            return json.dumps(runs.get(args[args.index("--workflow") + 1], []))
        if args[:2] == ("run", "view"):
            return logs.get(int(args[2]), "")
        if args[0] == "api":
            return json.dumps({"jobs": jobs.get(int(args[1].split("/")[-2]), [])})
        if args[:2] == ("issue", "list"):
            return json.dumps(list(found) if "--search" in args else issues)
        if args[:2] == ("pr", "list"):
            return json.dumps(prs)
        if args[:2] in (("issue", "create"), ("issue", "edit")):
            state["body"] = args[args.index("--body") + 1]
            return "" if args[1] == "edit" else created_url + "\n"
        if args[:2] == ("issue", "view"):
            return json.dumps({"body": state["body"]})
        raise AssertionError(f"unexpected gh call {args}")
    return run


def only_claude(monkeypatch, files):
    monkeypatch.setattr(mod.run_stats, "claude_workflows", lambda *a, **k: files)


def test_claude_workflows_finds_only_claude_files(tmp_path):
    (tmp_path / "a.yml").write_text("uses: anthropics/claude-code-action@x\n", encoding="utf-8")
    (tmp_path / "b.yml").write_text("run: echo hi\n", encoding="utf-8")
    assert rs.claude_workflows(tmp_path) == ["a.yml"]


def test_limit_pattern_matches_limit_and_rate_errors_only():
    assert rs.LIMIT_RE.search("Error: Claude AI usage limit reached")
    assert rs.LIMIT_RE.search("HTTP 429 Too Many Requests")
    assert rs.LIMIT_RE.search("rate_limit_error")
    assert not rs.LIMIT_RE.search("3 tests failed, 0 errors, overloaded host")


def test_workflow_stats_counts_days_failures_and_limit_errors():
    runs = [run_(1, day=8), run_(2, day=8, conclusion="failure"), run_(3, day=9, conclusion="failure"),
            run_(4, day=9, conclusion="skipped"), run_(5, day=1)]  # 4 skipped, 5 outside the window
    jobs = {1: MODEL, 2: MODEL, 3: MODEL, 4: MODEL, 5: MODEL}
    logs = {2: "Error: usage limit reached", 3: "tests failed"}
    result = rs.workflow_stats(runs, jobs.__getitem__, logs.__getitem__, now=NOW)
    assert result["model_runs"] == 3
    assert result["per_day"] == {"2026-11-08": 2, "2026-11-09": 1}
    assert (result["failed"], result["limit_failed"]) == (2, 1)
    assert result["median_min"] == 4.0


def test_workflow_stats_without_model_runs():
    result = rs.workflow_stats([run_(1)], lambda i: [{"steps": None}], lambda i: "", now=NOW)
    assert result["model_runs"] == 0 and result["median_min"] is None


def test_fetch_all_filters_by_date_and_reads_failed_log():
    calls = []

    def fake(*a):
        calls.append(a)
        if a[:2] == ("run", "list"):
            return json.dumps([run_(7)])
        if a[:2] == ("run", "view"):
            return "log text"
        return json.dumps({"jobs": MODEL})
    runs, jobs_of, log_of = rs.fetch_all(["scout.yml"], "2026-11-02", repo="o/r", run=fake)
    assert runs["scout.yml"][0]["databaseId"] == 7
    assert calls[0][2:4] == ("--workflow", "scout.yml") and ">=2026-11-02" in calls[0]
    assert log_of(7) == "log text"
    assert calls[-1] == ("run", "view", "7", "--repo", "o/r", "--log-failed")
    assert rs.ran_model(jobs_of(7))


def test_fetch_all_reads_jobs_and_logs_of_a_run_once():
    calls = []

    def fake(*a):
        calls.append(a)
        if a[:2] == ("run", "list"):
            return json.dumps([run_(7)])
        if a[:2] == ("run", "view"):
            return "log text"
        return json.dumps({"jobs": MODEL})
    _, jobs_of, log_of = rs.fetch_all(["scout.yml"], "2026-11-02", repo="o/r", run=fake)
    jobs_of(7), jobs_of(7), log_of(7), log_of(7)
    assert len(calls) == 3


def test_queue_numbers_counts_slots_waiting_and_human_age():
    issues = [
        {"number": 1, "labels": [{"name": "agent:dev"}]},
        {"number": 2, "labels": [{"name": "prio:2"}]},
        {"number": 3, "labels": [{"name": "prio:2"}, {"name": "agent:dev"}]},
        {"number": 4, "labels": [{"name": "parked"}], "updatedAt": "2026-11-05T12:00:00Z"},
    ]
    prs = [
        {"number": 9, "headRefName": "agent/1-x", "labels": []},
        {"number": 10, "headRefName": "agent/2-y", "labels": [{"name": "parked"}],
         "updatedAt": "2026-11-05T12:00:00Z"},
        {"number": 11, "headRefName": "feature/z", "labels": []},
    ]
    q = mod.queue_numbers(issues, prs, max_dev=4, max_prs=5, now=NOW)
    assert q["waiting"] == 1
    assert (q["free_dev"], q["free_prs"]) == (2, 4)
    assert q["parked"] == 2 and q["human_median_days"] == 4.0


def test_limit_failure_opens_one_proposal(monkeypatch):
    only_claude(monkeypatch, ["orchestrator.yml"])
    calls = []
    gh_fake = make_gh({"orchestrator.yml": [run_(1, conclusion="failure")]}, {1: MODEL},
                      {1: "Error: rate limit exceeded"}, [], [], calls=calls)
    model, queue, reasons, roles, candidates = mod.capacity_sections(TODAY, gh_fake, 4, 5, now=NOW)
    assert reasons == ["1 failed model run(s) with a limit or rate error (last 7 days)"]
    assert "orchestrator.yml (orchestrator): 1 runs" in model
    assert "turns and denied calls: open" in model
    assert candidates == []  # a limit error is not a role failure
    mod.upsert_proposal(mod.proposal_body(reasons, model, queue, "2026-11-09", roles), gh_fake)
    creates = [c for c in calls if c[:2] == ("issue", "create")]
    assert len(creates) == 1 and creates[0][3] == "Capacity proposal"
    assert "## Levers (Daniel decides)" in creates[0][5] and "MAX_DEV" in creates[0][5]
    assert "separate seat" not in creates[0][5] and "## Roles, last 7 days" in creates[0][5]


def test_no_limit_error_and_short_queue_opens_nothing(monkeypatch):
    only_claude(monkeypatch, ["orchestrator.yml"])
    gh_fake = make_gh({"orchestrator.yml": [run_(1)]}, {1: MODEL}, {}, [], [])
    assert mod.capacity_sections(TODAY, gh_fake, 2, 3, now=NOW)[2] == []


def test_waiting_backlog_with_no_free_dev_slot_opens_proposal(monkeypatch):
    only_claude(monkeypatch, [])
    issues = [{"number": 4, "labels": [{"name": "agent:dev"}]}] + [
        {"number": n, "labels": [{"name": "prio:3"}]} for n in (1, 2, 3)]
    reasons = mod.capacity_sections(TODAY, make_gh({}, {}, {}, issues, []), 1, 3, now=NOW)[2]
    assert reasons == ["3 queued issues wait while no agent:dev slot is free"]
    two_waiting = issues[:3]
    assert mod.capacity_sections(TODAY, make_gh({}, {}, {}, two_waiting, []), 1, 3, now=NOW)[2] == []


def test_existing_open_proposal_is_updated_not_duplicated():
    calls = []
    found = [{"number": 42, "title": "Capacity proposal"}]
    mod.upsert_proposal("Updated body\n", make_gh({}, {}, {}, [], [], found=found, calls=calls))
    assert ("issue", "edit", "42", "--body", "Updated body\n") in calls
    assert not any(c[:2] == ("issue", "create") for c in calls)


def test_capacity_run_only_reads_and_writes_issues(monkeypatch):
    only_claude(monkeypatch, ["orchestrator.yml"])
    calls = []
    gh_fake = make_gh({"orchestrator.yml": [run_(1, conclusion="failure")]}, {1: MODEL},
                      {1: "usage limit"}, [], [], calls=calls)
    model, queue, reasons, roles, _candidates = mod.capacity_sections(TODAY, gh_fake, 2, 3, now=NOW)
    mod.upsert_proposal(mod.proposal_body(reasons, model, queue, "2026-11-09", roles), gh_fake)
    assert reasons and {c[0] for c in calls} <= {"run", "api", "issue", "pr"}


def test_gh_failure_gives_unknown_sections_and_no_proposal(monkeypatch):
    only_claude(monkeypatch, ["orchestrator.yml"])

    def failing(*args):
        raise subprocess.CalledProcessError(1, "gh")
    model, queue, reasons, roles, candidates = mod.capacity_sections(TODAY, failing, now=NOW)
    assert model.endswith("- unknown") and queue.endswith("- unknown") and roles.endswith("- unknown")
    assert reasons == [] and candidates == []


SAME_FAILURE = "2026-11-08T08:01:00Z\t##[error]Build failed: 3 tests in 2.5s"


def test_failure_class_normalizes_and_skips_limit_and_empty_logs():
    assert rs.failure_class(f"job\tstep\t{SAME_FAILURE}\n") == "build failed: # tests in #.#s"
    assert rs.failure_class("job\tstep\t2026-11-08T08:01:00Z usage limit reached\n") is None
    assert rs.failure_class("job\tstep\t2026-11-08T08:01:00Z all good\n") is None


def test_failure_class_is_the_first_error_annotation_only():
    """agent-template #749 and #762: `gh run view --log-failed` returns the whole job log. The echoed step script
    (`echo "::error::..."`, also with the escape in caret form) and the echoed model prompt contain "error" and
    "failed" but are no failure; only a `##[error]` line is, and not the bare exit code line."""
    echo = ('orchestrate\tUNKNOWN STEP\t2026-11-23T14:11:44Z \x1b[36;1m  [ -n "${!n}" ] || '
            '{ echo "::error::Repo variable $n is not set"; exit 1; }\x1b[0m\n')
    caret = echo.replace("\x1b", "^[")
    prompt = "orchestrate\tUNKNOWN STEP\t2026-11-23T14:12:09Z These calls are NOT allowed and end the run as failed: x\n"
    exit_line = "orchestrate\tUNKNOWN STEP\t2026-11-23T14:12:39Z ##[error]Process completed with exit code 1.\n"
    assert rs.failure_class("\ufeff" + echo + caret + prompt + exit_line) is None
    real = "job\tstep\t2026-11-23T14:12:39Z \x1b[31m##[error]Repo variable AUTHOR_BOT is not set\x1b[0m\n"
    assert rs.failure_class(echo + prompt + real + exit_line) == "repo variable author_bot is not set"
    assert rs.failure_class("job\tstep\t2026-11-23T14:12:39Z FAILED tests/test_x.py::test_y\n" + exit_line) is None


def test_three_same_failures_open_one_role_proposal(monkeypatch):
    only_claude(monkeypatch, ["agent-dev.yml"])
    calls = []
    runs = {"agent-dev.yml": [run_(n, conclusion="failure") for n in (1, 2, 3)]}
    logs = {n: f"job\tstep\t{SAME_FAILURE}\n" for n in (1, 2, 3)}
    gh_fake = make_gh(runs, {n: MODEL for n in (1, 2, 3)}, logs, [], [], calls=calls)
    _model, _queue, _reasons, roles, candidates = mod.capacity_sections(TODAY, gh_fake, 2, 3, now=NOW)
    assert candidates == [("build failed: # tests in #.#s", 3)]
    assert "| dev | 3 | 3 | - | 0 restart(s) |" in roles and "| fix | no model step | - | - | - |" in roles
    mod.upsert_proposal(mod.role_proposal_body(candidates, roles, "2026-11-09"), gh_fake, mod.ROLE_PROPOSAL_TITLE)
    creates = [c for c in calls if c[:2] == ("issue", "create")]
    assert len(creates) == 1 and creates[0][3] == "Role proposal"
    assert "It proposes only" in creates[0][5] and "agent-dev.yml" not in creates[0][5]


def test_one_off_failure_opens_no_role_proposal(monkeypatch):
    only_claude(monkeypatch, ["agent-dev.yml"])
    runs = {"agent-dev.yml": [run_(n, conclusion="failure") for n in (1, 2)]}
    logs = {1: f"job\tstep\t{SAME_FAILURE}\n", 2: "job\tstep\t2026-11-08T08:01:00Z other error\n"}
    gh_fake = make_gh(runs, {1: MODEL, 2: MODEL}, logs, [], [])
    assert mod.capacity_sections(TODAY, gh_fake, 2, 3, now=NOW)[4] == []


def test_failures_older_than_7_days_count_for_roles_not_for_model_runs(monkeypatch):
    only_claude(monkeypatch, ["agent-dev.yml"])
    old = [run_(n, conclusion="failure", day=1) for n in (1, 2, 3)]  # 8 days before TODAY: outside the 7-day window
    gh_fake = make_gh({"agent-dev.yml": old}, {n: MODEL for n in (1, 2, 3)},
                      {n: f"job\tstep\t{SAME_FAILURE}\n" for n in (1, 2, 3)}, [], [])
    model, _queue, reasons, _roles, candidates = mod.capacity_sections(TODAY, gh_fake, 2, 3, now=NOW)
    assert "agent-dev.yml (dev): 0 runs" in model and reasons == []
    assert candidates == [("build failed: # tests in #.#s", 3)]


def test_env_int_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("MAX_DEV", "four")
    monkeypatch.setenv("MAX_PRS", "")
    assert (mod.env_int("MAX_DEV", 2), mod.env_int("MAX_PRS", 3)) == (2, 3)
    monkeypatch.setenv("MAX_DEV", "5")
    assert mod.env_int("MAX_DEV", 2) == 5


def test_summary_step_passes_caps_read_only():
    text = WORKFLOW_YML.read_text(encoding="utf-8")
    assert "MAX_DEV: ${{ vars.MAX_DEV || '4' }}" in text
    assert "MAX_PRS: ${{ vars.MAX_PRS || '5' }}" in text
    assert "gh variable" not in text and "gh secret" not in text


def test_app_token_can_read_actions_runs_and_logs():
    # gh run list, the jobs API and gh run view --log-failed need actions: read; without it the model section is "unknown"
    text = WORKFLOW_YML.read_text(encoding="utf-8")
    assert "permission-actions: read" in text


def _class_runs(n, start=1):
    return {"build failed: # tests": [{"databaseId": i, "createdAt": f"2026-11-0{i}T08:00:00Z"} for i in range(start, start + n)]}


class Issues:
    """Fake gh for repeat_issues: `known` is what the title search returns; creates are recorded."""

    def __init__(self, known=()):
        self.known, self.calls = list(known), []

    def __call__(self, *args):
        self.calls.append(args)
        return json.dumps(self.known) if args[:2] == ("issue", "list") else ""

    def creates(self):
        return [c for c in self.calls if c[:2] == ("issue", "create")]


def test_a_repeated_failure_class_becomes_a_signed_work_issue_for_the_agents():
    """The Role proposal ended with "Daniel decides". A class that repeats is work: one signed issue the pipeline
    trusts and starts, with fixed script text, the count and the run links, never the log text."""
    run = Issues()
    title = mod.repeat_title("build failed: # tests")
    assert mod.repeat_issues(_class_runs(3), "k3y", run, "o/r") == [title]
    create = run.creates()[0]
    body = create[create.index("--body") + 1]
    assert create[create.index("--title") + 1] == title and title.startswith("Repeated failure: ")
    assert "build failed" not in title and "build failed" not in body  # log text is never signed
    assert "3 failed model runs" in body and "https://github.com/o/r/actions/runs/3" in body
    assert "Nobody decides this for you" in body and "Daniel" not in body
    import guard_mark
    import trusted_issues

    assert guard_mark.verify(title, body, "k3y") and create[create.index("--label") + 1] == "prio:2"

    issue = {"title": title, "body": body, "author": {"login": "bot[bot]"}, "labels": []}
    assert trusted_issues.is_guard_issue(issue, "bot[bot]", "k3y")


def test_no_second_issue_while_one_is_open_and_a_closed_one_needs_new_runs():
    title = mod.repeat_title("build failed: # tests")
    opened = Issues([{"number": 5, "title": title, "state": "OPEN", "closedAt": None}])
    assert mod.repeat_issues(_class_runs(4), "k3y", opened, "o/r") == [] and opened.creates() == []
    closed = [{"number": 5, "title": title, "state": "CLOSED", "closedAt": "2026-11-03T12:00:00Z"}]
    assert mod.repeat_issues(_class_runs(5), "k3y", Issues(closed), "o/r") == []  # only runs 4 and 5 are newer
    again = Issues(closed)
    assert mod.repeat_issues(_class_runs(6), "k3y", again, "o/r") == [title]  # runs 4, 5 and 6
    assert "3 failed model runs" in again.creates()[0][again.creates()[0].index("--body") + 1]
    other = Issues([{"number": 9, "title": title + " and more", "state": "OPEN", "closedAt": None}])
    assert mod.repeat_issues(_class_runs(3), "k3y", other, "o/r") == [title]  # only the exact title counts


def test_without_the_guard_key_or_below_the_threshold_no_work_issue_is_written():
    assert mod.repeat_issues(_class_runs(3), "", Issues(), "o/r") == []
    assert mod.repeat_issues(_class_runs(2), "k3y", Issues(), "o/r") == []
    assert "Daniel decides" not in mod.role_proposal_body([("x", 3)], "## Roles", "2026-11-24")
