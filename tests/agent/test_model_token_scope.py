"""Token scope of the developer and fix model steps (design 0017, step 3): no workflows or actions write on the model token."""

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
# (workflow, job, the command that reports a refused push on the issue or PR)
JOBS = [("agent-dev.yml", "dev", "gh issue comment"), ("agent-fix.yml", "fix", "gh pr comment")]


def _steps(workflow: str, job: str) -> list:
    yaml = pytest.importorskip("yaml")  # installed by tools/ci/install_tools.sh
    doc = yaml.safe_load((ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8"))
    return doc["jobs"][job]["steps"]


def _by_id(steps: list, step_id: str) -> dict:
    return next(s for s in steps if s.get("id") == step_id)


def _by_name(steps: list, name: str) -> dict:
    return next(s for s in steps if s.get("name") == name)


@pytest.mark.parametrize("workflow,job,report", JOBS)
def test_model_token_has_no_workflows_or_actions_scope(workflow, job, report):
    scopes = {k for k in _by_id(_steps(workflow, job), "app")["with"] if k.startswith("permission-")}
    assert "permission-workflows" not in scopes and "permission-actions" not in scopes
    assert {"permission-contents", "permission-pull-requests", "permission-issues"} <= scopes


@pytest.mark.parametrize("workflow,job,report", JOBS)
def test_ci_token_is_actions_only_and_serves_the_ci_steps(workflow, job, report):
    steps = _steps(workflow, job)
    perms = {k: v for k, v in _by_id(steps, "ci-app")["with"].items() if k.startswith("permission-")}
    assert perms == {"permission-actions": "write"}
    for s in steps:
        if "gh workflow run" in s.get("run", ""):
            assert s["env"]["GH_TOKEN"] == "${{ steps.ci-app.outputs.token }}", s["name"]
    assert "ci-app" not in str(_by_id(steps, "claude"))  # the model step never sees the short token
    assert _by_id(steps, "claude")["env"]["GH_TOKEN"] == "${{ steps.app.outputs.token }}"


@pytest.mark.parametrize("workflow,job,report", JOBS)
def test_workflow_changes_are_carried_as_a_patch_after_the_model_step(workflow, job, report):
    steps = _steps(workflow, job)
    idx = [i for i, s in enumerate(steps) if s.get("name") == "Carry workflow changes as a patch"]
    assert len(idx) == 1
    step = steps[idx[0]]
    assert report in step["run"] and '"$RUNNER_TEMP/guard/tools/workflow_patch.py" stash' in step["run"]
    assert step["env"]["GH_TOKEN"] == "${{ steps.app.outputs.token }}"  # the model token: no workflows scope
    assert idx[0] > next(i for i, s in enumerate(steps) if s.get("id") == "claude")


def test_fix_reads_the_failed_log_with_the_short_token():
    steps = _steps("agent-fix.yml", "fix")
    assert _by_name(steps, "Fetch the failed CI log")["env"]["GH_TOKEN"] == "${{ steps.ci-app.outputs.token }}"
