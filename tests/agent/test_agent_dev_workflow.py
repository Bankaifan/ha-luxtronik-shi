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


def test_sync_issue_materializes_conflicted_files_before_the_model():
    # design 0014, 3 H: the developer gets ours/base/theirs of each conflicted file, after the template download
    # and before the model runs; the step is skipped (the `No template sync` exit) for any other issue.
    materialize = WORKFLOW.index("python3 tools/template_sync.py materialize")
    assert WORKFLOW.index("codeload.github.com") < materialize < WORKFLOW.index("id: claude")
    assert WORKFLOW.index('echo "No template sync"') < materialize


def test_prompt_names_the_three_versions_of_a_conflicted_file():
    assert "<path>.ours" in WORKFLOW
    assert "<path>.base" in WORKFLOW
    assert "<path>.theirs" in WORKFLOW
