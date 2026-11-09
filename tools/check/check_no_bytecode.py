"""Fail if compiled Python bytecode is tracked by git.

Build artifacts (__pycache__/, *.pyc, *.pyo) go stale and must not be committed.
"""
import subprocess
import sys


def main() -> int:
    out = subprocess.run(
        ["git", "ls-files", "-z"], check=True, capture_output=True, text=True
    ).stdout
    bad = [
        p
        for p in out.split("\0")
        if p and (p.endswith((".pyc", ".pyo")) or "__pycache__/" in p or p.startswith("__pycache__/"))
    ]
    for p in bad:
        print(f"check_no_bytecode: tracked bytecode {p}, run 'git rm --cached' on it")
    if bad:
        return 1
    print("check_no_bytecode: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
