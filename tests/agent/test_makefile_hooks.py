"""Optional project.mk hook for make check (design 0016 section 4.1).

Runs make in a throw-away directory that holds only a copy of the Makefile, so no real check runs.
"""
import os
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def make(cwd, *args):
    env = {k: v for k, v in os.environ.items() if k not in ("PR_BASE_REF", "NIGHTLY_HEAVY_TESTS")}
    return subprocess.run(["make", *args], cwd=cwd, check=True, capture_output=True, text=True, env=env).stdout


def project_dir(tmp_path, project_mk=None):
    shutil.copy(ROOT / "Makefile", tmp_path / "Makefile")
    if project_mk is not None:
        (tmp_path / "project.mk").write_text(project_mk)
    return tmp_path


def test_without_project_mk_hook_is_silent(tmp_path):
    repo = project_dir(tmp_path)
    assert make(repo, "project-check") == ""


def test_project_mk_recipe_runs(tmp_path):
    repo = project_dir(tmp_path, "project-check::\n\t@echo PROJECT_CHECK_RAN\n")
    assert make(repo, "project-check") == "PROJECT_CHECK_RAN\n"


def test_check_runs_project_check_last(tmp_path):
    repo = project_dir(tmp_path, "project-check::\n\t@echo PROJECT_CHECK_RAN\n")
    dry = make(repo, "-n", "check")
    # the sub-make call for project-check comes after test-evidence and before the project recipe
    assert dry.index("test-evidence") < dry.index("project-check") < dry.index("echo PROJECT_CHECK_RAN")


def test_check_without_project_mk_has_no_project_line(tmp_path):
    repo = project_dir(tmp_path)
    dry = make(repo, "-n", "check")
    assert "project-check" in dry  # the sub-make call itself is printed
    assert "PROJECT_CHECK_RAN" not in dry


def test_default_goal_stays_check(tmp_path):
    repo = project_dir(tmp_path, "build:\n\t@echo build\n")
    dry = make(repo, "-n")
    assert "unit-tests" in dry and "echo build" not in dry
