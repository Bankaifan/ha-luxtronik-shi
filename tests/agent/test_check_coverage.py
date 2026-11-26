import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "check" / "check_coverage.py"
_spec = importlib.util.spec_from_file_location("check_coverage", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _floor(root, value):
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "coverage.json").write_text(json.dumps({"floor": value}), encoding="utf-8")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "tests").mkdir()
    _floor(tmp_path, 50)
    monkeypatch.setattr(mod, "measure", lambda root: 49.9)
    return tmp_path


def test_below_floor_fails(repo, capsys):
    assert mod.main(repo) == 1
    assert "49.90 %, below the floor of 50 %" in capsys.readouterr().out


def test_at_floor_passes(repo, monkeypatch, capsys):
    monkeypatch.setattr(mod, "measure", lambda root: 50.0)
    assert mod.main(repo) == 0
    assert "check_coverage: ok" in capsys.readouterr().out


def test_above_floor_passes(repo, monkeypatch):
    monkeypatch.setattr(mod, "measure", lambda root: 80.0)
    assert mod.main(repo) == 0


def test_scoped_run_is_skipped(repo, capsys):
    assert mod.main(repo, scoped=True) == 0
    assert "skipped (scoped run" in capsys.readouterr().out


def test_missing_floor_file_is_skipped(repo, capsys):
    (repo / "docs" / "coverage.json").unlink()
    assert mod.main(repo) == 0
    assert "skipped (no docs/coverage.json)" in capsys.readouterr().out


def test_no_tests_dir_is_skipped(repo, capsys):
    (repo / "tests").rmdir()
    assert mod.main(repo) == 0
    assert "skipped (no tests/)" in capsys.readouterr().out


def test_malformed_floor_file_fails(repo, capsys):
    (repo / "docs" / "coverage.json").write_text('{"floor": "high"}', encoding="utf-8")
    assert mod.main(repo) == 2
    assert "cannot run" in capsys.readouterr().err


def test_measure_failure_fails(repo, monkeypatch, capsys):
    def boom(root):
        raise ValueError("no data")

    monkeypatch.setattr(mod, "measure", boom)
    assert mod.main(repo) == 2
    assert "no data" in capsys.readouterr().err


def test_measure_reads_the_total_of_real_coverage_data(tmp_path):
    pytest.importorskip("coverage")  # pinned by tools/ci/install_tools.sh
    (tmp_path / "half.py").write_text("import sys\nif len(sys.argv) > 5:\n    print('never')\n    print('never')\n",
                                      encoding="utf-8")
    subprocess.run([sys.executable, "-m", "coverage", "run", "half.py"], cwd=tmp_path, check=True)
    total = mod.measure(tmp_path)
    assert total == pytest.approx(50.0)
    (tmp_path / "tests").mkdir()
    _floor(tmp_path, 50)
    assert mod.main(tmp_path) == 0
    _floor(tmp_path, 51)
    assert mod.main(tmp_path) == 1
