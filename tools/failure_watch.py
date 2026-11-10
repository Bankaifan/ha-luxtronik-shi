"""Failure watch (design 0008, sections 4.1-4.5): one signed guard issue per failing workflow signature.

collect failed runs -> signature (workflow / job / step names) -> dedup by title -> flood cap -> priority ->
auto-close when green again (also stale `Overdue scheduled run` issues) -> reopen with a counter -> needs-human at
Reopened: 3. The issue is the state: counters live in its signed body. Bodies are fixed script text, never log text.
Not called by anything yet (wiring is a later PR). Needs the gh CLI (GH_TOKEN, GH_REPO) and GUARD_KEY.
"""
import datetime
import json
import re

import decision
import guard_mark
import liveness
from agent_guard import add_labels

TITLE_PREFIX = "Failing workflow: "
MAX_NEW = 5
MAX_PAGES = 3
MAX_BACK = datetime.timedelta(hours=24)
OVERLAP = datetime.timedelta(minutes=5)
KEPT = ("failure", "timed_out", "startup_failure")
FAILED_JOB = ("failure", "timed_out")
MERGE_GATES = ("validate.yml", "risk.yml", "agent-security-review.yml")
PR_ONLY = ("risk.yml", "agent-security-review.yml", "agent-review.yml")  # green on any non-agent ref counts
AGENT_OWNED = ("validate.yml", "agent-review.yml")  # failures on agent/* branches belong to agent-fix rounds
SELF = "status.yml"
ESCALATE_AT = 3
PART_MAX = 60
_BAD = re.compile(r"[^A-Za-z0-9 ._:/()-]")
_FIELD = re.compile(r"^(Failures|Reopened|Last run|Closed by): (.*)$", re.MULTILINE)


def _api(path, run):
    return json.loads(run("api", path))


def clean(part):
    return _BAD.sub("_", (part or "").strip())[:PART_MAX] or "-"


def workflow_file(run_obj):
    return (run_obj.get("path") or "").rsplit("/", 1)[-1]


def run_url(run_obj):
    return run_obj.get("html_url") or ""


def keep(run_obj):
    """Section 4.1 filter: only real failures, not the status run, not forks, not agent-owned branches."""
    wf = workflow_file(run_obj)
    if run_obj.get("conclusion") not in KEPT or wf == SELF:
        return False
    if (run_obj.get("head_repository") or {}).get("fork"):
        return False
    return not (wf in AGENT_OWNED and (run_obj.get("head_branch") or "").startswith("agent/"))


def collect(since, now, run=liveness.gh):
    """Kept failed runs completed since SINCE (minus overlap, at most 24h back), oldest first."""
    start = max(since - OVERLAP, now - MAX_BACK)
    found = []
    for page in range(1, MAX_PAGES + 1):
        path = (f"repos/{{owner}}/{{repo}}/actions/runs?created=%3E%3D{start:%Y-%m-%dT%H:%M:%SZ}"
                f"&status=completed&per_page=100&page={page}")
        runs = _api(path, run).get("workflow_runs") or []
        found += runs
        if len(runs) < 100:
            break
    return sorted((r for r in found if keep(r)), key=lambda r: r["id"])


def signature(run_obj, run=liveness.gh):
    """`<workflow file> / <job> / <step>`; the names come from workflow files, not from logs, and are sanitised."""
    jobs = _api(f"repos/{{owner}}/{{repo}}/actions/runs/{run_obj['id']}/jobs", run).get("jobs") or []
    job = next((j for j in jobs if j.get("conclusion") in FAILED_JOB), None)
    step = next((s for s in (job or {}).get("steps") or [] if s.get("conclusion") in FAILED_JOB), None)
    return " / ".join(clean(p) for p in (workflow_file(run_obj), (job or {}).get("name"), (step or {}).get("name")))


def title_for(sig):
    return TITLE_PREFIX + sig


def priority(sig, branch, failures):
    wf = sig.split(" / ")[0]
    gate = wf in MERGE_GATES and (wf != "validate.yml" or branch == "main")
    return "prio:1" if failures >= 3 or gate else "prio:2"


# --- body = state -------------------------------------------------------------------------------

def make_body(sig, failures, last_url, closed_by="none", reopened=0):
    wf, job, step = sig.split(" / ")
    lines = [f"The workflow {wf} failed in job {job}, step {step}.", f"Failures: {failures}", f"Last run: {last_url}"]
    if reopened:
        lines.append(f"Reopened: {reopened}")
    lines.append(f"Closed by: {closed_by}")
    return "\n".join(lines)


def parse_body(body):
    f = dict(_FIELD.findall(guard_mark.split(body)[0]))
    last = re.search(r"/runs/(\d+)", f.get("Last run", ""))
    return {"failures": int(f.get("Failures", "")) if f.get("Failures", "").isdigit() else 0,
            "reopened": int(f.get("Reopened", "")) if f.get("Reopened", "").isdigit() else 0,
            "last_url": f.get("Last run", ""), "closed_by": f.get("Closed by", "none"),
            "last_id": int(last.group(1)) if last else 0}


def load_issues(key, run=liveness.gh):
    """{title: issue} of signature-verified failure issues (open and closed). Unverified ones are ignored."""
    found = json.loads(run("issue", "list", "--state", "all", "--search", f'"{TITLE_PREFIX.strip()}" in:title',
                           "--limit", "200", "--json", "number,title,state,body,labels,closedAt,updatedAt"))
    return {i["title"]: i for i in found
            if i["title"].startswith(TITLE_PREFIX) and guard_mark.verify(i["title"], i["body"], key)}


def _write(issue, body, key, run):
    """Re-sign and store the body, read it back; keep the in-memory issue current."""
    signed = guard_mark.sign(issue["title"], body, key)
    run("issue", "edit", str(issue["number"]), "--body", signed)
    liveness.verify_body("issue", issue["number"], signed, run)
    issue["body"] = signed


def _set_prio(issue, want, run):
    have = {lb["name"] for lb in issue.get("labels") or []}
    if want not in have:
        add_labels("issue", issue["number"], [want], run)
        issue["labels"] = [*(issue.get("labels") or []), {"name": want}]
    if want == "prio:1" and "prio:2" in have:
        run("issue", "edit", str(issue["number"]), "--remove-label", "prio:2")


def _fix_pr(number, run):
    """URL of the PR that closed the issue (timeline `closed` event -> commit -> PR), or `none`."""
    try:
        events = _api(f"repos/{{owner}}/{{repo}}/issues/{number}/timeline", run)
        sha = next((e["commit_id"] for e in reversed(events) if e.get("event") == "closed" and e.get("commit_id")), None)
        pulls = _api(f"repos/{{owner}}/{{repo}}/commits/{sha}/pulls", run) if sha else []
        return pulls[0]["html_url"] if pulls else "none"
    except Exception:  # noqa: BLE001 - an unknown PR must never stop the watch
        return "none"


def escalate(issue, run):
    """needs-human once, with the German yes/no note of AGENTS.md (last comment, hidden decision marker)."""
    if any(lb["name"] == "needs-human" for lb in issue.get("labels") or []):
        return
    add_labels("issue", issue["number"], ["needs-human"], run)
    issue["labels"] = [*(issue.get("labels") or []), {"name": "needs-human"}]
    note = ("Dieser Fehler im Workflow ist nach zwei Reparaturen zum dritten Mal wieder aufgetreten. "
            "Schlimmster Fall: der Workflow bleibt kaputt und blockiert Aenderungen. "
            "Frage: Soll der Agent es noch einmal versuchen? "
            "Ja = Aufgabe wird neu gestartet, Nein = Issue wird geschlossen.\n"
            + decision.build(yes="restart-issue", no="close-issue"))
    liveness.post_comment("issue", issue["number"], note, run)


# --- the three outcomes of a failing run -----------------------------------------------------------

def _create(sig, run_obj, key, run):
    title = title_for(sig)
    body = guard_mark.sign(title, make_body(sig, 1, run_url(run_obj)), key)
    out = run("issue", "create", "--title", title, "--label", priority(sig, run_obj.get("head_branch"), 1), "--body", body)
    return {"number": int(out.strip().rsplit("/", 1)[-1]), "title": title, "state": "OPEN", "body": body,
            "labels": [{"name": priority(sig, run_obj.get("head_branch"), 1)}]}


def _recur(issue, sig, run_obj, key, run):
    """Failure of a known signature: bump the counter; a closed issue is reopened (Reopened + 1, fix PR linked)."""
    st = parse_body(issue["body"])
    failures, reopened, closed_by = st["failures"] + 1, st["reopened"], st["closed_by"]
    action = "updated"
    if issue["state"] != "OPEN":
        reopened, action = reopened + 1, "reopened"
        closed_by = _fix_pr(issue["number"], run)
        run("issue", "reopen", str(issue["number"]))
        issue["state"] = "OPEN"
        liveness.post_comment("issue", issue["number"],
                              f"Same failure again after the fix in {closed_by}: {run_url(run_obj)}.", run)
    _write(issue, make_body(sig, failures, run_url(run_obj), closed_by, reopened), key, run)
    _set_prio(issue, priority(sig, run_obj.get("head_branch"), failures), run)
    if reopened >= ESCALATE_AT and action == "reopened":
        escalate(issue, run)
    return action


def _success_closes(issue, run):
    """URL of a newer green run of the same workflow whose job of the signature succeeded, else None."""
    wf, job, _ = issue["title"][len(TITLE_PREFIX):].split(" / ")
    last_id = parse_body(issue["body"])["last_id"]
    runs = json.loads(run("run", "list", "--workflow", wf, "--limit", "5",
                          "--json", "conclusion,url,headBranch,databaseId"))
    for r in runs:
        branch = r.get("headBranch") or ""
        ok = branch == "main" or (wf in PR_ONLY and not branch.startswith("agent/"))
        if r["conclusion"] != "success" or r["databaseId"] <= last_id or not ok:
            continue
        jobs = _api(f"repos/{{owner}}/{{repo}}/actions/runs/{r['databaseId']}/jobs", run).get("jobs") or []
        if any(clean(j.get("name")) == job and j.get("conclusion") == "success" for j in jobs):
            return r["url"]
    return None


def _close(issue, comment, run):
    liveness.post_comment("issue", issue["number"], comment, run)
    run("issue", "close", str(issue["number"]))
    issue["state"] = "CLOSED"


def auto_close(issues, touched, key, run=liveness.gh):
    """Close open failure issues whose job is green again. TOUCHED: titles that failed in this tick (kept open)."""
    closed = []
    for issue in issues.values():
        if issue["state"] != "OPEN" or issue["title"] in touched:
            continue
        url = _success_closes(issue, run)
        if url:
            sig = issue["title"][len(TITLE_PREFIX):]
            st = parse_body(issue["body"])
            _write(issue, make_body(sig, st["failures"], st["last_url"], url, st["reopened"]), key, run)
            _close(issue, f"Closed by the failure watch: {url} succeeded.", run)
            closed.append(issue["number"])
    return closed


def close_overdue(overdue_labels, key, run=liveness.gh):
    """Close signed `Overdue scheduled run: <label>` issues whose workflow is not overdue any more."""
    closed = []
    for label, _interval in liveness.SCHEDULED.values():
        if label in overdue_labels:
            continue
        title = liveness.overdue_title(label)
        found = json.loads(run("issue", "list", "--state", "open", "--search", f'"{title}" in:title',
                               "--json", "number,title,body"))
        for issue in found:
            if issue["title"] == title and guard_mark.verify(title, issue["body"], key):
                _close(issue, "Closed by the failure watch: the scheduled run is current again.", run)
                closed.append(issue["number"])
    return closed


def watch(since, now, overdue_labels, key=None, run=liveness.gh):
    """One tick. Returns (actions, next_since). Without GUARD_KEY nothing is verifiable, so nothing is done."""
    key = guard_mark.key_from_env() if key is None else key
    if not key:
        return [], since
    issues = load_issues(key, run)
    actions, touched, deferred, new = [], set(), [], 0
    handled = since
    for r in collect(since, now, run):
        sig = signature(r, run)
        title = title_for(sig)
        issue = issues.get(title)
        created = datetime.datetime.fromisoformat(r["created_at"])
        if issue and parse_body(issue["body"])["last_id"] >= r["id"]:
            touched.add(title)
            continue
        if issue is None:
            if new >= MAX_NEW:
                deferred.append(created)
                continue
            issues[title] = issue = _create(sig, r, key, run)
            new += 1
            actions.append(f"opened failure issue #{issue['number']}")
        else:
            actions.append(f"{_recur(issue, sig, r, key, run)} failure issue #{issue['number']}")
        touched.add(title)
        handled = max(handled, created)
    actions += [f"closed failure issue #{n}" for n in auto_close(issues, touched, key, run)]
    actions += [f"closed overdue issue #{n}" for n in close_overdue(overdue_labels, key, run)]
    if deferred:
        actions.append(f"failure watch: {len(deferred)} signatures deferred")
    return actions, min(deferred) if deferred else handled
