"""Classify a dependabot PR as "patch", "minor" or "major" (conservative).

Usage: dependabot_update_type.py TITLE [UPDATED_DEPENDENCIES_JSON]
Prints one word. If the second argument (output `updated-dependencies-json` of
dependabot/fetch-metadata) is non-empty, it decides: the highest update type of all
dependencies wins, covering grouped PRs. Otherwise the title is parsed, including range
titles ("Update x requirement from >=1,<2 to >=2,<3"). Anything that cannot be parsed
(grouped titles without metadata, odd versions) is "major", so a human looks at it.
A 0.x minor bump counts as "major" in titles because 0.x minors may break.
"""
import json
import re
import sys

ORDER = {"patch": 0, "minor": 1, "major": 2}
_TITLE = re.compile(r"\bfrom\s+(.+?)\s+to\s+(.+?)\s*$")
_VERSION = re.compile(r"(?<![\d.])v?(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_META = {"version-update:semver-patch": "patch", "version-update:semver-minor": "minor"}


def _step(old, new):
    """Change between two (major, minor, patch) tuples, or None if equal."""
    if old == new:
        return None
    if old[0] != new[0] or new < old or (new[0] == 0 and old[1] != new[1]):
        return "major"
    return "minor" if old[1] != new[1] else "patch"


def _versions(text):
    return [tuple(int(x or 0) for x in m.groups()) for m in _VERSION.finditer(text)]


def classify_title(title: str) -> str:
    m = _TITLE.search(title.strip())
    if not m:
        return "major"
    old, new = (_versions(g) for g in m.groups())
    if not old or len(old) != len(new):
        return "major"
    steps = [s for s in map(_step, old, new) if s]
    # Identical numbers (pre-release or tag change): do not guess.
    return max(steps, key=ORDER.get) if steps else "major"


def classify_metadata(raw: str) -> str:
    """Highest update type in fetch-metadata's updated-dependencies-json; unknown is "major"."""
    try:
        deps = json.loads(raw)
    except ValueError:
        return "major"
    if not isinstance(deps, list) or not deps:
        return "major"
    kinds = [_META.get(d.get("updateType", ""), "major") if isinstance(d, dict) else "major" for d in deps]
    return max(kinds, key=ORDER.get)


def classify(title: str, metadata: str = "") -> str:
    return classify_metadata(metadata) if metadata.strip() else classify_title(title)


if __name__ == "__main__":
    args = sys.argv[1:] + ["", ""]
    print(classify(args[0], args[1]))
