"""Task IDs in issue and PR titles (issue #501): `<ID>: <summary>`.

ID = upper-case words joined by `-`, at most 3 words, digits allowed (`NAMES`, `SYNC-APPLY`, `WATCH-HEAL`, `SYNC-1`).
Titles without an ID (guard titles, `Template sync <sha>`, dependabot, `Design NNNN`) match nothing and stay as they are.
"""
import re

TASK_ID = re.compile(r"^([A-Z][A-Z0-9]*(?:-[A-Z0-9]+){0,2}): ")


def task_id_of(title):
    """The ID a title starts with (`NAMES: short summary` -> `NAMES`), else None."""
    m = TASK_ID.match(title or "")
    return m.group(1) if m else None
