"""template-sync.yml (designs 0011, 0014 sections 4.2 and 6): daily poll, version gate, token split, no new trigger."""
import re
from pathlib import Path

TEXT = (Path(__file__).resolve().parent.parent.parent / ".github" / "workflows" / "template-sync.yml").read_text(
    encoding="utf-8")
TRIGGERS = TEXT[TEXT.index("\non:\n"):TEXT.index("\npermissions:")]
_JOBS_PARTS = re.split(r"\n  (\w+):\n", TEXT[TEXT.index("\njobs:\n"):])
JOBS = dict(zip(_JOBS_PARTS[1::2], _JOBS_PARTS[2::2]))


def run_blocks(text):
    """The body of every `run:` key in text (the lines indented deeper than the key)."""
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        m = re.match(r"( *)run: ?(.*)$", line)
        if not m:
            continue
        indent = len(m.group(1))
        body = [m.group(2)]
        for nxt in lines[i + 1:]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= indent:
                break
            body.append(nxt)
        out.append("\n".join(body))
    return out


def test_runs_daily_and_by_hand_with_a_boolean_force_input():
    assert re.search(r'cron: "\d+ \d+ \* \* \*"', TRIGGERS)
    assert "workflow_dispatch:" in TRIGGERS
    force = TRIGGERS[TRIGGERS.index("force:"):]
    assert "type: boolean" in force


def test_no_repository_dispatch_or_other_trigger():
    assert "repository_dispatch" not in TEXT
    for bad in ("pull_request", "push:", "workflow_run", "issues:", "release:"):
        assert bad not in TRIGGERS, bad


def test_top_level_permission_is_read_only():
    top = TEXT[TEXT.index("\npermissions:"):TEXT.index("\njobs:")]
    assert re.findall(r"(\w+): (\w+)", top) == [("contents", "read")]


def test_jobs_are_build_publish_and_report():
    assert list(JOBS) == ["build", "publish", "report"]


def test_build_token_is_read_only():
    assert re.findall(r"permission-[\w-]+: \w+", JOBS["build"]) == ["permission-contents: read"]


def test_write_tokens_only_in_publish_and_the_report_fallback():
    writes = {name: re.findall(r"permission-[\w-]+: write", body) for name, body in JOBS.items()}
    assert writes["build"] == []
    assert writes["publish"] == ["permission-contents: write", "permission-pull-requests: write",
                                 "permission-issues: write"]
    assert writes["report"] == ["permission-issues: write"]


def test_publish_needs_build_and_runs_only_on_a_patch():
    assert "needs: build" in JOBS["publish"]
    assert "needs.build.outputs.patch == 'true'" in JOBS["publish"]


def test_publish_runs_only_git_and_gh():
    for block in run_blocks(JOBS["publish"]):
        for forbidden in ("python", "make", "bash", "tools/", "work/", "base/", "./"):
            assert forbidden not in block, (forbidden, block)


def test_make_check_runs_in_work_without_any_token():
    steps = re.split(r"\n      - ", JOBS["build"])
    checks = [s for s in steps if "run: make check" in s]
    assert len(checks) == 1
    assert "working-directory: work" in checks[0]
    assert "GH_TOKEN" not in checks[0] and "steps.app" not in checks[0]


def test_apply_runs_the_base_script_on_the_work_checkout():
    assert "python3 base/tools/template_sync.py apply --root work" in JOBS["build"]
    assert "work/tools" not in TEXT


def test_checkouts_in_build_hold_no_credentials():
    assert JOBS["build"].count("actions/checkout@") == JOBS["build"].count("persist-credentials: false")


def test_no_template_derived_value_in_a_run_expression():
    for block in run_blocks(TEXT):
        assert "${{" not in block, block
    for name in ("VERSION", "version", "changelog", "CHANGELOG"):
        assert f"${{{{ {name}" not in TEXT


def test_every_uses_is_pinned_to_a_sha():
    refs = re.findall(r"uses: \S+@(\S+)", TEXT)
    assert refs and all(re.fullmatch(r"[0-9a-f]{40}", r) for r in refs)


def test_no_model_and_only_the_author_secret():
    assert set(re.findall(r"secrets\.\w+", TEXT)) == {"secrets.AUTHOR_APP_KEY"}
    assert "claude" not in TEXT.lower()


def test_gate_expression_and_default_mode():
    assert "(vars.TEMPLATE_SYNC_MODE || 'all') == 'all'" in TEXT
    assert "!= 'all'" not in TEXT


def test_apply_flag_selects_build_and_report():
    assert "(vars.TEMPLATE_SYNC_APPLY || 'on') != 'off'" in JOBS["build"]
    assert "(vars.TEMPLATE_SYNC_APPLY || 'on') == 'off'" in JOBS["report"]
    assert "needs.build.result == 'failure'" in JOBS["report"]


def test_force_and_mode_reach_main_through_env():
    assert "SYNC_FORCE: ${{ inputs.force == true }}" in TEXT
    assert "template_sync.main(force=" in TEXT


def test_issue_flow_keeps_the_developer_label():
    assert "--label agent:dev" in JOBS["publish"]
