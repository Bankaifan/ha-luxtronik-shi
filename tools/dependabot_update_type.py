"""Classify a dependabot PR title as "patch", "minor" or "major" (conservative).

Reads the title from argv[1]. Prints one word. Anything that cannot be parsed
(grouped updates, odd versions) is "major", so a human looks at it. A 0.x
minor bump counts as "major" because 0.x minors may break.
"""
import re
import sys

_TITLE = re.compile(r"\bfrom\s+v?(\S+)\s+to\s+v?(\S+?)\s*$")
_VERSION = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def classify(title: str) -> str:
    m = _TITLE.search(title.strip())
    if not m:
        return "major"
    old, new = (_VERSION.match(v) for v in m.groups())
    if not old or not new:
        return "major"
    o = [int(x or 0) for x in old.groups()]
    n = [int(x or 0) for x in new.groups()]
    if o[0] != n[0] or (n[0] == 0 and o[1] != n[1]) or n < o:
        return "major"
    if o[1] != n[1]:
        return "minor"
    if o[2] != n[2]:
        return "patch"
    return "major"  # same numbers, e.g. a pre-release or tag change: do not guess


if __name__ == "__main__":
    print(classify(sys.argv[1] if len(sys.argv) > 1 else ""))
