"""Judging model steps stay read-only (design 0017, step 4).

A reviewer, security reviewer, scout, unblocker or answer-receiver model step must not gain Edit, Write, a write-scope
token beyond the ones named here, or a Bash form outside its pinned list. Their read confinement is pinned in
tests/agent/test_untrusted_boundary.py (design 0004).
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODEL_ACTION = "anthropics/claude-code-action"
APP_ACTION = "actions/create-github-app-token"
READ = ["Read", "Glob", "Grep"]
WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
VERDICT_EDIT = "Edit(verdict.json)"  # the one write-named tool a judging step may have

# The --allowedTools entries of each judging model step, pinned. Any other entry fails the test.
ALLOWED = {
    "agent-review.yml": READ + ["Bash(gh pr view:*)", "Bash(gh pr review:*)", "Bash(gh issue view:*)"],
    "agent-security-review.yml": READ + ["Bash(gh pr view:*)", "Bash(gh pr diff:*)", "Bash(gh issue view:*)"],
    "scout.yml": READ + [
        "Bash(gh issue list:*)", "Bash(gh issue view:*)", "Bash(gh pr list:*)", "Bash(gh pr view:*)",
        "Bash(python3 tools/idea_route.py create:*)", "Bash(gh label create:*)",
        "Bash(gh api repos/${{ github.repository }}/dependabot/alerts?state=open)",
        "Bash(gh api repos/${{ github.repository }}/code-scanning/alerts?state=open)",
    ],
    "unblocker.yml": READ + [VERDICT_EDIT],
    "answer-receiver.yml": READ + [VERDICT_EDIT],
}
# Write scopes a judging model step may reach, by name (design 0017, section 6): `pull-requests` for `gh pr review`,
# `issues` for `idea_route.py create`. Any other write scope fails the test.
NAMED_WRITE = {
    "agent-review.yml": {"pull-requests"},
    "agent-security-review.yml": {"pull-requests"},
    "scout.yml": {"issues"},
    "unblocker.yml": set(),
    "answer-receiver.yml": set(),
}
JUDGING = sorted(ALLOWED)


def load(name):
    yaml = pytest.importorskip("yaml")  # installed by tools/ci/install_tools.sh
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))


def model_step(doc):
    """(job, step) of the one claude-code-action step; its job is the model job."""
    found = [(job, s) for job in doc["jobs"].values() for s in job["steps"] if s.get("uses", "").startswith(MODEL_ACTION)]
    assert len(found) == 1, "expected exactly one model step"
    return found[0]


def tools(doc):
    _, step = model_step(doc)
    m = re.search(r'--allowedTools "([^"]*)"', step["with"]["claude_args"])
    assert m, "the model step has no --allowedTools"
    return m.group(1).split(",")


def write_tools(doc):
    return {t for t in tools(doc) if t.split("(")[0] in WRITE_TOOLS}


def write_scopes(doc):
    """Write scopes the model step can use: its referenced app tokens, and the job token if it reads github.token."""
    job, step = model_step(doc)
    refs = str(step.get("env", {})) + str(step.get("with", {}))
    token_ids = set(re.findall(r"steps\.([\w-]+)\.outputs\.token", refs))
    scopes = set()
    for s in job["steps"]:
        if s.get("uses", "").startswith(APP_ACTION) and s.get("id") in token_ids:
            perms = {k[len("permission-"):]: v for k, v in s.get("with", {}).items() if k.startswith("permission-")}
            if not perms:  # an app token without permission inputs gets every permission of the app
                scopes.add("(all app permissions)")
            scopes |= {p for p, level in perms.items() if level == "write"}
    if "github.token" in refs:  # the job token: the job's own permissions, else the workflow's
        perms = job.get("permissions", doc.get("permissions", {}))
        scopes |= {p for p, level in perms.items() if level == "write"}
    return scopes


@pytest.mark.parametrize("name", JUDGING)
def test_tools_are_the_pinned_list(name):
    assert sorted(tools(load(name))) == sorted(ALLOWED[name])


@pytest.mark.parametrize("name", JUDGING)
def test_no_write_tool_but_the_verdict_file(name):
    assert write_tools(load(name)) <= {VERDICT_EDIT}


@pytest.mark.parametrize("name", JUDGING)
def test_write_scopes_are_the_named_ones(name):
    assert write_scopes(load(name)) == NAMED_WRITE[name]


def test_guard_catches_a_gained_write_token():
    doc = load("agent-review.yml")
    job, _ = model_step(doc)
    app = next(s for s in job["steps"] if s.get("id") == "app")
    app["with"]["permission-contents"] = "write"
    assert write_scopes(doc) != NAMED_WRITE["agent-review.yml"]


def test_guard_catches_a_gained_edit_and_bash_form():
    doc = load("unblocker.yml")
    _, step = model_step(doc)
    step["with"]["claude_args"] = step["with"]["claude_args"].replace(
        VERDICT_EDIT, VERDICT_EDIT + ",Edit,Bash(rm:*)")
    assert not write_tools(doc) <= {VERDICT_EDIT}
    assert sorted(tools(doc)) != sorted(ALLOWED["unblocker.yml"])
