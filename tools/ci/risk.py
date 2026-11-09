"""Risk classification of a PR diff: `security`, `infra` or `none`.

security: the diff touches workflow `permissions:`, `allowedTools`, `allowed_bots`, secrets/token handling,
  trust logic (tools/trusted_issues.py, tools/agent_guard.py), `.github/rulesets/`, CODEOWNERS, this check,
  or the "Limits" section of AGENTS.md. infra: any other change to agent infrastructure. none: everything else.

CLI:
  risk.py classify [AGENTS_MD]   read a unified diff on stdin, print the level (AGENTS_MD: base file for the Limits section)
  risk.py pr NUMBER              (env GH_TOKEN, GH_REPO, optional OWNER, AUTHOR_BOT) label the PR, request the owner's review
                                 for `security`, publish the check run `risk`; it fails until OWNER approved the head SHA.
                                 Also starts the status `security-review` (pending for agent PRs that need that review).
  risk.py wait NUMBER SHA        (env GH_TOKEN, GH_REPO, APPROVER_BOT) called by agent-review and agent-security-review; acts only
                                 when for SHA the approver approved, validate/agent-smoke are green, risk is complete and
                                 `security-review` is success, and the PR waits for the owner (risk `security` or a code-owner
                                 path): label `needs-human`, request the owner's review, post the PR-specific German note once
  risk.py verdict NUMBER SHA     publish the status `security-review` from the security reviewer's comment for SHA
Runs from the default branch with the PR read through `gh`; PR code is never executed.
"""
import json
import os
import re
import subprocess
import sys

SECURITY_FILES = (".github/rulesets/", ".github/CODEOWNERS", "tools/trusted_issues.py", "tools/agent_guard.py",
                  "tools/ci/risk.py", ".github/workflows/risk.yml")
INFRA_PATHS = (".github/", ".agents/", "tools/", "AGENTS.md", "CLAUDE.md", "Makefile", ".claude/", ".mcp.json")
SECURITY_LINES = re.compile(
    r"permissions:|allowedTools|allowed_bots|secrets\.|_TOKEN|\btoken\b|app-token|APP_KEY", re.IGNORECASE)
LINE_SCANNED = (".github/", "tools/", ".claude/", ".mcp.json", "Makefile")  # prose in docs and roles is no token handling
LABELS = {"security": "risk:security", "infra": "risk:infra"}
OWNER_DEFAULT = "Bankaifan"
VERDICT = re.compile(r"^security-review:\s*(approve|changes)\s+([0-9a-f]{7,40})\b", re.IGNORECASE | re.MULTILINE)


def norm(login):
    return (login or "").lower().removeprefix("app/").removesuffix("[bot]")


def limits_range(text):
    """1-based inclusive line range of the `## Limits` section in AGENTS.md, or None."""
    start, last = None, 0
    for i, line in enumerate((text or "").splitlines(), 1):
        last = i
        if start is None:
            if re.match(r"##\s+Limits\b", line):
                start = i
        elif line.startswith("## "):
            return start, i - 1
    return (start, last) if start else None


def classify(diff, agents_md=""):
    """Level of a unified diff. `agents_md` is the base version of AGENTS.md (locates the Limits section)."""
    level = "none"
    path, old, header = "", 0, False
    limits = limits_range(agents_md)
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.*?) b/(.*)$", line)
            paths = (m.group(1), m.group(2)) if m else ("", "")
            path, old, header = paths[1], 0, True
            if any(p.startswith(s) for p in paths for s in SECURITY_FILES):
                return "security"
            if any(p.startswith(s) for p in paths for s in INFRA_PATHS):
                level = "infra"
        elif line.startswith("@@"):
            m = re.match(r"@@ -(\d+)", line)
            old, header = (int(m.group(1)) if m else 0), False
        elif header:  # ---/+++/index/mode lines between `diff --git` and the first hunk
            continue
        elif line[:1] in ("+", "-"):
            if path.startswith(LINE_SCANNED) and SECURITY_LINES.search(line[1:]):
                return "security"
            if path == "AGENTS.md" and limits and limits[0] <= old <= limits[1]:
                return "security"
            if line[0] == "-":
                old += 1
        else:
            old += 1
    return level


def gh(*args):
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def owner_approved(reviews, owner, sha):
    """The owner's latest decisive review is an approval of exactly this head SHA."""
    mine = [r for r in reviews if norm((r.get("user") or {}).get("login")) == norm(owner)
            and r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED")]
    return bool(mine) and mine[-1]["state"] == "APPROVED" and mine[-1].get("commit_id") == sha


def verdict_for(comments, sha, approver):
    """`approve` / `changes` from the latest security-review comment of the approver app for this SHA, else None."""
    found = None
    for c in comments:
        if norm((c.get("user") or {}).get("login")) != norm(approver) or not approver:
            continue
        for kind, s in VERDICT.findall(c.get("body") or ""):
            if sha.lower().startswith(s.lower()):
                found = kind.lower()
    return found


def read_text(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def owned_by(path, codeowners, owner):
    """True if a CODEOWNERS rule with a rooted pattern (`/x` file or `/dir/`) names the owner for this path."""
    for line in (codeowners or "").splitlines():
        parts = line.split("#")[0].split()
        if len(parts) >= 2 and parts[0].startswith("/") and any(norm(o.lstrip("@")) == norm(owner) for o in parts[1:]):
            pat = parts[0][1:]
            if path == pat or (pat.endswith("/") and path.startswith(pat)):
                return True
    return False


def waits_for_owner(level, files, codeowners, owner):
    """The PR cannot merge without the owner: risk `security` or a changed file owned by him in CODEOWNERS."""
    return level == "security" or any(owned_by(f, codeowners, owner) for f in files)


NOTE_MARK = "<!-- needs-human-note -->"
GATE_CHECKS = ("validate", "agent-smoke")  # check runs that must be green; `risk` only has to be complete (owner gate)


def first_lines(text, limit=3):
    """First `limit` non-empty, non-heading, non-marker lines of a text, joined (plain summary of what a PR changes)."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "<!--", "Closes", "Refs")):
            out.append(line)
        if len(out) == limit:
            break
    return " ".join(out)


def build_note(sha, level, summary, review):
    """PR-specific German note: what changes, worst case, recommendation, one yes/no question. Marker is per head SHA."""
    worst = ("ein Agent bekommt mehr Rechte oder eine Pruefung wird schwaecher" if level == "security"
             else "eine Aenderung an der Agenten-Infrastruktur verhaelt sich falsch")
    what = first_lines(summary) or "(keine Beschreibung im PR)"
    why = first_lines(review, 2)
    return (f"{NOTE_MARK[:-4]} {sha[:12]} -->\nHallo Daniel, alle Pruefungen fuer diesen PR sind fertig und gruen; nur dein Schritt fehlt "
            f"(er aendert Dateien, die nur du freigeben darfst).\nWas der PR aendert: {what}\n"
            f"Schlimmster Fall: {worst}; Zurueckdrehen ist per Revert moeglich.\n"
            f"Empfehlung der Pruefer: Freigabe{' (' + why + ')' if why else ''}.\nFrage: Soll der PR gemergt werden (ja/nein)?")


def checks_ready(check_runs, statuses):
    """All gates for the head SHA hold: validate/agent-smoke green (skipped counts), `risk` complete, `security-review` success."""
    by_name = {}
    for c in check_runs:
        by_name[c.get("name")] = c
    for name in GATE_CHECKS:
        c = by_name.get(name)
        if c is not None and (c.get("status") != "completed" or c.get("conclusion") not in ("success", "skipped", "neutral")):
            return False
    if "validate" not in by_name:
        return False
    if by_name.get("risk", {}).get("status") != "completed":
        return False
    sec = next((s for s in statuses if s.get("context") == "security-review"), None)  # newest first
    return bool(sec) and sec.get("state") == "success"


def api_list(path):
    pages = json.loads(gh("api", "--paginate", "--slurp", path))
    return [x for page in pages for x in page]


def set_status(repo, sha, context, state, description):
    gh("api", f"repos/{repo}/statuses/{sha}", "-f", f"state={state}", "-f", f"context={context}",
       "-f", f"description={description[:140]}")


def sync_labels(number, level, labels):
    wanted = LABELS.get(level)
    for name in LABELS.values():
        if name == wanted and name not in labels:
            subprocess.run(["gh", "label", "create", name, "--force"], check=False, capture_output=True)
            gh("pr", "edit", str(number), "--add-label", name)
        elif name != wanted and name in labels:
            gh("pr", "edit", str(number), "--remove-label", name)


def run_wait(number, sha, run=None):
    """After the approver approved SHA: label `needs-human` and post the German note once if the PR waits for the owner."""
    run = run or gh
    repo, owner = os.environ["GH_REPO"], os.environ.get("OWNER", OWNER_DEFAULT)
    approver = os.environ.get("APPROVER_BOT", "")
    reviews = json.loads(run("api", "--paginate", "--slurp", f"repos/{repo}/pulls/{number}/reviews"))
    mine = [r for page in reviews for r in page if approver and norm((r.get("user") or {}).get("login")) == norm(approver)
            and r.get("state") in ("APPROVED", "CHANGES_REQUESTED")]
    if not mine or mine[-1]["state"] != "APPROVED" or mine[-1].get("commit_id") != sha:
        print("not approved at this head: nothing to do")
        return 0
    codeowners, agents = read_text(".github/CODEOWNERS"), read_text("AGENTS.md")
    files = [f["filename"] for page in json.loads(run("api", "--paginate", "--slurp", f"repos/{repo}/pulls/{number}/files"))
             for f in page]
    level = classify(run("pr", "diff", str(number)), agents)
    if not waits_for_owner(level, files, codeowners, owner):
        print("does not wait for the owner")
        return 0
    runs = json.loads(run("api", f"repos/{repo}/commits/{sha}/check-runs")).get("check_runs", [])
    statuses = json.loads(run("api", f"repos/{repo}/commits/{sha}/statuses"))
    if not checks_ready(runs, statuses):
        print("checks or security review not done for this head: nothing to do")
        return 0
    pr = json.loads(run("api", f"repos/{repo}/pulls/{number}"))
    if pr.get("head", {}).get("sha") != sha:
        print("head moved: nothing to do")
        return 0
    comments = [c for page in json.loads(run("api", "--paginate", "--slurp", f"repos/{repo}/issues/{number}/comments"))
                for c in page]
    if any(f"{NOTE_MARK[:-4]} {sha[:12]} -->" in (c.get("body") or "") for c in comments):
        return 0  # idempotent: label, review request and note are already set for this head
    subprocess.run(["gh", "label", "create", "needs-human", "--force"], check=False, capture_output=True)
    run("pr", "edit", str(number), "--add-label", "needs-human")
    if norm(pr.get("user", {}).get("login")) != norm(owner):  # a label alone is not in the owner's inbox
        subprocess.run(["gh", "pr", "edit", str(number), "--add-reviewer", owner], check=False, capture_output=True)
    review = mine[-1].get("body") or ""
    run("pr", "comment", str(number), "--body", build_note(sha, level, pr.get("body") or "", review))
    return 0


def run_pr(number):
    repo, owner = os.environ["GH_REPO"], os.environ.get("OWNER", OWNER_DEFAULT)
    pr = json.loads(gh("api", f"repos/{repo}/pulls/{number}"))
    if pr.get("state") == "closed":  # merged or closed: the PR no longer waits for anyone
        if "needs-human" in [lb["name"] for lb in pr.get("labels", [])]:
            gh("pr", "edit", str(number), "--remove-label", "needs-human")
        return 0
    sha, author = pr["head"]["sha"], pr["user"]["login"]
    try:
        with open("AGENTS.md", encoding="utf-8") as f:  # the checkout is the default branch
            base = f.read()
    except OSError:
        base = ""
    level = classify(gh("pr", "diff", str(number)), base)
    sync_labels(number, level, [lb["name"] for lb in pr.get("labels", [])])
    approved = True
    if level == "security":
        approved = owner_approved(api_list(f"repos/{repo}/pulls/{number}/reviews"), owner, sha)
        if not approved and norm(author) != norm(owner):
            subprocess.run(["gh", "pr", "edit", str(number), "--add-reviewer", owner], check=False, capture_output=True)
    summary = f"Risk class {level}." + ("" if approved else f" Fails until {owner} approves this commit.")
    gh("api", f"repos/{repo}/check-runs", "-f", "name=risk", "-f", f"head_sha={sha}", "-f", "status=completed",
       "-f", f"conclusion={'success' if approved else 'failure'}", "-f", f"output[title]=risk: {level}",
       "-f", f"output[summary]={summary}")
    # Only agent PRs with infra/security changes wait for the security reviewer; set once per head SHA.
    agent = norm(author) == norm(os.environ.get("AUTHOR_BOT")) and pr["head"]["ref"].startswith("agent/")
    statuses = json.loads(gh("api", f"repos/{repo}/commits/{sha}/statuses"))
    if not any(s["context"] == "security-review" for s in statuses):
        if level != "none" and agent:
            set_status(repo, sha, "security-review", "pending", "waiting for the security reviewer")
        else:
            set_status(repo, sha, "security-review", "success", "not needed (no agent PR or no infrastructure change)")
    print(f"risk: {level}")
    return 0 if approved else 1


def run_verdict(number, sha):
    repo = os.environ["GH_REPO"]
    kind = verdict_for(api_list(f"repos/{repo}/issues/{number}/comments"), sha, os.environ.get("APPROVER_BOT", ""))
    if kind == "approve":
        set_status(repo, sha, "security-review", "success", "security reviewer approved")
    elif kind == "changes":
        set_status(repo, sha, "security-review", "failure", "security reviewer asks for changes")
    else:
        set_status(repo, sha, "security-review", "failure", "security reviewer left no verdict")
        return 1
    return 0


def main(argv):
    cmd, args = (argv[1], argv[2:]) if len(argv) > 1 else ("", [])
    if cmd == "classify" and len(args) <= 1:
        agents = ""
        if args:
            with open(args[0], encoding="utf-8") as f:
                agents = f.read()
        print(classify(sys.stdin.read(), agents))
        return 0
    if cmd == "pr" and len(args) == 1:
        return run_pr(args[0])
    if cmd == "wait" and len(args) == 2:
        return run_wait(*args)
    if cmd == "verdict" and len(args) == 2:
        return run_verdict(*args)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
