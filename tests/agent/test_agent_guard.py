import datetime
import json
import subprocess

import agent_guard as g
import decision
import guard_mark
import pytest


@pytest.mark.parametrize("form", ["bankaifan-agent-author", "app/bankaifan-agent-author",
                                  "bankaifan-agent-author[bot]", "app/Bankaifan-Agent-Author[bot]"])
def test_all_login_forms_match(form):
    assert g.same_login(form, "bankaifan-agent-author[bot]")
    assert g.norm_login(form) == "bankaifan-agent-author"


def test_empty_and_different_logins_never_match():
    assert not g.same_login("", "")
    assert not g.same_login(None, "x")
    assert not g.same_login("mallory", "bankaifan-agent-author[bot]")


class Recorder:
    def __init__(self, fail_create=False, replies=None):
        self.calls, self.fail_create, self.replies = [], fail_create, replies or {}
        self.posted, self.lossy = [], False

    def __call__(self, *args):
        self.calls.append(args)
        if args[1:2] == ("comment",) and not self.lossy:
            self.posted.append({"body": args[args.index("--body") + 1]})
        if args[1:2] == ("view",) and "comments" in args:
            return json.dumps({"comments": self.posted})
        if self.fail_create and args[:2] == ("label", "create"):
            raise subprocess.CalledProcessError(1, "gh")
        return self.replies.get(args[:2], "")


def test_labels_are_created_before_they_are_added():
    r = Recorder()
    g.add_labels("pr", 7, ["review:3", "needs-human"], r)
    assert r.calls == [("label", "create", "review:3", "--force"), ("label", "create", "needs-human", "--force"),
                       ("pr", "edit", "7", "--add-label", "review:3", "--add-label", "needs-human")]


def test_label_create_failure_does_not_stop_the_add():
    r = Recorder(fail_create=True)
    g.add_labels("issue", 3, ["agent:dev"], r)
    assert r.calls[-1] == ("issue", "edit", "3", "--add-label", "agent:dev")


T0 = "2026-11-09T10:00:00Z"


def test_dev_without_pr_is_silent():
    new = "2026-11-09T10:05:00Z"
    assert not g.dev_has_pr([{"headRefName": "agent/21-x", "createdAt": new}, {"headRefName": "main", "createdAt": new}], "22", T0)
    assert g.dev_has_pr([{"headRefName": "agent/22-slug", "createdAt": new}], "22", T0)
    assert not g.dev_has_pr([{"headRefName": "agent/220-slug", "createdAt": new}], "22", T0)


def test_dev_old_pr_for_same_issue_does_not_count():
    assert not g.dev_has_pr([{"headRefName": "agent/22-slug", "createdAt": "2026-11-01T00:00:00Z"}], "22", T0)


def test_fix_without_new_commit_is_silent():
    assert not g.head_moved("abc", "abc")
    assert not g.head_moved("abc", "")
    assert g.head_moved("abc", "def")


def test_review_missing_for_head_sha():
    reviews = [{"commit_id": "old", "user": {"login": "ap[bot]"}}, {"commit_id": "new", "user": {"login": "mallory"}}]
    assert not g.has_review(reviews, "ap[bot]", "new")
    assert g.has_review(reviews, "app/ap", "old")


def test_agent_pr_by_author_app_owner_or_label():
    assert g.is_agent_pr("app/my-author", [""], "my-author[bot]", "Bankaifan")
    assert g.is_agent_pr("Bankaifan", [""], "my-author[bot]", "Bankaifan")
    assert g.is_agent_pr("someone", ["agent:review"], "my-author[bot]", "Bankaifan")
    assert not g.is_agent_pr("someone", [""], "my-author[bot]", "Bankaifan")


def test_report_has_run_url_tail_and_masks_tokens():
    text = "\n".join(f"line {i}" for i in range(40)) + "\nghp_" + "a" * 30
    body = g.report("dev", "no PR was produced", "https://x/run/1", text)
    assert "https://x/run/1" in body and "line 39" in body and "line 5\n" not in body
    assert "ghp_" not in body and "***" in body
    assert "(no execution file)" in g.report("fix", "x", "", "")


def test_report_lists_denied_calls_not_the_raw_tail():
    denials = [{"tool_name": "Bash", "tool_input": {"command": "cat a.txt ghp_" + "b" * 30}},
               {"tool_name": "Read", "tool_input": {"file_path": "/etc/x"}}]
    denials += [{"tool_name": "Bash", "tool_input": {"command": f"ls {i}"}} for i in range(12)]
    text = json.dumps([{"type": "assistant"}, {"type": "result", "permission_denials": denials}])
    body = g.report("dev", "no PR", "https://x/run/1", text)
    assert "Denied tool calls:" in body and "Bash: cat a.txt" in body and "Read: /etc/x" in body
    assert "ghp_" not in body and "... and 4 more" in body and "ls 7" in body and "ls 8" not in body
    assert '"type"' not in body


def test_denied_calls_mask_token_straddling_the_cut():
    cmd = "x" * 140 + " ghp_" + "c" * 30
    out = g.denied_calls(json.dumps({"permission_denials": [{"tool_name": "Bash", "tool_input": {"command": cmd}}]}))
    assert out and "ghp_" not in out[0] and "c" * 5 not in out[0]


def test_report_without_denials_keeps_the_tail():
    body = g.report("dev", "no PR", "", json.dumps([{"type": "result", "permission_denials": []}]))
    assert "no denied tool calls found" in body and "permission_denials" in body


def test_escalate_issue_labels_comments_assigns(monkeypatch):
    monkeypatch.delenv("EXEC_FILE", raising=False)
    r = Recorder()
    g.escalate("dev", "22", False, "no PR", "Bankaifan", r)
    kinds = [c[:2] for c in r.calls]
    assert ("issue", "comment") in kinds and ("issue", "edit") in kinds
    assert r.calls[-1] == ("issue", "edit", "22", "--add-assignee", "Bankaifan")


def test_escalate_pr_requests_review_unless_owner_is_author(monkeypatch):
    monkeypatch.delenv("EXEC_FILE", raising=False)
    r = Recorder(replies={("pr", "view"): json.dumps({"author": {"login": "app/my-author"}})})
    g.escalate("fix", "5", True, "no fix", "Bankaifan", r)
    assert ("pr", "edit", "5", "--add-reviewer", "Bankaifan") in r.calls
    r = Recorder(replies={("pr", "view"): json.dumps({"author": {"login": "Bankaifan"}})})
    g.escalate("fix", "5", True, "no fix", "Bankaifan", r)
    assert ("pr", "edit", "5", "--add-reviewer", "Bankaifan") not in r.calls


@pytest.fixture
def stub_gh(tmp_path, monkeypatch):
    """A fake `gh` on PATH: logs each call to calls.log, answers `pr list`, `pr view` and `api` from env JSON."""
    script = tmp_path / "gh"
    script.write_text(
        '#!/usr/bin/env python3\n'
        'import json, os, sys\n'
        'a = sys.argv[1:]\n'
        'open(os.environ["GH_LOG"], "a").write(" ".join(a) + "\\n")\n'
        'store = os.environ["GH_LOG"] + ".comments"\n'
        'posted = json.load(open(store)) if os.path.exists(store) else []\n'
        'if a[1:2] == ["comment"]:\n'
        '    posted.append({"body": a[a.index("--body") + 1]})\n'
        '    json.dump(posted, open(store, "w"))\n'
        'elif a[1:2] == ["view"] and "comments" in a:\n'
        '    print(json.dumps({"comments": posted}))\n'
        'elif a[:2] == ["pr", "list"]:\n'
        '    sys.stdout.write(os.environ["GH_PR_LIST"])\n'
        'elif a[:2] == ["pr", "view"] and "--jq" in a and "headRefOid" in a:\n'
        '    print(os.environ.get("GH_HEAD", "sha1"))\n'
        'elif a[:2] == ["pr", "view"]:\n'
        '    sys.stdout.write(os.environ["GH_PR_VIEW"])\n'
        'elif a[:2] == ["api", "--paginate"]:\n'
        '    sys.stdout.write(os.environ["GH_REVIEWS"])\n')
    script.chmod(0o755)
    log = tmp_path / "calls.log"
    log.write_text("")
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin:/bin")
    monkeypatch.setenv("GH_LOG", str(log))
    monkeypatch.setenv("GH_REPO", "o/r")
    monkeypatch.delenv("EXEC_FILE", raising=False)
    monkeypatch.setenv("GH_PR_LIST", "[]")
    monkeypatch.setenv("GH_PR_VIEW", json.dumps({"headRefOid": "abc", "author": {"login": "app/x"}}))
    monkeypatch.setenv("GH_REVIEWS", "[[]]")
    return lambda: log.read_text().splitlines()


def test_cli_same_exit_codes():
    assert g.main(["g", "same", "app/Foo", "foo[bot]"]) == 0
    assert g.main(["g", "same", "mallory", "foo[bot]"]) == 1
    assert g.main(["g", "same", "", ""]) == 1


def test_cli_agent_pr_exit_codes(monkeypatch):
    monkeypatch.setenv("AUTHOR_BOT", "my-author[bot]")
    assert g.main(["g", "agent-pr", "app/my-author"]) == 0
    assert g.main(["g", "agent-pr", "someone", "x,agent:review"]) == 0
    assert g.main(["g", "agent-pr", "someone", "x"]) == 1
    assert g.main(["g", "agent-pr", "someone"]) == 1


def test_cli_label_creates_then_adds(stub_gh):
    assert g.main(["g", "label", "pr", "7", "agent:review"]) == 0
    assert stub_gh() == ["label create agent:review --force", "pr edit 7 --add-label agent:review"]


def test_cli_unknown_command_fails():
    assert g.main(["g", "bogus"]) == 2


def test_silent_wrong_arg_count_escalates_and_fails(stub_gh):
    assert g.main(["g", "silent", "fix", "5"]) == 1
    log = stub_gh()
    assert any(c.startswith("pr comment 5") for c in log) and "pr edit 5 --add-label needs-human" in log
    assert g.main(["g", "silent", "dev", "22"]) == 1
    assert any(c.startswith("issue comment 22") for c in stub_gh())


def test_silent_guard_error_comment_names_the_reason(stub_gh):
    assert g.silent_guarded(["fix", "5"], "Bankaifan", g.silent_check) == 1
    assert any(c.startswith("pr comment 5") and "guard error" in c for c in stub_gh())


def test_silent_exception_in_guard_escalates(stub_gh):
    def boom(args, owner):
        raise RuntimeError("kaboom ghp_" + "d" * 30)
    assert g.silent_guarded(["review", "5", "sha"], "Bankaifan", boom) == 1
    assert any(c.startswith("pr comment 5") for c in stub_gh())


def test_silent_extra_args_are_ignored(stub_gh):
    assert g.main(["g", "silent", "fix", "5", "old", "/nonexistent", "extra"]) == 0  # head moved: quiet
    assert not any(c.startswith("pr comment") for c in stub_gh())
    assert g.main(["g", "silent", "dev", "22", T0, "extra"]) == 0  # no PR: normal escalation, not a guard error
    assert any(c.startswith("issue comment 22") for c in stub_gh())


def test_silent_dev_escalates_without_new_pr(stub_gh, monkeypatch):
    monkeypatch.setenv("GH_PR_LIST", json.dumps([{"headRefName": "agent/22-x", "createdAt": "2026-11-01T00:00:00Z"}]))
    assert g.main(["g", "silent", "dev", "22", T0]) == 0
    assert any(c.startswith("issue comment 22") for c in stub_gh())
    assert "issue edit 22 --add-label needs-human" in stub_gh()


def test_silent_dev_quiet_with_new_pr(stub_gh, monkeypatch):
    monkeypatch.setenv("GH_PR_LIST", json.dumps([{"headRefName": "agent/22-x", "createdAt": "2026-11-09T10:05:00Z"}]))
    assert g.main(["g", "silent", "dev", "22", T0]) == 0
    assert not any(c.startswith("issue comment") for c in stub_gh())


def test_silent_fix_paths(stub_gh):
    assert g.main(["g", "silent", "fix", "5", "abc"]) == 0  # head unchanged -> escalate
    assert any(c.startswith("pr comment 5") for c in stub_gh())
    open_log = stub_gh()
    assert g.main(["g", "silent", "fix", "5", "old"]) == 0  # head moved -> quiet
    assert len(stub_gh()) == len(open_log) + 1  # only the pr view


def _settled_view(**kw):
    view = {"headRefOid": "abc", "labels": [], "reviewDecision": "APPROVED", "body": "Closes #456",
            "author": {"login": "app/x"},
            "statusCheckRollup": [{"name": "validate", "conclusion": "SUCCESS"}]}
    view.update(kw)
    return json.dumps(view)


def test_silent_fix_on_a_settled_pr_is_logged_not_parked(stub_gh, monkeypatch, capsys):
    monkeypatch.setenv("GH_PR_VIEW", _settled_view())
    assert g.main(["g", "silent", "fix", "5", "abc"]) == 0
    assert "logged only" in capsys.readouterr().out
    assert not any("needs-human" in c or c.startswith("pr comment") for c in stub_gh())


def test_silent_fix_on_an_unsettled_pr_still_escalates(stub_gh, monkeypatch):
    monkeypatch.setenv("GH_PR_VIEW", _settled_view(reviewDecision="REVIEW_REQUIRED"))
    assert g.main(["g", "silent", "fix", "5", "abc"]) == 0
    assert "pr edit 5 --add-label needs-human" in stub_gh()


def test_silent_review_paths(stub_gh, monkeypatch):
    monkeypatch.setenv("APPROVER_BOT", "ap[bot]")
    assert g.main(["g", "silent", "review", "5", "sha1"]) == 0  # no review -> escalate
    assert any(c.startswith("pr comment 5") for c in stub_gh())
    monkeypatch.setenv("GH_REVIEWS", json.dumps([[{"commit_id": "sha1", "user": {"login": "ap[bot]"}}]]))
    assert g.main(["g", "reviewed", "5", "sha1"]) == 0
    assert g.main(["g", "reviewed", "5", "other"]) == 1
    n = len(stub_gh())
    assert g.main(["g", "silent", "review", "5", "sha1"]) == 0
    assert not any(c.startswith("pr comment") for c in stub_gh()[n:])


def test_review_is_keyed_on_sha_and_body_hash():
    h1, h2 = g.body_hash("Closes #1"), g.body_hash("Refs #1")
    assert h1 != h2 and g.body_hash(" Refs #1\n") == h2
    rv = [{"commit_id": "s", "user": {"login": "ap[bot]"}, "body": f"no\nbody-hash: {h1}"}]
    assert g.has_review(rv, "ap", "s", h1)
    assert not g.has_review(rv, "ap", "s", h2)  # body edited after the review: review again, same SHA
    assert g.has_review(rv, "ap", "s")  # no hash asked: SHA only


def test_review_without_body_hash_line_falls_back_to_sha_only():
    rv = [{"commit_id": "s", "user": {"login": "ap[bot]"}, "body": "looks fine"}]
    assert g.has_review(rv, "ap", "s", g.body_hash("anything"))
    assert not g.has_review(rv, "ap", "other", g.body_hash("anything"))


def test_cli_body_hash_rereview(stub_gh, monkeypatch):
    monkeypatch.setenv("APPROVER_BOT", "ap[bot]")
    monkeypatch.setenv("GH_PR_VIEW", json.dumps({"body": "Refs #53"}))
    assert g.main(["g", "body-hash", "5"]) == 0
    old = g.body_hash("Closes #53")
    monkeypatch.setenv("GH_REVIEWS", json.dumps([[{"commit_id": "s", "user": {"login": "ap[bot]"}, "body": f"body-hash: {old}"}]]))
    assert g.main(["g", "reviewed", "5", "s", old]) == 0
    assert g.main(["g", "reviewed", "5", "s", g.body_hash("Refs #53")]) == 1


def test_body_only_silent_fix(stub_gh, tmp_path, monkeypatch):
    before = tmp_path / "body-before.txt"
    before.write_text("Closes #53\n")
    # head unchanged, body unchanged -> escalate
    stub_gh_env = {"headRefOid": "abc", "author": {"login": "app/x"}, "body": "Closes #53"}
    monkeypatch.setenv("GH_PR_VIEW", json.dumps(stub_gh_env))
    assert g.main(["g", "silent", "fix", "5", "abc", str(before)]) == 0
    assert any(c.startswith("pr comment 5") for c in stub_gh())
    # head unchanged, body changed -> not silent
    n = len(stub_gh())
    monkeypatch.setenv("GH_PR_VIEW", json.dumps({**stub_gh_env, "body": "Refs #53"}))
    assert g.main(["g", "silent", "fix", "5", "abc", str(before)]) == 0
    assert len(stub_gh()) == n + 1  # only the pr view


def test_fix_produced():
    assert g.fix_produced("a", "b", None, "x")
    assert not g.fix_produced("a", "a", None, "x")
    assert not g.fix_produced("a", "a", "x\n", "x")
    assert g.fix_produced("a", "a", "x", "y")


def test_missing_body_file_is_unknown_not_empty(stub_gh, tmp_path, monkeypatch):
    missing = str(tmp_path / "body-before.txt")  # the save step never wrote it
    assert g.read_body_before(missing) is None
    assert g.read_body_before(None) is None
    assert not g.fix_produced("a", "a", g.read_body_before(missing), "Refs #53")  # unknown body: head decides
    monkeypatch.setenv("GH_PR_VIEW", json.dumps({"headRefOid": "abc", "body": "Refs #53", "author": {"login": "app/x"}}))
    assert g.main(["g", "silent", "fix", "5", "abc", missing]) == 0
    assert any(c.startswith("pr comment 5") for c in stub_gh())  # escalated, not treated as a changed body


BOT = "my-author[bot]"
NOW = datetime.datetime(2026, 11, 9, 12, tzinfo=datetime.UTC)
DENIAL = {"tool_name": "Bash", "tool_input": {"command": "gh issue list | head"}}


class OrchGh:
    """Fake gh for the orchestrator guard: answers by command, logs every call."""
    def __init__(self, events=(), comments=(), prs=(), issues=(), open_issues=()):
        self.calls = []
        self.data = {("issue", "list", "--state", "open"): list(open_issues),
                     ("pr", "list"): list(prs), ("issue", "list", "--state", "all"): list(issues)}
        self.events, self.comments = list(events), list(comments)
        self.posted, self.lossy = [], False

    def __call__(self, *a):
        self.calls.append(a)
        if a[1:2] == ("comment",) and not self.lossy:
            self.posted.append({"body": a[a.index("--body") + 1]})
        if a[:2] == ("issue", "view") and "comments" in a:
            return json.dumps({"comments": self.posted})
        if a[0] == "api" and "/issues/events" in a[-1]:
            return json.dumps(self.events)
        if a[0] == "api":
            return json.dumps([self.comments])
        for k, v in self.data.items():
            if a[:len(k)] == k:
                return json.dumps(v)
        return ""

    def made(self, *prefix):
        return [c for c in self.calls if c[:len(prefix)] == prefix]


@pytest.fixture
def orch_env(tmp_path, monkeypatch):
    f = tmp_path / "exec.json"

    def setup(denials=(), startable=False, result=""):
        f.write_text(json.dumps([{"type": "result", "result": result, "permission_denials": list(denials)}]))
        monkeypatch.setenv("EXEC_FILE", str(f))
        monkeypatch.setenv("STARTABLE", "true" if startable else "false")
    monkeypatch.setenv("GH_REPO", "o/r")
    monkeypatch.setenv("AUTHOR_BOT", BOT)
    monkeypatch.setenv("RUN_URL", "https://x/run/9")
    monkeypatch.delenv("STATUS_ISSUE", raising=False)
    return setup


def test_orchestrator_denials_escalate(orch_env):
    orch_env(denials=[DENIAL] * 3)
    r = OrchGh()
    assert g.silent_orchestrator(T0, r) == 1
    comment = r.made("issue", "comment", "57")
    assert comment and "https://x/run/9" in comment[0][-1] and "Bash: gh issue list" in comment[0][-1]
    assert not r.made("issue", "create")  # first failure: no issue yet


def test_denied_gh_run_view_fails_the_run_even_with_a_conclusion(orch_env):
    # Run 42821430379 (issue #313): two denied `gh run view` calls, the run still ended with a Conclusion line.
    # The guard keys on denials, not on the Conclusion line, so that run must fail and name the calls.
    run_view = [{"tool_name": "Bash", "tool_input": {"command": f"gh run view 42821187787{flag}"}}
                for flag in ("", " --log-failed")]
    orch_env(denials=run_view, result="Conclusion: Started prio:1 issue #309.")
    r = OrchGh()
    assert g.silent_orchestrator(T0, r) == 1
    comment = r.made("issue", "comment", "57")
    assert comment and "Bash: gh run view 42821187787 --log-failed" in comment[0][-1]


def test_run_with_conclusion_and_no_denials_passes(orch_env):
    orch_env(startable=True, result="Started #313 with a slip.\nConclusion: Started #313 with a slip.")
    r = OrchGh(comments=[{"user": {"login": BOT}, "created_at": "2026-11-09T10:05:00Z"}])  # a visible action
    assert g.silent_orchestrator(T0, r) == 0
    assert not r.made("issue", "comment")


def test_orchestrator_free_slot_without_action_escalates(orch_env):
    orch_env(startable=True)
    r = OrchGh(events=[{"actor": {"login": "mallory"}, "created_at": "2026-11-09T10:05:00Z"}],
               comments=[{"user": {"login": BOT}, "created_at": "2026-11-09T09:00:00Z"}])  # before the run
    assert g.silent_orchestrator(T0, r) == 1
    assert r.made("issue", "comment", "57")


@pytest.mark.parametrize("kw", [
    {"events": [{"actor": {"login": "app/my-author"}, "created_at": "2026-11-09T10:05:00Z"}]},
    {"comments": [{"user": {"login": BOT}, "created_at": "2026-11-09T10:05:00Z"}]},
    {"prs": [{"author": {"login": "app/my-author"}, "createdAt": "2026-11-09T10:05:00Z"}]},
    {"issues": [{"author": {"login": "app/my-author"}, "createdAt": "2026-11-09T10:05:00Z"}]},
])
def test_orchestrator_visible_action_is_fine(orch_env, kw):
    orch_env(startable=True)
    r = OrchGh(**kw)
    assert g.silent_orchestrator(T0, r) == 0
    assert not r.made("issue", "comment")


def test_orchestrator_nothing_to_do_is_quiet(orch_env):
    orch_env(startable=False)
    r = OrchGh()
    assert g.silent_orchestrator(T0, r) == 0
    assert not r.calls


def test_orchestrator_second_failure_same_day_opens_one_issue(orch_env):
    orch_env(denials=[DENIAL])
    prior = {"user": {"login": BOT}, "created_at": "2026-11-09T08:00:00Z", "body": g.ORCH_MARK + ": 1 tool call(s)"}
    r = OrchGh(comments=[prior])
    g.escalate_orchestrator("denied", "57", "o/r", BOT, r, now=NOW)
    created = r.made("issue", "create")
    assert len(created) == 1 and "prio:1" in created[0]
    # an open issue with that title already exists: no duplicate
    r = OrchGh(comments=[prior], open_issues=[{"title": g.ORCH_REPEAT_TITLE}])
    g.escalate_orchestrator("denied", "57", "o/r", BOT, r, now=NOW)
    assert not r.made("issue", "create") and r.made("issue", "comment", "57")


def test_escalate_fails_loudly_when_comment_missing(monkeypatch):
    monkeypatch.delenv("EXEC_FILE", raising=False)
    r = Recorder()
    r.lossy = True
    with pytest.raises(g.liveness.ReadbackError):
        g.escalate("dev", "22", False, "no PR", "Bankaifan", r)


def test_escalate_orchestrator_fails_loudly_when_comment_missing(orch_env):
    orch_env(denials=[DENIAL])
    r = OrchGh()
    r.lossy = True
    with pytest.raises(g.liveness.ReadbackError):
        g.escalate_orchestrator("denied", "57", "o/r", BOT, r, now=NOW)


def test_orchestrator_old_failure_does_not_count(orch_env):
    old = {"user": {"login": BOT}, "created_at": "2026-11-07T08:00:00Z", "body": g.ORCH_MARK}
    r = OrchGh(comments=[old])
    g.escalate_orchestrator("denied", "57", "o/r", BOT, r,
                            now=NOW)
    assert not r.made("issue", "create")


def _pr_run(labels="", head="a" * 40):
    calls = []

    def run(*a):
        calls.append(a)
        if a[:2] == ("pr", "view"):
            return head + "\n" if "headRefOid" in a else labels
        return ""

    return calls, run


def test_round_is_counted_once_per_head():
    sha = "a" * 40
    calls, run = _pr_run("review:1\nround:" + sha[:7] + "\n")
    assert g.count_round(5, sha, run) == "already"
    assert not any("--add-label" in c for c in calls)
    calls, run = _pr_run("review:1\nround:bbbbbbb\n")
    assert g.count_round(5, sha, run) == "counted"
    assert ("pr", "edit", "5", "--add-label", "review:2", "--add-label", "round:aaaaaaa") in calls
    assert ("pr", "edit", "5", "--remove-label", "round:bbbbbbb") in calls
    calls, run = _pr_run("review:3\n")
    assert g.count_round(5, sha, run) == "limit"
    assert not any("--add-label" in c for c in calls)


def test_stale_head_is_detected_and_fails_open():
    assert g.is_stale_head(5, "b" * 40, _pr_run()[1])
    assert not g.is_stale_head(5, "a" * 40, _pr_run()[1])

    def broken(*a):
        raise subprocess.CalledProcessError(1, "gh")

    assert not g.is_stale_head(5, "b" * 40, broken)


def test_silent_review_check_ignores_a_superseded_head(monkeypatch):
    monkeypatch.setattr(g, "gh", _pr_run(head="c" * 40)[1])
    monkeypatch.setattr(g, "reviews_of", lambda *a: pytest.fail("must not look for a review of a stale head"))
    assert g.silent_check(["review", "5", "d" * 40], "Bankaifan") == 0


# --- denial notes (#416 goals 1, 3, 4): retrigger only after a change, never on protected paths, cap on a repeat ---

DENIED = {"tool_name": "Bash", "tool_input": {"command": "gh issue list | head"}}
OTHER = {"tool_name": "Bash", "tool_input": {"command": "gh pr list"}}
T1, T2 = "2026-11-09T10:10:00Z", "2026-11-09T11:00:00Z"


def write_exec(tmp_path, monkeypatch, denials):
    f = tmp_path / "exec.json"
    f.write_text(json.dumps([{"type": "result", "permission_denials": list(denials)}]))
    monkeypatch.setenv("EXEC_FILE", str(f))
    monkeypatch.setenv("AUTHOR_BOT", BOT)
    monkeypatch.setenv("GH_REPO", "o/r")


def note(id, body, at, login=BOT):
    return {"id": id, "user": {"login": login}, "created_at": at, "body": body}


class Hist(Recorder):
    """Recorder that also serves the issue comments (the history) and the commits of the watched files."""
    def __init__(self, history=(), commits=None):
        super().__init__()
        self.history, self.commits = list(history), commits or {}

    def __call__(self, *args):
        if args[:2] == ("api", "--paginate") and args[-1].endswith("/comments"):
            return json.dumps([self.history])
        if args[0] == "api" and "/commits?" in args[1]:
            return json.dumps(self.commits.get(args[1].split("path=")[1].split("&")[0], []))
        return super().__call__(*args)


def denial_run(tmp_path, monkeypatch, history=(), commits=None, denials=(DENIED,)):
    """One denied run escalated on issue 22; returns the posted note and the fake gh."""
    write_exec(tmp_path, monkeypatch, denials)
    r = Hist(history, commits)
    g.escalate("dev", "22", False, "no PR", "Bankaifan", r)
    return r.posted[0]["body"], r


def test_first_denial_offers_the_retrigger(tmp_path, monkeypatch):
    body, _ = denial_run(tmp_path, monkeypatch)
    assert "(ja)" in body and decision.parse(body) == {"yes": "drop-block", "no": "close-issue"}


def test_135_same_denial_again_gives_no_retrigger_and_ends_restarts(tmp_path, monkeypatch):
    first, _ = denial_run(tmp_path, monkeypatch)
    second, r = denial_run(tmp_path, monkeypatch, history=[note(1, first, T1)])
    assert "(ja)" not in second and decision.parse(second) == {"no": "close-issue"}
    assert ("issue", "edit", "22", "--add-label", "needs-human", "--add-label", "restart:1",
            "--add-label", "unblock:1") in r.calls


def test_a_slip_comment_after_the_last_denial_offers_the_retrigger_again(tmp_path, monkeypatch):
    first, _ = denial_run(tmp_path, monkeypatch)
    hist = [note(1, first, T1), {"id": 2, "user": {"login": "stranger"}, "created_at": T2, "body": "clarified"}]
    second, _ = denial_run(tmp_path, monkeypatch, history=hist, denials=(OTHER,))
    assert "(ja)" in second


def test_answered_owner_comment_and_receiver_confirmation_do_not_reopen(tmp_path, monkeypatch):
    first, _ = denial_run(tmp_path, monkeypatch)
    hist = [note(1, first, T1), {"id": 2, "user": {"login": "Bankaifan"}, "created_at": T2, "body": "ja"},
            note(3, "Verstanden <!-- answer-receiver comment=2 -->", T2)]
    second, _ = denial_run(tmp_path, monkeypatch, history=hist, denials=(OTHER,))
    assert "(ja)" not in second


def test_a_commit_to_the_allow_list_offers_the_retrigger_again(tmp_path, monkeypatch):
    first, _ = denial_run(tmp_path, monkeypatch)
    commits = {".github/workflows/agent-dev.yml": [{"sha": "abc"}]}
    second, _ = denial_run(tmp_path, monkeypatch, history=[note(1, first, T1)], commits=commits, denials=(OTHER,))
    assert "(ja)" in second


def test_protected_path_gives_a_note_and_never_a_retrigger(tmp_path, monkeypatch):
    edit = {"tool_name": "Edit", "tool_input": {"file_path": ".github/CODEOWNERS"}}
    body, _ = denial_run(tmp_path, monkeypatch, denials=(edit,))
    assert "(ja)" not in body and "geschuetzte Datei" in body and "CODEOWNERS" in body
    assert decision.parse(body) == {"no": "close-issue"}


def test_unreadable_history_offers_no_retrigger(tmp_path, monkeypatch):
    write_exec(tmp_path, monkeypatch, [DENIED])
    r = Recorder()  # the history read returns nothing: unknown, fail closed
    g.escalate("dev", "22", False, "no PR", "Bankaifan", r)
    assert "(ja)" not in r.posted[0]["body"] and "nicht lesbar" in r.posted[0]["body"]


def test_owner_note_refuses_a_body_without_decision_marker():  # #416 req. 7
    r = Recorder()
    with pytest.raises(ValueError):
        g.post_owner_note("issue", 5, "Soll ich das tun?", r)
    assert not any(c[:2] == ("issue", "comment") for c in r.calls)
    g.post_owner_note("issue", 5, "Soll ich das tun?\n" + decision.build(yes="drop-block"), r)
    assert r.posted and "decision:" in r.posted[0]["body"]


def test_park_adds_marker_and_refuses_a_bad_action():  # #416 req. 7
    r = Recorder()
    g.park("pr", 5, "drop-block", "close-pr", "Frage?", r)
    assert decision.parse(r.posted[0]["body"]) == {"yes": "drop-block", "no": "close-pr"}
    g.park("issue", 6, "-", "close-issue", "Frage?", r)
    assert decision.parse(r.posted[1]["body"]) == {"no": "close-issue"}
    with pytest.raises(ValueError):
        g.park("issue", 7, "merge", "-", "Frage?", r)
    assert len(r.posted) == 2


# --- upstream issue for an allow-list miss (#416 goal 2, security requirements 3 to 5) ---

GKEY = "k" * 40
SLIP = "Slip body"


def denial_text(*denials):
    return json.dumps([{"type": "result", "permission_denials": list(denials)}])


def miss_title(text, workflow="agent-dev"):
    return f"Denied command in {workflow}: {' '.join(g.denied_tools(text))} ({g.denial_sig(text)})"


class Upstream(Recorder):
    """Fake gh for the upstream route: template.json (None = 404), the source issue, the open denied-command family."""
    def __init__(self, template=None, body=SLIP, title="Slip", family=()):
        super().__init__(replies={("issue", "create"): "https://github.com/o/r/issues/77\n"})
        self.template, self.body, self.title, self.family = template, body, title, list(family)

    def __call__(self, *args):
        if args[0] == "api" and args[-1].endswith("/contents/.agents/template.json"):
            self.calls.append(args)
            if self.template is None:
                raise subprocess.CalledProcessError(1, "gh", stderr="gh: Not Found (HTTP 404)")
            return self.template
        if args[:2] == ("issue", "view") and "title,body" in args:
            self.calls.append(args)
            return json.dumps({"title": self.title, "body": self.body})
        if args[:2] == ("issue", "list"):
            self.calls.append(args)
            return json.dumps([{"number": n, "title": t} for n, t in self.family])
        return super().__call__(*args)

    def made(self, *prefix):
        return [c for c in self.calls if c[:len(prefix)] == prefix]


@pytest.fixture
def upstream_env(monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")
    monkeypatch.setenv("GUARD_KEY", GKEY)
    monkeypatch.setenv("RUN_URL", "https://x/run/3")
    monkeypatch.setenv("AUTHOR_BOT", BOT)


def test_allow_list_miss_creates_one_signed_issue_and_the_source_waits(upstream_env):
    text = denial_text(DENIED)
    r = Upstream()
    assert g.route_upstream("dev", "22", text, r)
    (create,) = r.made("issue", "create")
    title, body = create[create.index("--title") + 1], create[create.index("--body") + 1]
    assert title == miss_title(text) and guard_mark.verify(title, body, GKEY)
    assert "gh issue list" not in title + body  # the model's command text never reaches the signed issue
    (edit,) = r.made("issue", "edit", "22")
    assert "Depends on: #77" in edit[edit.index("--body") + 1].splitlines()
    assert not any("--add-label" in c and "needs-human" in c for c in r.calls)


def test_next_run_with_the_same_miss_bumps_the_issue(upstream_env):
    text = denial_text(DENIED)
    r = Upstream(family=[(77, miss_title(text))])
    assert g.route_upstream("dev", "22", text, r)
    assert not r.made("issue", "create")
    assert r.made("issue", "comment", "77") and r.made("issue", "edit", "22")


def test_cap_per_workflow_stops_new_upstream_issues(upstream_env):
    text = denial_text(DENIED)
    family = [(i, f"Denied command in agent-dev: Edit (old{i:04d})") for i in range(g.UPSTREAM_CAP)]
    r = Upstream(family=family)
    assert not g.route_upstream("dev", "22", text, r)
    assert not r.made("issue", "create") and not r.made("issue", "edit")
    assert g.route_upstream("fix", "22", text, Upstream(family=family))  # the cap is per workflow


def test_forged_marker_is_never_resigned(upstream_env):
    forged = SLIP + "\n\n<!-- guard-sig: " + "0" * 64 + " -->"
    r = Upstream(body=forged)
    assert not g.route_upstream("dev", "22", denial_text(DENIED), r)
    assert not r.made("issue", "create") and not r.made("issue", "edit")
    with pytest.raises(ValueError):
        g.add_dependency("22", "#77", GKEY, r)
    assert not r.made("issue", "edit")


def test_verified_signature_is_renewed_with_the_dependency_line(upstream_env):
    r = Upstream(body=guard_mark.sign("Slip", SLIP, GKEY))
    g.add_dependency("22", "#77", GKEY, r)
    (edit,) = r.made("issue", "edit", "22")
    new = edit[edit.index("--body") + 1]
    assert "Depends on: #77" in new.splitlines() and guard_mark.verify("Slip", new, GKEY)


def test_dependency_already_named_is_not_added_twice(upstream_env):
    r = Upstream(body="Slip\n\nDepends on: #77\n")
    g.add_dependency("22", "#77", GKEY, r)
    g.add_dependency("22", "#7", GKEY, r)  # #7 is not #77
    assert len(r.made("issue", "edit", "22")) == 1


def test_protected_path_never_routes(upstream_env):
    edit = {"tool_name": "Edit", "tool_input": {"file_path": ".github/CODEOWNERS"}}
    r = Upstream()
    assert not g.route_upstream("dev", "22", denial_text(edit), r)
    assert not r.made("issue", "create")


@pytest.mark.parametrize("template", ['{"template": "other/agent-template"}', "not json", '{"template": "a b/c"}'])
def test_downstream_or_unreadable_template_does_not_route(upstream_env, template):
    r = Upstream(template=template)
    assert not g.route_upstream("dev", "22", denial_text(DENIED), r)
    assert not r.made("issue", "create")


def test_routes_upstream_reads_the_default_branch(upstream_env):
    r = Upstream(template='{"template": "O/R"}')
    assert g.routes_upstream(r) == ""  # the template names this repo (case-insensitive)
    (call,) = r.made("api")
    assert call[-1] == "repos/o/r/contents/.agents/template.json"  # no ref: the default branch
    assert g.routes_upstream(Upstream()) == ""  # 404: no template.json, this repo is the template
    assert g.routes_upstream(Upstream(template='{"template": "other/tpl"}')) == "other/tpl"


def test_no_key_means_no_upstream_issue(upstream_env, monkeypatch):
    monkeypatch.delenv("GUARD_KEY")
    r = Upstream()
    assert not g.route_upstream("dev", "22", denial_text(DENIED), r)
    assert not r.calls


def test_only_harness_tool_names_reach_the_title():
    odd = {"tool_name": "Bash; rm -rf", "tool_input": {"command": "x"}}
    assert g.denied_tools(denial_text(DENIED, odd)) == ["Bash"]


def test_denied_issue_escalation_waits_instead_of_needs_human(tmp_path, monkeypatch, upstream_env):
    f = tmp_path / "exec.json"
    f.write_text(denial_text(DENIED))
    monkeypatch.setenv("EXEC_FILE", str(f))
    r = Upstream()
    g.escalate("dev", "22", False, "no PR", "Bankaifan", r)
    assert r.made("issue", "create") and r.made("issue", "edit", "22")
    assert not any("--add-label" in c and "needs-human" in c for c in r.calls)
