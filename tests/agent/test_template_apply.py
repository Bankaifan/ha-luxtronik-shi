import importlib.util
import pathlib

import pytest

_TOOLS = pathlib.Path(__file__).parent.parent.parent / "tools"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ta = _load("template_apply")
ts = _load("template_sync")
MANAGED = ["tools/", "AGENTS.md"]


def test_plan_splits_like_split_overrides():
    changed = [{"path": "tools/a.py", "status": "modified"}, {"path": "tools/b.py", "status": "added"}]
    overrides = [{"path": "tools/a.py", "why": "local"}]
    assert ta.plan(changed, overrides) == ts.split_overrides(changed, overrides)
    clean, overridden = ta.plan(changed, overrides)
    assert clean == [{"path": "tools/b.py", "status": "added"}]
    assert overridden == [{"path": "tools/a.py", "status": "modified", "why": "local"}]


@pytest.mark.parametrize("path", [
    "../x", "tools/../../x", "/etc/x", "tools/../AGENTS.md", "README.md", "tools", "toolsx.py", "tools\\x.py", "",
])
def test_check_path_refuses(path):
    with pytest.raises(ta.PathRefused):
        ta.check_path(path, MANAGED)


def test_check_path_accepts_managed():
    assert ta.check_path("tools/a.py", MANAGED) == "tools/a.py"
    assert ta.check_path("AGENTS.md", MANAGED) == "AGENTS.md"


def test_three_way_clean_for_non_overlapping_edits():
    assert ta.three_way("A\nb\nc\n", "a\nb\nc\n", "a\nb\nC\n") == ("clean", "A\nb\nC\n")


def test_three_way_conflict_on_same_line_returns_no_text():
    assert ta.three_way("x\n", "a\n", "y\n") == ("conflict", None)


def test_three_way_missing_base_is_conflict():
    assert ta.three_way("x\n", None, "y\n") == ("conflict", None)


def test_three_way_missing_theirs_or_ours_is_conflict():
    assert ta.three_way("x\n", "a\n", None) == ("conflict", None)
    assert ta.three_way(None, "a\n", "y\n") == ("conflict", None)


def test_apply_clean_refuses_before_any_write(tmp_path):
    clean = [{"path": "tools/a.py", "status": "added"}, {"path": "../escape.txt", "status": "added"}]
    with pytest.raises(ta.PathRefused):
        ta.apply_clean(tmp_path, clean, lambda p: "new\n", MANAGED)
    assert not (tmp_path / "tools" / "a.py").exists()
    assert not (tmp_path.parent / "escape.txt").exists()


def test_apply_clean_writes_added_and_modified(tmp_path):
    clean = [{"path": "tools/a.py", "status": "added"}, {"path": "AGENTS.md", "status": "modified"}]
    got = ta.apply_clean(tmp_path, clean, lambda p: f"text of {p}\n", MANAGED)
    assert got == {"written": ["tools/a.py", "AGENTS.md"], "deleted": []}
    assert (tmp_path / "tools" / "a.py").read_text() == "text of tools/a.py\n"
    assert (tmp_path / "AGENTS.md").read_text() == "text of AGENTS.md\n"


def test_apply_clean_deletes_removed_file(tmp_path):
    f = tmp_path / "tools" / "gone.py"
    f.parent.mkdir()
    f.write_text("old\n")
    got = ta.apply_clean(tmp_path, [{"path": "tools/gone.py", "status": "removed"}], None, MANAGED)
    assert got == {"written": [], "deleted": ["tools/gone.py"]}
    assert not f.exists()


def test_apply_clean_moves_renamed_file(tmp_path):
    old = tmp_path / "tools" / "old.py"
    old.parent.mkdir()
    old.write_text("body\n")
    clean = [{"path": "tools/new.py", "status": "renamed"}, {"path": "tools/old.py", "status": "renamed-from"}]
    got = ta.apply_clean(tmp_path, clean, lambda p: "body\n", MANAGED)
    assert got == {"written": ["tools/new.py"], "deleted": ["tools/old.py"]}
    assert (tmp_path / "tools" / "new.py").read_text() == "body\n"
    assert not old.exists()


def test_apply_clean_refuses_unknown_status(tmp_path):
    with pytest.raises(ValueError):
        ta.apply_clean(tmp_path, [{"path": "tools/a.py", "status": "copied"}], None, MANAGED)


def test_merge_overridden_writes_clean_and_leaves_conflict_untouched(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "a.py").write_text("mine 1\nb\nc\n")
    (tmp_path / "tools" / "b.py").write_text("x\n")
    base = {"tools/a.py": "1\nb\nc\n", "tools/b.py": "a\n"}
    theirs = {"tools/a.py": "1\nb\nC\n", "tools/b.py": "y\n"}
    overridden = [
        {"path": "tools/a.py", "status": "modified", "why": ""},
        {"path": "tools/b.py", "status": "modified", "why": ""},
    ]
    got = ta.merge_overridden(tmp_path, overridden, base.get, theirs.get, MANAGED)
    assert got == {"merged": ["tools/a.py"], "conflicted": ["tools/b.py"]}
    assert (tmp_path / "tools" / "a.py").read_text() == "mine 1\nb\nC\n"
    assert (tmp_path / "tools" / "b.py").read_text() == "x\n"


def test_merge_overridden_conflicts_without_base_missing_file_or_removal(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "r.py").write_text("x\n")
    overridden = [
        {"path": "tools/r.py", "status": "removed", "why": ""},
        {"path": "tools/missing.py", "status": "modified", "why": ""},
    ]
    got = ta.merge_overridden(tmp_path, overridden, {"tools/missing.py": "a\n"}.get, {"tools/missing.py": "b\n"}.get,
                              MANAGED)
    assert got == {"merged": [], "conflicted": ["tools/r.py", "tools/missing.py"]}
    assert not (tmp_path / "tools" / "missing.py").exists()


def test_merge_overridden_conflicts_when_theirs_is_absent_at_target(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "t.py").write_text("mine\n")
    overridden = [{"path": "tools/t.py", "status": "modified", "why": ""}]
    got = ta.merge_overridden(tmp_path, overridden, {"tools/t.py": "a\n"}.get, {}.get, MANAGED)
    assert got == {"merged": [], "conflicted": ["tools/t.py"]}
    assert (tmp_path / "tools" / "t.py").read_text() == "mine\n"


def test_template_move_to_agent_dir_renames_cleanly(tmp_path):
    # tests/test_x.py -> tests/agent/test_x.py (issue 532): the new file is written, the old one removed
    old = tmp_path / "tests" / "test_x.py"
    old.parent.mkdir()
    old.write_text("body\n")
    clean = [{"path": "tests/agent/test_x.py", "status": "renamed"}, {"path": "tests/test_x.py", "status": "renamed-from"}]
    got = ta.apply_clean(tmp_path, clean, lambda p: "body\n", ["tests/"])
    assert got == {"written": ["tests/agent/test_x.py"], "deleted": ["tests/test_x.py"]}
    assert (tmp_path / "tests" / "agent" / "test_x.py").read_text() == "body\n"
    assert not old.exists()


def test_project_override_on_old_test_path_blocks_the_delete_and_is_reported(tmp_path):
    old = tmp_path / "tests" / "test_x.py"
    old.parent.mkdir()
    old.write_text("mine\n")
    overridden = [{"path": "tests/test_x.py", "status": "renamed-from", "why": "local"}]
    got = ta.merge_overridden(tmp_path, overridden, {"tests/test_x.py": "body\n"}.get, {}.get, ["tests/"])
    assert got == {"merged": [], "conflicted": ["tests/test_x.py"]}
    assert old.read_text() == "mine\n"


def test_narrowed_managed_prefix_refuses_project_test():
    assert ta.check_path("tests/agent/test_x.py", ["tests/agent/"]) == "tests/agent/test_x.py"
    with pytest.raises(ta.PathRefused):
        ta.check_path("tests/test_x.py", ["tests/agent/"])
