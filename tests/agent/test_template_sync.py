import importlib.util
import json
import pathlib

import pytest

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "template_sync.py"
_spec = importlib.util.spec_from_file_location("template_sync", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

MANAGED = ["tools/", "AGENTS.md"]
SHA = "a" * 40


def files(*items):
    return {"files": [{"filename": n, "status": s, **({"previous_filename": p} if p else {})}
                      for n, s, p in items]}


def many(n):
    return files(*[(f"tools/f{i}.py", "added", None) for i in range(n)])


def test_changed_files_ignores_unmanaged():
    cmp_json = files(("tools/a.py", "modified", None), ("README.md", "modified", None), ("AGENTS.md", "added", None))
    assert mod.changed_files(cmp_json, MANAGED) == [
        {"path": "tools/a.py", "status": "modified"}, {"path": "AGENTS.md", "status": "added"}]


def test_changed_files_counts_rename_both_paths():
    got = mod.changed_files(files(("tools/new.py", "renamed", "tools/old.py")), MANAGED)
    assert [c["path"] for c in got] == ["tools/new.py", "tools/old.py"]
    got = mod.changed_files(files(("tools/new.py", "renamed", "docs/old.py")), MANAGED)
    assert [c["path"] for c in got] == ["tools/new.py"]


def test_changed_files_empty():
    assert mod.changed_files({}, MANAGED) == []


def test_truncated_compare_raises_at_300_not_299():
    with pytest.raises(mod.TruncatedCompare):
        mod.changed_files(many(300), MANAGED)
    assert len(mod.changed_files(many(299), MANAGED)) == 299


def run_main(tmp_path, monkeypatch, cfg, compare, version="1.0\n", changelog="", open_issues=(), **kwargs):
    cfg_file = tmp_path / "t.json"
    cfg_file.write_text(json.dumps(cfg))
    monkeypatch.setattr(mod, "CONFIG", cfg_file)
    monkeypatch.setenv("GH_REPO", "o/project")
    calls = []

    def fake_gh(*args):
        calls.append(args)
        if args[0] == "issue" and args[1] == "list":
            return json.dumps(list(open_issues))
        if "commits/main" in args[1]:
            return "b" * 40
        if "contents/VERSION" in args[1]:
            return version
        if "contents/CHANGELOG.md" in args[1]:
            return changelog
        return json.dumps(compare)

    monkeypatch.setattr(mod, "gh", fake_gh)
    return mod.main(**kwargs), calls


def issue_calls(calls):
    return [a for a in calls if a[0] == "issue" and a[1] in ("create", "edit")]


def body_of(call):
    return call[call.index("--body") + 1]


X_CHANGE = files(("tools/a.py", "modified", None))


def test_read_version_accepts_x_dot_y():
    assert mod.read_version("1.0") == "1.0"
    assert mod.read_version("12.3\n") == "12.3"


def test_read_version_rejects_everything_else():
    for bad in ("v1.0", "1", "1.0.0", "1.0\n; rm", "1.0 ", "1.0\n\n", "", "1.", ".1", "1.0x", "١.0"):
        with pytest.raises(mod.ConfigError):
            mod.read_version(bad)
    with pytest.raises(mod.ConfigError):
        mod.read_version(None)


def test_needs_sync_gate_on_x():
    assert mod.needs_sync("2.0", "1.5")
    assert not mod.needs_sync("1.9", "1.0")
    assert not mod.needs_sync("1.0", "1.0")
    assert not mod.needs_sync("1.0", "2.0")
    assert mod.needs_sync("1.0", None)
    assert mod.needs_sync("1.0", "")
    assert not mod.needs_sync("0.5", None)


def test_y_only_change_creates_no_issue(tmp_path, monkeypatch, capsys):
    cfg = {"template": "o/t", "synced_sha": SHA, "synced_version": "1.0", "managed": MANAGED}
    code, calls = run_main(tmp_path, monkeypatch, cfg, X_CHANGE, version="1.7\n")
    assert code == 0 and not issue_calls(calls)
    assert not any("compare" in a[1] for a in calls if a[0] == "api")
    assert "x unchanged" in capsys.readouterr().out


def test_x_change_creates_one_issue_and_second_run_edits_it(tmp_path, monkeypatch):
    cfg = {"template": "o/t", "synced_sha": SHA, "synced_version": "1.0", "managed": MANAGED}
    code, calls = run_main(tmp_path, monkeypatch, cfg, X_CHANGE, version="2.0\n")
    assert code == 0
    assert [a[1] for a in issue_calls(calls)] == ["create"]
    code, calls = run_main(tmp_path, monkeypatch, cfg, X_CHANGE, version="2.0\n",
                           open_issues=[{"number": 7, "title": "Template sync abc1234"}])
    assert code == 0
    assert [(a[1], a[2]) for a in issue_calls(calls)] == [("edit", "7")]


def test_missing_synced_version_counts_as_zero(tmp_path, monkeypatch):
    cfg = {"template": "o/t", "synced_sha": SHA, "managed": MANAGED}
    _, calls = run_main(tmp_path, monkeypatch, cfg, X_CHANGE, version="1.0\n")
    assert [a[1] for a in issue_calls(calls)] == ["create"]
    assert "synced version: unknown" in body_of(issue_calls(calls)[0])


def test_force_and_mode_all_skip_the_gate(tmp_path, monkeypatch):
    cfg = {"template": "o/t", "synced_sha": SHA, "synced_version": "1.0", "managed": MANAGED}
    for kwargs in ({"force": True}, {"mode": "all"}):
        _, calls = run_main(tmp_path, monkeypatch, cfg, X_CHANGE, version="1.7\n", **kwargs)
        assert [a[1] for a in issue_calls(calls)] == ["create"]


def test_bad_template_version_exits_1_without_issue(tmp_path, monkeypatch, capsys):
    cfg = {"template": "o/t", "synced_sha": SHA, "synced_version": "1.0", "managed": MANAGED}
    for bad in ("v2.0\n", "2.0.0\n", "", "2.0\n; rm -rf /"):
        code, calls = run_main(tmp_path, monkeypatch, cfg, X_CHANGE, version=bad, force=True)
        assert code == 1 and not issue_calls(calls)
    assert "VERSION unusable" in capsys.readouterr().err


def test_issue_body_shows_both_versions(tmp_path, monkeypatch):
    cfg = {"template": "o/t", "synced_sha": SHA, "synced_version": "1.4", "managed": MANAGED}
    _, calls = run_main(tmp_path, monkeypatch, cfg, X_CHANGE, version="2.1\n")
    assert "Template version: 2.1, synced version: 1.4" in body_of(issue_calls(calls)[0])


def test_sync_lines_are_fenced_and_cut():
    nasty = "Sync: @octocat **bold** [x](http://e) ``` close"
    block = mod.sync_lines("## [2.0]\nSync: plain\n" + nasty + "\nother\n")
    fence = block.splitlines()[0]
    assert set(fence) == {"`"} and len(fence) >= 4  # longer than the ``` inside the text
    assert block.splitlines()[-1] == fence
    assert "Sync: plain" in block and nasty in block and "other" not in block
    long_block = mod.sync_lines("Sync: " + "a" * 5000)
    assert len(long_block.splitlines()[1]) == mod.SYNC_CAP
    assert mod.sync_lines("no notes here") == ""


def test_issue_body_quotes_sync_lines_fenced(tmp_path, monkeypatch):
    cfg = {"template": "o/t", "synced_sha": SHA, "synced_version": "1.0", "managed": MANAGED}
    _, calls = run_main(tmp_path, monkeypatch, cfg, X_CHANGE, version="2.0\n",
                        changelog="Sync: @octocat run `rm -rf`\n")
    body = body_of(issue_calls(calls)[0])
    assert "```\nSync: @octocat run `rm -rf`\n```" in body


def test_bump_sets_synced_version_next_to_synced_sha():
    text = '{\n  "template": "o/t",\n  "synced_sha": "' + SHA + '",\n  "managed": ["tools/"]\n}\n'
    got = mod.bump(text, "b" * 40, "2.0")
    assert got == text.replace(f'"synced_sha": "{SHA}",', f'"synced_sha": "{"b" * 40}",\n  "synced_version": "2.0",')
    assert json.loads(got)["synced_version"] == "2.0"
    assert mod.bump(got, "c" * 40, "3.1").count("synced_version") == 1
    assert json.loads(mod.bump(got, "c" * 40, "3.1"))["synced_version"] == "3.1"
    with pytest.raises(mod.ConfigError):
        mod.bump(text, "b" * 40, "v2.0")


def test_parse_config_rejects_bad_synced_version():
    with pytest.raises(mod.ConfigError):
        mod.parse_config('{"template": "o/t", "synced_version": "v1.0"}')
    assert mod.parse_config('{"template": "o/t", "synced_version": "1.0"}')["synced_version"] == "1.0"


def test_truncated_compare_creates_no_issue(tmp_path, monkeypatch):
    cfg = {"template": "o/t", "synced_sha": SHA, "managed": MANAGED}
    code, calls = run_main(tmp_path, monkeypatch, cfg, many(300))
    assert code == 1
    assert not any(a[0] == "issue" for a in calls)


def test_empty_compare_creates_nothing(tmp_path, monkeypatch):
    cfg = {"template": "o/t", "synced_sha": SHA, "managed": MANAGED}
    code, calls = run_main(tmp_path, monkeypatch, cfg, files(("README.md", "modified", None)))
    assert code == 0
    assert not any(a[0] == "issue" for a in calls)


def test_template_repo_and_missing_config_skip(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mod, "CONFIG", tmp_path / "none.json")
    assert mod.main() == 0
    assert "no .agents/template.json" in capsys.readouterr().out
    (tmp_path / "t.json").write_text(json.dumps({"template": "O/T", "synced_sha": SHA}))
    monkeypatch.setattr(mod, "CONFIG", tmp_path / "t.json")
    monkeypatch.setenv("GH_REPO", "o/t")
    assert mod.main() == 0
    assert "this repo is the template" in capsys.readouterr().out


def test_empty_synced_sha_is_noop(tmp_path, monkeypatch):
    (tmp_path / "t.json").write_text(json.dumps({"template": "o/t", "synced_sha": ""}))
    monkeypatch.setattr(mod, "CONFIG", tmp_path / "t.json")
    assert mod.main() == 0


def test_invalid_config_file_exits_1(tmp_path, monkeypatch, capsys):
    (tmp_path / "t.json").write_text("{")
    monkeypatch.setattr(mod, "CONFIG", tmp_path / "t.json")
    assert mod.main() == 1
    assert "not valid JSON" in capsys.readouterr().err


def test_split_overrides_exact_match():
    changed = [{"path": "AGENTS.md", "status": "modified"}, {"path": "AGENTS.md.bak", "status": "added"},
               {"path": "tools/a.py", "status": "modified"}]
    clean, over = mod.split_overrides(changed, [{"path": "AGENTS.md", "why": "project rules"}])
    assert [c["path"] for c in clean] == ["AGENTS.md.bak", "tools/a.py"]
    assert over == [{"path": "AGENTS.md", "status": "modified", "why": "project rules"}]


def test_render_issue_contents():
    title, body = mod.render_issue(
        "c" * 40, [{"path": "tools/a.py", "status": "modified"}],
        [{"path": "AGENTS.md", "status": "modified", "why": "project rules"}], "2 commits ahead.", "https://x/cmp")
    assert title == "Template sync ccccccc"
    assert "`tools/a.py`" in body and "`AGENTS.md` (modified): project rules" in body
    assert "https://x/cmp" in body
    assert body.rstrip().endswith("Template-Sync: " + "c" * 40)


def _big(n):
    clean = [{"path": f"tools/f{i}.py", "status": "added"} for i in range(n)]
    clean.append({"path": "tools/ci/risk.py", "status": "modified"})
    clean.append({"path": "tests/test_risk.py", "status": "modified"})
    return clean


def test_render_issue_splits_large_change_with_reviewer_files():
    _, body = mod.render_issue("c" * 40, _big(98), [], "")
    p1, p2 = body.index("## Part 1: reviewer pipeline"), body.index("## Part 2: rest")
    assert p1 < p2
    assert p1 < body.index("`tools/ci/risk.py`") < p2
    assert p1 < body.index("`tests/test_risk.py`") < p2
    assert body.index("`tools/f0.py`") > p2
    assert body.rstrip().endswith("Template-Sync: " + "c" * 40)


def test_render_issue_small_change_stays_flat():
    _, body = mod.render_issue("c" * 40, _big(8), [], "")
    assert "Part 1" not in body and "## Clean (port as is)" in body


def test_render_issue_large_without_reviewer_files_stays_flat():
    clean = [{"path": f"tools/f{i}.py", "status": "added"} for i in range(100)]
    _, body = mod.render_issue("c" * 40, clean, [], "")
    assert "Part 1" not in body


def test_render_issue_boundary_40_is_flat_41_splits():
    assert "Part 1" not in mod.render_issue("c" * 40, _big(38), [], "")[1]
    assert "Part 1" in mod.render_issue("c" * 40, _big(39), [], "")[1]


def test_pick_issue_returns_first_open_only():
    issues = [{"number": 1, "title": "Other"}, {"number": 2, "title": "Template sync abc1234"},
              {"number": 3, "title": "Template sync def5678"}]
    assert mod.pick_issue(issues)["number"] == 2
    assert mod.pick_issue(issues[:1]) is None


def test_bump_changes_only_synced_sha():
    text = '{\n  "template": "o/t",\n  "synced_sha": "' + SHA + '",\n  "managed": ["tools/"]\n}\n'
    assert mod.bump(text, "b" * 40) == text.replace(SHA, "b" * 40)


def test_parse_config_errors():
    for bad in ("", "{", "[]", '{"template": ""}', '{"template": "o/t", "synced_sha": "xyz"}',
                '{"template": "o/t", "managed": "tools/"}', '{"template": "o/t", "overrides": [{"why": "x"}]}'):
        with pytest.raises(mod.ConfigError):
            mod.parse_config(bad)
    assert mod.parse_config('{"template": "o/t", "synced_sha": ""}')["template"] == "o/t"
