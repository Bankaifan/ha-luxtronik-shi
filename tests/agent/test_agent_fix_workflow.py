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
