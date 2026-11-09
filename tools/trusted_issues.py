"""List the open issues the orchestrator may act on, as one line of JSON.

Trusted: authored by OWNER, or labelled `approved` / `auto-ok` where the latest label event
on the issue timeline was made by OWNER. Everything else is never shown to the agent.
Needs the gh CLI (GH_TOKEN, GH_REPO). Environment: OWNER (default Bankaifan).
"""
import json
import os
import subprocess
import sys

GATED = ("approved", "auto-ok")


def label_set_by(events, label, actor):
    """True if the latest label/unlabel event for `label` is a `labeled` made by `actor`."""
    last = None
    for e in events:
        if e.get("event") in ("labeled", "unlabeled") and (e.get("label") or {}).get("name") == label:
            last = e
    return bool(last) and last["event"] == "labeled" and (last.get("actor") or {}).get("login") == actor


def classify(issue, events, owner):
    """Return a dict for a trusted issue, or None. `events` is only needed for gated labels."""
    labels = {lab["name"] for lab in issue.get("labels", [])}
    by_owner = {g for g in GATED if g in labels and label_set_by(events, g, owner)}
    authored = (issue.get("author") or {}).get("login") == owner
    if not authored and not by_owner:
        return None
    return {
        "number": issue["number"],
        "title": issue["title"],
        "authored_by_owner": authored,
        "approved": "approved" in by_owner,
        "auto_ok": "auto-ok" in by_owner,
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
    repo = os.environ["GH_REPO"]
    issues = json.loads(gh("issue", "list", "--state", "open", "--limit", "200",
                           "--json", "number,title,author,labels"))
    result = []
    for issue in issues:
        names = {lab["name"] for lab in issue["labels"]}
        events = timeline(issue["number"], repo) if names & set(GATED) else []
        item = classify(issue, events, owner)
        if item:
            result.append(item)
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
