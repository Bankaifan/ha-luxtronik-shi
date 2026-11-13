"""Keep projects from changing template-managed files (no model).

A project's .agents/template.json lists `managed` paths (owned by the template) and `overrides` (managed
paths the project may change on purpose). Two checks, both no-ops in the template repo itself and without a config:

  python3 tools/managed_guard.py check          # validate: fail a PR that changes managed, non-override paths
  python3 tools/managed_guard.py route-issue    # agent-dev: route a slip that only touches such paths to the template

`check` reads PR_NUMBER (gh pr view for files, title, head branch). A template-sync PR is exempt: its title starts
with `Template sync` and it changes .agents/template.json (it must set synced_sha).
Every part of a split sync (title `Template sync <sha> part <label>`, e.g. `part 1`, `part 2a`, `part 2b-1`) is exempt
without that change; only the last part sets synced_sha (issue #648).
`route-issue` reads the issue JSON (`gh issue view --json number,title,body,comments`; comments of untrusted authors are ignored) from ISSUE_JSON, takes the
last `Files touched:` line of the slip, and when every path is managed and not overridden opens an issue in the
template repo (TEMPLATE_GH_TOKEN) and comments on the project issue. Prints `skip=true` when it routed.
"""
import json
import os
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from template_sync import CONFIG, ConfigError, is_managed, parse_config

MANAGED_FILE = pathlib.Path(".agents/managed.json")
SYNC_TITLE = "Template sync"
PART_TITLE = re.compile(r"Template sync [0-9a-f]{7,40} part [0-9][0-9a-z-]*(?![\w-])", re.IGNORECASE)
FILES_LINE =re.compile(r"^\s*Files touched:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
PATH_RE = re.compile(r"[A-Za-z0-9_.][A-Za-z0-9_./-]*")


def load(path=CONFIG):
    """Parsed config, or None when missing or invalid."""
    try:
        return parse_config(pathlib.Path(path).read_text())
    except (OSError, ConfigError):
        return None


def template_managed(path=MANAGED_FILE):
    """Managed path prefixes of the template repo itself; a missing file gives an empty list."""
    try:
        text = pathlib.Path(path).read_text()
    except FileNotFoundError:
        return []
    try:
        managed = json.loads(text).get("managed", [])
    except (ValueError, AttributeError) as exc:
        raise ConfigError(f"{path} is not a JSON object with a 'managed' list: {exc}") from exc
    if not isinstance(managed, list) or not all(isinstance(m, str) for m in managed):
        raise ConfigError(f"{path}: 'managed' must be a list of strings")
    return managed


def is_template_repo(cfg, project):
    return bool(cfg) and project.lower() == cfg["template"].lower()


def protected(files, cfg):
    """Changed paths that are managed and not overridden."""
    managed = cfg.get("managed", [])
    overridden = {o["path"] for o in cfg.get("overrides", [])}
    return [f for f in files if is_managed(f, managed) and f not in overridden]


def is_sync_pr(title, files):
    """Normal sync PR (title + config change) or a part of a split sync (title only, synced_sha stays)."""
    if PART_TITLE.match(title.strip()):
        return True
    return title.strip().lower().startswith(SYNC_TITLE.lower()) and CONFIG.as_posix() in files


def pr_errors(cfg, project, title, files):
    """Error lines for a PR; empty list means fine."""
    if not cfg or is_template_repo(cfg, project) or is_sync_pr(title, files):
        return []
    bad = protected(files, cfg)
    if not bad:
        return []
    tpl = cfg["template"]
    return [f"{f} is managed by the template {tpl}: change it there (open an issue in {tpl}); "
            f"this repo gets it by template sync, or add an override with a reason" for f in bad]


def slip_paths(slip_text):
    """Paths from the last `Files touched:` line; None when there is no such line or no path."""
    found = FILES_LINE.findall(slip_text or "")
    if not found:
        return None
    paths = []
    for tok in re.split(r"[,\s]+", found[-1].replace("`", " ")):
        tok = tok.strip(".;:()")
        if ("/" in tok or "." in tok) and PATH_RE.fullmatch(tok):
            paths.append(tok)
    return paths or None


def route_decision(cfg, project, files):
    """'template' when the slip only touches managed, non-override paths, else 'project'."""
    if not cfg or not files or is_template_repo(cfg, project):
        return "project"
    if any(f.startswith("/") or ".." in f.split("/") for f in files):
        return "project"
    return "template" if all(f in protected([f], cfg) for f in files) else "project"


def gh(*args, token=None):
    env = {**os.environ, "GH_TOKEN": token} if token else None
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, env=env).stdout


def cmd_check():
    number = os.environ.get("PR_NUMBER")
    cfg = load()
    if not number or not cfg:
        print("managed_guard: skipped (no PR or no .agents/template.json)")
        return 0
    try:
        pr = json.loads(gh("pr", "view", number, "--json", "title,files"))
    except (OSError, subprocess.CalledProcessError, ValueError):
        print("managed_guard: skipped (cannot read the PR)")
        return 0
    files = [f.get("path", "") for f in pr.get("files") or []]
    errors = pr_errors(cfg, os.environ.get("GH_REPO", ""), pr.get("title") or "", files)
    for e in errors:
        print(f"managed_guard: {e}")
    if not errors:
        print("managed_guard: ok")
    return 1 if errors else 0


def cmd_route_issue():
    cfg, project = load(), os.environ.get("GH_REPO", "")
    token = os.environ.get("TEMPLATE_GH_TOKEN", "")
    try:
        issue = json.loads(os.environ.get("ISSUE_JSON", ""))
    except ValueError:
        return 0
    trusted = ("OWNER", "MEMBER", "COLLABORATOR")  # a comment by anyone else must not steer the routing
    slip = "\n".join([issue.get("body") or ""] + [c.get("body") or "" for c in issue.get("comments") or []
                                                  if c.get("authorAssociation") in trusted])
    files = slip_paths(slip)
    if not token or route_decision(cfg, project, files or []) != "template":
        return 0
    tpl, num = cfg["template"], issue["number"]
    title = (issue.get("title") or "").replace("@", "")
    body = f"{(issue.get('body') or '').replace('@', '').rstrip()}\n\nFound in: {project}#{num}"
    url = gh("issue", "create", "-R", tpl, "--label", "idea", "--title", title, "--body", body, token=token).strip()
    gh("issue", "comment", str(num), "--body",
       f"Only template-managed files are touched ({', '.join(files)}). Routed to the template: {url}. "
       f"This repo gets the fix by template sync; nothing is built here.")
    print("skip=true")
    return 0


def main(argv=None):
    cmd = (argv if argv is not None else sys.argv[1:])[:1]
    if cmd == ["check"]:
        return cmd_check()
    if cmd == ["route-issue"]:
        return cmd_route_issue()
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
