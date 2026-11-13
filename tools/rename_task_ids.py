"""One-off: give open task issues their task ID in the title (issue #501): `<ID>: <summary>`.

Usage: rename_task_ids.py MAP.json [--apply]
MAP.json maps issue numbers to IDs, e.g. {"501": "NAMES"}, and is written by the owner. Without --apply only the
plan is printed. Only the title changes (`gh issue edit --title`): body, labels, numbers and `Depends on:` lines stay.
Never renamed: guard titles (tools/trusted_issues.py GUARD_TITLES), `Template sync ` and `Design ` titles.
Needs the gh CLI (GH_TOKEN, GH_REPO).
"""
import json
import re
import subprocess
import sys

import task_ids
from trusted_issues import GUARD_TITLES

KEEP = (*GUARD_TITLES, "Template sync ", "Design ")  # titles other code parses: the map cannot rename them
ID_FORM = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+){0,2}$")


def renamed(title, task_id):
    """The title under the scheme, or None when it stays (kept prefix, already has this ID, no summary left)."""
    if title.startswith(KEEP) or task_ids.task_id_of(title) == task_id:
        return None
    summary = task_ids.TASK_ID.sub("", title, count=1).strip()  # drop another ID the title may carry
    return f"{task_id}: {summary}" if summary else None


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    apply = "--apply" in args
    paths = [a for a in args if a != "--apply"]
    if len(paths) != 1:
        print("usage: rename_task_ids.py MAP.json [--apply]", file=sys.stderr)
        return 2
    try:
        with open(paths[0], encoding="utf-8") as f:
            mapping = json.load(f)
    except (OSError, ValueError) as e:
        print(f"rename_task_ids: cannot read map: {e}", file=sys.stderr)
        return 2
    if not isinstance(mapping, dict) or not all(k.isdigit() and ID_FORM.match(str(v)) for k, v in mapping.items()):
        print('rename_task_ids: map must be {"<issue number>": "<ID>"} with IDs like NAMES or SYNC-1', file=sys.stderr)
        return 2
    try:
        for number, task_id in sorted(mapping.items(), key=lambda kv: int(kv[0])):
            title = json.loads(gh("issue", "view", number, "--json", "title"))["title"]
            new = renamed(title, task_id)
            if new is None:
                print(f"#{number}: unchanged: {title}")
                continue
            print(f"#{number}: {title} -> {new}")
            if apply:
                gh("issue", "edit", number, "--title", new)
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError, TypeError) as e:
        print(f"rename_task_ids: stopped: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
