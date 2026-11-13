"""Run report (issue #179): report builder, required-denial detection and the dedup of guard issues."""
import json
import pathlib

import guard_mark
import pytest
import run_report as r

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
TOKEN = "ghp_" + "a" * 24
KEY = "k" * 32


def execfile(denials=(), result="did stuff\nConclusion: nothing worth changing", created=None, turns=13):
    recs = []
    if created:
        recs.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "input": {"command": created[0]}}]}})
        recs.append({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": created[1]}]}})
    recs.append({"type": "result", "num_turns": turns, "result": result,
                 "permission_denials": [{"tool_name": t, "tool_input": {"command": c}} for t, c in denials]})
    return json.dumps(recs)


def test_report_without_changes_has_outcome_conclusion_and_denials():
    text = execfile(denials=[("Bash", "gh pr create --title x"), ("Read", "")])
    out = r.build_report("rule-keeper", text, "https://x/run/1", "haiku")
    assert "Outcome: no change" in out and "Conclusion: nothing worth changing" in out
    assert "turns: 13" in out and "Denied tool calls: 2" in out
    assert "Bash: gh pr create --title x" in out and "https://x/run/1" in out


def test_report_lists_created_pr_and_masks_secrets():
    text = execfile(denials=[("Bash", f"curl {TOKEN}")],
                    created=("gh pr create --title t", "https://github.com/o/r/pull/42\n"),
                    result=f"Conclusion: opened {TOKEN}")
    out = r.build_report("rule-keeper", text)
    assert "PR #42" in out and TOKEN not in out and "***" in out


def test_conclusion_falls_back_to_last_line_and_open():
    assert r.conclusion({"result": "a\nlast line"}) == "last line"
    assert r.conclusion({}) == "open (no final answer)"


def test_empty_execution_file_still_reports():
    out = r.build_report("scout", "", "", "")
    assert "Outcome: no change" in out and "Denied tool calls: 0" in out and "turns: open" in out


def test_required_denials_only_known_commands():
    text = execfile(denials=[("Bash", "gh pr create --title x"), ("Bash", "rm -rf /"), ("Read", "gh pr create")])
    assert r.required_denials("rule-keeper", text) == ["gh pr create"]
    assert r.required_denials("scout", text) == []


def fake_run(open_issues, calls):
    def run(*args):
        calls.append(args)
        if args[:2] == ("issue", "list"):
            return json.dumps(open_issues)
        return "https://github.com/o/r/issues/9\n" if args[:2] == ("issue", "create") else ""
    return run


def test_denial_issue_is_created_once_signed_prio2():
    calls = []
    assert r.ensure_denial_issue("rule-keeper", "gh pr create", KEY, run=fake_run([], calls)) == "9"
    create = next(c for c in calls if c[:2] == ("issue", "create"))
    title, body = create[create.index("--title") + 1], create[create.index("--body") + 1]
    assert "prio:2" in create and guard_mark.verify(title, body, KEY)


def test_denial_issue_deduplicated_by_title():
    calls = []
    title = r.denial_title("rule-keeper", "gh pr create")
    open_ = [{"number": 3, "title": title}]
    assert r.ensure_denial_issue("rule-keeper", "gh pr create", KEY, run=fake_run(open_, calls)) is None
    assert not any(c[:2] == ("issue", "create") for c in calls)
    # another workflow is a different issue
    assert r.ensure_denial_issue("scout", "gh pr create", KEY, run=fake_run(open_, [])) == "9"


def test_target_repo_routes_managed_workflows_to_template():
    cfg = {"template": "o/agent-template", "managed": [".github/workflows/"]}
    assert r.target_repo("scout", "o/proj", cfg) == "o/agent-template"
    assert r.target_repo("scout", "o/agent-template", cfg) == "o/agent-template"
    assert r.target_repo("scout", "o/proj", {"template": "o/agent-template", "managed": ["docs/"]}) == "o/proj"


def test_report_posts_comment_and_issue(monkeypatch, tmp_path):
    f = tmp_path / "e.json"
    f.write_text(execfile(denials=[("Bash", "make check")]))
    calls, comments = [], []

    def run(*args):
        calls.append(args)
        if args[:2] == ("issue", "comment"):
            comments.append(args[args.index("--body") + 1])
        if args[:2] == ("issue", "view"):
            return json.dumps({"comments": [{"body": b} for b in comments]})
        return fake_run([], [])(*args)

    monkeypatch.setattr(r, "target_repo", lambda *a, **k: "o/r")
    monkeypatch.setenv("GUARD_KEY", KEY)
    body, new = r.report("rule-keeper", {"EXEC_FILE": str(f), "GH_REPO": "o/r"}, run)
    assert ("issue", "comment", "57", "--body", body) in calls and new == ["9"]


def test_main_never_fails_the_job(monkeypatch):
    def boom(*a):
        raise RuntimeError("x")
    monkeypatch.setattr(r, "report", boom)
    assert r.main(["run_report.py", "scout"]) == 0


@pytest.mark.parametrize("wf", ["rule-keeper", "scout", "orchestrator"])
def test_workflow_runs_report_and_prompt_asks_for_conclusion(wf):
    text = (ROOT / ".github/workflows" / f"{wf}.yml").read_text(encoding="utf-8")
    assert "tools/run_report.py" in text and "`Conclusion:" in text
