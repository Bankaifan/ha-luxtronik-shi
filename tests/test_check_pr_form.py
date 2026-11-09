import importlib.util
import json
import pathlib
import subprocess

_path = pathlib.Path(__file__).parent.parent / "tools" / "check" / "check_pr_form.py"
_spec = importlib.util.spec_from_file_location("check_pr_form", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def run(monkeypatch, env):
    for k in ("PR_TITLE", "PR_BODY", "GITHUB_EVENT_NAME", "GITHUB_REF_NAME"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return mod.main()


def fake_gh(monkeypatch, payload=None, fail=False):
    def _run(cmd, **kw):
        assert cmd[:3] == ["gh", "pr", "view"]
        if fail:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(mod.subprocess, "run", _run)


def test_local_run_defaults_to_pull_request_and_skips_without_title(monkeypatch):
    assert run(monkeypatch, {}) == 0


def test_pull_request_ok_and_bad(monkeypatch):
    assert run(monkeypatch, {"GITHUB_EVENT_NAME": "pull_request", "PR_TITLE": "Fix x", "PR_BODY": "why"}) == 0
    assert run(monkeypatch, {"GITHUB_EVENT_NAME": "pull_request", "PR_TITLE": "Fix ü", "PR_BODY": "why"}) == 1


def test_push_skipped(monkeypatch):
    assert run(monkeypatch, {"GITHUB_EVENT_NAME": "push", "PR_TITLE": ""}) == 0


def test_dispatch_reads_pr(monkeypatch):
    env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF_NAME": "agent/1-x"}
    fake_gh(monkeypatch, {"title": "Fix x", "body": ""})
    assert run(monkeypatch, env) == 1
    fake_gh(monkeypatch, {"title": "Fix x", "body": "why"})
    assert run(monkeypatch, env) == 0


def check(monkeypatch, body, files, head="agent/1-x"):
    fake_gh(monkeypatch, {"title": "Fix x", "body": body, "headRefName": head,
                          "files": [{"path": f} for f in files]})
    return run(monkeypatch, {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF_NAME": head})


def test_design_pr_with_closing_keyword_fails(monkeypatch):
    for body in ("Closes #5", "fixes #5", "Resolved: #5", "closes Bankaifan/x#5"):
        assert check(monkeypatch, body, ["docs/design/0002-x.md"]) == 1


def test_design_pr_with_refs_ok_and_other_pr_may_close(monkeypatch):
    assert check(monkeypatch, "Refs #5", ["docs/design/0002-x.md"]) == 0
    assert check(monkeypatch, "Closes #5", ["tools/a.py"]) == 0
    assert check(monkeypatch, "Closes #5", ["docs/design/0002-x.md", "tools/a.py"]) == 0


def test_handover_only_for_orchestrator(monkeypatch):
    assert check(monkeypatch, "why", ["HANDOVER.md"]) == 1
    assert check(monkeypatch, "why", ["tools/a.py", "HANDOVER.md"]) == 1
    assert check(monkeypatch, "why", ["HANDOVER.md"], head="agent/orchestrator-handover-2026-11-09") == 0


def test_pull_request_event_reads_files_by_number(monkeypatch):
    fake_gh(monkeypatch, {"title": "t", "body": "b", "headRefName": "agent/1-x", "files": [{"path": "HANDOVER.md"}]})
    env = {"GITHUB_EVENT_NAME": "pull_request", "PR_TITLE": "Fix x", "PR_BODY": "why", "PR_NUMBER": "7",
           "PR_HEAD_REF": "agent/1-x"}
    assert run(monkeypatch, env) == 1
    fake_gh(monkeypatch, fail=True)
    assert run(monkeypatch, env) == 0


def test_dispatch_without_pr_skipped(monkeypatch):
    fake_gh(monkeypatch, fail=True)
    assert run(monkeypatch, {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF_NAME": "agent/1-x"}) == 0
