"""Fail a PR that changes a template-managed path without a changelog fragment (design 0013 option A, issue #468).

Usage: check_version_bump.py [BASE_REF]   (BASE_REF default: origin/main)
Changed files: `git diff --name-only BASE_REF...HEAD`. Managed paths: .agents/managed.json.
Fails when (1) a managed path changed and no `changelog.d/<issue>.md` was added or changed, (2) the PR edits VERSION
(a script on main assigns it after the merge, tools/release_fragments.py), (3) a fragment is malformed.
A diff without managed paths passes. Env PR_HEAD_REF=release/next (the train's release PR): only VERSION, CHANGELOG.md
and changelog.d/ may change, VERSION may be edited, no fragment may be added (issue #570). The Makefile runs it only when PR_BASE_REF is set.
"""
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from managed_guard import template_managed
from release_fragments import FRAGMENT_DIR, FRAGMENT_NAME, Refused, parse_fragment
from template_sync import CONFIG, ConfigError, is_managed

VERSION_FILE = "VERSION"
RELEASE_BRANCH = "release/next"  # head of the train's release PR (tools/train.py)


def is_downstream():
    """A downstream project has .agents/template.json and no VERSION policy of its own (design 0014 section 4.4)."""
    return CONFIG.is_file()


def is_fragment(path):
    p = pathlib.PurePosixPath(path)
    return str(p.parent) == FRAGMENT_DIR and bool(FRAGMENT_NAME.fullmatch(p.name))


def is_release_path(path):
    return path in (VERSION_FILE, "CHANGELOG.md") or path.startswith(FRAGMENT_DIR + "/")


def errors(changed, managed, read=None, head_ref=""):
    """Error lines for a changed-file list; empty list means fine. read(path) -> text of a fragment, None: not read.
    The release PR (head `release/next`, issue #570) may only touch VERSION, CHANGELOG.md and changelog.d/: it may
    edit VERSION and must not add fragments."""
    if head_ref == RELEASE_BRANCH:
        other = [f for f in changed if not is_release_path(f)]
        out = [f"release PR touches other paths: {', '.join(other)}"] if other else []
        added = [f for f in changed if is_fragment(f) and (read is None or read(f) is not None)]
        if added:
            out.append(f"release PR must not add changelog fragments: {', '.join(added)}")
        return out
    out = []
    if VERSION_FILE in changed:
        out.append("VERSION must not be edited in a PR: add a changelog fragment, the version is assigned after the merge")
    frags = [f for f in changed if is_fragment(f)]
    bad = [f for f in changed if f != VERSION_FILE and not is_fragment(f) and is_managed(f, managed)]
    if bad and not frags:
        out.append(f"managed paths changed without a changelog fragment {FRAGMENT_DIR}/<issue>.md: {', '.join(bad)}")
    for f in frags if read else []:
        text = read(f)
        if text is None:
            continue  # deleted by the PR
        try:
            parse_fragment(f, text)
        except Refused as e:
            out.append(f"bad changelog fragment: {e}")
    return out


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def read_file(path):
    p = pathlib.Path(path)
    return p.read_text(encoding="utf-8") if p.is_file() else None


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    base = args[0] if args else "origin/main"
    if is_downstream():
        print("check_version_bump: skipped (downstream project: .agents/template.json exists)")
        return 0
    try:
        changed = [f for f in git("diff", "--name-only", f"{base}...HEAD").split("\n") if f]
        errs = errors(changed, template_managed(), read_file, os.environ.get("PR_HEAD_REF", ""))
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
