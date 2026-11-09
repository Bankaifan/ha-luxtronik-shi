"""Count work for a model run with no model; write `work=true|false` to $GITHUB_OUTPUT.

Usage: python3 prefilter.py orchestrator|scout
Needs the gh CLI (GH_TOKEN, GH_REPO) and git history. Environment: OWNER (default Bankaifan),
IDEAS (scout, issues per run), STALE_DAYS (default 7), TRUSTED (orchestrator, JSON from trusted_issues.py).
The Claude step runs only when `work=true`; the counts are printed to the log.
"""
import json
import os
import subprocess
import sys
import time

MAX_DEV = 2
MAX_OPEN_IDEAS = 10


def startable(trusted, dev_open):
    """Trusted issues the orchestrator could start: no agent:dev yet, ideas only when approved/auto-ok."""
    if dev_open >= MAX_DEV:
        return []
    out = []
    for item in trusted:
        labels = set(item["labels"])
        if "agent:dev" in labels or "needs-human" in labels:
            continue
        if "idea" in labels and not (item["approved"] or item["auto_ok"]):
            continue
        out.append(item["number"])
    return out


def handover_stale(age_days, newer_commits, stale_days):
    """HANDOVER.md is stale if it is old and main moved on since."""
    return age_days >= stale_days and newer_commits > 0


def orchestrator_work(candidates, needs_human, stale):
    return bool(candidates) or needs_human > 0 or stale


def scout_work(open_ideas, ideas_per_run):
    return ideas_per_run > 0 and open_ideas < MAX_OPEN_IDEAS


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def count(*args):
    return len(json.loads(gh(*args, "--limit", "200", "--json", "number")))


def handover_state():
    sha = git("log", "-1", "--format=%H %ct", "--", "HANDOVER.md")
    if not sha:
        return 9999, 1
    commit, ts = sha.split()
    newer = int(git("rev-list", "--count", f"{commit}..HEAD"))
    return (time.time() - int(ts)) / 86400, newer


def main(mode) -> int:
    if mode == "orchestrator":
        dev_open = count("issue", "list", "--state", "open", "--label", "agent:dev")
        trusted = json.loads(os.environ.get("TRUSTED") or subprocess.run(
            [sys.executable, "tools/trusted_issues.py"], check=True, capture_output=True, text=True).stdout)
        cands = startable(trusted, dev_open)
        human = count("pr", "list", "--state", "open", "--label", "needs-human")
        age, newer = handover_state()
        stale = handover_stale(age, newer, float(os.environ.get("STALE_DAYS", "7")))
        work = orchestrator_work(cands, human, stale)
        print(f"dev_open={dev_open} candidates={cands} needs_human_prs={human} "
              f"handover_age_days={age:.1f} commits_since={newer} stale={stale} work={work}")
    elif mode == "scout":
        ideas = count("issue", "list", "--state", "open", "--label", "idea")
        work = scout_work(ideas, int(os.environ.get("IDEAS", "3")))
        print(f"open_ideas={ideas} work={work}")
    else:
        print(__doc__, file=sys.stderr)
        return 2
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"work={str(work).lower()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
