import json

import rename_task_ids as rt


def test_plain_title_gets_the_id_and_keeps_its_summary():
    assert rt.renamed("short task IDs in issue names", "NAMES") == "NAMES: short task IDs in issue names"


def test_other_id_is_replaced_and_same_id_stays():
    assert rt.renamed("R10-ROSTER-QUEUE: roster queue residue", "ROSTER") == "ROSTER: roster queue residue"
    assert rt.renamed("NAMES: already named", "NAMES") is None


def test_guard_sync_and_design_titles_are_never_renamed():
    for title in ("Overdue scheduled run: liveness", "Denied command in run 1: x", "Failing workflow: ci",
                  "Unstarted run: x", "Template sync " + "a" * 40, "Design 0015: study"):
        assert rt.renamed(title, "OPS") is None


def test_empty_summary_is_not_renamed():
    assert rt.renamed("NAMES: ", "NAMES") is None


def test_dry_run_prints_the_plan_and_calls_no_edit(tmp_path, monkeypatch, capsys):
    calls = []

    def fake_gh(*args):
        calls.append(args)
        return json.dumps({"title": "Fix x"}) if args[:2] == ("issue", "view") else ""

    monkeypatch.setattr(rt, "gh", fake_gh)
    m = tmp_path / "map.json"
    m.write_text(json.dumps({"501": "NAMES"}))
    assert rt.main([str(m)]) == 0
    assert "#501: Fix x -> NAMES: Fix x" in capsys.readouterr().out
    assert all(c[:2] == ("issue", "view") for c in calls)
    assert rt.main([str(m), "--apply"]) == 0
    assert ("issue", "edit", "501", "--title", "NAMES: Fix x") in calls


def test_bad_map_is_refused_before_any_gh_call(tmp_path, monkeypatch):
    monkeypatch.setattr(rt, "gh", lambda *a: (_ for _ in ()).throw(AssertionError("gh called")))
    m = tmp_path / "map.json"
    for bad in ('{"x": "NAMES"}', '{"5": "lower"}', '{"5": "FOUR-WORD-ID-NOPE-X"}', "[]"):
        m.write_text(bad)
        assert rt.main([str(m)]) == 2
    assert rt.main([]) == 2
