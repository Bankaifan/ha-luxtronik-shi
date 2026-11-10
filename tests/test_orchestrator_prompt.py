import re
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "orchestrator.yml"

# Calls the orchestrator tried in runs that ended silently (issue #57); none may be allowed.
DENIED = ["gh issue close", "gh workflow list", "gh api", "git checkout", "git switch", "git fetch", "git -c", "gh run view"]


def test_prompt_names_the_calls_that_are_not_allowed():
    text = WF.read_text(encoding="utf-8")
    for call in DENIED:
        assert f"`{call}" in text, call


def test_allow_list_does_not_contain_the_denied_calls():
    text = WF.read_text(encoding="utf-8")
    allowed = re.search(r'--allowedTools "([^"]*)"', text).group(1)
    for call in DENIED:
        assert f"Bash({call}" not in allowed, call


def test_handover_is_stale_only_on_material_change_and_one_pr_per_day():
    # Issue #341: 13 of 30 merged PRs were handover PRs because "stale" was never defined.
    # Whitespace is flattened so the YAML line wrapping does not matter.
    text = WF.read_text(encoding="utf-8")
    prompt = " ".join(text[text.index("prompt: |"):text.index("claude_args:")].split())
    assert "HANDOVER.md is stale only if the open PR set, the trusted list, the main CI state or an Open/Next item" in prompt
    assert "changed materially since the file was written" in prompt
    assert "A run number, a timestamp or a new day alone is never a reason" in prompt
    assert "At most one handover PR per UTC day" in prompt
    assert "head:agent/orchestrator-handover-<date>" in prompt
    assert "leave HANDOVER.md untouched" in prompt
    assert "If HANDOVER.md is stale: run" not in prompt


def test_prompt_forbids_pipes_inside_jq():
    # Run 42828222608: `gh issue view ... --jq {labels:...|...}` was denied because the unquoted `|` is a shell pipe.
    text = WF.read_text(encoding="utf-8")
    assert "inside `--jq` write a plain" in text
    assert "no `|`, `{` or `}`" in text
    prompt = text[text.index("prompt: |"):text.index("claude_args:")]
    # A --jq argument (no spaces) that contains a pipe is the denied form; the instruction line itself is fine.
    assert not re.search(r"--jq\s+\S*\|", prompt)
