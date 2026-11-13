"""Guard for agent-fix.yml: a review on a merged or closed PR must not start a fix run (#311)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
TEXT = (ROOT / ".github" / "workflows" / "agent-fix.yml").read_text(encoding="utf-8")


def test_review_on_closed_pr_starts_no_fix_round():
    check = 'gh pr view "$pr" --json state --jq .state'
    assert check in TEXT
    review_branch = TEXT.index('pr="$REVIEW_PR"; branch="$REVIEW_BRANCH"')
    approved_check = TEXT.index('if [ "$REVIEW_STATE" = approved ]')
    assert review_branch < TEXT.index(check) < approved_check
