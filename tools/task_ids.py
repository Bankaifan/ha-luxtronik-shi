"""Names in issue, PR and commit titles (docs/decisions/0017-hpo-flow.md): one NAME per piece of work.

NAME = upper-case words joined by `-`, at most 3 words, digits allowed (`NAMES`, `SYNC-APPLY`, `WATCH-HEAL`).
Issue and PR title: `V<major>-<NAME>: <summary>` (`V1-SYNC-APPLY: ...`). Commit subject: `V<VERSION>-<NAME>: <change>`
(`V1.101-SYNC-APPLY: ...`, VERSION = the file on main). Titles from before the `V<major>-` prefix (`NAMES: ...`) still
count as an ID. Titles without one (guard titles, `Template sync <sha>`, dependabot, `Release <version>`) match nothing.
A merge of main into the branch (`Merge branch 'main' into agent/...`, GitHub's "Update branch" button or `git merge`)
is not a subject error: the train drops it at the next rebase (tools/branch_repair.py).
"""
import re

_NAME = r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){0,2}"
TASK_ID = re.compile(rf"^((?:V\d+-)?{_NAME}): ")
_VERSIONED = re.compile(rf"^V\d+-({_NAME})$")
MERGE_OF_MAIN = re.compile(r"^Merge (?:remote-tracking )?branch '(?:origin/)?main'(?: of \S+)? into \S+$")


def task_id_of(title):
    """The ID a title starts with (`V1-NAMES: short summary` -> `V1-NAMES`), else None."""
    m = TASK_ID.match(title or "")
    return m.group(1) if m else None


def name_of(title):
    """The NAME of a `V<major>-<NAME>: ...` title (`V1-SYNC-APPLY: x` -> `SYNC-APPLY`), else None."""
    m = _VERSIONED.match(task_id_of(title) or "")
    return m.group(1) if m else None


def commit_errors(title, subjects):
    """A PR titled `V<major>-<NAME>: ...` has only commits `V<version>-<NAME>: ...` of any version (a release
    in between changes nothing) and merges of main; other PRs are not checked."""
    name = name_of(title)
    if not name:
        return []
    form = re.compile(rf"^V\d+(?:\.\d+)+-{re.escape(name)}: \S")
    bad = [f"commit subject must be `V<version>-{name}: <change>`: {s}" for s in subjects
           if not form.match(s) and not MERGE_OF_MAIN.match(s)]
    fix = f"repair all subjects with `python3 tools/commit_names.py {name}` and `git push --force-with-lease`"
    return [*bad, fix] if bad else []
