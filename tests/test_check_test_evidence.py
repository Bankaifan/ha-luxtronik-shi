import importlib.util
import pathlib
import subprocess

import pytest

_path = pathlib.Path(__file__).parent.parent / "tools" / "check" / "check_test_evidence.py"
_spec = importlib.util.spec_from_file_location("check_test_evidence", _path)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_docs_only_is_exempt():
    assert mod.decide(["README.md", "docs/a.md"], "")[0] == "exempt"


def test_no_test_file_is_exempt():
    assert mod.decide(["tools/x.py"], "")[0] == "exempt"


def test_exemption_with_reason_passes():
    assert mod.decide(["tools/x.py", "tests/test_x.py"], "Why\nTest evidence exempt: pure refactor\n")[0] == "exempt"


def test_exemption_without_reason_fails():
    assert mod.decide(["tools/x.py", "tests/test_x.py"], "Test evidence exempt:   \n")[0] == "fail"


def test_code_and_tests_need_a_run():
    assert mod.decide(["tools/x.py", "tests/test_x.py"], "Closes #1")[0] == "run"


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.name", "t")
    git(tmp_path, "config", "user.email", "t@example.com")
    (tmp_path / "pytest.ini").write_text("[pytest]\nasyncio_mode = auto\n")  # the Home Assistant plugin needs it
    (tmp_path / "lib.py").write_text("def f():\n    return 1\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "base")
    git(tmp_path, "checkout", "-q", "-b", "feature")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PR_BODY", raising=False)
    return tmp_path


def commit_change(repo, test_src):
    (repo / "lib.py").write_text("def f():\n    return 2\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_lib.py").write_text(test_src)
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "change")


def test_red_without_change_passes(repo, capsys):
    commit_change(repo, "import sys\nsys.path.insert(0, '.')\nimport lib\n\ndef test_f():\n    assert lib.f() == 2\n")
    assert mod.main(["main"]) == 0
    assert "red without the change" in capsys.readouterr().out


def test_data_file_under_tests_is_not_a_pytest_target(repo, capsys):
    commit_change(repo, "import sys\nsys.path.insert(0, '.')\nimport lib\n\ndef test_f():\n    assert lib.f() == 2\n")
    (repo / "tests" / "data.json").write_text("{}\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "data")
    assert mod.main(["main"]) == 0
    assert "red without the change" in capsys.readouterr().out


def test_always_green_test_fails(repo, capsys):
    commit_change(repo, "import sys\nsys.path.insert(0, '.')\nimport lib\n\ndef test_f():\n    assert lib.f() in (1, 2)\n")
    assert mod.main(["main"]) == 1
    assert "also pass without the change" in capsys.readouterr().out


def test_always_green_test_with_exemption_passes(repo, tmp_path):
    commit_change(repo, "def test_f():\n    assert True\n")
    body = repo.parent / "body.md"
    body.write_text("Test evidence exempt: tests existing behaviour\n")
    assert mod.main(["main", "--body-file", str(body)]) == 0


def test_unknown_base_is_an_error(repo):
    assert mod.main(["nope"]) == 2
