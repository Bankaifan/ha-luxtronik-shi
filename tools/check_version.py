"""Check that manifest version, CHANGELOG and (optional) git tag agree. Run from repo root.

Usage:
  python tools/check_version.py                    # version format + CHANGELOG section exists
  python tools/check_version.py --release          # additionally: section is dated (ready to release)
  python tools/check_version.py refs/tags/v0.3.0   # tag must match the manifest version, section dated
  python tools/check_version.py --version          # print the manifest version
  python tools/check_version.py --notes            # print the CHANGELOG section of the manifest version
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
version = json.loads((ROOT / "custom_components" / "luxtronik_shi" / "manifest.json").read_text())["version"]
changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
args = sys.argv[1:]

if "--version" in args:
    print(version)
    sys.exit(0)

heading = re.compile(rf"^## \[{re.escape(version)}\](.*)$", re.MULTILINE)
match = heading.search(changelog)

if "--notes" in args:
    if not match:
        sys.exit(f"CHANGELOG.md has no section '## [{version}]'")
    rest = changelog[match.end() :]
    end = re.search(r"^## \[|^\[[^\]]+\]: ", rest, re.MULTILINE)
    print((rest[: end.start()] if end else rest).strip())
    sys.exit(0)

errors = []
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    errors.append(f"Manifest version '{version}' is not X.Y.Z")
if not match:
    errors.append(f"CHANGELOG.md has no section '## [{version}]'")

ref = next((a for a in args if a.startswith("refs/")), "")
release = "--release" in args or ref.startswith("refs/tags/")
if ref.startswith("refs/tags/") and ref.removeprefix("refs/tags/") != f"v{version}":
    errors.append(f"Tag '{ref.removeprefix('refs/tags/')}' does not match manifest version v{version}")
if release and match and not re.search(r"\d{4}-\d{2}-\d{2}", match.group(1)):
    errors.append(f"CHANGELOG: section '## [{version}]' needs a release date (YYYY-MM-DD), not 'unreleased'")

if errors:
    print("\n".join(errors))
    sys.exit(1)
print(f"Version {version} ok" + (" (ready to release)" if release else ""))
