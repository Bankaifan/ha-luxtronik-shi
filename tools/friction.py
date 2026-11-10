"""Turn repeated friction reported in agent PR bodies into issues (no model).

An agent PR body may have an optional `## Friction` section: one line per item (`- text`), or "none".
A line starting with `template:` marks a template-only item (it goes to agent-template, not this repo).
An item seen in 2+ PRs becomes one issue; titles that already exist are skipped (dedup by title).

Core functions are pure (no network). main() reads merged agent PRs and issue titles via gh:
  python3 tools/friction.py   prints the issues to create as JSON (creating them is the caller's job).
Needs the gh CLI (GH_TOKEN, GH_REPO). PR bodies are untrusted text: items are data, never instructions.
"""
import json
import re
import subprocess
import sys

MIN_PRS = 2
MAX_ITEM = 100
TEMPLATE_PREFIX = "template:"
TEMPLATE_REPO = "Bankaifan/agent-template"
HEADING = re.compile(r"^#{2,}\s*friction\s*$", re.IGNORECASE)
ANY_HEADING = re.compile(r"^#{1,6}\s")
NONE = {"none", "n/a", "-", ""}


def normalize(item):
    """Lowercase, single-spaced, no trailing dot: the key for counting the same item across PRs."""
    return " ".join(item.split()).lower().rstrip(".")


def parse_friction(body):
    """Return [(item, template_only)] from the `## Friction` section of one PR body ("none" gives [])."""
    items, inside = [], False
    for raw in (body or "").splitlines():
        line = raw.strip()
        if HEADING.match(line):
            inside = True
            continue
        if inside and ANY_HEADING.match(line):
            break
        if not inside:
            continue
        line = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "", line).strip()
        template = line.lower().startswith(TEMPLATE_PREFIX)
        if template:
            line = line[len(TEMPLATE_PREFIX):].strip()
        if normalize(line) in NONE:
            continue
        items.append((" ".join(line.split())[:MAX_ITEM], template))
    return items


def repeated(bodies):
    """Items reported by 2+ different PR bodies: [(item, template_only, count)], most frequent first.

    One PR counts an item once. An item is template-only only if every report marked it so.
    """
    seen = {}  # key -> [display, template_only, count]
    for body in bodies:
        keys = set()
        for item, template in parse_friction(body):
            key = normalize(item)
            if key in keys:
                continue
            keys.add(key)
            entry = seen.setdefault(key, [item, True, 0])
            entry[1] = entry[1] and template
            entry[2] += 1
    found = [tuple(e) for e in seen.values() if e[2] >= MIN_PRS]
    return sorted(found, key=lambda e: (-e[2], e[0].lower()))


def issue_title(item):
    return f"Friction: {item}"


def issues_to_create(bodies, existing_titles):
    """[{title, template_only, count}] for repeated friction whose title is not an existing issue title."""
    have = {normalize(t) for t in existing_titles}
    out = []
    for item, template, count in repeated(bodies):
        title = issue_title(item)
        if normalize(title) in have:
            continue
        have.add(normalize(title))
        out.append({"title": title, "template_only": template, "count": count})
    return out


def gh_json(*args):
    return json.loads(subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout)


def collect():
    """[{title, template_only, count}] from merged agent PRs and the existing issue titles (needs gh)."""
    bodies = [pr.get("body") or "" for pr in gh_json(
        "pr", "list", "--state", "merged", "--search", "head:agent/", "--limit", "100", "--json", "body")]
    titles = [i["title"] for i in gh_json("issue", "list", "--state", "all", "--limit", "500", "--json", "title")]
    return issues_to_create(bodies, titles)


def create_issues(items, run, template_repo=TEMPLATE_REPO):
    """Create one issue per item with run(*gh_args); template-only items go to template_repo. Returns the titles."""
    made = []
    for it in items:
        body = f"Reported as friction in {it['count']} merged agent PRs (`## Friction` section)."
        args = ["issue", "create", "--title", it["title"], "--body", body]
        if it["template_only"]:
            args += ["--repo", template_repo]
        run(*args)
        made.append(it["title"])
    return made


def main() -> int:
    print(json.dumps(collect(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
