"""rule-keeper (issue #203): the model is denied `git checkout -b`, so a script step creates the branch."""
import re
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "rule-keeper.yml"
TEXT = WF.read_text(encoding="utf-8")
PROMPT = TEXT[TEXT.index("prompt: |"):TEXT.index("claude_args:")]
ALLOWED = re.search(r'--allowedTools "([^"]*)"', TEXT).group(1)
BRANCH_CALLS = ["git checkout", "git switch"]


def test_branch_is_created_by_a_script_step_before_the_model():
    step = TEXT.index("id: branch")
    model = TEXT.index("id: claude")
    assert step < model
    assert 'git checkout -b "$branch"' in TEXT[step:model]
    assert 'echo "branch=$branch" >> "$GITHUB_OUTPUT"' in TEXT[step:model]


def test_prompt_uses_the_branch_and_never_creates_one():
    for call in BRANCH_CALLS:
        assert call not in PROMPT, call
    assert "steps.branch.outputs.branch" in PROMPT


def test_allow_list_has_no_branch_commands_and_keeps_commit_and_push():
    assert "Bash(git:*)" not in ALLOWED
    for call in BRANCH_CALLS:
        assert f"Bash({call}" not in ALLOWED, call
    assert "Bash(git commit:*)" in ALLOWED
    assert "Bash(git push origin HEAD)" in ALLOWED


def test_allow_list_is_exact_and_has_no_make_wildcard_or_rm():
    assert "make:*" not in ALLOWED
    assert "rm:*" not in ALLOWED
    assert ALLOWED.split(",") == [
        "Read", "Glob", "Grep", "Edit", "Write",
        "Bash(gh pr list:*)", "Bash(gh pr view:*)", "Bash(gh issue list:*)", "Bash(gh issue view:*)",
        "Bash(git add:*)", "Bash(git commit:*)", "Bash(git push origin HEAD)",
        "Bash(git status:*)", "Bash(git diff:*)", "Bash(gh pr create:*)",
        "Bash(make check)", "Bash(date:*)", "Bash(wc:*)", "Bash(ls:*)",
    ]
