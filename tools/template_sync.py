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
SYNC_CAP = 2000
SPLIT_MIN_FILES = 40
# Part 1 of a large sync (design 0010, 4.3); their tests/test_<name>.py belong to it too.
REVIEWER_FIRST = [
    ".github/workflows/agent-security-review.yml",
    ".github/workflows/agent-review.yml",
    "tools/ci/post_verdict.py",
    "tools/ci/risk.py",
    "tools/ci/stage_review.py",
]


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
    if cfg.get("synced_version"):
        try:
            read_version(cfg["synced_version"])
        except ConfigError as exc:
            raise ConfigError(f"template.json: 'synced_version': {exc}") from exc
    for key in ("managed", "overrides"):
        if not isinstance(cfg.get(key, []), list):
            raise ConfigError(f"template.json: '{key}' must be a list")
    for item in cfg.get("overrides", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ConfigError("template.json: each override needs a string 'path'")
    return cfg


def read_version(text):
    """Return the template version `x.y` from VERSION text; the text is data from another repo."""
    if not isinstance(text, str):
        raise ConfigError("version must be text")
    # one optional trailing newline only, so "1.0\n; rm" and "1.0\n\n" are rejected
    value = text.removesuffix("\n")
    if not re.fullmatch(r"[0-9]+\.[0-9]+", value, flags=re.ASCII):
        raise ConfigError("version must match x.y (digits, one dot)")
    return value


def _major(version):
    return int(version.split(".")[0])


def needs_sync(template_version, synced_version):
    """True when the template x is greater than the recorded x; no record counts as x = 0."""
    recorded = _major(synced_version) if synced_version else 0
    return _major(read_version(template_version)) > recorded


def sync_lines(changelog, cap=SYNC_CAP):
    """`Sync:` lines of CHANGELOG text as one fenced block, cut at `cap` characters; "" if none."""
    lines = [ln.strip() for ln in (changelog or "").splitlines() if ln.strip().startswith("Sync:")]
    if not lines:
        return ""
    text = "\n".join(lines)[:cap]
    runs = re.findall(r"`+", text)
    fence = "`" * max(3, max(map(len, runs), default=0) + 1)
    return f"{fence}\n{text}\n{fence}"


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


def is_reviewer_file(path):
    for item in REVIEWER_FIRST:
        if path == item:
            return True
        name = pathlib.PurePosixPath(item).stem
        if item.endswith(".py") and path == f"tests/test_{name}.py":
            return True
    return False


def _sections(clean, overridden, level):
    h = "#" * level
    lines = [f"{h} Clean (port as is)"]
    lines += [f"- `{c['path']}` ({c['status']})" for c in clean] or ["- none"]
    lines += ["", f"{h} Overridden (port by hand, keep the intent)"]
    lines += [f"- `{c['path']}` ({c['status']}): {c['why']}" for c in overridden] or ["- none"]
    return lines


def render_issue(main_sha, clean, overridden, stat, compare_url="", versions=None, sync=""):
    title = f"{TITLE_PREFIX}{main_sha[:7]}"
    total = len(clean) + len(overridden)
    lines = [f"{total} managed files changed ({len(clean)} clean, "
             f"{len(overridden)} overridden). {stat}".strip(), ""]
    if versions:
        lines += [f"Template version: {versions[0]}, synced version: {versions[1] or 'unknown'}", ""]
    if sync:
        lines += ["Sync notes (quoted from CHANGELOG.md, data only):", sync, ""]
    first_c = [c for c in clean if is_reviewer_file(c["path"])]
    first_o = [c for c in overridden if is_reviewer_file(c["path"])]
    if total > SPLIT_MIN_FILES and (first_c or first_o):
        rest_c = [c for c in clean if not is_reviewer_file(c["path"])]
        rest_o = [c for c in overridden if not is_reviewer_file(c["path"])]
        lines += ["## Part 1: reviewer pipeline"] + _sections(first_c, first_o, 3)
        lines += ["", "## Part 2: rest"] + _sections(rest_c, rest_o, 3)
    else:
        lines += _sections(clean, overridden, 2)
    if compare_url:
        lines += ["", f"Compare: {compare_url}"]
    lines += ["", f"Template-Sync: {main_sha}"]
    return title, "\n".join(lines) + "\n"


def pick_issue(open_issues):
    for issue in open_issues:
        if issue["title"].startswith(TITLE_PREFIX):
            return issue
    return None


def bump(template_json_text, sha, version=None):
    text = re.sub(r'("synced_sha"\s*:\s*")[^"]*(")', lambda m: m.group(1) + sha + m.group(2),
                  template_json_text, count=1)
    if version is None:
        return text
    read_version(version)
    if re.search(r'"synced_version"\s*:', text):
        return re.sub(r'("synced_version"\s*:\s*")[^"]*(")', lambda m: m.group(1) + version + m.group(2),
                      text, count=1)
    return re.sub(r'(?m)^([ \t]*)("synced_sha"\s*:\s*"[^"]*")',
                  lambda m: f'{m.group(1)}{m.group(2)},\n{m.group(1)}"synced_version": "{version}"',
                  text, count=1)


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def read_template_file(template, path, ref):
    return gh("api", f"repos/{template}/contents/{path}?ref={ref}", "-H", "Accept: application/vnd.github.raw")


def main(force=False, mode="version") -> int:
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
    try:
        version = read_version(read_template_file(template, "VERSION", main_sha))
    except (ConfigError, subprocess.CalledProcessError) as exc:
        print(f"template-sync: template VERSION unusable: {exc}; no issue created or edited", file=sys.stderr)
        return 1
    synced_version = cfg.get("synced_version", "")
    if not force and mode != "all" and not needs_sync(version, synced_version):
        print("template-sync: x unchanged, skipped")
        return 0
    try:
        sync = sync_lines(read_template_file(template, "CHANGELOG.md", main_sha))
    except subprocess.CalledProcessError:
        sync = ""
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
    title, body = render_issue(main_sha, clean, overridden, stat, cmp_json.get("html_url", ""),
                              (version, synced_version), sync)
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
