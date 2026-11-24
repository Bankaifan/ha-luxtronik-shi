"""Guards for agent-review.yml: the script re-approval sits before the model and runs only from the default branch."""
import json
import re
import shlex
from pathlib import Path

import pytest
import review_select

ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "agent-review.yml"
TEXT = WORKFLOW.read_text(encoding="utf-8")


def step_index(marker):
    return TEXT.index(marker)


def test_reapprove_step_sits_between_round_and_model():
    assert step_index("id: round") < step_index("id: reapprove") < step_index("id: claude")


def test_model_step_is_skipped_after_a_script_approval():
    claude = TEXT[step_index("id: claude"):]
    assert "steps.reapprove.outputs.approved != 'true'" in claude.split("env:")[0]


def test_a_refused_batch_is_never_reviewed_by_the_model():
    after = TEXT[step_index("id: reapprove"):step_index("Request the code owner's review")]
    assert after.count("&& env.BRANCH != 'agent/batch'\n") == after.count("\n        if: ") - 1 == 4


def test_the_batch_pr_counts_no_review_round_and_is_never_parked():
    block = TEXT[step_index("id: round"):step_index("id: reapprove")]
    gate = block.index('if [ "$BRANCH" = agent/batch ] && guard same "$author" "$AUTHOR_BOT"; then')
    assert gate < block.index("else", gate) < block.index("guard round") < block.index("guard park") < block.index("\n          fi\n", gate)
    assert block.count("guard round") == block.count("guard park") == 1


def test_reapprove_never_fails_the_job_and_gets_sha_from_env():
    block = TEXT[step_index("id: reapprove"):step_index("id: claude")]
    assert 'if python3 tools/reapprove.py "$PR" "$SHA"; then' in block
    assert "${{ github.event.workflow_run" not in block.split("run: |")[1]  # untrusted values only through env


def test_trigger_is_workflow_run_and_no_pull_request_event():
    head = TEXT.split("jobs:")[0]
    assert "workflow_run:" in head
    assert not re.search(r"^\s*pull_request(_target)?:", TEXT, re.MULTILINE)


def test_checkout_is_the_default_branch_and_never_the_pr_head():
    checkout = TEXT[step_index("actions/checkout@"):step_index("id: round")]
    assert "ref: ${{ github.event.repository.default_branch }}" in checkout
    assert "persist-credentials: false" in checkout
    assert "head_sha" not in checkout and "head_branch" not in checkout


def test_approver_token_scope_is_unchanged():
    assert "permission-pull-requests: write" in TEXT
    scopes = re.findall(r"(?m)^\s+(permission-[a-z-]+: \w+)", TEXT)  # token scopes, not --permission-mode
    assert scopes == ["permission-pull-requests: write", "permission-actions: write"]
    model = TEXT[step_index("id: claude"):step_index("id: again")]
    assert "steps.app.outputs.token" in model and "ci-app" not in model  # the actions token is made after the model step
    assert "permissions:\n  contents: read\n  pull-requests: read\n" in TEXT


SEC = (WORKFLOW.parent / "agent-security-review.yml").read_text(encoding="utf-8")


def test_superseded_heads_are_cancelled_in_both_reviews():
    assert "cancel-in-progress: true" in TEXT and "cancel-in-progress: false" not in TEXT
    assert "cancel-in-progress: true" in SEC and "cancel-in-progress: false" not in SEC


def test_cancelled_runs_report_nothing():
    for text in (TEXT, SEC):
        assert "always()" not in text.split("jobs:")[1]


def test_reviewer_reads_staged_files_before_the_model_runs():
    assert step_index("id: reapprove") < step_index("Stage the change as files") < step_index("id: claude")
    block = TEXT[step_index("Stage the change as files"):step_index("id: claude")]
    assert "> .review/pr.diff" in block and ".review/files/" in block
    prompt = TEXT[step_index("id: claude"):]
    assert ".review/pr.diff" in prompt and "Bash(gh pr diff" not in prompt


def test_staging_loops_url_encode_the_path():
    # agent-review keeps its inline loop; the security review stages through tools/ci/stage_review.py (urllib quote)
    assert "@uri" in TEXT
    assert "contents/$enc?ref=$SHA" in TEXT
    assert "contents/$f?ref" not in TEXT
    assert "contents/$f?ref" not in SEC


def test_delta_is_staged_after_the_full_change_and_prompt_scopes_to_it():
    assert step_index("Stage the change as files") < step_index("Stage the delta since") < step_index("id: claude")
    block = TEXT[step_index("Stage the delta since"):step_index("id: claude")]
    assert 'python3 tools/review_delta.py "$PR" "$SHA"' in block
    prompt = TEXT[step_index("id: claude"):]
    assert ".review/delta.diff" in prompt and ".review/pr.diff" in prompt
    role = (WORKFLOW.parent.parent.parent / ".agents" / "roles" / "reviewer.md").read_text(encoding="utf-8")
    assert ".review/delta.diff" in role and ".review/prior-findings.md" in role and "widen" in role


def test_body_hash_and_one_review_per_head_are_unchanged():
    block = TEXT[step_index("id: round"):step_index("id: reapprove")]
    assert 'guard body-hash "$num"' in block and 'guard reviewed "$num" "$SHA" "$bhash"' in block
    assert 'guard round "$num" "$SHA"' in block


def test_developer_role_names_the_current_pr_body_file():
    role = (WORKFLOW.parent.parent.parent / ".agents" / "roles" / "developer.md").read_text(encoding="utf-8")
    assert ".agent-out/pr-body.md" in role and "/tmp/pr-body.md" not in role


def test_review_round_is_counted_per_head_not_per_label_case():
    block = TEXT[step_index("id: round"):step_index("id: reapprove")]
    assert 'guard round "$num" "$SHA"' in block
    assert "guard label pr \"$num\" review:" not in block


def test_a_run_without_a_review_is_repeated_once_per_head_before_the_guard_acts():
    """First silent run on a head: label silent:<sha7> and validate starts again. The guard only acts when no second
    run was started (the head already carries the label, or a step of the repeat failed)."""
    assert step_index("id: claude") < step_index("id: again") < step_index("id: ci-app") < step_index("id: redo")
    assert step_index("id: redo") < step_index("Escalate a run that left no review")
    again = TEXT[step_index("id: again"):step_index("id: ci-app")]
    assert 'guard reviewed "$PR" "$SHA"' in again and 'mark="silent:${SHA:0:7}"' in again
    assert again.index("the guard takes over") < again.index('guard label pr "$PR" "$mark"') < again.index("retry=true")
    redo = TEXT[step_index("id: ci-app"):step_index("Escalate a run that left no review")]
    assert redo.count("steps.again.outputs.retry == 'true'") == 2
    assert 'gh workflow run validate.yml --ref "$BRANCH"' in redo and "GH_TOKEN: ${{ steps.ci-app.outputs.token }}" in redo
    escalate = TEXT[step_index("Escalate a run that left no review"):]
    assert "steps.redo.outcome != 'success'" in escalate and "agent_guard.py silent review" in escalate


def test_the_reviewer_is_told_to_use_single_commands_and_the_read_tools():
    prompt = TEXT[step_index("id: claude"):step_index("id: again")]
    assert "one per Bash call" in prompt and "no `cd`, `cat`," in prompt and "A denied call is no reason to stop" in prompt


def claude_args():
    """The model step's arguments as the action sees them: YAML fold first, then a shell-style split."""
    yaml = pytest.importorskip("yaml")  # installed by tools/ci/install_tools.sh
    steps = yaml.safe_load(TEXT)["jobs"]["review"]["steps"]
    step = next(s for s in steps if s.get("id") == "claude")
    return shlex.split(step["with"]["claude_args"])


def test_specialists_are_defined_inline_read_only_on_haiku():
    args = claude_args()
    assert args.count("--agents") == 1
    agents = json.loads(args[args.index("--agents") + 1])
    assert sorted(agents) == sorted(review_select.SPECIALISTS) and len(agents) == 3
    for name, agent in agents.items():
        assert agent["tools"] == ["Read", "Glob", "Grep"] and agent["model"] == "haiku"
        assert agent["description"].strip()
        role = f".agents/roles/{name}.md"
        assert role in agent["prompt"] and (ROOT / role).is_file()


def test_the_lead_may_start_subagents_and_keeps_its_other_arguments():
    args = claude_args()
    allowed = args[args.index("--allowedTools") + 1].split(",")
    assert {"Agent", "Task"} <= set(allowed)
    assert args[args.index("--model") + 1] == "sonnet" and args[args.index("--max-turns") + 1] == "30"
    assert args[args.index("--settings") + 1] == ".github/claude-judge-settings.json"  # the --agents JSON swallowed nothing


def test_specialists_are_picked_by_script_between_the_delta_and_the_model():
    pick = step_index("python3 tools/review_select.py .review")
    assert step_index("Stage the delta since") < pick < step_index("id: claude")
    step = TEXT[TEXT.rindex("\n      - ", 0, pick):pick]
    assert "steps.round.outputs.skip != 'true' && steps.reapprove.outputs.approved != 'true' && env.BRANCH != 'agent/batch'" in step
    assert "continue-on-error" not in step and "||" not in step  # a missing diff fails the job, no empty selection


def test_a_reviewed_head_ends_the_red_streak_and_a_failure_fails_the_step():
    block = TEXT[step_index("id: round"):step_index("id: reapprove")]
    green = block.index('python3 tools/review_rounds.py green "$num"')
    assert block.index('guard round "$num" "$SHA"') < green < block.index('echo "pr=$num"')
    line = block[green:block.index("\n", green)]
    assert line == 'python3 tools/review_rounds.py green "$num"'  # no `||`: a stale streak would park the PR wrongly
    assert "set -euo pipefail" in block[:green] or "set -e" in block[:green]
