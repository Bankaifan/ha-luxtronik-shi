"""Run report for agents that may do nothing (issue #179): one comment on the "Agent status" issue per run.

Script step after the model step, no extra model turns. Reads the execution file (exec_log.py) and posts:
workflow, run link, model, turns, outcome (PR/issue numbers created, or "no change"), the model's final
`Conclusion:` line and the denied tool calls (secrets masked). A denied call that the workflow's prompt requires
opens one `prio:2` guard issue per workflow and command (dedup by title), signed with GUARD_KEY (guard_mark.py).
Only fixed script strings go into the signed issue; denied command text only appears in the unsigned report.

CLI (env: GH_TOKEN, GH_REPO, EXEC_FILE, RUN_URL, MODEL, STATUS_ISSUE (default 57), GUARD_KEY, WORKFLOW_FILE):
  run_report.py WORKFLOW_NAME
Never fails the job: a reporting error prints a warning and exits 0.
"""
import json
import os
import re
import subprocess
import sys

import exec_log
import guard_mark
import liveness

STATUS_ISSUE = "57"
STATUS_TITLE = "Agent status"
GUARD_LABEL = "prio:2"
MAX_LINE = 300
_CREATED = re.compile(r"github\.com/[^/\s]+/[^/\s]+/(pull|issues)/(\d+)")
# Required commands per workflow: a denied Bash call starting with one of these keys blocks the role's own steps.
REQUIRED = {
    "rule-keeper": ("gh pr create", "git checkout -b", "git push origin", "git commit", "git add", "make check",
                    "gh pr list", "gh pr view"),
    "scout": ("python3 tools/idea_route.py create", "gh issue list", "gh label create", "gh pr list", "gh pr view"),
    "orchestrator": ("gh issue comment", "gh issue edit", "gh label create", "gh pr create", "git push origin HEAD",
                     "git commit", "git add", "make check", "gh pr list", "gh pr view", "gh issue list",
                     "gh issue view", "gh run list"),
}


def _line(text, n=MAX_LINE):
    return exec_log.mask(" ".join(str(text or "").split()))[:n].replace("`", "'")


def summary(text):
    """(final result record or {}, turns or None)."""
    final = {}
    for rec in exec_log._records(text):
        if rec.get("type") == "result":
            final = rec
    return final, final.get("num_turns")


def created(text):
    """Sorted ('pr'|'issue', number) pairs from successful creating commands (gh pr/issue create, idea_route create)."""
    ids, out = {}, set()
    for rec in exec_log._records(text):
        msg = rec.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                cmd = str((block.get("input") or {}).get("command") or "")
                if re.match(r"\s*(gh (pr|issue) create|python3 tools/idea_route\.py create)", cmd):
                    ids[block.get("id")] = True
            elif block.get("type") == "tool_result" and ids.get(block.get("tool_use_id")):
                body = block.get("content")
                if isinstance(body, list):
                    body = " ".join(str(b.get("text", "")) for b in body if isinstance(b, dict))
                for kind, num in _CREATED.findall(str(body or "")):
                    out.add(("pr" if kind == "pull" else "issue", int(num)))
    return sorted(out)


def conclusion(final):
    """The `Conclusion:` line of the final answer, else its last non-empty line, else 'open'."""
    lines = [ln.strip() for ln in str(final.get("result") or "").splitlines() if ln.strip()]
    for ln in reversed(lines):
        if ln.lower().startswith("conclusion:"):
            return _line(ln.split(":", 1)[1])
    return _line(lines[-1]) if lines else "open (no final answer)"


def outcome(items):
    if not items:
        return "no change"
    return ", ".join(f"{'PR' if k == 'pr' else 'issue'} #{n}" for k, n in items)


def build_report(workflow, text, run_url="", model=""):
    final, turns = summary(text)
    denials = exec_log.denied_calls(text)
    total = exec_log.count_denials(text)
    lines = [f"Run report: {workflow}",
             f"- Run: {run_url or 'open'}",
             f"- Model: {_line(model) or 'open'}, turns: {turns if turns is not None else 'open'}",
             f"- Outcome: {outcome(created(text))}",
             f"- Conclusion: {conclusion(final)}",
             f"- Denied tool calls: {total}"]
    lines += [f"  - {d}" for d in denials]
    return "\n".join(lines)


def required_denials(workflow, text):
    """Fixed command keys (from REQUIRED) of denied Bash calls that the workflow's prompt requires; sorted, unique."""
    keys = set()
    for rec in exec_log._records(text):
        for d in rec.get("permission_denials") or []:
            if not isinstance(d, dict) or d.get("tool_name") != "Bash":
                continue
            inp = d.get("tool_input")
            cmd = " ".join(str((inp if isinstance(inp, dict) else {}).get("command") or "").split())
            for key in REQUIRED.get(workflow, ()):
                if cmd.startswith(key):
                    keys.add(key)
    return sorted(keys)


def denial_title(workflow, key):
    return f"Denied command in {workflow}: {key}"


def denial_body(workflow, key):
    # Fixed script text only: the body is signed (see guard_mark.py).
    return (f"The workflow {workflow} was denied the command `{key}`, which its prompt requires. "
            "Check the allowedTools of the workflow and the latest run report on the Agent status issue.")


def ensure_denial_issue(workflow, key, key_secret=None, repo=None, run=liveness.gh):
    """One open prio:2 issue per workflow and command (found by title). Returns its number or None if one exists."""
    title = denial_title(workflow, key)
    secret = guard_mark.key_from_env() if key_secret is None else key_secret
    base = ["--repo", repo] if repo else []
    found = json.loads(run("issue", "list", *base, "--state", "open", "--search", f'"{title}" in:title',
                           "--json", "number,title"))
    if any(i["title"] == title for i in found):
        return None
    run("label", "create", GUARD_LABEL, *base, "--force")
    out = run("issue", "create", *base, "--title", title, "--label", GUARD_LABEL, "--body",
              guard_mark.sign(title, denial_body(workflow, key), secret))
    return out.strip().rsplit("/", 1)[-1]


def target_repo(workflow, project, cfg=None, workflow_file=None):
    """Template-managed workflows file their guard issues in the template repo, all others in the project."""
    try:
        import idea_route
        cfg = idea_route.load_config() if cfg is None else cfg
        path = workflow_file or f".github/workflows/{workflow}.yml"
        if cfg and project.lower() != cfg["template"].lower() and idea_route.same_owner(cfg["template"], project) \
                and idea_route.route([path], cfg, project) == "template":
            return cfg["template"]
    except Exception as e:  # noqa: BLE001 - routing must never break a report
        print(f"routing failed, using the project repo: {type(e).__name__}")
    return project


def report(workflow, env=None, run=liveness.gh):
    env = os.environ if env is None else env
    text = exec_log.read_exec(env.get("EXEC_FILE", ""))
    body = build_report(workflow, text, env.get("RUN_URL", ""), env.get("MODEL", ""))
    liveness.post_comment("issue", env.get("STATUS_ISSUE") or STATUS_ISSUE, body, run)
    project = env.get("GH_REPO", "")
    repo = target_repo(workflow, project, workflow_file=env.get("WORKFLOW_FILE"))
    issue_run, other = run, None
    if repo != project:
        token = env.get("TEMPLATE_GH_TOKEN")
        if token:
            other = repo
            def issue_run(*a):
                return subprocess.run(["gh", *a], check=True, capture_output=True, text=True,
                                      env={**os.environ, "GH_TOKEN": token}).stdout
    new = [ensure_denial_issue(workflow, k, repo=other, run=issue_run) for k in required_denials(workflow, text)]
    return body, [n for n in new if n]


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 0
    try:
        _, new = report(argv[1])
        print(f"report posted; new denial issues: {new or 'none'}")
    except Exception as e:  # noqa: BLE001 - a reporting error must not fail the job
        print(f"::warning::run report failed: {type(e).__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
