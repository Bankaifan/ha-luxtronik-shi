"""Guards for agent-security-review.yml: staging by script (design 0010 section 4.2), turns from a step output."""
import re
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "agent-security-review.yml"
TEXT = WORKFLOW.read_text(encoding="utf-8")


def idx(marker):
    return TEXT.index(marker)


def test_stage_step_runs_the_script_before_the_model_step():
    assert idx("id: pr") < idx("id: stage") < idx("id: claude")
    block = TEXT[idx("id: stage"):idx("id: claude")]
    assert "python3 tools/ci/stage_review.py .review" in block
    assert '>> "$GITHUB_OUTPUT"' in block


def test_max_turns_comes_from_the_stage_output_not_model_text():
    claude = TEXT[idx("id: claude"):]
    assert "--max-turns ${{ steps.stage.outputs.turns }}" in claude
    assert "--max-turns 12" not in TEXT
    assert not re.search(r"--max-turns \S*steps\.claude", TEXT)


def test_stage_step_is_skipped_with_the_model_step():
    stage = TEXT[idx("id: stage"):idx("id: claude")]
    assert "steps.pr.outputs.skip != 'true'" in stage


def test_prompt_names_the_skipped_list():
    prompt = TEXT[idx("id: claude"):]
    assert ".review/skipped.txt" in prompt and ".review/pr.diff" in prompt


def test_no_new_secret_reaches_the_stage_or_model_step():
    stage = TEXT[idx("Stage the change as files"):idx("id: claude")]
    assert "secrets." not in stage
    assert stage.count("GH_TOKEN: ${{ steps.app.outputs.token }}") == 1
    assert TEXT.count("secrets.") == 2  # APPROVER_APP_KEY (token step) and CLAUDE_CODE_OAUTH_TOKEN (model step)
    model = TEXT[idx("id: claude"):idx("Post the verdict")]
    assert model.count("secrets.") == 1 and "secrets.CLAUDE_CODE_OAUTH_TOKEN" in model


def test_stage_step_takes_untrusted_values_only_through_env():
    run = TEXT[idx("id: stage"):idx("id: claude")].split("run: |")[1]
    assert "${{" not in run
