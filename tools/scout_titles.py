"""Collect the titles the scout must not propose again (no model).

Lists, one line each: open issues, issues closed in the last 90 days plus all closed `idea` issues,
open PRs, and the heading of each design study in docs/design/*.md. Titles only, no bodies.
Writes a multiline `titles` output to $GITHUB_OUTPUT (or prints to stdout without it).

Usage: python3 tools/scout_titles.py
Needs the gh CLI (GH_TOKEN, GH_REPO). Titles are untrusted text: the scout treats them as data.
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
import uuid

CLOSED_DAYS = 90
MAX_TITLE = 150
ROOT = pathlib.Path(__file__).resolve().parent.parent


def gh_json(*args):
    return json.loads(subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout)


def clean(title):
    return " ".join(str(title).split())[:MAX_TITLE]


def design_titles(root=ROOT):
    """First `# ` heading of each design study (README.md is an index, not a study)."""
    out = []
    for path in sorted((pathlib.Path(root) / "docs" / "design").glob("*.md")):
        if path.name == "README.md":
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                out.append(clean(line[2:]))
                break
    return out


def collect(today, root=ROOT):
    """Return the list of lines for the scout prompt."""
    cutoff = (today - datetime.timedelta(days=CLOSED_DAYS)).isoformat()
    lines = []
    seen = set()

    def add(items, kind):
        for item in items:
            if item["number"] in seen:
                continue
            seen.add(item["number"])
            lines.append(f"- #{item['number']} {clean(item['title'])} ({kind})")

    add(gh_json("issue", "list", "--state", "open", "--limit", "300", "--json", "number,title"), "open issue")
    add(gh_json("issue", "list", "--state", "closed", "--search", f"closed:>={cutoff}", "--limit", "300",
                "--json", "number,title"), "closed issue")
    add(gh_json("issue", "list", "--state", "closed", "--label", "idea", "--limit", "300",
                "--json", "number,title"), "closed idea")
    add(gh_json("pr", "list", "--state", "open", "--limit", "100", "--json", "number,title"), "open PR")
    lines += [f"- {title} (design study)" for title in design_titles(root)]
    return lines


def main() -> int:
    lines = collect(datetime.date.today())
    text = "\n".join(lines) if lines else "(none)"
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        delim = f"EOF-{uuid.uuid4().hex}"
        with open(out, "a") as f:
            f.write(f"titles<<{delim}\n{text}\n{delim}\n")
        print(f"titles: {len(lines)} lines")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
