"""Issue #468: managed changes need a changelog fragment, not a VERSION edit. The changed-file list is passed in, no git call."""
import importlib.util
import pathlib

import pytest

pytestmark = pytest.mark.template_only

ROOT = pathlib.Path(__file__).parent.parent.parent
_spec = importlib.util.spec_from_file_location("check_version_bump", ROOT / "tools" / "check" / "check_version_bump.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

MANAGED = ["tools/", "AGENTS.md"]


def test_managed_change_without_fragment_fails():
    errs = mod.errors(["tools/a.py", "README.md"], MANAGED)
    assert len(errs) == 1 and "tools/a.py" in errs[0] and "without a changelog fragment" in errs[0]


def test_managed_change_with_fragment_passes():
    assert mod.errors(["tools/a.py", "changelog.d/468.md"], MANAGED) == []
    assert mod.errors(["AGENTS.md", "changelog.d/7.md"], MANAGED, lambda f: "a line\nstep: x\n") == []


def test_version_edit_in_a_pr_fails_even_with_a_fragment():
    errs = mod.errors(["tools/a.py", "VERSION", "changelog.d/468.md"], MANAGED)
    assert len(errs) == 1 and "VERSION must not be edited" in errs[0]
    assert mod.errors(["VERSION"], MANAGED)


def test_docs_only_diff_passes():
    assert mod.errors(["README.md", "docs/a.md"], MANAGED) == []


def test_readme_in_changelog_dir_is_not_a_fragment():
    assert mod.errors(["tools/a.py", "changelog.d/README.md"], MANAGED)
    assert not mod.is_fragment("changelog.d/README.md") and not mod.is_fragment("x/changelog.d/1.md")
    assert mod.is_fragment("changelog.d/468.md")


def test_malformed_fragment_fails():
    for text in ("step: y\n", "\n", "line\nstep: z\n", "line\nstep: x\nstep: y\n"):
        errs = mod.errors(["tools/a.py", "changelog.d/1.md"], MANAGED, lambda f, t=text: t)
        assert len(errs) == 1 and "bad changelog fragment" in errs[0], text


def test_deleted_fragment_is_not_read():
    assert mod.errors(["tools/a.py", "changelog.d/1.md"], MANAGED, lambda f: None) == []


def test_release_pr_may_edit_version_and_remove_fragments():
    changed = ["VERSION", "CHANGELOG.md", "changelog.d/10.md", "changelog.d/11.md"]
    assert mod.errors(changed, MANAGED, lambda f: None, "release/next") == []
    assert mod.errors(changed, MANAGED, None, "release/next")  # without a reader a fragment counts as added
    assert mod.errors(changed, MANAGED, lambda f: None, "agent/1-x")  # the same diff elsewhere still fails


def test_release_pr_refuses_other_paths_and_added_fragments():
    errs = mod.errors(["VERSION", "tools/a.py"], MANAGED, None, "release/next")
    assert len(errs) == 1 and "tools/a.py" in errs[0]
    errs = mod.errors(["VERSION", "changelog.d/10.md"], MANAGED, lambda f: "x\n", "release/next")
    assert len(errs) == 1 and "must not add" in errs[0]


def test_main_uses_git_output(monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    monkeypatch.delenv("PR_HEAD_REF", raising=False)
    monkeypatch.setattr(mod, "git", lambda *a: "tools/a.py\n")
    monkeypatch.setattr(mod, "template_managed", lambda: MANAGED)
    assert mod.main(["origin/main"]) == 1
    assert "without a changelog fragment" in capsys.readouterr().out


def test_downstream_skips_without_git(monkeypatch, tmp_path, capsys):
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents" / "template.json").write_text("{}")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(mod, "git", lambda *a: pytest.fail("no git call downstream"))
    assert mod.main([]) == 0
    assert "skipped" in capsys.readouterr().out
