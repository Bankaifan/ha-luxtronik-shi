"""check_downstream_compat: the parsers of older releases read this tree's install_tools.sh (PR #839)."""
import importlib.util
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location("cdc", ROOT / "tools" / "check" / "check_downstream_compat.py")
cdc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cdc)

STRICT = (
    "import re\n"
    "def tool_requirements(text):\n"
    "    out = []\n"
    "    for tok in text.split()[2:]:\n"
    "        if not re.fullmatch(r'[a-z-]+(==[0-9.]+)?', tok):\n"
    "            raise ValueError(f'unusable requirement in install_tools.sh: {tok!r}')\n"
    "        out.append(tok)\n"
    "    return out\n"
)
LENIENT = STRICT.replace("(==[0-9.]+)?", "((==|>=)[0-9.]+)?")


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin", "HOME": str(root)})


def _release(root, version, parser):
    tools = root / "tools"
    tools.mkdir(exist_ok=True)
    if parser is None:
        (tools / "template_sync.py").write_text("X = 1\n")
    else:
        (tools / "template_sync.py").write_text(parser)
    (root / "VERSION").write_text(f"{version}\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", f"release {version}")


def _repo(tmp_path, *parsers):
    root = tmp_path / "t"
    root.mkdir()
    _git(root, "init", "-q")
    for i, parser in enumerate(parsers):
        _release(root, f"1.{i}", parser)
    return root


def _script(root, line):
    path = root / "tools" / "ci" / "install_tools.sh"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"pip install {line}\n")


def test_a_script_every_release_reads_passes_with_the_newest_requirements(tmp_path):
    root = _repo(tmp_path, STRICT, LENIENT)
    _script(root, "ruff==0.1 pytest")
    assert cdc.check(root, 5) == ([], ["ruff==0.1", "pytest"])


def test_a_specifier_an_older_parser_refuses_fails_naming_that_release(tmp_path):
    root = _repo(tmp_path, STRICT, LENIENT)
    _script(root, "coverage>=7.0")
    errors, _ = cdc.check(root, 5)
    old = subprocess.run(["git", "-C", str(root), "log", "--format=%h", "-n1", "HEAD~1"],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert len(errors) == 1 and old[:7] in errors[0] and "coverage>=7.0" in errors[0]


def test_releases_beyond_the_window_are_not_asked(tmp_path):
    root = _repo(tmp_path, STRICT, LENIENT, LENIENT)
    _script(root, "coverage>=7.0")
    assert cdc.check(root, 2)[0] == []


def test_a_release_without_tool_requirements_is_skipped(tmp_path):
    root = _repo(tmp_path, None, LENIENT)
    _script(root, "coverage>=7.0")
    assert cdc.check(root, 5) == ([], ["coverage>=7.0"])


def test_no_release_history_is_an_error(tmp_path):
    root = tmp_path / "t"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "x").write_text("x")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "x")
    errors, _ = cdc.check(root, 5)
    assert errors and "fetch-depth" in errors[0]


def test_outside_the_template_it_skips(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cdc, "ROOT", tmp_path)
    assert cdc.main(["--out", str(tmp_path / "r.txt")]) == 0
    assert "skipped" in capsys.readouterr().out and not (tmp_path / "r.txt").exists()


def test_a_crashing_parser_is_reported_not_skipped(tmp_path):
    root = _repo(tmp_path, "raise RuntimeError('boom')\n")
    _script(root, "ruff==0.1")
    errors, _ = cdc.check(root, 5)
    assert len(errors) == 1 and "parser crashed" in errors[0] and "boom" in errors[0]


def test_main_writes_the_requirements_and_fails_on_an_unreadable_script(tmp_path, monkeypatch, capsys):
    root = _repo(tmp_path, STRICT)
    (root / ".agents").mkdir()
    (root / ".agents" / "managed.json").write_text("{}")
    monkeypatch.setattr(cdc, "ROOT", root)
    _script(root, "ruff==0.1 pytest")
    out = tmp_path / "r.txt"
    assert cdc.main(["--out", str(out)]) == 0
    assert out.read_text() == "ruff==0.1\npytest\n"
    _script(root, "coverage>=7.0")
    out.unlink()
    assert cdc.main(["--out", str(out)]) == 1
    assert "cannot read" in capsys.readouterr().err and not out.exists()


def test_a_window_without_any_tool_pin_parser_is_an_error_not_an_empty_pass(tmp_path):
    root = _repo(tmp_path, None)
    _script(root, "ruff==0.1")
    errors, reqs = cdc.check(root, 5)
    assert reqs == [] and errors and "nothing was checked" in errors[0]
