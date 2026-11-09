"""Workflow action refs must not point at a branch: a branch can change without review and Dependabot cannot bump it.

Issue #77: the Validate workflow pinned ``home-assistant/actions/hassfest@master`` and ``hacs/action@main``. Both must
now be commit SHAs (Dependabot's github-actions ecosystem proposes SHA bumps with the tag in a trailing comment).
"""

from __future__ import annotations

import pathlib
import re

WORKFLOWS = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows"
USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)", re.MULTILINE)
SHA = re.compile(r"^[0-9a-f]{40}$")
BRANCH_NAMES = {"master", "main", "HEAD"}
# Third-party actions in Validate that are pinned to a commit SHA (issue #77 acceptance).
MUST_BE_SHA = ("home-assistant/actions/", "hacs/action@")


def _uses() -> list[tuple[str, str]]:
    found = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for match in USES.finditer(path.read_text(encoding="utf-8")):
            found.append((path.name, match.group(1)))
    return found


def test_no_action_ref_points_at_a_branch():
    offenders = []
    for name, ref in _uses():
        if "@" not in ref or ref.startswith("./"):
            continue
        version = ref.rsplit("@", 1)[1]
        if version in BRANCH_NAMES:
            offenders.append(f"{name}: {ref}")
    assert not offenders, "action refs pinned to a branch: " + ", ".join(offenders)


def test_hassfest_and_hacs_are_pinned_to_a_sha():
    refs = [ref for _, ref in _uses() if ref.startswith(MUST_BE_SHA)]
    assert len(refs) == 2, f"expected hassfest and hacs refs in .github/workflows, found {refs}"
    for ref in refs:
        version = ref.rsplit("@", 1)[1]
        assert SHA.match(version), f"{ref} is not pinned to a 40-character commit SHA"
