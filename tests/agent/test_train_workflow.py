"""Guards for the train workflow (design 0003, 4.3): triggers, permissions, token use, no PR code."""

import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent.parent / ".github" / "workflows" / "train.yml"


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _code() -> str:
    """Workflow text without comment lines."""
    return "\n".join(line for line in _text().splitlines() if not line.lstrip().startswith("#"))


def _on_block() -> str:
    code = _code()
    return code.split("\non:\n", 1)[1].split("\npermissions:", 1)[0]


def test_triggers_are_push_to_main_schedule_and_dispatch_only():
    block = _on_block()
    top = re.findall(r"^  (\w+):", block, flags=re.MULTILINE)
    assert top == ["push", "schedule", "workflow_dispatch"]
    assert "branches: [main]" in block
    assert "cron:" in block


def test_no_pull_request_triggers_anywhere():
    code = _code()
    for bad in ("pull_request", "workflow_run", "issue_comment"):
        assert bad not in code, bad


def test_workflow_permissions_are_contents_read_only():
    code = _code()
    assert "\npermissions:\n  contents: read\nconcurrency:" in code
    assert code.count("permissions:") == 1


def test_token_is_the_author_app_token_not_github_token():
    code = _code()
    assert "actions/create-github-app-token@" in code
    assert "GH_TOKEN: ${{ steps.app.outputs.token }}" in code
    assert "secrets.GITHUB_TOKEN" not in code
    assert "github.token" not in code
    # Minimal app scopes: what update-branch, labels and the agent-fix dispatch need.
    scopes = re.findall(r"permission-([\w-]+): (\w+)", code)
    assert sorted(scopes) == [("actions", "write"), ("contents", "write"), ("issues", "write"), ("pull-requests", "write")]


def test_checkout_is_main_without_credentials_and_no_pr_ref():
    code = _code()
    assert "persist-credentials: false" in code
    assert "ref: ${{ github.event.repository.default_branch }}" in code
    for bad in ("github.head_ref", "pull_request.head", "head.sha", "head.ref", "refs/pull"):
        assert bad not in code, bad


def test_runs_are_serialised_without_cancelling():
    code = _code()
    assert "group: train" in code
    assert "cancel-in-progress: false" in code


def test_kill_switch_and_script_call():
    code = _code()
    assert "if: (vars.TRAIN || 'on') != 'off'" in code
    assert "run: python3 tools/train.py" in code


def test_no_expression_is_interpolated_into_a_run_script():
    """Expressions go through env: only, never into a run: body (design 0004)."""
    lines = _code().splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("run:"):
            body = [line]
            if line.strip() == "run: |":
                body = []
                for nxt in lines[i + 1 :]:
                    if nxt.strip() and not nxt.startswith(" " * 10):
                        break
                    body.append(nxt)
            assert "${{" not in "\n".join(body), body
