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
    assert re.findall(r"^  ([a-z-]+):$", jobs, re.MULTILINE) == ["validate", "scope", "changes", "agent-smoke"]


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
    assert "run: make check\n" in block("validate")


def test_a_text_edit_runs_only_the_text_checks_when_the_head_is_already_green():
    """A PR title or body edit (scripts do that) started the whole suite again although the code did not change."""
    scope, job = block("scope"), block("validate")
    assert "github.event.action == 'edited' && github.event.changes.base == null" in scope
    assert "validate.yml/runs?head_sha=$SHA&status=success" in scope and '"${n:-0}" -gt 0' in scope
    assert "permissions:\n      actions: read\n" in scope
    assert "actions/checkout" not in scope and "make " not in scope  # no PR code where the token can read runs
    assert "needs: scope" in job and "if: ${{ !cancelled() }}" in job  # a skipped or failed scope means the full run
    text = job[job.index("Text checks only"):job.index("- name: Checks (ruff")]
    full = job[job.index("- name: Checks (ruff"):]
    assert "needs.scope.outputs.text_only == 'true'" in text and "run: make check-text" in text
    assert "needs.scope.outputs.text_only != 'true'" in full and "run: make check\n" in full


def test_the_workflow_token_of_the_job_that_runs_pr_code_cannot_read_runs():
    head = TEXT[:TEXT.index("\njobs:\n")]
    assert head.endswith("permissions:\n  contents: read\n  pull-requests: read") and "actions:" not in head
    assert "actions:" not in block("validate")


def test_check_text_holds_every_check_that_reads_the_pr_text():
    makefile = (Path(__file__).resolve().parent.parent.parent / "Makefile").read_text(encoding="utf-8")
    target = makefile[makefile.index("\ncheck-text:\n"):makefile.index("# Empty template default")]
    for line in ("python3 tools/check/check_pr_form.py", "python3 tools/managed_guard.py check", "test-evidence"):
        assert line in target, line
    assert "pytest" not in target and "ruff" not in target


def test_the_validate_time_limit_is_a_repo_variable_with_the_old_default():
    """roblox_energy #353: `make check` there takes about 14 minutes, the fixed 15 minute limit cancelled the run, and a
    cancelled run starts no review and no fix round."""
    root = Path(__file__).resolve().parent.parent.parent
    text = (root / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
    assert "timeout-minutes: ${{ fromJSON(vars.VALIDATE_TIMEOUT || '15') }}" in text


@pytest.mark.template_only  # docs/variables.md is not a managed path: a downstream project does not get it by sync
def test_the_validate_time_limit_is_documented():
    root = Path(__file__).resolve().parent.parent.parent
    assert "`VALIDATE_TIMEOUT` | `15`" in (root / "docs" / "variables.md").read_text(encoding="utf-8")
