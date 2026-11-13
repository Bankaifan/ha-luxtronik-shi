"""Model-free dispatcher (design 0015, step 3): start ready issues that already carry a slip, no model run.

  python3 tools/dispatch.py start
  python3 tools/dispatch.py after-merge PR_NUMBER

start: candidates are the whole startable list of `prefilter.start_state()` (trusted issues from
`tools/trusted_issues.py`, unblocked, in list order), not the cut list the orchestrator sees. Slip-less issues are skipped
(the orchestrator writes their slip). Each one with a slip (`slip.py`) is checked with `overlap.py` (exit 1 or 2:
skipped, retried next run), then gets its model label and `agent:dev` last. The walk stops after min(free dev, free PR
slots) starts. Before that, an agent:dev issue parked by a run (last bot comment `Waiting for #N`, #N closed, no agent-dev
run queued or in progress for it) is restarted: agent:dev removed and added again, then one fixed comment `Restarted: #N is closed.` is posted so the
same `Waiting for #N` is not acted on twice. While #N is open it holds no slot. after-merge: removes `agent:dev` from the
issues a merged same-repo `agent/` PR names with `Refs #N` / `Closes #N`, then runs start. Writes labels and that one
fixed restart comment; issue text is read for numbers and `Files:` / `Model:` / `Depends on:` lines and never copied
into a comment. Needs the gh CLI (GH_TOKEN, GH_REPO).
"""
import json
import subprocess
import sys

import budget
import overlap
import prefilter
import slip

LABEL_COLOR = "ededed"
RESTARTED_NOTE = "Restarted: #{blocker} is closed."  # fixed text, never issue content


def start(state, gh=prefilter.gh, overlap_main=overlap.main, authors=overlap.DEFAULT_TRUSTED):
    """Start the first issues of STATE["startable"] that hold a slip, up to STATE["limit"] starts; slip-less issues
    are passed over, not counted. Returns the numbers started."""
    started = []
    for n in state["startable"]:
        if len(started) >= state["limit"]:
            break
        issue = json.loads(gh("issue", "view", str(n), "--json", "labels,body,author,comments"))
        files = slip.slip_files(issue, authors)
        if not files:
            continue  # no slip: the model writes it
        if overlap_main(["--files", ",".join(files), "--issue", str(n)]) != 0:
            print(f"#{n}: overlap or unreadable, deferred")
            continue
        model = f"model:{slip.model_of(issue, authors)}"
        try:
            gh("label", "create", model, "--force", "--color", LABEL_COLOR)
            gh("issue", "edit", str(n), "--add-label", model)
            gh("issue", "edit", str(n), "--add-label", "agent:dev")  # last: this label starts the developer run
        except (subprocess.CalledProcessError, OSError) as e:  # a failed label call must not stop the other issues
            print(f"#{n}: label call failed ({type(e).__name__}), skipped", file=sys.stderr)
            continue
        started.append(n)
        print(f"#{n}: started ({model})")
    return started


def run_active(n, title, gh=prefilter.gh):
    """True while an agent-dev run for issue N is queued or in progress. A run is matched by its display title
    (the issue title or `#N`); a run that matches neither is not seen."""
    for status in ("queued", "in_progress"):
        runs = json.loads(gh("run", "list", "--workflow", "agent-dev.yml", "--status", status, "--json", "displayTitle"))
        if any(title in r["displayTitle"] or f"#{n}" in r["displayTitle"] for r in runs):
            return True
    return False


def restart_waiting(state, gh=prefilter.gh):
    """Restart the parked agent:dev issues of STATE["restart"] (last comment `Waiting for #N`, #N closed) that have no
    run in progress: remove and re-add agent:dev. Returns the numbers restarted."""
    restarted = []
    for n, blocker in sorted(state.get("restart", {}).items()):
        try:
            title = json.loads(gh("issue", "view", str(n), "--json", "title"))["title"]
            if run_active(n, title, gh):
                print(f"#{n}: run in progress, not restarted")
                continue
            gh("issue", "edit", str(n), "--remove-label", "agent:dev")
            gh("issue", "edit", str(n), "--add-label", "agent:dev")
            # the marker: the last trusted comment is no longer `Waiting for #N`, so this wait is acted on once
            gh("issue", "comment", str(n), "--body", RESTARTED_NOTE.format(blocker=blocker))
        except (subprocess.CalledProcessError, OSError) as e:
            print(f"#{n}: restart failed ({type(e).__name__}), skipped", file=sys.stderr)
            continue
        restarted.append(n)
        print(f"#{n}: restarted (#{blocker} closed)")
    return restarted


def after_merge(pr, gh=prefilter.gh):
    """Remove `agent:dev` from the issues a merged same-repo `agent/` PR names; returns their numbers."""
    p = json.loads(gh("pr", "view", str(pr), "--json", "state,body,headRefName,isCrossRepository"))
    if p.get("state") != "MERGED" or p.get("isCrossRepository") or not p.get("headRefName", "").startswith("agent/"):
        return []
    done = sorted(prefilter.closing_issues(p.get("body")))
    for n in done:
        try:
            gh("issue", "edit", str(n), "--remove-label", "agent:dev")
        except (subprocess.CalledProcessError, OSError) as e:
            print(f"#{n}: cannot remove agent:dev ({type(e).__name__})", file=sys.stderr)
    return done


def main(argv) -> int:
    if not argv or argv[0] not in ("start", "after-merge") or (argv[0] == "after-merge" and len(argv) != 2):
        print(__doc__, file=sys.stderr)
        return 2
    if argv[0] == "after-merge":
        print(f"agent:dev removed from {after_merge(int(argv[1]))}")
    if reason := budget.low(budget.START):
        print(reason)
        return 0
    state = prefilter.start_state()
    restart_waiting(state)
    start(state)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
