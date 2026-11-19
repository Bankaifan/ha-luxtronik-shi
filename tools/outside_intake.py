"""Outside intake (decision 0017, rule 5): issues by outsiders and scout ideas are triaged, answered or turned into work.

OUTSIDE is any author who is not the owner, not an agent app and not a bot. An open issue by an outsider is `triage`
(no marked answer of ours yet) or `reply` (an outside message is newer than our last marked answer); an open `idea`
issue of the author app is `triage` until it has a marker. The markers `<!-- outside-intake:answered -->` and
`<!-- outside-intake:declined -->` count only in comments of the author app; an outsider pasting one is ignored.

The model step (intake.yml) has no token and no shell. It reads untrusted/*.txt and writes verdict.json:
  {"action": "answer" | "decline" | "build", "reply": "<text for the issue author, in the language of the issue>",
   "title": "<NAME: summary>", "goal": "...", "files": ["path", ...], "acceptance": "..."}
`title`, `goal`, `files`, `acceptance` only for build. reply: at most 1500 chars, no `@`, no links, no HTML.
title (task ID form of tools/task_ids.py), goal and acceptance: one line of plain English words, no code, quotes or
backticks. files: 1 to 10 plain repo-relative paths. A build that names a protected path (workflows, tools, agent
rules, CODEOWNERS paths, docs/design/: tools/ci/risk.py) or asks for a forbidden action in words (unblock.forbidden) is not built:
the issue gets the fixed answer NEEDS_MAINTAINER and stays open.

  outside_intake.py list [N]        JSON list of the owed issue numbers the caps still allow (N: only that issue)
  outside_intake.py fetch N DIR     write the issue text as masked, capped files to DIR/untrusted/ (unblock.fetch)
  outside_intake.py validate FILE   check a verdict file without acting; exit 0 = valid
  outside_intake.py apply N FILE    answer (comment), decline (comment, close as not planned) or build (one slip issue
                                    from the fixed template with `Intake: #N`, comment, close N); idempotent. An
                                    `idea` is never left answered: answer counts as decline (NEEDS_MAINTAINER stays open)
  outside_intake.py failed N        mark a run that applied nothing, so it counts against the caps; the third such
                                    run on a thread declines it (fixed text, closed as not planned)

Caps: THREAD_CAP model runs per issue and REPO_CAP per repo in 24 hours, counted from the marker comments of the
author app (Actions keeps no state between runs). Needs the gh CLI (GH_TOKEN, GH_REPO). Environment: OWNER (default
Bankaifan), AUTHOR_BOT (author app login).
"""
import datetime
import json
import os
import re
import sys
import tempfile

import exec_log
import overlap
import task_ids
import trusted_issues
import unblock
from agent_guard import gh as run_gh
from agent_guard import norm_login, same_login

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci"))
import risk

ANSWERED, DECLINED = "<!-- outside-intake:answered -->", "<!-- outside-intake:declined -->"
FAILED = "<!-- outside-intake:failed -->"
MARKERS = (ANSWERED, DECLINED)
THREAD_CAP = 3  # model runs per thread in 24 hours
REPO_CAP = 20  # model runs per repo in 24 hours
MAX_FAILED = 3  # runs without an applied verdict on one thread, in total: then it is declined without a model
MAX_REPLY, MAX_LINE, MAX_TITLE, MAX_FILES = 1500, 300, 100, 10
NEEDS_MAINTAINER = ("Thank you. This request touches a protected part of the project, so this needs a maintainer; "
                    "it is not started automatically.")
FAILED_TEXT = "Automatic triage did not finish for this issue. It is tried again later."
GAVE_UP_TEXT = "Automatic triage could not handle this issue, so it is closed. A maintainer can reopen it."
SLIP = "Goal: {goal}\nFiles: {files}\nAcceptance: {acceptance}\nIntake: #{n}\n"
# Nothing we post may notify, link, embed or start a line a script reads (slip fields, trust lines).
_UNSAFE = re.compile(r"@|://|www\.|mailto:|xmpp:|\]\(|\]\[|\]:|<[A-Za-z!/]|[\w.-]/[\w.-]+#\d", re.IGNORECASE)
_FIELD = re.compile(r"\b(?:Files(?:\s+touched)?|Intake|Design|Template-Sync|Depends on|Model|Goal|Acceptance)\**\s*:"
                    r"|\bDesign \d{4}\b", re.IGNORECASE)
_PATH = re.compile(r"[A-Za-z0-9._][A-Za-z0-9._/-]*")


def is_outside(login, kind, owner, author_bot):
    """True for a human account that is neither the owner nor the author app nor any bot."""
    if not norm_login(login):
        return False
    if same_login(login, owner) or same_login(login, author_bot):
        return False
    return not ((kind or "").lower() == "bot" or login.endswith("[bot]") or login.startswith("app/"))


def _who(msg):
    u = msg.get("user") or {}
    return u.get("login"), u.get("type")


def _app(msg, author_bot):
    """True if the author app itself wrote MSG (REST: type `Bot`), not a person whose account is named like it."""
    login, kind = _who(msg)
    return same_login(login, author_bot) and kind == "Bot"


def _marked(comments, author_bot, markers=MARKERS):
    """created_at of the author app's comments that carry one of MARKERS."""
    return [c["created_at"] for c in comments if _app(c, author_bot) and any(m in (c.get("body") or "") for m in markers)]


def owed(issue, comments, owner, author_bot):
    """Return "triage", "reply" or "" for one thread.

    issue: {"user": {"login", "type"}, "created_at", ...}; comments: [{"user": {...}, "body", "created_at"}].
    """
    outside = [c["created_at"] for c in comments if is_outside(*_who(c), owner, author_bot)]
    if is_outside(*_who(issue), owner, author_bot):
        outside.append(issue["created_at"])
    if not outside:
        return ""
    ours = _marked(comments, author_bot)
    if not ours:
        return "triage"
    return "reply" if max(outside) > max(ours) else ""


def state_of(issue, comments, owner, author_bot):
    """What intake owes an issue: `owed` for an issue an outsider wrote, "triage" for an unmarked `idea` of the author
    app, "" for everything else (an outside comment on the owner's or an agent's issue starts nothing)."""
    login, kind = _who(issue)
    if is_outside(login, kind, owner, author_bot):
        return owed(issue, comments, owner, author_bot)
    if _app(issue, author_bot) and any(lab.get("name") == "idea" for lab in issue.get("labels") or []):
        return "" if _marked(comments, author_bot) else "triage"
    return ""


def _pages(gh, path):
    return [x for page in json.loads(gh("api", "--paginate", "--slurp", path)) for x in page]


def scan(numbers, repo, owner, author_bot, gh=None):
    """State per issue number: {number: "triage"|"reply"}, empty states, PRs and closed issues left out."""
    gh = gh or run_gh
    result = {}
    for n in numbers:
        issue = json.loads(gh("api", f"repos/{repo}/issues/{n}"))
        if issue.get("pull_request") or issue.get("state") != "open":
            continue
        state = state_of(issue, _pages(gh, f"repos/{repo}/issues/{n}/comments"), owner, author_bot)
        if state:
            result[n] = state
    return result


def open_numbers(repo, gh=None):
    return [i["number"] for i in _pages(gh or run_gh, f"repos/{repo}/issues?state=open&per_page=100")
            if not i.get("pull_request")]


def recent_runs(repo, author_bot, now, gh=None):
    """Issue number of every intake run of the last 24 hours: one per marker comment of the author app."""
    since = (now - datetime.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    comments = _pages(gh or run_gh, f"repos/{repo}/issues/comments?since={since}&per_page=100")
    return [int(c["issue_url"].rsplit("/", 1)[-1]) for c in comments
            if c.get("created_at", "") >= since and _marked([c], author_bot, (*MARKERS, FAILED))]


def allowed(found, counted):
    """The numbers of FOUND that the caps still allow, lowest first. COUNTED: `recent_runs`."""
    out = []
    for n in sorted(found):
        if len(counted) + len(out) >= REPO_CAP:
            break
        if counted.count(n) < THREAD_CAP:
            out.append(n)
    return out


def protected(path, codeowners=""):
    """True if PATH is, lies in or contains a path that risk.py classes as infra or security, a CODEOWNERS path or
    a design file (design-split turns a merged design into trusted issues)."""
    if risk.classify(f"diff --git a/{path} b/{path}\n") != "none":
        return True
    owned = [line.split()[0][1:] for line in codeowners.splitlines() if line.startswith("/")]
    return any(overlap.overlaps(path, p) for p in (*risk.INFRA_PATHS, *risk.SECURITY_FILES, risk.DESIGN_DIR, *owned))


def _text(verdict, key, limit, lines=False):
    """One model string that will be posted: bounded, printable, no mention, link, HTML or script-read line start."""
    val = verdict.get(key)
    if not isinstance(val, str) or not val.strip() or len(val) > limit:
        raise ValueError(f"{key} must be non-empty text up to {limit} chars")
    val = val.strip()
    if _UNSAFE.search(val) or _FIELD.search(val) or overlap.parse_files(val):
        raise ValueError(f"{key} must not mention anyone, link anywhere or hold a slip field")
    if not all(ch.isprintable() or (lines and ch == "\n") for ch in val) or not (lines or val.isascii()):
        raise ValueError(f"{key} holds characters that are not allowed")
    return val


def slip_title(title, version=""):
    """TITLE in the task ID form, with the `V<major>-` prefix added if only that makes it one; else ValueError."""
    for cand in (title, f"V{version.split('.')[0]}-{title}"):
        if task_ids.task_id_of(cand):
            return cand
    raise ValueError("title must start with a task ID")


def validate(verdict, codeowners="", version=""):
    """Normalised verdict or ValueError (fail closed). A build that names a protected path or asks for a forbidden
    action becomes the fixed NEEDS_MAINTAINER answer."""
    if not isinstance(verdict, dict) or verdict.get("action") not in ("answer", "decline", "build"):
        raise ValueError("action must be answer, decline or build")
    unblock.check_outgoing(verdict)
    out = {"action": verdict["action"], "reply": _text(verdict, "reply", MAX_REPLY, lines=True)}
    if out["action"] != "build":
        return out
    files = verdict.get("files")
    if not isinstance(files, list) or not 0 < len(files) <= MAX_FILES:
        raise ValueError(f"files must be a list of 1 to {MAX_FILES} paths")
    if not all(isinstance(p, str) and len(p) <= 200 and _PATH.fullmatch(p) for p in files):
        raise ValueError("files must be plain repo-relative paths")
    out.update(title=slip_title(_text(verdict, "title", MAX_TITLE), version), files=files,
               goal=_text(verdict, "goal", MAX_LINE), acceptance=_text(verdict, "acceptance", MAX_LINE))
    if any(protected(p, codeowners) for p in files) or any(
            unblock.forbidden(out[k]) for k in ("title", "goal", "acceptance")):
        return {"action": "answer", "reply": NEEDS_MAINTAINER}
    if any(overlap.clean_path(p) != p for p in files):  # what a slip reader would not read back as written
        raise ValueError("files must be plain repo-relative paths")
    return out


def slip_body(v, number):
    """The slip from the fixed template; ValueError unless scripts read back exactly the validated files and N."""
    body = SLIP.format(goal=v["goal"], files=", ".join(v["files"]), acceptance=v["acceptance"], n=number)
    if overlap.parse_files(body) != v["files"] or trusted_issues.INTAKE.findall(body) != [str(number)]:
        raise ValueError("slip does not read back as written")
    return body


def _post(gh, *args, body):
    """Run a gh command with BODY passed as a file, never as an argument gh could interpret."""
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md") as f:
        f.write(body)
        f.flush()
        return gh(*args, "--body-file", f.name)


def find_slip(number, author_bot, gh):
    """Number of the slip issue (open or closed) the author app wrote for #NUMBER, else None."""
    found = json.loads(gh("issue", "list", "--state", "all", "--limit", "50", "--search",
                          f'"Intake: #{number}" in:body', "--json", "number,body,author"))
    for i in found:
        if (trusted_issues.by_app(i.get("author"), author_bot)
                and str(number) in trusted_issues.INTAKE.findall(i.get("body") or "")):
            return i["number"]
    return None


def apply(number, verdict, repo, owner, author_bot, gh=None, codeowners="", version=""):
    """Apply a verdict to issue NUMBER; the state is re-read first. Returns the action carried out, or "skip"."""
    gh = gh or run_gh
    v = validate(verdict, codeowners, version)
    if int(number) not in scan([int(number)], repo, owner, author_bot, gh):
        return "skip"
    n = str(number)
    labels = json.loads(gh("api", f"repos/{repo}/issues/{n}")).get("labels") or []
    if v["action"] == "answer" and v["reply"] != NEEDS_MAINTAINER and any(lab.get("name") == "idea" for lab in labels):
        v["action"] = "decline"  # nobody replies to an idea: an answered one would stay open for ever
    if v["action"] == "build":
        slip = find_slip(number, author_bot, gh)
        if slip is None:
            url = _post(gh, "issue", "create", "--title", v["title"], body=slip_body(v, number))
            slip = int(url.strip().rsplit("/", 1)[-1])
        _post(gh, "issue", "comment", n, body=f"{ANSWERED}\n{v['reply']}\n\nTracked in #{slip}.")
        gh("issue", "close", n)
    elif v["action"] == "decline":
        _post(gh, "issue", "comment", n, body=f"{DECLINED}\n{v['reply']}")
        gh("issue", "close", n, "--reason", "not planned")
    else:
        _post(gh, "issue", "comment", n, body=f"{ANSWERED}\n{v['reply']}")
    return v["action"]


def mark_failed(number, repo, author_bot, gh=None):
    """Mark a run that applied nothing. The MAX_FAILED-th such run on a thread declines it with a fixed text."""
    gh, n = gh or run_gh, str(number)
    before = len(_marked(_pages(gh, f"repos/{repo}/issues/{n}/comments"), author_bot, (FAILED,)))
    _post(gh, "issue", "comment", n, body=f"{FAILED}\n{FAILED_TEXT}")
    if before + 1 >= MAX_FAILED:
        _post(gh, "issue", "comment", n, body=f"{DECLINED}\n{GAVE_UP_TEXT}")
        gh("issue", "close", n, "--reason", "not planned")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    owner = os.environ.get("OWNER", "Bankaifan")
    author_bot = os.environ.get("AUTHOR_BOT", "")
    repo = os.environ.get("GH_REPO", "")
    cmd, args = (argv[0], argv[1:]) if argv else ("", [])
    number = args[0] if args and args[0].isdigit() else ""
    if cmd == "list" and (number or not args) and len(args) <= 1:
        found = scan([int(number)] if number else open_numbers(repo), repo, owner, author_bot)
        print(json.dumps(allowed(found, recent_runs(repo, author_bot, datetime.datetime.now(datetime.UTC)))))
        return 0
    if cmd == "fetch" and number and len(args) == 2:
        print("\n".join(unblock.fetch("issue", number, args[1])))
        return 0
    if cmd == "validate" and len(args) == 1:
        try:
            v = validate(unblock.load_verdict(exec_log.read_exec(args[0])), _read(".github/CODEOWNERS"), _read("VERSION"))
        except ValueError as exc:  # json.JSONDecodeError is a ValueError
            print(f"invalid verdict: {exc}")
            return 1
        print(f"valid, {v['action']}")
        return 0
    if cmd == "apply" and number and len(args) == 2:
        verdict = unblock.load_verdict(exec_log.read_exec(args[1]))
        print(apply(number, verdict, repo, owner, author_bot, codeowners=_read(".github/CODEOWNERS"),
                    version=_read("VERSION")))
        return 0
    if cmd == "failed" and number and len(args) == 1:
        mark_failed(number, repo, author_bot)
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
