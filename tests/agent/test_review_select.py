"""The specialist reviewers are picked by script from the added lines of the staged diff (decision 0021)."""
import pytest
import review_select as rs

SFH, PTA, TDA = "silent-failure-hunter", "pr-test-analyzer", "type-design-analyzer"
EVERYTHING = ("def load(path):", "    if not path:", "    try:", "    except OSError:", "class Config:")


def diff(path, *added, removed=()):
    lines = [f"diff --git a/{path} b/{path}", f"--- a/{path}", f"+++ b/{path}", "@@ -1,3 +1,9 @@", " unchanged = 1"]
    return "\n".join([*lines, *(f"-{r}" for r in removed), *(f"+{a}" for a in added)]) + "\n"


def test_names_are_the_three_specialists_in_a_fixed_order():
    assert rs.SPECIALISTS == (SFH, PTA, TDA)
    assert rs.select(diff("tools/x.py", *reversed(EVERYTHING))) == [SFH, PTA, TDA]


@pytest.mark.parametrize("path, line", [
    ("tools/x.py", "    except ValueError:"), ("tools/x.py", "    run(cmd, check=False)"),
    ("tools/x.py", "    with suppress(OSError):"), ("tools/ci/x.sh", "gh pr edit 5 || true"),
    ("tools/ci/x.sh", "rm x 2>/dev/null"), ("tools/ci/x.sh", "set +e"), ("src/x.js", "} catch (e) {"),
    ("src/x.js", "p.catch(() => null)"), (".github/workflows/x.yml", "        continue-on-error: true"),
    (".github/workflows/x.yml", "        if: always()"), (".github/workflows/x.yml", "          gh label create x || echo no"),
])
def test_error_handling_picks_the_silent_failure_hunter(path, line):
    assert SFH in rs.select(diff(path, line))


@pytest.mark.parametrize("path, line", [
    ("tools/x.py", "def helper(a):"), ("tools/x.py", "    elif a > 1:"), ("tools/x.py", "    for item in items:"),
    ("tools/x.py", "    while pending:"), ("tools/ci/x.sh", 'if [ -f "$f" ]; then'), ("tools/ci/x.sh", 'case "$v" in'),
    ("src/x.ts", "function parse(s) {"), ("src/x.ts", "const f = (a) => a + 1"), ("src/x.ts", "} else if (a) {"),
    ("src/x.go", "func Parse(s string) int {"), ("src/x.rs", "fn parse(s: &str) -> u8 {"), ("src/x.js", "switch (kind) {"),
])
def test_new_logic_in_code_picks_the_test_analyzer(path, line):
    assert rs.select(diff(path, line)) == [PTA]


@pytest.mark.parametrize("path, line", [
    ("tools/x.py", "class Round:"), ("tools/x.py", "@dataclass(frozen=True)"), ("tools/x.py", "class Row(TypedDict):"),
    ("tools/x.py", 'Point = NamedTuple("Point", [("x", int)])'), ("tools/x.py", "class Kind(Enum):"),
    ("src/x.ts", "interface Verdict {"), ("src/x.ts", "type Verdict = {"), ("src/x.go", "type Round struct {"),
    ("src/x.rs", "enum Kind {"), ("src/X.java", "record Point(int x, int y) {}"),
])
def test_a_new_data_structure_picks_the_type_analyzer(path, line):
    assert rs.select(diff(path, line)) == [TDA]


@pytest.mark.parametrize("path", [
    "README.md", "docs/decisions/0021-review-panel.md", "docs/example.py", "changelog.d/12.md", "notes.txt", "guide.rst",
])
def test_docs_and_text_pick_nobody(path):
    assert rs.select(diff(path, *EVERYTHING)) == []


@pytest.mark.parametrize("path", [
    "tests/agent/test_x.py", "tests/helpers.py", "test/x.js", "pkg/test_x.py", "pkg/x_test.go", "src/x.test.ts", "src/x.spec.ts",
])
def test_a_test_only_change_needs_no_test_or_type_analyzer(path):
    picked = rs.select(diff(path, "def test_it():", "    for i in range(3):", "class FakePr:", "@dataclass"))
    assert picked == []


def test_a_file_that_only_looks_like_a_test_is_code():
    for path in ("tools/latest/x.py", "tools/contest.py", "tools/attest_x.py"):
        assert rs.select(diff(path, "def f():", "class X:")) == [PTA, TDA]


def test_error_patterns_outside_code_and_workflows_pick_nobody():
    for path in ("config.yml", "data.json", "Makefile", "docs/budgets.json"):
        assert rs.select(diff(path, "x || true", "continue-on-error: true", "fallback: 1")) == []


def test_only_added_lines_count():
    removed = rs.select(diff("tools/x.py", "x = 1", removed=EVERYTHING))
    context = rs.select("diff --git a/t.py b/t.py\n--- a/t.py\n+++ b/t.py\n@@ -1,3 +1,3 @@\n def f():\n     try:\n class X:\n+x = 2\n")
    deleted = rs.select("diff --git a/t.py b/t.py\n--- a/t.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-def f():\n-class X:\n")
    assert removed == context == deleted == []
    assert rs.select("") == []


def test_each_file_is_judged_by_its_own_path():
    both = diff("README.md", *EVERYTHING) + diff("tests/agent/test_x.py", "def test_x():", "class Fake:") + diff("tools/x.py", "x = 1")
    assert rs.select(both) == []
    assert rs.select(both + diff("tools/y.py", "    if x:")) == [PTA]


def test_delta_wins_over_the_full_diff(tmp_path, capsys):
    (tmp_path / "pr.diff").write_text(diff("tools/x.py", *EVERYTHING), encoding="utf-8")
    assert rs.main(["review_select.py", str(tmp_path)]) == 0
    assert (tmp_path / "reviewers.txt").read_text(encoding="utf-8").split("\n") == [SFH, PTA, TDA, ""]
    out = capsys.readouterr().out
    assert all(name in out for name in (SFH, PTA, TDA))
    (tmp_path / "delta.diff").write_text(diff("tools/x.py", "class Round:"), encoding="utf-8")
    assert rs.main(["review_select.py", str(tmp_path)]) == 0
    assert (tmp_path / "reviewers.txt").read_text(encoding="utf-8") == TDA + "\n"
    (tmp_path / "delta.diff").write_text(diff("README.md", "text"), encoding="utf-8")
    assert rs.main(["review_select.py", str(tmp_path)]) == 0
    assert (tmp_path / "reviewers.txt").read_text(encoding="utf-8") == ""  # an empty selection is a result


def test_default_directory_is_dot_review(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".review").mkdir()
    (tmp_path / ".review" / "pr.diff").write_text(diff("tools/x.py", "def f():"), encoding="utf-8")
    assert rs.main(["review_select.py"]) == 0
    assert (tmp_path / ".review" / "reviewers.txt").read_text(encoding="utf-8") == PTA + "\n"


def test_a_missing_diff_is_an_error_and_writes_no_selection(tmp_path, capsys):
    assert rs.main(["review_select.py", str(tmp_path)]) == 1
    assert not (tmp_path / "reviewers.txt").exists()
    assert "pr.diff" in capsys.readouterr().err
    assert rs.main(["review_select.py", str(tmp_path / "nowhere")]) == 1
    (tmp_path / "pr.diff").mkdir()  # unreadable
    assert rs.main(["review_select.py", str(tmp_path)]) == 1
    assert not (tmp_path / "reviewers.txt").exists()


def test_a_git_quoted_path_header_is_read():
    quoted = ('diff --git "a/tools/t\\303\\244st.py" "b/tools/t\\303\\244st.py"\n--- "a/tools/t\\303\\244st.py"\n'
              '+++ "b/tools/t\\303\\244st.py"\n@@ -1 +1,3 @@\n x = 1\n+def f():\n+class X:\n')
    assert rs.select(quoted) == [PTA, TDA]
    assert rs.select(quoted.replace("tools/t", "docs/t")) == []
