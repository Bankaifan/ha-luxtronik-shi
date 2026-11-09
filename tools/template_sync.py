"""Report template changes as one issue, without a model (design 0001, section 4.2).

Reads .agents/template.json, compares the template's main with synced_sha through the GitHub
compare API, and creates or edits the single open issue "Template sync <short SHA>".
Needs the gh CLI (GH_TOKEN, GH_REPO). No-op when the config is missing or synced_sha is empty,
and when the repo is the template itself.
"""
import json
import os
import pathlib
import re
import subprocess
import sys

CONFIG = pathlib.Path(".agents/template.json")
TITLE_PREFIX = "Template sync "
COMPARE_CAP = 300


class TruncatedCompare(Exception):
    """The compare API file list may be cut off at 300 entries."""


class ConfigError(Exception):
    """.agents/template.json is invalid."""


def parse_config(text):
    try:
        cfg = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"template.json is not valid JSON: {exc}") from exc
    if not isinstance(cfg, dict):
        raise ConfigError("template.json must be a JSON object")
    if not isinstance(cfg.get("template"), str) or not cfg["template"]:
        raise ConfigError("template.json: 'template' must be a non-empty string")
    sha = cfg.get("synced_sha", "")
    if not isinstance(sha, str) or (sha and not re.fullmatch(r"[0-9a-f]{40}", sha)):
        raise ConfigError("template.json: 'synced_sha' must be empty or 40 hex characters")
    for key in ("managed", "overrides"):
        if not isinstance(cfg.get(key, []), list):
            raise ConfigError(f"template.json: '{key}' must be a list")
    for item in cfg.get("overrides", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ConfigError("template.json: each override needs a string 'path'")
    return cfg


def is_managed(path, managed):
    return any(path.startswith(m) if m.endswith("/") else path == m for m in managed)


def changed_files(compare_json, managed):
    files = compare_json.get("files") or []
    if len(files) >= COMPARE_CAP:
        raise TruncatedCompare(f"compare returned {len(files)} files (cap {COMPARE_CAP}), list may be incomplete")
    out = []
    for f in files:
        path, status = f["filename"], f["status"]
        if is_managed(path, managed):
            out.append({"path": path, "status": status})
        old = f.get("previous_filename")
        if status == "renamed" and old and is_managed(old, managed):
            out.append({"path": old, "status": "renamed-from"})
    return out


def split_overrides(changed, overrides):
    why = {o["path"]: o.get("why", "") for o in overrides}
    clean = [c for c in changed if c["path"] not in why]
    overridden = [{**c, "why": why[c["path"]]} for c in changed if c["path"] in why]
    return clean, overridden


def render_issue(main_sha, clean, overridden, stat, compare_url=""):
    title = f"{TITLE_PREFIX}{main_sha[:7]}"
    lines = [f"{len(clean) + len(overridden)} managed files changed ({len(clean)} clean, "
             f"{len(overridden)} overridden). {stat}".strip(), "", "## Clean (port as is)"]
    lines += [f"- `{c['path']}` ({c['status']})" for c in clean] or ["- none"]
    lines += ["", "## Overridden (port by hand, keep the intent)"]
    lines += [f"- `{c['path']}` ({c['status']}): {c['why']}" for c in overridden] or ["- none"]
    if compare_url:
        lines += ["", f"Compare: {compare_url}"]
    lines += ["", f"Template-Sync: {main_sha}"]
    return title, "\n".join(lines) + "\n"


def pick_issue(open_issues):
    for issue in open_issues:
        if issue["title"].startswith(TITLE_PREFIX):
            return issue
    return None


def bump(template_json_text, sha):
    return re.sub(r'("synced_sha"\s*:\s*")[^"]*(")', lambda m: m.group(1) + sha + m.group(2),
                  template_json_text, count=1)


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main() -> int:
    if not CONFIG.exists():
        print("template-sync: no .agents/template.json, skipped")
        return 0
    try:
        cfg = parse_config(CONFIG.read_text())
    except ConfigError as exc:
        print(f"template-sync: {exc}", file=sys.stderr)
        return 1
    if not cfg.get("synced_sha"):
        print("template-sync: no .agents/template.json, skipped")
        return 0
    repo, template = os.environ.get("GH_REPO", ""), cfg["template"]
    if repo.lower() == template.lower():
        print("template-sync: this repo is the template, skipped")
        return 0
    main_sha = gh("api", f"repos/{template}/commits/main", "--jq", ".sha").strip()
    cmp_json = json.loads(gh("api", f"repos/{template}/compare/{cfg['synced_sha']}...{main_sha}"))
    try:
        changed = changed_files(cmp_json, cfg.get("managed", []))
    except TruncatedCompare as exc:
        print(f"template-sync: {exc}; no issue created or edited", file=sys.stderr)
        return 1
    if not changed:
        print("template-sync: no managed changes")
        return 0
    clean, overridden = split_overrides(changed, cfg.get("overrides", []))
    stat = f"{cmp_json.get('ahead_by', 0)} commits ahead."
    title, body = render_issue(main_sha, clean, overridden, stat, cmp_json.get("html_url", ""))
    found = pick_issue(json.loads(gh("issue", "list", "--state", "open", "--search",
                                     f'"{TITLE_PREFIX.strip()}" in:title', "--json", "number,title")))
    if found:
        gh("issue", "edit", str(found["number"]), "--title", title, "--body", body)
        print(f"updated #{found['number']}")
    else:
        print(gh("issue", "create", "--title", title, "--body", body,
                 "--label", "agent:dev", "--label", "model:sonnet").strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
