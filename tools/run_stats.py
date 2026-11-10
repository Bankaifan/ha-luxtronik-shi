"""Quota baseline (design 0007, section 4.7): model runs per day of the orchestrator workflow.

A run counts as a model run when its conclusion is not `skipped` and a job step named like `claude` ran
(step conclusion not `skipped`, from the jobs API). Runs with conclusion `skipped` are gate-skipped runs.

CLI (env: GH_REPO optional): run_stats.py [DAYS (default 14)] [WORKFLOW_FILE (default orchestrator.yml)]
"""
import datetime
import json
import pathlib
import re
import statistics
import sys

import liveness

WORKFLOW = "orchestrator.yml"
LIMIT = 1000
CLAUDE_MARK = "claude-code-action"
# Heuristic (design 0014): a failed run whose failed-step log mentions a limit or rate error. Not a guarantee.
LIMIT_RE = re.compile(r"rate.?limit|usage limit|too many requests|\b429\b", re.IGNORECASE)
ROLES = {"orchestrator.yml": "orchestrator", "agent-dev.yml": "dev", "agent-fix.yml": "fix",
         "agent-review.yml": "review", "agent-security-review.yml": "security review", "scout.yml": "scout",
         "unblocker.yml": "unblocker", "answer-receiver.yml": "answer receiver", "rule-keeper.yml": "rule keeper"}


def parse_time(text):
    return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.UTC)


def ran_model(jobs):
    """True if any step whose name contains `claude` was not skipped."""
    for job in jobs:
        for step in job.get("steps") or []:
            if "claude" in str(step.get("name", "")).lower() and step.get("conclusion") not in (None, "skipped"):
                return True
    return False


def stats(runs, jobs_of, days=14, now=None):
    """runs: dicts with conclusion, createdAt, databaseId. jobs_of(run_id) -> list of jobs.
    Returns {"days", "model_runs", "gate_skipped", "per_day": {date: model runs}}."""
    now = now or datetime.datetime.now(datetime.UTC)
    cutoff = now - datetime.timedelta(days=days)
    per_day, skipped = {}, 0
    for run in runs:
        created = parse_time(run["createdAt"])
        if created < cutoff:
            continue
        if run.get("conclusion") == "skipped":
            skipped += 1
        elif ran_model(jobs_of(run["databaseId"])):
            day = created.date().isoformat()
            per_day[day] = per_day.get(day, 0) + 1
    total = sum(per_day.values())
    return {"days": days, "model_runs": total, "gate_skipped": skipped, "per_day": dict(sorted(per_day.items()))}


def format_stats(result):
    lines = [f"Model runs per day, last {result['days']} days:"]
    lines += [f"  {d}: {n}" for d, n in result["per_day"].items()]
    lines.append(f"Model runs: {result['model_runs']}, gate-skipped runs: {result['gate_skipped']}")
    lines.append(f"Model runs per day (average): {result['model_runs'] / result['days']:.2f}")
    return "\n".join(lines)


def jobs_getter(repo, run):
    slug = repo or "{owner}/{repo}"

    def jobs_of(run_id):
        return json.loads(run("api", f"repos/{slug}/actions/runs/{run_id}/jobs", "--paginate",
                              "--jq", "{jobs: .jobs}")).get("jobs", [])
    return jobs_of


def fetch(workflow=WORKFLOW, repo=None, run=liveness.gh):
    base = ["--repo", repo] if repo else []
    runs = json.loads(run("run", "list", "--workflow", workflow, *base, "--limit", str(LIMIT),
                          "--json", "databaseId,conclusion,createdAt"))
    return runs, jobs_getter(repo, run)


def claude_workflows(directory=".github/workflows"):
    """Workflow file names (not paths) whose YAML uses claude-code-action, i.e. have a model step."""
    return sorted(p.name for p in pathlib.Path(directory).glob("*.yml")
                  if CLAUDE_MARK in p.read_text(encoding="utf-8"))


def fetch_all(files, since, repo=None, run=liveness.gh):
    """Runs of each workflow file created on or after `since` (YYYY-MM-DD), with a jobs and a failed-log getter."""
    base = ["--repo", repo] if repo else []
    fields = "databaseId,conclusion,createdAt,startedAt,updatedAt"
    runs = {f: json.loads(run("run", "list", "--workflow", f, *base, "--created", f">={since}",
                              "--limit", str(LIMIT), "--json", fields)) for f in files}

    def log_of(run_id):
        return run("run", "view", str(run_id), *base, "--log-failed")
    return runs, jobs_getter(repo, run), log_of


def workflow_stats(runs, jobs_of, log_of, days=7, now=None):
    """Model runs of one workflow in the last `days` days (same rule as stats()). Failed-log text is read only
    for failed model runs. median_min: median duration of model runs (None without timestamps)."""
    now = now or datetime.datetime.now(datetime.UTC)
    cutoff = now - datetime.timedelta(days=days)
    per_day, durations, failed, limit_failed = {}, [], 0, 0
    for run in runs:
        created = parse_time(run["createdAt"])
        if created < cutoff or run.get("conclusion") == "skipped" or not ran_model(jobs_of(run["databaseId"])):
            continue
        day = created.date().isoformat()
        per_day[day] = per_day.get(day, 0) + 1
        if run.get("startedAt") and run.get("updatedAt"):
            durations.append((parse_time(run["updatedAt"]) - parse_time(run["startedAt"])).total_seconds())
        if run.get("conclusion") == "failure":
            failed += 1
            limit_failed += bool(LIMIT_RE.search(log_of(run["databaseId"])))
    return {"days": days, "model_runs": sum(per_day.values()), "per_day": dict(sorted(per_day.items())),
            "failed": failed, "limit_failed": limit_failed,
            "median_min": round(statistics.median(durations) / 60, 1) if durations else None}


ERROR_RE = re.compile(r"error|exception|failed", re.IGNORECASE)
STAMP_RE = re.compile(r"^\d{4}-\d\d-\d\dT[\d:.]+Z\s*")


def failure_class(log):
    """Normalized first error line of a failed model run (digits become #), or None. Limit or rate errors are not a
    role failure and give None. Heuristic (design 0015): same text = same class."""
    if LIMIT_RE.search(log):
        return None
    for line in log.splitlines():
        text = STAMP_RE.sub("", line.rsplit("\t", 1)[-1]).strip()
        if ERROR_RE.search(text):
            return re.sub(r"\d+", "#", text.lower())[:120]
    return None


def failure_classes(runs, jobs_of, log_of, days=28, now=None):
    """{failure class: number of failed model runs in the last `days` days}; runs: {workflow file: run list}."""
    now = now or datetime.datetime.now(datetime.UTC)
    cutoff = now - datetime.timedelta(days=days)
    counts = {}
    for file_runs in runs.values():
        for run in file_runs:
            if parse_time(run["createdAt"]) < cutoff or run.get("conclusion") != "failure":
                continue
            if not ran_model(jobs_of(run["databaseId"])):
                continue
            cls = failure_class(log_of(run["databaseId"]))
            if cls:
                counts[cls] = counts.get(cls, 0) + 1
    return counts


def main(argv):
    import os
    days = int(argv[1]) if len(argv) > 1 else 14
    workflow = argv[2] if len(argv) > 2 else WORKFLOW
    runs, jobs_of = fetch(workflow, os.environ.get("GH_REPO"))
    print(format_stats(stats(runs, jobs_of, days)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
