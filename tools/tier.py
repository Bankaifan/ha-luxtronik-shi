"""Tier proposal: compare the last four rows of docs/metrics.csv with the (estimated) thresholds.

`.agents/tier` holds the current tier (S, M or L). When at least two thresholds are exceeded in each of
the last four weeks, `--propose` opens ONE issue "Propose tier M" / "Propose tier L" (skipped if one is open).
Never changes `.agents/tier`. Needs the gh CLI (GH_TOKEN, GH_REPO) only for --propose.
"""
import csv
import json
import pathlib
import subprocess
import sys

TIER_FILE = pathlib.Path(".agents/tier")
METRICS = pathlib.Path("docs/metrics.csv")
WEEKS = 4
NEEDED = 2
NEXT = {"S": "M", "M": "L"}
# Estimates, to be calibrated (docs/decisions/0008-tiers.md). "lines or modules" counts as one threshold.
THRESHOLDS = {
    "S": {"lines": 5000, "modules": 30, "prs": 3, "conflicts": 3, "rounds": 1.5, "ci": 10},
    "M": {"lines": 30000, "modules": 150, "prs": 6, "conflicts": 10, "rounds": 2, "ci": 20},
}


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None  # empty = unknown = not exceeded


def exceeded(row, tier):
    """Names of the thresholds the row exceeds for the step away from `tier`."""
    t = THRESHOLDS[tier]
    lines, modules = num(row.get("code_lines")), num(row.get("modules"))
    prs, conflicts = num(row.get("max_parallel_agent_prs")), num(row.get("conflicts_rebuilt"))
    rounds, ci = num(row.get("avg_review_rounds")), num(row.get("median_ci_minutes"))
    hits = []
    if (lines is not None and lines >= t["lines"]) or (modules is not None and modules >= t["modules"]):
        hits.append("code")
    if prs is not None and prs >= t["prs"]:
        hits.append("parallel PRs")
    if conflicts is not None and conflicts >= t["conflicts"]:
        hits.append("conflicts")
    if rounds is not None and rounds > t["rounds"]:
        hits.append("review rounds")
    if ci is not None and ci > t["ci"]:
        hits.append("CI duration")
    return hits


def propose(rows, tier):
    """Target tier if the last four weeks each exceed two or more thresholds, else None."""
    if tier not in NEXT or len(rows) < WEEKS:
        return None
    last = rows[-WEEKS:]
    return NEXT[tier] if all(len(exceeded(r, tier)) >= NEEDED for r in last) else None


def read_tier(path=TIER_FILE):
    try:
        tier = pathlib.Path(path).read_text().strip().upper()
    except OSError:
        return "S"
    return tier if tier in ("S", "M", "L") else "S"


def read_rows(path=METRICS):
    try:
        with pathlib.Path(path).open(newline="") as f:
            return sorted(csv.DictReader(f), key=lambda r: r["week"])
    except OSError:
        return []


def issue_body(rows, tier, target):
    lines = [(f"The last {WEEKS} weeks each exceeded at least {NEEDED} thresholds for tier {tier} to {target} "
              "(estimates, to be calibrated: docs/decisions/0008-tiers.md)."), ""]
    for r in rows[-WEEKS:]:
        lines.append(f"- {r['week']}: {', '.join(exceeded(r, tier))} "
                     f"(lines {r['code_lines']}, modules {r['modules']}, parallel PRs {r['max_parallel_agent_prs']}, "
                     f"conflicts {r['conflicts_rebuilt'] or 'n/a'}, rounds {r['avg_review_rounds'] or 'n/a'}, "
                     f"CI {r['median_ci_minutes'] or 'n/a'} min)")
    note = (f"Proposal only: to switch, Daniel changes `.agents/tier` to `{target}` and approves the tier "
            "parts as their own issues.")
    lines += ["", note]
    return "\n".join(lines)


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main(argv) -> int:
    rows, tier = read_rows(), read_tier()
    target = propose(rows, tier)
    if not target:
        print(f"tier {tier}: no proposal")
        return 0
    title = f"Propose tier {target}"
    print(f"tier {tier}: proposing {target}")
    if "--propose" not in argv:
        print(issue_body(rows, tier, target))
        return 0
    open_ = json.loads(gh("issue", "list", "--state", "open", "--search", f'"{title}" in:title',
                          "--json", "title"))
    if any(i["title"] == title for i in open_):
        print("proposal issue already open")
        return 0
    print(gh("issue", "create", "--title", title, "--body", issue_body(rows, tier, target)).strip())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
