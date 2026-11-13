"""Issue #468: changelog fragments get versions after the merge (tools/release_fragments.py)."""
import pytest
import release_fragments as rf

CL = "# Changelog\n\n## [Unreleased]\n- pending\n\n## [1.4] - 2026-01-01\n- old\n"


def repo(tmp_path, fragments, version="1.4\n", changelog=CL):
    (tmp_path / "VERSION").write_text(version)
    (tmp_path / "CHANGELOG.md").write_text(changelog)
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "changelog.d" / "README.md").write_text("how to\n")
    for name, text in fragments.items():
        (tmp_path / "changelog.d" / name).write_text(text)
    return tmp_path


@pytest.mark.parametrize("version, step, want", [("1.5", "y", "1.6"), ("1.5", "x", "2.0"), ("2.0", "y", "2.1"), ("1.9", "y", "1.10")])
def test_next_version(version, step, want):
    assert rf.next_version(version, step) == want


def test_parse_fragment_default_step_and_bullets():
    assert rf.parse_fragment("1.md", "one\n- two\n\n") == ("y", ["- one", "- two"])
    assert rf.parse_fragment("1.md", "a\nstep: x\n") == ("x", ["- a"])


@pytest.mark.parametrize("text", ["", "step: x\n", "a\nstep: z\n", "a\nstep: x\nstep: y\n"])
def test_parse_fragment_refuses(text):
    with pytest.raises(rf.Refused):
        rf.parse_fragment("1.md", text)


def test_two_fragments_two_versions_two_sections(tmp_path):
    root = repo(tmp_path, {"11.md": "second\nstep: x\n", "9.md": "first\n"})
    assert rf.release(root, "2026-11-12") == [("1.5", "9.md"), ("2.0", "11.md")]
    assert (root / "VERSION").read_text() == "2.0\n"
    text = (root / "CHANGELOG.md").read_text()
    assert text.index("## [Unreleased]") < text.index("## [2.0] - 2026-11-12") < text.index("## [1.5] - 2026-11-12") < text.index("## [1.4]")
    assert "- first\n" in text and "- second\n" in text and "- pending\n" in text
    assert sorted(p.name for p in (root / "changelog.d").iterdir()) == ["README.md"]


def test_no_fragments_changes_nothing(tmp_path):
    root = repo(tmp_path, {})
    assert rf.release(root, "2026-11-12") == []
    assert (root / "VERSION").read_text() == "1.4\n" and (root / "CHANGELOG.md").read_text() == CL


def test_bad_fragment_writes_nothing(tmp_path):
    root = repo(tmp_path, {"1.md": "ok\n", "2.md": "step: x\n"})
    with pytest.raises(rf.Refused):
        rf.release(root, "2026-11-12")
    assert (root / "VERSION").read_text() == "1.4\n" and (root / "CHANGELOG.md").read_text() == CL
    assert (root / "changelog.d" / "1.md").exists()


def test_existing_heading_is_refused(tmp_path):
    root = repo(tmp_path, {"1.md": "ok\n"}, changelog=CL.replace("[1.4]", "[1.5]"))
    with pytest.raises(rf.Refused):
        rf.release(root, "2026-11-12")


def test_bad_version_is_refused(tmp_path):
    with pytest.raises(rf.Refused):
        rf.release(repo(tmp_path, {"1.md": "ok\n"}, version="v1\n"), "2026-11-12")


def test_main_cli(tmp_path, capsys):
    root = repo(tmp_path, {"3.md": "x\n"})
    assert rf.main([str(root)]) == 0
    assert "3.md -> 1.5" in capsys.readouterr().out
    assert rf.main([str(root)]) == 0
    assert "no fragments" in capsys.readouterr().out
