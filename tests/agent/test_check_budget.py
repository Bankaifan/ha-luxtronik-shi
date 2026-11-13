import importlib.util
import json
import pathlib

import pytest

_path = pathlib.Path(__file__).parent.parent.parent / "tools" / "check" / "check_budget.py"
_spec = importlib.util.spec_from_file_location("check_budget", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

REPO = pathlib.Path(__file__).parent.parent.parent


def _write_budgets(root, files, total):
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "budgets.json").write_text(json.dumps({"files": files, "total": total}), encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "AGENTS.md").write_bytes(b"x" * 100)
    (tmp_path / ".agents" / "roles").mkdir(parents=True)
    (tmp_path / ".agents" / "roles" / "developer.md").write_bytes(b"x" * 50)
    _write_budgets(tmp_path, {"AGENTS.md": 110, ".agents/roles/developer.md": 55}, total=165)
    return tmp_path


def test_within_caps_passes(repo, capsys):
    assert mod.main(repo) == 0
    assert "check_budget: ok (2 files, 150 of 165 bytes)" in capsys.readouterr().out


def test_shrinking_passes(repo, capsys):
    (repo / "AGENTS.md").write_bytes(b"x" * 10)
    assert mod.main(repo) == 0
    assert "check_budget: ok" in capsys.readouterr().out


def test_agents_over_cap_fails_and_names_file_size_and_cap(repo, capsys):
    (repo / "AGENTS.md").write_bytes(b"x" * 120)
    assert mod.main(repo) == 1
    out = capsys.readouterr().out
    assert "check_budget: AGENTS.md is 120 bytes, over its cap of 110 bytes" in out


def test_role_over_cap_fails_and_is_named(repo, capsys):
    (repo / ".agents" / "roles" / "developer.md").write_bytes(b"x" * 60)
    assert mod.main(repo) == 1
    out = capsys.readouterr().out
    assert "check_budget: .agents/roles/developer.md is 60 bytes, over its cap of 55 bytes" in out


def test_new_role_without_entry_fails(repo, capsys):
    (repo / ".agents" / "roles" / "new.md").write_bytes(b"x")
    assert mod.main(repo) == 1
    out = capsys.readouterr().out
    assert "check_budget: .agents/roles/new.md has no budget entry, add it to docs/budgets.json" in out


def test_total_over_cap_fails(repo, capsys):
    _write_budgets(repo, {"AGENTS.md": 110, ".agents/roles/developer.md": 55}, total=140)
    assert mod.main(repo) == 1
    out = capsys.readouterr().out
    assert "instruction files total 150 bytes, over the cap of 140 bytes" in out


def test_missing_budgets_file_is_an_error(repo, capsys):
    (repo / "docs" / "budgets.json").unlink()
    assert mod.main(repo) == 2
    assert "check_budget: cannot run" in capsys.readouterr().err


def test_malformed_budgets_file_is_an_error(repo, capsys):
    (repo / "docs" / "budgets.json").write_text('{"files": {"AGENTS.md": "big"}, "total": 1}', encoding="utf-8")
    assert mod.main(repo) == 2
    assert "expected" in capsys.readouterr().err


def test_repo_is_within_its_budgets(capsys):
    assert mod.main(REPO) == 0, capsys.readouterr().out
