import re
from pathlib import Path

WF = Path(__file__).resolve().parent.parent.parent / ".github" / "workflows" / "orchestrator.yml"

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


def test_prompt_forbids_rm_and_keeps_body_files_in_git_ignored_agent_out():
    # Run 42889616904 ended silently: `rm slip-116.md` was denied. Body files stay in .agent-out/, which the workflow excludes.
    text = WF.read_text(encoding="utf-8")
    assert "`rm` (run 42889616904" in text
    assert "`.agent-out/<name>.md`" in text
    assert 'echo ".agent-out/" >> .git/info/exclude' in text
    allowed = re.search(r'--allowedTools "([^"]*)"', text).group(1)
    assert "Bash(rm" not in allowed


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


def _prompt():
    text = WF.read_text(encoding="utf-8")
    return " ".join(text[text.index("prompt: |"):text.index("claude_args:")].split())


def test_prompt_starts_every_issue_the_script_names():
    # One run started one issue ("pick the next issue"); the script now names all issues that fit the free slots.
    prompt = _prompt()
    assert "Start ALL of these issues in this run, in this order: ${{ steps.pre.outputs.start }}" in prompt
    assert "an empty list means start nothing" in prompt
    assert "Never start an issue that is not in that start list" in prompt
    assert "${{ steps.cand.outputs.list }}" in prompt and "never pick or read any other issue" in prompt
    assert "pick the next issue" not in prompt
    assert "A prio:1 issue may start even with 2 open agent:dev issues" not in prompt


def test_design_split_issues_run_in_parallel_with_depends_on_lines():
    prompt = _prompt()
    assert "in the order of the design's split" not in prompt
    assert "split issues run in parallel" in prompt
    assert "carries a `Depends on: #N` line and the script holds it back until #N is closed" in prompt
    assert "add a line `Depends on: #<n>[, #<m>]` (alone on its line, after the `Design:` line)" in prompt
    assert "steps without that need get no such line" in prompt


def test_caps_default_to_4_and_5_in_every_repo():
    text = WF.read_text(encoding="utf-8")
    assert "MAX_DEV: ${{ vars.MAX_DEV || '4' }}" in text and "MAX_PRS: ${{ vars.MAX_PRS || '5' }}" in text
    assert "Bankaifan/agent-template" not in text


def test_author_app_issue_edits_do_not_start_a_run():
    """Status issue edits by the author app must be skipped at job level: a waiting run of them replaced the
    pending label or dispatch run in the concurrency group, which GitHub then cancelled."""
    text = Path(".github/workflows/orchestrator.yml").read_text(encoding="utf-8")
    cond = text.split("orchestrate:", 1)[1].split("concurrency:", 1)[0]
    assert "github.event.action == 'edited'" in cond
    assert "format('[\"{0}\",\"{0}[bot]\"]', vars.AUTHOR_BOT)), github.event.sender.login)" in cond  # both login forms
