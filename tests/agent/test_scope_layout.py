import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent / "tools"))
import scope_tests as st


def make_files(root, *files):
    for f in files:
        p = root / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("")
    return root


def sel(root, paths, scope=None):
    return st.select(paths, scope or {}, root=root)


def test_template_test_selects_itself(tmp_path):
    make_files(tmp_path, "tests/agent/test_a.py")
    assert sel(tmp_path, ["tests/agent/test_a.py"]) == ["tests/agent/test_a.py"]


def test_project_test_selects_itself(tmp_path):
    make_files(tmp_path, "tests/test_p.py")
    assert sel(tmp_path, ["tests/test_p.py"]) == ["tests/test_p.py"]


def test_project_and_template_tests_side_by_side(tmp_path):
    make_files(tmp_path, "tests/agent/test_a.py", "tests/test_p.py")
    assert sel(tmp_path, ["tests/test_p.py", "tests/agent/test_a.py"]) == ["tests/agent/test_a.py", "tests/test_p.py"]


def test_tool_maps_to_template_test(tmp_path):
    make_files(tmp_path, "tests/agent/test_a.py")
    assert sel(tmp_path, ["tools/a.py"]) == ["tests/agent/test_a.py"]


def test_tool_maps_to_both_test_trees(tmp_path):
    make_files(tmp_path, "tests/agent/test_a.py", "tests/test_a.py")
    assert sel(tmp_path, ["tools/a.py"]) == ["tests/agent/test_a.py", "tests/test_a.py"]


def test_tool_without_test_in_either_tree_gives_all(tmp_path):
    make_files(tmp_path, "tests/agent/test_b.py", "tests/test_c.py")
    assert sel(tmp_path, ["tools/a.py"]) == st.ALL


def test_deleted_template_test_is_not_selected(tmp_path):
    make_files(tmp_path, "tests/test_p.py")
    assert sel(tmp_path, ["tests/agent/test_gone.py"]) == []


def test_template_conftest_gives_all(tmp_path):
    make_files(tmp_path, "tests/agent/conftest.py")
    assert sel(tmp_path, ["tests/agent/conftest.py"]) == st.ALL


def test_nested_test_dir_gives_all(tmp_path):
    make_files(tmp_path, "tests/agent/sub/test_x.py")
    assert sel(tmp_path, ["tests/agent/sub/test_x.py"]) == st.ALL
