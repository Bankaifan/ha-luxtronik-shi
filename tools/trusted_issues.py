"""List the open issues the orchestrator may act on, as one line of JSON.

Trusted: authored by OWNER, or labelled `approved` / `auto-ok` where the latest label event
on the issue timeline was made by OWNER. Everything else is never shown to the agent.
Output is sorted by prio (1, 2, 3, unlabelled), then oldest first; `prio` is 4 for unlabelled.
Also trusted: an issue created by the orchestrator (author AUTHOR_BOT) from a merged design study. Its body
has a line `Design: docs/design/NNNN-slug.md` naming a file that exists on the checked-out `main`, and it
is not an `idea`. Authorship cannot be forged; a stranger's "Design:" line counts for nothing.
Also trusted: a template sync issue (author AUTHOR_BOT, title starting `Template sync `, body line
`Template-Sync: <40 hex>`; design 0001, section 4.4).
Also trusted: an issue a guard script wrote (liveness `Overdue scheduled run`): author AUTHOR_BOT, not an `idea`,
and a valid HMAC signature over title and body (tools/guard_mark.py, repo secret GUARD_KEY). No key, no trust.
Needs the gh CLI (GH_TOKEN, GH_REPO). Environment: OWNER (default Bankaifan), AUTHOR_BOT (login of the author app).
"""
import json
import os
import re
import subprocess
import sys

import guard_mark
from agent_guard import same_login  # logins compare as `x`, `app/x` and `x[bot]` alike

GATED = ("approved", "auto-ok")
PRIOS = ("prio:1", "prio:2", "prio:3")  # counted only when Daniel or the author app set the label
NO_PRIO = 4  # unlabelled (or a stranger's prio label) sorts after prio:3
_DESIGN = re.compile(r"^Design: (docs/design/\d{4}-[a-z0-9-]+\.md)\s*$", re.MULTILINE)


def design_ref(issue, author_bot, exists):
    """Path of the merged design an orchestrator-created issue refers to, else None."""
    if not same_login((issue.get("author") or {}).get("login"), author_bot):
        return None
    if any(lab["name"] == "idea" for lab in issue.get("labels", [])):
        return None
    m = _DESIGN.search(issue.get("body") or "")
    return m.group(1) if m and exists(m.group(1)) else None


_SYNC = re.compile(r"^Template-Sync: [0-9a-f]{40}\s*$", re.MULTILINE)
SYNC_PREFIX = "Template sync "


def is_sync_issue(issue, author_bot):
    """True for a template sync issue created by the author app."""
    if not same_login((issue.get("author") or {}).get("login"), author_bot):
        return False
    return (issue.get("title") or "").startswith(SYNC_PREFIX) and bool(_SYNC.search(issue.get("body") or ""))


GUARD_TITLES = ("Overdue scheduled run: ", "Denied command in ", "Failing workflow: ",
                "Unstarted run: ", "Canary: ")


def is_guard_issue(issue, author_bot, key):
    """True for an issue a guard script signed with GUARD_KEY, authored by the author app, not an idea,
    with a known guard title prefix (a leaked key alone does not make any title trusted)."""
    if not key or not same_login((issue.get("author") or {}).get("login"), author_bot):
        return False
    if not (issue.get("title") or "").startswith(GUARD_TITLES):
        return False
    if any(lab["name"] == "idea" for lab in issue.get("labels", [])):
        return False
    return guard_mark.verify(issue.get("title"), issue.get("body"), key)


def label_set_by(events, label, actor):
    """True if the latest label/unlabel event for `label` is a `labeled` made by `actor`."""
    last = None
    for e in events:
        if e.get("event") in ("labeled", "unlabeled") and (e.get("label") or {}).get("name") == label:
            last = e
    return bool(last) and last["event"] == "labeled" and same_login((last.get("actor") or {}).get("login"), actor)


def prio_of(labels, events, owner, author_bot):
    """1..3 from the best prio label set by the owner or the author app, else NO_PRIO."""
    best = NO_PRIO
    for n, name in enumerate(PRIOS, 1):
        if name in labels and (label_set_by(events, name, owner)
                               or (author_bot and label_set_by(events, name, author_bot))):
            best = min(best, n)
    return best


def classify(issue, events, owner, author_bot="", exists=os.path.isfile, guard_key=""):
    """Return a dict for a trusted issue, or None. `events` is only needed for gated labels."""
    labels = {lab["name"] for lab in issue.get("labels", [])}
    by_owner = {g for g in GATED if g in labels and label_set_by(events, g, owner)}
    authored = same_login((issue.get("author") or {}).get("login"), owner)
    design = design_ref(issue, author_bot, exists)
    sync = is_sync_issue(issue, author_bot)
    guard = is_guard_issue(issue, author_bot, guard_key)
    if not authored and not by_owner and not design and not sync and not guard:
        return None
    return {
        "number": issue["number"],
        "title": issue["title"],
        "authored_by_owner": authored,
        "approved": "approved" in by_owner,
        "auto_ok": "auto-ok" in by_owner,
        "design": design,
        "template_sync": sync,
        "guard": guard,
        "prio": prio_of(labels, events, owner, author_bot),
        "labels": sorted((labels - set(GATED)) | by_owner),
    }


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def timeline(number, repo):
    # --paginate prints one JSON array per page; --slurp joins them.
    pages = json.loads(gh("api", "--paginate", "--slurp", f"repos/{repo}/issues/{number}/timeline"))
    return [e for page in pages for e in page]


def main() -> int:
    owner = os.environ.get("OWNER", "Bankaifan")
    author_bot = os.environ.get("AUTHOR_BOT", "")
    repo = os.environ["GH_REPO"]
    guard_key = guard_mark.key_from_env()
    issues = json.loads(gh("issue", "list", "--state", "open", "--limit", "200",
                           "--json", "number,title,author,labels,body"))
    result = []
    for issue in issues:
        names = {lab["name"] for lab in issue["labels"]}
        events = timeline(issue["number"], repo) if names & (set(GATED) | set(PRIOS)) else []
        item = classify(issue, events, owner, author_bot, guard_key=guard_key)
        if item:
            result.append(item)
    result.sort(key=lambda i: (i["prio"], i["number"]))  # prio first, then oldest (lowest number)
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
