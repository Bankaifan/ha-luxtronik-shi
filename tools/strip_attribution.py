"""Strip tool attribution footers from a PR or issue body and save it (only when it changed); cut a PR title over
TITLE_MAX characters at a word boundary (check_pr_form caps it; a fix run cannot edit titles, #624).

Usage: strip_attribution.py <number>. Reads the live body with `gh api` (needs GH_TOKEN and GH_REPO). Writes with `gh api -X PATCH` (issues endpoint, also for PRs) only when
`tools/attribution.remove` changed the text, so the `edited` event this triggers finds nothing and stops (no loop).
Never runs PR code: it only handles the text. Exit 0 on success or nothing to do, 1 on a gh error.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import attribution

TITLE_MAX = 100  # tools/check/check_pr_form.py


def short_title(title):
    """TITLE cut at the last space within TITLE_MAX characters (hard cut if there is none); unchanged if it fits."""
    if len(title) <= TITLE_MAX:
        return title
    cut = title[:TITLE_MAX]
    return (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip(" ,;:-")


def gh(args, stdin=None):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, input=stdin).stdout


def main(argv=None, environ=None):
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if environ is None else environ
    if len(argv) != 1 or not argv[0].isdigit():
        print("usage: strip_attribution.py <number>", file=sys.stderr)
        return 2
    number, repo = argv[0], env.get("GH_REPO", "")
    endpoint = f"repos/{repo}/issues/{number}"
    try:
        item = json.loads(gh(["api", endpoint]))  # live text, never the (possibly stale) event copy
        body, title = item.get("body") or "", item.get("title") or ""
        new = attribution.remove(body)
        if "pull_request" in item and short_title(title) != title:
            gh(["api", "-X", "PATCH", endpoint, "-f", f"title={short_title(title)}"])
            print(f"strip_attribution: #{number} title cut to {TITLE_MAX} characters")
        if new == body:
            print(f"strip_attribution: #{number} has no footer")
            return 0
        gh(["api", "-X", "PATCH", endpoint, "-F", "body=@-"], stdin=new)
    except (OSError, subprocess.CalledProcessError, ValueError) as e:
        print(f"strip_attribution: #{number}: {e}", file=sys.stderr)
        return 1
    print(f"strip_attribution: #{number} footer removed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
