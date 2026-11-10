"""Guards for the answer receiver workflow (design 0006 section 4.1/4.2, design 0004 rules 1 to 4)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT = (ROOT / ".github" / "workflows" / "answer-receiver.yml").read_text(encoding="utf-8")


def _blocks():
    return re.split(r"\n      - ", TEXT)


def _step(name_part: str) -> str:
    return next(b for b in _blocks() if name_part in b.split("\n", 1)[0] or f"id: {name_part}" in b)


def _model_step() -> str:
    return _step("claude")


def test_trigger_and_gate():
    assert "issue_comment:" in TEXT and "types: [created]" in TEXT
    assert "(vars.ANSWER_RECEIVER || 'on') != 'off'" in TEXT
    assert "github.event.comment.author_association == 'OWNER'" in TEXT
    assert "github.event.comment.user.type != 'Bot'" in TEXT
    assert "github.event.comment.user.login == (vars.OWNER || 'Bankaifan')" in TEXT
    assert "contains(github.event.issue.labels.*.name, 'needs-human')" in TEXT


def test_debounce_and_concurrency():
    assert "concurrency:" in TEXT and "cancel-in-progress: false" in TEXT
    assert "answer-receiver-${{ github.event.issue.number }}" in TEXT
    assert "sleep 45" in TEXT
    assert TEXT.index("sleep 45") < TEXT.index("answer.py gate")


def test_workflow_permissions_read_only():
    assert re.search(r"^permissions:\n  contents: read\n", TEXT, re.MULTILINE)


def test_checkout_is_main_without_credentials():
    block = _step("actions/checkout")
    assert "persist-credentials: false" in block and "default_branch" in block
    assert "pull_request.head" not in TEXT


def test_read_token_is_read_only():
    block = _step("reader")
    assert "permission-contents: read" in block
    assert not re.search(r"permission-[a-z-]+: write", block)


def test_model_step_has_no_token_and_no_bash():
    block = _model_step()
    assert "GH_TOKEN" not in block
    assert "steps.reader" not in block and "steps.writer" not in block
    allowed = re.search(r'--allowedTools "([^"]*)"', block).group(1)
    assert {t.split("(")[0] for t in allowed.split(",")} == {"Read", "Glob", "Grep", "Edit"}
    assert "Edit(verdict.json)" in allowed.split(",")
    assert "Bash" not in block.replace("no shell", "")


def test_model_step_is_confined():
    assert "--settings .github/claude-judge-settings.json" in _model_step()


def test_no_untrusted_event_text_in_expressions():
    """Only numbers, logins and fixed names reach the job; titles, bodies and comment text never do."""
    for ref in re.findall(r"\$\{\{[^}]*\}\}", TEXT):
        assert not re.search(r"\.(title|body|head\.ref|head_ref)\b", ref), ref


def test_write_token_comes_after_model_and_validation():
    assert TEXT.index("id: claude") < TEXT.index("id: verdict") < TEXT.index("id: writer") < TEXT.index("id: apply")
    block = _step("writer")
    assert "permission-actions: write" in block and "permission-issues: write" in block


def test_write_token_only_in_apply_and_report_steps():
    users = [b for b in _blocks() if "steps.writer.outputs.token" in b]
    assert len(users) == 2
    assert all("anthropics/claude-code-action" not in b for b in users)


def test_validate_runs_with_read_token_only():
    block = _step("Validate the verdict")
    assert "steps.reader.outputs.token" in block and "steps.writer" not in block


def test_clean_step_removes_everything_but_the_verdict():
    block = _step("clean")
    assert "git checkout -- ." in block and "git clean -fdxq" in block
    assert block.index("cp verdict.json") < block.index("git clean")


def test_setup_reports_variable():
    setup = (ROOT / ".github" / "workflows" / "setup.yml").read_text(encoding="utf-8")
    assert "ANSWER_RECEIVER: ${{ vars.ANSWER_RECEIVER }}" in setup
    assert 'row ANSWER_RECEIVER on "$ANSWER_RECEIVER"' in setup


def test_orchestrator_skips_receiver_items_and_acts_on_owner_instruction():
    orch = (ROOT / ".github" / "workflows" / "orchestrator.yml").read_text(encoding="utf-8")
    step2 = orch.split("2. For each other PR labeled needs-human", 1)[1].split("3. If HANDOVER", 1)[0]
    assert "<!-- answer-receiver comment=<id> -->" in step2 and "<!-- owner-instruction comment=<id> -->" in step2
    role = (ROOT / ".agents" / "roles" / "orchestrator.md").read_text(encoding="utf-8")
    assert "answer-receiver comment=<id>" in role and "owner-instruction comment=<id>" in role
