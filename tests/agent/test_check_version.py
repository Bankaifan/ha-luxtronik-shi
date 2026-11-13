import importlib.util
import pathlib

import pytest

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "check" / "check_version.py"
_spec = importlib.util.spec_from_file_location("check_version", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

CHANGELOG_OK = "# Changelog\n\n## [Unreleased]\n\n## [1.2.3] - 2026-01-01\n"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VERSION_FILE", raising=False)
    monkeypatch.delenv("VERSION_REGEX", raising=False)
    return tmp_path


def _version(repo, text="1.2.3\n", name="VERSION.txt"):
    (repo / name).write_text(text, encoding="utf-8")
    return name


def test_no_version_source_is_skipped(repo, capsys):
    (repo / "CHANGELOG.md").write_text(CHANGELOG_OK, encoding="utf-8")
    assert mod.main() == 0
    assert "skipped" in capsys.readouterr().out


def test_no_changelog_is_skipped(repo, capsys, monkeypatch):
    monkeypatch.setenv("VERSION_FILE", _version(repo))
    assert mod.main() == 0
    assert "skipped" in capsys.readouterr().out


def test_version_file_env_missing_exits(repo, monkeypatch):
    (repo / "CHANGELOG.md").write_text(CHANGELOG_OK, encoding="utf-8")
    monkeypatch.setenv("VERSION_FILE", "nope.txt")
    with pytest.raises(SystemExit, match="VERSION_FILE nope.txt does not exist"):
        mod.main()


def test_bad_regex_no_match_exits(repo, monkeypatch):
    (repo / "CHANGELOG.md").write_text(CHANGELOG_OK, encoding="utf-8")
    monkeypatch.setenv("VERSION_FILE", _version(repo))
    monkeypatch.setenv("VERSION_REGEX", r"version=(\d+)")
    with pytest.raises(SystemExit, match="no version found in"):
        mod.main()


def test_non_semver_version_fails(repo, capsys, monkeypatch):
    (repo / "CHANGELOG.md").write_text(CHANGELOG_OK, encoding="utf-8")
    monkeypatch.setenv("VERSION_FILE", _version(repo, "release v12\n"))
    monkeypatch.setenv("VERSION_REGEX", r"(v\d+)")
    assert mod.main() == 1
    assert "'v12' is not x.y or x.y.z" in capsys.readouterr().out


def test_missing_unreleased_section_fails(repo, capsys, monkeypatch):
    (repo / "CHANGELOG.md").write_text("## [1.2.3] - 2026-01-01\n", encoding="utf-8")
    monkeypatch.setenv("VERSION_FILE", _version(repo))
    assert mod.main() == 1
    assert "no '## [Unreleased]' section" in capsys.readouterr().out


def test_missing_version_section_fails(repo, capsys, monkeypatch):
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n\n## [1.2.2] - 2025-12-01\n", encoding="utf-8")
    monkeypatch.setenv("VERSION_FILE", _version(repo))
    assert mod.main() == 1
    assert "no '## [1.2.3]' section" in capsys.readouterr().out


def test_matching_sections_pass(repo, capsys, monkeypatch):
    (repo / "CHANGELOG.md").write_text(CHANGELOG_OK, encoding="utf-8")
    monkeypatch.setenv("VERSION_FILE", _version(repo))
    assert mod.main() == 0
    assert "check_version: ok (1.2.3)" in capsys.readouterr().out


def test_x_y_version_with_section_passes(repo, capsys):
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n\n## [1.0] - 2026-01-01\n", encoding="utf-8")
    _version(repo, "1.0\n", name="VERSION")
    assert mod.main() == 0
    assert "check_version: ok (1.0)" in capsys.readouterr().out


def test_x_y_version_without_section_fails(repo, capsys):
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n\n## [0.9] - 2026-01-01\n", encoding="utf-8")
    _version(repo, "1.0\n", name="VERSION")
    assert mod.main() == 1
    assert "no '## [1.0]' section" in capsys.readouterr().out


@pytest.mark.parametrize("text", ["v1.0\n", "1.2.3.4\n", "1\n"])
def test_prefixed_or_malformed_version_is_not_found(repo, text):
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n\n## [1.0] - 2026-01-01\n", encoding="utf-8")
    _version(repo, text, name="VERSION")
    with pytest.raises(SystemExit, match="no version found in"):
        mod.main()


def test_default_version_file_in_root_is_used(repo, capsys):
    (repo / "CHANGELOG.md").write_text(CHANGELOG_OK, encoding="utf-8")
    _version(repo, "1.2.3\n", name="VERSION")
    assert mod.main() == 0
    assert "check_version: ok (1.2.3)" in capsys.readouterr().out
