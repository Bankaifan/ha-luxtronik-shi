"""Read confinement for the judging model steps (design 0004, rule 1)."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / ".github" / "claude-judge-settings.json"
JUDGING = ["agent-review.yml", "agent-security-review.yml", "scout.yml"]
ACTING = ["agent-dev.yml", "agent-fix.yml", "orchestrator.yml", "rule-keeper.yml", "unblocker.yml"]
TOOLS = ["Read", "Glob", "Grep"]
REQUIRED = ["/proc", "/etc", "/root", "/run", "/var", "/home/runner/work/_temp"]


def _deny() -> list[str]:
    assert SETTINGS.is_file(), "workflow-owned settings file is missing"
    return json.loads(SETTINGS.read_text(encoding="utf-8"))["permissions"]["deny"]


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("path", REQUIRED)
def test_deny_rule_present(tool, path):
    assert f"{tool}(/{path}/**)" in _deny()


def test_workspace_not_denied():
    """The checkout lives under /home/runner/work/<repo>; denying all of /home would blind the model."""
    for rule in _deny():
        assert not re.fullmatch(r"\w+\(//(home|home/runner|home/runner/work)/\*\*\)", rule), rule


@pytest.mark.parametrize("name", JUDGING)
def test_step_passes_settings(name):
    text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    assert "--settings .github/claude-judge-settings.json" in text


@pytest.mark.parametrize("name", ACTING)
def test_acting_step_passes_settings(name):
    text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    assert "--settings .github/claude-judge-settings.json" in text


def test_every_claude_code_action_workflow_is_covered():
    """A new workflow using claude-code-action must be listed above, so it cannot skip the deny settings."""
    users = {
        p.name
        for p in (ROOT / ".github" / "workflows").glob("*.yml")
        if "anthropics/claude-code-action" in p.read_text(encoding="utf-8")
    }
    assert users == set(JUDGING) | set(ACTING)


@pytest.mark.parametrize("name", JUDGING)
def test_judging_step_has_no_write_tools(name):
    text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    allowed = re.search(r'--allowedTools "([^"]*)"', text).group(1)
    names = {t.split("(")[0] for t in allowed.split(",")}
    assert not names & {"Edit", "Write", "MultiEdit"}
    assert "Bash" not in allowed.replace("Bash(", "")
