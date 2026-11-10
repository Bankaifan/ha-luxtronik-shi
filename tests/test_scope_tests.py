import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import scope_tests as st

ROOT = pathlib.Path(__file__).resolve().parent.parent
# tools/*.py without a same-name tests/test_<name>.py: they fall back to a full run. Project generators (override).
NO_TEST_TOOLS = [
    "dashboard_layout",
    "entity_docs_entries",
    "entity_docs_texts",
    "gen_contract",
    "gen_dashboard",
    "gen_entity_docs",
    "gen_icons",
    "gen_register_docs",
    "gen_translations",
    "gen_yaml",
]


def sel(paths, scope=None):
    return st.select(paths, scope or {}, root=ROOT)


def test_tool_selects_its_test():
    assert sel(["tools/tier.py"]) == ["tests/test_tier.py"]


def test_several_tools_are_sorted_and_deduplicated():
    assert sel(["tools/tier.py", "tools/status.py", "tools/tier.py"]) == ["tests/test_status.py", "tests/test_tier.py"]


def test_ci_tool_gives_all():
    assert sel(["tools/ci/risk.py"]) == st.ALL


@pytest.mark.parametrize("path", [
    "tests/conftest.py", "tests/scope.json", "tools/scope_tests.py", "Makefile",
    ".github/workflows/validate.yml", ".github/actions/x/action.yml", ".github/rulesets/main.json",
    ".github/CODEOWNERS", "tools/liveness.py", "tools/ci/risk.py", "tools/ci/install_tools.sh",
    "tools/check/check_version.py", "pyproject.toml", "requirements.txt", "requirements-dev.txt",
])
def test_full_run_paths(path):
    assert sel([path, "tools/tier.py"]) == st.ALL


@pytest.mark.parametrize("path", ["docs/design/0009-test-scoping.md", "README.md", "CHANGELOG.md", "HANDOVER.md"])
def test_docs_select_nothing(path):
    assert sel([path]) == []


def test_empty_diff_selects_nothing():
    assert sel([]) == []


def test_changed_test_selects_itself():
    assert sel(["tests/test_tier.py"]) == ["tests/test_tier.py"]


def test_deleted_test_is_not_selected():
    assert sel(["tests/test_gone.py"]) == []


def test_scope_extras_are_added():
    scope = {"tools/guard_mark.py": ["tests/test_liveness.py"]}
    assert sel(["tools/guard_mark.py"], scope) == ["tests/test_guard_mark.py", "tests/test_liveness.py"]


def test_scope_extra_alone_covers_a_tool_without_test(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_b.py").write_text("")
    assert st.select(["tools/a.py"], {"tools/a.py": ["tests/test_b.py"]}, root=tmp_path) == ["tests/test_b.py"]


def test_unknown_tool_without_test_gives_all(tmp_path):
    assert st.select(["tools/new_tool.py"], {}, root=tmp_path) == st.ALL


def test_unknown_file_kind_gives_all():
    assert sel(["setup.cfg"]) == st.ALL


def test_no_test_tools_list_matches_tree():
    tools = {p.stem for p in (ROOT / "tools").glob("*.py")}
    missing = sorted(n for n in tools if not (ROOT / "tests" / f"test_{n}.py").exists())
    assert missing == NO_TEST_TOOLS
    for name in NO_TEST_TOOLS:
        assert sel([f"tools/{name}.py"]) == st.ALL


def test_load_scope_missing_is_empty(tmp_path):
    assert st.load_scope(tmp_path / "nope.json") == {}


def test_load_scope_repo_file_is_valid():
    assert isinstance(st.load_scope(ROOT / st.SCOPE_FILE), dict)


@pytest.mark.parametrize("text", ["{not json", "[]", '{"tools/a.py": "tests/test_a.py"}', '{"tools/a.py": [1]}'])
def test_load_scope_rejects_broken(tmp_path, text):
    p = tmp_path / "scope.json"
    p.write_text(text)
    with pytest.raises(ValueError):
        st.load_scope(p)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "config", "user.email", "t@example.com")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tools" / "a.py").write_text("")
    (tmp_path / "tests" / "test_a.py").write_text("")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "base")
    git(tmp_path, "checkout", "-q", "-b", "topic")
    return tmp_path


def run(cwd, *args):
    return subprocess.run([sys.executable, str(ROOT / "tools" / "scope_tests.py"), *args], cwd=cwd,
                          check=False, capture_output=True, text=True)


def test_cli_selects_test_for_changed_tool(repo):
    (repo / "tools" / "a.py").write_text("x = 1\n")
    git(repo, "commit", "-q", "-am", "change")
    r = run(repo, "main")
    assert (r.returncode, r.stdout.strip()) == (0, "tests/test_a.py")


def test_cli_empty_diff_prints_nothing(repo):
    r = run(repo, "main")
    assert (r.returncode, r.stdout) == (0, "\n")


def test_cli_docs_only_prints_nothing(repo):
    (repo / "README.md").write_text("hi\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "docs")
    assert run(repo, "main").stdout == "\n"


def test_cli_bad_base_ref_gives_all(repo):
    assert run(repo, "origin/nope").stdout.strip() == "ALL"


@pytest.mark.parametrize("text", ["{broken", json.dumps([1])])
def test_cli_unreadable_scope_gives_all(repo, text):
    # scope.json stays untracked, so only the loader (not the FULL_RUN rule) can cause ALL here
    (repo / "tests" / "scope.json").write_text(text)
    (repo / "tools" / "a.py").write_text("x = 1\n")
    git(repo, "commit", "-q", "-am", "change")
    assert run(repo, "main").stdout.strip() == "ALL"


def test_cli_without_argument_gives_all(repo):
    r = run(repo)
    assert (r.returncode, r.stdout.strip()) == (2, "ALL")
