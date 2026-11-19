"""Names in issue, PR and commit titles (docs/decisions/0017-hpo-flow.md): one NAME per piece of work.

NAME = upper-case words joined by `-`, at most 3 words, digits allowed (`NAMES`, `SYNC-APPLY`, `WATCH-HEAL`).
Issue and PR title: `V<major>-<NAME>: <summary>` (`V1-SYNC-APPLY: ...`). Commit subject: `V<VERSION>-<NAME>: <change>`
(`V1.101-SYNC-APPLY: ...`, VERSION = the file on main). Titles from before the `V<major>-` prefix (`NAMES: ...`) still
count as an ID. Titles without one (guard titles, `Template sync <sha>`, dependabot, `Release <version>`) match nothing.
"""
import re

_NAME = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){0,2}"
TASK_ID = re.compile(rf"^((?:V\d+-)?{_NAME}): ")
_VERSIONED = re.compile(rf"^V\d+-({_NAME})$")


def task_id_of(title):
    """The ID a title starts with (`V1-NAMES: short summary` -> `V1-NAMES`), else None."""
    m = TASK_ID.match(title or "")
    return m.group(1) if m else None


def commit_errors(title, subjects):
    """A PR titled `V<major>-<NAME>: ...` has only commits `V<version>-<NAME>: ...`; other PRs are not checked."""
    m = _VERSIONED.match(task_id_of(title) or "")
    if not m:
        return []
    form = re.compile(rf"^V\d+(?:\.\d+)+-{re.escape(m.group(1))}: \S")
    return [f"commit subject must be `V<version>-{m.group(1)}: <change>`: {s}" for s in subjects if not form.match(s)]
