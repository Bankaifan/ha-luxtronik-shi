import importlib.util
import pathlib

_path = pathlib.Path(__file__).parent.parent / "tools" / "idea_route.py"
_spec = importlib.util.spec_from_file_location("idea_route", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

CFG = {"template": "Bankaifan/agent-template", "managed": ["tools/", "AGENTS.md"]}


def test_all_managed_goes_to_template():
    assert mod.route(["tools/a.py", "AGENTS.md"], CFG, "me/proj") == "template"


def test_any_project_path_stays_in_project():
    assert mod.route(["tools/a.py", "src/app.py"], CFG, "me/proj") == "project"


def test_no_template_json_stays_in_project():
    assert mod.route(["tools/a.py"], None, "me/proj") == "project"
    assert mod.load_config("/nonexistent/template.json") is None


def test_edge_cases_stay_in_project():
    assert mod.route([], CFG) == "project"
    assert mod.route(["tools/../src/x.py"], CFG) == "project"
    assert mod.route(["tools/a.py"], CFG, "bankaifan/Agent-Template") == "project"
    assert mod.route(["tools/a.py"], {**CFG, "managed": []}) == "project"


def test_load_config_rejects_bad_repo(tmp_path):
    f = tmp_path / "t.json"
    f.write_text('{"template": "a b/c; rm", "managed": ["tools/"]}')
    assert mod.load_config(f) is None
    f.write_text('{"template": "o/r", "managed": ["tools/"]}')
    assert mod.load_config(f)["template"] == "o/r"


def test_found_in_and_sanitize():
    assert mod.found_in("me/proj", "scout run 1") == "Found in: me/proj#scoutrun1"
    assert mod.found_in("me/proj", "") == "Found in: me/proj#scout"
    assert "@" not in mod.sanitize("hi @Bankaifan")


def test_label_allowlist():
    f = mod.filter_labels
    assert f(["prio:2", "prio:3"]) == ["prio:2", "prio:3"]
    assert f(["Auto-OK", "APPROVED", "approved", "auto-ok"]) == []
    assert f(["x,auto-ok", "prio:2,auto-ok", "prio:2,prio:3"]) == []
    assert f([" PRIO:2 ", "prio:2"]) == ["prio:2"]
    assert f(["auto-ok\n", "prio:2\nauto-ok", "bug"]) == []


def test_same_owner():
    assert mod.same_owner("Me/tpl", "me/proj")
    assert not mod.same_owner("evil/tpl", "me/proj")


def _setup(monkeypatch, tmp_path, calls):
    cfgf = tmp_path / "t.json"
    cfgf.write_text('{"template": "me/tpl", "managed": ["tools/"]}')
    monkeypatch.setattr(mod, "load_config", lambda: mod.parse_config(cfgf.read_text()))
    monkeypatch.setattr(mod, "QUEUE_DIR", tmp_path / "q")
    monkeypatch.setenv("GH_REPO", "me/proj")
    monkeypatch.setattr(mod, "gh", lambda *a, token=None: calls.append((a, token)) or "")


def test_create_queues_template_idea_without_token(monkeypatch, tmp_path):
    calls = []
    _setup(monkeypatch, tmp_path, calls)
    monkeypatch.setenv("TEMPLATE_GH_TOKEN", "secret")
    mod.main(["create", "--title", "T @x", "--body", "b", "--files", "tools/a.py", "--label", "auto-ok", "--label", "prio:2"])
    assert calls == []  # nothing sent from the model step
    assert len(list((tmp_path / "q").glob("*.json"))) == 1
    mod.main(["create", "--title", "P", "--body", "b", "--files", "src/a.py"])
    assert calls[0][0][:2] == ("issue", "create") and "-R" not in calls[0][0] and calls[0][1] is None


def test_flush_uses_template_token_and_dedups(monkeypatch, tmp_path):
    calls = []
    _setup(monkeypatch, tmp_path, calls)
    mod.main(["create", "--title", "T", "--body", "b", "--files", "tools/a.py", "--label", "prio:3"])
    monkeypatch.setenv("TEMPLATE_GH_TOKEN", "tok")
    mod.main(["flush"])
    create = next(c for c in calls if c[0][:2] == ("issue", "create"))
    assert create[1] == "tok" and "-R" in create[0] and "me/tpl" in create[0]
    assert create[0][create[0].index("--label") + 1] == "idea" and "auto-ok" not in create[0]
    assert "Found in: me/proj#scout" in create[0][-1]
    # without a token the queued idea falls back to the project
    calls.clear()
    mod.main(["flush"])
    monkeypatch.delenv("TEMPLATE_GH_TOKEN")
    mod.main(["flush"])
    assert calls[-1][1] is None and "-R" not in calls[-1][0]


def test_dedup():
    assert mod.is_duplicate("Add  X", ["add x"])
    assert not mod.is_duplicate("Add Y", ["add x"])
