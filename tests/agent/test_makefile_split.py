"""make check is composed of check-lint, check-tests, check-workflows and check-repo (validate.yml runs each as a job)."""
import os
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PARTS = ["check-lint", "check-tests", "check-workflows", "check-repo"]


def dry(target):
    env = {k: v for k, v in os.environ.items() if k not in ("PR_BASE_REF", "NIGHTLY_HEAVY_TESTS")}
    out = subprocess.run(["make", "-n", "--no-print-directory", target], cwd=ROOT, check=True, capture_output=True,
                         text=True, env=env).stdout
    return out


def commands(text):
    """Leaf commands of a dry run: lines that do not just call a sub-make."""
    return [line for line in text.splitlines() if line.strip() and "$(MAKE)" not in line and not re.search(r"make .*--no-print-directory (check-|type-check|unit-tests|test-evidence|project-check)", line)]


def test_check_calls_exactly_the_four_targets_in_order():
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    body = text[text.index("\ncheck:\n"):text.index(".PHONY: check-lint")]
    assert re.findall(r"\$\(MAKE\) --no-print-directory (\S+)", body) == PARTS


def test_check_runs_exactly_the_union_of_the_four_targets():
    union = "".join(dry(p) for p in PARTS)
    assert sorted(commands(dry("check"))) == sorted(commands(union))
    assert commands(dry("check"))


MARKS = {"check-lint": "ruff check", "check-tests": "pytest", "check-workflows": "actionlint",
         "check-repo": "check_pr_form.py"}  # one command each part must run, not just any output


def test_each_part_runs_its_own_check():
    assert sorted(MARKS) == sorted(PARTS)
    for p in PARTS:
        assert MARKS[p] in dry(p), p


def unit_tests(*args, cwd=ROOT, dry_run=True):
    env = {k: v for k, v in os.environ.items() if k not in ("PR_BASE_REF", "NIGHTLY_HEAVY_TESTS")}
    cmd = ["make", "--no-print-directory", *(["-n"] if dry_run else []), "unit-tests", *args]
    return subprocess.run(cmd, check=False, cwd=cwd, capture_output=True, text=True, env=env)


def test_full_run_measures_coverage_and_checks_the_floor():
    out = unit_tests().stdout
    assert "coverage run --source=tools" in out and "python3 tools/check/check_coverage.py;" in out
    assert "import coverage" not in out  # no silent fallback to a plain run when the tool is missing


def test_scoped_run_runs_only_the_scoped_files_and_skips_the_floor():
    out = unit_tests("SCOPE_OUT=tests/agent/test_x.py").stdout
    assert "tests/agent/test_x.py && python3 tools/check/check_coverage.py --scoped" in out
    assert "coverage run" not in out


def test_empty_scope_runs_no_tests():
    out = unit_tests("SCOPE_OUT=").stdout
    assert "no tests in scope" in out and "pytest" not in out


def _tree(tmp_path, floor):
    (tmp_path / "Makefile").write_text((ROOT / "Makefile").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "bin").mkdir()
    stub = tmp_path / "bin" / "pytest"
    stub.write_text("#!/bin/sh\necho plain-pytest-ran\n", encoding="utf-8")
    stub.chmod(0o755)
    if floor:
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "coverage.json").write_text('{"floor": 40}', encoding="utf-8")
    return ["SCOPE_OUT=ALL", f"PATH={tmp_path / 'bin'}:{os.environ['PATH']}"]


def test_floor_file_without_the_coverage_tool_fails_instead_of_running_plain(tmp_path):
    args = _tree(tmp_path, floor=True)
    res = unit_tests(*args, "COVERAGE=no-such-coverage-tool", cwd=tmp_path, dry_run=False)
    assert res.returncode != 0 and "no-such-coverage-tool is not installed" in res.stderr
    assert "plain-pytest-ran" not in res.stdout


def test_no_floor_file_runs_plain_pytest(tmp_path):
    args = _tree(tmp_path, floor=False)
    res = unit_tests(*args, "COVERAGE=no-such-coverage-tool", cwd=tmp_path, dry_run=False)
    assert res.returncode == 0 and "plain-pytest-ran" in res.stdout
