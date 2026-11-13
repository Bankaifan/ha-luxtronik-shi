"""Check that the project version has a section in CHANGELOG.md, and that a PR's new version is free (issue #462).

Version source (first match wins):
  1. env VERSION_FILE (+ optional VERSION_REGEX with one group, default: first x.y or x.y.z found)
  2. a file named VERSION in the repo root
If neither exists, or there is no CHANGELOG.md, the check is skipped (exit 0).

Release check, only with env PR_BASE_REF (pull requests): when the version differs from the base branch's
(origin/PR_BASE_REF), the new version must have no tag yet (`v<version>` or `<version>`) and must be greater than the
highest tag. Tags come from `git tag --list`; pre-release suffixes (1.0.0-rc1) sort before the final version.

CLI: check_version.py --next minor|patch|major   prints the next version after the highest tag (no version file needed).
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

SEMVER = r"\d+\.\d+(?:\.\d+)?"  # x.y or x.y.z
# default search: a version not glued to other word characters or dots, so "v1.0" and "1.2.3.4" are not found
DEFAULT_REGEX = rf"(?<![\w.])({SEMVER})(?![\w.])"
TAG = re.compile(r"v?(\d+)\.(\d+)(?:\.(\d+))?(?:-([0-9A-Za-z.]+))?")  # v1.2.3, 1.2, 1.2.3-rc1
BUMPS = ("major", "minor", "patch")


def find_version(text: str) -> str | None:
    """The version in a version file's text (VERSION_REGEX or the first x.y[.z]); None when there is none."""
    match = re.search(os.environ.get("VERSION_REGEX") or DEFAULT_REGEX, text)
    return match.group(1) if match else None


def read_version() -> str | None:
    name = os.environ.get("VERSION_FILE")
    path = Path(name) if name else Path("VERSION")
    if not path.is_file():
        if name:
            sys.exit(f"VERSION_FILE {name} does not exist")
        return None
    version = find_version(path.read_text(encoding="utf-8"))
    if version is None:
        sys.exit(f"no version found in {path} with pattern {os.environ.get('VERSION_REGEX') or DEFAULT_REGEX}")
    return version


def parse(text: str):
    """Sort key (major, minor, patch, rank) of a version or tag; None when it is not one. A final version ranks
    above its pre-releases; pre-release parts compare as numbers when they are numbers ("rc2" < "rc10")."""
    m = TAG.fullmatch(text)
    if not m:
        return None
    major, minor, patch, pre = int(m[1]), int(m[2]), int(m[3] or 0), m[4]
    if pre is None:
        rank = (1,)
    else:
        rank = (0, *((0, int(p)) if p.isdigit() else (1, p) for p in re.findall(r"\d+|[A-Za-z]+", pre)))
    return (major, minor, patch, rank)


def released(tags):
    """{tag: sort key} for the tags that name a version."""
    return {t: key for t in tags if (key := parse(t)) is not None}


def next_version(tags, bump: str) -> str:
    """The next version after the highest tag (0.0.0 without tags): minor 1.0 -> 1.1.0, patch 1.0 -> 1.0.1."""
    tops = released(tags).values()
    major, minor, patch = max(tops, default=(0, 0, 0, ()))[:3]
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def release_errors(version: str, tags) -> list[str]:
    """Error lines for a PR's new version against the tags; empty list means fine."""
    out = []
    taken = [t for t in tags if t in (version, f"v{version}")]
    if taken:
        out.append(f"tag {taken[0]} already exists: version {version} is taken, pick a version above the release")
    known = released(tags)
    new = parse(version)
    if known and new is not None and new <= max(known.values()):
        top = max(known, key=known.get)
        out.append(f"version {version} is not above the highest release {top}; next: "
                   f"{next_version(tags, 'minor')} (minor) or {next_version(tags, 'patch')} (patch)")
    return out


def git(*args) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def git_tags() -> list[str]:
    return git("tag", "--list").split()


def base_version(ref: str, name: str) -> str | None:
    """The version in the file `name` at git `ref`; None when the file or the version is not there (a new version)."""
    done = subprocess.run(["git", "show", f"{ref}:{name}"], check=False, capture_output=True, text=True)
    return find_version(done.stdout) if done.returncode == 0 else None


def pr_errors(version: str, name: str) -> list[str]:
    """Release errors when this PR changes the version; nothing without PR_BASE_REF or when the version is unchanged."""
    base = os.environ.get("PR_BASE_REF")
    if not base or base_version(f"origin/{base}", name) == version:
        return []
    return release_errors(version, git_tags())


def main(argv=()) -> int:
    parser = argparse.ArgumentParser(description="Check the changelog section and the version tags; --next prints a version.")
    parser.add_argument("--next", choices=BUMPS, dest="bump", help="print the next version after the highest tag")
    args = parser.parse_args(list(argv))
    try:
        if args.bump:
            print(next_version(git_tags(), args.bump))
            return 0
        name = os.environ.get("VERSION_FILE") or "VERSION"
        version = read_version()
        changelog = Path("CHANGELOG.md")
        if version is None or not changelog.is_file():
            print("check_version: skipped (no version source or no CHANGELOG.md)")
            return 0
        if not re.fullmatch(SEMVER, version):
            print(f"check_version: '{version}' is not x.y or x.y.z")
            return 1
        text = changelog.read_text(encoding="utf-8")
        if not re.search(r"^## \[Unreleased\]", text, re.MULTILINE | re.IGNORECASE):
            print("check_version: CHANGELOG.md has no '## [Unreleased]' section")
            return 1
        if not re.search(rf"^## \[{re.escape(version)}\]", text, re.MULTILINE):
            print(f"check_version: CHANGELOG.md has no '## [{version}]' section")
            return 1
        errs = pr_errors(version, name)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"check_version: cannot run: {e}", file=sys.stderr)
        return 2
    for e in errs:
        print(f"check_version: {e}")
    if errs:
        return 1
    print(f"check_version: ok ({version})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
