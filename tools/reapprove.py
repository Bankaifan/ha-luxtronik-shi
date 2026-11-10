"""Cheap re-approval (docs/design/0003-merge-train.md, section 4.4): approve a rebased agent PR without the model
when its own patch is byte-for-byte the patch a model already approved.

CLI: reapprove.py PR SHA   (env GH_TOKEN of the approver app, GH_REPO, APPROVER_BOT, AUTHOR_BOT, OWNER)
Exit 0: approved SHA. Exit 1: refused or any error; the model review then runs as before. Nothing here fails open.
Runs from the default branch (agent-review.yml, workflow_run); PR data is read through `gh` and treated as data.

Approve only if ALL hold, else refuse:
1. The PR is open, same repo, `agent/*`, SHA is its head, one commit, fewer than 100 files (the file list is complete),
   no `needs-human` / `risk:security`, not a design PR, no changed path owned by the owner in CODEOWNERS, and the
   risk classifier (tools/ci/risk.py) rates the commit patch `none` (infra and security both refuse).
2. No reviewer's latest decisive review is CHANGES_REQUESTED. The newest approver review for another head OLD is an
   APPROVED one, or a DISMISSED one whose dismissal event says: previous state `approved`, no message (a manual
   dismissal always has one), actor = the author app (the pusher). Anything unreadable refuses.
   Its `body-hash:` line must equal the current PR body hash.
3. `git patch-id --verbatim` of the commit patch of OLD equals that of SHA. Refused on binary markers, mode changes,
   a patch over MAX_PATCH characters, or a `diff --git` count that differs from the PR's file count (truncation).
4. The head is re-read just before posting, and the review is submitted through the API with `commit_id=SHA`.
"""
import json
import os
import re
import subprocess
import sys

import agent_guard

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci"))
import risk

MAX_FILES = 100
MAX_PATCH = 300_000
SHA_RE = re.compile(r"[0-9a-f]{40}")
PATCH_ACCEPT = "Accept: application/vnd.github.patch"
MODE_LINE = re.compile(r"^(old|new) mode ", re.MULTILINE)


class Refuse(Exception):
    """A reason not to approve without the model."""


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def paged(run, path):
    return [x for page in json.loads(run("api", "--paginate", "--slurp", path)) for x in page]


def check_pr(pr, repo, sha):
    """Gate 1, part one: facts of the PR object (called again just before posting)."""
    labels = {lb.get("name") for lb in pr.get("labels") or []}
    head = pr.get("head") or {}
    if pr.get("state") != "open" or head.get("sha") != sha:
        raise Refuse("PR is not open at this head")
    if (head.get("repo") or {}).get("full_name") != repo or not str(head.get("ref", "")).startswith("agent/"):
        raise Refuse("not a same-repo agent/* branch")
    if pr.get("commits") != 1:
        raise Refuse("PR has not exactly one commit")
    if labels & {"needs-human", "risk:security"}:
        raise Refuse("PR is labelled needs-human or risk:security")


def check_files(files, pr, codeowners, owner):
    if len(files) >= MAX_FILES or len(files) != pr.get("changed_files"):
        raise Refuse("file list is capped or incomplete")
    paths = [p for f in files for p in (f.get("filename"), f.get("previous_filename")) if p]
    if paths and all(p.startswith("docs/design/") for p in paths):
        raise Refuse("design PR")
    if any(risk.owned_by(p, codeowners, owner) for p in paths):
        raise Refuse("a changed path is owned by the owner in CODEOWNERS")


def check_patch(patch, nfiles):
    if len(patch) > MAX_PATCH or "GIT binary patch" in patch or "Binary files" in patch:
        raise Refuse("patch is large or binary")
    if MODE_LINE.search(patch):
        raise Refuse("patch changes a file mode")
    if len(re.findall(r"^diff --git ", patch, re.MULTILINE)) != nfiles:
        raise Refuse("patch does not cover the PR's files")


def patch_id(patch):
    out = subprocess.run(["git", "patch-id", "--verbatim"], input=patch, capture_output=True, text=True,
                         check=True).stdout.split()
    if not out:
        raise Refuse("empty patch-id")
    return out[0]


def decisive_blockers(reviews):
    """Reviewers whose latest decisive review is CHANGES_REQUESTED."""
    latest = {}
    for r in reviews:
        if r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
            latest[agent_guard.norm_login((r.get("user") or {}).get("login"))] = r["state"]
    return [u for u, s in latest.items() if s == "CHANGES_REQUESTED"]


def dismissal_ok(review, timeline, author_bot):
    """A DISMISSED review counts only if the push-time dismissal is proven: prior state approved, no message, pusher actor."""
    for ev in timeline:
        d = ev.get("dismissed_review") or {}
        if ev.get("event") != "review_dismissed" or d.get("review_id") != review.get("id"):
            continue
        prior = d.get("previous_review_state", ev.get("previous_review_state"))
        manual = bool((d.get("dismissal_message") or "").strip())
        pusher = agent_guard.same_login((ev.get("actor") or {}).get("login"), author_bot)
        if str(prior).lower() == "approved" and not manual and pusher:
            return True
    return False


def previous_head(reviews, timeline, approver, author_bot, sha, bhash):
    """Head OLD of the newest approver review for another commit, if it was an approval that still holds."""
    mine = [r for r in reviews if agent_guard.same_login((r.get("user") or {}).get("login"), approver)
            and r.get("commit_id") not in (sha, None)]
    if not approver or not mine:
        raise Refuse("no earlier approver review")
    last = mine[-1]
    m = agent_guard._BODY_HASH_LINE.search(last.get("body") or "")
    if not m or m.group(1).lower() != bhash:
        raise Refuse("earlier review has another body-hash (body edited)")
    if last.get("state") == "APPROVED" or (last.get("state") == "DISMISSED" and dismissal_ok(last, timeline, author_bot)):
        return last["commit_id"]
    raise Refuse("earlier review was not a confirmed approval (previous_review_state unconfirmed or manual dismissal)")


def run_reapprove(pr_no, sha, env, run=gh, ident=patch_id):
    repo, owner = env["GH_REPO"], env.get("OWNER", risk.OWNER_DEFAULT)
    approver, author_bot = env.get("APPROVER_BOT", ""), env.get("AUTHOR_BOT", "")
    pr = json.loads(run("api", f"repos/{repo}/pulls/{pr_no}"))
    check_pr(pr, repo, sha)
    files = paged(run, f"repos/{repo}/pulls/{pr_no}/files")
    check_files(files, pr, risk.read_text(".github/CODEOWNERS"), owner)
    reviews = paged(run, f"repos/{repo}/pulls/{pr_no}/reviews")
    if decisive_blockers(reviews):
        raise Refuse("a reviewer has requested changes")
    bhash = agent_guard.body_hash(pr.get("body"))
    old = previous_head(reviews, paged(run, f"repos/{repo}/issues/{pr_no}/timeline"), approver, author_bot, sha, bhash)
    new_patch, old_patch = (run("api", f"repos/{repo}/commits/{c}", "-H", PATCH_ACCEPT) for c in (sha, old))
    for p in (new_patch, old_patch):
        check_patch(p, len(files))
    if risk.classify(new_patch, risk.read_text("AGENTS.md")) != "none":
        raise Refuse("risk class is not none")
    pid, old_pid = ident(new_patch), ident(old_patch)
    if pid != old_pid:
        raise Refuse("patch changed since the approved head")
    check_pr(json.loads(run("api", f"repos/{repo}/pulls/{pr_no}")), repo, sha)  # head did not move while we compared
    body = f"Re-approved without model: patch unchanged since {old} (patch-id {pid}).\n\nbody-hash: {bhash}"
    run("api", "-X", "POST", f"repos/{repo}/pulls/{pr_no}/reviews", "-f", f"commit_id={sha}", "-f", "event=APPROVE",
        "-f", f"body={body}")
    print(f"re-approved PR #{pr_no} at {sha[:12]} (patch unchanged since {old[:12]})")
    return 0


def main(argv):
    if len(argv) != 3 or not argv[1].isdigit() or not SHA_RE.fullmatch(argv[2]):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        return run_reapprove(argv[1], argv[2], os.environ)
    except Refuse as e:
        print(f"not re-approved: {e}")
    except Exception as e:  # noqa: BLE001 - fail closed: any error means the model reviews
        print(f"not re-approved: {type(e).__name__}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
