"""Outside intake, script core (no model): list what each thread of an outside submission is owed.

OUTSIDE is any author who is not the owner, not an agent app and not a bot. Per open issue the state is
`triage` (no answer of ours yet), `reply` (an outside message is newer than our last comment) or empty
(answered or declined, nothing newer). The markers `<!-- outside-intake:answered -->` and
`<!-- outside-intake:declined -->` count only in comments of the author app; an outsider pasting one is ignored.
A cursor file keeps a thread listed while something is owed. Model runs are capped per thread and per repo per day.

  outside_intake.py list         print `<number> <triage|reply>` per owed thread
  outside_intake.py record <n>   count one model run for thread n; exit 1 when a cap is reached

Needs the gh CLI (GH_TOKEN, GH_REPO). Environment: OWNER (default Bankaifan), AUTHOR_BOT (author app login),
OUTSIDE_CURSOR (state file, default .agent-out/outside-intake.json).
"""
import datetime
import json
import os
import sys

from agent_guard import gh as run_gh
from agent_guard import norm_login, same_login

MARKERS = ("<!-- outside-intake:answered -->", "<!-- outside-intake:declined -->")
THREAD_CAP = 3  # model runs per thread per day
REPO_CAP = 20  # model runs per repo per day


def is_outside(login, kind, owner, author_bot):
    """True for a human account that is neither the owner nor the author app nor any bot."""
    if not norm_login(login):
        return False
    if same_login(login, owner) or same_login(login, author_bot):
        return False
    return not ((kind or "").lower() == "bot" or login.endswith("[bot]") or login.startswith("app/"))


def owed(issue, comments, owner, author_bot):
    """Return "triage", "reply" or "" for one thread.

    issue: {"user": {"login", "type"}, "created_at", ...}; comments: [{"user": {...}, "body", "created_at"}].
    """
    def who(msg):
        u = msg.get("user") or {}
        return u.get("login"), u.get("type")

    ours = [c for c in comments if same_login(who(c)[0], author_bot)]
    outside = [c["created_at"] for c in comments if is_outside(*who(c), owner, author_bot)]
    if is_outside(*who(issue), owner, author_bot):
        outside.append(issue["created_at"])
    if not outside:
        return ""
    if not any(m in (c.get("body") or "") for c in ours for m in MARKERS):
        return "triage"
    last_ours = max((c["created_at"] for c in ours), default="")
    return "reply" if max(outside) > last_ours else ""


def can_run(state, number, today):
    """True while the day's caps allow one more model run for this thread."""
    day = state.get("runs", {}).get(today, {})
    return day.get("repo", 0) < REPO_CAP and day.get("threads", {}).get(str(number), 0) < THREAD_CAP


def count_run(state, number, today):
    """Record one model run (drops older days) and return the state."""
    day = {"repo": 0, "threads": {}}
    day.update(state.get("runs", {}).get(today, {}))
    day["repo"] += 1
    day["threads"][str(number)] = day["threads"].get(str(number), 0) + 1
    state["runs"] = {today: day}
    return state


def scan(numbers, repo, owner, author_bot, gh=None):
    """Owed state per issue number: {number: "triage"|"reply"}, empty states left out."""
    gh = gh or run_gh
    result = {}
    for n in numbers:
        issue = json.loads(gh("api", f"repos/{repo}/issues/{n}"))
        if issue.get("pull_request") or issue.get("state") != "open":
            continue
        pages = json.loads(gh("api", "--paginate", "--slurp", f"repos/{repo}/issues/{n}/comments"))
        comments = [c for page in pages for c in page]
        state = owed(issue, comments, owner, author_bot)
        if state:
            result[n] = state
    return result


def open_numbers(repo, gh=None):
    gh = gh or run_gh
    pages = json.loads(gh("api", "--paginate", "--slurp", f"repos/{repo}/issues?state=open&per_page=100"))
    return [i["number"] for page in pages for i in page if not i.get("pull_request")]


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, sort_keys=True)


def listing(state, numbers, repo, owner, author_bot, gh=None):
    """Scan the open issues plus the cursor's threads; the cursor then holds exactly the threads still owed."""
    wanted = sorted(set(numbers) | {int(n) for n in state.get("owed", {})})
    found = scan(wanted, repo, owner, author_bot, gh)
    state["owed"] = {str(n): s for n, s in found.items()}
    return found


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    owner = os.environ.get("OWNER", "Bankaifan")
    author_bot = os.environ.get("AUTHOR_BOT", "")
    repo = os.environ["GH_REPO"]
    path = os.environ.get("OUTSIDE_CURSOR", ".agent-out/outside-intake.json")
    today = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    state = load(path)
    if argv[:1] == ["list"]:
        found = listing(state, open_numbers(repo), repo, owner, author_bot)
        save(path, state)
        for n in sorted(found):
            print(n, found[n])
        return 0
    if len(argv) == 2 and argv[0] == "record" and argv[1].isdigit():
        if not can_run(state, argv[1], today):
            print(f"cap reached for #{argv[1]}", file=sys.stderr)
            return 1
        save(path, count_run(state, argv[1], today))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
