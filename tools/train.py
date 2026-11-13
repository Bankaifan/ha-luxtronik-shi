"""Merge train core (docs/design/0003-merge-train.md, sections 4.3 and 5): lets approved agent PRs land one after another.

Model-free. The workflow (a later PR) runs it on push to main, on a schedule and on dispatch. One run:
1. Candidates: open same-repo agent PRs (status.is_agent_pr), not needs-human, not design PRs (only docs/design/ files),
   with an APPROVED review of the approver app on their current head (agent_guard.has_review).
   Oldest PR number first. A CHANGES_REQUESTED or dismissed review does not count.
2. One in flight: if a candidate is CLEAN, UNSTABLE or HAS_HOOKS, or BLOCKED with a required check running, it is about
   to merge. "Running" counts only the checks that `.github/rulesets/main.json` requires (none listed: every check).
   The run does nothing; the push of that merge starts the next run.
3. The oldest BEHIND candidate with auto-merge enabled is rebased (PUT pulls/N/update-branch, update_method=rebase).
4. The oldest DIRTY candidate gets status.handle_conflict at once, unless an agent-fix run is queued or running.
   PRs no longer edit VERSION or CHANGELOG.md, so those never conflict (issue #468).
0. Before all of that, `release_main` is the one writer of VERSION and CHANGELOG.md: changelog fragments on main
   (changelog.d/<issue>.md) get the next versions through tools/release_fragments.py, one commit force-pushed to
   `release/next` and released through one PR `Release <versions>` (never a push to main; nothing to release closes it).
5. A PR waiting only for the owner (waiting_for_owner) is skipped: it never counts as in flight, so the next ready PR
   lands. When main moves it is still rebased (BEHIND, even without auto-merge) or sent to agent-fix (DIRTY), so the
   owner approves the current head; the push re-runs the agent reviews. After his approval it is a normal candidate.
6. Prints numbers and actions, never tokens. A failed gh call is reported and ends the run with exit 1, before
   any label change of that run.

CLI: train.py   do the run. Environment: GH_REPO, APPROVER_BOT (unset: nothing is approved, nothing happens),
     OWNER (default Bankaifan). Needs the gh CLI with GH_TOKEN.
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import agent_guard
import status

RELEASE = Path(__file__).resolve().parent / "release_fragments.py"  # always main's copy
RELEASE_PATHS = {"VERSION", "CHANGELOG.md"}  # plus changelog.d/: the only paths of the release commit
RELEASE_BRANCH = "release/next"  # force-updated, at most one open release PR
COMMITTER = ("Daniel", "476059+Bankaifan@users.noreply.github.com")

IN_FLIGHT = {"CLEAN", "UNSTABLE", "HAS_HOOKS"}
ACTIVE_RUN = {"in_progress", "queued", "waiting", "requested", "pending"}
LIST_FIELDS = ("number,title,url,headRefName,headRefOid,labels,mergeStateStatus,statusCheckRollup,"
               "isCrossRepository,files,autoMergeRequest,reviewRequests")


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
    owner's approval missing: risk:security, a review request to the owner, no needs-human, not a design PR."""
    return (status.is_agent_pr(pr) and "risk:security" in status.names(pr) and "needs-human" not in status.names(pr)
            and not is_design_pr(pr) and status.ci_state(pr.get("statusCheckRollup"), required) == "green"
            and any(status.same_login(r.get("login"), owner) for r in pr.get("reviewRequests") or [])
            and approved_on_head(pr, reviews, approver))


def candidates(prs, reviews_of, approver):
    """Approved agent PRs, oldest first. reviews_of(number) is called only for PRs that pass the cheap filters."""
    out = []
    for p in prs:
        if not status.is_agent_pr(p) or "needs-human" in status.names(p) or is_design_pr(p):
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


def release_main(remote, token="", base="main", fragments=None):
    """The one writer of VERSION and CHANGELOG.md (issue #468, #570): folds the changelog fragments on `base` into
    CHANGELOG.md, assigns the versions (tools/release_fragments.py, main's copy) and force-pushes one commit to
    RELEASE_BRANCH, never to `base`. A run whose result equals the branch already there pushes nothing.
    Returns the released versions ([] when there is nothing to release); None when it failed (git error, malformed
    fragment, push refused). `fragments`, if a list, receives the folded fragment file names."""
    env = git_env(token)

    def git(tmp, *args):
        return subprocess.run(["git", *args], cwd=tmp, env=env, check=True, capture_output=True, text=True)

    try:
        with tempfile.TemporaryDirectory() as tmp:
            git(tmp, "init", "-q")
            git(tmp, "fetch", "-q", remote, f"+refs/heads/{base}:refs/remotes/origin/{base}")
            git(tmp, "checkout", "-q", "--detach", f"origin/{base}")
            names = sorted(p.name for p in Path(tmp, "changelog.d").glob("[0-9]*.md"))
            if not names:
                return []
            done = subprocess.run([sys.executable, "-I", str(RELEASE), tmp], check=False, env=env,
                                  capture_output=True, text=True)
            if done.returncode != 0:
                return None
            versions = [line.split(" -> ")[-1] for line in done.stdout.splitlines() if " -> " in line]
            git(tmp, "add", "-A")
            staged = git(tmp, "diff", "--cached", "--name-only").stdout.split()
            if not staged or not all(p in RELEASE_PATHS or p.startswith("changelog.d/") for p in staged):
                return None  # the release commit may only touch these paths, whatever the script did
            git(tmp, "commit", "-q", "-m", f"Release {', '.join(versions)} from changelog fragments")
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
            if fragments is not None:
                fragments.extend(names)
            return versions
    except (subprocess.CalledProcessError, OSError):
        return None


def release_pr(run, versions, fragments):
    """One open release PR at most: open or update it for `versions`, or close it when there is nothing to release.
    Returns a short report line."""
    open_prs = jlist(run, "pr", "list", "--state", "open", "--head", RELEASE_BRANCH, "--json", "number,headRefName")
    number = next((p["number"] for p in open_prs if p.get("headRefName") == RELEASE_BRANCH), None)
    if not versions:
        if number is None:
            return ""
        run("pr", "close", str(number), "--comment", "Nothing left to release.")
        return f"closed release PR #{number}: nothing to release"
    title = f"Release {', '.join(versions)}"
    if len(title) > 100:  # check_pr_form caps titles at 100 characters
        title = f"Release {versions[0]} to {versions[-1]} ({len(versions)} versions)"
    body = f"Versions: {', '.join(versions)}\nFragments: {', '.join(fragments) or 'none'}"
    if number is None:
        run("pr", "create", "--base", "main", "--head", RELEASE_BRANCH, "--title", title, "--body", body)
        return f"opened release PR {title}"
    run("pr", "edit", str(number), "--title", title, "--body", body)
    return f"updated release PR #{number}: {title}"


def run_train(env, run=status.gh, releaser=None):
    repo = env["GH_REPO"]
    folded = []
    if releaser is None:
        def releaser():
            return release_main(f"https://github.com/{repo}.git", env.get("GH_TOKEN", ""), fragments=folded)
    released = releaser()
    if released is None:
        print("release: failed (see the fragment and the branch push); the next run retries")
    else:
        try:
            line = release_pr(run, released, folded)
        except subprocess.CalledProcessError as e:
            print(f"release: PR step failed, a gh call exited {e.returncode}; the next run retries")
        else:
            if line:
                print(line)
    owner = env.get("OWNER", status.OWNER_DEFAULT)
    approver = env.get("APPROVER_BOT", "")
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
        busy, rebase, conflict = plan(cands, fix_busy, waiting, required)
        if busy:
            print(f"waiting: PR #{busy['number']} is about to merge; the train runs again after its push")
            return 0
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
    return 0


def main(argv):
    if len(argv) == 1:
        return run_train(os.environ)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
