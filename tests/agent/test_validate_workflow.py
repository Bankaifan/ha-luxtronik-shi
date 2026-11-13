"""validate.yml keeps the job names and triggers the required checks report under (design 0016 step 5)."""
import re
from pathlib import Path

import pytest

TEXT = (Path(__file__).resolve().parent.parent.parent / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")


def block(name):
    """Text of one job, from its key to the next job key (or the end)."""
    start = TEXT.index(f"\n  {name}:\n")
    nxt = re.search(r"\n  [a-z-]+:\n", TEXT[start + 1:])
    return TEXT[start:start + 1 + nxt.start()] if nxt else TEXT[start:]


@pytest.mark.template_only  # checks the template's own files, not a downstream project
def test_job_names_are_exactly_the_required_ones():
    jobs = TEXT[TEXT.index("\njobs:\n"):]
    assert re.findall(r"^  ([a-z-]+):$", jobs, re.MULTILINE) == ["validate", "changes", "agent-smoke"]


@pytest.mark.template_only  # checks the template's own files, not a downstream project
def test_triggers_are_pull_request_push_to_main_and_dispatch():
    on = TEXT[TEXT.index("\non:\n"):TEXT.index("\npermissions:")]
    assert "pull_request:" in on
    assert "types: [opened, synchronize, reopened, edited]" in on
    assert "push:" in on and "branches: [main]" in on
    assert "workflow_dispatch:" in on
    for bad in ("schedule:", "workflow_run", "issues:"):
        assert bad not in on, bad


def test_agent_smoke_waits_for_changes_and_reports_on_skip():
    job = block("agent-smoke")
    assert "needs: changes" in job
    assert "needs.changes.outputs.agents == 'true'" in job


def test_validate_runs_make_check():
    assert "run: make check" in block("validate")
