"""template-sync.yml (design 0011, sections 4.3, 4.4 and 6): daily poll, version gate, no new trust edge."""
import re
from pathlib import Path

TEXT = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "template-sync.yml").read_text(
    encoding="utf-8")
TRIGGERS = TEXT[TEXT.index("\non:\n"):TEXT.index("\npermissions:")]


def test_runs_daily_and_by_hand_with_a_boolean_force_input():
    assert re.search(r'cron: "\d+ \d+ \* \* \*"', TRIGGERS)
    assert "workflow_dispatch:" in TRIGGERS
    force = TRIGGERS[TRIGGERS.index("force:"):]
    assert "type: boolean" in force


def test_no_repository_dispatch_or_other_trigger():
    assert "repository_dispatch" not in TEXT
    for bad in ("pull_request", "push:", "workflow_run", "issues:", "release:"):
        assert bad not in TRIGGERS, bad


def test_no_new_permission_token_or_secret():
    top = TEXT[TEXT.index("\npermissions:"):TEXT.index("\njobs:")]
    assert re.findall(r"(\w+): (\w+)", top) == [("contents", "read")]
    assert re.findall(r"permission-[\w-]+: \w+", TEXT) == ["permission-issues: write"]
    assert re.findall(r"secrets\.\w+", TEXT) == ["secrets.AUTHOR_APP_KEY"]
    assert "claude" not in TEXT.lower()


def test_gate_expression_and_default_mode():
    assert "(vars.TEMPLATE_SYNC_MODE || 'version') == 'all'" in TEXT
    assert "!= 'all'" not in TEXT


def test_version_text_is_never_used_in_a_run_expression():
    run = TEXT[TEXT.index("run:"):]
    assert "${{" not in run
    for name in ("VERSION", "version", "changelog", "CHANGELOG"):
        assert f"${{{{ {name}" not in TEXT


def test_every_uses_is_pinned_to_a_sha():
    refs = re.findall(r"uses: \S+@(\S+)", TEXT)
    assert refs and all(re.fullmatch(r"[0-9a-f]{40}", r) for r in refs)


def test_force_and_mode_reach_main_through_env():
    assert "SYNC_FORCE: ${{ inputs.force == true }}" in TEXT
    assert "template_sync.main(force=" in TEXT
