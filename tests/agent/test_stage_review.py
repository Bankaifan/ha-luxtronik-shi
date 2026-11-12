import importlib.util
import pathlib
import sys

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "ci" / "stage_review.py"
sys.path.insert(0, str(_path.parent))
_spec = importlib.util.spec_from_file_location("stage_review", _path)
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)


def block(path, add=1, delete=0, mode=""):
    head = f"diff --git a/{path} b/{path}\n{mode}--- a/{path}\n+++ b/{path}\n@@ -1,1 +1,1 @@\n"
    return head + "-old\n" * delete + "+new\n" * add


def run(tmp_path, diff, fetch=None):
    turns = sr.stage(diff, str(tmp_path), fetch)
    return turns, (tmp_path / "pr.diff").read_text(), (tmp_path / "skipped.txt").read_text()


def test_stages_workflow_and_tool_and_lists_test(tmp_path):
    diff = block(".github/workflows/a.yml") + block("tools/x.py") + block("tests/agent/test_x.py", add=3, delete=2)
    turns, staged, skipped = run(tmp_path, diff, lambda p: "content of " + p)
    assert ".github/workflows/a.yml" in staged and "tools/x.py" in staged
    assert "tests/agent/test_x.py" not in staged
    assert skipped == "tests/agent/test_x.py\tmodified\t+3/-2\n"
    assert (tmp_path / "files" / "tools" / "x.py").read_text() == "content of tools/x.py"
    assert turns == 13


def test_deleted_test_and_security_tool_test_stay(tmp_path):
    diff = (block("tests/agent/test_old.py", add=0, delete=4, mode="deleted file mode 100644\n")
            + block("tests/agent/test_risk.py") + block("tests/agent/test_other.py") + block("tools/y.py"))
    _, staged, skipped = run(tmp_path, diff)
    assert "tests/agent/test_old.py" in staged and "tests/agent/test_risk.py" in staged
    assert "tests/agent/test_other.py" not in staged and "tests/agent/test_other.py" in skipped
    assert not (tmp_path / "files" / "tests" / "agent" / "test_old.py").exists()


def test_root_test_of_security_tool_is_staged(tmp_path):
    diff = block("tests/test_guard_mark.py") + block("tests/test_agent_guard.py") + block("tests/test_other.py")
    _, staged, skipped = run(tmp_path, diff)
    assert "tests/test_guard_mark.py" in staged and "tests/test_agent_guard.py" in staged
    assert "tests/test_other.py" not in staged and "tests/test_other.py" in skipped


def test_turns_grow_and_cap():
    assert sr.turns_for(100) == 13
    assert sr.turns_for(0) == 12
    assert sr.turns_for(3000) == 14
    assert sr.turns_for(3001) == 15
    assert sr.turns_for(10**6) == 30


def test_no_relevant_file_stages_full_diff(tmp_path):
    diff = block("docs/a.md") + block("tests/agent/test_z.py")
    _, staged, skipped = run(tmp_path, diff)
    assert staged == diff and skipped == ""


def test_error_stages_full_diff(tmp_path):
    diff = block("tools/x.py")

    def boom(_path):
        raise RuntimeError("fetch failed")

    _, staged, _ = run(tmp_path, diff, boom)
    assert staged == diff


def test_unsafe_paths_stay_in_diff_but_are_not_fetched(tmp_path):
    diff = block("tools/x.py") + block("tools/../evil.py") + block("/tools/abs.py")
    seen = []
    _, staged, skipped = run(tmp_path, diff, lambda p: seen.append(p) or "x")
    assert seen == ["tools/x.py"]
    assert "evil.py" in staged and "abs.py" in staged
    assert skipped == ""


def test_quoted_non_ascii_path_under_github_is_staged(tmp_path):
    q = '"a/.github/workflows/\\303\\244.yml" "b/.github/workflows/\\303\\244.yml"'
    quoted = f"diff --git {q}\nindex 1..2 100644\n--- {q.split(' ')[0]}\n+++ {q.split(' ')[1]}\n@@ -1,1 +1,1 @@\n+new\n"
    seen = []
    _, staged, skipped = run(tmp_path, block("docs/a.md") + quoted, lambda p: seen.append(p) or "x")
    assert quoted in staged and "docs/a.md" not in staged
    assert seen == [".github/workflows/ä.yml"]
    assert skipped == "docs/a.md\tmodified\t+1/-0\n"


def test_parse_header_forms():
    from_risk = sr.risk.parse_header
    assert from_risk("diff --git a/x y b/x y\n") == ("x y", "x y")
    assert from_risk('diff --git "a/\\303\\244\\t\\"q\\"" b/plain') == ('ä\t"q"', "plain")
    assert from_risk("diff --git garbage") == ("", "")


def test_risk_classifies_quoted_workflow_path():
    q = '"a/.github/workflows/\\303\\244.yml" "b/.github/workflows/\\303\\244.yml"'
    assert sr.risk.classify(f"diff --git {q}\n--- a\n+++ b\n@@ -1 +1 @@\n+x\n") == "infra"


def test_main_prints_turns(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(block("tools/x.py")))
    monkeypatch.delenv("SHA", raising=False)
    assert sr.main(["stage_review.py", str(tmp_path)]) == 0
    assert capsys.readouterr().out == "turns=13\n"
