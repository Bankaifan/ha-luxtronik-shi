"""The developer prompt states the allowed Bash forms before the first tool call."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW = (ROOT / ".github" / "workflows" / "agent-dev.yml").read_text()
ROLE = (ROOT / ".agents" / "roles" / "developer.md").read_text()


def test_prompt_forbids_helper_scripts_and_compounds():
    assert "one simple command per Bash call" in WORKFLOW
    assert "no helper scripts" in WORKFLOW
    assert "one plain `cp <src> <dst>` per file" in WORKFLOW


def test_prompt_rule_comes_before_claude_args():
    assert WORKFLOW.index("no helper scripts") < WORKFLOW.index("claude_args:")


def test_role_states_the_rule():
    assert "One simple command per Bash call" in ROLE
    assert "no helper scripts" in ROLE


def test_allowed_tools_not_widened():
    assert "Bash(bash:*)" not in WORKFLOW
    assert "Bash(sed:*)" not in WORKFLOW
