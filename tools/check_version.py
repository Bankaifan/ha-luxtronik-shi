"""Check that manifest version, CHANGELOG and (optional) git tag agree. Run from repo root.

Usage: python tools/check_version.py [git-ref]   e.g. refs/tags/v0.3.0
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
version = json.loads((ROOT / "custom_components" / "luxtronik_shi" / "manifest.json").read_text())["version"]
errors = []

if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    errors.append(f"Manifest-Version '{version}' ist kein X.Y.Z")

changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
if not re.search(rf"^## \[{re.escape(version)}\]", changelog, re.MULTILINE):
    errors.append(f"CHANGELOG.md hat keinen Abschnitt '## [{version}]'")

ref = sys.argv[1] if len(sys.argv) > 1 else ""
if ref.startswith("refs/tags/"):
    tag = ref.removeprefix("refs/tags/")
    if tag != f"v{version}":
        errors.append(f"Tag '{tag}' passt nicht zur Manifest-Version v{version}")
    if re.search(rf"^## \[{re.escape(version)}\].*unveröffentlicht", changelog, re.MULTILINE):
        errors.append(f"CHANGELOG: Version {version} ist noch als 'unveröffentlicht' markiert")

if errors:
    print("\n".join(errors))
    sys.exit(1)
print(f"Version {version} ok")
