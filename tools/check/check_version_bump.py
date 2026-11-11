"""Fail a PR that changes a template-managed path without bumping VERSION (design 0011, 4.1b).

Usage: check_version_bump.py [BASE_REF]   (BASE_REF default: origin/main)
Changed files: `git diff --name-only BASE_REF...HEAD`. Managed paths: .agents/managed.json.
Fails when (1) a managed path changed and VERSION did not, (2) VERSION is not `x.y`, (3) VERSION is lower than on BASE_REF.
A diff without managed paths passes. The Makefile runs it only when PR_BASE_REF is set.
"""
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from managed_guard import template_managed
from template_sync import ConfigError, is_managed

VERSION_FILE = "VERSION"


def parse(text):
    """(x, y) of an `x.y` VERSION text (one optional trailing newline), else None."""
    m = re.fullmatch(r"([0-9]+)\.([0-9]+)", text.removesuffix("\n"), flags=re.ASCII)
    return (int(m.group(1)), int(m.group(2))) if m else None


def errors(changed, managed, version_text, base_text=None):
    """Error lines for a changed-file list; empty list means fine. base_text None: VERSION is new."""
    out = []
    version = parse(version_text) if version_text is not None else None
    if version_text is None:
        out.append("VERSION is missing")
    elif version is None:
        out.append(f"VERSION {version_text.strip()!r} is not x.y (digits, one dot, no prefix)")
    elif base_text is not None and parse(base_text) and version < parse(base_text):
        out.append(f"VERSION {version_text.strip()} is lower than the base {base_text.strip()}")
    bad = [f for f in changed if f != VERSION_FILE and is_managed(f, managed)]
    if bad and VERSION_FILE not in changed:
        out.append(f"managed paths changed without a VERSION bump: {', '.join(bad)}")
    return out


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    base = args[0] if args else "origin/main"
    try:
        changed = git("diff", "--name-only", f"{base}...HEAD").split("\n")
        changed = [f for f in changed if f]
        try:
            base_text = git("show", f"{base}:{VERSION_FILE}")
        except subprocess.CalledProcessError:
            base_text = None
        path = pathlib.Path(VERSION_FILE)
        version_text = path.read_text(encoding="utf-8") if path.is_file() else None
        errs = errors(changed, template_managed(), version_text, base_text)
    except (OSError, subprocess.CalledProcessError, ConfigError) as e:
        print(f"check_version_bump: cannot run: {e}", file=sys.stderr)
        return 2
    for e in errs:
        print(f"check_version_bump: {e}")
    if not errs:
        print("check_version_bump: ok")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
