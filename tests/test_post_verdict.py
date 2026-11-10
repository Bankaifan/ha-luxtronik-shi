import importlib.util
import json
import pathlib

spec = importlib.util.spec_from_file_location(
    "post_verdict", pathlib.Path(__file__).resolve().parents[1] / "tools" / "ci" / "post_verdict.py")
pv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pv)

SHA = "b9f7de0afcbe86090adf5f4673bbe3826bbb06ee"


def exec_file(result, denials=()):
    return json.dumps([{"type": "assistant", "message": {"content": [{"type": "text", "text": "thinking"}]}},
                       {"type": "result", "result": result, "permission_denials": list(denials)}])


def pr_view(a, labels, head=SHA):
    """Fake `gh pr view`: the head SHA for the headRefOid query, else the label names."""
    if a[:2] != ("pr", "view"):
        return ""
    return head + "\n" if "headRefOid" in a else labels


def test_changes_posts_comment_and_requests_changes(tmp_path):
    calls = []

    def run(*a):
        calls.append(a)
        return pr_view(a, "risk:security\n")

    text = f"Looked at it.\n\nsecurity-review: changes {SHA[:7]}\n\n- a.yml:3: Write is unscoped"
    assert pv.post(5, SHA, exec_file(text), run, tmp_path) == 0
    comment = next(c for c in calls if c[:2] == ("pr", "comment"))
    body = pathlib.Path(comment[4]).read_text()
    assert body.startswith(f"security-review: changes {SHA}\n\n- a.yml:3")
    assert ("pr", "edit", "5", "--add-label", "review:1", "--add-label", "round:b9f7de0") in calls
    assert calls[-1][:3] == ("pr", "review", "5") and "--request-changes" in calls[-1]


def test_changes_after_round_limit_requests_no_review(tmp_path):
    calls = []

    def run(*a):
        calls.append(a)
        return pr_view(a, "review:3\n")

    assert pv.post(5, SHA, exec_file(f"security-review: changes {SHA}\n- x"), run, tmp_path) == 0
    assert not any(c[:2] in (("pr", "review"), ("pr", "edit")) for c in calls)


def test_approve_posts_only_the_comment(tmp_path, monkeypatch):
    monkeypatch.delenv("APPROVER_BOT", raising=False)
    calls = []
    assert pv.post(5, SHA, exec_file(f"`security-review: approve {SHA}`\n- fine"),
                   lambda *a: calls.append(a) or pr_view(a, ""), tmp_path) == 0
    assert [c[:2] for c in calls if "headRefOid" not in c] == [("pr", "comment")]


def test_no_verdict_or_other_sha_logs_denials(tmp_path, capsys):
    calls = []
    denied = [{"tool_name": "Bash", "tool_input": {"command": "gh pr comment 5 --body x"}}]
    assert pv.post(5, SHA, exec_file("security-review: approve 1234567", denied), lambda *a: calls.append(a),
                   tmp_path) == 1
    assert calls == []
    assert "denied: Bash: gh pr comment 5 --body x" in capsys.readouterr().out


REQ = "Security review asks for changes at abc1234: see the comment."


def _review(rid, login="my-approver[bot]", state="CHANGES_REQUESTED", body=REQ):
    return {"id": rid, "state": state, "user": {"login": login}, "body": body}


def _run_with(reviews, fail_on=None):
    calls = []

    def run(*a):
        calls.append(a)
        if a[:2] == ("api", "--paginate"):
            return json.dumps([reviews])
        if fail_on is not None and a[:3] == ("api", "-X", "PUT") and f"/{fail_on}/" in a[3]:
            raise pv.subprocess.CalledProcessError(1, "gh")
        return ""

    return calls, run


def _env(monkeypatch):
    monkeypatch.setenv("APPROVER_BOT", "my-approver[bot]")
    monkeypatch.setenv("GH_REPO", "o/r")


def test_approve_dismisses_exactly_the_apps_own_security_request(tmp_path, monkeypatch):
    _env(monkeypatch)
    calls, run = _run_with([
        _review(1),
        _review(2, login="someone-else"),
        _review(3, body="Please rename this"),
        _review(4, state="APPROVED"),
        _review(5, state="COMMENTED"),
        _review(6, login="app/my-approver"),
    ])
    assert pv.post(5, SHA, exec_file(f"security-review: approve {SHA}\n- fine"), run, tmp_path) == 0
    puts = [c for c in calls if c[:3] == ("api", "-X", "PUT")]
    assert [c[3] for c in puts] == ["repos/o/r/pulls/5/reviews/1/dismissals", "repos/o/r/pulls/5/reviews/6/dismissals"]
    assert all("message=Security review approved b9f7de0" in c for c in puts)


def test_changes_verdict_dismisses_nothing(tmp_path, monkeypatch):
    _env(monkeypatch)
    calls, run = _run_with([_review(1)])
    pv.post(5, SHA, exec_file(f"security-review: changes {SHA}\n- x"), run, tmp_path)
    assert not any(c[:3] == ("api", "-X", "PUT") for c in calls)


def test_dismissal_failure_does_not_break_the_approve(tmp_path, monkeypatch):
    _env(monkeypatch)
    calls, run = _run_with([_review(1), _review(2)], fail_on=1)
    assert pv.post(5, SHA, exec_file(f"security-review: approve {SHA}"), run, tmp_path) == 0
    assert any("/reviews/2/dismissals" in c[3] for c in calls if c[:3] == ("api", "-X", "PUT"))

    def broken(*a):
        if a[:2] == ("api", "--paginate"):
            raise pv.subprocess.CalledProcessError(1, "gh")
        return ""

    assert pv.post(5, SHA, exec_file(f"security-review: approve {SHA}"), broken, tmp_path) == 0


def test_approve_without_approver_bot_dismisses_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("APPROVER_BOT", raising=False)
    calls = []
    assert pv.post(5, SHA, exec_file(f"security-review: approve {SHA}"),
                   lambda *a: calls.append(a) or pr_view(a, ""), tmp_path) == 0
    assert [c[:2] for c in calls if "headRefOid" not in c] == [("pr", "comment")]


def _labelled(labels, head=SHA):
    calls = []

    def run(*a):
        calls.append(a)
        return pr_view(a, labels, head)

    return calls, run


def _bumps(calls):
    return [c for c in calls if c[:3] == ("pr", "edit", "5") and any(x.startswith("review:") for x in c)]


def test_both_reviewers_on_one_head_count_one_round(tmp_path):
    calls, run = _labelled("review:1\nround:" + SHA[:7] + "\n")  # the code reviewer counted this head
    assert pv.post(5, SHA, exec_file(f"security-review: changes {SHA}\n- x"), run, tmp_path) == 0
    assert _bumps(calls) == []
    assert any(c[:3] == ("pr", "review", "5") and "--request-changes" in c for c in calls)


def test_first_verdict_for_a_new_head_counts_and_replaces_the_marker(tmp_path):
    calls, run = _labelled("review:1\nround:1111111\n")
    pv.post(5, SHA, exec_file(f"security-review: changes {SHA}\n- x"), run, tmp_path)
    assert ("pr", "edit", "5", "--add-label", "review:2", "--add-label", "round:" + SHA[:7]) in calls
    assert ("pr", "edit", "5", "--remove-label", "round:1111111") in calls


def test_verdict_for_a_superseded_head_is_discarded(tmp_path):
    calls, run = _labelled("", head="2" * 40)
    assert pv.post(5, SHA, exec_file(f"security-review: changes {SHA}\n- x"), run, tmp_path) == 0
    assert not any(c[:2] in (("pr", "comment"), ("pr", "review")) or "--add-label" in c for c in calls)


def test_changes_without_reason_is_no_verdict(tmp_path):
    # #292: a bare `changes` line gave the fix run nothing to fix and blocked a re-run for the same SHA.
    calls = []
    assert pv.post(5, SHA, exec_file(f"security-review: changes {SHA}"), lambda *a: calls.append(a) or "", tmp_path) == 1
    assert calls == []
