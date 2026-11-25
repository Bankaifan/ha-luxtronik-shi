"""make type-check fails on a seeded type error and is skipped in a tree without Python files."""
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).parent.parent.parent


def _tree(tmp_path, source):
    shutil.copy(ROOT / "Makefile", tmp_path / "Makefile")
    shutil.copy(ROOT / "mypy.ini", tmp_path / "mypy.ini")
    if source is not None:
        (tmp_path / "tools").mkdir()
        (tmp_path / "tools" / "mod.py").write_text(source)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return subprocess.run(
        ["make", "--no-print-directory", "type-check"], cwd=tmp_path, capture_output=True, text=True, check=False
    )


def test_skipped_without_python_files(tmp_path):
    r = _tree(tmp_path, None)
    assert r.returncode == 0, r.stderr
    assert "no Python files" in r.stdout


@pytest.mark.skipif(shutil.which("mypy") is None, reason="mypy not installed")
def test_seeded_type_error_fails(tmp_path):
    r = _tree(tmp_path, "x: int = 'a'\n")
    assert r.returncode != 0
    assert "mod.py" in r.stdout


@pytest.mark.skipif(shutil.which("mypy") is None, reason="mypy not installed")
def test_clean_module_passes(tmp_path):
    r = _tree(tmp_path, "x: int = 1\n")
    assert r.returncode == 0, r.stdout
