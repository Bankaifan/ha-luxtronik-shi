"""Design 0011 4.1b: managed changes need a VERSION bump. The changed-file list is passed in, no git call."""
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).parent.parent
if not (ROOT / "VERSION").exists():
    pytest.skip("the template VERSION file and its bump rule are not part of this project", allow_module_level=True)
_spec = importlib.util.spec_from_file_location("check_version_bump", ROOT / "tools" / "check" / "check_version_bump.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

MANAGED = ["tools/", "AGENTS.md"]


def test_managed_change_without_version_change_fails():
    errs = mod.errors(["tools/a.py", "README.md"], MANAGED, "1.0\n", "1.0\n")
    assert len(errs) == 1 and "tools/a.py" in errs[0] and "without a VERSION bump" in errs[0]


def test_managed_change_with_bump_passes():
    assert mod.errors(["tools/a.py", "VERSION"], MANAGED, "1.1\n", "1.0\n") == []
    assert mod.errors(["AGENTS.md", "VERSION"], MANAGED, "2.0\n", "1.5\n") == []


def test_docs_only_diff_passes():
    assert mod.errors(["README.md", "docs/a.md"], MANAGED, "1.0\n", "1.0\n") == []


def test_new_version_file_without_base_passes():
    assert mod.errors(["tools/a.py", "VERSION"], MANAGED, "1.0\n", None) == []


@pytest.mark.parametrize("text", ["v1.0\n", "1\n", "1.0.0\n", "1.0\n\n", "1.0\n; rm\n", ""])
def test_malformed_version_fails(text):
    errs = mod.errors(["VERSION"], MANAGED, text, "1.0\n")
    assert len(errs) == 1 and "not x.y" in errs[0]


def test_lowered_version_fails():
    errs = mod.errors(["tools/a.py", "VERSION"], MANAGED, "1.0\n", "1.5\n")
    assert len(errs) == 1 and "lower than the base" in errs[0]
    assert mod.errors(["VERSION"], MANAGED, "1.9\n", "2.0\n")  # numeric, not text, comparison: 1.9 < 2.0
    assert mod.errors(["VERSION"], MANAGED, "1.10\n", "1.9\n") == []


def test_missing_version_fails():
    assert mod.errors(["tools/a.py"], MANAGED, None, None)


def test_main_uses_git_output(monkeypatch, capsys):
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(mod, "git", lambda *a: "tools/a.py\n" if a[0] == "diff" else (ROOT / "VERSION").read_text())
    monkeypatch.setattr(mod, "template_managed", lambda: MANAGED)
    assert mod.main(["origin/main"]) == 1
    assert "without a VERSION bump" in capsys.readouterr().out
