"""Orchestrator HANDOVER.md text from the run result (design 0017, step 5): markers, size, attribution, no write by the model."""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import handover_text as ht


def _execution(*results):
    messages = [{"type": "assistant", "message": {"content": []}}]
    messages += [{"type": "result", "subtype": "success", "result": r} for r in results]
    return json.dumps(messages)


def _run(tmp_path, text):
    src = tmp_path / "execution.json"
    src.write_text(text, encoding="utf-8")
    out = tmp_path / "HANDOVER.md"
    return ht.main(["handover_text.py", str(src), str(out)]), out


def test_block_is_written_without_the_markers(tmp_path):
    answer = f"Checked.\n{ht.BEGIN}\n# HANDOVER\nOpen: none\n{ht.END}\nConclusion: stale, rewritten."
    code, out = _run(tmp_path, _execution(answer))
    assert code == 0
    assert out.read_text(encoding="utf-8") == "# HANDOVER\nOpen: none\n"


def test_no_block_writes_nothing(tmp_path):
    code, out = _run(tmp_path, _execution("Not stale.\nConclusion: nothing to do."))
    assert code == 0 and not out.exists()


def test_the_last_result_message_is_used(tmp_path):
    code, out = _run(tmp_path, _execution(f"{ht.BEGIN}\nold\n{ht.END}", f"{ht.BEGIN}\nnew\n{ht.END}"))
    assert code == 0 and out.read_text(encoding="utf-8") == "new\n"


def test_a_single_result_object_is_accepted(tmp_path):
    single = json.dumps({"type": "result", "result": f"{ht.BEGIN}\nx\n{ht.END}"})
    code, out = _run(tmp_path, single)
    assert code == 0 and out.read_text(encoding="utf-8") == "x\n"


def test_missing_end_marker_fails_and_writes_nothing(tmp_path):
    code, out = _run(tmp_path, _execution(f"{ht.BEGIN}\n# HANDOVER\n"))
    assert code == 2 and not out.exists()


def test_more_than_sixty_lines_fails(tmp_path):
    body = "\n".join(f"line {i}" for i in range(61))
    code, out = _run(tmp_path, _execution(f"{ht.BEGIN}\n{body}\n{ht.END}"))
    assert code == 2 and not out.exists()


def test_sixty_lines_pass(tmp_path):
    body = "\n".join(f"line {i}" for i in range(60))
    code, out = _run(tmp_path, _execution(f"{ht.BEGIN}\n{body}\n{ht.END}"))
    assert code == 0 and out.read_text(encoding="utf-8").count("\n") == 60


def test_attribution_fails_and_writes_nothing(tmp_path):
    code, out = _run(tmp_path, _execution(f"{ht.BEGIN}\n# HANDOVER\nGenerated with Claude Code\n{ht.END}"))
    assert code == 2 and not out.exists()


def test_unreadable_execution_file_fails(tmp_path):
    code, out = _run(tmp_path, "not json")
    assert code == 2 and not out.exists()
