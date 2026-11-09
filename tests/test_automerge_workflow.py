"""Guards for the automerge workflow: one run per PR, and a second run must not fail."""

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "automerge.yml"

FAKE_GH = """#!/bin/bash
if [ "$1 $2" = "pr merge" ]; then
  printf '%s\\n' "$MERGE_OUT"
  exit "$MERGE_RC"
fi
if [ "$1 $2" = "pr view" ]; then
  if [ "$VIEW_RC" != 0 ]; then exit "$VIEW_RC"; fi
  printf '%s' "$VIEW_STATE"
  exit 0
fi
echo "unexpected gh call: $*" >&2
exit 99
"""


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _merge_step_script() -> str:
    """Return the run: body of the 'Enable auto-merge' step (YAML is not parsed, the block is copied)."""
    lines = _text().splitlines()
    start = next(i for i, line in enumerate(lines) if "name: Enable auto-merge" in line)
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    body = []
    for line in lines[run + 1 :]:
        if line.strip() and not line.startswith(" " * 10):
            break
        body.append(line)
    return textwrap.dedent("\n".join(body)) + "\n"


def test_runs_are_serialised_per_pr_without_cancelling():
    text = _text()
    assert "concurrency:" in text
    assert "group: automerge-${{ github.event.pull_request.number || github.event.sha }}" in text
    assert "cancel-in-progress: false" in text


def test_already_merging_or_merged_is_success():
    text = _text()
    for phrase in ("Merge already in progress", "already merged", "not open"):
        assert phrase in text, phrase
    assert "exit 0" in text


def test_other_merge_errors_still_fail():
    text = _text()
    assert 'echo "$out" >&2' in text
    assert text.rstrip().endswith("exit 1")


@pytest.mark.parametrize(
    ("merge_rc", "merge_out", "view_rc", "view_state", "expected_rc"),
    [
        # Merge succeeded: nothing to check.
        (0, "enabled", 0, "OPEN", 0),
        # Real failure, state read as OPEN: must fail.
        (1, "GraphQL: boom", 0, "OPEN", 1),
        # Real failure, state read but empty: must fail.
        (1, "GraphQL: boom", 0, "", 1),
        # Real failure and the state read itself failed (same root cause, e.g. token): must fail, not go green.
        (1, "GraphQL: boom", 1, "", 1),
        # Read state says the PR is no longer open: success.
        (1, "GraphQL: boom", 0, "MERGED", 0),
        # Known phrase: success even if the state read failed.
        (1, "Merge already in progress", 1, "", 0),
        (1, "Pull request is already merged", 1, "", 0),
    ],
)
def test_merge_step_exit_code(tmp_path, merge_rc, merge_out, view_rc, view_state, expected_rc):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)
    script = tmp_path / "step.sh"
    script.write_text(_merge_step_script(), encoding="utf-8")
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "PR": "63",
        "GH_REPO": "owner/repo",
        "GH_TOKEN": "x",
        "MERGE_RC": str(merge_rc),
        "MERGE_OUT": merge_out,
        "VIEW_RC": str(view_rc),
        "VIEW_STATE": view_state,
    }
    result = subprocess.run(
        ["bash", "-eo", "pipefail", str(script)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == expected_rc, result.stdout + result.stderr


GATE_GH = """#!/bin/bash
if [ "$1 $2" = "pr view" ]; then printf '%s' "$VIEW_JSON"; exit 0; fi
if [ "$1" = "api" ]; then printf '%s' "$STATUS_STATE"; exit 0; fi
echo "unexpected gh call: $*" >&2
exit 99
"""


def _gate_script() -> str:
    lines = _text().splitlines()
    start = next(i for i, line in enumerate(lines) if "name: Wait for security-review" in line)
    run = next(i for i in range(start, len(lines)) if lines[i].strip() == "run: |")
    body = []
    for line in lines[run + 1 :]:
        if line.strip() and not line.startswith(" " * 10):
            break
        body.append(line)
    return textwrap.dedent("\n".join(body)) + "\n"


@pytest.mark.parametrize(
    ("label", "state", "wait"),
    [
        ("risk:security", "pending", True),
        ("risk:security", "failure", True),
        ("risk:security", "none", True),
        ("risk:security", "success", False),
        ("other", "failure", False),
    ],
)
def test_security_gate_waits_without_error_unless_success(tmp_path, label, state, wait):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(GATE_GH, encoding="utf-8")
    gh.chmod(0o755)
    script = tmp_path / "gate.sh"
    script.write_text(_gate_script(), encoding="utf-8")
    out = tmp_path / "out"
    out.touch()
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "PR": "67",
        "GH_REPO": "owner/repo",
        "GITHUB_OUTPUT": str(out),
        "STATUS_STATE": state,
        "VIEW_JSON": '{"headRefOid": "64024cd", "labels": [{"name": "' + label + '"}]}',
    }
    result = subprocess.run(["bash", "-eo", "pipefail", str(script)], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert ("wait=true" in out.read_text()) is wait


def test_merge_step_is_skipped_while_waiting_and_status_event_reruns():
    text = _text()
    assert "steps.gate.outputs.wait != 'true'" in text
    assert "github.event.context == 'security-review'" in text
    assert "github.event.state == 'success'" in text
