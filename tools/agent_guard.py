"""Shared helpers for the agent workflows: login normalization, labels that always exist, silent-run guard.

CLI (needs the gh CLI with GH_TOKEN and GH_REPO):
  agent_guard.py login LOGIN                 print the normalized login
  agent_guard.py same A B                    exit 0 if both logins name the same account
  agent_guard.py label pr|issue N LABEL...   create each label if missing, then add it
  agent_guard.py agent-pr AUTHOR [LABELS]    exit 0 if the PR is an agent PR (env AUTHOR_BOT, OWNER; LABELS comma list)
  agent_guard.py reviewed PR SHA [BODYHASH]  exit 0 if the approver app (env APPROVER_BOT) reviewed SHA (and BODYHASH)
  agent_guard.py body-hash PR                print the hash of the PR body (the reviewer repeats it as `body-hash: H`)
  agent_guard.py silent dev ISSUE SINCE      after agent-dev: no PR for agent/ISSUE-* created at/after SINCE (UTC ISO) -> escalate
  agent_guard.py silent fix PR HEAD_BEFORE [BODY_FILE]
                                             after agent-fix: PR head and body (BODY_FILE = body before the run) unchanged -> escalate
  agent_guard.py silent review PR SHA [BODYHASH]
                                             after agent-review: no approver review for SHA (and BODYHASH) -> escalate
  agent_guard.py silent orchestrator - SINCE after the orchestrator model step: denials, or STARTABLE=true and no visible action
                                             by AUTHOR_BOT since SINCE -> comment on STATUS_ISSUE (default 57), exit 1; 2nd in 24 h -> prio:1 issue
`silent` ignores extra trailing arguments (the guard runs from main, the workflow from the PR branch: no version drift).
A usage error or exception in `silent` escalates with reason "guard error" and exits 1; it never fails quietly.
Escalate = comment (run URL, denied tool calls from the execution file, else its last lines), label needs-human, request OWNER's review.
Environment for escalation: RUN_URL, EXEC_FILE (path of the action's execution file), OWNER (default Bankaifan).
"""
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys

OWNER_DEFAULT = "Bankaifan"
TAIL_LINES = 15
TAIL_CHARS = 1500
MAX_DENIALS = 10
_SECRET = re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-ant-[A-Za-z0-9_-]{20,})")


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
    for name in labels:
        ensure_label(name, run)
    run(kind, "edit", str(number), *[a for name in labels for a in ("--add-label", name)])


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


def tail_text(text, lines=TAIL_LINES, chars=TAIL_CHARS):
    """Last lines of the execution file, secret-looking tokens masked, fences neutralized, length capped."""
    out = "\n".join(text.splitlines()[-lines:])[-chars:].replace("```", "'''")
    return _SECRET.sub("***", out)


def _records(text):
    """Execution file = JSON array of messages (or JSON lines); return every dict."""
    try:
        data = json.loads(text)
    except ValueError:
        data = []
        for line in text.splitlines():
            try:
                data.append(json.loads(line))
            except ValueError:
                pass
    return [d for d in (data if isinstance(data, list) else [data]) if isinstance(d, dict)]


def denied_calls(text, limit=MAX_DENIALS):
    """One line per denied tool call (tool + command/path) from `permission_denials`; secrets masked."""
    lines = []
    for rec in _records(text):
        for d in rec.get("permission_denials") or []:
            if not isinstance(d, dict):
                continue
            inp = d.get("tool_input")
            inp = inp if isinstance(inp, dict) else {}
            what = inp.get("command") or inp.get("file_path") or inp.get("path") or inp.get("pattern") or ""
            text_ = _SECRET.sub("***", " ".join(str(what).split()))[:150]  # mask first, then cut
            lines.append(f"{d.get('tool_name') or '?'}: {text_}".replace("`", "'"))
    more = len(lines) - limit
    return lines[:limit] + ([f"... and {more} more"] if more > 0 else [])


def count_denials(text):
    """Number of permission denials in the execution file (all of them, not only the listed ones)."""
    return sum(len([d for d in rec.get("permission_denials") or [] if isinstance(d, dict)]) for rec in _records(text))


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
    run("issue", "comment", str(status_issue), "--body", body)
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


def read_exec(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, TypeError):
        return ""


def read_body_before(path):
    """PR body saved before a fix run. None if missing or unreadable: unknown, not an empty body."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, TypeError):
        return None


def escalate(kind, number, is_pr, what, owner, run=gh):
    body = report(kind, what, os.environ.get("RUN_URL", ""), read_exec(os.environ.get("EXEC_FILE", "")))
    thing = "pr" if is_pr else "issue"
    add_labels(thing, number, ["needs-human"], run)
    run(thing, "comment", str(number), "--body", body)
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


def reviews_of(pr, run=gh):
    pages = json.loads(run("api", "--paginate", "--slurp", f"repos/{os.environ['GH_REPO']}/pulls/{pr}/reviews"))
    return [r for page in pages for r in page]


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
        if not fix_produced(args[2], now["headRefOid"], before, now.get("body")):
            escalate("fix", number, True, "no fix was produced (no new commit, PR body unchanged)", owner)
    elif kind == "review" and len(args) >= 3:
        bh = args[3] if len(args) >= 4 else None
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
    elif cmd == "agent-pr" and len(args) in (1, 2):
        labels = (args[1] if len(args) == 2 else "").split(",")
        return 0 if is_agent_pr(args[0], labels, os.environ.get("AUTHOR_BOT", ""), owner) else 1
    elif cmd == "body-hash" and len(args) == 1:
        print(body_hash(json.loads(gh("pr", "view", args[0], "--json", "body"))["body"]))
    elif cmd == "reviewed" and len(args) in (2, 3):
        bh = args[2] if len(args) == 3 else None
        return 0 if has_review(reviews_of(args[0]), os.environ.get("APPROVER_BOT", ""), args[1], bh) else 1
    elif cmd == "silent":
        return silent_guarded(args, owner)
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
