"""Orchestrator model step is comment-only (design 0017, step 5): no Edit or Write outside .agent-out/ (body files), no git
or make; no contents scope;
HANDOVER.md is committed and pushed by a script step with its own contents token."""

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import handover_text

WORKFLOW = ROOT / ".github" / "workflows" / "orchestrator.yml"


def _doc() -> dict:
    yaml = pytest.importorskip("yaml")  # installed by tools/ci/install_tools.sh
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps() -> list:
    return _doc()["jobs"]["orchestrate"]["steps"]


def _by_id(step_id: str) -> dict:
    return next(s for s in _steps() if s.get("id") == step_id)


def _allowed_tools() -> list:
    args = _by_id("claude")["with"]["claude_args"]
    return args.split('--allowedTools "', 1)[1].split('"', 1)[0].split(",")


def test_model_tools_have_no_edit_write_git_or_make():
    tools = _allowed_tools()
    assert "Edit" not in tools and "Write" not in tools
    assert not [t for t in tools if t.startswith(("Bash(git", "Bash(make", "Bash(gh pr create"))]
    assert {"Read", "Glob", "Grep"} <= set(tools)
    assert [t for t in tools if t.startswith(("Edit", "Write"))] == ["Edit(.agent-out/**)"]  # body files only (#620)


def test_model_token_has_no_contents_scope():
    scopes = {k for k in _by_id("app")["with"] if k.startswith("permission-")}
    assert "permission-contents" not in scopes
    assert {"permission-pull-requests", "permission-issues"} <= scopes


def test_workflow_default_token_is_read_only():
    assert _doc()["permissions"] == {"contents": "read"}


def test_model_step_sees_only_the_app_token():
    claude = _by_id("claude")
    assert claude["env"]["GH_TOKEN"] == "${{ steps.app.outputs.token }}"
    assert "handover-app" not in str(claude)


def test_handover_is_committed_by_script_and_pushed_with_its_own_token():
    steps = _steps()
    claude = next(i for i, s in enumerate(steps) if s.get("id") == "claude")
    app = next(i for i, s in enumerate(steps) if s.get("id") == "handover-app")
    push = next(i for i, s in enumerate(steps) if "Push the handover branch" in s.get("name", ""))
    assert claude < app < push
    assert steps[app]["with"]["permission-contents"] == "write"
    assert steps[push]["env"]["GH_TOKEN"] == "${{ steps.handover-app.outputs.token }}"
    commit = next(s for s in steps if s.get("id") == "handover-commit")
    assert "handover-app" not in str(commit)
    assert "handover_text.py" in commit["run"] and "git commit" in commit["run"]


def test_model_prompt_asks_for_the_markers_the_script_reads():
    prompt = _by_id("claude")["with"]["prompt"]
    assert handover_text.BEGIN in prompt and handover_text.END in prompt
    assert "write no file" in prompt
