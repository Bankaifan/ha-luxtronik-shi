"""Post the security reviewer's verdict from the model's final output (the model has no write or comment tools).

  post_verdict.py NUMBER SHA    env: EXEC_FILE (execution file of claude-code-action), GH_TOKEN, GH_REPO, RUNNER_TEMP

The final reply must contain a line `security-review: approve|changes <SHA>`; that line and everything after it is
posted as one PR comment (secrets masked). A `changes` verdict also gets a request-changes review by the same app and the
round label review:N is bumped, so agent-fix starts a normal fix round. No verdict: the denied tool calls are printed and the exit code is 1.
"""
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import agent_guard

LINE = re.compile(r"^\s*`?security-review: (approve|changes) ([0-9a-f]{7,40})`?\s*$", re.IGNORECASE | re.MULTILINE)
MAX_CHARS = 6000


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


def bump_round(number, run=gh):
    """Count the round like agent-review does (review:1 -> 2 -> 3). agent-fix starts a fix on review:1/2 and applies
    the round limit on review:3. Returns False when review:3 was already set (the limit was handled before)."""
    labels = set(run("pr", "view", str(number), "--json", "labels", "--jq", ".labels[].name").split())
    if "review:3" in labels:
        return False
    nxt = "review:3" if "review:2" in labels else "review:2" if "review:1" in labels else "review:1"
    agent_guard.add_labels("pr", number, [nxt], run)
    return True


def post(number, sha, exec_text, run=gh, tmpdir=None):
    got = extract(final_text(exec_text), sha)
    if not got:
        print("post_verdict: no verdict line for this SHA in the final output")
        for line in agent_guard.denied_calls(exec_text) or ["(no denied tool calls)"]:
            print(f"  denied: {line}")
        return 1
    kind, body = got
    fd, path = tempfile.mkstemp(suffix=".md", dir=tmpdir or os.environ.get("RUNNER_TEMP") or None)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body + "\n")
    run("pr", "comment", str(number), "--body-file", path)
    if kind == "changes" and bump_round(number, run):
        run("pr", "review", str(number), "--request-changes", "--body",
            f"Security review asks for changes at {sha[:7]}: see the `security-review: changes` comment.")
    print(f"post_verdict: {kind} posted for #{number}")
    return 0


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    return post(argv[1], argv[2], agent_guard.read_exec(os.environ.get("EXEC_FILE", "")))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
