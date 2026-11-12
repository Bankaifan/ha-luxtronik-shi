import importlib.util
import json
import pathlib

import pytest

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "ci" / "risk.py"
_spec = importlib.util.spec_from_file_location("risk", _path)
risk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(risk)

AGENTS = "# Rules\n\n## Limits (not negotiable)\n1. a\n2. b\n3. c\n\n## How to work\n- x\n- y\n"


def diff(path, *lines, start=1):
    body = "\n".join(lines)
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -{start},3 +{start},3 @@\n{body}\n"


def test_plain_code_and_docs_are_none():
    assert risk.classify(diff("src/app.py", "+x = 1")) == "none"
    assert risk.classify(diff("README.md", "+Mentions a token and permissions: in prose")) == "none"


def test_infra_paths():
    for p in (".github/workflows/scout.yml", ".agents/roles/developer.md", "tools/status.py", "Makefile",
              "AGENTS.project.md", "CLAUDE.md"):
        assert risk.classify(diff(p, "+echo hi")) == "infra", p


def test_security_lines_in_workflows_and_tools():
    for line in ("+permissions:", "-permissions: write-all", "+  --allowedTools Bash", "+allowed_bots: x",
                 "+  GH_TOKEN: ${{ secrets.X }}", "+x = os.environ.get('GITHUB_TOKEN')"):
        assert risk.classify(diff(".github/workflows/a.yml", line)) == "security", line
    assert risk.classify(diff("tools/x.py", "+token = 1")) == "security"


def test_security_files():
    for p in (".github/rulesets/main.json", ".github/CODEOWNERS", "tools/trusted_issues.py", "tools/ci/risk.py"):
        assert risk.classify(diff(p, "+# comment")) == "security", p


def test_security_wins_over_infra_in_any_order():
    a, b = diff("tools/status.py", "+x = 1"), diff(".github/CODEOWNERS", "+/x @a")
    assert risk.classify(a + b) == "security"
    assert risk.classify(b + a) == "security"


def test_agents_md_limits_section_only():
    assert risk.limits_range(AGENTS) == (3, 7)
    # old line 5 is inside Limits (rule 2 changes), old line 9 is in "How to work"
    assert risk.classify(diff("AGENTS.md", " 1. a", "-2. b", "+2. B", start=4), AGENTS) == "security"
    assert risk.classify(diff("AGENTS.md", " - x", "+- z", start=9), AGENTS) == "infra"


def test_owner_approval_needs_head_sha_and_latest_state():
    ok = {"user": {"login": "Bankaifan"}, "state": "APPROVED", "commit_id": "abc"}
    assert risk.owner_approved([ok], "Bankaifan", "abc")
    assert not risk.owner_approved([ok], "Bankaifan", "def")
    assert not risk.owner_approved([ok, dict(ok, state="CHANGES_REQUESTED")], "Bankaifan", "abc")
    assert not risk.owner_approved([dict(ok, user={"login": "mallory"})], "Bankaifan", "abc")
    assert not risk.owner_approved([], "Bankaifan", "abc")


def test_verdict_from_approver_comment_for_this_sha():
    bot = {"login": "my-approver[bot]"}
    sha = "a" * 40

    def c(body, user=bot):
        return {"user": user, "body": body}

    assert risk.verdict_for([c(f"security-review: approve {sha}\nok")], sha, "my-approver[bot]") == "approve"
    both = [c(f"security-review: approve {sha}"), c(f"security-review: changes {sha}")]
    assert risk.verdict_for(both, sha, "my-approver") == "changes"
    assert risk.verdict_for([c("security-review: approve " + "b" * 40)], sha, "my-approver[bot]") is None
    assert risk.verdict_for([c(f"security-review: approve {sha}", {"login": "mallory"})], sha, "my-approver[bot]") is None
    assert risk.verdict_for([c(f"security-review: approve {sha}")], sha, "") is None


def test_codeowner_paths_wait_for_owner():
    co = "/AGENTS.md @Bankaifan\n/.github/rulesets/ @Bankaifan\n# c\n/x @other\n"
    assert risk.owned_by("AGENTS.md", co, "Bankaifan")
    assert risk.owned_by(".github/rulesets/main.json", co, "Bankaifan")
    assert not risk.owned_by("x", co, "Bankaifan")
    assert not risk.owned_by("tools/status.py", co, "Bankaifan")
    assert not risk.waits_for_owner("security", [], co, "Bankaifan")  # the security reviewer gates it
    assert not risk.waits_for_owner("security", [".github/workflows/x.yml"], co, "Bankaifan")
    assert risk.waits_for_owner("infra", ["AGENTS.md"], co, "Bankaifan")
    assert not risk.waits_for_owner("infra", ["tools/status.py"], co, "Bankaifan")


GREEN_RUNS = [{"name": n, "status": "completed", "conclusion": "success"} for n in ("validate", "agent-smoke")] + [
    {"name": "risk", "status": "completed", "conclusion": "failure"}]
SEC_OK = [{"context": "security-review", "state": "success"}]


def _stub(calls, reviews, files, comments, diff_text, runs=GREEN_RUNS, statuses=SEC_OK, user="agent-bot", lossy=False):
    posted = []

    def run(*a):
        calls.append(a)
        if a[:2] == ("pr", "comment") and not lossy:
            posted.append({"body": a[a.index("--body") + 1]})
        if a[:2] == ("pr", "view") and "comments" in a:
            return json.dumps({"comments": posted})
        if a[0] == "api" and a[-1].endswith("/reviews"):
            return json.dumps([reviews])
        if a[0] == "api" and a[-1].endswith("/files"):
            return json.dumps([[{"filename": f} for f in files]])
        if a[0] == "api" and a[-1].endswith("/comments"):
            return json.dumps([comments])
        if a[0] == "api" and a[-1].endswith("/check-runs"):
            return json.dumps({"check_runs": runs})
        if a[0] == "api" and a[-1].endswith("/statuses"):
            return json.dumps(statuses)
        if a[0] == "api" and "/pulls/" in a[-1]:
            return json.dumps({"head": {"sha": "abc"}, "user": {"login": user}, "body": "Adds a gate.\nCloses #65"})
        if a[:2] == ("pr", "diff"):
            return diff_text
        return ""
    return run


def _wait_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GH_REPO", "o/r")
    monkeypatch.setenv("APPROVER_BOT", "appr")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "CODEOWNERS").write_text("/AGENTS.md @Bankaifan\n")
    monkeypatch.setattr(risk.subprocess, "run", lambda *a, **k: None)


REV = [{"user": {"login": "appr[bot]"}, "state": "APPROVED", "commit_id": "abc", "body": "Looks right."}]


def test_run_wait_all_green_labels_and_comments_once(monkeypatch, tmp_path):
    _wait_env(monkeypatch, tmp_path)
    calls = []
    run = _stub(calls, REV, ["AGENTS.md"], [], diff("AGENTS.md", "+x"))
    assert risk.run_wait("5", "abc", run) == 0
    assert ("pr", "edit", "5", "--add-label", "needs-human") in calls
    notes = [c[-1] for c in calls if c[:3] == ("pr", "comment", "5")]
    assert len(notes) == 1 and "Hallo Daniel" in notes[0] and "Adds a gate." in notes[0] and "abc" in notes[0]
    calls.clear()
    run = _stub(calls, REV, ["AGENTS.md"], [{"body": notes[0]}], diff("AGENTS.md", "+x"))
    risk.run_wait("5", "abc", run)
    assert not any(c[:2] == ("pr", "comment") or "--add-label" in c for c in calls)


def test_run_wait_fails_loudly_when_note_missing(monkeypatch, tmp_path):
    _wait_env(monkeypatch, tmp_path)
    run = _stub([], REV, ["AGENTS.md"], [], diff("AGENTS.md", "+x"), lossy=True)
    with pytest.raises(risk.liveness.ReadbackError):
        risk.run_wait("5", "abc", run)


def test_run_wait_security_review_pending_or_failed_sets_nothing(monkeypatch, tmp_path):
    _wait_env(monkeypatch, tmp_path)
    for st in ([{"context": "security-review", "state": "pending"}],
               [{"context": "security-review", "state": "failure"}], []):
        calls = []
        risk.run_wait("5", "abc", _stub(calls, REV, ["AGENTS.md"], [], diff("AGENTS.md", "+x"), statuses=st))
        assert not any(c[:2] in (("pr", "edit"), ("pr", "comment")) for c in calls), st


def test_run_wait_red_or_missing_check_sets_nothing(monkeypatch, tmp_path):
    _wait_env(monkeypatch, tmp_path)
    bad = [dict(r, conclusion="failure") if r["name"] == "agent-smoke" else r for r in GREEN_RUNS]
    for runs in (bad, GREEN_RUNS[1:], [dict(r, status="in_progress") for r in GREEN_RUNS]):
        calls = []
        risk.run_wait("5", "abc", _stub(calls, REV, ["AGENTS.md"], [], diff("AGENTS.md", "+x"), runs=runs))
        assert not any(c[:2] in (("pr", "edit"), ("pr", "comment")) for c in calls)


def test_run_wait_ignores_other_heads_and_plain_prs(monkeypatch, tmp_path):
    _wait_env(monkeypatch, tmp_path)
    for sha, files in (("zzz", ["AGENTS.md"]), ("abc", ["src/a.py"])):
        calls = []
        risk.run_wait("5", sha, _stub(calls, REV, files, [], diff("src/a.py", "+x")))
        assert not any(c[:2] == ("pr", "edit") for c in calls)


def test_removed_line_starting_with_dashes_is_scanned():
    d = "diff --git a/tools/x.sh b/tools/x.sh\n--- a/tools/x.sh\n+++ b/tools/x.sh\n@@ -1,2 +1,1 @@\n---allowedTools Bash\n keep\n"
    assert risk.classify(d) == "security"


def _pr_stub(calls, pr, statuses=(), diff_text="", files=()):
    def run(*a):
        calls.append(a)
        if a[0] == "api" and a[-1].endswith("/files"):
            return json.dumps([list(files)])
        if a[0] == "api" and a[1].endswith("/statuses"):
            return json.dumps(list(statuses))
        if a[0] == "api" and "/pulls/" in a[1]:
            return json.dumps(pr)
        if a[:2] == ("pr", "diff"):
            return diff_text
        return ""
    return run


def _pr(label_names=(), state="open", user="agent-bot", ref="agent/1-x"):
    return {"state": state, "head": {"sha": "abc", "ref": ref}, "user": {"login": user},
            "labels": [{"name": n} for n in label_names]}


def _setup_pr(monkeypatch, tmp_path, run, reviews=()):
    monkeypatch.setenv("GH_REPO", "o/r")
    monkeypatch.setenv("AUTHOR_BOT", "agent-bot")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(risk, "gh", run)
    monkeypatch.setattr(risk, "api_list", lambda path: list(reviews))
    monkeypatch.setattr(risk.subprocess, "run", lambda *a, **k: None)


def _has(calls, *parts):
    return any(all(p in c for p in parts) for c in calls)


def test_run_pr_security_fails_until_owner_approves(monkeypatch, tmp_path):
    sec = diff(".github/CODEOWNERS", "+/x @a")
    calls = []
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "CODEOWNERS").write_text("/.github/CODEOWNERS @Bankaifan\n")
    owned = [{"filename": ".github/CODEOWNERS"}]
    _setup_pr(monkeypatch, tmp_path, _pr_stub(calls, _pr(), diff_text=sec, files=owned))
    assert risk.run_pr("5") == 0  # the job stays green, the check run `risk` carries the gate
    assert _has(calls, "conclusion=failure") and _has(calls, "--add-label", "risk:security")
    assert _has(calls, "context=security-review", "state=pending")
    ok = [{"user": {"login": "Bankaifan"}, "state": "APPROVED", "commit_id": "abc"}]
    calls.clear()
    _setup_pr(monkeypatch, tmp_path, _pr_stub(calls, _pr(["risk:security"]), diff_text=sec, files=owned), reviews=ok)
    assert risk.run_pr("5") == 0
    assert _has(calls, "conclusion=success")
    assert not _has(calls, "--add-label")


def test_run_pr_infra_agent_pending_and_stale_label_removed(monkeypatch, tmp_path):
    calls = []
    _setup_pr(monkeypatch, tmp_path, _pr_stub(calls, _pr(["risk:security"]), diff_text=diff("tools/status.py", "+x = 1")))
    assert risk.run_pr("5") == 0
    assert _has(calls, "--add-label", "risk:infra") and _has(calls, "--remove-label", "risk:security")
    assert _has(calls, "conclusion=success") and _has(calls, "state=pending")


def test_run_pr_non_agent_or_none_is_success_and_status_not_overwritten(monkeypatch, tmp_path):
    calls = []
    _setup_pr(monkeypatch, tmp_path, _pr_stub(calls, _pr(user="human"), diff_text=diff("tools/status.py", "+x = 1")))
    risk.run_pr("5")
    assert _has(calls, "context=security-review", "state=success")
    calls.clear()
    _setup_pr(monkeypatch, tmp_path, _pr_stub(calls, _pr(), diff_text=diff("src/a.py", "+x = 1")))
    risk.run_pr("5")
    assert _has(calls, "state=success") and not _has(calls, "state=pending")
    calls.clear()
    _setup_pr(monkeypatch, tmp_path, _pr_stub(calls, _pr(), statuses=[{"context": "security-review"}],
                                              diff_text=diff("tools/status.py", "+x = 1")))
    risk.run_pr("5")
    assert not _has(calls, "context=security-review")


def test_run_pr_closed_removes_needs_human(monkeypatch, tmp_path):
    calls = []
    _setup_pr(monkeypatch, tmp_path, _pr_stub(calls, _pr(["needs-human"], state="closed")))
    assert risk.run_pr("5") == 0
    assert ("pr", "edit", "5", "--remove-label", "needs-human") in calls
    assert not _has(calls, "name=risk")


def test_run_verdict(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")
    monkeypatch.setenv("APPROVER_BOT", "appr")
    sha = "a" * 40
    for body, code, state in ((f"security-review: approve {sha}", 0, "success"),
                              (f"security-review: changes {sha}", 0, "failure"), ("nothing", 1, "failure")):
        calls = []
        monkeypatch.setattr(risk, "gh", lambda *a, calls=calls: calls.append(a) or "")
        monkeypatch.setattr(risk, "api_list", lambda path, body=body: [{"user": {"login": "appr[bot]"}, "body": body}])
        assert risk.run_verdict("5", sha) == code
        assert _has(calls, f"state={state}", "context=security-review")


def test_run_pr_security_outside_codeowner_paths_needs_no_owner(monkeypatch, tmp_path):
    sec = diff(".github/workflows/x.yml", "+permissions:", "+  contents: write")
    calls = []
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "CODEOWNERS").write_text("/.github/CODEOWNERS @Bankaifan\n")
    _setup_pr(monkeypatch, tmp_path, _pr_stub(calls, _pr(), diff_text=sec, files=[{"filename": ".github/workflows/x.yml"}]))
    assert risk.run_pr("5") == 0
    assert _has(calls, "conclusion=success") and _has(calls, "--add-label", "risk:security")
    assert _has(calls, "context=security-review", "state=pending")  # the AI security reviewer still gates it


def test_pr_paths_include_rename_source():
    pages = [[{"filename": "tools/x.py", "previous_filename": "tools/trusted_issues.py"}], [{"filename": "a b.py"}]]
    assert risk.pr_paths(pages) == ["a b.py", "tools/trusted_issues.py", "tools/x.py"]
