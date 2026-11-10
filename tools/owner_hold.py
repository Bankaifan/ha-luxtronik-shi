"""Respect the owner's label removals: if OWNER unlabelled `needs-human` or `review:N`, no agent sets it again.

The label timeline (`issues/N/events`) decides, no extra state: the latest `labeled`/`unlabeled` event for a label
is an `unlabeled` by OWNER -> the label is held. For a PR the hold ends with a new head (a commit newer than the
removal); on any item it ends when the label is set again or OWNER sets another label (a new decision).
A bot's removal never holds. A failed lookup fails open (no hold): the guard must not block the pipeline.
Needs the gh CLI (GH_TOKEN) and GH_REPO.
"""
import json
import os
import re
import subprocess

GUARDED = re.compile(r"^(needs-human|review:\d)$")
REVIEW_LABELS = ("review:1", "review:2", "review:3")


def _login(s):
    return (s or "").strip().removeprefix("app/").removesuffix("[bot]").lower()


def guarded(label):
    return bool(GUARDED.match(label))


def owner_removed(events, label, owner, head_date=None):
    """True if OWNER's `unlabeled` is the latest event for LABEL, not older than HEAD_DATE (UTC ISO, a PR's newest
    commit) and not followed by another label event of OWNER."""
    evs = sorted((e for e in events if e.get("event") in ("labeled", "unlabeled")),
                 key=lambda e: e.get("created_at") or "")
    own = _login(owner)
    mine = [e for e in evs if (e.get("label") or {}).get("name") == label]
    if not mine or mine[-1]["event"] != "unlabeled" or _login((mine[-1].get("actor") or {}).get("login")) != own:
        return False
    at = mine[-1].get("created_at") or ""
    if head_date and head_date >= at:
        return False  # a new head ends the hold
    return not any(e["event"] == "labeled" and _login((e.get("actor") or {}).get("login")) == own
                   and (e.get("created_at") or "") > at for e in evs)


def held_labels(events, labels, owner, head_date=None):
    return [name for name in labels if guarded(name) and owner_removed(events, name, owner, head_date)]


def fetch_events(number, run):
    pages = json.loads(run("api", "--paginate", "--slurp", f"repos/{os.environ['GH_REPO']}/issues/{number}/events"))
    return [e for page in pages for e in page]


def head_date(number, run):
    commits = json.loads(run("pr", "view", str(number), "--json", "commits"))["commits"]
    return commits[-1]["committedDate"] if commits else None


def held(kind, number, labels, run, owner=None):
    """The labels of LABELS that OWNER removed and that stay removed. Fails open."""
    wanted = [name for name in labels if guarded(name)]
    if not wanted or not os.environ.get("GH_REPO"):
        return []
    try:
        events = fetch_events(number, run)
        head = head_date(number, run) if kind == "pr" else None
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError, TypeError):
        return []
    return held_labels(events, wanted, owner or os.environ.get("OWNER", "Bankaifan"), head)


def pr_held(number, run, owner=None):
    """True if OWNER removed needs-human or a review:N label from this PR for its current head."""
    return bool(held("pr", number, ("needs-human", *REVIEW_LABELS), run, owner))
