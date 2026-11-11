"""Closes design parents whose split issues are all done (issue #335). Model-free, called by the status run.

A merged design study names its source issue (the parent) in the header line `Issue: #N` of docs/design/NNNN-slug.md.
The orchestrator opens the split issues, each with a line `Design: docs/design/NNNN-slug.md`, authored by Daniel or
the author app. A parent is closed when it has split issues and every one is closed as completed by a merged PR:
the parent's prio:* and agent:dev labels are removed, one comment lists the split issues, then the parent is closed
as completed. One open split issue, or one closed as not planned, keeps the parent open. If the issue or merged PR
list is truncated, nothing is closed. Needs the gh CLI (GH_TOKEN, GH_REPO).

A split issue written by hand (issue #400: #389 "Build Design 0011: ...") has no `Design:` line; it links to the design
by its title `Design NNNN` (NNNN = the number of the design file). Without that link the parent never closed.
"""
import json
import pathlib
import re
import subprocess

import liveness
from agent_guard import same_login

DESIGN_DIR = pathlib.Path(__file__).resolve().parent.parent / "docs" / "design"
ISSUE_LIMIT = 500
MERGED_PR_LIMIT = 500
ISSUE_FIELDS = "number,title,body,state,stateReason,author,labels,closedByPullRequestsReferences"
_HEADER = re.compile(r"^Issue: #(\d+)\b")
_SPLIT = re.compile(r"^Design: (docs/design/\d{4}-[a-z0-9-]+\.md)\s*$", re.MULTILINE)
_TITLE = re.compile(r"\bDesign (\d{4})\b")


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def jlist(run, *args):
    return json.loads(run(*args))


def parent_designs(design_dir=DESIGN_DIR):
    """{parent issue number: [docs/design/NNNN-slug.md, ...]} from the `Issue: #N` header line of each design doc."""
    out = {}
    for f in sorted(design_dir.glob("[0-9][0-9][0-9][0-9]-*.md")):
        for line in f.read_text(encoding="utf-8").splitlines()[:5]:
            m = _HEADER.match(line)
            if m:
                out.setdefault(int(m.group(1)), []).append(f"docs/design/{f.name}")
                break
    return out


def split_issues(issues, parent, paths, owner, author_bot):
    """Issues by Daniel or the author app (never the parent itself) that name one of `paths`: a `Design:` line in the
    body, or a title `Design NNNN` with the number of one of the designs."""
    numbers = {p.rsplit("/", 1)[-1][:4] for p in paths}
    out = []
    for i in issues:
        login = (i.get("author") or {}).get("login")
        if i["number"] == parent or not (same_login(login, owner) or same_login(login, author_bot)):
            continue
        title = _TITLE.search(i.get("title") or "")
        if set(_SPLIT.findall(i.get("body") or "")) & set(paths) or (title and title.group(1) in numbers):
            out.append(i)
    return out


def is_done(issue, merged):
    """Closed as completed, and at least one PR that closed it is merged."""
    if issue.get("state") != "CLOSED" or issue.get("stateReason") != "COMPLETED":
        return False
    return any(r.get("number") in merged for r in issue.get("closedByPullRequestsReferences") or [])


def merged_numbers(run):
    """Numbers of the merged PRs. A truncated list gives an empty set, so nothing is closed."""
    prs = jlist(run, "pr", "list", "--state", "merged", "--limit", str(MERGED_PR_LIMIT), "--json", "number")
    return set() if len(prs) >= MERGED_PR_LIMIT else {p["number"] for p in prs}


def close_parent(parent, children, run):
    number = parent["number"]
    labels = {lab["name"] for lab in parent.get("labels", [])}
    drop = sorted(n for n in labels if n.startswith("prio:")) + (["agent:dev"] if "agent:dev" in labels else [])
    if drop:
        run("issue", "edit", str(number), *[a for n in drop for a in ("--remove-label", n)])
    listed = ", ".join(f"#{c['number']}" for c in children)
    liveness.post_comment("issue", number, f"Status run: all {len(children)} split issues are closed as completed "
                          f"with a merged PR ({listed}). Closing this design parent.", run)
    run("issue", "close", str(number), "--reason", "completed")


def close_done_parents(run=gh, owner="Bankaifan", author_bot="", design_dir=DESIGN_DIR):
    """Closes every open design parent whose split issues are all done. Returns one action line per parent."""
    designs = parent_designs(design_dir)
    if not designs:
        return []
    issues = jlist(run, "issue", "list", "--state", "all", "--limit", str(ISSUE_LIMIT), "--json", ISSUE_FIELDS)
    if len(issues) >= ISSUE_LIMIT:
        return [f"design parents not checked: the issue list reached {ISSUE_LIMIT}"]
    by_number = {i["number"]: i for i in issues}
    merged = None
    actions = []
    for parent, paths in sorted(designs.items()):
        p = by_number.get(parent)
        if not p or p.get("state") != "OPEN":
            continue
        children = split_issues(issues, parent, paths, owner, author_bot)
        if not children or not all(c.get("state") == "CLOSED" and c.get("stateReason") == "COMPLETED"
                                   for c in children):
            continue
        if merged is None:
            merged = merged_numbers(run)
        if not all(is_done(c, merged) for c in children):
            continue
        try:
            close_parent(p, children, run)
            actions.append(f"closed design parent #{parent}: {len(children)} split issues done")
        except (subprocess.CalledProcessError, liveness.ReadbackError, OSError) as e:
            actions.append(f"design parent #{parent} not closed: {type(e).__name__}")
    return actions
