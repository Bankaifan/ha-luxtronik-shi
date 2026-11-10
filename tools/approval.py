"""Effective approval at the head SHA: one rule for status.py, agent-fix and automerge.

A PR is approved only if GitHub's review decision is APPROVED and, for a risk:security PR, the security reviewer's
verdict for exactly this head is not `changes`. The code reviewer's approval must not mask a security `changes`
(both reviews come from the same approver app, so the later review replaces the earlier one in reviewDecision).

  approval.py check PR        env: GH_TOKEN, GH_REPO, APPROVER_BOT
      prints `approved` or `not-approved` (exit 0); for a missing/unreadable input it prints `not-approved`.
  approval.py security-changes PR
      prints `yes` when the security reviewer asked for changes at the current head, `no` otherwise,
      `unknown` when the PR could not be read.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_guard import same_login

VERDICT = re.compile(r"^security-review:\s*(approve|changes)\s+([0-9a-f]{7,40})\b", re.IGNORECASE | re.MULTILINE)


def security_verdict(comments, sha, approver):
    """`approve` / `changes` from the newest security-review comment of the approver app naming SHA, else None."""
    found = None
    for c in comments or []:
        if not approver or not same_login((c.get("user") or c.get("author") or {}).get("login"), approver):
            continue
        for kind, s in VERDICT.findall(c.get("body") or ""):
            if sha and sha.lower().startswith(s.lower()):
                found = kind.lower()
    return found


def security_changes(labels, comments, sha, approver):
    """True when a risk:security PR carries a security `changes` verdict for this head."""
    return "risk:security" in labels and security_verdict(comments, sha, approver) == "changes"


def effective_approval(decision, labels, comments, sha, approver):
    """Code review approved AND (risk:security only) no security `changes` verdict for the head SHA.
    A security PR without any verdict yet is left to the `security-review` status gate (it stays pending)."""
    if decision != "APPROVED":
        return False
    return not security_changes(labels, comments, sha, approver)


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def load(number, run=gh):
    """(reviewDecision, label names, headRefOid, issue comments) of a PR."""
    repo = os.environ["GH_REPO"]
    view = json.loads(run("pr", "view", str(number), "--json", "reviewDecision,labels,headRefOid"))
    pages = json.loads(run("api", "--paginate", "--slurp", f"repos/{repo}/issues/{number}/comments") or "[]")
    comments = [c for page in pages for c in (page if isinstance(page, list) else [page])]
    return (view.get("reviewDecision"), {x["name"] for x in view.get("labels", [])}, view.get("headRefOid", ""),
            comments)


def main(argv, run=gh):
    if len(argv) != 3 or argv[1] not in ("check", "security-changes") or not argv[2].isdigit():
        print(__doc__)
        return 2
    approver = os.environ.get("APPROVER_BOT", "")
    try:
        decision, labels, sha, comments = load(argv[2], run)
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError):
        print("not-approved" if argv[1] == "check" else "unknown")  # never approve on a failed read
        return 0
    if argv[1] == "check":
        print("approved" if effective_approval(decision, labels, comments, sha, approver) else "not-approved")
    else:
        print("yes" if security_changes(labels, comments, sha, approver) else "no")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
