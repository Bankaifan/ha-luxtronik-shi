"""Check that the project version has a section in CHANGELOG.md.

Version source (first match wins):
  1. env VERSION_FILE (+ optional VERSION_REGEX with one group, default: first x.y.z found)
  2. a file named VERSION in the repo root
If neither exists, or there is no CHANGELOG.md, the check is skipped (exit 0).
"""
import os
import re
import sys
from pathlib import Path

SEMVER = r"\d+\.\d+\.\d+"


def read_version() -> str | None:
    name = os.environ.get("VERSION_FILE")
    path = Path(name) if name else Path("VERSION")
    if not path.is_file():
        if name:
            sys.exit(f"VERSION_FILE {name} does not exist")
        return None
    text = path.read_text(encoding="utf-8")
    regex = os.environ.get("VERSION_REGEX") or rf"({SEMVER})"
    match = re.search(regex, text)
    if not match:
        sys.exit(f"no version found in {path} with pattern {regex}")
    return match.group(1)


def main() -> int:
    version = read_version()
    changelog = Path("CHANGELOG.md")
    if version is None or not changelog.is_file():
        print("check_version: skipped (no version source or no CHANGELOG.md)")
        return 0
    if not re.fullmatch(SEMVER, version):
        print(f"check_version: '{version}' is not x.y.z")
        return 1
    text = changelog.read_text(encoding="utf-8")
    if not re.search(r"^## \[Unreleased\]", text, re.MULTILINE | re.IGNORECASE):
        print("check_version: CHANGELOG.md has no '## [Unreleased]' section")
        return 1
    if not re.search(rf"^## \[{re.escape(version)}\]", text, re.MULTILINE):
        print(f"check_version: CHANGELOG.md has no '## [{version}]' section")
        return 1
    print(f"check_version: ok ({version})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
