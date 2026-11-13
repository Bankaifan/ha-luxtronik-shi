"""Unblocker core (design 0002, section 8 item 2): gate a `needs-human` block, then apply the verdict.

CLI (gh CLI with GH_TOKEN and GH_REPO; the model step is not here, the verdict is data in a JSON file):
  unblock.py gate KIND NUMBER      exit 0 = the unblocker may look at it, 1 = leave it to Daniel (reason on stdout)
  unblock.py fetch KIND NUMBER DIR  write masked, capped untrusted input to DIR/untrusted/*.txt for the model step
  unblock.py validate FILE         check a verdict file (shape, limits, secret filter) without acting; exit 0 = valid
  unblock.py landed NUMBER FILE    issue only, before the model step: a step that already landed writes a class 1 verdict
                                   to FILE and exits 0; otherwise exit 1 (the model step decides)
  unblock.py apply KIND NUMBER FILE  apply the verdict in FILE ({"class": 1|2|3, "reason", "comment", "issue", "note"})
Environment: OWNER (default Bankaifan), AUTHOR_BOT, APPROVER_BOT, RUN_URL.

Classes: 1 wrong assumption (comment, drop needs-human, unblock:1, restart), 2 infrastructure bug (one prio:1 issue,
needs-human stays), 3 owner decision (needs-human stays, German note as the LAST comment).

Open question of the design, how agent-fix starts for a red CI without a new commit: the unblocker dispatches
`agent-fix.yml` with input `pr=N` (the existing workflow_dispatch entry, also used for conflicts with main). No new
trigger or comment command is needed. Cost: the author app token needs actions:write; that is a permissions change
for the workflow PR (item 4, risk:security). An issue restarts like restart.py: agent:dev removed, then added.

Limits are enforced here as one layer besides the prompt (a word filter cannot catch every wording): a class 1
verdict that asks for a tool, permission, install, workflow or check change is turned into class 3, and so is a
class 2 issue with such wording; model text with `@` is refused; `apply` re-runs the gate on live data; `unblock:1` is set once, a second block goes to Daniel; design PRs
never get class 1. A risk:security PR is refused by the gate only if it changes a CODEOWNERS path of the owner.
"""
import json
import os
import re
import subprocess
import sys

import exec_log
import ghcall
import overlap
import restart
import slip
from agent_guard import add_labels, ensure_label, is_agent_pr
from trusted_issues import classify, label_set_by

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci"))
import decision
import risk

OWNER_DEFAULT = "Bankaifan"
MARK = "<!-- unblocker -->"
UNBLOCK = "unblock:1"
NEEDS_HUMAN = "needs-human"
MAX_COMMENT = 600
MAX_TITLE = 100
MAX_UNTRUSTED = 20000  # chars per untrusted input file
RISK_SECURITY = "risk:security"
_FORBIDDEN = re.compile(
    r"allowedtools|allowed-tools|pip3? install|-m pip|npm (?:install|i)\b|apt(?:-get)? install|brew install|"
    r"allow (?:the )?(?:command|tool|call)|grant|permissions?:|secrets?\b|token|\.github/|agents\.md|--dangerously|"
    r"workflows?/|codeowners|rulesets?|protection|risk\.py|security-review|tools/ci|"
    r"\b(?:disable|skip|bypass|ignore|override|instructions?)\b|"
    r"\b(?:curl|wget|sudo|chmod|chown|base64|bash|sh|eval|exec|rm|git|gh)\b",
    re.IGNORECASE)
_SAFE_SHAPE = re.compile(r"[A-Za-z0-9 .,;:'()/_#=+-]+")
_GERMAN_HINT = re.compile(r"\b(?:Daniel|Frage|ja|nein|Soll|Schlimmster|Hallo|Fall|und|der|die|das|nicht|ist)\b")
_FENCE = re.compile(r"\A\s*```[A-Za-z]*\s*\n(.*?)\n\s*```\s*\Z", re.DOTALL)


def load_verdict(text):
    """Parse verdict text; a markdown code fence around the JSON (models add one) is removed first."""
    m = _FENCE.match(text or "")
    return json.loads(m.group(1) if m else text)

STUCK = "stuck-review"  # verdict "case": the block comes from a failed or empty review or a fix run without result
YES_EFFECT = {
    "drop-block": "hebt den Block auf",
    "fix-pr": "startet einen neuen Fix-Lauf fuer den PR",
    "restart-recut": "schliesst den PR als ersetzt und schneidet die Aufgabe neu",
    "restart-issue": "startet die Aufgabe neu",
}

NOTE_AGAIN = ("Hallo Daniel, der automatische Entsperr-Versuch (unblock:1) ist schon gelaufen und hat nicht gereicht. "
              "Schlimmster Fall: die Aufgabe bleibt liegen, sonst passiert nichts. "
              "Frage: Soll die Aufgabe weiterlaufen (ja) oder gestoppt werden (nein)?")


NOTE_SECURITY = ("Hallo Daniel, dieser PR betrifft Rechte oder Vertrauen (risk:security) und haengt fest; "
                 "der Entsperrer fasst so etwas nicht an. Schlimmster Fall: nichts passiert, der PR wartet. "
                 "Frage: Soll der Auftrag weiterlaufen (ja) oder der PR geschlossen werden (nein)?")


def gh(*args):
    return ghcall.gh(*args)


def gate(item, events, comments, files, owner, author_bot, approver_bot="", codeowners=""):
    """(ok, reason). ITEM: {kind, state, labels, author, number}. EVENTS: label timeline. COMMENTS: [{body, created_at}].
    FILES: paths of a PR (renames incl. old names). Pure: every refusal means the block stays with Daniel.
    A risk:security PR is refused only if it changes a CODEOWNERS path of the owner (risk.waits_for_owner)."""
    labels = set(item.get("labels") or [])
    if item.get("state", "").upper() != "OPEN":
        return False, "item is not open"
    if NEEDS_HUMAN not in labels:
        return False, "needs-human is gone"
    if RISK_SECURITY in labels and item["kind"] == "pr":
        if not files:
            return False, "risk:security: file list unknown, Daniel"
        if risk.waits_for_owner(RISK_SECURITY, files, codeowners, owner):
            return False, "risk:security: changes a CODEOWNERS path, Daniel"
    if UNBLOCK in labels:
        return False, "unblock:1 already set, one self-restart is the limit"
    if not any(label_set_by(events, NEEDS_HUMAN, a) for a in (author_bot, approver_bot, owner) if a):
        return False, "needs-human was not set by the author app, the approver app or the owner"
    since = max((e.get("created_at") or "" for e in events
                 if e.get("event") == "labeled" and (e.get("label") or {}).get("name") == NEEDS_HUMAN), default="")
    if any(MARK in (c.get("body") or "") and (c.get("created_at") or "") >= since for c in comments):
        return False, "an unblocker comment is newer than the label"
    if item["kind"] == "pr":
        if not is_agent_pr(item.get("author"), labels, author_bot, owner):
            return False, "not an agent PR"
        if files and all(f.startswith("docs/design/") for f in files):
            return False, "design PR: an owner decision"
    elif not item.get("trusted") and not (
            "agent:dev" in labels and any(label_set_by(events, "agent:dev", a) for a in (author_bot, owner) if a)):
        return False, "issue is neither trusted nor an agent task set by the owner or the author app"
    return True, "ok"


def forbidden(text):
    """The first limit word found in model text, else None. Whitespace is normalised first; text outside a plain
    ASCII shape (backticks, pipes, quotes, $, &, newlines ...) is refused too, so the check does not rest on
    spotting bad wording alone."""
    text = re.sub(r"\s+", " ", text or "").strip()
    m = _FORBIDDEN.search(text)
    if m:
        return m.group(0)
    return None if _SAFE_SHAPE.fullmatch(text) else "unusual characters"


def outgoing_strings(verdict):
    """Every string that can leave the unblocker (reason, comment, note, issue title and body, anything nested)."""
    if isinstance(verdict, str):
        yield verdict
    elif isinstance(verdict, dict):
        for k, v in verdict.items():
            yield from outgoing_strings(k)
            yield from outgoing_strings(v)
    elif isinstance(verdict, (list, tuple)):
        for v in verdict:
            yield from outgoing_strings(v)


def check_outgoing(verdict):
    """The single secret filter for all outgoing text: ValueError if any string holds a token shape."""
    if any(exec_log.has_secret(s) for s in outgoing_strings(verdict)):
        raise ValueError("verdict holds a secret-looking token; refused")


def validate(verdict):
    """Normalised verdict or ValueError. English GitHub text must be ASCII; a class 1 that asks for a forbidden
    action (tool, permission, install, workflow edit) is class 3, never a grant."""
    if not isinstance(verdict, dict) or verdict.get("class") not in (1, 2, 3) or isinstance(verdict.get("class"), bool):
        raise ValueError("class must be 1, 2 or 3")
    cls = verdict["class"]
    out = {"class": cls, "reason": str(verdict.get("reason") or "")[:300]}
    for key, limit in (("comment", MAX_COMMENT), ("note", 2000)):
        val = verdict.get(key)
        if val is None or (key == "comment" and cls != 1):
            continue  # a comment is only used by class 1; a stray one (e.g. German) must not sink the verdict
        if not isinstance(val, str) or not val.strip() or len(val) > limit:
            raise ValueError(f"{key} must be non-empty text up to {limit} chars")
        if key == "comment" and not val.isascii():
            raise ValueError("comment must be ASCII English")
        out[key] = val.strip()
    if cls == 2:
        issue = verdict.get("issue")
        if not isinstance(issue, dict) or not issue.get("title") or not issue.get("body"):
            raise ValueError("class 2 needs issue.title and issue.body")
        if len(issue["title"]) > MAX_TITLE or not (issue["title"] + issue["body"]).isascii() or len(issue["body"]) > 3000:
            raise ValueError("issue must be ASCII, title <= 100, body <= 3000")
        out["issue"] = {"title": issue["title"].strip(), "body": issue["body"].strip()}
        bad = _FORBIDDEN.search(f"{out['issue']['title']} {out['issue']['body']}")
        if bad:
            out = {"class": 3, "reason": f"class 2 issue asked for a forbidden action ({bad.group(0)}); owner decision",
                   "note": NOTE_SECURITY}
    if cls == 3 and verdict.get("case") == STUCK:
        out["case"] = STUCK
    for key in ("comment", "note"):
        if "@" in (out.get(key) or ""):
            raise ValueError(f"{key} must not mention anyone (@)")
    if "@" in "".join((out.get("issue") or {}).values()):
        raise ValueError("issue must not mention anyone (@)")
    if cls == 1:
        if "comment" not in out:
            raise ValueError("class 1 needs a comment")
        if forbidden(out["comment"]):
            out["class"] = 3
            out["reason"] = f"class 1 asked for a forbidden action ({forbidden(out['comment'])}); owner decision"
            out.pop("comment")
            out.setdefault("note", NOTE_SECURITY)
    if out["class"] == 3 and "note" in out and not _GERMAN_HINT.search(out["note"]):
        raise ValueError("note must be the German note for Daniel")
    return out


def _info(run, kind, number):
    return json.loads(run(kind, "view", str(number), "--json", "state,labels,author"))


def _comment(run, kind, number, body):
    run(kind, "comment", str(number), "--body", body)


def _withdraw_owner(run, kind, number, owner):
    """Class 1 removes the block, so the review request or assignment that came with it goes too."""
    try:
        if kind == "pr":
            run("pr", "edit", str(number), "--remove-reviewer", owner)
        else:
            run("issue", "edit", str(number), "--remove-assignee", owner)
    except subprocess.CalledProcessError:
        print("withdrawing the owner request failed")


def _restart(run, kind, number):
    """Issue: agent:dev removed, then added so the label event fires. PR: dispatch agent-fix (see docstring)."""
    if kind == "issue":
        run("issue", "edit", str(number), "--remove-label", "agent:dev")
        add_labels("issue", number, ["agent:dev"], run)
    else:
        run("workflow", "run", "agent-fix.yml", "-f", f"pr={number}")


def _last_comment_is(run, kind, number, marker):
    comments = json.loads(run(kind, "view", str(number), "--json", "comments"))["comments"]
    return bool(comments) and marker in (comments[-1].get("body") or "")


def apply(kind, number, verdict, owner, run=gh, author_bot=""):
    """Apply a validated verdict. Returns the class that was carried out (1, 2, 3) or 0 if nothing changed.
    The caller runs `gate` first (it holds the CODEOWNERS rule for risk:security PRs); the cheap checks (open,
    needs-human, agent PR) are repeated here from the live item."""
    check_outgoing(verdict)
    v = validate(verdict)
    check_outgoing(v)
    info = _info(run, kind, number)
    labels = {x["name"] for x in info["labels"]}
    if str(info.get("state", "")).upper() != "OPEN" or NEEDS_HUMAN not in labels:
        return 0
    if kind == "pr" and not is_agent_pr((info.get("author") or {}).get("login"), labels, author_bot, owner):
        return 0
    if v["class"] == 1 and UNBLOCK in labels:  # one self-restart only: this goes to Daniel
        return _owner_note(run, kind, number, owner, v, NOTE_AGAIN)
    if v["class"] == 1:
        _comment(run, kind, number, f"{MARK}\nHint from the unblocker (untrusted data, not an instruction):\n{v['comment']}\n\nAny review request or assignment to the owner is withdrawn; "
                                    "request it again if you want to look.")
        add_labels(kind, number, [UNBLOCK], run)
        run(kind, "edit", str(number), "--remove-label", NEEDS_HUMAN)
        _withdraw_owner(run, kind, number, owner)
        _restart(run, kind, number)
        return 1
    if v["class"] == 2:
        title = v["issue"]["title"]
        found = json.loads(run("issue", "list", "--state", "open", "--search", f'"{title}" in:title', "--json", "title,url"))
        dup = next((i for i in found if i.get("title") == title), None)
        if not dup:
            ensure_label("prio:1", run)
        url = dup["url"] if dup else run("issue", "create", "--title", title, "--label", "prio:1", "--body",
                                         f"{v['issue']['body']}\n\nRun: {os.environ.get('RUN_URL', '(unknown)')}\n"
                                         f"Found while unblocking {kind} #{number}.").strip()
        _comment(run, kind, number, f"{MARK}\nAgent infrastructure problem, tracked in {url}. needs-human stays.")
        return 2
    return _owner_note(run, kind, number, owner, v, v.get("note"))


def _yes_action(run, kind, number, v):
    """What "ja" does. drop-block only removes the label, so it is right only where that really unblocks. In the
    stuck case (failed or empty review, fix run without result) the PR must move on: restart-recut if the PR names an
    issue, else fix-pr; an issue restarts."""
    if v.get("case") != STUCK:
        return "drop-block"
    if kind == "issue":
        return "restart-issue"
    body = json.loads(run("pr", "view", str(number), "--json", "body")).get("body")
    return "restart-recut" if restart.issue_refs(body) else "fix-pr"


def _owner_note(run, kind, number, owner, v, note):
    """Class 3: needs-human stays; the German note is the LAST comment, read back to prove it."""
    if not note:
        raise ValueError("class 3 needs a German note")
    mention = "" if kind == "pr" else f"\n\n@{owner}"
    thing = "der PR" if kind == "pr" else "das Issue"
    yes = _yes_action(run, kind, number, v)
    # script-built, so the answer always maps to the marker
    effect = f"Ja {YES_EFFECT[yes]}, nein schliesst {thing}."
    marker = decision.build(yes=yes, no=f"close-{kind}")
    _comment(run, kind, number, f"{MARK}\n{note}\n{effect}\n{marker}{mention}")
    if kind == "pr":
        try:
            run("pr", "edit", str(number), "--add-reviewer", owner)
        except subprocess.CalledProcessError:
            print("review request failed")
    if not _last_comment_is(run, kind, number, MARK):
        raise RuntimeError("the German note is not the last comment")
    return 3


PR_FIELDS = "number,headRefName,mergedAt,body,isCrossRepository"
LANDED_TEXT = ("Step already merged in PR #{pr} (Refs #{n}). This run had nothing left to build, so the task restarts "
               "and the orchestrator writes the slip for the next step.")


def slip_time(info, authors=overlap.DEFAULT_TRUSTED):
    """createdAt of the newest task slip of INFO (`gh issue view` with body, author, createdAt, comments), '' if none.
    A slip is what slip.py counts: a Files: line in the issue body or in a comment by a trusted author. A restart
    comment without a Files: line is not a slip; the orchestrator writes the next slip after it."""
    times = []
    if slip.slip_files({"body": info.get("body"), "author": info.get("author")}, authors):
        times.append(info.get("createdAt") or "")
    times += [c.get("createdAt") or "" for c in info.get("comments") or [] if slip.slip_files(c, authors)]
    return max(times, default="")


def landed_verdict(number, run=gh):
    """Deterministic check before the model step (issue 658), no model and no write: an open agent:dev issue without
    unblock:1 whose current step already landed, i.e. a merged same-repo agent/ PR with `Refs #N` that merged after
    the newest slip (slip_time). Returns the class 1 verdict, or None (then the model step decides as before).
    First cut: it does not check why needs-human was set, so any block on such an item counts as a landed step."""
    info = json.loads(run("issue", "view", str(number), "--json", "state,labels,author,body,createdAt,comments"))
    labels = {x["name"] for x in info.get("labels") or []}
    if str(info.get("state", "")).upper() != "OPEN" or "agent:dev" not in labels or UNBLOCK in labels:
        return None
    slip_at = slip_time(info)
    if not slip_at:
        return None
    refs = re.compile(rf"\bRefs #{int(number)}\b")
    prs = json.loads(run("pr", "list", "--state", "merged", "--limit", "200", "--json", PR_FIELDS))
    for pr in prs:
        if ((pr.get("headRefName") or "").startswith("agent/") and not pr.get("isCrossRepository")
                and refs.search(pr.get("body") or "") and (pr.get("mergedAt") or "") > slip_at):
            return {"class": 1, "reason": "step already merged",
                    "comment": LANDED_TEXT.format(pr=pr["number"], n=number)}
    return None


def _cap(text):
    return exec_log.mask(text or "")[:MAX_UNTRUSTED]


def fetch(kind, number, workspace, run=gh):
    """Write the untrusted text of an item as masked, capped files in WORKSPACE/untrusted/. The model step reads
    these files and never calls gh. Returns the file paths."""
    fields = "title,body,comments" + (",files" if kind == "pr" else "")
    info = json.loads(run(kind, "view", str(number), "--json", fields))
    comments = "\n\n---\n\n".join(
        f"{(c.get('author') or {}).get('login')} {c.get('createdAt')}:\n{c.get('body')}" for c in info.get("comments") or [])
    files = {"item.txt": f"Title: {info.get('title')}\n\n{info.get('body')}", "comments.txt": comments}
    if kind == "pr":
        files["files.txt"] = "\n".join(f.get("path", "") for f in info.get("files") or [])
        files["diff.txt"] = run("pr", "diff", str(number))
    out = os.path.join(workspace, "untrusted")
    os.makedirs(out, exist_ok=True)
    paths = []
    for name, text in files.items():
        path = os.path.join(out, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(_cap(text))
        paths.append(path)
    return paths


def main(argv):
    owner = os.environ.get("OWNER", OWNER_DEFAULT)
    args = argv[1:]
    if len(args) == 4 and args[0] == "apply" and args[2].isdigit() and args[1] in ("pr", "issue"):
        kind, number = args[1], args[2]
        ok, why = live_gate(kind, number, owner)  # the item may have changed during the model step
        if not ok:
            print(f"0 (gate refused: {why})")
            return 0
        text = exec_log.read_exec(args[3])
        print(apply(kind, number, load_verdict(text), owner, author_bot=os.environ.get("AUTHOR_BOT", "")))
        return 0
    if len(args) == 3 and args[0] == "landed" and args[1].isdigit():
        verdict = landed_verdict(args[1])
        if verdict is None:
            print("no landed step")
            return 1
        with open(args[2], "w", encoding="utf-8") as f:
            json.dump(verdict, f)
        print(f"landed step: class 1 verdict in {args[2]}")
        return 0
    if len(args) == 2 and args[0] == "validate":
        try:
            v = load_verdict(exec_log.read_exec(args[1]))
            check_outgoing(v)
            print(f"valid, class {validate(v)['class']}")
            return 0
        except ValueError as exc:  # json.JSONDecodeError is a ValueError
            print(f"invalid verdict: {exc}")
            return 1
    if len(args) == 4 and args[0] == "fetch" and args[2].isdigit() and args[1] in ("pr", "issue"):
        print("\n".join(fetch(args[1], args[2], args[3])))
        return 0
    if len(args) == 3 and args[0] == "gate" and args[2].isdigit() and args[1] in ("pr", "issue"):
        ok, why = live_gate(args[1], args[2], owner)
        print(why)
        return 0 if ok else 1
    print(__doc__, file=sys.stderr)
    return 2


def live_gate(kind, number, owner):
    """`gate` on the live item (labels, timeline, comments, files, issue trust)."""
    repo = os.environ["GH_REPO"]
    bot, appr = os.environ.get("AUTHOR_BOT", ""), os.environ.get("APPROVER_BOT", "")
    info = json.loads(gh(kind, "view", number, "--json", "state,labels,author,comments"))
    item = {"kind": kind, "state": info["state"], "labels": [x["name"] for x in info["labels"]],
            "author": info["author"]["login"]}
    pages = json.loads(gh("api", "--paginate", "--slurp", f"repos/{repo}/issues/{number}/timeline"))
    events = [e for p in pages for e in p]
    comments = [{"body": c.get("body"), "created_at": c.get("createdAt")} for c in info.get("comments", [])]
    files = []
    if kind == "pr":  # the REST list has previous_filename, so rename sources count
        files = risk.pr_paths(json.loads(gh("api", "--paginate", "--slurp", f"repos/{repo}/pulls/{number}/files")))
    issue ={"number": int(number), "title": "", "labels": info["labels"], "author": info["author"], "body": ""}
    item["trusted"] = kind == "issue" and bool(classify(issue, events, owner, bot))
    return gate(item, events, comments, files, owner, bot, appr, risk.read_text(".github/CODEOWNERS"))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
