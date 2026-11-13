import importlib.util
import pathlib
import subprocess

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "overlap.py"
_spec = importlib.util.spec_from_file_location("overlap", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

SLIP = ("Files: tools/overlap.py, tests/test_overlap.py, .agents/roles/orchestrator.md "
        "(disjoint from open PR #213: tools/status.py). Acceptance: tests fail without the change.")


def test_parse_files_drops_parentheses_and_acceptance():
    assert mod.parse_files(SLIP) == ["tools/overlap.py", "tests/test_overlap.py", ".agents/roles/orchestrator.md"]


def test_parse_files_touched_line_and_unsafe_paths():
    text = "Goal: x\n**Files touched:** `a/b.py`, /etc/passwd, ../x.py, docs/\nmore"
    assert mod.parse_files(text) == ["a/b.py", "docs/"]


def test_empty_slip_has_no_files():
    assert mod.parse_files("") == []
    assert mod.parse_files("no file line here") == []


def test_overlap_equal_prefix_and_disjoint():
    assert mod.overlaps("tools/a.py", "tools/a.py")
    assert mod.overlaps("tools/", "tools/a.py")
    assert mod.overlaps("tools/a.py", "tools")
    assert not mod.overlaps("tools/a.py", "tools/ab.py")
    assert not mod.overlaps("tools/a.py", "tests/a.py")


def test_collect_and_find_overlaps_skips_own_issue_and_non_agent_prs():
    me = {"login": "Bankaifan"}
    prs = [
        {"number": 5, "headRefName": "agent/7-x", "author": me, "files": [{"path": "tools/status.py"}]},
        {"number": 6, "headRefName": "agent/150-own", "author": me, "files": [{"path": "tools/overlap.py"}]},
        {"number": 7, "headRefName": "feature/y", "author": me, "files": [{"path": "tools/overlap.py"}]},
    ]
    issues = [
        {"number": 150, "author": me, "body": "Files: tools/overlap.py", "comments": []},
        {"number": 9, "author": me, "body": "x",
         "comments": [{"author": me, "body": "Files: docs/design/, tools/z.py. Acceptance: y"}]},
    ]
    others = mod.collect(prs, issues, own_issue=150)
    assert mod.find_overlaps(["tools/overlap.py"], others) == []
    got = mod.find_overlaps(["tools/status.py", "docs/design/0003.md"], others)
    assert got == ["tools/status.py overlaps PR #5", "docs/design/0003.md overlaps slip #9"]


def test_collect_ignores_untrusted_authors_and_forks():
    evil, me = {"login": "evil"}, {"login": "Bankaifan"}
    prs = [
        {"number": 1, "headRefName": "agent/7-x", "author": evil, "files": [{"path": "a/b.py"}]},
        {"number": 2, "headRefName": "agent/150-x", "author": evil, "files": [{"path": "a/b.py"}]},
        {"number": 3, "headRefName": "agent/8-x", "author": me, "isCrossRepository": True, "files": [{"path": "a/b.py"}]},
        {"number": 4, "headRefName": "agent/9-x", "files": [{"path": "a/b.py"}]},
    ]
    issues = [
        {"number": 10, "author": evil, "body": "Files: a/b.py", "comments": []},
        {"number": 11, "author": me, "body": "x", "comments": [{"author": evil, "body": "Files: a/b.py"}]},
    ]
    others = mod.collect(prs, issues, own_issue=150)
    assert mod.find_overlaps(["a/b.py"], others) == []


def test_overlap_on_non_first_path_and_app_authors():
    bot = {"login": "app/bankaifan-agent-author"}
    prs = [{"number": 5, "headRefName": "agent/7-x", "author": bot,
            "files": [{"path": "a.py"}, {"path": "tools/status.py"}]}]
    issues = [{"number": 9, "author": bot, "comments": [],
               "body": "Files: b.py, docs/x.md, c.py"}]
    others = mod.collect(prs, issues)
    assert mod.find_overlaps(["z.py", "tools/status.py", "c.py"], others) == [
        "tools/status.py overlaps PR #5", "c.py overlaps slip #9"]


def test_pr_waiting_for_owner_and_its_slip_do_not_defer():
    me = {"login": "Bankaifan"}

    def lab(*n):
        return [{"name": x} for x in n]

    prs = [
        {"number": 500, "headRefName": "agent/400-x", "author": me, "labels": lab("risk:security", "needs-human"),
         "files": [{"path": "tools/status.py"}]},
        {"number": 501, "headRefName": "agent/401-x", "author": me, "labels": lab("risk:security"),
         "headRefOid": "abc", "files": [{"path": "tools/a.py"}],
         "reviews": [{"state": "APPROVED", "author": {"login": "app/bankaifan-agent-approver"}, "commit": {"oid": "abc"}}]},
        {"number": 502, "headRefName": "agent/402-x", "author": me, "labels": lab("risk:security"),
         "headRefOid": "new", "files": [{"path": "tools/b.py"}],
         "reviews": [{"state": "APPROVED", "author": {"login": "app/bankaifan-agent-approver"}, "commit": {"oid": "old"}}]},
        {"number": 503, "headRefName": "agent/403-x", "author": me, "labels": lab("needs-human"),
         "files": [{"path": "tools/c.py"}]},
        {"number": 504, "headRefName": "agent/404-x", "author": me, "files": [{"path": "tools/d.py"}]},
    ]
    issues = [{"number": n, "author": me, "body": f"Files: tools/{f}.py", "comments": []}
              for n, f in ((400, "status"), (401, "a"), (402, "b"), (403, "c"))]
    others = mod.collect(prs, issues)
    assert mod.find_overlaps(["tools/status.py", "tools/a.py"], others) == []
    assert mod.find_overlaps(["tools/b.py", "tools/c.py", "tools/d.py"], others) == [
        "tools/b.py overlaps PR #502", "tools/c.py overlaps PR #503", "tools/d.py overlaps PR #504",
        "tools/b.py overlaps slip #402", "tools/c.py overlaps slip #403"]


def test_main_exit_codes(monkeypatch, capsys):
    data = {"pr": [{"number": 5, "headRefName": "agent/7-x", "author": {"login": "Bankaifan"},
                    "files": [{"path": "tools/status.py"}]}], "issue": []}
    monkeypatch.setattr(mod, "gh_json", lambda *a: data[a[0]])
    assert mod.main(["--files", "tools/status.py"]) == 1
    assert "PR #5" in capsys.readouterr().out
    assert mod.main(["--files", "tools/other.py"]) == 0
    assert mod.main(["--files", "/etc/passwd"]) == 2


def test_main_fails_closed_when_gh_fails(monkeypatch):
    def boom(*a):
        raise subprocess.CalledProcessError(1, "gh")
    monkeypatch.setattr(mod, "gh_json", boom)
    assert mod.main(["--files", "tools/a.py"]) == 2
