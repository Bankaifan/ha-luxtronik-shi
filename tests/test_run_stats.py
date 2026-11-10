"""Quota baseline (design 0007): model runs per day from fixture data."""
import datetime
import json

import run_stats as s

NOW = datetime.datetime(2026, 11, 10, 12, 0, tzinfo=datetime.UTC)
MODEL = [{"steps": [{"name": "Gate", "conclusion": "success"}, {"name": "Run claude", "conclusion": "success"}]}]
NO_MODEL = [{"steps": [{"name": "Gate", "conclusion": "success"}, {"name": "Run claude", "conclusion": "skipped"}]}]


def run(id_, day, conclusion="success"):
    return {"databaseId": id_, "conclusion": conclusion, "createdAt": f"2026-11-{day:02d}T08:00:00Z"}


def test_ran_model():
    assert s.ran_model(MODEL)
    assert not s.ran_model(NO_MODEL)
    assert not s.ran_model([{"steps": None}, {}])


def test_stats_counts_model_and_skipped_runs():
    runs = [run(1, 10), run(2, 10), run(3, 9), run(4, 9, "skipped"), run(5, 8)]
    jobs = {1: MODEL, 2: MODEL, 3: MODEL, 5: NO_MODEL}
    result = s.stats(runs, lambda i: jobs[i], days=14, now=NOW)
    assert result["model_runs"] == 3
    assert result["gate_skipped"] == 1
    assert result["per_day"] == {"2026-11-09": 1, "2026-11-10": 2}


def test_stats_ignores_runs_outside_window():
    runs = [run(1, 10), run(2, 1), run(3, 1, "skipped")]
    result = s.stats(runs, lambda i: MODEL, days=7, now=NOW)
    assert (result["model_runs"], result["gate_skipped"]) == (1, 0)


def test_format_stats():
    out = s.format_stats({"days": 14, "model_runs": 28, "gate_skipped": 5, "per_day": {"2026-11-10": 28}})
    assert "2026-11-10: 28" in out
    assert "Model runs: 28, gate-skipped runs: 5" in out
    assert "(average): 2.00" in out


def test_fetch_uses_gh_calls():
    calls = []

    def fake(*a):
        calls.append(a)
        if a[0] == "run":
            return json.dumps([run(7, 10)])
        return json.dumps({"jobs": MODEL})
    runs, jobs_of = s.fetch(repo="o/r", run=fake)
    assert runs[0]["databaseId"] == 7
    assert s.ran_model(jobs_of(7))
    assert calls[1][1] == "repos/o/r/actions/runs/7/jobs"
