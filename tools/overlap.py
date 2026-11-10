"""Overlap guard for the orchestrator (no model): does a new slip touch files that an open agent PR
or an open agent:dev slip already touches? (design 0003, section 4.1)

  python3 tools/overlap.py --files a.py,docs/ [--issue N]

Prints one line per overlap and exits 1 (defer the slip); exits 0 when disjoint, 2 when GitHub data
could not be read (fail closed: treat as overlap). `--issue N` ignores the PR and slip of issue N itself.
Paths are untrusted text: they are only compared as strings, never opened.
"""
import argparse
import json
import re
import subprocess
import sys

FILES_RE = re.compile(r"^[\s>*_-]*Files(?:\s+touched)?\**\s*:\**\s*(.*)$", re.IGNORECASE | re.MULTILINE)
BRANCH_RE = re.compile(r"agent/(\d+)-")
DEFAULT_TRUSTED = frozenset({
    "Bankaifan", "app/github-actions", "github-actions",
    "bankaifan-agent-author", "app/bankaifan-agent-author", "bankaifan-agent-author[bot]",
    "bankaifan-agent-approver", "app/bankaifan-agent-approver", "bankaifan-agent-approver[bot]",
})


def clean_path(tok):
    tok = tok.strip().strip("`'\"*").rstrip(".,;:")
    if not tok or tok.startswith("/") or ".." in tok.split("/"):
        return ""
    return tok.removeprefix("./") if ("/" in tok or "." in tok) else ""


def parse_files(text):
    """Paths from the 'Files:' / 'Files touched:' line(s) of a slip; parentheses and text after 'Acceptance' are dropped."""
    out = []
    for m in FILES_RE.finditer(text or ""):
        line = re.split(r"\bAcceptance\b", m.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
        line = re.sub(r"\([^)]*\)", " ", line)
        for tok in re.split(r"[,\s]+", line):
            p = clean_path(tok)
            if p and p not in out:
                out.append(p)
    return out


def overlaps(a, b):
    """Equal paths, or one is a directory prefix of the other."""
    a, b = a.rstrip("/"), b.rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def find_overlaps(slip_files, others):
    """others: list of (label, [paths]). Returns 'path vs path (label)' lines."""
    found = []
    for label, paths in others:
        for s in slip_files:
            if any(overlaps(s, p) for p in paths):
                found.append(f"{s} overlaps {label}")
    return found


def trusted(obj, authors):
    """Author login of a gh object is in the trusted set (empty set trusts nobody)."""
    return (obj.get("author") or {}).get("login") in authors


def collect(prs, issues, own_issue=None, authors=DEFAULT_TRUSTED):
    """Build (label, paths) from `gh pr list` and `gh issue list` JSON. Own issue is skipped.
    Only same-repo PRs and slips/comments by trusted authors count; others are ignored."""
    others = []
    for pr in prs:
        m = BRANCH_RE.match(pr.get("headRefName", ""))
        if not m or pr.get("isCrossRepository") or not trusted(pr, authors):
            continue
        if own_issue is not None and int(m.group(1)) == own_issue:
            continue
        others.append((f"PR #{pr['number']}", [f["path"] for f in pr.get("files", [])]))
    for iss in issues:
        if own_issue is not None and iss["number"] == own_issue:
            continue
        if not trusted(iss, authors):
            continue
        texts = [iss.get("body", "")] + [c.get("body", "") for c in iss.get("comments", []) if trusted(c, authors)]
        paths = []
        for t in texts:
            paths += parse_files(t)
        others.append((f"slip #{iss['number']}", paths))
    return others


def gh_json(*args):
    out = subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--files", required=True)
    p.add_argument("--issue", type=int)
    args = p.parse_args(argv)
    slip = [f for f in (clean_path(t) for t in args.files.split(",")) if f]
    if not slip:
        print("overlap: no usable paths in --files", file=sys.stderr)
        return 2
    try:
        prs = gh_json("pr", "list", "--state", "open", "--limit", "100", "--json", "number,headRefName,files,author,isCrossRepository")
        issues = gh_json("issue", "list", "--state", "open", "--label", "agent:dev", "--limit", "100",
                         "--json", "number,body,comments,author")
    except (subprocess.CalledProcessError, OSError, ValueError) as e:
        print(f"overlap: cannot read GitHub data ({type(e).__name__}), defer the slip", file=sys.stderr)
        return 2
    found = find_overlaps(slip, collect(prs, issues, args.issue))  # output: slip path + label only, never foreign text
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
