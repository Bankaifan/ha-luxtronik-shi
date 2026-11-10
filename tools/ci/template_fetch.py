"""Which template agent-dev downloads for a run on a template sync issue.

Prints `<owner>/<repo> <sha>` on one line, or nothing when the issue is no trusted template sync issue
(then the step does nothing). Trusted is the rule of tools/trusted_issues.py: the author app (AUTHOR_BOT) wrote the
issue, its title starts with `Template sync ` and its body has a `Template-Sync: <40 hex>` line. The SHA is the last
such line (CRLF tolerated). The repo is the `template` value of .agents/template.json, and only if it is `owner/repo`.

Environment: ISSUE_AUTHOR, ISSUE_TITLE, ISSUE_BODY (the issue as GitHub sent it), AUTHOR_BOT.
Run from the checkout: python3 tools/ci/template_fetch.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import trusted_issues  # tools/, for the same trust rule

MANIFEST = ".agents/template.json"
_REPO = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*/[A-Za-z0-9_][A-Za-z0-9_.-]*")  # no leading dot: no `..` path
_LINE = re.compile(r"^Template-Sync: ([0-9a-f]{40})$", re.MULTILINE)


def sync_sha(body):
    """SHA of the last `Template-Sync:` line of an issue body, else None."""
    found = _LINE.findall((body or "").replace("\r", ""))
    return found[-1] if found else None


def template_repo(manifest_text):
    """The `template` value of the manifest text if it is `owner/repo`, else None."""
    try:
        tpl = json.loads(manifest_text).get("template", "")
    except (ValueError, AttributeError):
        return None
    return tpl if isinstance(tpl, str) and _REPO.fullmatch(tpl) else None


def plan(env, manifest_text):
    """`<owner>/<repo> <sha>` to download for this run, or None."""
    issue = {"title": env.get("ISSUE_TITLE", ""), "body": env.get("ISSUE_BODY", ""),
             "author": {"login": env.get("ISSUE_AUTHOR", "")}}
    if not trusted_issues.is_sync_issue(issue, env.get("AUTHOR_BOT", "")):
        return None
    repo, sha = template_repo(manifest_text), sync_sha(issue["body"])
    return f"{repo} {sha}" if repo and sha else None


def main():
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            manifest = f.read()
    except OSError:
        manifest = ""
    out = plan(os.environ, manifest)
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
