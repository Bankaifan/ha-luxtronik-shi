import json

import design_split
import pytest

DESIGN = "docs/design/0016-example.md"

GOOD = """# Example

## 7. Rollback

none

## 8. Split into PR-sized implementation issues

### Step 1: First step
Files: `tools/a.py`, `tests/test_a.py`
Acceptance: a works

### Step 2: Second step
Files: `tools/b.py`
Acceptance: b works

### Step 3: Third step
Files: `tools/c.py`
Acceptance: c works
Depends on: 1, 2

## 9. Owner decisions

none
"""


class FakeGh:
    """Records calls; keeps the created issues so a rerun sees them."""

    def __init__(self, source_labels=("prio:2", "agent:dev", "needs-human"), source_body="Source text\n"):
        self.issues = []
        self.calls = []
        self.source_labels = source_labels
        self.source_body = source_body

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("issue", "view"):
            return json.dumps({"labels": [{"name": n} for n in self.source_labels], "body": self.source_body})
        if args[:2] == ("issue", "edit") and "--body" in args:
            self.source_body = args[args.index("--body") + 1]
            return ""
        if args[:2] == ("issue", "list"):
            return json.dumps(self.issues)
        if args[:2] == ("issue", "create"):
            title, body = args[args.index("--title") + 1], args[args.index("--body") + 1]
            number = 100 + len(self.issues)
            self.issues.append({"number": number, "title": title, "body": body, "labels": [
                args[i + 1] for i, a in enumerate(args) if a == "--label"]})
            return f"https://github.com/o/r/issues/{number}\n"
        return ""

    def creates(self):
        return [c for c in self.calls if c[:2] == ("issue", "create")]


def test_three_steps_one_dependency_create_three_issues():
    gh = FakeGh()
    numbers = design_split.split(DESIGN, GOOD, 417, gh)
    assert numbers == {1: 100, 2: 101, 3: 102}
    first, second, third = gh.issues
    assert first["body"].splitlines()[0] == f"Design: {DESIGN}"
    assert "Depends on" not in first["body"] and "Depends on" not in second["body"]
    assert "Files: `tools/a.py`, `tests/test_a.py`" in first["body"] and "Acceptance: a works" in first["body"]
    assert third["body"].splitlines()[:2] == [f"Design: {DESIGN}", "Depends on: #100, #101"]
    assert [i["title"] for i in gh.issues] == ["First step", "Second step", "Third step"]
    assert all(i["labels"] == ["prio:2"] for i in gh.issues)


def test_source_issue_loses_agent_dev_and_needs_human():
    gh = FakeGh()
    design_split.split(DESIGN, GOOD, 417, gh)
    assert ("issue", "edit", "417", "--remove-label", "agent:dev", "--remove-label", "needs-human") in gh.calls


def test_source_body_gets_depends_on_with_the_final_steps():
    gh = FakeGh()
    design_split.split(DESIGN, GOOD, 417, gh)
    # step 3 depends on 1 and 2, so step 3 (#102) is the only final step
    assert gh.source_body == "Source text\nDepends on: #102"


def test_several_final_steps_are_listed_in_step_order():
    gh = FakeGh()
    design_split.split(DESIGN, GOOD.replace("Depends on: 1, 2", "Depends on: 1"), 417, gh)
    assert gh.source_body.splitlines()[-1] == "Depends on: #101, #102"


def test_existing_depends_on_line_is_replaced_and_the_rest_kept():
    gh = FakeGh(source_body="Intro\nDepends on: #5\nOutro\n")
    design_split.split(DESIGN, GOOD, 417, gh)
    assert gh.source_body == "Intro\nDepends on: #102\nOutro"


def test_rerun_leaves_the_source_body_alone():
    gh = FakeGh()
    design_split.split(DESIGN, GOOD, 417, gh)
    body = gh.source_body
    gh.calls.clear()
    design_split.split(DESIGN, GOOD, 417, gh)
    assert gh.source_body == body
    assert not [c for c in gh.calls if c[:2] == ("issue", "edit") and "--body" in c]


def test_rerun_creates_nothing():
    gh = FakeGh()
    design_split.split(DESIGN, GOOD, 417, gh)
    gh.calls.clear()
    numbers = design_split.split(DESIGN, GOOD, 417, gh)
    assert numbers == {1: 100, 2: 101, 3: 102}
    assert gh.creates() == []
    assert len(gh.issues) == 3


def test_partial_rerun_creates_only_the_missing_step_with_mapped_dependencies():
    gh = FakeGh()
    design_split.split(DESIGN, GOOD, None, gh)
    del gh.issues[2]  # step 3 was never created
    design_split.split(DESIGN, GOOD, None, gh)
    assert len(gh.issues) == 3
    assert gh.issues[2]["body"].splitlines()[1] == "Depends on: #100, #101"


def test_other_design_with_the_same_title_is_not_reused():
    gh = FakeGh()
    gh.issues.append({"number": 7, "title": "First step", "body": "Design: docs/design/0017-other.md\n", "labels": []})
    design_split.split(DESIGN, GOOD, None, gh)
    assert len(gh.creates()) == 3


def test_no_source_issue_means_no_label_and_no_edit():
    gh = FakeGh()
    design_split.split(DESIGN, GOOD, None, gh)
    assert gh.issues[0]["labels"] == []
    assert not [c for c in gh.calls if c[:2] == ("issue", "edit")]


@pytest.mark.parametrize("bad, message", [
    (GOOD.replace("## 8. Split into PR-sized implementation issues", "## 8b. Other"), "no section"),
    (GOOD.split("### Step 1")[0] + "## 9. Owner decisions\n\nnone\n", "no '### Step"),
    (GOOD.replace("Acceptance: b works\n", ""), "missing 'Acceptance:'"),
    (GOOD.replace("Files: `tools/b.py`\n", ""), "missing 'Files:'"),
    (GOOD.replace("### Step 2:", "### Step 3:"), "step numbers"),
    (GOOD.replace("Depends on: 1, 2", "Depends on: 3"), "not earlier"),
    (GOOD.replace("Depends on: 1, 2", "Depends on: #1"), "step numbers like"),
    (GOOD.replace("### Step 2: Second step", "### Step 2: First step"), "duplicate step title"),
])
def test_malformed_section_8_does_not_parse(bad, message):
    with pytest.raises(design_split.DesignError, match=message):
        design_split.parse_section8(bad)


def test_malformed_design_creates_no_issue():
    gh = FakeGh()
    with pytest.raises(design_split.DesignError):
        design_split.split(DESIGN, GOOD.replace("Acceptance: c works\n", ""), 417, gh)
    assert gh.issues == []


def _tree(tmp_path, name, text):
    d = tmp_path / "docs" / "design"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")


def test_check_fails_a_malformed_design_and_passes_a_good_one(tmp_path):
    _tree(tmp_path, "0016-example.md", GOOD)
    assert design_split.check(tmp_path) == []
    _tree(tmp_path, "0017-bad.md", GOOD.replace("Files: `tools/a.py`, `tests/test_a.py`\n", ""))
    errs = design_split.check(tmp_path)
    assert len(errs) == 1 and "0017-bad.md" in errs[0] and "missing 'Files:'" in errs[0]


def test_check_skips_legacy_table_designs(tmp_path):
    _tree(tmp_path, "0015-old.md", "## 8. Split\n\n| Step | Title |\n|---|---|\n| 1 | x |\n")
    assert design_split.check(tmp_path) == []


def test_main_check_exit_codes(tmp_path):
    _tree(tmp_path, "0016-bad.md", "## 8. Split\n\nnothing\n")
    assert design_split.main(["check", str(tmp_path)]) == 1
    assert design_split.main([]) == 2


def test_the_repo_designs_pass_the_check():
    assert design_split.main(["check"]) == 0


def test_run_splits_added_design_with_the_pr_source_issue(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_REPO", "o/r")
    _tree(tmp_path, "0016-example.md", GOOD)
    _tree(tmp_path, "0015-legacy.md", "no section")
    gh = FakeGh()
    base = gh.__call__

    def fake_gh(*args):
        if args[0] == "api":
            assert args[1] == "repos/o/r/commits/abc123/pulls"
            return json.dumps([{"body": "Design.\nRefs #417"}])
        return base(*args)

    def fake_git(*args):
        if args[0] == "diff":
            return f"{DESIGN}\ndocs/design/0015-legacy.md\ndocs/design/README.md"
        return "abc123"

    assert design_split.run("b", "a", tmp_path, fake_gh, fake_git) == 0
    assert len(gh.issues) == 3 and gh.issues[0]["labels"] == ["prio:2"]


def test_run_reports_a_malformed_design(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GH_REPO", "o/r")
    _tree(tmp_path, "0016-example.md", "## 8. Split\n\nnothing\n")
    gh = FakeGh()
    rc = design_split.run("b", "a", tmp_path, lambda *a: "[]" if a[0] == "api" else gh(*a),
                          lambda *a: DESIGN if a[0] == "diff" else "abc123")
    assert rc == 1 and gh.issues == []
    assert "no '### Step" in capsys.readouterr().err
