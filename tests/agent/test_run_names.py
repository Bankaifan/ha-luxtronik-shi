"""Guards for the workflow-level run-name lines (display only): every agent run shows its subject, never an empty name."""
from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parent.parent.parent / ".github" / "workflows"
NAMED = ["agent-review", "agent-security-review", "dependabot-automerge", "status", "orchestrator", "agent-fix"]


@pytest.mark.parametrize("name", NAMED)
def test_run_name_is_a_quoted_expression_with_fallback(name):
    text = (WORKFLOWS / f"{name}.yml").read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if line.startswith("run-name:")]
    assert len(lines) == 1, name
    value = lines[0].split(":", 1)[1].strip()
    assert value.startswith('"') and "${{" in value, name
    assert "||" in value, name  # a fallback keeps the name non-empty when a context value is missing


@pytest.mark.parametrize("name", NAMED)
def test_run_name_parses_as_yaml_and_is_not_empty(name):
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load((WORKFLOWS / f"{name}.yml").read_text(encoding="utf-8"))
    assert isinstance(data.get("run-name"), str) and data["run-name"].strip(), name


def test_status_names_scheduled_runs_and_triggering_workflow():
    text = (WORKFLOWS / "status.yml").read_text(encoding="utf-8")
    assert "status (scheduled)" in text and "status after {0}" in text


def test_agent_fix_names_pr_on_manual_dispatch():
    text = (WORKFLOWS / "agent-fix.yml").read_text(encoding="utf-8")
    assert "format('PR #{0}', inputs.pr)" in text
