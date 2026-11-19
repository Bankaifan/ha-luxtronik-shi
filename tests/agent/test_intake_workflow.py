"""intake.yml keeps the order of the untrusted-text boundary (decision 0013) for text written by outsiders."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
TEXT = (ROOT / ".github" / "workflows" / "intake.yml").read_text(encoding="utf-8")


def test_switch_defaults_to_on_and_is_shown_by_setup():
    assert "(vars.INTAKE || 'on') != 'off'" in TEXT
    setup = (ROOT / ".github" / "workflows" / "setup.yml").read_text(encoding="utf-8")
    assert "INTAKE: ${{ vars.INTAKE }}" in setup and 'row INTAKE on "$INTAKE"' in setup


def test_write_token_is_created_only_after_the_model_step_and_the_validation():
    model, clean, validate, writer, apply = (TEXT.index(s) for s in (
        "anthropics/claude-code-action@", "git clean -fdxq", "outside_intake.py validate", "- id: writer",
        "outside_intake.py apply"))
    assert model < clean < validate < writer < apply
    assert TEXT.count("permission-issues: write") == 1 and "permission-contents: write" not in TEXT
    step = TEXT[model:clean]
    assert "steps.reader" not in step and "steps.writer" not in step and "GH_TOKEN" not in step
    assert '--allowedTools "Read,Glob,Grep,Edit(verdict.json)"' in step


def test_no_outside_text_reaches_an_expression_and_pull_requests_are_skipped():
    for field in ("title", "body", "comment.body", "user.login"):
        assert f"github.event.issue.{field}" not in TEXT and f"github.event.{field}" not in TEXT
    assert "!github.event.issue.pull_request" in TEXT
    assert "ref:" not in TEXT  # the default branch, never anything an event names


def test_all_intake_jobs_share_one_queue_so_a_burst_cannot_pass_the_daily_cap():
    assert "      group: intake\n      cancel-in-progress: false\n" in TEXT and "max-parallel: 1" in TEXT


def test_workflows_whose_tools_compare_with_the_owner_pass_the_owner_of_this_repo():
    for name in ("intake", "unblocker", "risk", "agent-review", "agent-security-review", "workflow-apply"):
        text = (ROOT / ".github" / "workflows" / f"{name}.yml").read_text(encoding="utf-8")
        assert "OWNER: ${{ vars.OWNER || github.repository_owner }}" in text, name
    assert TEXT.count("OWNER: ${{ vars.OWNER") == 2  # the pick job and the intake job
