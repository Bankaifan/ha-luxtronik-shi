"""Guards for agent-review.yml: the script re-approval sits before the model and runs only from the default branch."""
import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent.parent / ".github" / "workflows" / "agent-review.yml"
TEXT = WORKFLOW.read_text(encoding="utf-8")


def step_index(marker):
    return TEXT.index(marker)


def test_reapprove_step_sits_between_round_and_model():
    assert step_index("id: round") < step_index("id: reapprove") < step_index("id: claude")


def test_model_step_is_skipped_after_a_script_approval():
    claude = TEXT[step_index("id: claude"):]
    assert "steps.reapprove.outputs.approved != 'true'" in claude.split("env:")[0]


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
    assert TEXT.count("permission-") == 1
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
