"""Issue #104: orchestrator runs ended silently because `make check` had no tools and `git -c` was denied."""

from __future__ import annotations

import pathlib

TEXT = (
    pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows" / "orchestrator.yml"
).read_text(encoding="utf-8")


def test_tools_are_installed_before_the_claude_run():
    install = TEXT.index("bash tools/ci/install_tools.sh")
    assert install < TEXT.index("id: claude")


def test_prompt_forbids_git_dash_c_and_cd_prefix():
    assert "plain `git commit -m" in TEXT
    assert "never `git -c ...` and never a `cd` prefix" in TEXT


def _step(name_part: str) -> str:
    """Text of the step whose `name:` contains name_part (up to the next step)."""
    start = TEXT.index(name_part)
    nxt = TEXT.find("\n      - ", start)
    return TEXT[start:nxt if nxt != -1 else len(TEXT)]


def test_event_triggers_exist():
    head = TEXT[: TEXT.index("permissions:")]
    assert "types: [opened, edited, closed, labeled]" in head
    assert "issue_comment:" in head and "types: [created]" in head
    assert "pull_request_target:" in head and "types: [opened, closed]" in head
    assert "pull_request_review:" in head and "types: [submitted]" in head
    for old in ("workflow_run:", "schedule:", "workflow_dispatch:"):
        assert old in head


def test_no_pr_code_checkout():
    assert "github.event.pull_request.head" not in TEXT
    assert "head_ref" not in TEXT
    checkout = TEXT[TEXT.index("actions/checkout@"):TEXT.index("# Checked-out main only")]
    assert "ref:" not in checkout
    assert "zizmor: ignore[dangerous-triggers]" in TEXT[TEXT.index("pull_request_target:"):][:200]


def test_events_switch_guards_the_new_events():
    cond = TEXT[TEXT.index("    if: >-"):TEXT.index("    # Job level on purpose")]
    assert "vars.ORCHESTRATOR_ENABLED == 'true'" in cond
    assert cond.count("vars.ORCHESTRATOR_EVENTS == 'on'") == 2
    assert "pull_request_review" in cond and "issue_comment" in cond
    assert "ORCHESTRATOR_EVENTS: ${{ vars.ORCHESTRATOR_EVENTS }}" in _step("name: Gate")


def test_order_sleep_gate_prefilter_model():
    sleep = TEXT.index("run: sleep 60")
    assert sleep < TEXT.index("- id: app")
    gate = TEXT.index("id: gate")
    assert sleep < gate < TEXT.index("id: pre") < TEXT.index("id: claude")


def test_prefilter_gets_normalised_event_and_facts():
    pre = _step("name: Count work")
    assert "'pull_request_target' && 'pull_request'" in pre
    for key in ("EVENT_ACTION", "EVENT_NUMBER", "EVENT_SENDER", "EVENT_MERGED", "REVIEW_STATE", "REVIEWER"):
        assert f"{key}: ${{{{" in pre


def test_no_untrusted_text_in_run_blocks():
    risky = ("github.event.comment.body", "github.event.issue.title", "github.event.issue.body",
             "github.event.pull_request.title", "github.event.pull_request.body", "github.event.review.body",
             "head_ref")
    # run-name: is display only (never executed), so the issue title may show there; nowhere else in the file.
    without_run_name = "\n".join(line for line in TEXT.splitlines() if not line.startswith("run-name:"))
    for r in risky:
        assert r not in without_run_name
    in_run = False
    for line in TEXT.splitlines():
        s = line.strip()
        if s.startswith(("run: |", "run: >")):
            in_run = True
            continue
        if in_run and s and not line.startswith("          "):
            in_run = False
        if in_run or (s.startswith("run: ") and "${{" in s):
            assert "${{" not in line, line


def test_allowed_tools_not_widened():
    line = next(x for x in TEXT.splitlines() if "--allowedTools" in x)
    assert "Bash(git commit:*)" in line
    assert "Bash(bash" not in line
    assert "Bash(git -c" not in line
