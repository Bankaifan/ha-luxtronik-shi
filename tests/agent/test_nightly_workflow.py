"""nightly.yml (design 0009 step 4): gated by NIGHTLY_HEAVY_TESTS, least privilege, watched by the liveness guard."""
import re
from pathlib import Path

import liveness

TEXT = (Path(__file__).resolve().parent.parent.parent / ".github" / "workflows" / "nightly.yml").read_text(encoding="utf-8")


def block(name):
    """Text of one job, from its key to the next job key (or the end)."""
    start = TEXT.index(f"\n  {name}:\n")
    nxt = re.search(r"\n  [a-z-]+:\n", TEXT[start + 1:])
    return TEXT[start:start + 1 + nxt.start()] if nxt else TEXT[start:]


def test_triggers_are_schedule_and_dispatch_only():
    on = TEXT[TEXT.index("\non:\n"):TEXT.index("\npermissions:")]
    assert "schedule:" in on and "workflow_dispatch:" in on
    for bad in ("pull_request", "push:", "workflow_run", "issues:"):
        assert bad not in on, bad


def test_default_permissions_are_read_only():
    top = TEXT[TEXT.index("\npermissions:"):TEXT.index("\nconcurrency:")]
    assert "contents: read" in top and "write" not in top


def test_slow_job_is_gated_and_runs_only_slow_tests():
    job = block("slow-tests")
    assert "if: vars.NIGHTLY_HEAVY_TESTS == 'true'" in job
    assert "pytest --timeout=300 -q -m slow" in job
    assert "ref: main" in job
    assert "write" not in job and "secrets." not in job


def test_report_job_needs_issues_write_and_nothing_more():
    job = block("report")
    assert "needs: slow-tests" in job and "if: failure()" in job
    perms = job[job.index("permissions:"):job.index("steps:")]
    assert re.findall(r"(\w+): (\w+)", perms) == [("contents", "read"), ("issues", "write")]


def test_secret_only_in_the_script_step():
    assert TEXT.count("secrets.") == 1
    step = TEXT[TEXT.index("- name: Open the failure issue"):]
    assert "secrets.GUARD_KEY" in step and "run: python3 tools/liveness.py nightly-failed" in step
    assert "claude" not in TEXT.lower()


def test_nightly_is_watched_and_gated_in_liveness():
    assert liveness.SCHEDULED["nightly.yml"][1] == 24 * 60
    assert liveness.GATED["nightly.yml"] == "NIGHTLY_HEAVY_TESTS"
