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


def test_a_run_without_a_pr_on_a_closed_issue_is_not_escalated():
    """agent-template #751: #745 was closed while its developer run found nothing to change; the guard still counted
    the run as silent and opened a stuck issue. Only a state read as CLOSED skips the guard."""
    text = (ROOT / ".github" / "workflows" / "agent-dev.yml").read_text(encoding="utf-8")
    step = text[text.index("Escalate a run that produced no PR"):]
    closed = 'if [ "$(gh issue view "$ISSUE" --json state --jq .state || true)" = CLOSED ]; then'
    assert closed in step and step.index(closed) < step.index("agent_guard.py\" silent dev")
    assert "nothing to escalate\"; exit 0" in step


def test_the_pr_title_is_set_by_script_after_the_pr_is_found():
    text = (ROOT / ".github" / "workflows" / "agent-dev.yml").read_text(encoding="utf-8")
    step = text[text.index("Give the PR the task ID of its issue (no model)"):text.index("- id: ci-app")]
    assert text.index("Find the open PR of this issue") < text.index("Give the PR the task ID of its issue")
    assert "steps.pr.outputs.num != ''" in step and 'tools/pr_title.py" fix "$PR" || echo' in step
    assert "GH_TOKEN: ${{ steps.app.outputs.token }}" in step and "GUARD_KEY" not in step


def test_a_run_that_says_it_had_nothing_to_build_is_settled_before_the_guard():
    text = (ROOT / ".github" / "workflows" / "agent-dev.yml").read_text(encoding="utf-8")
    assert "rm -rf .agent-out && mkdir .agent-out" in text[text.index("- id: started"):text.index("- id: claude")]
    assert ".agent-out/nothing-to-build.md" in text[text.index("- id: claude"):text.index("claude_args:")]
    step = text[text.index("Settle a run that had nothing to build (no model)"):text.index("Escalate a run that produced no PR")]
    assert "steps.pr.outputs.num == ''" in step and 'no_build.py" settle "$ISSUE" .agent-out/nothing-to-build.md' in step
    assert "GUARD_KEY" not in step
    escalate = text[text.index("Escalate a run that produced no PR"):]
    assert "steps.nobuild.outputs.settled != 'true'" in escalate.split("env:")[0]


def test_only_a_template_sync_issue_gets_the_wider_turn_cap():
    # a sync issue ports files one by one and ran 110 to 126 turns: 60 marked every such run red after the work was done
    assert "--max-turns ${{ steps.template.outputs.dir && '150' || '60' }}" in WORKFLOW
    assert WORKFLOW.count("--max-turns") == 1
    assert WORKFLOW.count('echo "dir=.template" >> "$GITHUB_OUTPUT"') == 1  # the only writer of that output
    assert WORKFLOW.index("id: template") < WORKFLOW.index("--max-turns")

