import datetime
import importlib.util
import json
import pathlib
import subprocess

_path = pathlib.Path(__file__).parent.parent / "tools" / "weekly_summary.py"
_spec = importlib.util.spec_from_file_location("weekly_summary", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

NOW = datetime.datetime(2026, 11, 9, 12, 0, tzinfo=datetime.UTC)


def status_runs(created_at):
    """Fake gh: `gh run list` returns the given status run (or none)."""
    def run(*args):
        assert args[:2] == ("run", "list")
        return json.dumps([{"createdAt": created_at, "url": "u"}] if created_at else [])
    return run


def test_build_body_lists_rows_and_none():
    body = mod.build_body([{"number": 5, "title": "Fix x"}], [], [], [{"number": 9, "title": "Idea"}], "2026-11-09")
    assert "- #5 Fix x" in body
    assert "- #9 Idea" in body
    assert body.count("- none") == 2
    assert "Updated 2026-11-09." in body


def test_count_code_skips_generated_and_unknown():
    files = ["a.py", "tools/b.py", "x.sh", "package-lock.json", "dist/c.js", "app.min.js", "README.md", "vendor/d.py"]
    lines, modules = mod.count_code(files, lambda p: 10)
    assert lines == {"python": 20, "shell": 10}
    assert modules == {"python": 2, "shell": 1}


def test_max_parallel_counts_overlap_and_ignores_non_agent():
    prs = [
        {"headRefName": "agent/1-a", "createdAt": "2026-11-03T10:00:00Z", "closedAt": "2026-11-04T10:00:00Z"},
        {"headRefName": "agent/2-b", "createdAt": "2026-11-03T12:00:00Z", "closedAt": None},
        {"headRefName": "agent/3-c", "createdAt": "2026-11-04T10:00:00Z", "closedAt": "2026-11-05T10:00:00Z"},
        {"headRefName": "feature/x", "createdAt": "2026-11-03T10:00:00Z", "closedAt": None},
        {"headRefName": "agent/4-d", "createdAt": "2026-10-01T10:00:00Z", "closedAt": "2026-10-02T10:00:00Z"},
    ]
    assert mod.max_parallel(prs, "2026-11-02T00:00:00Z", "2026-11-09T23:59:59Z") == 2


def test_avg_review_rounds():
    merged = [{"headRefName": "agent/1", "reviews": [{"state": "CHANGES_REQUESTED"}, {"state": "APPROVED"}]},
              {"headRefName": "agent/2", "reviews": [{"state": "APPROVED"}]},
              {"headRefName": "other", "reviews": [{"state": "CHANGES_REQUESTED"}] * 5}]
    assert mod.avg_review_rounds(merged) == 1.5
    assert mod.avg_review_rounds([]) is None


def test_median_ci_minutes():
    def run(minutes, conclusion="success"):
        return {"startedAt": "2026-11-03T10:00:00Z", "updatedAt": f"2026-11-03T10:{minutes:02d}:00Z",
                "conclusion": conclusion}
    assert mod.median_ci_minutes([run(2), run(4), run(9), run(50, "")]) == 4.0
    assert mod.median_ci_minutes([]) is None


def test_metrics_row_and_append_idempotent(tmp_path):
    row = mod.metrics_row("2026-11-09", {"python": 30}, {"python": 3}, 2, None, 4.0, None)
    assert row["code_lines"] == 30 and row["lines_by_lang"] == "python=30"
    assert row["avg_review_rounds"] == "" and row["actions_minutes"] == "" and row["conflicts_rebuilt"] == ""
    path = tmp_path / "docs" / "metrics.csv"
    assert mod.append_metrics(path, row) is True
    assert mod.append_metrics(path, row) is False
    lines = path.read_text().splitlines()
    assert lines[0] == ",".join(mod.COLUMNS) and len(lines) == 2


def test_status_run_stale_fresh_stale_and_none():
    liveness = mod.liveness
    assert liveness.status_run_stale(status_runs("2026-11-09T11:00:00+00:00"), NOW) is False
    assert liveness.status_run_stale(status_runs("2026-11-09T08:00:00+00:00"), NOW) is True
    assert liveness.status_run_stale(status_runs(None), NOW) is True


def test_status_stale_safe_skips_warning_when_gh_fails():
    def failing(*args):
        raise subprocess.CalledProcessError(1, "gh")

    assert mod.status_stale_safe(failing) is False


def test_build_body_warns_when_status_stale():
    body = mod.build_body([], [], [], [], "2026-11-09", status_stale=True)
    assert "## Warning" in body and "last 3 hours" in body
    assert "## Warning" not in mod.build_body([], [], [], [], "2026-11-09", status_stale=False)


def test_run_main_exits_nonzero_on_readback_failure(monkeypatch):
    def boom():
        raise mod.liveness.ReadbackError("issue #1: body not as written after update")

    monkeypatch.setattr(mod, "main", boom)
    assert mod.run_main() == 1
