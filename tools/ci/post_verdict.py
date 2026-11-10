"""Post the security reviewer's verdict from the model's final output (the model has no write or comment tools).

  post_verdict.py NUMBER SHA    env: EXEC_FILE (execution file of claude-code-action), GH_TOKEN, GH_REPO, RUNNER_TEMP

The final reply must contain a line `security-review: approve|changes <SHA>`; that line and everything after it is
posted as one PR comment (secrets masked). A `changes` verdict also gets a request-changes review by the same app and the
round label review:N is bumped (once per head SHA, shared with agent-review; a verdict for a superseded head is discarded), so agent-fix starts a normal fix round. An `approve` dismisses the app's own open
"Security review asks for changes" reviews (env APPROVER_BOT names the app; unset: nothing is dismissed). No verdict: the denied tool calls are printed and the exit code is 1.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import agent_guard

LINE = re.compile(r"^\s*`?security-review: (approve|changes) ([0-9a-f]{7,40})`?\s*$", re.IGNORECASE | re.MULTILINE)
MAX_CHARS = 6000
REQUEST_PREFIX = "Security review asks for changes"


def final_text(exec_text):
    """Text of the last `result` record, else of the last assistant message."""
    text = ""
    for rec in agent_guard._records(exec_text):
        if rec.get("type") == "result" and isinstance(rec.get("result"), str):
            text = rec["result"]
        elif rec.get("type") == "assistant":
            parts = (rec.get("message") or {}).get("content") or []
            got = "\n".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text")
            text = got or text
    return text


def extract(text, sha):
    """(kind, body) for the last verdict line naming SHA, or None. The body starts at that line."""
    found = None
    for m in LINE.finditer(text or ""):
        if sha.lower().startswith(m.group(2).lower()):
            found = m
    if not found:
        return None
    rest = text[found.end():].strip()
    body = f"security-review: {found.group(1).lower()} {sha}" + (f"\n\n{rest}" if rest else "")
    return found.group(1).lower(), agent_guard._SECRET.sub("***", body)[:MAX_CHARS]


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def bump_round(number, sha, run=gh):
    """Count the round like agent-review does (review:1 -> 2 -> 3), once per head SHA: if the code reviewer already
    counted this head, nothing is bumped. agent-fix starts a fix on review:1/2 and applies the round limit on review:3.
    Returns True when a `changes` review should be requested: the head is newly counted or was counted already
    (the round is open, the fix is still to be started); False at the limit (handled before)."""
    return agent_guard.count_round(number, sha, run) != "limit"


def dismiss_own_requests(number, sha, run=gh, approver=None):
    """After an approve: dismiss the approver app's own open CHANGES_REQUESTED reviews whose body starts with
    REQUEST_PREFIX. Reviews by anyone else, with other bodies or in other states are never touched. A failure here
    must not turn the approve into a crash."""
    approver = approver if approver is not None else os.environ.get("APPROVER_BOT", "")
    if not approver:
        return 0
    try:
        repo = os.environ.get("GH_REPO") or run("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner").strip()
        reviews = json.loads(run("api", "--paginate", "--slurp", f"repos/{repo}/pulls/{number}/reviews") or "[]")
        reviews = [r for page in reviews for r in (page if isinstance(page, list) else [page])]
    except (subprocess.CalledProcessError, OSError, ValueError) as e:
        print(f"post_verdict: could not list reviews for #{number}: {type(e).__name__}")
        return 0
    done = 0
    for r in reviews:
        if not (isinstance(r, dict) and r.get("state") == "CHANGES_REQUESTED"
                and agent_guard.same_login((r.get("user") or {}).get("login"), approver)
                and (r.get("body") or "").startswith(REQUEST_PREFIX) and r.get("id")):
            continue
        try:
            run("api", "-X", "PUT", f"repos/{repo}/pulls/{number}/reviews/{r['id']}/dismissals",
                "-f", f"message=Security review approved {sha[:7]}")
            done += 1
        except (subprocess.CalledProcessError, OSError) as e:
            print(f"post_verdict: could not dismiss review {r['id']} on #{number}: {type(e).__name__}")
    return done


def post(number, sha, exec_text, run=gh, tmpdir=None):
    got = extract(final_text(exec_text), sha)
    if not got:
        print("post_verdict: no verdict line for this SHA in the final output")
        for line in agent_guard.denied_calls(exec_text) or ["(no denied tool calls)"]:
            print(f"  denied: {line}")
        return 1
    kind, body = got
    if agent_guard.is_stale_head(number, sha, run):  # pushed during the review: discard, the next head is reviewed
        print(f"post_verdict: head of #{number} moved past {sha[:7]}; verdict discarded")
        return 0
    fd, path = tempfile.mkstemp(suffix=".md", dir=tmpdir or os.environ.get("RUNNER_TEMP") or None)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body + "\n")
    run("pr", "comment", str(number), "--body-file", path)
    if kind == "changes" and bump_round(number, sha, run):
        run("pr", "review", str(number), "--request-changes", "--body",
            f"Security review asks for changes at {sha[:7]}: see the `security-review: changes` comment.")
    if kind == "approve":
        dismiss_own_requests(number, sha, run)
    print(f"post_verdict: {kind} posted for #{number}")
    return 0


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    return post(argv[1], argv[2], agent_guard.read_exec(os.environ.get("EXEC_FILE", "")))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
