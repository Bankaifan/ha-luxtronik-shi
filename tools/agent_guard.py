"""Shared helpers for the agent workflows: login normalization, labels that always exist, silent-run guard.

CLI (needs the gh CLI with GH_TOKEN and GH_REPO):
  agent_guard.py login LOGIN                 print the normalized login
  agent_guard.py same A B                    exit 0 if both logins name the same account
  agent_guard.py label pr|issue N LABEL...   create each label if missing, then add it
  agent_guard.py agent-pr AUTHOR [LABELS]    exit 0 if the PR is an agent PR (env AUTHOR_BOT, OWNER; LABELS comma list)
  agent_guard.py reviewed PR SHA [BODYHASH]  exit 0 if the approver app (env APPROVER_BOT) reviewed SHA (and BODYHASH)
  agent_guard.py body-hash PR                print the hash of the PR body (the reviewer repeats it as `body-hash: H`)
  agent_guard.py refund PR SHA               give the round of SHA back if the approver app (env APPROVER_BOT) approved it
  agent_guard.py form-failure RUN_ID         exit 0 if the failed validate run failed on PR form or VERSION/CHANGELOG only (no round)
  agent_guard.py silent dev ISSUE SINCE     after agent-dev: no PR for agent/ISSUE-* created at/after SINCE (UTC ISO) -> escalate
  agent_guard.py silent fix PR HEAD_BEFORE [BODY_FILE]
                                             after agent-fix: PR head and body (BODY_FILE = body before the run) unchanged -> escalate
  agent_guard.py silent review PR SHA [BODYHASH]
                                             after agent-review: no approver review for SHA (and BODYHASH) -> escalate
  agent_guard.py silent orchestrator - SINCE after the orchestrator model step: denials, or STARTABLE=true and no visible action
                                             by AUTHOR_BOT since SINCE -> comment on STATUS_ISSUE (default 57), exit 1; 2nd in 24 h -> prio:1 issue
  agent_guard.py park pr|issue N YES NO TEXT post the German owner note with a decision marker (YES/NO = action id or -)
`silent` ignores extra trailing arguments (the guard runs from main, the workflow from the PR branch: no version drift).
A usage error or exception in `silent` escalates with reason "guard error" and exits 1; it never fails quietly.
Escalate = comment (run URL, denied tool calls from the execution file, else its last lines), label needs-human, request OWNER's review.
Environment for escalation: RUN_URL, EXEC_FILE (path of the action's execution file), OWNER (default Bankaifan).
An allow-list miss on an issue (a denied call that is not a protected path) becomes ONE signed issue in the template repo
(route_upstream) and the issue waits with `Depends on:` instead of needs-human. Needs GUARD_KEY (script step only).
"""
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys

import decision
import guard_mark
import liveness
import owner_hold

# Execution-file helpers live in exec_log.py; re-exported here so `agent_guard.X` keeps working.
from exec_log import (  # noqa: F401
    _SECRET,
    MAX_DENIALS,
    TAIL_CHARS,
    TAIL_LINES,
    _records,
    count_denials,
    denied_calls,
    read_exec,
    tail_text,
)

OWNER_DEFAULT = "Bankaifan"
DENIAL_RE = re.compile(r"<!-- denied-run sig=([0-9a-f]{16}|none) -->")  # hidden line of every denial note
RECEIVER_RE = re.compile(r"<!-- answer-receiver comment=(\d+)")  # receiver confirmations name the owner comment they answer
PROTECTED = ("CODEOWNERS", "claude-judge-settings.json")  # a retrigger never changes these
ALLOW_FILES = {"dev": (".github/workflows/agent-dev.yml", ".agents/roles/developer.md"),
               "fix": (".github/workflows/agent-fix.yml", ".agents/roles/developer.md"),
               "review": (".github/workflows/agent-review.yml", ".agents/roles/reviewer.md")}
CAP_LABELS = ("restart:1", "unblock:1")  # the same call denied twice: no automatic restart any more
TOOL_RE = re.compile(r"[A-Za-z]{1,20}")  # only harness tool names reach an upstream issue, never model text
WORKFLOW_NAME = {"dev": "agent-dev", "fix": "agent-fix", "review": "agent-review"}  # fixed names of the workflow files
UPSTREAM_CAP = 5  # open denied-command issues per workflow in the template repo
REPO_RE = re.compile(r"[\w.-]+/[\w.-]+")


def norm_login(login):
    """`app/x`, `x[bot]` and `x` all name the same account; compare case-insensitively."""
    s = (login or "").strip()
    s = s.removeprefix("app/")
    s = s.removesuffix("[bot]")
    return s.lower()


def same_login(a, b):
    na = norm_login(a)
    return bool(na) and na == norm_login(b)


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def ensure_label(name, run=gh):
    """Create the label if missing. A failure is not fatal: the label may exist and the add will tell."""
    try:
        run("label", "create", name, "--force")
    except (subprocess.CalledProcessError, OSError):
        pass


def add_labels(kind, number, labels, run=gh):
    """Add labels (created first). `needs-human` and `review:N` that OWNER removed are not set again (owner_hold):
    one comment says so, the rest of the labels are still added."""
    refused = owner_hold.held(kind, number, labels, run)
    if refused:
        liveness.post_comment(kind, number, f"Daniel removed {', '.join(refused)}; not set again for this head.", run)
    labels = [name for name in labels if name not in refused]
    for name in labels:
        ensure_label(name, run)
    if labels:
        run(kind, "edit", str(number), *[a for name in labels for a in ("--add-label", name)])


def count_round(number, sha, run=gh):
    """One review round per head SHA, shared by both reviewers. Marker label `round:<sha7>` (older markers are removed).
    Returns "already" (this head was counted), "limit" (review:3 is set, nothing bumped), "held" (OWNER removed that
    review label, nothing bumped) or "counted" (review:N bumped)."""
    labels = set(run("pr", "view", str(number), "--json", "labels", "--jq", ".labels[].name").split())
    mark = f"round:{sha[:7]}"
    if mark in labels:
        return "already"
    if "review:3" in labels:
        return "limit"
    nxt = "review:3" if "review:2" in labels else "review:2" if "review:1" in labels else "review:1"
    if owner_hold.held("pr", number, [nxt], run):
        add_labels("pr", number, [nxt], run)  # refuses and comments
        return "held"
    add_labels("pr", number, [nxt, mark], run)
    for old in sorted(n for n in labels if n.startswith("round:")):
        try:
            run("pr", "edit", str(number), "--remove-label", old)
        except (subprocess.CalledProcessError, OSError):
            pass
    return "counted"


def reviews_of(pr, run=gh):
    pages = json.loads(run("api", "--paginate", "--slurp", f"repos/{os.environ['GH_REPO']}/pulls/{pr}/reviews"))
    return [r for page in pages for r in page]


def refund_round(number, sha, approver, run=gh):
    """A round counts only for a finding. The reviewer counts a head before it reviews; when the approver app's latest
    review of that head is APPROVED, the round is given back (label review:N lowered, marker removed).
    Returns "refunded", "kept" (no approval of this head) or "none" (this head was not counted)."""
    labels = set(run("pr", "view", str(number), "--json", "labels", "--jq", ".labels[].name").split())
    mark = f"round:{sha[:7]}"
    if mark not in labels:
        return "none"
    mine = [r for r in reviews_of(number, run) if r.get("commit_id") == sha
            and same_login((r.get("user") or {}).get("login"), approver)]
    if not mine or mine[-1].get("state") != "APPROVED":
        return "kept"
    if "risk:security" in labels:  # the security verdict comes from a separate run; without its approve keep the round
        import approval  # imports agent_guard itself: load it here, not at module level

        pages = json.loads(run("api", "--paginate", "--slurp", f"repos/{os.environ['GH_REPO']}/issues/{number}/comments"))
        if approval.security_verdict([c for page in pages for c in page], sha, approver) != "approve":
            return "kept"
    cur = next((n for n in ("review:3", "review:2", "review:1") if n in labels), None)
    if cur:  # the labels accumulate (review:2 implies review:1): the highest one is this head's round
        run("pr", "edit", str(number), "--remove-label", cur)
    run("pr", "edit", str(number), "--remove-label", mark)
    return "refunded"


# Failing lines of the form checks (PR title/body, VERSION/CHANGELOG): no round; agent-fix gives the first one per PR a fix run.
_FORM_FAIL = re.compile(r"check_(?:pr_form|version_bump|version):\s+(?!ok\b|skipped\b|cannot run\b)")


def form_failure(log):
    """True if the failed validate log shows a PR-form or version/changelog failure (not a defect in the diff)."""
    return bool(_FORM_FAIL.search(log or ""))


def is_form_failure(run_id, run=gh):
    """Unknown (log unreadable) is not a form failure: the red CI counts as a round, as before."""
    try:
        return form_failure(run("run", "view", str(run_id), "--log-failed"))
    except (subprocess.CalledProcessError, OSError):
        return False


def settled(view, comments, approver):
    """The PR is green and approved by the reviewers at its head: `view` is `gh pr view --json
    reviewDecision,labels,headRefOid,statusCheckRollup`. A risk:security PR also needs the security `approve`."""
    import approval  # late: approval imports this module
    checks = view.get("statusCheckRollup") or []
    states = [(c.get("conclusion") or c.get("state") or "").upper() for c in checks]
    green = bool(states) and all(s in ("SUCCESS", "NEUTRAL", "SKIPPED") for s in states)
    labels = {x["name"] for x in view.get("labels", [])}
    sha = view.get("headRefOid", "")
    if not (green and approval.effective_approval(view.get("reviewDecision"), labels, comments, sha, approver)):
        return False
    return "risk:security" not in labels or approval.security_verdict(comments, sha, approver) == "approve"


def is_settled(number, approver, run=gh):
    """Read failures count as not settled: the silent run then escalates as before."""
    try:
        view = json.loads(run("pr", "view", str(number), "--json", "reviewDecision,labels,headRefOid,statusCheckRollup"))
        pages = json.loads(run("api", "--paginate", "--slurp",
                               f"repos/{os.environ['GH_REPO']}/issues/{number}/comments") or "[]")
        comments = [c for p in pages for c in (p if isinstance(p, list) else [p])]
        return settled(view, comments, approver)
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError):
        return False


def is_stale_head(number, sha, run=gh):
    """True if the PR head is known and no longer SHA. Unknown (lookup failed) is not stale: fail open."""
    try:
        head = run("pr", "view", str(number), "--json", "headRefOid", "--jq", ".headRefOid").strip()
    except (subprocess.CalledProcessError, OSError):
        return False
    return bool(head) and not head.startswith(sha) and not sha.startswith(head)


def is_agent_pr(author, labels, author_bot, owner):
    """Own-branch PRs by the author app or by the owner's account are reviewed; others only with agent:review."""
    return same_login(author, author_bot) or same_login(author, owner) or "agent:review" in labels


_BODY_HASH_LINE = re.compile(r"^\s*body-hash:\s*([0-9a-f]{8,64})\s*$", re.IGNORECASE | re.MULTILINE)


def body_hash(body):
    """Short hash of the PR body (surrounding whitespace ignored); gh adds a trailing newline."""
    return hashlib.sha256((body or "").strip().encode("utf-8")).hexdigest()[:16]


def has_review(reviews, approver, sha, bhash=None):
    """Approver review of SHA. With BHASH, a review that names another `body-hash:` is stale (the body was edited
    after it); a review without that line falls back to the SHA-only key, so it is never repeated endlessly."""
    for r in reviews:
        if r.get("commit_id") != sha or not same_login((r.get("user") or {}).get("login"), approver):
            continue
        m = _BODY_HASH_LINE.search(r.get("body") or "")
        if not bhash or not m or m.group(1).lower() == bhash:
            return True
    return False


def dev_has_pr(prs, issue, since):
    """A PR for agent/ISSUE-* created by this run: createdAt >= SINCE (same UTC ISO format, compares as text).
    Older PRs for the same issue number, open or closed, must not hide a silent run."""
    prefix = f"agent/{issue}-"
    return any(p.get("headRefName", "").startswith(prefix) and p.get("createdAt", "") >= since for p in prs)


def head_moved(before, after):
    return bool(after) and after != before


def fix_produced(head_before, head_after, body_before, body_after):
    """A fix run is not silent if the head moved or (body-only fix) the PR body changed since the run started."""
    if head_moved(head_before, head_after):
        return True
    return body_before is not None and body_hash(body_before) != body_hash(body_after)


def _after(ts, since):
    return (ts or "") >= since  # same UTC ISO format, compares as text


def visible_action(author_bot, since, events=(), comments=(), prs=(), issues=()):
    """Did the author app label, comment, open an issue or a PR at/after SINCE?"""
    return (any(same_login((e.get("actor") or {}).get("login"), author_bot) and _after(e.get("created_at"), since)
                for e in events)
            or any(same_login((c.get("user") or {}).get("login"), author_bot) and _after(c.get("created_at"), since)
                   for c in comments)
            or any(same_login((x.get("author") or {}).get("login"), author_bot) and _after(x.get("createdAt"), since)
                   for x in [*prs, *issues]))


def orchestrator_silent(denials, startable, acted):
    """Reason the orchestrator run counts as silent, else None. Nothing startable and no denials is fine."""
    if denials > 0:
        return f"{denials} tool call(s) were denied"
    if startable and not acted:
        return "a startable issue existed but no label, comment, issue or PR followed"
    return None


ORCH_MARK = "agent-orchestrator run finished silently"
ORCH_REPEAT_TITLE = "Orchestrator runs keep ending silently"


def recent_failures(comments, author_bot, since):
    return sum(1 for c in comments if same_login((c.get("user") or {}).get("login"), author_bot)
               and _after(c.get("created_at"), since) and ORCH_MARK in (c.get("body") or ""))


def escalate_orchestrator(why, status_issue, repo, author_bot, run=gh, now=None):
    """Comment on the status issue (run URL, denied calls). Second failure within 24 h: one prio:1 issue, no duplicates."""
    now = now or dt.datetime.now(dt.UTC)
    day_ago = (now - dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pages = json.loads(run("api", "--paginate", "--slurp",
                           f"repos/{repo}/issues/{status_issue}/comments?since={day_ago}"))
    earlier = recent_failures([c for p in pages for c in p], author_bot, day_ago)
    body = report("orchestrator", why, os.environ.get("RUN_URL", ""), read_exec(os.environ.get("EXEC_FILE", "")))
    body = body.split("Labelled needs-human")[0] + "The run is marked failed."  # no needs-human here: the status issue is not a task
    liveness.post_comment("issue", status_issue, body, run)
    if earlier:
        open_ = json.loads(run("issue", "list", "--state", "open", "--search", f'"{ORCH_REPEAT_TITLE}" in:title',
                               "--json", "title"))
        if not any(i.get("title") == ORCH_REPEAT_TITLE for i in open_):
            ensure_label("prio:1", run)
            run("issue", "create", "--title", ORCH_REPEAT_TITLE, "--label", "prio:1", "--body",
                f"The orchestrator ended silently {earlier + 1} times within 24 h (latest: {why}). "
                f"Details: comments on #{status_issue}, run {os.environ.get('RUN_URL', '(unknown)')}.")


def silent_orchestrator(since, run=gh):
    """Check after the orchestrator model step. Returns 1 (run must fail) if it was silent."""
    repo, bot = os.environ["GH_REPO"], os.environ.get("AUTHOR_BOT", "")
    denials = count_denials(read_exec(os.environ.get("EXEC_FILE", "")))
    startable = os.environ.get("STARTABLE") == "true"
    acted = False
    if denials == 0 and startable:
        events = json.loads(run("api", f"repos/{repo}/issues/events?per_page=100"))
        pages = json.loads(run("api", "--paginate", "--slurp", f"repos/{repo}/issues/comments?since={since}&per_page=100"))
        prs = json.loads(run("pr", "list", "--state", "all", "--limit", "50", "--json", "author,createdAt"))
        issues = json.loads(run("issue", "list", "--state", "all", "--limit", "50", "--json", "author,createdAt"))
        acted = visible_action(bot, since, events, [c for p in pages for c in p], prs, issues)
    why = orchestrator_silent(denials, startable, acted)
    if not why:
        return 0
    escalate_orchestrator(why, os.environ.get("STATUS_ISSUE", "57"), repo, bot, run)
    return 1


def report(kind, what, run_url, exec_text):
    denied = denied_calls(exec_text) if exec_text else []
    if denied:
        detail = "Denied tool calls:\n```\n" + "\n".join(denied) + "\n```\n"
    else:
        tail = tail_text(exec_text) if exec_text else "(no execution file)"
        detail = f"Last lines of the execution file (no denied tool calls found):\n```\n{tail}\n```\n"
    return (f"agent-{kind} run finished silently: {what}.\n\nRun: {run_url or '(unknown)'}\n\n{detail}"
            "Labelled needs-human; Daniel is asked to look at it.")


def read_body_before(path):
    """PR body saved before a fix run. None if missing or unreadable: unknown, not an empty body."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, TypeError):
        return None


def denial_sig(exec_text):
    """Hash of the denied calls of a run (masked, as reported); "none" if the run was denied nothing."""
    lines = denied_calls(exec_text)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16] if lines else "none"


def protected_hit(exec_text):
    """True if a denied call names a protected file (CODEOWNERS or the judge settings)."""
    for rec in _records(exec_text):
        for d in rec.get("permission_denials") or []:
            if isinstance(d, dict) and any(p in json.dumps(d.get("tool_input") or {}) for p in PROTECTED):
                return True
    return False


def last_denial(history, author_bot):
    """(sig, created_at) of the newest denial note by the author app, or None. HISTORY: issue comments, oldest first."""
    for c in reversed(history):
        m = DENIAL_RE.search(c.get("body") or "")
        if m and same_login((c.get("user") or {}).get("login"), author_bot):
            return m.group(1), c.get("created_at") or ""
    return None


def changed_since(kind, number, history, since, run=gh):
    """Something changed after SINCE: a commit to the kind's allow list or role file, or a slip comment. Answers by
    Daniel, receiver confirmations and denial notes do not count: they would reopen the same loop."""
    repo = os.environ.get("GH_REPO", "")
    for path in ALLOW_FILES.get(kind, ()):
        try:
            if json.loads(run("api", f"repos/{repo}/commits?path={path}&since={since}&per_page=1")):
                return True
        except (ValueError, OSError, subprocess.CalledProcessError):
            return False  # unknown: fail closed
    answered = {int(m) for c in history for m in RECEIVER_RE.findall(c.get("body") or "")}
    return any((c.get("created_at") or "") > since and c.get("id") not in answered
               and not RECEIVER_RE.search(c.get("body") or "") and not DENIAL_RE.search(c.get("body") or "")
               for c in history)


def retrigger_offer(kind, number, sig, exec_text, run=gh):
    """(offer, reason, cap): may the note offer "ja" (a retrigger)? Only if something changed since the last denied run.
    A protected file is never retriggered. The same call denied twice sets CAP: automatic restarts end. Unknown history
    (or unknown author app) fails closed: no offer."""
    if protected_hit(exec_text):
        return False, "eine geschuetzte Datei (CODEOWNERS oder claude-judge-settings.json) wurde verweigert; die Aenderung kommt ueber einen geskripteten Weg oder einen PR des Owners", False
    author = os.environ.get("AUTHOR_BOT", "")
    if not author:
        return False, "der Autor-App-Login ist nicht bekannt", False
    try:
        pages = json.loads(run("api", "--paginate", "--slurp", f"repos/{os.environ.get('GH_REPO', '')}/issues/{number}/comments"))
        history = [c for page in pages for c in page]
    except (ValueError, TypeError, OSError, subprocess.CalledProcessError):
        return False, "der Verlauf des Items ist nicht lesbar", False
    prev = last_denial(history, author)
    if prev is None:
        return True, "", False
    if sig != "none" and prev[0] == sig:
        return False, "dieselbe verweigerte Aktion zum zweiten Mal", True
    if changed_since(kind, number, history, prev[1], run):
        return True, "", False
    return False, "seit dem letzten verweigerten Lauf hat sich nichts geaendert (Erlaubnisliste, Rollendatei, Auftrag)", False


def denial_question(is_pr, offer, reason):
    """The German question for Daniel: "ja" is offered only when a retrigger is allowed; the marker follows the offer."""
    thing = "pr" if is_pr else "issue"
    what = "der PR" if is_pr else "das Issue"
    head = "\n\nHallo Daniel, ein Agenten-Lauf ist ohne Ergebnis geendet. "
    if offer:
        return (head + f"Frage: Soll der Block aufgehoben werden (ja) oder {what} geschlossen werden (nein)?\n"
                + decision.build(yes="drop-block", no=f"close-{thing}"))
    return (head + f"Kein Neustart angeboten: {reason}. Frage: Soll {what} geschlossen werden (nein)? "
            "Ja fuehrt in diesem Fall nichts aus.\n" + decision.build(no=f"close-{thing}"))


def post_owner_note(kind, number, body, run=gh):
    """The one path for a note that parks something with Daniel: refuses a body without a valid decision marker."""
    if not decision.has_marker(body):
        raise ValueError("an owner note needs a valid decision marker")
    liveness.post_comment(kind, number, body, run)


def park(kind, number, yes, no, text, run=gh):
    """Park an item with Daniel: TEXT (the German note) plus a marker built from YES/NO action ids ("-" = no answer of
    that kind). The only path the orchestrator uses; an invalid action id raises before anything is posted."""
    answers = {k: v for k, v in (("yes", yes), ("no", no)) if v != "-"}
    post_owner_note(kind, number, text.rstrip() + "\n" + decision.build(**answers), run)


def denied_tools(exec_text):
    """Sorted harness tool names of the denied calls; anything else (model text) is dropped."""
    names = {d.get("tool_name") for rec in _records(exec_text) for d in rec.get("permission_denials") or []
             if isinstance(d, dict)}
    return sorted(n for n in names if isinstance(n, str) and TOOL_RE.fullmatch(n))


def routes_upstream(run=gh):
    """Where this repo's upstream issues go: "" = this repo is the template (no .agents/template.json on the default
    branch, or its `template` names this repo); another owner/repo = a downstream project; None = unknown (fail closed).
    Read from the default branch (contents API without ref), never from the checkout the agent may have edited."""
    repo = os.environ.get("GH_REPO", "")
    try:
        raw = run("api", "-H", "Accept: application/vnd.github.raw", f"repos/{repo}/contents/.agents/template.json")
    except subprocess.CalledProcessError as exc:
        return "" if "HTTP 404" in (exc.stderr or "") else None
    except OSError:
        return None
    try:
        name = json.loads(raw).get("template")
    except (ValueError, AttributeError):
        return None
    if not isinstance(name, str) or not REPO_RE.fullmatch(name):
        return None
    return "" if name.lower() == repo.lower() else name


def upstream_issues(workflow, run=gh):
    """Open issues of the denied-command family of WORKFLOW in this repo, as (number, title)."""
    prefix = f"Denied command in {workflow}: "
    found = json.loads(run("issue", "list", "--state", "open", "--search", f'"{prefix}" in:title', "--limit", "100",
                           "--json", "number,title") or "[]")
    return [(i["number"], i["title"]) for i in found if i.get("title", "").startswith(prefix)]


def _source_issue(source, key, run=gh):
    """(title, body) of the source issue. A guard signature that does not verify raises ValueError: never re-signed."""
    view = json.loads(run("issue", "view", str(source), "--json", "title,body"))
    title, body = view.get("title") or "", view.get("body") or ""
    if guard_mark.split(body)[1] is not None and not guard_mark.verify(title, body, key):
        raise ValueError(f"issue #{source} carries a guard signature that does not verify: not re-signed")
    return title, body


def add_dependency(source, dep, key, run=gh):
    """Append `Depends on: DEP` on its own line (deps.py syntax). A verified signature is renewed; an unsigned body stays
    unsigned; a body that already names DEP is left alone."""
    title, body = _source_issue(source, key, run)
    core, sig = guard_mark.split(body)
    if dep in re.findall(r"#\d+", "\n".join(x for x in core.splitlines() if x.startswith("Depends on:"))):
        return
    new = core.rstrip() + f"\n\nDepends on: {dep}\n"
    if sig is not None:
        new = guard_mark.sign(title, new, key)
    run("issue", "edit", str(source), "--body", new)


def create_upstream(workflow, title, key, run=gh):
    """The signed issue for a new miss: fixed text only (workflow name and run URL from the environment)."""
    run_url = os.environ.get("RUN_URL", "") or "(unknown)"
    body = (f"The workflow {workflow} was denied a tool call that its allow list does not cover. Run: {run_url}. "
            f"Decide: add the call to the allow list of {workflow}, or keep it denied.")
    ensure_label("prio:2", run)
    out = run("issue", "create", "--title", title, "--label", "prio:2", "--body", guard_mark.sign(title, body, key))
    return int(out.strip().rsplit("/", 1)[-1])


def route_upstream(kind, source, exec_text, run=gh):
    """An allow-list miss (a denied call, not a protected path) gets ONE signed issue in the template repo; the next run
    with the same miss comments on it. The source issue then waits with `Depends on:` instead of needs-human.
    True if it waits. False: escalate as before (no key, protected path, cross-repo or unknown template, cap reached,
    any error)."""
    workflow, key = WORKFLOW_NAME.get(kind), guard_mark.key_from_env()
    sig = denial_sig(exec_text)
    if not workflow or not key or sig == "none" or protected_hit(exec_text):
        return False
    if routes_upstream(run) != "":  # cross-repo: deps.py holds back only same-repo #N (cross-repo routing is a later issue)
        return False
    title = f"Denied command in {workflow}: {' '.join(denied_tools(exec_text)) or 'tool'} ({sig})"
    try:
        _source_issue(source, key, run)  # an unverified marker stops here, before anything is created
        family = upstream_issues(workflow, run)
        same = [n for n, t in family if t == title]
        if same:
            number = same[0]
            liveness.post_comment("issue", number, f"Seen again in run {os.environ.get('RUN_URL', '(unknown)')}.", run)
        elif len(family) < UPSTREAM_CAP:
            number = create_upstream(workflow, title, key, run)
        else:
            return False
        add_dependency(source, f"#{number}", key, run)
        liveness.post_comment("issue", source, f"Waiting for #{number}, the template issue for a denied tool call. "
                              "Not needs-human: a retrigger would be denied again.", run)
    except (subprocess.CalledProcessError, OSError, ValueError, liveness.ReadbackError):
        return False
    return True


RETRY_MARK = "<!-- silent-retry -->"
STUCK_TITLE = "Agent {kind} runs end silently on #{number}"


def _retried(number, author, run):
    pages = json.loads(run("api", "--paginate", "--slurp", f"repos/{os.environ.get('GH_REPO', '')}/issues/{number}/comments"))
    return any(RETRY_MARK in (c.get("body") or "") and same_login((c.get("user") or {}).get("login"), author)
               for page in pages for c in page)


def _stuck_issue(kind, number, what, key, run):
    """One open signed prio:1 issue per item for the agents (found by title); returns its number."""
    title = STUCK_TITLE.format(kind=kind, number=number)
    found = json.loads(run("issue", "list", "--state", "open", "--search", f'"{title}" in:title', "--json", "number,title"))
    same = [i["number"] for i in found if i["title"] == title]
    if same:
        return same[0]
    body = (f"Two agent-{kind} runs on #{number} ended without a result ({what}); the automatic retry did not help. "
            f"Last run: {os.environ.get('RUN_URL', '(unknown)')}. Goal: find why the run cannot finish (allow list, "
            f"prompt, a step the model cannot do) and fix that, so #{number} moves again.")
    ensure_label("prio:1", run)
    out = run("issue", "create", "--title", title, "--label", "prio:1", "--body", guard_mark.sign(title, body, key))
    return out.strip().rsplit("/", 1)[-1]


def self_heal(kind, number, is_pr, what, run=gh):
    """#624: a silent run is the agents' job, not Daniel's. First time on an item: retry once (dev: agent:dev re-added;
    fix: the task restarts from main unless it already has restart:1). Again: one signed prio:1 issue for the agents.
    True if handled; False (no key, no author app, a review run, any error): the old needs-human path."""
    key, author = guard_mark.key_from_env(), os.environ.get("AUTHOR_BOT", "")
    if not key or not author or kind not in ("dev", "fix"):
        return False
    import restart  # restart imports this module: import late
    url = os.environ.get("RUN_URL", "(unknown)")
    thing = "pr" if is_pr else "issue"
    try:
        if not _retried(number, author, run):
            if kind == "dev":
                liveness.post_comment(thing, number, f"{RETRY_MARK}\nRetry 1/1 after a silent run ({what}): {url}", run)
                run("issue", "edit", str(number), "--remove-label", "agent:dev")
                add_labels("issue", number, ["agent:dev"], run)
                return True
            info = json.loads(run("pr", "view", str(number), "--json", "body"))
            for issue in restart.own_issues(info.get("body")):
                labels = {x["name"] for x in json.loads(run("issue", "view", str(issue), "--json", "labels"))["labels"]}
                if restart.RESTART not in labels:
                    liveness.post_comment(thing, number, f"{RETRY_MARK}\nSilent fix run ({what}): {url}", run)
                    restart.restart_issue(number, issue, [], run, why=f"a fix run on #{number} ended silently ({what})")
                    return True
        n = _stuck_issue(kind, number, what, key, run)
        liveness.post_comment(thing, number, f"{RETRY_MARK}\nSilent again ({what}): {url}. Handed to #{n}, "
                              "not needs-human.", run)
        return True
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError, liveness.ReadbackError):
        return False


SETTLED_MARK = "<!-- settled -->"


def settle_if_done(number, exec_text, run=gh):
    """A dev run without a PR on an issue that already has a merged agent/NUMBER-* PR, and no denied call, found nothing
    left to build: drop agent:dev and close the issue, or the dispatcher would start it again (no retry, no stuck issue,
    no needs-human). True if settled; any error: False."""
    if count_denials(exec_text):
        return False
    try:
        prs = json.loads(run("pr", "list", "--state", "merged", "--limit", "100", "--json", "headRefName,mergedAt"))
        if not any(p.get("mergedAt") and p.get("headRefName", "").startswith(f"agent/{number}-") for p in prs):
            return False
        liveness.post_comment("issue", number, f"{SETTLED_MARK}\nNothing left to implement: a PR for agent/{number}-* is "
                              f"already merged and this run produced no new one: {os.environ.get('RUN_URL', '(unknown)')}. "
                              "Closing, no retry. Open a new issue for anything that is left.", run)
        run("issue", "edit", str(number), "--remove-label", "agent:dev")
        run("issue", "close", str(number), "--reason", "completed")
    except (subprocess.CalledProcessError, OSError, ValueError, liveness.ReadbackError):
        return False
    return True


def escalate(kind, number, is_pr, what, owner, run=gh):
    exec_text = read_exec(os.environ.get("EXEC_FILE", ""))
    if not is_pr and route_upstream(kind, number, exec_text, run):
        return  # the issue waits for the template issue: no needs-human, no question to Daniel
    if kind == "dev" and not is_pr and not protected_hit(exec_text) and settle_if_done(number, exec_text, run):
        return  # work already merged: nothing to retry
    if not protected_hit(exec_text) and self_heal(kind, number, is_pr, what, run):
        return  # retried once, or handed to a signed issue for the agents: no needs-human
    body = report(kind, what, os.environ.get("RUN_URL", ""), exec_text)
    thing = "pr" if is_pr else "issue"
    sig = denial_sig(exec_text)
    offer, reason, cap = retrigger_offer(kind, number, sig, exec_text, run)
    body += denial_question(is_pr, offer, reason) + f"\n<!-- denied-run sig={sig} -->"
    blocked = bool(owner_hold.held(thing, number, ["needs-human"], run, owner))
    add_labels(thing, number, ["needs-human", *(CAP_LABELS if cap else [])], run)
    post_owner_note(thing, number, body, run)
    if blocked:  # Daniel removed needs-human: comment only, no review request or assignment
        return
    if is_pr:
        author = json.loads(run("pr", "view", str(number), "--json", "author"))["author"]["login"]
        if not same_login(author, owner):  # nobody can review their own PR
            try:
                run("pr", "edit", str(number), "--add-reviewer", owner)
            except subprocess.CalledProcessError:
                print("review request failed")
    else:  # an issue has no reviewers: assigning puts it in the owner's inbox
        try:
            run("issue", "edit", str(number), "--add-assignee", owner)
        except subprocess.CalledProcessError:
            print("assignment failed")


class UsageError(ValueError):
    pass


def silent_check(args, owner):
    """One `silent KIND NUMBER ...` check. Extra trailing arguments are ignored (workflow/guard version drift:
    the guard runs from main, the workflow from the PR branch). Too few arguments or an unknown KIND: UsageError."""
    if len(args) < 2:
        raise UsageError("silent needs KIND and NUMBER")
    kind, number = args[0], args[1]
    if kind == "dev" and len(args) >= 3:
        prs = json.loads(gh("pr", "list", "--state", "all", "--limit", "100", "--json", "headRefName,createdAt"))
        if not dev_has_pr(prs, number, args[2]):
            escalate("dev", number, False, f"no PR was produced for the agent/{number}-* branch", owner)
    elif kind == "fix" and len(args) >= 3:
        now = json.loads(gh("pr", "view", number, "--json", "headRefOid,body"))
        before = read_body_before(args[3]) if len(args) >= 4 else None
        if fix_produced(args[2], now["headRefOid"], before, now.get("body")):
            pass
        elif is_settled(number, os.environ.get("APPROVER_BOT", "")):  # nothing to fix: log it, no needs-human
            print(f"fix run on #{number} pushed nothing, but the PR is green and approved at its head: logged only")
        else:
            escalate("fix", number, True, "no fix was produced (no new commit, PR body unchanged)", owner)
    elif kind == "review" and len(args) >= 3:
        bh = args[3] if len(args) >= 4 else None
        if is_stale_head(number, args[2], gh):  # the head moved during the run: that review is discarded, not silent
            print(f"head moved past {args[2][:7]}: stale run, nothing to report")
            return 0
        if not has_review(reviews_of(number), os.environ.get("APPROVER_BOT", ""), args[2], bh):
            escalate("review", number, True, "no review by the approver app exists for the head commit", owner)
    elif kind == "orchestrator" and len(args) >= 3:
        return silent_orchestrator(args[2])
    else:
        raise UsageError(f"bad arguments for silent {kind}: {len(args) - 1} after the kind")
    return 0


def silent_guarded(args, owner, check=silent_check):
    """A silent-run guard never fails quietly: a usage error or an exception escalates ("guard error"), exit 1."""
    try:
        return check(args, owner)
    except Exception as exc:  # noqa: BLE001 - the whole point is to catch everything
        detail = _SECRET.sub("***", " ".join(f"{type(exc).__name__}: {exc}".split()))[:200]
        print(f"guard error: {detail}", file=sys.stderr)
        kind, number = (args + ["", ""])[:2]
        why = f"guard error ({detail})"
        try:
            if kind == "orchestrator" or not number.isdigit():
                escalate_orchestrator(why, os.environ.get("STATUS_ISSUE", "57"), os.environ.get("GH_REPO", ""),
                                      os.environ.get("AUTHOR_BOT", ""))
            else:
                escalate(kind if kind in ("dev", "fix", "review") else "guard", number, kind != "dev", why, owner)
        except Exception as exc2:  # noqa: BLE001
            print(f"escalation failed: {type(exc2).__name__}", file=sys.stderr)
        return 1


def main(argv):
    owner = os.environ.get("OWNER", OWNER_DEFAULT)
    cmd, args = (argv[1], argv[2:]) if len(argv) > 1 else ("", [])
    if cmd == "login" and len(args) == 1:
        print(norm_login(args[0]))
    elif cmd == "same" and len(args) == 2:
        return 0 if same_login(*args) else 1
    elif cmd == "label" and len(args) >= 3 and args[0] in ("pr", "issue"):
        add_labels(args[0], args[1], args[2:])
    elif cmd == "round" and len(args) == 2:
        print(count_round(args[0], args[1]))
    elif cmd == "refund" and len(args) == 2:
        print(refund_round(args[0], args[1], os.environ.get("APPROVER_BOT", "")))
    elif cmd == "form-failure" and len(args) == 1:
        return 0 if is_form_failure(args[0]) else 1
    elif cmd == "agent-pr" and len(args) in (1, 2):
        labels = (args[1] if len(args) == 2 else "").split(",")
        return 0 if is_agent_pr(args[0], labels, os.environ.get("AUTHOR_BOT", ""), owner) else 1
    elif cmd == "body-hash" and len(args) == 1:
        print(body_hash(json.loads(gh("pr", "view", args[0], "--json", "body"))["body"]))
    elif cmd == "reviewed" and len(args) in (2, 3):
        bh = args[2] if len(args) == 3 else None
        return 0 if has_review(reviews_of(args[0]), os.environ.get("APPROVER_BOT", ""), args[1], bh) else 1
    elif cmd == "park" and len(args) == 5 and args[0] in ("pr", "issue"):
        try:
            park(args[0], args[1], args[2], args[3], args[4])
        except ValueError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 1
    elif cmd == "silent":
        return silent_guarded(args, owner)
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
