import json

import agent_guard
import exec_log as e

TOKEN = "ghp_" + "a" * 24


def test_agent_guard_reexports_the_same_objects():
    for name in ("tail_text", "_records", "denied_calls", "count_denials", "read_exec", "_SECRET",
                 "TAIL_LINES", "TAIL_CHARS", "MAX_DENIALS"):
        assert getattr(agent_guard, name) is getattr(e, name)


def test_tail_text_caps_lines_masks_secrets_and_neutralizes_fences():
    text = "\n".join(f"line {i}" for i in range(40)) + f"\n```\n{TOKEN}"
    out = e.tail_text(text, lines=3)
    assert out.count("\n") == 2
    assert TOKEN not in out and "***" in out and "```" not in out
    assert len(e.tail_text("x" * 5000)) == e.TAIL_CHARS


def test_records_reads_array_json_lines_and_skips_garbage():
    assert e._records('[{"a": 1}, 2, {"b": 3}]') == [{"a": 1}, {"b": 3}]
    assert e._records('{"a": 1}\nnot json\n{"b": 2}') == [{"a": 1}, {"b": 2}]
    assert e._records("") == []


def _denial(tool, **inp):
    return {"tool_name": tool, "tool_input": inp}


def test_denied_calls_lists_masks_and_limits():
    text = json.dumps([{"permission_denials": [_denial("Bash", command=f"echo {TOKEN}"),
                                               _denial("Read", file_path="/x"), "junk",
                                               {"tool_name": "Grep", "tool_input": "bad"}]}])
    assert e.denied_calls(text) == ["Bash: echo ***", "Read: /x", "Grep: "]
    many = json.dumps([{"permission_denials": [_denial("Bash", command=str(i)) for i in range(12)]}])
    out = e.denied_calls(many)
    assert len(out) == e.MAX_DENIALS + 1 and out[-1] == "... and 2 more"


def test_count_denials_counts_all_dicts():
    text = json.dumps([{"permission_denials": [_denial("Bash", command="a"), "junk"]},
                       {"permission_denials": [_denial("Read", file_path="b")]}, {"type": "result"}])
    assert e.count_denials(text) == 2
    assert e.count_denials("") == 0


def test_read_exec_returns_text_or_empty(tmp_path):
    p = tmp_path / "exec.json"
    p.write_text("hello", encoding="utf-8")
    assert e.read_exec(str(p)) == "hello"
    assert e.read_exec(str(tmp_path / "missing")) == ""
    assert e.read_exec(None) == ""
