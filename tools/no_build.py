"""A developer run that has nothing to build says so instead of ending silently (no model).

The developer writes one short line to `.agent-out/nothing-to-build.md` when the slip is already done or the cause lies
outside this repo, and opens no PR. Without this the run counted as silent: one retry, then a signed issue
`Agent dev runs end silently on #N` for a run that was right (roblox_energy #368, #375).

  python3 tools/no_build.py settle ISSUE FILE    exit 0: settled, the silent-run guard is not needed; exit 1: no valid
                                                 file, the guard runs as before

settle: one comment with the hidden marker MARK and the developer's line, then `agent:dev` is removed. tools/prefilter.py
reads the marker like a merged step: the dispatcher does not start the old slip again and the orchestrator writes the
next slip (or parks the issue). A line that starts with `complete:` also closes the issue, but only when a merged
same-repo `agent/` PR names it (`Refs #N` or `Closes #N`): the model's word alone closes nothing.
The file is read as data: a regular file inside `.agent-out` (no symlink), at most MAX_BYTES of printable ASCII, at
most 3 lines, no token; `@` and comment markers are taken out before it is posted. Needs the gh CLI (GH_TOKEN, GH_REPO).
"""
import json
import os
import pathlib
import re
import subprocess
import sys

import exec_log
import liveness
import prefilter

MARK = prefilter.NOTHING_MARK
MAX_BYTES = 400
MAX_LINES = 3


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def reason(path, root="."):
    """The developer's line as plain text, or None when the file is missing or not acceptable."""
    p, base = pathlib.Path(path), pathlib.Path(root, ".agent-out")
    try:
        if base.is_symlink() or p.is_symlink() or not p.is_file() or p.resolve().parent != base.resolve():
            return None
        raw = p.read_bytes()
    except OSError:
        return None
    if not raw.strip() or len(raw) > MAX_BYTES:
        return None
    try:
        text = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    if len(lines) > MAX_LINES or any(not (32 <= ord(c) < 127) for x in lines for c in x) or exec_log._SECRET.search(text):
        return None
    text = " ".join(lines).replace("@", "").replace("<!--", "").replace("-->", "").replace("```", "'''")
    return re.sub(r"(?i)\bfiles(\s+touched)?\s*:", r"files\1 -", text)  # never a slip line (overlap.FILES_RE)


def landed(issue, run=gh):
    """A merged same-repo `agent/` PR names the issue with `Refs #N` or `Closes #N`."""
    out = run("pr", "list", "--state", "merged", "--search", f"#{issue} in:body", "--limit", "20", "--json",
              "body,headRefName,isCrossRepository,mergedAt")
    return any(p.get("mergedAt") and int(issue) in prefilter.closing_issues(p.get("body"))
               and (p.get("headRefName") or "").startswith("agent/") and not p.get("isCrossRepository")
               for p in json.loads(out or "[]"))


def settle(issue, path, run=gh, root="."):
    """True when the run was settled (comment posted, agent:dev removed, issue closed when complete and landed)."""
    why = reason(path, root)
    if why is None:
        return False
    try:
        done = why.lower().startswith("complete:") and landed(issue, run)
        url = os.environ.get("RUN_URL", "(unknown)")
        liveness.post_comment("issue", issue, f"{MARK}\nNothing to build in this run: {why}\nRun: {url}", run)
        run("issue", "edit", str(issue), "--remove-label", "agent:dev")
        if done:
            run("issue", "close", str(issue), "--reason", "completed")
    except (subprocess.CalledProcessError, OSError, ValueError, liveness.ReadbackError):
        return False
    return True


def main(argv):
    if len(argv) != 4 or argv[1] != "settle" or not argv[2].isdigit():
        print(__doc__, file=sys.stderr)
        return 2
    if settle(argv[2], argv[3]):
        print(f"issue #{argv[2]}: nothing to build, settled")
        return 0
    print("no valid nothing-to-build file: the silent-run guard decides")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
