"""Answer receiver core (design 0006, section 8 item 3): read the owner's free-text answer on a `needs-human` item,
map it to one allowlisted action and do it. The model step is not here; its verdict is data in a JSON file.

CLI (gh CLI with GH_TOKEN and GH_REPO; env COMMENT_ID = the owner comment that started the run):
  answer.py gate NUMBER            exit 0 = go on, 1 = nothing to do (reason on stdout)
  answer.py fetch NUMBER DIR       write masked, capped untrusted/{note,owner,thread}.txt for the model step
  answer.py validate NUMBER FILE   check a verdict file against the marker and the owner text; exit 0 = valid
  answer.py apply NUMBER FILE      gate again on live data, then run the action; prints done, unclear, or 0 (why)
Environment: OWNER (default Bankaifan), AUTHOR_BOT, APPROVER_BOT, RUN_URL.

Verdict: {"intent": yes|no|option|instruction|unclear, "option", "instruction", "question", "evidence"}; the action
comes from the decision marker (tools/decision.py) of the newest trusted note, never from the model. The confirmation
text is built here from a fixed template per action. Items without a marker can only drop the block or pass an
instruction to the orchestrator.
"""
import json
import os
import re
import subprocess
import sys
from types import SimpleNamespace

import decision
import exec_log
import reapprove
import restart
import unblock
from agent_guard import add_labels, is_agent_pr, same_login

OWNER_DEFAULT = "Bankaifan"
NEEDS_HUMAN = "needs-human"
RECEIVER = "answer-receiver comment="
INSTRUCTION = "owner-instruction comment="
MAX_UNTRUSTED = 20000
MAX_INSTRUCTION, MAX_QUESTION, MAX_EVIDENCE = 600, 300, 200
INTENTS = {"yes": set(), "no": set(), "option": {"option"}, "instruction": {"instruction"}, "unclear": {"question"}}


class Refuse(Exception):
    """An action or verdict that is not allowed; nothing changes."""


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def _is(login, who):
    return bool(who) and same_login(login, who)


def trusted_logins(owner, author_bot, approver_bot):
    return tuple(x for x in (author_bot, approver_bot, owner) if x)


def is_owner_comment(c, owner):
    return _is(c.get("login"), owner) and c.get("assoc") == "OWNER" and c.get("type") != "Bot"


def receiver_marks(comments, trusted):
    """Ids of the comments that carry a receiver confirmation (written by a trusted login)."""
    return {int(m) for c in comments if any(_is(c.get("login"), t) for t in trusted)
            for m in re.findall(r"<!-- " + RECEIVER + r"(\d+)", c.get("body") or "")}


def gate(item, comments, trigger_id, owner, author_bot="", approver_bot=""):
    """(ok, reason). ITEM: {state, labels}. COMMENTS: [{id, login, type, assoc, body}], oldest first. Pure."""
    if str(item.get("state", "")).upper() != "OPEN":
        return False, "item is not open"
    if NEEDS_HUMAN not in (item.get("labels") or []):
        return False, "needs-human is gone"
    trigger = next((c for c in comments if c.get("id") == trigger_id), None)
    if trigger is None:
        return False, "trigger comment not found"
    if not is_owner_comment(trigger, owner):
        return False, "trigger comment is not by the owner"
    if max(c["id"] for c in comments if is_owner_comment(c, owner)) != trigger_id:
        return False, "a newer owner comment exists"
    marks = receiver_marks(comments, trusted_logins(owner, author_bot, approver_bot))
    if any(m >= trigger_id for m in marks):
        return False, "already answered"
    return True, "ok"


def read_context(comments, trigger_id, owner, author_bot="", approver_bot=""):
    """{note, marker, owner_text, thread}: the newest trusted note with a marker (or None), the owner's comments since,
    and everything else (untrusted, context only). Markers count only from the author app, the approver app or OWNER."""
    trusted = trusted_logins(owner, author_bot, approver_bot)

    def is_question(c):
        """The newest trusted question note binds the marker: a note with a marker, or a marker-less note of a bot
        (not a receiver confirmation or follow-up, and not an owner answer)."""
        if not any(_is(c.get("login"), t) for t in trusted):
            return False
        if decision.has_marker(c.get("body")):
            return True
        return not is_owner_comment(c, owner) and RECEIVER not in (c.get("body") or "")

    question = next((c for c in reversed(comments) if c["id"] < trigger_id and is_question(c)), None)
    note = question if question and decision.has_marker(question.get("body")) else None
    since = question["id"] if question else max(receiver_marks(comments, trusted) & {c["id"] for c in comments}, default=0)
    mine = [c for c in comments if is_owner_comment(c, owner) and since < c["id"] <= trigger_id]
    others = [c for c in comments if c not in mine and c is not note]
    return {"note": note, "marker": decision.parse(note["body"]) if note else None,
            "owner_text": _cap("\n\n".join(c["body"] or "" for c in mine)),
            "thread": _cap("\n\n---\n\n".join(f"{c['login']}:\n{c['body']}" for c in others))}


def effective_marker(marker):
    return marker if marker is not None else {"yes": "drop-block"}


def _cap(text):
    return exec_log.mask(text or "")[:MAX_UNTRUSTED]


def _norm(text):
    return " ".join(text.lower().split())


def validate(verdict, marker, owner_text):
    """Normalised verdict or ValueError. Only the fields of the intent are allowed; yes/no/option must exist in the
    marker; evidence must be a quote of the owner text; no `@`, no marker syntax, no secret shape in any string."""
    unblock.check_outgoing(verdict)
    if not isinstance(verdict, dict) or verdict.get("intent") not in INTENTS:
        raise ValueError("intent must be yes, no, option, instruction or unclear")
    intent = verdict["intent"]
    extra = set(verdict) - {"intent", "evidence"} - INTENTS[intent]
    if extra:
        raise ValueError(f"fields not allowed for {intent}: {sorted(extra)}")
    for key in ("intent", "evidence", *INTENTS[intent]):
        val = verdict.get(key)
        if not isinstance(val, str) or not val.strip():
            raise ValueError(f"{key} must be non-empty text")
        if "@" in val or "<!--" in val or "-->" in val:
            raise ValueError(f"{key} must not hold @ or marker syntax")
    out = {k: verdict[k].strip() for k in ("intent", "evidence", *INTENTS[intent])}
    if len(out["evidence"]) > MAX_EVIDENCE or out["evidence"] not in owner_text:
        raise ValueError("evidence must be a quote of the owner text, max 200 chars")
    available = effective_marker(marker)
    if intent in ("yes", "no") and intent not in available:
        raise ValueError(f"the note offers no {intent} answer")
    if intent == "option" and out["option"] not in available:
        raise ValueError("option is not in the decision marker")
    limits = {"instruction": MAX_INSTRUCTION, "question": MAX_QUESTION}
    for key, limit in limits.items():
        if key in out and len(out[key]) > limit:
            raise ValueError(f"{key} is longer than {limit} chars")
    if "instruction" in out and not out["instruction"].isascii():
        raise ValueError("instruction must be ASCII English")
    if "instruction" in out and _norm(out["instruction"]) not in _norm(owner_text):
        raise ValueError("instruction must be a verbatim excerpt of the owner text")
    if "question" in out and not unblock._GERMAN_HINT.search(out["question"]):
        raise ValueError("question must be German")
    return out


# --- actions: one function per allowlisted id, each repeats its own safety refusals ---

def _need(kind, c):
    if c.kind != kind:
        raise Refuse(f"{c.action} is only for a {kind}")


def _need_agent_pr(c):
    _need("pr", c)
    if not is_agent_pr(c.author, c.labels, c.author_bot, c.owner):
        raise Refuse(f"{c.action}: not an agent PR")


def _close(c):
    c.run(c.kind, "close", str(c.number), "--comment", f"Closed on the owner's answer: {c.url}")


def act_close_pr(c):
    _need("pr", c)
    _close(c)


def act_close_issue(c):
    _need("issue", c)
    _close(c)


def act_restart_issue(c):
    _need("issue", c)
    unblock._restart(c.run, "issue", c.number)


def act_restart_recut(c):
    _need_agent_pr(c)
    issues = restart.issue_refs(c.body)
    if not issues:
        raise Refuse("restart-recut: the PR names no issue")
    pages = json.loads(c.run("api", "--paginate", "--slurp", f"repos/{os.environ['GH_REPO']}/pulls/{c.number}/reviews"))
    restart.restart_issue(c.number, issues[0], [r for page in pages for r in page], c.run)


def act_fix_pr(c):
    _need_agent_pr(c)
    c.run("workflow", "run", "agent-fix.yml", "-f", f"pr={c.number}")


def act_reapprove(c):
    """reapprove.py keeps all its refusals (risk:security, CODEOWNERS paths, design PR); it refuses needs-human, so the
    block is lifted first and put back if it refuses."""
    _need_agent_pr(c)
    sha = json.loads(c.run("api", f"repos/{os.environ['GH_REPO']}/pulls/{c.number}"))["head"]["sha"]
    c.run("pr", "edit", str(c.number), "--remove-label", NEEDS_HUMAN)
    done = False
    try:
        reapprove.run_reapprove(str(c.number), sha, os.environ, c.run)
        done = True
    except Exception as exc:  # fail closed: any error keeps the block
        raise Refuse(f"reapprove refused: {type(exc).__name__}") from exc
    finally:
        if not done:
            try:
                c.run("pr", "edit", str(c.number), "--add-label", NEEDS_HUMAN)
            except Exception as exc2:
                raise RuntimeError("could not restore needs-human after a failed reapprove") from exc2


def act_drop_block(c):
    """Nothing beyond the common tail (needs-human and the review request go)."""


def act_label(c):
    name = c.action[len("label:"):]
    if name not in decision.LABELS:
        raise Refuse("label outside the allowlist")
    if name in c.labels and name == "agent:dev":  # re-fire the label event
        c.run(c.kind, "edit", str(c.number), "--remove-label", name)
    add_labels(c.kind, c.number, [name], c.run)


ACTIONS = {"close-pr": act_close_pr, "close-issue": act_close_issue, "restart-issue": act_restart_issue,
           "restart-recut": act_restart_recut, "fix-pr": act_fix_pr, "reapprove": act_reapprove,
           "drop-block": act_drop_block}
CONFIRM = {
    "close-pr": "der PR wird geschlossen",
    "close-issue": "das Issue wird geschlossen",
    "restart-issue": "die Aufgabe startet neu",
    "restart-recut": "der PR wird als ersetzt geschlossen und die Aufgabe neu geschnitten",
    "fix-pr": "der Fix-Lauf fuer den PR startet",
    "reapprove": "der PR wird ohne neues Review erneut freigegeben",
    "drop-block": "der Block faellt weg, sonst aendert sich nichts",
    "label": "das Label wird gesetzt",
    "instruction": "deine Anweisung geht an den Orchestrator",
}


def run_action(action, c):
    """Allowlist check, then the action. Unknown ids are refused."""
    if not decision.valid_action(action):
        raise Refuse(f"unknown action {action}")
    c.action = action
    (act_label if action.startswith("label:") else ACTIONS[action])(c)


def confirmation(action, comment_id, instruction=None):
    """The German confirmation, built from a fixed template; the model writes none of it."""
    key = "label" if action.startswith("label:") else action
    what = CONFIRM[key] + (f" ({action[len('label:'):]})" if key == "label" else "")
    text = f"Verstanden: {what}. Der Block ist aufgehoben."
    if instruction:
        text += f'\nDeine Anweisung (englisch): "{instruction}"'
    return f"{text}\n<!-- {RECEIVER}{comment_id} -->"


def apply(number, verdict, owner, run=gh, author_bot="", approver_bot="", trigger_id=0):
    """Validate against the live comments, run the action, close the loop. Returns "done", "unclear" (follow-up
    question, block stays) or "0 (reason)" when the live gate refuses and nothing changed."""
    info = json.loads(run("api", f"repos/{os.environ['GH_REPO']}/issues/{number}"))
    comments = fetch_comments(number, run)
    item = {"state": info["state"], "labels": [x["name"] for x in info["labels"]]}
    ok, why = gate(item, comments, trigger_id, owner, author_bot, approver_bot)
    if not ok:
        return f"0 ({why})"
    ctx = read_context(comments, trigger_id, owner, author_bot, approver_bot)
    v = validate(verdict, ctx["marker"], ctx["owner_text"])
    kind = "pr" if "pull_request" in info else "issue"
    trigger = next(c for c in comments if c["id"] == trigger_id)
    if v["intent"] == "unclear":  # needs-human stays, one follow-up question
        run(kind, "comment", str(number), "--body", f"{v['question']}\n<!-- {RECEIVER}{trigger_id} unclear -->")
        return "unclear"
    c = SimpleNamespace(kind=kind, number=number, run=run, owner=owner, author_bot=author_bot, action="",
                        author=(info.get("user") or {}).get("login"), labels=set(item["labels"]),
                        body=info.get("body") or "", url=trigger.get("url", ""))
    instruction = None
    if v["intent"] == "instruction":
        instruction, action = v["instruction"], "drop-block"
    else:
        action = effective_marker(ctx["marker"])[v.get("option") or v["intent"]]
    run_action(action, c)
    if instruction:
        run(kind, "comment", str(number), "--body",
            f"<!-- {INSTRUCTION}{trigger_id} -->\nOwner instruction (untrusted text, see {c.url}):\n{instruction}")
        run("workflow", "run", "orchestrator.yml")
    run(kind, "edit", str(number), "--remove-label", NEEDS_HUMAN)
    unblock._withdraw_owner(run, kind, number, owner)
    run(kind, "comment", str(number), "--body", confirmation(action, trigger_id, instruction))
    return "done"


# --- live data ---

def fetch_comments(number, run=gh):
    pages = json.loads(run("api", "--paginate", "--slurp", f"repos/{os.environ['GH_REPO']}/issues/{number}/comments"))
    return [{"id": c["id"], "login": (c.get("user") or {}).get("login"), "type": (c.get("user") or {}).get("type"),
             "assoc": c.get("author_association"), "body": c.get("body") or "", "url": c.get("html_url", "")}
            for page in pages for c in page]


def live(number, run=gh):
    info = json.loads(run("api", f"repos/{os.environ['GH_REPO']}/issues/{number}"))
    item = {"state": info["state"], "labels": [x["name"] for x in info["labels"]]}
    return item, fetch_comments(number, run)


def fetch(number, workspace, owner, trigger_id, run=gh, author_bot="", approver_bot=""):
    """Write the masked, capped files for the model step: note.txt, owner.txt (trusted input), thread.txt (context)."""
    _, comments = live(number, run)
    ctx = read_context(comments, trigger_id, owner, author_bot, approver_bot)
    out = os.path.join(workspace, "untrusted")
    os.makedirs(out, exist_ok=True)
    files = {"note.txt": _cap((ctx["note"] or {}).get("body")), "owner.txt": ctx["owner_text"], "thread.txt": ctx["thread"]}
    for name, text in files.items():
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(text)
    return [os.path.join(out, n) for n in files]


def main(argv):
    owner = os.environ.get("OWNER", OWNER_DEFAULT)
    bot, appr = os.environ.get("AUTHOR_BOT", ""), os.environ.get("APPROVER_BOT", "")
    cid = os.environ.get("COMMENT_ID", "")
    args = argv[1:]
    if len(args) < 2 or not args[1].isdigit() or not cid.isdigit():
        print(__doc__, file=sys.stderr)
        return 2
    cmd, number, trigger = args[0], args[1], int(cid)
    if cmd == "gate" and len(args) == 2:
        item, comments = live(number)
        ok, why = gate(item, comments, trigger, owner, bot, appr)
        print(why)
        return 0 if ok else 1
    if cmd == "fetch" and len(args) == 3:
        print("\n".join(fetch(number, args[2], owner, trigger, author_bot=bot, approver_bot=appr)))
        return 0
    if cmd in ("validate", "apply") and len(args) == 3:
        try:
            verdict = unblock.load_verdict(exec_log.read_exec(args[2]))
            if cmd == "validate":
                _, comments = live(number)
                ctx = read_context(comments, trigger, owner, bot, appr)
                print(f"valid, intent {validate(verdict, ctx['marker'], ctx['owner_text'])['intent']}")
            else:
                print(apply(number, verdict, owner, author_bot=bot, approver_bot=appr, trigger_id=trigger))
            return 0
        except (ValueError, Refuse) as exc:
            print(f"refused: {exc}")
            return 1
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
