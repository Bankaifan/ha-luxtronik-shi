"""Check test evidence: new or changed tests must fail without the change.

Usage: check_test_evidence.py [BASE_REF] [--body-file FILE]   (BASE_REF default: origin/main; body default: env PR_BODY)

Takes the test files changed between merge-base(BASE_REF, HEAD) and HEAD, checks out the merge-base into a temporary
git worktree, copies the changed test files into it and runs them there. At least one failure (or collection error)
is the expected "red without the change". Exit 0 = red, or exempt; exit 1 = all tests pass without the change;
exit 2 = the check itself could not run.
Exempt: no code file changed (docs only), no test file changed, or a body line `Test evidence exempt: <reason>`
with a non-empty reason (pure refactor, docs, tests for behaviour that already existed).
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

CODE_SUFFIXES = {".py", ".sh", ".js", ".ts", ".yml", ".yaml"}
EXEMPT = re.compile(r"^\s*Test evidence exempt:[ \t]*(\S.*?)\s*$", re.IGNORECASE | re.MULTILINE)
EMPTY_EXEMPT = re.compile(r"^\s*Test evidence exempt:", re.IGNORECASE | re.MULTILINE)


def is_test(path):
    p = pathlib.PurePosixPath(path)
    return p.parts[0] == "tests" or p.name.startswith("test_") or p.name.endswith("_test.py")


def is_code(path):
    return not is_test(path) and pathlib.PurePosixPath(path).suffix in CODE_SUFFIXES


def decide(changed, body):
    """('exempt'|'run'|'fail', message) from the changed files and the PR body."""
    tests = [f for f in changed if is_test(f)]
    if not any(is_code(f) for f in changed):
        return "exempt", "no code file changed (docs only)"
    if not tests:
        return "exempt", "no test file changed"
    m = EXEMPT.search(body)
    if m:
        return "exempt", f"exempt with reason: {m.group(1)}"
    if EMPTY_EXEMPT.search(body):
        return "fail", "`Test evidence exempt:` needs a reason"
    return "run", ""


def git(*args, cwd=None):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, cwd=cwd).stdout


def red_without_change(base, tests):
    """True if the changed tests fail against the merge-base version of the code."""
    merge_base = git("merge-base", base, "HEAD").strip()
    root = pathlib.Path(git("rev-parse", "--show-toplevel").strip())
    tmp = tempfile.mkdtemp(prefix="test-evidence-")
    work = os.path.join(tmp, "base")
    try:
        git("worktree", "add", "--detach", work, merge_base)
        for t in tests:
            if (root / t).exists():
                (pathlib.Path(work) / t).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(root / t, pathlib.Path(work) / t)
        # data files under tests/ (e.g. scope.json) are copied but are not pytest targets (pytest exits 4 on them)
        existing = [t for t in tests if t.endswith(".py") and (root / t).exists()]
        if not existing:
            return False
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "--timeout=60", *existing], check=False, cwd=work,
                           capture_output=True, text=True)
        return r.returncode in (1, 2)  # tests failed / collection error; 0 = green, 5 = nothing collected
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", work], check=False, capture_output=True, text=True)
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    body = os.environ.get("PR_BODY") or ""
    if "--body-file" in args:
        i = args.index("--body-file")
        try:
            body = pathlib.Path(args[i + 1]).read_text(encoding="utf-8", errors="replace")
        except (OSError, IndexError) as e:
            print(f"check_test_evidence: cannot read body file: {e}", file=sys.stderr)
            return 2
        del args[i:i + 2]
    base = args[0] if args else "origin/main"
    try:
        merge_base = git("merge-base", base, "HEAD").strip()
        changed = git("diff", "--name-only", "--diff-filter=AMR", merge_base, "HEAD").split()
        verdict, msg = decide(changed, body)
        if verdict == "run":
            tests = [f for f in changed if is_test(f)]
            if red_without_change(base, tests):
                verdict, msg = "exempt", "red without the change"
            else:
                verdict, msg = "fail", "the changed tests also pass without the change (add a test that fails, or state `Test evidence exempt: <reason>` in the PR body)"
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"check_test_evidence: cannot run: {e}", file=sys.stderr)
        return 2
    print(f"check_test_evidence: {'ok' if verdict == 'exempt' else 'FAIL'}: {msg}")
    return 1 if verdict == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
