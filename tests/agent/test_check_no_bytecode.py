import importlib.util
import pathlib
import subprocess

import pytest

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "check" / "check_no_bytecode.py"
_spec = importlib.util.spec_from_file_location("check_no_bytecode", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=repo, check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q")
    (tmp_path / "app.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _track(repo, *names):
    for name in names:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x00artifact")
    _git(repo, "add", "-A")


def test_clean_repo_passes(repo, capsys):
    _git(repo, "add", "-A")
    assert mod.main() == 0
    assert "check_no_bytecode: ok" in capsys.readouterr().out


@pytest.mark.parametrize("name", [
    "mod.pyc",
    "pkg/mod.pyo",
    "__pycache__/notes.txt",
    "pkg/__pycache__/data.bin",
])
def test_tracked_bytecode_fails_and_is_named(repo, capsys, name):
    _track(repo, name)
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert f"check_no_bytecode: tracked bytecode {name}" in out
    assert "git rm --cached" in out


def test_untracked_bytecode_is_ignored(repo, capsys):
    (repo / "mod.pyc").write_bytes(b"\x00artifact")
    _git(repo, "add", "-A", "--", "app.py")
    assert mod.main() == 0
    assert "check_no_bytecode: ok" in capsys.readouterr().out
