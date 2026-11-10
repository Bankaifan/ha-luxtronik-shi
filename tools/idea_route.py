"""Route a scout idea to the template repo or the project (no model).

An idea whose files are all under the `managed` paths of .agents/template.json belongs to the
template and is opened there (label `idea`, body ends with 'Found in: <project>#<context>').
Anything else, or a missing/invalid template.json, stays in the project.

  python3 tools/idea_route.py repo                      # print the template repo (for the workflow)
  python3 tools/idea_route.py create --title T --body B --files a,b [--context C] [--label L ...]
  python3 tools/idea_route.py flush                     # later step, no model: open queued template ideas

The model step runs `create` with the project GH_TOKEN only: project ideas are opened at once,
template ideas are queued as JSON under /tmp/idea-queue. TEMPLATE_GH_TOKEN exists only in the
later `flush` step (no model), so a model never has it. Labels are an allowlist (prio:2, prio:3),
so approved/auto-ok can never be set.
"""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from template_sync import CONFIG, ConfigError, is_managed, parse_config

REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
ALLOWED_LABELS = {"prio:2", "prio:3"}
QUEUE_DIR = pathlib.Path("/tmp/idea-queue")
MAX_QUEUE = 10


def filter_labels(labels):
    """Allowlist: only exact prio:2 / prio:3 after strip+lower; commas and anything else are dropped."""
    out = []
    for lb in labels:
        norm = lb.strip().lower()
        if norm in ALLOWED_LABELS and norm not in out:
            out.append(norm)
    return out


def load_config(path=CONFIG):
    """Return the parsed config, or None when missing, invalid or not a valid repo name."""
    try:
        cfg = parse_config(pathlib.Path(path).read_text())
    except (OSError, ConfigError):
        return None
    return cfg if REPO_RE.fullmatch(cfg["template"]) else None


def same_owner(template, project):
    """The template must live under the project's owner: the app token is never minted for a foreign owner."""
    return template.split("/")[0].lower() == project.split("/")[0].lower()


def route(files, cfg, project=""):
    """Return 'template' or 'project'."""
    if not cfg or not files:
        return "project"
    if project.lower() == cfg["template"].lower():
        return "project"
    managed = cfg.get("managed", [])
    if not managed or not all(isinstance(m, str) for m in managed):
        return "project"
    clean = [f.strip() for f in files if f.strip()]
    if not clean or any(f.startswith("/") or ".." in f.split("/") for f in clean):
        return "project"
    return "template" if all(is_managed(f, managed) for f in clean) else "project"


def sanitize(text):
    """No mentions: '@' would notify people in another repo."""
    return text.replace("@", "")


def found_in(project, context):
    ctx = re.sub(r"[^A-Za-z0-9_.-]", "", context) or "scout"
    return f"Found in: {project}#{ctx}"


def is_duplicate(title, open_titles):
    def norm(s):
        return " ".join(s.lower().split())
    return norm(title) in {norm(t) for t in open_titles}


def gh(*args, token=None):
    env = {**os.environ, "GH_TOKEN": token} if token else None
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True, env=env).stdout


def open_in_project(title, body, labels):
    cmd = ["issue", "create", "--label", "idea", "--title", title, "--body", body]
    for lb in labels:
        cmd += ["--label", lb]
    print(gh(*cmd).strip())


def create(args):
    """Model step: project token only. Template ideas are queued, never sent from here."""
    project = os.environ.get("GH_REPO", "")
    cfg = load_config()
    files = [f for f in args.files.split(",") if f.strip()]
    body = sanitize(args.body).rstrip()
    title = sanitize(args.title)
    labels = filter_labels(args.label)
    if cfg and same_owner(cfg["template"], project) and route(files, cfg, project) == "template":
        QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        n = len(list(QUEUE_DIR.glob("*.json")))
        if n >= MAX_QUEUE:
            raise SystemExit("idea-route: queue full")
        item = {"title": title, "body": body, "labels": labels, "context": args.context}
        (QUEUE_DIR / f"{n:03d}.json").write_text(json.dumps(item))
        print("idea-route: queued for the template repo")
        return 0
    open_in_project(title, body, labels)
    return 0


def flush():
    """Later step, no model: open queued ideas in the template (TEMPLATE_GH_TOKEN), else in the project."""
    project = os.environ.get("GH_REPO", "")
    cfg = load_config()
    token = os.environ.get("TEMPLATE_GH_TOKEN", "")
    open_titles = None
    for f in sorted(QUEUE_DIR.glob("*.json")) if QUEUE_DIR.is_dir() else []:
        item = json.loads(f.read_text())
        title = sanitize(str(item.get("title", "")))
        body = sanitize(str(item.get("body", ""))).rstrip()
        labels = filter_labels([str(x) for x in item.get("labels", [])])
        if not title:
            continue
        if not (cfg and token and same_owner(cfg["template"], project)):
            print("idea-route: no template token or config, opening in the project", file=sys.stderr)
            open_in_project(title, body, labels)
            continue
        repo = cfg["template"]
        if open_titles is None:
            open_titles = gh("issue", "list", "-R", repo, "--state", "open", "--label", "idea",
                             "--limit", "200", "--json", "title", "--jq", ".[].title",
                             token=token).splitlines()
        if is_duplicate(title, open_titles):
            print(f"idea-route: duplicate in {repo}, nothing created")
            continue
        open_titles.append(title)
        foot = found_in(project, str(item.get("context", "")))
        print(gh("issue", "create", "-R", repo, "--label", "idea", "--title", title, "--body",
                 f"{body}\n\n{foot}", token=token).strip())
    return 0


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("repo")
    sub.add_parser("flush")
    c = sub.add_parser("create")
    c.add_argument("--title", required=True)
    c.add_argument("--body", required=True)
    c.add_argument("--files", required=True)
    c.add_argument("--context", default="scout")
    c.add_argument("--label", action="append", default=[])
    args = p.parse_args(argv)
    if args.cmd == "repo":
        cfg = load_config()
        project = os.environ.get("GH_REPO", "")
        if cfg and cfg["template"].lower() != project.lower() and same_owner(cfg["template"], project):
            print(cfg["template"])
        return 0
    if args.cmd == "flush":
        return flush()
    return create(args)


if __name__ == "__main__":
    sys.exit(main())
