"""Read confinement for the judging model steps (design 0004, rule 1)."""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SETTINGS = ROOT / ".github" / "claude-judge-settings.json"
JUDGING = ["agent-review.yml", "agent-security-review.yml", "scout.yml"]
ACTING = ["agent-dev.yml", "agent-fix.yml", "orchestrator.yml", "rule-keeper.yml", "cleaner.yml", "unblocker.yml",
          "intake.yml"]
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


def _action_steps(name: str) -> list[str]:
    """The text of every step in a workflow that runs claude-code-action."""
    text = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    return [s for s in re.split(r"(?m)^ {6}- ", text) if re.search(r"uses: anthropics/claude-code-action@", s)]


@pytest.mark.parametrize("name", JUDGING + ACTING)
def test_allowed_tools_stay_a_strict_list(name):
    """claude-code-action 1.0.273 starts sessions in auto mode, where a safety review may pass tool calls that no
    allow rule covers. `--permission-mode default` keeps --allowedTools a hard boundary: the rest is denied."""
    steps = _action_steps(name)
    assert steps, name
    for step in steps:
        block = re.search(r"claude_args: >-\n((?: {12}\S.*\n)+)", step)
        assert block, f"{name}: claude-code-action step without claude_args"
        assert re.findall(r"--permission-mode[=\s]+(\S+)", block.group(1)) == ["default"], name
