"""Slip detection for the dispatcher (design 0015, step 1): does an issue already carry a task slip, and which model?

A slip is a `Files:` line (`overlap.parse_files`) in the body of an issue written by a trusted author (the owner or
the author app) or in a comment by one of them. A body by a stranger never counts, whatever labels the issue
has: such an issue has no slip (intake turns an accepted one into a slip issue of the author app). Text is untrusted: only paths and the model word
are parsed, nothing is opened or run.
"""
import re

import overlap

_MODEL = re.compile(r"^[\s>*_-]*Model\**\s*:\**\s*(sonnet|haiku)\b", re.IGNORECASE | re.MULTILINE)


def slip_texts(issue, authors):
    """Texts of ISSUE (a `gh issue view --json body,author,comments` dict) that may hold a slip, trusted authors only."""
    texts = [issue.get("body") or ""] if overlap.trusted(issue, authors) else []
    return texts + [c.get("body") or "" for c in issue.get("comments", []) if overlap.trusted(c, authors)]


def slip_files(issue, authors):
    """Paths of the slip of ISSUE, [] when it has none."""
    paths = []
    for t in slip_texts(issue, authors):
        paths += [p for p in overlap.parse_files(t) if p not in paths]
    return paths


def has_slip(issue, authors=overlap.DEFAULT_TRUSTED):
    return bool(slip_files(issue, authors))


SONNET_PATHS = (".github/workflows/", "tools/ci/", "tools/trusted_issues.py", "tools/agent_guard.py",
                "tools/dispatch.py", "tools/slip.py", ".github/CODEOWNERS", "CODEOWNERS", "docs/design/")
FAILED_ROUND_LABELS = ("restart:1", "stalled:1")  # a previous round failed: escalate instead of a second identical try
MANY_FILES = 3  # a slip over this many files is not routine work: haiku runs on such slips ended silently and were restarted


def needs_sonnet(paths):
    """True when one of PATHS is core: workflows, CI tools, trust or guard tools, CODEOWNERS, design docs."""
    return any(p.removeprefix("./").startswith(SONNET_PATHS) for p in paths)


def model_of(issue, authors=overlap.DEFAULT_TRUSTED):
    """`sonnet` or `haiku`, decided by the table: sonnet when the slip files are core (`SONNET_PATHS`), the slip names
    MANY_FILES files or more, or a previous round failed (`FAILED_ROUND_LABELS`), else `haiku`. A `Model:` line or `model:` label is only a hint and is
    ignored. `opus` is never set by script (it needs the owner's OK)."""
    labels = {lab["name"] for lab in issue.get("labels", [])}
    files = slip_files(issue, authors)
    if labels & set(FAILED_ROUND_LABELS) or needs_sonnet(files) or len(files) >= MANY_FILES:
        return "sonnet"
    return "haiku"
