import json
import subprocess

import no_build
import prefilter


def note(tmp_path, text):
    out = tmp_path / ".agent-out"
    out.mkdir(exist_ok=True)
    (out / "nothing-to-build.md").write_text(text)
    return str(out / "nothing-to-build.md")


class Gh:
    """Fake gh: `merged` is what the merged-PR search returns; comments posted are read back."""

    def __init__(self, merged=(), fail=()):
        self.merged, self.fail, self.calls, self.comments = list(merged), fail, [], []

    def __call__(self, *args):
        if args[:2] in self.fail:
            raise subprocess.CalledProcessError(1, "gh")
        if args[:2] == ("pr", "list"):
            return json.dumps(self.merged)
        if args[:2] == ("issue", "comment"):
            self.comments.append({"body": args[args.index("--body") + 1]})
        if args[:2] == ("issue", "view"):
            return json.dumps({"comments": self.comments})
        self.calls.append(args)
        return ""


MERGED = {"body": "Step 1.\nRefs #308", "headRefName": "agent/themes-1", "isCrossRepository": False,
          "mergedAt": "2026-11-23T13:49:32Z"}


def test_reason_is_short_plain_ascii_from_a_regular_file_in_agent_out(tmp_path):
    ok = note(tmp_path, "The design note merged with PR 312.\nNothing is left for this slip.\n")
    assert no_build.reason(ok, tmp_path) == "The design note merged with PR 312. Nothing is left for this slip."
    assert no_build.reason(note(tmp_path, "ping @owner <!-- x --> ```"), tmp_path) == "ping owner  x  '''"
    assert "Files:" not in no_build.reason(note(tmp_path, "Done. Files: a.py"), tmp_path)  # never read as a slip
    for bad in ("", "   \n", "x" * 401, "a\nb\nc\nd", "café", "token ghp_" + "a" * 30):
        assert no_build.reason(note(tmp_path, bad), tmp_path) is None, bad
    assert no_build.reason(str(tmp_path / ".agent-out" / "missing.md"), tmp_path) is None
    outside = tmp_path / "elsewhere.md"
    outside.write_text("fine")
    assert no_build.reason(str(outside), tmp_path) is None
    link = tmp_path / ".agent-out" / "link.md"
    link.symlink_to(outside)
    assert no_build.reason(str(link), tmp_path) is None


def test_settle_comments_with_the_marker_and_drops_agent_dev(tmp_path, monkeypatch):
    monkeypatch.setenv("RUN_URL", "https://example.invalid/run/1")
    run = Gh()
    assert no_build.settle("308", note(tmp_path, "The slip is the design note; it merged."), run, tmp_path)
    assert run.comments[0]["body"] == (f"{no_build.MARK}\nNothing to build in this run: The slip is the design note; "
                                       "it merged.\nRun: https://example.invalid/run/1")
    assert [c[:2] for c in run.calls] == [("issue", "comment"), ("issue", "edit")]
    assert run.calls[-1] == ("issue", "edit", "308", "--remove-label", "agent:dev")


def test_complete_closes_only_when_a_merged_agent_pr_names_the_issue(tmp_path):
    path = note(tmp_path, "complete: every step of the issue is on main.")
    run = Gh(merged=[MERGED])
    assert no_build.settle("308", path, run, tmp_path)
    assert run.calls[-1] == ("issue", "close", "308", "--reason", "completed")
    for merged in ([], [{**MERGED, "body": "mentions #308 only"}], [{**MERGED, "headRefName": "feature/x"}],
                   [{**MERGED, "isCrossRepository": True}]):
        run = Gh(merged=merged)
        assert no_build.settle("308", path, run, tmp_path)
        assert not any(c[:2] == ("issue", "close") for c in run.calls), merged
    run = Gh(merged=[MERGED])
    assert no_build.settle("308", note(tmp_path, "The slip is done; steps 3 to 8 are left."), run, tmp_path)
    assert not any(c[:2] == ("issue", "close") for c in run.calls)  # no `complete:`: the issue stays open


def test_no_valid_note_or_a_failed_call_leaves_the_guard_in_charge(tmp_path, capsys):
    assert not no_build.settle("308", str(tmp_path / ".agent-out" / "nothing-to-build.md"), Gh(), tmp_path)
    path = note(tmp_path, "nothing to do")
    assert not no_build.settle("308", path, Gh(fail=(("issue", "comment"),)), tmp_path)
    assert no_build.main(["no_build.py", "settle", "abc", path]) == 2


def test_the_marker_counts_like_a_landed_step_until_a_newer_slip_exists():
    authors = frozenset({"bankaifan-agent-author[bot]", "Bankaifan"})
    slip = {"body": "Task slip\nFiles: docs/x.md", "author": {"login": "Bankaifan"}, "createdAt": "2026-11-22T10:11:44Z"}
    mark = {"body": f"{prefilter.NOTHING_MARK}\nNothing to build in this run: done.",
            "author": {"login": "bankaifan-agent-author[bot]"}, "createdAt": "2026-11-23T16:25:00Z"}
    issue = {"body": "themes", "author": {"login": "Bankaifan"}, "createdAt": "2026-11-22T09:00:00Z", "comments": [slip, mark]}
    assert prefilter.nothing_to_build(issue, authors)
    assert prefilter.step_landed(308, issue, authors, lambda *a: "[]")  # no merged PR needed
    stranger = {**mark, "author": {"login": "someone"}}
    assert not prefilter.nothing_to_build({**issue, "comments": [slip, stranger]}, authors)
    newer = {**slip, "createdAt": "2026-11-23T17:00:00Z"}
    assert not prefilter.nothing_to_build({**issue, "comments": [slip, mark, newer]}, authors)
    assert not prefilter.step_landed(308, {**issue, "comments": [slip, mark, newer]}, authors, lambda *a: "[]")
