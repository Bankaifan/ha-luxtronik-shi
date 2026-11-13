"""Flow metrics (issue #420, no model): stage waits and counts per merged agent PR, and the status block.

Stages (minutes): dispatch (issue trusted -> agent:dev), develop (agent:dev -> PR opened), ci (PR opened -> first green
validate run), review (green CI -> first review), fix (first review -> first approval), train (approval -> merge).
Counts: fix rounds (CHANGES_REQUESTED reviews), model runs by workflow, restart:1, needs-human. A missing timestamp
leaves its stage empty. Open (carry item): train rebases, conflict fixes, denied calls, cost per PR, the two guard issues.

CLI (env GH_REPO): flow.py [CSV_PATH]   print the "Flow, last 24 h" block, write one CSV row per merged PR to CSV_PATH
"""
import csv
import datetime
import json
import statistics
import subprocess
import sys

TRUSTED_LABELS = ("approved", "auto-ok")
MODEL_WORKFLOWS = ("agent-dev", "agent-fix", "agent-review", "orchestrator", "scout", "rule-keeper")
STAGES = ("dispatch", "develop", "ci", "review", "fix", "train")
COLUMNS = ["pr", "issue", "merged_at", *(f"{s}_min" for s in STAGES), "lead_min", "fix_rounds", "model_runs",
           "runs_by_workflow", "restarts", "needs_human"]
WINDOW_H = 24


def ts(text):
    return datetime.datetime.fromisoformat(text) if text else None


def minutes(a, b):
    """Minutes from a to b (ISO strings), None if either is missing or b is before a."""
    if not a or not b:
        return None
    d = (ts(b) - ts(a)).total_seconds() / 60
    return round(d, 1) if d >= 0 else None


def issue_number(pr):
    head = pr.get("headRefName", "")
    part = head.split("/", 1)[1].split("-", 1)[0] if head.startswith("agent/") and "/" in head else ""
    return int(part) if part.isdigit() else None


def first_label_time(events, wanted):
    times = sorted(e["created_at"] for e in events
                   if e.get("event") == "labeled" and (e.get("label") or {}).get("name") in wanted)
    return times[0] if times else None


def first_green(runs):
    done = sorted(r["updatedAt"] for r in runs if r.get("workflowName") == "validate" and r.get("conclusion") == "success")
    return done[0] if done else None


def model_runs(runs):
    out = {}
    for r in runs:
        if r.get("workflowName") in MODEL_WORKFLOWS and r.get("conclusion") != "skipped":
            out[r["workflowName"]] = out.get(r["workflowName"], 0) + 1
    return out


def pr_row(pr, events, runs, issue_created=None):
    """One metrics row. pr: number, createdAt, mergedAt, headRefName, labels, reviews[{state, submittedAt}].
    events: issue events (labeled). runs: workflow runs of the PR branch (workflowName, conclusion, updatedAt)."""
    reviews = sorted(pr.get("reviews") or [], key=lambda r: r["submittedAt"])
    first_review = reviews[0]["submittedAt"] if reviews else None
    approved = next((r["submittedAt"] for r in reviews if r["state"] == "APPROVED"), None)
    trusted = first_label_time(events, TRUSTED_LABELS) or issue_created
    dev = first_label_time(events, ("agent:dev",))
    green = first_green(runs)
    waits = {"dispatch": minutes(trusted, dev), "develop": minutes(dev, pr["createdAt"]),
             "ci": minutes(pr["createdAt"], green), "review": minutes(green, first_review),
             "fix": minutes(first_review, approved), "train": minutes(approved, pr["mergedAt"])}
    by_wf = model_runs(runs)
    labels = {lab["name"] for lab in pr.get("labels") or []} | {(e.get("label") or {}).get("name") for e in events}
    row = {"pr": pr["number"], "issue": issue_number(pr) or "", "merged_at": pr["mergedAt"],
           **{f"{s}_min": "" if waits[s] is None else waits[s] for s in STAGES},
           "lead_min": minutes(trusted, pr["mergedAt"]) if trusted else "",
           "fix_rounds": sum(r["state"] == "CHANGES_REQUESTED" for r in reviews), "model_runs": sum(by_wf.values()),
           "runs_by_workflow": ";".join(f"{k}:{v}" for k, v in sorted(by_wf.items())),
           "restarts": int("restart:1" in labels), "needs_human": "yes" if "needs-human" in labels else "no"}
    row["lead_min"] = "" if row["lead_min"] is None else row["lead_min"]
    return row


def percentile(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(q * len(values)))] if values else None


def max_parallel(runs):
    """Highest number of agent runs overlapping in time (runs: createdAt, updatedAt)."""
    points = []
    for r in runs:
        if r.get("workflowName") in MODEL_WORKFLOWS and r.get("createdAt") and r.get("updatedAt"):
            points += [(ts(r["createdAt"]), 1), (ts(r["updatedAt"]), -1)]
    best = cur = 0
    for _, d in sorted(points, key=lambda p: (p[0], p[1])):
        cur += d
        best = max(best, cur)
    return best


def flow_block(rows, runs, now, hours=WINDOW_H):
    """Markdown lines for the status issue, from rows whose merged_at lies in the last `hours`."""
    recent = [r for r in rows if now - ts(r["merged_at"]) <= datetime.timedelta(hours=hours)]
    lines = [f"- merged PRs: {len(recent)}"]
    if not recent:
        return lines
    lead = [r["lead_min"] for r in recent if r["lead_min"] != ""]
    if lead:
        lines.append(f"- lead time (trusted to merge): median {statistics.median(lead):.0f} min, "
                     f"p90 {percentile(lead, 0.9):.0f} min")
    med = {s: statistics.median(v) for s in STAGES if (v := [r[f"{s}_min"] for r in recent if r[f"{s}_min"] != ""])}
    if med:
        slow = max(med, key=med.get)
        lines.append(f"- slowest stage: {slow} (median {med[slow]:.0f} min)")
    lines.append(f"- max parallel agent jobs (runs of these PRs): {max_parallel(runs)}")
    lines.append(f"- model runs per merged PR: {sum(r['model_runs'] for r in recent) / len(recent):.1f}")
    owner = sum(r["needs_human"] == "yes" for r in recent)
    lines.append(f"- needed the owner: {owner} of {len(recent)} ({100 * owner // len(recent)} %)")
    return lines


def write_csv(rows, path):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def collect(repo, run=gh, limit=30):
    """(rows, runs) for the newest merged agent PRs. Network: one call each for events and runs per PR."""
    prs = json.loads(run("pr", "list", "--state", "merged", "--limit", str(limit), "--json",
                         "number,createdAt,mergedAt,headRefName,labels,reviews"))
    rows, all_runs = [], []
    for pr in prs:
        n = issue_number(pr)
        if n is None or not pr.get("mergedAt"):
            continue
        pages = json.loads(run("api", "--paginate", "--slurp", f"repos/{repo}/issues/{n}/events"))
        events = [e for page in pages for e in page]
        runs = json.loads(run("run", "list", "--branch", pr["headRefName"], "--limit", "50", "--json",
                              "workflowName,conclusion,createdAt,updatedAt"))
        rows.append(pr_row(pr, events, runs))
        all_runs += runs
    return rows, all_runs


def main(argv, env, now=None):
    now = now or datetime.datetime.now(datetime.UTC)
    rows, runs = collect(env["GH_REPO"])
    if len(argv) > 1:
        write_csv(rows, argv[1])
    print("\n".join(flow_block(rows, runs, now)))
    return 0


if __name__ == "__main__":
    import os
    sys.exit(main(sys.argv, os.environ))
