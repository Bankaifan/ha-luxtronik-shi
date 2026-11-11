import importlib.util
import json
import pathlib
import subprocess

import pytest

from tests import test_status as ts

_path = pathlib.Path(__file__).parent.parent / "tools" / "design_parents.py"
_spec = importlib.util.spec_from_file_location("design_parents", _path)
dp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dp)

OWNER = "Bankaifan"
BOT = "app/author"
DESIGN = "docs/design/0003-merge-train.md"


def design_dir(tmp_path, number=5):
    d = tmp_path / "docs" / "design"
    d.mkdir(parents=True)
    (d / "0003-merge-train.md").write_text(f"# Merge train\n\nIssue: #{number} (design study).\n", encoding="utf-8")
    (d / "0004-no-header.md").write_text("# No header\n", encoding="utf-8")
    return d


def child(number, state="CLOSED", reason="COMPLETED", prs=(7,), author=OWNER, body=None, title=None):
    return {"number": number, "title": title or f"Split {number}", "state": state, "stateReason": reason,
            "body": body if body is not None else f"Part {number}.\n\nDesign: {DESIGN}\n",
            "author": {"login": author}, "labels": [],
            "closedByPullRequestsReferences": [{"number": n} for n in prs]}


def parent(number=5, state="OPEN", labels=("prio:1", "agent:dev", "approved")):
    return {"number": number, "title": "Design study", "state": state, "stateReason": "", "body": "",
            "author": {"login": OWNER}, "labels": [{"name": n} for n in labels], "closedByPullRequestsReferences": []}


class Gh:
    """Fake gh: answers issue list, merged PR list and the readback of comments; records every call."""

    def __init__(self, issues, merged=(7,)):
        self.issues, self.merged, self.calls, self.comments = issues, list(merged), [], []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("issue", "list"):
            return json.dumps(self.issues)
        if args[:2] == ("pr", "list"):
            return json.dumps([{"number": n} for n in self.merged])
        if args[:2] == ("issue", "comment"):
            self.comments.append(args[args.index("--body") + 1])
            return ""
        if args[:2] == ("issue", "view"):
            return json.dumps({"comments": [{"body": c} for c in self.comments]})
        return ""


def close_calls(run):
    return [c for c in run.calls if c[:2] == ("issue", "close")]


def test_parent_designs_reads_the_header_line(tmp_path):
    assert dp.parent_designs(design_dir(tmp_path)) == {5: [DESIGN]}


def test_all_children_done_closes_parent_and_drops_labels(tmp_path):
    run = Gh([parent(), child(11), child(12, prs=(8,))], merged=(7, 8))
    assert dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path)) == [
        "closed design parent #5: 2 split issues done"]
    assert ("issue", "edit", "5", "--remove-label", "prio:1", "--remove-label", "agent:dev") in run.calls
    assert close_calls(run) == [("issue", "close", "5", "--reason", "completed")]
    assert "#11, #12" in run.comments[0]
    assert ("issue", "edit", "5", "--remove-label", "approved") not in run.calls  # other labels stay


def test_one_open_child_keeps_parent_open(tmp_path):
    run = Gh([parent(), child(11), child(12, state="OPEN", reason="")])
    assert dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path)) == []
    assert close_calls(run) == [] and run.comments == []


def test_not_planned_child_keeps_parent_open(tmp_path):
    run = Gh([parent(), child(11), child(12, reason="NOT_PLANNED", prs=())])
    assert dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path)) == []
    assert close_calls(run) == []


def test_closed_without_merged_pr_keeps_parent_open(tmp_path):
    run = Gh([parent(), child(11), child(12, prs=(9,))], merged=(7,))
    assert dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path)) == []
    assert close_calls(run) == []


def test_no_split_issues_keeps_parent_open(tmp_path):
    run = Gh([parent()])
    assert dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path)) == []
    assert close_calls(run) == []


def test_stranger_child_is_ignored(tmp_path):
    stranger = child(12, state="OPEN", reason="", author="mallory")
    run = Gh([parent(), child(11), stranger])
    assert dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path)) == [
        "closed design parent #5: 1 split issues done"]


HAND = {"body": "Build it and push it.\n", "title": "Build Design 0003: merge train"}


def test_hand_written_split_issue_links_by_title(tmp_path):
    run = Gh([parent(), child(11, **HAND)])
    assert dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path)) == [
        "closed design parent #5: 1 split issues done"]
    assert close_calls(run) == [("issue", "close", "5", "--reason", "completed")]


def test_open_hand_written_split_issue_keeps_parent_open(tmp_path):
    run = Gh([parent(), child(11), child(12, state="OPEN", reason="", **HAND)])
    assert dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path)) == []
    assert close_calls(run) == []


def test_title_of_another_design_does_not_link(tmp_path):
    run = Gh([parent(), child(11, body="Build it.\n", title="Build Design 0004: other")])
    assert dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path)) == []
    assert close_calls(run) == []


def test_stranger_with_matching_title_is_ignored(tmp_path):
    stranger = child(12, state="OPEN", reason="", author="mallory", **HAND)
    run = Gh([parent(), child(11), stranger])
    assert dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path)) == [
        "closed design parent #5: 1 split issues done"]


def test_closed_parent_is_skipped(tmp_path):
    run = Gh([parent(state="CLOSED"), child(11)])
    assert dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path)) == []
    assert close_calls(run) == []


def test_truncated_issue_list_closes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(dp, "ISSUE_LIMIT", 2)
    run = Gh([parent(), child(11)])
    assert dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path)) == [
        "design parents not checked: the issue list reached 2"]
    assert close_calls(run) == []


def test_truncated_merged_list_closes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(dp, "MERGED_PR_LIMIT", 1)
    run = Gh([parent(), child(11)], merged=(7, 8))
    assert dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path)) == []
    assert close_calls(run) == []


def test_failed_close_is_reported_not_raised(tmp_path):
    class NoClose(Gh):
        def __call__(self, *args):
            if args[:2] == ("issue", "close"):
                raise subprocess.CalledProcessError(1, "gh")
            return super().__call__(*args)

    run = NoClose([parent(), child(11)])
    assert dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path)) == [
        "design parent #5 not closed: CalledProcessError"]


def test_no_design_docs_means_no_gh_calls(tmp_path):
    empty = tmp_path / "docs" / "design"
    empty.mkdir(parents=True)
    run = Gh([parent(), child(11)])
    assert dp.close_done_parents(run, OWNER, BOT, empty) == []
    assert run.calls == []


def test_status_run_reports_closed_parents(monkeypatch):
    _order, bodies = ts.wire(monkeypatch, lambda *a: ([], ts.NOW))
    monkeypatch.setattr(ts.st.design_parents, "close_done_parents",
                        lambda run, owner, bot="": ["closed design parent #5: 2 split issues done"])
    assert ts.st.run_status({"GH_REPO": "o/r"}, ts.NOW, ts.empty) == 0
    assert "- closed design parent #5: 2 split issues done" in bodies[0]


def test_orchestrator_role_no_longer_closes_parents_by_hand():
    role = (pathlib.Path(__file__).parent.parent / ".agents" / "roles" / "orchestrator.md").read_text(encoding="utf-8")
    assert "Close the source issue once" not in role
    assert "Do not close the source issue by hand" in role
    assert "tools/design_parents.py" in role


@pytest.mark.parametrize("label", ["prio:2", "agent:dev"])
def test_labels_of_parent_are_removed(tmp_path, label):
    run = Gh([parent(labels=(label,)), child(11)])
    dp.close_done_parents(run, OWNER, BOT, design_dir(tmp_path))
    assert ("issue", "edit", "5", "--remove-label", label) in run.calls
