"""Merge train core (docs/design/0003-merge-train.md, sections 4.3 and 5): lets approved agent PRs land one after another.

Model-free. The workflow (a later PR) runs it on push to main, on a schedule and on dispatch. One run:
1. Candidates: open same-repo agent PRs (status.is_agent_pr), not parked, not design PRs (only docs/design/ files),
   with an APPROVED review of the approver app on their current head (agent_guard.has_review).
   Oldest PR number first. A CHANGES_REQUESTED or dismissed review does not count.
2. One in flight: if a candidate is CLEAN, UNSTABLE or HAS_HOOKS, or BLOCKED with a required check running, it is about
   to merge. "Running" counts only the checks that `.github/rulesets/main.json` requires (none listed: every check).
   The run does nothing; the push of that merge starts the next run.
3. The oldest BEHIND candidate with auto-merge enabled is rebased (PUT pulls/N/update-branch, update_method=rebase).
4. The oldest DIRTY candidate gets status.handle_conflict at once, unless an agent-fix run is queued or running.
   PRs no longer edit VERSION or CHANGELOG.md, so those never conflict (issue #468).
0. Before all of that, `release_main` is the one writer of VERSION and CHANGELOG.md: the changelog fragments on main
   (changelog.d/<issue>.md) become ONE next version through tools/release_fragments.py, one commit force-pushed to
   `release/next` and released through one PR `Release <version>` (never a push to main; nothing to release closes it).
   That PR is the owner's only task: it carries a review request to OWNER, and its body is the fragments' user-facing
   lines (safe_note: no mention, no closing keyword, no HTML comment) plus one line naming the open `parked` issues
   and PRs (what the agents could not solve yet). A release that fails ends the run with exit 1 after the train steps.
5. A PR waiting only for the owner (waiting_for_owner) is skipped: it never counts as in flight, so the next ready PR
   lands. When main moves it is still rebased (BEHIND, even without auto-merge) or sent to agent-fix (DIRTY), so the
   owner approves the current head; the push re-runs the agent reviews. After his approval it is a normal candidate.
6. Prints numbers and actions, never tokens. A failed gh call is reported and ends the run with exit 1, before
   any label change of that run.
7. Batch (docs/decisions/0018-batch-train.md): two or more candidates that are green, carry no `risk:*` label, touch
   no docs/design/ file and whose files are pairwise disjoint (`batchable`) land as ONE PR on BATCH_BRANCH. No model:
   `build_batch` cherry-picks them onto main, the PR body records `Batch: #a@<sha7> ...` and their `Closes`/`Refs`
   numbers, tools/reapprove.py approves it. Per run (`batch_step`, before the serial plan):
   - a merged batch: its members still open at the recorded head are closed with `Merged with #<batch>.`, but only
     agent/<N>- PRs and only when the approver's review of the merged head names the hash of the body the member
     list is read from (`vouched`: a body edited after the approval closes nothing);
   - an open batch is closed when it is red, conflicting, has changes requested, has fewer than two members left,
     or is still open BATCH_WAIT_MIN minutes after its head was committed. That last rule is the signal for
     "refused" (a refusal writes nothing, and a workflow_run review run cannot be matched to a PR head): CI and the
     script approval take minutes, so a batch that old was refused or is stuck;
   - an open batch whose members are still ready at the recorded heads holds the train (nothing serial happens); it
     is built again and pushed only when main moved. Members that changed: built again from the ready ones;
   - no open batch and no PR in flight: a new one is built, unless the newest batch was closed unmerged with the same
     member set (those PRs then go the serial way). TRAIN_BATCH=off builds none.

CLI: train.py   do the run. Environment: GH_REPO, APPROVER_BOT (unset: nothing is approved, nothing happens),
     OWNER (default Bankaifan), TRAIN_BATCH. Needs the gh CLI with GH_TOKEN.
"""
import base64
import datetime
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import agent_guard
import reapprove
import restart
import status

sys.path.insert(0, str(Path(__file__).resolve().parent / "check"))
import check_pr_form

RELEASE = Path(__file__).resolve().parent / "release_fragments.py"  # always main's copy
RELEASE_PATHS = {"VERSION", "CHANGELOG.md"}  # plus changelog.d/: the only paths of the release commit
RELEASE_BRANCH = "release/next"  # force-updated, at most one open release PR
COMMITTER = ("Daniel", "476059+Bankaifan@users.noreply.github.com")

IN_FLIGHT = {"CLEAN", "UNSTABLE", "HAS_HOOKS"}
ACTIVE_RUN = {"in_progress", "queued", "waiting", "requested", "pending"}
LIST_FIELDS = ("number,title,url,headRefName,headRefOid,labels,mergeStateStatus,statusCheckRollup,"
               "isCrossRepository,files,autoMergeRequest,reviewRequests,body")
BATCH_BRANCH = check_pr_form.BATCH_BRANCH  # force-updated, at most one open batch PR
BATCH_MAX = 8
BATCH_WAIT_MIN = 30  # an open batch older than this (head commit) was refused or is stuck
EVIDENCE = "Test evidence exempt: every member passed this check in its own PR."
BATCH_FIELDS = ("number,state,body,headRefName,baseRefName,author,headRefOid,isCrossRepository,mergeStateStatus,"
                "statusCheckRollup")


def jlist(run, *args):
    return json.loads(run(*args))


def is_design_pr(pr):
    files = [f.get("path", "") for f in pr.get("files") or []]
    return bool(files) and all(f.startswith("docs/design/") for f in files)


def approved_on_head(pr, reviews, approver):
    """Only APPROVED reviews count: has_review alone also matches a CHANGES_REQUESTED review on the same head."""
    approved = [r for r in reviews if (r.get("state") or "").upper() == "APPROVED"]
    return agent_guard.has_review(approved, approver, pr["headRefOid"])


MAX_WAITING = 5  # waiting-for-owner PRs at once; beyond that new security slips wait


def waiting_for_owner(pr, reviews, approver, owner, required=None):
    """Agent PR with every agent review approved at its head, green CI (security-review included) and only the
    owner's approval missing: risk:security, a review request to the owner, not parked, not a design PR."""
    return (status.is_agent_pr(pr) and "risk:security" in status.names(pr) and "parked" not in status.names(pr)
            and not is_design_pr(pr) and status.ci_state(pr.get("statusCheckRollup"), required) == "green"
            and any(status.same_login(r.get("login"), owner) for r in pr.get("reviewRequests") or [])
            and approved_on_head(pr, reviews, approver))


def candidates(prs, reviews_of, approver):
    """Approved agent PRs, oldest first. reviews_of(number) is called only for PRs that pass the cheap filters."""
    out = []
    for p in prs:
        if not status.is_agent_pr(p) or "parked" in status.names(p) or is_design_pr(p):
            continue
        if approved_on_head(p, reviews_of(p["number"]), approver):
            out.append(p)
    return sorted(out, key=lambda p: p["number"])


def in_flight(pr, required=None):
    state = pr.get("mergeStateStatus")
    return state in IN_FLIGHT or (state == "BLOCKED"
                                  and status.ci_state(pr.get("statusCheckRollup"), required) == "running")


def plan(cands, fix_busy, waiting=(), required=None):
    """(PR in flight or None, PR to rebase or None, PR for a conflict fix or None). Nothing else happens while one is in flight.
    `waiting` = numbers of waiting-for-owner PRs: never in flight, rebased when BEHIND even without auto-merge.
    `required` = the ruleset's required checks; a non-required check neither holds the train nor counts as red."""
    busy = next((p for p in cands if p["number"] not in waiting and in_flight(p, required)), None)
    if busy:
        return busy, None, None
    rebase = next((p for p in cands if p.get("mergeStateStatus") == "BEHIND"
                   and (p.get("autoMergeRequest") or p["number"] in waiting)), None)
    conflict = None if fix_busy else next(iter(status.conflict_prs(cands)), None)
    return None, rebase, conflict


def git_env(token=""):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_COMMITTER_NAME": COMMITTER[0],
           "GIT_COMMITTER_EMAIL": COMMITTER[1], "GIT_AUTHOR_NAME": COMMITTER[0], "GIT_AUTHOR_EMAIL": COMMITTER[1]}
    if token:  # through the environment, never argv
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.extraheader",
                   GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {basic}")
    return env


def release_main(remote, token="", base="main", notes=None):
    """The one writer of VERSION and CHANGELOG.md (issue #468, #570): folds the changelog fragments on `base` into
    CHANGELOG.md, assigns the version (tools/release_fragments.py, main's copy) and force-pushes one commit to
    RELEASE_BRANCH, never to `base`. A run whose result equals the branch already there pushes nothing.
    Returns the new version ("" when there is nothing to release); None when it failed (git error, malformed
    fragment, push refused). `notes`, if a list, receives the user-facing changelog lines."""
    env = git_env(token)

    def git(tmp, *args):
        return subprocess.run(["git", *args], cwd=tmp, env=env, check=True, capture_output=True, text=True)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            git(tmp, "init", "-q")
            git(tmp, "fetch", "-q", remote, f"+refs/heads/{base}:refs/remotes/origin/{base}")
            git(tmp, "checkout", "-q", "--detach", f"origin/{base}")
            if not list(Path(tmp, "changelog.d").glob("[0-9]*.md")) or not Path(tmp, "VERSION").is_file():
                return ""  # no fragments, or a project that keeps its version elsewhere: nothing to release by script
            old = Path(tmp, "VERSION").read_text(encoding="utf-8").strip()
            done = subprocess.run([sys.executable, "-I", str(RELEASE), tmp], check=False, env=env,
                                  capture_output=True, text=True)
            if done.returncode != 0:
                return None
            lines = done.stdout.splitlines()
            version = next(line.split(" -> ")[-1] for line in lines if " -> " in line)
            git(tmp, "add", "-A")
            staged = git(tmp, "diff", "--cached", "--name-only").stdout.split()
            if not staged or not all(p in RELEASE_PATHS or p.startswith("changelog.d/") for p in staged):
                return None  # the release commit may only touch these paths, whatever the script did
            git(tmp, "commit", "-q", "-m", f"V{old}-RELEASE: version {version}")
            tree = git(tmp, "rev-parse", "HEAD^{tree}").stdout.strip()
            main_sha = git(tmp, "rev-parse", f"origin/{base}").stdout.strip()
            have = subprocess.run(["git", "fetch", "-q", remote, f"+refs/heads/{RELEASE_BRANCH}:refs/remotes/origin/{RELEASE_BRANCH}"],
                                  cwd=tmp, env=env, check=False, capture_output=True, text=True)
            same = False
            if have.returncode == 0:
                same = (git(tmp, "rev-parse", f"origin/{RELEASE_BRANCH}^{{tree}}").stdout.strip() == tree
                        and git(tmp, "rev-parse", f"origin/{RELEASE_BRANCH}^").stdout.strip() == main_sha)
            if not same:
                git(tmp, "push", "-q", "--force", remote, f"HEAD:refs/heads/{RELEASE_BRANCH}")
            if notes is not None:
                notes.extend(line.removeprefix("note: ") for line in lines if line.startswith("note: "))
            return version
    except (subprocess.CalledProcessError, OSError, StopIteration):
        return None


def batchable(cands, required=None):
    """Members of the next batch (decision 0018, rule 1) out of the approved candidates, oldest first: `agent/<N>-`,
    green, not conflicting, no `risk:*` label (so none waits for the owner), no docs/design/ file (auto-merge may
    hold those), files known and disjoint from every earlier member, at most BATCH_MAX PRs and fewer files than
    reapprove accepts. Fewer than two: [] (the serial path)."""
    out, seen = [], set()
    for p in cands:
        files = {f.get("path", "") for f in p.get("files") or []}
        if (len(out) < BATCH_MAX and check_pr_form.AGENT_BRANCH.match(p["headRefName"]) and files
                and not any(n.startswith("risk:") for n in status.names(p))
                and status.ci_state(p.get("statusCheckRollup"), required) == "green"
                and p.get("mergeStateStatus") != "DIRTY"
                and not any(f.startswith("docs/design/") for f in files)
                and not files & seen and len(files | seen) < reapprove.MAX_FILES):
            out.append(p)
            seen |= files
    return out if len(out) > 1 else []


def recorded(pr):
    """[(member number, sha7)] of a batch PR's `Batch:` line; [] when there is none."""
    try:
        return reapprove.batch_members(pr.get("body"))
    except reapprove.Refuse:
        return []


def batch_text(members):
    """(title, body) of the batch PR. The body is the `Batch:` line, one fixed line for check_test_evidence (a
    member's own exemption cannot be copied) and, per member, the numbers of its own closing keywords and `Refs`:
    numbers only, no text of a member's body is copied."""
    lines = ["Batch: " + " ".join(f"#{p['number']}@{p['headRefOid'][:7]}" for p in members), EVIDENCE]
    for p in members:
        closing = [int(n) for n in restart._CLOSING.findall(p.get("body") or "")]
        lines += [f"Closes #{n}" for n in closing]
        lines += [f"Refs #{n}" for n in restart.issue_refs(p.get("body")) if n not in closing]
    return "Batch: " + ", ".join(f"#{p['number']}" for p in members), "\n".join(dict.fromkeys(lines))


def build_batch(remote, members, token="", base="main", avoid=frozenset()):
    """Cherry-pick every member (merge base to its listed head, fetched by PR ref) onto `base` in a scratch clone and
    force-push the result to BATCH_BRANCH. A member whose head moved, whose pick fails or whose files changed on
    `base` since its merge base (reapprove wants every file blob-exact as approved) is dropped. Returns the
    members kept; [] and no push when fewer than two are left or their numbers equal `avoid`; None on a git error.
    A result with the tree of the branch already there, on top of the current `base`, is not pushed again."""
    if len(members) < 2 or {p["number"] for p in members} == set(avoid):
        return []  # known before any clone: the set that just failed is not built again on every run
    env = git_env(token)

    def git(tmp, *args, check=True):
        return subprocess.run(["git", *args], cwd=tmp, env=env, check=check, capture_output=True, text=True)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            git(tmp, "init", "-q")
            git(tmp, "fetch", "-q", remote, f"+refs/heads/{base}:refs/remotes/origin/{base}")
            git(tmp, "checkout", "-q", "--detach", f"origin/{base}")
            kept = []
            for p in members:
                ref = f"refs/remotes/pr/{p['number']}"
                got = git(tmp, "fetch", "-q", remote, f"+refs/pull/{p['number']}/head:{ref}", check=False)
                if got.returncode != 0 or git(tmp, "rev-parse", ref).stdout.strip() != p["headRefOid"]:
                    continue
                fork = git(tmp, "merge-base", f"origin/{base}", ref).stdout.strip()
                names = [set(git(tmp, "diff", "--name-only", fork, r).stdout.splitlines()) for r in (ref, f"origin/{base}")]
                if names[0] & names[1]:
                    continue
                if git(tmp, "cherry-pick", f"{fork}..{ref}", check=False).returncode == 0:
                    kept.append(p)
                else:
                    git(tmp, "cherry-pick", "--abort", check=False)  # back to the state before this member
            if len(kept) < 2 or {p["number"] for p in kept} == set(avoid):
                return []
            have = git(tmp, "fetch", "-q", remote, f"+refs/heads/{BATCH_BRANCH}:refs/remotes/origin/{BATCH_BRANCH}",
                       check=False)
            there = f"origin/{BATCH_BRANCH}"
            same = (have.returncode == 0
                    and git(tmp, "rev-parse", f"{there}^{{tree}}").stdout == git(tmp, "rev-parse", "HEAD^{tree}").stdout
                    and git(tmp, "merge-base", "--is-ancestor", f"origin/{base}", there, check=False).returncode == 0)
            if not same:
                git(tmp, "push", "-q", "--force", remote, f"HEAD:refs/heads/{BATCH_BRANCH}")
            return kept
    except (subprocess.CalledProcessError, OSError):
        return None


def vouched(pr, reviews, approver):
    """The approver's APPROVED review of this head carries the hash of this body: the `Batch:` line read from it is
    the one tools/reapprove.py checked, not a later edit."""
    mine = [r for r in reviews if (r.get("state") or "").upper() == "APPROVED"
            and agent_guard._BODY_HASH_LINE.search(r.get("body") or "")]
    return bool(approver) and agent_guard.has_review(mine, approver, pr["headRefOid"], agent_guard.body_hash(pr.get("body")))


def batch_step(run, repo, prs, cands, reviews_of, required, now, builder, enabled=True, idle=True, approver="",
               author=""):
    """Step 7 of the module text. Returns (numbers of PRs closed as landed, text when a batch holds the train or "").
    The batch PR is the one from BATCH_BRANCH into main (by the author app, when its name is known): a PR from that
    branch into another base is not it and hides nothing."""
    known = [p for p in jlist(run, "pr", "list", "--state", "all", "--head", BATCH_BRANCH, "--base", "main",
                              "--limit", "5", "--json", BATCH_FIELDS)
             if p.get("headRefName") == BATCH_BRANCH and p.get("baseRefName") == "main" and not p.get("isCrossRepository")
             and (not author or status.same_login((p.get("author") or {}).get("login"), author))]  # newest first
    opened = next((p for p in known if p.get("state") == "OPEN"), None)
    last = next((p for p in known if p.get("state") in ("MERGED", "CLOSED")), None)
    landed = set()
    if last and last["state"] == "MERGED":
        pool = {p["number"]: p["headRefOid"] for p in prs
                if status.is_agent_pr(p) and check_pr_form.AGENT_BRANCH.match(p["headRefName"])}
        mine = [n for n, sha7 in recorded(last) if pool.get(n, "").startswith(sha7)]
        for n in mine if mine and vouched(last, reviews_of(last["number"]), approver) else []:
            run("pr", "close", str(n), "--comment", f"Merged with #{last['number']}.")
            landed.add(n)
    ready = [p for p in cands if p["number"] not in landed]
    failed = {n for n, _ in recorded(last)} if last and last["state"] == "CLOSED" else frozenset()
    fresh = batchable(ready, required) if enabled else []
    if not opened:
        kept = builder(fresh, failed) if fresh and idle else []
        if kept:
            title, body = batch_text(kept)
            run("pr", "create", "--base", "main", "--head", BATCH_BRANCH, "--title", title, "--body", body)
            return landed, f"batch: opened {title}"
        return landed, ""
    number, old = opened["number"], recorded(opened)
    ci = status.ci_state(opened.get("statusCheckRollup"), required)
    built = run("api", f"repos/{repo}/commits/{opened['headRefOid']}", "--jq", ".commit.committer.date").strip()
    why = ("red" if ci == "red" else "conflicting" if opened.get("mergeStateStatus") == "DIRTY"
           else "changes requested" if reapprove.decisive_blockers(reviews_of(number))
           else f"not merged {BATCH_WAIT_MIN} min after it was built (refused or stuck)"
           if built and status.minutes_since(built, now) > BATCH_WAIT_MIN else "")
    if not why:
        same = batchable([p for p in ready if (p["number"], p["headRefOid"][:7]) in old], required)
        members = same if enabled and len(same) == len(old) else fresh  # its members, all still ready as recorded
        kept = builder(members, failed) if members else []
        if kept is None:
            return landed, f"batch: PR #{number} could not be built again; the next run retries"
        why = "" if kept else "fewer than two members are ready"
    if why:
        run("pr", "close", str(number))
        print(f"batch: closed PR #{number}: {why}")
        return landed, ""
    if [(p["number"], p["headRefOid"][:7]) for p in kept] != old:
        if jlist(run, "pr", "view", str(number), "--json", "state").get("state") != "OPEN":
            return landed, f"batch: PR #{number} was merged or closed meanwhile; its body stays as approved"
        title, body = batch_text(kept)
        run("pr", "edit", str(number), "--title", title, "--body", body)
    return landed, f"waiting: batch PR #{number} is about to merge; the train runs again after its push"


# Fixed words of the release PR body per OWNER_LANG (the notes themselves are written in that language by the developers).
WORDS = {"German": ("Nur interne Änderungen.", "Noch ungelöst"), "English": ("Internal changes only.", "Not solved yet")}


def safe_note(line):
    """A changelog line as plain text for the PR the owner merges: it mentions nobody, closes no issue and hides
    nothing (fragments are written by developer models, also for intake work)."""
    line = line.replace("@", "")
    while check_pr_form.CLOSING.search(line):
        line = check_pr_form.CLOSING.sub(lambda m: m.group(0).split()[0], line)  # the keyword stays, its target goes
    return line.replace("<!--", "&lt;!--")


def release_pr(run, version, notes, owner, lang="German"):
    """One open release PR at most: open or update it for `version`, or close it when there is nothing to release.
    Returns a short report line."""
    open_prs = jlist(run, "pr", "list", "--state", "open", "--head", RELEASE_BRANCH, "--json", "number,headRefName")
    number = next((p["number"] for p in open_prs if p.get("headRefName") == RELEASE_BRANCH), None)
    if not version:
        if number is None:
            return ""
        run("pr", "close", str(number))
        return f"closed release PR #{number}: nothing to release"
    internal, unsolved = WORDS.get(lang, WORDS["English"])
    parked = sorted({i["number"] for kind in ("issue", "pr")
                     for i in jlist(run, kind, "list", "--state", "open", "--label", status.PARKED, "--json", "number")})
    body = "\n".join(map(safe_note, notes)) or internal
    if parked:
        body += f"\n\n{unsolved}: " + ", ".join(f"#{n}" for n in parked)
    title = f"Release {version}"
    if number is None:
        run("pr", "create", "--base", "main", "--head", RELEASE_BRANCH, "--title", title, "--body", body, "--reviewer", owner)
        return f"opened release PR {title}"
    run("pr", "edit", str(number), "--title", title, "--body", body, "--add-reviewer", owner)
    return f"updated release PR #{number}: {title}"


def run_train(env, run=status.gh, releaser=None, now=None, builder=None):
    repo = env["GH_REPO"]
    notes = []
    owner = env.get("OWNER", status.OWNER_DEFAULT)
    if releaser is None:
        def releaser():
            return release_main(f"https://github.com/{repo}.git", env.get("GH_TOKEN", ""), notes=notes)
    released = releaser()
    if released is None:
        print("release: failed (see the fragment and the branch push); the next run retries")
    else:
        try:
            line = release_pr(run, released, notes, owner, env.get("OWNER_LANG") or "German")
        except subprocess.CalledProcessError as e:
            print(f"release: PR step failed, a gh call exited {e.returncode}; the next run retries")
        else:
            if line:
                print(line)
    approver = env.get("APPROVER_BOT", "")
    if builder is None:
        def builder(members, avoid):
            return build_batch(f"https://github.com/{repo}.git", members, env.get("GH_TOKEN", ""), avoid=avoid)
    required = status.required_contexts()  # None: every check counts
    try:
        prs = jlist(run, "pr", "list", "--state", "open", "--limit", str(status.PR_LIMIT), "--json", LIST_FIELDS)

        def reviews_of(number):
            pages = jlist(run, "api", "--paginate", "--slurp", f"repos/{repo}/pulls/{number}/reviews")
            return [r for page in pages for r in page]

        cands = candidates(prs, reviews_of, approver)
        waiting = {p["number"] for p in cands
                   if waiting_for_owner(p, reviews_of(p["number"]), approver, owner, required)}
        fix_runs = jlist(run, "run", "list", "--workflow", "agent-fix.yml", "--limit", "5", "--json", "status")
        fix_busy = any(r.get("status") in ACTIVE_RUN for r in fix_runs)
        landed, hold = batch_step(run, repo, prs, cands, reviews_of, required, now or datetime.datetime.now(datetime.UTC),
                                  builder, env.get("TRAIN_BATCH") != "off",
                                  idle=not plan(cands, fix_busy, waiting, required)[0], approver=approver,
                                  author=env.get("AUTHOR_BOT", ""))
        if hold:
            print(hold)
            return int(released is None)
        cands = [p for p in cands if p["number"] not in landed]  # closed just now: the batch they were in is merged
        busy, rebase, conflict = plan(cands, fix_busy, waiting, required)
        if busy:
            print(f"waiting: PR #{busy['number']} is about to merge; the train runs again after its push")
            return int(released is None)
        if rebase:
            run("api", "-X", "PUT", f"repos/{repo}/pulls/{rebase['number']}/update-branch", "-f", "update_method=rebase")
            print(f"rebased PR #{rebase['number']} onto main")
        if conflict:
            print(f"conflict PR #{conflict['number']}: {status.handle_conflict(conflict, owner, run)}")
        if not rebase and not conflict:
            print(f"nothing to do; approved candidates: {len(cands)}, waiting for owner: {len(waiting)}")
    except subprocess.CalledProcessError as e:
        print(f"train stopped: a gh call exited {e.returncode}; this run changed no labels")
        return 1
    return int(released is None)  # a release that failed is a red run, but only after the train did its work


def main(argv):
    if len(argv) == 1:
        return run_train(os.environ)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
