import task_ids


def test_task_id_forms():
    for title, tid in (("NAMES: short summary", "NAMES"), ("R10-ROSTER-QUEUE: roster queue residue", "R10-ROSTER-QUEUE"),
                       ("SYNC-APPLY: apply", "SYNC-APPLY"), ("SYNC-1: step one", "SYNC-1"), ("SYNC: parent", "SYNC")):
        assert task_ids.task_id_of(title) == tid


def test_titles_without_task_id():
    for title in ("Fix x", "NAMES:short", "A-B-C-D: four words", "lower: x", "Overdue scheduled run: x",
                  "Failing workflow: x", "Denied command in run: x", "Design 0015: x", "Template sync abc", "", None):
        assert task_ids.task_id_of(title) is None
