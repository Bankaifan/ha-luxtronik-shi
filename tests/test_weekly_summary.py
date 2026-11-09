import importlib.util
import pathlib

_path = pathlib.Path(__file__).parent.parent / "tools" / "weekly_summary.py"
_spec = importlib.util.spec_from_file_location("weekly_summary", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_build_body_lists_rows_and_none():
    body = mod.build_body([{"number": 5, "title": "Fix x"}], [], [], [{"number": 9, "title": "Idea"}], "2026-11-09")
    assert "- #5 Fix x" in body
    assert "- #9 Idea" in body
    assert body.count("- none") == 2
    assert "Updated 2026-11-09." in body
