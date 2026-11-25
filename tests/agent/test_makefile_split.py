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


def test_each_part_runs_something():
    for p in PARTS:
        assert dry(p).strip(), p
