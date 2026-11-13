"""Guards for the unblocker workflow (design 0004 rules 1 to 4, design 0002 section 6)."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
TEXT = (ROOT / ".github" / "workflows" / "unblocker.yml").read_text(encoding="utf-8")


def _step(name_part: str) -> str:
    """Text of the step whose header line contains name_part (up to the next step)."""
    blocks = re.split(r"\n      - ", TEXT)
    return next(b for b in blocks if name_part in b.split("\n", 1)[0] or f"id: {name_part}" in b)


def _model_step() -> str:
    return _step("claude")


def test_trigger_and_gate():
    assert re.search(r"github\.event\.label\.name == 'needs-human'", TEXT)
    assert not re.search(r"label\.name == '(?!needs-human)", TEXT)
    assert "(vars.UNBLOCKER || 'on') != 'off'" in TEXT
    assert "concurrency:" in TEXT and "cancel-in-progress: false" in TEXT


def test_workflow_permissions_read_only():
    assert re.search(r"^permissions:\n  contents: read\n", TEXT, re.MULTILINE)


def test_checkout_is_main_without_credentials():
    block = _step("actions/checkout")
    assert "persist-credentials: false" in block
    assert "default_branch" in block
    assert "pull_request.head" not in TEXT


def test_read_token_is_read_only():
    block = _step("reader")
    assert "permission-contents: read" in block
    assert not re.search(r"permission-[a-z-]+: write", block)


def test_model_step_has_no_token_and_no_bash():
    block = _model_step()
    assert "GH_TOKEN" not in block
    assert "steps.reader" not in block and "steps.writer" not in block
    assert "app.outputs.token" not in block
    allowed = re.search(r'--allowedTools "([^"]*)"', block).group(1)
    names = {t.split("(")[0] for t in allowed.split(",")}
    assert names == {"Read", "Glob", "Grep", "Edit"}
    assert "Edit(verdict.json)" in allowed.split(",")
    assert "Bash" not in block.replace("no shell", "")


def test_model_step_is_confined():
    assert "--settings .github/claude-judge-settings.json" in _model_step()


def test_no_untrusted_event_text_in_run_scripts():
    """Only numbers and fixed names reach shell code; titles, bodies and comments are never interpolated."""
    for ref in re.findall(r"\$\{\{[^}]*\}\}", TEXT):
        assert not re.search(r"\.(title|body|head\.ref|head_ref|name)\b", ref) or "label.name" in ref, ref


def test_model_step_allows_both_bots():
    """The approver app labels PRs too, so its label event starts this run; the action refuses unlisted bots (#457)."""
    assert "allowed_bots: ${{ vars.AUTHOR_BOT }},${{ vars.APPROVER_BOT }}" in _model_step()


def test_write_token_comes_after_model_and_validation():
    assert TEXT.index("id: claude") < TEXT.index("id: writer")
    assert TEXT.index("id: verdict") < TEXT.index("id: writer") < TEXT.index("id: apply")
    block = _step("writer")
    assert "permission-actions: write" in block  # agent-fix dispatch for a class 1 PR


def test_write_token_only_in_apply_and_report_steps():
    users = [b for b in re.split(r"\n      - ", TEXT) if "steps.writer.outputs.token" in b]
    assert len(users) == 2
    assert all("anthropics/claude-code-action" not in b for b in users)


def test_clean_step_removes_everything_but_the_verdict():
    block = _step("clean")
    assert "git checkout -- ." in block and "git clean -fdxq" in block
    assert block.index("cp verdict.json") < block.index("git clean")


@pytest.mark.parametrize("verdict,rc", [
    ({"class": 3, "reason": "x", "note": "Hallo Daniel, soll das Release raus? Frage: ja oder nein?"}, 0),
    ({"class": 7}, 1),
    ({"class": 1, "comment": "token ghp_" + "a" * 36}, 1),
    ({"class": 3, "note": "Hallo Daniel, Frage: ghp_" + "a" * 36}, 1),
    ("not a dict", 1),
])
def test_validate_subcommand(tmp_path, verdict, rc):
    f = tmp_path / "v.json"
    f.write_text(json.dumps(verdict), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "unblock.py"), "validate", str(f)],
                       check=False, capture_output=True, text=True)
    assert r.returncode == rc, r.stdout


def test_validate_subcommand_missing_or_broken_file(tmp_path):
    for content in (None, "{not json"):
        f = tmp_path / "v.json"
        if content is not None:
            f.write_text(content, encoding="utf-8")
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "unblock.py"), "validate", str(f)],
                           check=False, capture_output=True, text=True)
        assert r.returncode == 1


def test_setup_creates_label_and_reports_variable():
    setup = (ROOT / ".github" / "workflows" / "setup.yml").read_text(encoding="utf-8")
    assert " unblock:1 " in setup
    assert "UNBLOCKER: ${{ vars.UNBLOCKER }}" in setup
    assert 'row UNBLOCKER on "$UNBLOCKER"' in setup


def test_orchestrator_step2_skips_unblocker_items():
    orch = (ROOT / ".github" / "workflows" / "orchestrator.yml").read_text(encoding="utf-8")
    step2 = orch.split("2. For each other PR labeled needs-human", 1)[1].split("3. If HANDOVER", 1)[0]
    assert "unblock:1" in step2 and "<!-- unblocker -->" in step2
