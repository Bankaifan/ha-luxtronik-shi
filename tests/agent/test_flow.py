"""Flow metrics (issue #420): recorded-style timelines of agent-template #404 and ha-luxtronik-shi #135."""
import datetime
import json

import flow
import status

NOW = datetime.datetime(2026, 11, 12, 12, 0, tzinfo=datetime.UTC)


def ev(name, at):
    return {"event": "labeled", "created_at": at, "label": {"name": name}}


def run(wf, concl, created, updated):
    return {"workflowName": wf, "conclusion": concl, "createdAt": created, "updatedAt": updated}


# agent-template #404: one fix round, merged through the train.
PR404 = {"number": 404, "headRefName": "agent/404-flow", "createdAt": "2026-11-12T09:20:00Z",
         "mergedAt": "2026-11-12T10:30:00Z", "labels": [],
         "reviews": [{"state": "CHANGES_REQUESTED", "submittedAt": "2026-11-12T09:50:00Z"},
                     {"state": "APPROVED", "submittedAt": "2026-11-12T10:10:00Z"}]}
EV404 = [ev("approved", "2026-11-12T09:00:00Z"), ev("agent:dev", "2026-11-12T09:05:00Z")]
RUNS404 = [run("agent-dev", "success", "2026-11-12T09:05:00Z", "2026-11-12T09:19:00Z"),
           run("validate", "failure", "2026-11-12T09:20:00Z", "2026-11-12T09:25:00Z"),
           run("validate", "success", "2026-11-12T09:30:00Z", "2026-11-12T09:40:00Z"),
           run("agent-review", "success", "2026-11-12T09:41:00Z", "2026-11-12T09:50:00Z"),
           run("agent-fix", "success", "2026-11-12T09:51:00Z", "2026-11-12T10:00:00Z"),
           run("agent-review", "skipped", "2026-11-12T10:01:00Z", "2026-11-12T10:01:00Z")]

# ha-luxtronik-shi #135: no trusted label (owner's own issue), restart, needs the owner.
PR135 = {"number": 135, "headRefName": "agent/135-heat", "createdAt": "2026-11-12T08:30:00Z",
         "mergedAt": "2026-11-12T11:00:00Z", "labels": [{"name": "needs-human"}], "reviews": []}
EV135 = [ev("agent:dev", "2026-11-12T08:00:00Z"), ev("restart:1", "2026-11-12T08:10:00Z")]


def test_issue_number():
    assert flow.issue_number(PR404) == 404
    assert flow.issue_number({"headRefName": "dependabot/x"}) is None


def test_row_stage_waits_and_counts():
    row = flow.pr_row(PR404, EV404, RUNS404)
    assert [row[f"{s}_min"] for s in flow.STAGES] == [5.0, 15.0, 20.0, 10.0, 20.0, 20.0]
    assert row["lead_min"] == 90.0
    assert row["fix_rounds"] == 1
    assert row["model_runs"] == 3  # the skipped run does not count
    assert row["runs_by_workflow"] == "agent-dev:1;agent-fix:1;agent-review:1"
    assert (row["restarts"], row["needs_human"]) == (0, "no")


def test_row_without_trusted_label_uses_issue_creation_and_leaves_gaps_empty():
    row = flow.pr_row(PR135, EV135, [], issue_created="2026-11-12T07:50:00Z")
    assert row["dispatch_min"] == 10.0 and row["develop_min"] == 30.0
    assert row["ci_min"] == row["review_min"] == row["fix_min"] == row["train_min"] == ""
    assert row["lead_min"] == 190.0
    assert (row["restarts"], row["needs_human"]) == (1, "yes")


def test_block_summarises_the_last_24_hours():
    rows = [flow.pr_row(PR404, EV404, RUNS404), flow.pr_row(PR135, EV135, [], "2026-11-12T07:50:00Z")]
    old = dict(rows[0], merged_at="2026-11-10T10:00:00Z")
    lines = flow.flow_block(rows + [old], RUNS404, NOW)
    text = "\n".join(lines)
    assert "merged PRs: 2" in text
    assert "median 140 min, p90 190 min" in text
    assert "slowest stage: develop (median 22 min)" in text
    assert "max parallel agent jobs (runs of these PRs): 1" in text
    assert "model runs per merged PR: 1.5" in text
    assert "needed the owner: 1 of 2 (50 %)" in text


def test_block_without_merged_prs():
    assert flow.flow_block([], [], NOW) == ["- merged PRs: 0"]


def test_max_parallel_counts_overlap():
    runs = [run("agent-dev", "success", "2026-11-12T09:00:00Z", "2026-11-12T09:30:00Z"),
            run("agent-fix", "success", "2026-11-12T09:10:00Z", "2026-11-12T09:20:00Z"),
            run("validate", "success", "2026-11-12T09:12:00Z", "2026-11-12T09:15:00Z")]
    assert flow.max_parallel(runs) == 2


def test_write_csv(tmp_path):
    path = tmp_path / "flow.csv"
    flow.write_csv([flow.pr_row(PR404, EV404, RUNS404)], path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(flow.COLUMNS)
    assert lines[1].startswith("404,404,2026-11-12T10:30:00Z,5.0,15.0")


def test_collect_reads_prs_events_and_runs():
    def fake(*args):
        if args[0] == "pr":
            return json.dumps([PR404, {"number": 9, "headRefName": "feature/x", "mergedAt": "2026-11-12T10:30:00Z"}])
        if args[0] == "api":
            return json.dumps([EV404])
        return json.dumps(RUNS404)
    rows, runs = flow.collect("o/r", fake)
    assert [r["pr"] for r in rows] == [404] and len(runs) == len(RUNS404)


def test_status_body_has_flow_block_only_when_given():
    base = {"runs": [], "prs": [], "issues": [], "ages": {}, "orchestrator": None, "ideas": [],
            "actions": [], "now": NOW, "owner": "o"}
    assert "Flow, last 24 h" not in status.build_body(**base)
    assert "## Flow, last 24 h\n- merged PRs: 0" in status.build_body(**base, flow_lines=["- merged PRs: 0"])


def test_status_flow_failure_leaves_block_out():
    def boom(*args):
        raise OSError("no gh")
    assert status.flow_lines_for({}, "o/r", NOW, boom) is None
