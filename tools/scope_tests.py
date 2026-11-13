"""Test scoping: pick the test files that cover the files changed against a base ref.

`python3 tools/scope_tests.py <base-ref>` prints `ALL` (run everything) or a space-separated list of
test files (possibly empty: nothing to run). Input is `git diff --name-only <base>...HEAD`.
Design: docs/design/0009-test-scoping.md section 4.1. Any error fails open to `ALL`, never to fewer tests.
"""
import fnmatch
import json
import pathlib
import subprocess
import sys

SCOPE_FILE = "tests/scope.json"
ALL = "ALL"
# Test directories side by side: the template tests (tests/agent/) and the project tests (tests/).
TEST_DIRS = ("tests", "tests/agent")
# Changed paths that force a full run (fnmatch patterns on the repo-relative path; `*` also matches `/`).
FULL_RUN = (
    "tests/conftest.py",
    "tests/agent/conftest.py",
    SCOPE_FILE,
    "tools/scope_tests.py",
    "Makefile",
    ".github/*",  # workflows, actions, rulesets and every other file under .github/
    "tools/liveness.py",
    "tools/ci/*",
    "tools/check/*",
    "pyproject.toml",
    "requirements*.txt",
    "tools/ci/install_tools.sh",
)
# Changes that need no test: documentation only.
NO_TESTS = ("docs/*", "*.md")


def matches(path, patterns):
    return any(fnmatch.fnmatchcase(path, p) for p in patterns)


def changed_files(base):
    out = subprocess.run(["git", "diff", "--name-only", f"{base}...HEAD"],
                         check=True, capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line]


def load_scope(path=SCOPE_FILE):
    """Extra edges {"tools/x.py": ["tests/test_y.py", ...]}. Missing file = no extras; broken file raises."""
    p = pathlib.Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    if not isinstance(data, dict) or not all(
            isinstance(v, list) and all(isinstance(t, str) for t in v) for v in data.values()):
        raise ValueError(f"{path}: expected an object mapping paths to lists of test files")
    return data


def select(paths, scope, root="."):
    """ALL or a sorted list of test files for the changed `paths` (first matching rule wins)."""
    if any(matches(p, FULL_RUN) for p in paths):
        return ALL
    base = pathlib.Path(root)
    tests = set()
    for p in paths:
        name = pathlib.PurePosixPath(p)
        if matches(p, NO_TESTS) and p not in scope:
            continue
        if p.startswith("tests/") and name.parent.as_posix() in TEST_DIRS and name.name.startswith("test_") \
                and name.suffix == ".py":
            tests.add(p)
            continue
        if p.startswith("tools/") and name.suffix == ".py":
            found = False
            for d in TEST_DIRS:
                own = f"{d}/test_{name.stem}.py"
                if (base / own).exists():
                    tests.add(own)
                    found = True
            for extra in scope.get(p, []):
                tests.add(extra)
                found = True
            if not found:
                return ALL
            continue
        if p in scope:
            tests.update(scope[p])
            continue
        return ALL  # unknown kind of file: be safe
    return sorted(t for t in tests if (base / t).exists())


def main(argv) -> int:
    if len(argv) != 1:
        print("usage: scope_tests.py <base-ref>", file=sys.stderr)
        print(ALL)
        return 2
    try:
        result = select(changed_files(argv[0]), load_scope())
    except (subprocess.CalledProcessError, OSError, ValueError):  # includes bad JSON
        result = ALL
    print(result if result == ALL else " ".join(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
