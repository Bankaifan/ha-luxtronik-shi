"""Merge train core (docs/design/0003-merge-train.md, sections 4.3 and 5): lets approved agent PRs land one after another.

Model-free. The workflow (a later PR) runs it on push to main, on a schedule and on dispatch. One run:
1. Candidates: open same-repo agent PRs (status.is_agent_pr), not needs-human, not design PRs (only docs/design/ files),
   with an APPROVED review of the approver app on their current head (agent_guard.has_review).
   Oldest PR number first. A CHANGES_REQUESTED or dismissed review does not count.
2. One in flight: if a candidate is CLEAN, UNSTABLE or HAS_HOOKS, or BLOCKED with checks running, it is about to merge.
   The run does nothing; the push of that merge starts the next run.
3. The oldest BEHIND candidate with auto-merge enabled is rebased (PUT pulls/N/update-branch, update_method=rebase).
4. The oldest DIRTY candidate gets status.handle_conflict at once, unless an agent-fix run is queued or running.
5. A PR waiting only for the owner (waiting_for_owner) is skipped: it never counts as in flight, so the next ready PR
   lands. When main moves it is still rebased (BEHIND, even without auto-merge) or sent to agent-fix (DIRTY), so the
   owner approves the current head; the push re-runs the agent reviews. After his approval it is a normal candidate.
6. Prints numbers and actions, never tokens. A failed gh call is reported and ends the run with exit 1, before
   any label change of that run.

CLI: train.py   do the run. Environment: GH_REPO, APPROVER_BOT (unset: nothing is approved, nothing happens),
     OWNER (default Bankaifan). Needs the gh CLI with GH_TOKEN.
"""
import json
import os
import subprocess
import sys

import agent_guard
import status

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


def waiting_for_owner(pr, reviews, approver, owner):
    """Agent PR with every agent review approved at its head, green CI (security-review included) and only the
    owner's approval missing: risk:security, a review request to the owner, no needs-human, not a design PR."""
    return (status.is_agent_pr(pr) and "risk:security" in status.names(pr) and "needs-human" not in status.names(pr)
            and not is_design_pr(pr) and status.ci_state(pr.get("statusCheckRollup")) == "green"
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


def in_flight(pr):
    state = pr.get("mergeStateStatus")
    return state in IN_FLIGHT or (state == "BLOCKED" and status.ci_state(pr.get("statusCheckRollup")) == "running")


def plan(cands, fix_busy, waiting=()):
    """(PR in flight or None, PR to rebase or None, PR for a conflict fix or None). Nothing else happens while one is in flight.
    `waiting` = numbers of waiting-for-owner PRs: never in flight, rebased when BEHIND even without auto-merge."""
    busy = next((p for p in cands if p["number"] not in waiting and in_flight(p)), None)
    if busy:
        return busy, None, None
    rebase = next((p for p in cands if p.get("mergeStateStatus") == "BEHIND"
                   and (p.get("autoMergeRequest") or p["number"] in waiting)), None)
    conflict = None if fix_busy else next(iter(status.conflict_prs(cands)), None)
    return None, rebase, conflict


def run_train(env, run=status.gh):
    repo = env["GH_REPO"]
    owner = env.get("OWNER", status.OWNER_DEFAULT)
    approver = env.get("APPROVER_BOT", "")
    try:
        prs = jlist(run, "pr", "list", "--state", "open", "--limit", str(status.PR_LIMIT), "--json", LIST_FIELDS)

        def reviews_of(number):
            pages = jlist(run, "api", "--paginate", "--slurp", f"repos/{repo}/pulls/{number}/reviews")
            return [r for page in pages for r in page]

        cands = candidates(prs, reviews_of, approver)
        waiting = {p["number"] for p in cands if waiting_for_owner(p, reviews_of(p["number"]), approver, owner)}
        fix_runs = jlist(run, "run", "list", "--workflow", "agent-fix.yml", "--limit", "5", "--json", "status")
        fix_busy = any(r.get("status") in ACTIVE_RUN for r in fix_runs)
        busy, rebase, conflict = plan(cands, fix_busy, waiting)
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
