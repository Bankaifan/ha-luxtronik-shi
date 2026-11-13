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
    monkeypatch.delenv("PR_BASE_REF", raising=False)  # set by make check in CI; these tests use no base ref
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


# Issue #462: tags and the release order.
TAGS = ["v0.19.0", "v1.0.0"]


def test_parse_orders_pre_releases_before_the_final_version():
    assert mod.parse("1.0.0-rc1") < mod.parse("1.0.0") < mod.parse("1.0.1")
    assert mod.parse("1.0.0-rc2") < mod.parse("1.0.0-rc10")  # numeric, not text
    assert mod.parse("v1.0") == mod.parse("1.0.0")
    assert mod.parse("0.19.0") < mod.parse("0.20.0") < mod.parse("1.0.0")
    assert mod.parse("latest") is None and mod.parse("build-5") is None


def test_next_version_from_the_highest_tag():
    assert mod.next_version(TAGS, "minor") == "1.1.0"
    assert mod.next_version(TAGS, "patch") == "1.0.1"
    assert mod.next_version(TAGS, "major") == "2.0.0"
    assert mod.next_version(["v0.9.0", "v0.19.0"], "minor") == "0.20.0"  # 0.19 is above 0.9 numerically
    assert mod.next_version([], "minor") == "0.1.0"
    assert mod.next_version(["latest"], "patch") == "0.0.1"


def test_version_equal_to_a_tag_fails():
    errs = mod.release_errors("1.0.0", TAGS)
    assert errs and "tag v1.0.0 already exists" in errs[0]
    assert any("tag 1.0.0 already exists" in e for e in mod.release_errors("1.0.0", ["1.0.0"]))


def test_version_below_the_highest_tag_fails():
    errs = mod.release_errors("0.19.5", TAGS)
    assert len(errs) == 1 and "not above the highest release v1.0.0" in errs[0]
    assert "1.1.0 (minor)" in errs[0] and "1.0.1 (patch)" in errs[0]


def test_version_above_the_highest_tag_passes():
    assert mod.release_errors("1.1.0", TAGS) == []
    assert mod.release_errors("1.0.1", TAGS) == []
    assert mod.release_errors("2.0", TAGS) == []
    assert mod.release_errors("1.1.0", []) == []


def test_pr_without_base_ref_does_not_read_tags(repo, monkeypatch):
    monkeypatch.delenv("PR_BASE_REF", raising=False)
    monkeypatch.setattr(mod, "git_tags", lambda: pytest.fail("no tag read outside a PR"))
    assert mod.pr_errors("1.0.0", "VERSION") == []


def test_pr_with_unchanged_version_passes(repo, monkeypatch):
    monkeypatch.setenv("PR_BASE_REF", "main")
    monkeypatch.setattr(mod, "base_version", lambda ref, name: "1.0.0")
    monkeypatch.setattr(mod, "git_tags", lambda: pytest.fail("unchanged version needs no tag check"))
    assert mod.pr_errors("1.0.0", "VERSION") == []


def test_pr_changing_the_version_is_checked_against_tags(repo, capsys, monkeypatch):
    (repo / "CHANGELOG.md").write_text("## [Unreleased]\n\n## [1.0.0] - 2026-01-01\n", encoding="utf-8")
    _version(repo, "1.0.0\n", name="VERSION")
    monkeypatch.setenv("PR_BASE_REF", "main")
    monkeypatch.setattr(mod, "base_version", lambda ref, name: "0.19.0")
    monkeypatch.setattr(mod, "git_tags", lambda: TAGS)
    assert mod.main() == 1
    assert "tag v1.0.0 already exists" in capsys.readouterr().out


def test_main_next_prints_only_the_number(monkeypatch, capsys):
    monkeypatch.setattr(mod, "git_tags", lambda: TAGS)
    assert mod.main(["--next", "minor"]) == 0
    assert capsys.readouterr().out == "1.1.0\n"
