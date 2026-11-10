"""Stage a PR change for the security reviewer as plain files (design 0010, section 4.1).

  stage_review.py [OUTDIR]   read the full unified diff on stdin; env GH_REPO and SHA (optional) fetch the new
                             content of the relevant files. Writes OUTDIR/pr.diff (security-relevant files only),
                             OUTDIR/skipped.txt (path, status, +/- counts) and OUTDIR/files/<path>, prints `turns=<n>`.
Relevant = a path risk.py classes as security or infra, a deleted file, or a test of a SECURITY_FILES tool.
Fail-open: no relevant file or any error stages the full diff. Data only: nothing from the diff is run.
"""
import math
import os
import re
import subprocess
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import risk

MIN_TURNS, MAX_TURNS, LINES_PER_TURN = 12, 30, 1500
SECURITY_STEMS = {os.path.splitext(os.path.basename(p))[0] for p in risk.SECURITY_FILES if p.endswith(".py")}


def split_diff(diff):
    """[(path, status, added, removed, text)] per `diff --git` block; status is added/deleted/renamed/modified."""
    blocks, cur = [], None
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            old, new = risk.parse_header(line)
            cur = {"path": new, "old": old, "status": "modified",
                   "add": 0, "del": 0, "text": [], "body": False}
            blocks.append(cur)
        if cur is None:
            continue
        cur["text"].append(line)
        if line.startswith("@@"):
            cur["body"] = True
        elif not cur["body"]:
            if line.startswith("deleted file mode"):
                cur["status"] = "deleted"
            elif line.startswith("new file mode"):
                cur["status"] = "added"
            elif line.startswith("rename from"):
                cur["status"] = "renamed"
        elif line.startswith("+"):
            cur["add"] += 1
        elif line.startswith("-"):
            cur["del"] += 1
    return blocks


def unsafe(path):
    return not path or path.startswith("/") or ".." in path


def bad(b):
    return unsafe(b["path"]) or unsafe(b["old"])


def is_test_of_security_tool(path):
    m = re.fullmatch(r"tests/test_(.+)\.py", path)
    return bool(m) and any(m.group(1) == s or m.group(1).startswith(s + "_") for s in SECURITY_STEMS)


def relevant(b):
    paths = (b["old"], b["path"])
    if b["status"] == "deleted" and b["path"].startswith("tests/"):
        return True
    if any(p.startswith(risk.SECURITY_FILES + risk.INFRA_PATHS) for p in paths):
        return True
    return is_test_of_security_tool(b["path"]) or is_test_of_security_tool(b["old"])


def turns_for(diff_lines):
    return min(MAX_TURNS, MIN_TURNS + math.ceil(diff_lines / LINES_PER_TURN))


def fetch_gh(path):
    """New content of path at $SHA, or None."""
    repo, sha = os.environ.get("GH_REPO"), os.environ.get("SHA")
    if not repo or not sha:
        return None
    enc = urllib.parse.quote(path)
    r = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github.raw", f"repos/{repo}/contents/{enc}?ref={sha}"],
                       capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else None


def write(outdir, name, text):
    path = os.path.join(outdir, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def stage(diff, outdir, fetch=None):
    """Write the staged files, return the turns number. Falls back to the full diff on no relevant file or an error."""
    try:
        blocks = split_diff(diff)
        # Unsafe/unparsable blocks stay in the diff (the reviewer must see them); only the content fetch is skipped.
        keep = [b for b in blocks if bad(b) or relevant(b)]
        if not keep:
            raise ValueError("no relevant file")
        skipped = [b for b in blocks if b not in keep]
        staged = "".join("".join(b["text"]) for b in keep)
        lines = "".join(f"{b['path']}\t{b['status']}\t+{b['add']}/-{b['del']}\n" for b in skipped)
        files = {}
        for b in keep:
            if b["status"] != "deleted" and fetch and not bad(b):
                content = fetch(b["path"])
                if content is not None:
                    files[b["path"]] = content
        os.makedirs(outdir, exist_ok=True)
        write(outdir, "pr.diff", staged)
        write(outdir, "skipped.txt", lines)
        for path, content in files.items():
            write(outdir, os.path.join("files", path), content)
        return turns_for(staged.count("\n"))
    except Exception as e:  # noqa: BLE001 - fail-open: the reviewer gets the whole diff as before
        print(f"stage fallback: {e}", file=sys.stderr)
        os.makedirs(outdir, exist_ok=True)
        write(outdir, "pr.diff", diff)
        write(outdir, "skipped.txt", "")
        return turns_for(diff.count("\n"))


def main(argv):
    if len(argv) > 2:
        print(__doc__)
        return 2
    outdir = argv[1] if len(argv) == 2 else ".review"
    print(f"turns={stage(sys.stdin.read(), outdir, fetch_gh)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
