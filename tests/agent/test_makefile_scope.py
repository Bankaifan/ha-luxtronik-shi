"""make check wiring for test scoping and NIGHTLY_HEAVY_TESTS (design 0009 section 4.1/4.2).

Parses `make -n unit-tests` in a throw-away git repo so no real pytest run happens.
"""
import os
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]


def run(cmd, cwd, env=None):
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "tools").mkdir()
    (tmp_path / "tests").mkdir()
    shutil.copy(ROOT / "Makefile", tmp_path / "Makefile")
    shutil.copy(ROOT / "tools" / "scope_tests.py", tmp_path / "tools" / "scope_tests.py")
    for f in ("tools/tier.py", "tests/test_tier.py", "docs.md"):
        (tmp_path / f).write_text("x = 1\n")
    run(["git", "init", "-q", "-b", "main"], tmp_path)
    run(["git", "add", "."], tmp_path)
    run(GIT + ["commit", "-q", "-m", "base"], tmp_path)
    run(["git", "update-ref", "refs/remotes/origin/main", "main"], tmp_path)
    run(["git", "checkout", "-q", "-b", "feature"], tmp_path)
    return tmp_path


def pytest_line(repo, pr_base=None, heavy=None):
    env = {k: v for k, v in os.environ.items() if k not in ("PR_BASE_REF", "NIGHTLY_HEAVY_TESTS")}
    if pr_base is not None:
        env["PR_BASE_REF"] = pr_base
    if heavy is not None:
        env["NIGHTLY_HEAVY_TESTS"] = heavy
    return run(["make", "-n", "unit-tests"], repo, env).strip()


def change(repo, path):
    with (repo / path).open("a") as f:
        f.write("\n# changed\n")
    run(["git", "add", "."], repo)
    run(GIT + ["commit", "-q", "-m", "change"], repo)


def test_local_run_is_full(repo):
    line = pytest_line(repo)
    assert "pytest --timeout=60 -q" in line
    assert "test_tier.py" not in line and "-m" not in line


def test_pr_scopes_to_changed_tool(repo):
    change(repo, "tools/tier.py")
    assert "pytest --timeout=60 -q  tests/test_tier.py" in pytest_line(repo, pr_base="main")


def test_pr_with_makefile_change_is_full(repo):
    change(repo, "Makefile")
    line = pytest_line(repo, pr_base="main")
    assert "pytest --timeout=60 -q" in line and "test_tier.py" not in line


def test_docs_only_pr_runs_no_tests(repo):
    change(repo, "docs.md")
    line = pytest_line(repo, pr_base="main")
    assert "no tests in scope" in line and "pytest --timeout" not in line


def test_bad_base_ref_fails_open_to_full(repo):
    line = pytest_line(repo, pr_base="nope")
    assert "pytest --timeout=60 -q" in line and "test_tier.py" not in line


@pytest.mark.parametrize("heavy", [None, "", "false", "TRUE", "1"])
def test_slow_tests_stay_without_true(repo, heavy):
    assert "-m" not in pytest_line(repo, heavy=heavy)


def test_true_deselects_slow(repo):
    assert '-m "not slow"' in pytest_line(repo, heavy="true")


def test_validate_workflow_passes_variable_with_default():
    text = (ROOT / ".github" / "workflows" / "validate.yml").read_text()
    assert "NIGHTLY_HEAVY_TESTS: ${{ vars.NIGHTLY_HEAVY_TESTS || 'false' }}" in text
