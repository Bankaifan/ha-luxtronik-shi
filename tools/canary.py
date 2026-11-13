"""Pipeline canary (issue #423, no model): prove issue -> slip -> developer -> CI -> review -> train -> merge still works.

create: after a merge that touched .github/workflows/ or tools/ (and after a template sync), open one signed issue
  `Canary: <UTC timestamp>` with a fixed slip (append one line to docs/canary.md, model haiku). At most one per 6 h.
check: for the newest canary issue that is 45 min to 2 h old: a merged PR and a closed issue = pass. Otherwise one signed
  `Failing workflow: canary` issue (prio:1) naming the stage where the run stopped, from the stage order of tools/flow.py (#420).
The canary PR touches only docs/canary.md, which is not template-managed, so it needs no changelog fragment and no VERSION
change (tools/check/check_version_bump.py asks for a fragment only for managed paths). Signed text is fixed script text only.

CLI (env GH_REPO, GH_TOKEN, GUARD_KEY; DRY_RUN=1 prints the writes and runs none): canary.py create | check
"""
import datetime
import json
import os
import sys

import flow
import ghcall
import guard_mark
import liveness
import trusted_issues

PREFIX = "Canary: "
FAIL_TITLE = "Failing workflow: canary"
LABEL = "model:haiku"
MIN_GAP_H = 6  # at most one canary per 6 h
CHECK_AFTER_MIN = 45
CHECK_UNTIL_MIN = 120  # an older canary was judged already; a closed failure issue must not be reopened by it
FILE = "docs/canary.md"
STAGE_NAMES = (*flow.STAGES, "close")  # close: PR merged, issue still open


def slip(stamp):
    return (f"Fixed canary slip. Append exactly one line `canary {stamp}` to {FILE} (create the file with a one-line "
            f"title if it is missing). Change nothing else: no changelog fragment, no VERSION or CHANGELOG edit. "
            f"Model: haiku.\n\nAcceptance:\n- {FILE} has the new line\n- the PR is merged and this issue is closed")


def _ts(text):
    return datetime.datetime.fromisoformat(text)


def canaries(key, author_bot, run=ghcall.gh):
    """Canary issues (any state) authored by the author app and signed with the guard key, newest first.
    A stranger's issue titled `Canary: ` is ignored (it must not block create or be judged by check)."""
    found = json.loads(run("issue", "list", "--state", "all", "--search", f'"{PREFIX.strip()}" in:title',
                           "--limit", "20", "--json", "number,title,state,createdAt,author,body,labels"))
    mine = [i for i in found if (i["title"] or "").startswith(PREFIX) and trusted_issues.is_guard_issue(i, author_bot, key)]
    return sorted(mine, key=lambda i: i["createdAt"], reverse=True)


def create(now, key=None, run=ghcall.gh, author_bot=None):
    """Open the canary issue unless one was created in the last 6 h. Returns its number, or None."""
    key = guard_mark.key_from_env() if key is None else key
    author_bot = os.environ.get("AUTHOR_BOT", "") if author_bot is None else author_bot
    found = canaries(key, author_bot, run)
    if found and now - _ts(found[0]["createdAt"]) < datetime.timedelta(hours=MIN_GAP_H):
        return None
    stamp = now.strftime("%Y-%m-%dT%H:%MZ")
    title = f"{PREFIX}{stamp}"
    out = run("issue", "create", "--title", title, "--label", LABEL, "--body", guard_mark.sign(title, slip(stamp), key))
    return out.strip().rsplit("/", 1)[-1]


def stopped_stage(issue, pr, events, runs):
    """Name of the first pipeline stage without its end mark, else `close`. pr is None when no PR exists."""
    if pr is None:
        dev = flow.first_label_time(events, ("agent:dev",))
        trusted = flow.first_label_time(events, flow.TRUSTED_LABELS) or issue["createdAt"]
        return "develop" if flow.minutes(trusted, dev) is not None else "dispatch"
    row = flow.pr_row(pr, events, runs, issue["createdAt"])
    if not pr.get("mergedAt"):
        return next((s for s in flow.STAGES if row[f"{s}_min"] == ""), "train")
    return "close"


def find_pr(number, run):
    prs = json.loads(run("pr", "list", "--state", "all", "--limit", "50", "--json",
                         "number,createdAt,mergedAt,headRefName,labels,reviews"))
    mine = [p for p in prs if flow.issue_number(p) == number]
    return max(mine, key=lambda p: p["createdAt"], default=None)


def fail_body(number, stage):
    return (f"The pipeline canary issue #{number} did not finish within {CHECK_AFTER_MIN} min. "
            f"It stopped at stage: {stage}. Check that stage and the workflow runs.")


def check(now, repo, key=None, run=ghcall.gh, author_bot=None):
    """('wait'|'none'|'pass'|'fail', detail). A fail opens (once) the signed `Failing workflow: canary` issue."""
    key = guard_mark.key_from_env() if key is None else key
    author_bot = os.environ.get("AUTHOR_BOT", "") if author_bot is None else author_bot
    found = canaries(key, author_bot, run)
    if not found:
        return "none", None
    newest = found[0]
    age = (now - _ts(newest["createdAt"])).total_seconds() / 60
    if age < CHECK_AFTER_MIN:
        return "wait", None
    if age > CHECK_UNTIL_MIN:
        return "none", None
    number = newest["number"]
    pr = find_pr(number, run)
    if newest["state"] == "CLOSED" and pr and pr.get("mergedAt"):
        return "pass", None
    pages = json.loads(run("api", "--paginate", "--slurp", f"repos/{repo}/issues/{number}/events"))
    events = [e for page in pages for e in page]
    runs = json.loads(run("run", "list", "--branch", pr["headRefName"], "--limit", "50", "--json",
                          "workflowName,conclusion,createdAt,updatedAt")) if pr else []
    stage = stopped_stage(newest, pr, events, runs)
    liveness.ensure_signed_issue(FAIL_TITLE, fail_body(number, stage), key, run)
    return "fail", stage


def dry_run(run):
    """Wrap gh: reads run, writes (issue create) are printed instead."""
    def wrapped(*args):
        if args[:2] == ("issue", "create"):
            print("dry-run:", " ".join(args[:4]))
            return "https://example.invalid/issues/0\n"
        return run(*args)
    return wrapped


def main(argv, env, now=None):
    now = now or datetime.datetime.now(datetime.UTC)
    run = dry_run(ghcall.gh) if env.get("DRY_RUN") else ghcall.gh
    if argv[1:] == ["create"]:
        print(create(now, run=run) or "skipped: a canary exists from the last 6 h")
        return 0
    if argv[1:] == ["check"]:
        status, detail = check(now, env["GH_REPO"], run=run)
        print(status if detail is None else f"{status}: stopped at {detail}")
        return 0
    sys.exit("usage: canary.py create | check")


if __name__ == "__main__":
    sys.exit(main(sys.argv, os.environ))
