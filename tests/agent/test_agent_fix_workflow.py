"""Guard for agent-fix.yml: a review on a merged or closed PR must not start a fix run (#311)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TEXT = (ROOT / ".github" / "workflows" / "agent-fix.yml").read_text(encoding="utf-8")
GATE = "steps.open.outputs.open == 'true'"


def test_review_on_closed_pr_starts_no_fix_round():
    check = 'gh pr view "$pr" --json state --jq .state'
    assert check in TEXT
    review_branch = TEXT.index('pr="$REVIEW_PR"; branch="$REVIEW_BRANCH"')
    approved_check = TEXT.index('if [ "$REVIEW_STATE" = approved ]')
    assert review_branch < TEXT.index(check) < approved_check


def _fix_steps():
    job = TEXT[TEXT.index("\n  fix:\n") :]
    body = job[job.index("\n    steps:\n") + len("\n    steps:\n") :]
    return [s for s in re.split(r"(?m)^      - ", body) if s.strip()]


def test_fix_job_rechecks_open_before_checkout():
    steps = _fix_steps()
    idx = next(i for i, s in enumerate(steps) if s.startswith("id: open"))
    assert 'gh pr view "$PR" --json state' in steps[idx]
    checkout = next(i for i, s in enumerate(steps) if "uses: actions/checkout@" in s)
    assert idx < checkout


def test_fix_job_steps_after_open_are_all_gated():
    steps = _fix_steps()
    idx = next(i for i, s in enumerate(steps) if s.startswith("id: open"))
    after = steps[idx + 1 :]
    assert len(after) >= 10
    for s in after:
        ifs = re.findall(r"(?m)^\s+if: (.*)$", s)
        assert len(ifs) == 1 and GATE in ifs[0], f"ungated step after open:\n{s[:200]}"
    # The agent run and checkout are among the gated steps.
    assert any("uses: actions/checkout@" in s for s in after)
    assert any("anthropics/claude-code-action@" in s for s in after)


def test_a_failed_hand_over_parks_with_the_marker_comment_so_the_cool_down_grows():
    assert 'guard park pr "$pr"' in TEXT and "label pr \"$pr\" parked" not in TEXT


def test_the_batch_pr_gets_no_fix_round_whatever_started_the_run():
    gate = TEXT.index('if [ "$branch" = agent/batch ]; then echo "Batch PR: no fix round"; echo "fix=false"')
    assert TEXT.index('branch="$RUN_BRANCH"') < gate < TEXT.index('echo "pr=$pr" >> "$GITHUB_OUTPUT"')  # before any label


def test_a_run_without_a_fix_is_repeated_once_per_head_before_the_guard_acts():
    """First run with the same head and body: label silent:<sha7> and one more run (why=retry). The guard only acts
    when no second run was started (the head already carries the label, or a step of the repeat failed)."""
    again = TEXT[TEXT.index("id: again"):TEXT.index("id: redo")]
    assert '!= "$HEAD_BEFORE" ]; then exit 0; fi' in again and 'cmp -s - "$RUNNER_TEMP/body-before.txt"' in again
    assert 'approval.py" check "$PR")" = approved ]; then exit 0; fi' in again  # nothing to fix is not silent
    assert again.index("the guard takes over") < again.index('label pr "$PR" "$mark"') < again.index("retry=true")
    assert "gh workflow run" not in again and "ci-app" not in again
    redo = TEXT[TEXT.index("id: redo"):TEXT.index("Escalate a run that pushed no fix")]
    assert "steps.again.outputs.retry == 'true'" in redo and 'gh workflow run agent-fix.yml -f pr="$PR" -f why=retry' in redo
    escalate = TEXT[TEXT.index("Escalate a run that pushed no fix"):]
    assert "steps.redo.outcome != 'success'" in escalate and "agent_guard.py\" silent fix" in escalate
    assert "options: [conflict, retry]" in TEXT and "default: conflict" in TEXT  # the status run's dispatch stays a conflict


def test_the_fix_prompt_allows_a_rebase_only_never_a_merge_of_main():
    prompt = TEXT[TEXT.index("prompt: |"):TEXT.index("claude_args:")]
    assert "never `git merge`" in prompt and "never `gh pr update-branch`" in prompt and "`retry`: an earlier fix run" in prompt
