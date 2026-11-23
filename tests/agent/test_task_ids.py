import task_ids


def test_task_id_forms():
    for title, tid in (("NAMES: short summary", "NAMES"), ("R10-ROSTER-QUEUE: roster queue residue", "R10-ROSTER-QUEUE"),
                       ("SYNC-APPLY: apply", "SYNC-APPLY"), ("SYNC-1: step one", "SYNC-1"), ("SYNC: parent", "SYNC")):
        assert task_ids.task_id_of(title) == tid


def test_titles_without_task_id():
    for title in ("Fix x", "NAMES:short", "A-B-C-D: four words", "lower: x", "Overdue scheduled run: x",
                  "Failing workflow: x", "Denied command in run: x", "Design 0015: x", "Template sync abc", "", None):
        assert task_ids.task_id_of(title) is None


def test_versioned_names_and_commit_subjects():
    assert task_ids.task_id_of("V1-HPO-FLOW-NOW: summary") == "V1-HPO-FLOW-NOW"
    assert task_ids.task_id_of("V1-A-B-C-D: five words") is None
    good = ["V1.101-HPO-FLOW: shorten summary template", "V0.12-HPO-FLOW: x"]
    assert task_ids.commit_errors("V1-HPO-FLOW: summary", good) == []
    bad = ["fix typo", "V1-HPO-FLOW: no version", "V1.101-OTHER: wrong name", "V1.101-HPO-FLOW:"]
    assert len(task_ids.commit_errors("V1-HPO-FLOW: summary", bad)) == 5  # four subjects and one repair hint
    assert task_ids.commit_errors("NAMES: old form", bad) == [] and task_ids.commit_errors("Release 1.102", bad) == []


def test_a_merge_of_main_and_an_older_version_are_no_subject_errors():
    title = "V0-NEON-OFF: glow off"
    merges = ["Merge branch 'main' into agent/341-neon-off", "Merge remote-tracking branch 'origin/main' into agent/341-neon-off",
              "Merge branch 'main' of https://github.com/o/r into agent/341-neon-off"]
    assert task_ids.commit_errors(title, ["V0.14-NEON-OFF: before the release", "V0.15-NEON-OFF: after it", *merges]) == []
    for other in ("Merge branch 'agent/1-x' into agent/341-neon-off", "Merge pull request #3 from o/b",
                  "Merge branch 'main' into agent/341-neon-off and more"):
        assert len(task_ids.commit_errors(title, [other])) == 2, other
    assert task_ids.name_of(title) == "NEON-OFF" and task_ids.name_of("NAMES: old form") is None
