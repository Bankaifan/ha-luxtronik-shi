"""Create or update the issue "Weekly summary" without a model.

Sections: merged PRs of the last 7 days, PRs labelled needs-human, rule-keeper PRs,
ideas without `approved`. Also appends one row per week to docs/metrics.csv (the workflow opens a PR
for it). Needs the gh CLI (GH_TOKEN, GH_REPO).
"""
import csv
import datetime
import json
import os
import pathlib
import statistics
import subprocess
import sys

import liveness

TITLE = "Weekly summary"
METRICS = pathlib.Path("docs/metrics.csv")
COLUMNS = ["week", "code_lines", "modules", "lines_by_lang", "modules_by_lang", "max_parallel_agent_prs",
           "conflicts_rebuilt", "avg_review_rounds", "median_ci_minutes", "actions_minutes"]
LANGS = {".py": "python", ".sh": "shell", ".js": "javascript", ".ts": "typescript", ".go": "go",
         ".rs": "rust", ".java": "java", ".rb": "ruby", ".c": "c", ".h": "c", ".cpp": "cpp"}
GENERATED = ("package-lock.json", "yarn.lock", "poetry.lock", "uv.lock", "Cargo.lock", "go.sum")
GENERATED_DIRS = ("dist/", "build/", "vendor/", "node_modules/", "generated/")


def section(heading, rows):
    lines = [f"## {heading}"]
    lines += [f"- #{r['number']} {r['title']}" for r in rows] or ["- none"]
    return "\n".join(lines)


def build_body(merged, needs_human, rule_keeper, ideas, today, status_stale=False):
    parts = [f"Updated {today}.", section("Merged in the last 7 days", merged),
             section("PRs labelled needs-human", needs_human),
             section("Rule-keeper PRs", rule_keeper),
             section("Ideas waiting for approval", ideas)]
    if status_stale:
        parts.append("## Warning\n- The status run has no successful run in the last 3 hours.")
    return "\n\n".join(parts) + "\n"


def is_generated(path):
    name = path.rsplit("/", 1)[-1]
    return name in GENERATED or ".min." in name or any(path.startswith(d) or "/" + d in path for d in GENERATED_DIRS)


def count_code(files, read_lines):
    """Lines and modules (= source files) per language; generated files are skipped."""
    lines, modules = {}, {}
    for path in files:
        lang = LANGS.get(pathlib.PurePosixPath(path).suffix)
        if not lang or is_generated(path):
            continue
        lines[lang] = lines.get(lang, 0) + read_lines(path)
        modules[lang] = modules.get(lang, 0) + 1
    return lines, modules


def max_parallel(prs, week_start, week_end):
    """Max number of agent PRs open at the same time inside [week_start, week_end] (ISO strings)."""
    events = []
    for p in prs:
        if not p["headRefName"].startswith("agent/"):
            continue
        start, end = max(p["createdAt"], week_start), min(p.get("closedAt") or week_end, week_end)
        if start <= end:
            events += [(start, 1), (end, -1)]
    best = cur = 0
    for _, delta in sorted(events):  # closes (-1) sort before opens (+1) at the same time
        cur += delta
        best = max(best, cur)
    return best


def avg_review_rounds(merged):
    """Average of 1 + CHANGES_REQUESTED reviews over merged agent PRs; None without any."""
    rounds = [1 + sum(r["state"] == "CHANGES_REQUESTED" for r in p.get("reviews", []))
              for p in merged if p["headRefName"].startswith("agent/")]
    return round(sum(rounds) / len(rounds), 2) if rounds else None


def _ts(value):
    return datetime.datetime.fromisoformat(value)


def median_ci_minutes(runs):
    """Median duration in minutes of finished runs (startedAt/updatedAt ISO strings); None without runs."""
    secs = [(_ts(r["updatedAt"]) - _ts(r["startedAt"])).total_seconds()
            for r in runs if r.get("startedAt") and r.get("updatedAt") and r.get("conclusion")]
    return round(statistics.median(secs) / 60, 1) if secs else None


def fmt(by_lang):
    return ";".join(f"{k}={v}" for k, v in sorted(by_lang.items()))


def metrics_row(week, lines, modules, parallel, rounds, ci, actions):
    """One CSV row; unknown values stay empty. conflicts_rebuilt has no cheap source yet and stays empty."""
    def blank(v):
        return "" if v is None else v
    return {"week": week, "code_lines": sum(lines.values()), "modules": sum(modules.values()),
            "lines_by_lang": fmt(lines), "modules_by_lang": fmt(modules), "max_parallel_agent_prs": parallel,
            "conflicts_rebuilt": "", "avg_review_rounds": blank(rounds), "median_ci_minutes": blank(ci),
            "actions_minutes": blank(actions)}


def append_metrics(path, row):
    """Append the row unless the week is already in the file (re-runs are idempotent)."""
    path = pathlib.Path(path)
    if path.exists():
        with path.open(newline="") as f:
            if any(r["week"] == row["week"] for r in csv.DictReader(f)):
                return False
    new = not path.exists() or path.stat().st_size == 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, COLUMNS, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow(row)
    return True


def read_lines(path):
    try:
        with open(path, "rb") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def actions_minutes():
    """Actions minutes used this month if the API gives them (user billing endpoint), else None."""
    owner = os.environ.get("GH_REPO", "").split("/")[0]
    try:
        return json.loads(gh("api", f"users/{owner}/settings/billing/actions")).get("total_minutes_used")
    except (subprocess.CalledProcessError, ValueError, OSError, AttributeError):
        return None


def collect_metrics(today):
    week_end = today.isoformat() + "T23:59:59Z"
    week_start = (today - datetime.timedelta(days=7)).isoformat() + "T00:00:00Z"
    files = subprocess.run(["git", "ls-files"], check=True, capture_output=True, text=True).stdout.splitlines()
    lines, modules = count_code(files, read_lines)
    prs = json.loads(gh("pr", "list", "--state", "all", "--limit", "200",
                        "--json", "headRefName,createdAt,closedAt,mergedAt,reviews"))
    merged = [p for p in prs if p.get("mergedAt") and p["mergedAt"] >= week_start]
    runs = json.loads(gh("run", "list", "--workflow", "validate.yml", "--limit", "100",
                         "--created", ">=" + week_start[:10], "--json", "startedAt,updatedAt,conclusion"))
    return metrics_row(today.isoformat(), lines, modules, max_parallel(prs, week_start, week_end),
                       avg_review_rounds(merged), median_ci_minutes(runs), actions_minutes())


def status_stale_safe(run=gh):
    """The status-run warning; if gh cannot list the runs, skip the warning instead of aborting the summary."""
    try:
        return liveness.status_run_stale(run)
    except (subprocess.CalledProcessError, ValueError, OSError):
        return False


def main() -> int:
    today = datetime.date.today()
    since = (today - datetime.timedelta(days=7)).isoformat()
    merged = json.loads(gh("pr", "list", "--state", "merged", "--limit", "100",
                           "--search", f"merged:>={since}", "--json", "number,title"))
    human = json.loads(gh("pr", "list", "--state", "open", "--label", "needs-human", "--json", "number,title"))
    prs = json.loads(gh("pr", "list", "--state", "open", "--limit", "100", "--json", "number,title,headRefName"))
    keeper = [p for p in prs if p["headRefName"].startswith("agent/rule-keeper-")]
    ideas = [i for i in json.loads(gh("issue", "list", "--state", "open", "--label", "idea", "--limit", "100",
                                      "--json", "number,title,labels"))
             if "approved" not in {lab["name"] for lab in i["labels"]}]
    if append_metrics(METRICS, collect_metrics(today)):
        print(f"appended a row to {METRICS}")
    body = build_body(merged, human, keeper, ideas, today.isoformat(), status_stale_safe())
    found = json.loads(gh("issue", "list", "--state", "open", "--search", f'"{TITLE}" in:title',
                          "--json", "number,title"))
    found = [i for i in found if i["title"] == TITLE]
    if found:
        number = str(found[0]["number"])
        gh("issue", "edit", number, "--body", body)
        print(f"updated #{number}")
    else:
        url = gh("issue", "create", "--title", TITLE, "--body", body).strip()
        print(url)
        number = url.rsplit("/", 1)[-1]
    liveness.verify_body("issue", number, body, gh)
    return 0


def run_main() -> int:
    try:
        return main()
    except liveness.ReadbackError as e:
        print(f"read-back failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run_main())
