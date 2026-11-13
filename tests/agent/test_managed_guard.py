"""Issue #195: projects must not change template-managed files (check in validate, routing in agent-dev)."""
import importlib.util
import json
import pathlib

import pytest

pytestmark = pytest.mark.template_only

ROOT = pathlib.Path(__file__).parent.parent.parent
_spec = importlib.util.spec_from_file_location("managed_guard", ROOT / "tools" / "managed_guard.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

CFG = {"template": "me/tpl", "managed": ["tools/", "AGENTS.md"],
       "overrides": [{"path": "tools/local.py", "why": "x"}]}
PROJ = "me/proj"


def test_template_managed_reads_file(tmp_path):
    f = tmp_path / "managed.json"
    f.write_text(json.dumps({"managed": ["tools/", "AGENTS.md"]}))
    assert mod.template_managed(f) == ["tools/", "AGENTS.md"]


def test_template_managed_missing_file_is_empty(tmp_path):
    assert mod.template_managed(tmp_path / "nope.json") == []


def test_template_managed_invalid_raises(tmp_path):
    f = tmp_path / "managed.json"
    f.write_text('{"managed": "tools/"}')
    with pytest.raises(mod.ConfigError):
        mod.template_managed(f)


@pytest.mark.skipif(not (ROOT / ".agents" / "managed.json").is_file(),
                    reason=".agents/managed.json exists only in the template repo")
def test_repo_managed_file_lists_tools_and_makefile():
    managed = mod.template_managed(ROOT / ".agents" / "managed.json")
    assert "tools/" in managed and "Makefile" in managed


def test_pr_with_managed_file_fails_and_names_template():
    errs = mod.pr_errors(CFG, PROJ, "Fix", ["src/a.py", "tools/a.py"])
    assert len(errs) == 1 and "tools/a.py" in errs[0] and "me/tpl" in errs[0]


def test_pr_without_managed_or_with_override_passes():
    assert mod.pr_errors(CFG, PROJ, "Fix", ["src/a.py", "README.md"]) == []
    assert mod.pr_errors(CFG, PROJ, "Fix", ["tools/local.py"]) == []


def test_template_repo_and_missing_config_are_noop():
    assert mod.pr_errors(CFG, "Me/TPL", "Fix", ["tools/a.py"]) == []
    assert mod.pr_errors(None, PROJ, "Fix", ["tools/a.py"]) == []


def test_sync_pr_is_exempt_only_with_title_and_config_change():
    files = ["tools/a.py", ".agents/template.json"]
    assert mod.pr_errors(CFG, PROJ, "Template sync abc1234", files) == []
    assert mod.pr_errors(CFG, PROJ, "Template sync abc1234", ["tools/a.py"])
    assert mod.pr_errors(CFG, PROJ, "Fix", files)


def test_split_sync_parts_are_exempt_without_config_change():
    files = ["tools/a.py", "AGENTS.md"]
    for title in ["Template sync abc1234 part 1", "Template sync abc1234 part 1: reviewer pipeline",
                  "Template sync abc1234 part 2", "Template sync abc1234 part 10", "Template sync abc1234 part 2a",
                  "Template sync 09335eb part 2b-1: leaf tools and tests"]:
        assert mod.pr_errors(CFG, PROJ, title, files) == [], title


def test_other_titles_are_not_part_exempt():
    files = ["tools/a.py"]
    for title in ["Fix", "Template sync abc1234", "Template sync abc1234 part", "Template sync abc1234 part x",
                  "Template sync abc1234 partial", "Template sync part 1", "Template sync xyz part 1",
                  "Fix: Template sync abc1234 part 1"]:
        assert mod.pr_errors(CFG, PROJ, title, files), title


def test_slip_paths_takes_last_line():
    text = "Files touched: `a.py`\nmore\nFiles touched: new tools/managed_guard.py, tests/test_x.py (and AGENTS.md)."
    assert mod.slip_paths(text) == ["tools/managed_guard.py", "tests/test_x.py", "AGENTS.md"]
    assert mod.slip_paths("no list") is None


def test_route_decision():
    assert mod.route_decision(CFG, PROJ, ["tools/a.py", "AGENTS.md"]) == "template"
    assert mod.route_decision(CFG, PROJ, ["tools/a.py", "src/b.py"]) == "project"
    assert mod.route_decision(CFG, PROJ, ["tools/local.py"]) == "project"
    assert mod.route_decision(CFG, PROJ, ["tools/../src/b.py"]) == "project"
    assert mod.route_decision(CFG, "me/tpl", ["tools/a.py"]) == "project"
    assert mod.route_decision(None, PROJ, ["tools/a.py"]) == "project"
    assert mod.route_decision(CFG, PROJ, []) == "project"


def test_route_issue_creates_template_issue_and_comments(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(mod, "load", lambda: CFG)
    monkeypatch.setattr(mod, "gh", lambda *a, token=None: calls.append((a, token)) or "https://x/1\n")
    issue = {"number": 7, "title": "Fix @bob", "body": "b", "comments": [{"body": "Files touched: tools/a.py", "authorAssociation": "OWNER"}]}
    monkeypatch.setenv("ISSUE_JSON", json.dumps(issue))
    monkeypatch.setenv("GH_REPO", PROJ)
    monkeypatch.setenv("TEMPLATE_GH_TOKEN", "tok")
    assert mod.main(["route-issue"]) == 0
    assert capsys.readouterr().out.strip() == "skip=true"
    create, comment = calls
    assert create[1] == "tok" and "me/tpl" in create[0] and "@" not in " ".join(create[0])
    assert comment[1] is None and comment[0][:2] == ("issue", "comment")


def test_route_issue_does_nothing_for_project_files_or_no_token(monkeypatch, capsys):
    def no_gh(*a, **k):
        raise AssertionError("no gh call expected")

    monkeypatch.setattr(mod, "load", lambda: CFG)
    monkeypatch.setattr(mod, "gh", no_gh)
    monkeypatch.setenv("GH_REPO", PROJ)
    issue = {"number": 7, "title": "t", "body": "Files touched: tools/a.py, src/b.py", "comments": []}
    monkeypatch.setenv("ISSUE_JSON", json.dumps(issue))
    monkeypatch.setenv("TEMPLATE_GH_TOKEN", "tok")
    assert mod.main(["route-issue"]) == 0
    issue["body"] = "Files touched: tools/a.py"
    monkeypatch.setenv("ISSUE_JSON", json.dumps(issue))
    monkeypatch.delenv("TEMPLATE_GH_TOKEN")
    assert mod.main(["route-issue"]) == 0
    assert capsys.readouterr().out == ""


def test_check_command_uses_pr_files(monkeypatch, capsys):
    monkeypatch.setattr(mod, "load", lambda: CFG)
    monkeypatch.setattr(mod, "gh", lambda *a, **k: json.dumps({"title": "Fix", "files": [{"path": "AGENTS.md"}]}))
    monkeypatch.setenv("PR_NUMBER", "3")
    monkeypatch.setenv("GH_REPO", PROJ)
    assert mod.main(["check"]) == 1
    assert "me/tpl" in capsys.readouterr().out
    monkeypatch.delenv("PR_NUMBER")
    assert mod.main(["check"]) == 0


def test_untrusted_comment_does_not_route(monkeypatch, capsys):
    monkeypatch.setattr(mod, "load", lambda: CFG)
    monkeypatch.setattr(mod, "gh", lambda *a, **k: pytest.fail("must not call gh"))
    issue = {"number": 7, "title": "t", "body": "b",
             "comments": [{"body": "Files touched: tools/a.py", "authorAssociation": "NONE"}]}
    monkeypatch.setenv("ISSUE_JSON", json.dumps(issue))
    monkeypatch.setenv("GH_REPO", PROJ)
    monkeypatch.setenv("TEMPLATE_GH_TOKEN", "tok")
    assert mod.main(["route-issue"]) == 0
    assert capsys.readouterr().out == ""


def test_agent_dev_routes_in_a_job_without_the_model():
    yaml = pytest.importorskip("yaml")  # installed by tools/ci/install_tools.sh
    jobs = yaml.safe_load((ROOT / ".github/workflows/agent-dev.yml").read_text())["jobs"]
    route, dev = jobs["route"], jobs["dev"]
    assert dev["needs"] == "route" and "needs.route.outputs.skip != 'true'" in dev["if"]
    assert any("route-issue" in s.get("run", "") for s in route["steps"])
    assert not any("claude-code-action" in s.get("uses", "") for s in route["steps"])
    assert "tpl-app" not in json.dumps(dev) and "TEMPLATE_GH_TOKEN" not in json.dumps(dev)


def test_makefile_runs_the_check():
    assert "tools/managed_guard.py check" in (ROOT / "Makefile").read_text()
