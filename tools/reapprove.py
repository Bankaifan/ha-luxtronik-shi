"""Cheap re-approval (docs/design/0003-merge-train.md, section 4.4): approve a rebased agent PR without the model
when its own patch is byte-for-byte the patch a model already approved.

CLI: reapprove.py PR SHA   (env GH_TOKEN of the approver app, GH_REPO, APPROVER_BOT, AUTHOR_BOT, OWNER)
Exit 0: approved SHA. Exit 1: refused or any error; the model review then runs as before. Nothing here fails open.
Runs from the default branch (agent-review.yml, workflow_run); PR data is read through `gh` and treated as data.

Approve only if ALL hold, else refuse:
1. The PR is open, same repo, `agent/*`, SHA is its head, fewer than 100 files (the file list is complete),
   not `parked`, not a design PR, no changed path owned by the owner in CODEOWNERS, and the risk classifier
   (tools/ci/risk.py) rates the PR diff `none` or `security` (infra refuses). A `security` patch or a
   `risk:security` label also needs a `security-review: approve <sha>` comment of the approver app for the new head.
2. No reviewer's latest decisive review is CHANGES_REQUESTED. The newest approver review for another head OLD is an
   APPROVED one, or a DISMISSED one whose dismissal event says: previous state `approved`, no message (a manual
   dismissal always has one), actor = the author app (the pusher). Anything unreadable refuses.
   Its `body-hash:` line must equal the current PR body hash.
3. `git patch-id --verbatim` of the diff of OLD against its merge base equals that of SHA. Refused on binary markers, mode changes,
   a patch over MAX_PATCH characters, or a `diff --git` count that differs from the PR's file count (truncation).
4. The head is re-read just before posting, and the review is submitted through the API with `commit_id=SHA`.
5. Every commit of the PR has exactly one parent and the commit list is complete (both modes): a merge commit can
   carry content the three-dot diff does not show.

Batch mode (docs/decisions/0018-batch-train.md, rule 3): a PR whose head branch is exactly `agent/batch` is never
compared with an earlier head. It is approved only if ALL hold, else refused (and no model reviews it):
a. Gate 1 without the security path: by the author app, risk class `none`, no reviewer requesting changes, and no
   file under docs/design/ (a design file becomes trusted step issues; it never lands through a batch).
b. Its body has exactly one line `Batch: #a@<sha7> #b@<sha7> ...` (2 to 8 members, each once).
c. Every member is open, same repo, `agent/<N>-...`, on the same base, not `parked`, without a `risk:*` label, its head
   starts with the recorded sha7, the approver app approved exactly that head and nobody requests changes. Its own
   gates hold at that head: check run `risk` and commit status `security-review` are success (unreadable refuses).
d. Per file (`diff --git` section): every section of every member diff is in the batch diff with the same patch-id
   and the same `index <old>..<new>` line (same blob before and after: a patch-id ignores where a hunk applies),
   and every section of the batch diff belongs to exactly one member. Nothing is added, changed or left out.
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
PATCH_ACCEPT = "Accept: application/vnd.github.diff"  # one diff per file, whatever the number of commits
MODE_LINE = re.compile(r"^(old|new) mode ", re.MULTILINE)
BATCH_BRANCH = risk.check_pr_form.BATCH_BRANCH
INDEX_LINE = re.compile(r"^index [0-9a-f]+\.\.[0-9a-f]+(?: \d+)?$", re.MULTILINE)
BATCH_LINE = re.compile(r"Batch:(?: #[1-9]\d*@[0-9a-f]{7}){2,8}")


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
    if "parked" in labels:
        raise Refuse("PR is parked")


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


def check_linear(run, repo, pr_no, pr):
    """Gate 5: the PR's commits are all there and none is a merge."""
    commits = paged(run, f"repos/{repo}/pulls/{pr_no}/commits")
    if not commits or len(commits) != pr.get("commits") or any(len(c.get("parents") or []) != 1 for c in commits):
        raise Refuse("commit list is incomplete or holds a merge commit")


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


def batch_members(body):
    """[(PR number, sha7)] of the one `Batch:` line of a batch PR body; a missing, second or malformed line refuses."""
    lines = [line for line in (body or "").splitlines() if line.startswith("Batch:")]
    if len(lines) != 1 or not BATCH_LINE.fullmatch(lines[0]):
        raise Refuse("no single well-formed Batch: line")
    members = [(int(n), s) for n, s in re.findall(r"#(\d+)@([0-9a-f]{7})", lines[0])]
    if len({n for n, _ in members}) != len(members):
        raise Refuse("a member is named twice")
    return members


def sections(patch):
    """{`diff --git` line: that file's part of the patch}; the same file twice refuses."""
    out = {}
    for part in re.split(r"^(?=diff --git )", patch, flags=re.MULTILINE)[1:]:
        if out.setdefault(part.split("\n", 1)[0], part) is not part:
            raise Refuse("a file occurs twice in a patch")
    return out


def blobs(part):
    """The `index <old>..<new>` line of a file section: the blobs before and after. None (a pure rename or copy) refuses."""
    m = INDEX_LINE.search(part.split("\n@@ ", 1)[0])
    if not m:
        raise Refuse("a file section names no blobs")
    return m.group(0)


def check_member_gates(run, repo, n, head):
    """A member's own required gates at its head: every latest check run `risk` and the newest commit status
    `security-review` are success. A batch of approved diffs must not carry a member its own PR would not land."""
    runs = json.loads(run("api", f"repos/{repo}/commits/{head}/check-runs?check_name=risk")).get("check_runs") or []
    statuses = json.loads(run("api", f"repos/{repo}/commits/{head}/statuses?per_page=100"))  # newest first
    sec = next((s for s in statuses if s.get("context") == "security-review"), {})
    if (not runs or any(c.get("name") != "risk" or c.get("conclusion") != "success" for c in runs)
            or sec.get("state") != "success"):
        raise Refuse(f"member #{n} has no green risk check and security-review status at the recorded head")


def check_batch(pr, patch, repo, approver, author_bot, run, ident):
    """Batch mode b to d: the batch diff is exactly its members' approved diffs, file by file. Returns the members."""
    if not author_bot or not agent_guard.same_login((pr.get("user") or {}).get("login"), author_bot):
        raise Refuse("batch PR is not by the author app")
    if risk.classify(patch, risk.read_text("AGENTS.md")) != "none":
        raise Refuse("risk class is not none")
    base, left, members = (pr.get("base") or {}).get("ref", ""), sections(patch), batch_members(pr.get("body"))
    for n, sha7 in members:
        m = json.loads(run("api", f"repos/{repo}/pulls/{n}"))
        head = (m.get("head") or {}).get("sha") or ""
        if not SHA_RE.fullmatch(head) or not head.startswith(sha7):
            raise Refuse(f"member #{n} is not at the recorded head")
        check_pr(m, repo, head)
        if (not risk.check_pr_form.AGENT_BRANCH.match(m["head"]["ref"]) or (m.get("base") or {}).get("ref") != base
                or any(str(lb.get("name")).startswith("risk:") for lb in m.get("labels") or [])):
            raise Refuse(f"member #{n} is not a plain agent/<N>- PR on {base}")
        reviews = paged(run, f"repos/{repo}/pulls/{n}/reviews")
        approved = [r for r in reviews if r.get("state") == "APPROVED"]
        if not approver or decisive_blockers(reviews) or not agent_guard.has_review(approved, approver, head):
            raise Refuse(f"member #{n} is not approved at the recorded head")
        own = run("api", f"repos/{repo}/compare/{base}...{head}", "-H", PATCH_ACCEPT)
        check_patch(own, m.get("changed_files"))
        for name, part in sections(own).items():
            mine = left.pop(name, None)  # popped: a file claimed by two members refuses at the second
            if mine is None or blobs(mine) != blobs(part) or ident(mine) != ident(part):
                raise Refuse(f"a file of member #{n} is missing or changed in the batch")
        check_member_gates(run, repo, n, head)
    if left:
        raise Refuse("a batch file belongs to no member")
    return members


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
    if pr["head"]["ref"] == BATCH_BRANCH:
        if any(p.startswith("docs/design/") for f in files for p in (f.get("filename"), f.get("previous_filename")) if p):
            raise Refuse("a batch never carries a docs/design/ file")
        patch = run("api", f"repos/{repo}/compare/{(pr.get('base') or {}).get('ref', '')}...{sha}", "-H", PATCH_ACCEPT)
        check_patch(patch, len(files))
        members = check_batch(pr, patch, repo, approver, author_bot, run, ident)
        check_linear(run, repo, pr_no, pr)
        again = json.loads(run("api", f"repos/{repo}/pulls/{pr_no}"))  # neither head nor member list moved meanwhile
        check_pr(again, repo, sha)
        if agent_guard.body_hash(again.get("body")) != bhash:
            raise Refuse("batch body changed while it was checked")
        names = ", ".join(f"#{n}" for n, _ in members)
        body = f"Re-approved without model: batch of {names}, every file as approved there.\n\nbody-hash: {bhash}"
        run("api", "-X", "POST", f"repos/{repo}/pulls/{pr_no}/reviews", "-f", f"commit_id={sha}", "-f", "event=APPROVE",
            "-f", f"body={body}")
        print(f"re-approved batch PR #{pr_no} at {sha[:12]} (members {names})")
        return 0
    old = previous_head(reviews, paged(run, f"repos/{repo}/issues/{pr_no}/timeline"), approver, author_bot, sha, bhash)
    base = (pr.get("base") or {}).get("ref", "")  # three dots: each head against its own merge base, any number of commits
    new_patch, old_patch = (run("api", f"repos/{repo}/compare/{base}...{c}", "-H", PATCH_ACCEPT) for c in (sha, old))
    for p in (new_patch, old_patch):
        check_patch(p, len(files))
    level = risk.classify(new_patch, risk.read_text("AGENTS.md"))
    labelled = any(lb.get("name") == "risk:security" for lb in pr.get("labels") or [])
    if level not in ("none", "security"):
        raise Refuse("risk class is not none")
    if level == "security" or labelled:  # the security verdict must cover exactly the new head
        comments = paged(run, f"repos/{repo}/issues/{pr_no}/comments")
        if risk.verdict_for(comments, sha, approver) != "approve":
            raise Refuse("no security-review approve for this head")
    pid, old_pid = ident(new_patch), ident(old_patch)
    if pid != old_pid:
        raise Refuse("patch changed since the approved head")
    check_linear(run, repo, pr_no, pr)
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
