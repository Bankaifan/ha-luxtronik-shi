import datetime
import importlib.util
import pathlib

_path = pathlib.Path(__file__).parent.parent / "tools" / "scout_titles.py"
_spec = importlib.util.spec_from_file_location("scout_titles", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

TODAY = datetime.date(2026, 11, 10)


def fake_gh(calls):
    """Answer each gh_json call by its arguments; record the cutoff used for closed issues."""
    def run(*args):
        calls.append(args)
        if args[:2] == ("issue", "list") and "open" in args:
            return [{"number": 1, "title": "Open one"}, {"number": 2, "title": "Shared"}]
        if args[:2] == ("issue", "list") and "--search" in args:
            return [{"number": 3, "title": "Closed recent"}, {"number": 2, "title": "Shared"}]
        if args[:2] == ("issue", "list") and "idea" in args:
            return [{"number": 4, "title": "Old idea"}]
        if args[:2] == ("pr", "list"):
            return [{"number": 5, "title": "  Open   PR\nwith newline  "}]
        raise AssertionError(args)
    return run


def test_collect_lists_titles_once_each_with_kind(monkeypatch):
    calls = []
    monkeypatch.setattr(mod, "gh_json", fake_gh(calls))
    lines = mod.collect(TODAY, root=pathlib.Path("/nonexistent"))
    assert lines == [
        "- #1 Open one (open issue)",
        "- #2 Shared (open issue)",
        "- #3 Closed recent (closed issue)",
        "- #4 Old idea (closed idea)",
        "- #5 Open PR with newline (open PR)",
    ]


def test_closed_cutoff_is_ninety_days_back(monkeypatch):
    calls = []
    monkeypatch.setattr(mod, "gh_json", fake_gh(calls))
    mod.collect(TODAY, root=pathlib.Path("/nonexistent"))
    assert ("issue", "list", "--state", "closed", "--search", "closed:>=2026-08-12", "--limit", "300",
            "--json", "number,title") in calls


def test_design_titles_skip_readme_and_take_first_heading(tmp_path):
    design = tmp_path / "docs" / "design"
    design.mkdir(parents=True)
    (design / "README.md").write_text("# Design studies\n", encoding="utf-8")
    (design / "0002-x.md").write_text("intro\n# 0002 Unblocker role\n# later\n", encoding="utf-8")
    (design / "0001-y.md").write_text("no heading here\n", encoding="utf-8")
    assert mod.design_titles(tmp_path) == ["0002 Unblocker role"]


def test_clean_collapses_whitespace_and_truncates():
    assert mod.clean("a \t b\n c") == "a b c"
    assert len(mod.clean("x" * 500)) == mod.MAX_TITLE


def test_main_writes_multiline_output(tmp_path, monkeypatch):
    out = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(mod, "collect", lambda today: ["- #1 A (open issue)", "- #2 B (open PR)"])
    assert mod.main() == 0
    text = out.read_text(encoding="utf-8")
    head, _, rest = text.partition("\n")
    assert head.startswith("titles<<EOF-")
    delim = head[len("titles<<"):]
    assert rest == "- #1 A (open issue)\n- #2 B (open PR)\n" + delim + "\n"
