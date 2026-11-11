"""Stage the delta for a later review round (agent-review.yml, after the full change is staged).

CLI: review_delta.py PR SHA   (env GH_TOKEN of the approver app, GH_REPO, APPROVER_BOT)
Round 1 (no earlier approver review): nothing is staged, the reviewer reads the full diff.
Round 2 and 3: `.review/delta.diff` (compare <last reviewed head>...SHA) and `.review/prior-findings.md` (the approver's
own earlier reviews). If the last reviewed head is not an ancestor of SHA (rebase, squash), is SHA itself, or the compare
fails, nothing is staged and the full diff stays the input. Never fails the job: exit 0 always. Data only, nothing is run.
"""
import json
import os
import re
import subprocess
import sys

import agent_guard

SHA_RE = re.compile(r"[0-9a-f]{40}")
DIFF_ACCEPT = "Accept: application/vnd.github.diff"


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def paged(run, path):
    return [x for page in json.loads(run("api", "--paginate", "--slurp", path)) for x in page]


def approver_reviews(reviews, approver):
    return [r for r in reviews if approver and r.get("commit_id")
            and agent_guard.same_login((r.get("user") or {}).get("login"), approver)]


def prior_findings(mine):
    parts = []
    for r in mine:
        body = (r.get("body") or "").strip()
        parts.append(f"## Review of {r['commit_id'][:12]} ({r.get('state')})\n\n{body}\n")
    return "\n".join(parts)


def stage_delta(pr_no, sha, env, run=gh, outdir=".review"):
    """Return 'delta' if the delta files were written, else 'full' (reason printed)."""
    repo, approver = env["GH_REPO"], env.get("APPROVER_BOT", "")
    try:
        mine = approver_reviews(paged(run, f"repos/{repo}/pulls/{pr_no}/reviews"), approver)
        if not mine:
            print("round 1: full diff")
            return "full"
        old = mine[-1]["commit_id"]
        if old == sha:
            print("last reviewed head is the current head: full diff")
            return "full"
        cmp = json.loads(run("api", f"repos/{repo}/compare/{old}...{sha}"))
        if cmp.get("status") != "ahead":
            print(f"{old[:12]} is not an ancestor of {sha[:12]} (status {cmp.get('status')}): full diff")
            return "full"
        delta = run("api", f"repos/{repo}/compare/{old}...{sha}", "-H", DIFF_ACCEPT)
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError, TypeError) as e:
        print(f"delta unavailable ({type(e).__name__}): full diff")
        return "full"
    if not delta.strip():
        print("empty delta: full diff")
        return "full"
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "delta.diff"), "w", encoding="utf-8") as f:
        f.write(delta)
    with open(os.path.join(outdir, "prior-findings.md"), "w", encoding="utf-8") as f:
        f.write(prior_findings(mine))
    print(f"delta since {old[:12]} staged")
    return "delta"


def main(argv):
    if len(argv) != 3 or not argv[1].isdigit() or not SHA_RE.fullmatch(argv[2]):
        print(__doc__, file=sys.stderr)
        return 2
    stage_delta(argv[1], argv[2], os.environ)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
