"""Downstream fixture end to end: template sync by script (design 0014, sections 4 and 6, acceptance 1-3).

The template and the downstream project are real git repos. Only `gh` is replaced: the compare and contents API are
answered from the template repo. apply, materialize, the guard, risk.classify and make check run as in production.
"""
import importlib.util
import io
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_TOOLS = ROOT / "tools"


def _load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ts = _load(_TOOLS / "template_sync.py")
mg = _load(_TOOLS / "managed_guard.py")
risk = _load(_TOOLS / "ci" / "risk.py")

SYNCED_FILES = {  # the template at synced_sha
    "VERSION": "1.0\n",
    ".github/claude-judge-settings.json": '{"permissions": {}}\n',
    "tools/a.py": "one\ntwo\nthree\n",
    "tools/gone.py": "bye\n",
    "tools/over_ok.py": "1\nb\nc\n",
    "tools/over_conflict.py": "x\n",
}
MAIN_CHANGES = {  # what the template changed up to the target SHA; None deletes the file
    "VERSION": "1.1\n",
    "tools/a.py": "one\nTWO\nthree\n",
    "tools/gone.py": None,
    "tools/b.py": "new b\n",
    "tools/c.py": "new c\n",
    "tools/over_ok.py": "1\nb\nC\n",
    "tools/over_conflict.py": "theirs\n",
}
LOCAL_EDITS = {  # the downstream project edited the overridden files on purpose
    "tools/over_ok.py": "mine 1\nb\nc\n",
    "tools/over_conflict.py": "mine\n",
}
OVERRIDES = [{"path": "tools/over_ok.py", "why": "local"}, {"path": "tools/over_conflict.py", "why": "local"}]
FIVE = ["tools/a.py", "tools/b.py", "tools/c.py", "tools/gone.py", "tools/over_ok.py"]
STATUS = {"A": "added", "M": "modified", "D": "removed"}
TEMPLATE_ONLY_TESTS = ["conftest.py", "test_check_version_bump.py", "test_managed_guard.py"]


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


def _commit(root, message):
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=test", "-c", "user.email=test@example.com", "commit", "-q", "-m", message)
    return _git(root, "rev-parse", "HEAD").strip()


def _write(root, files):
    for path, text in files.items():
        target = pathlib.Path(root, path)
        if text is None:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)


def _cfg_text(synced, overrides):
    cfg = {"template": "o/t", "synced_sha": synced, "synced_version": "1.0",
           "managed": ["tools/", ".github/"], "overrides": overrides}
    return json.dumps(cfg, indent=2) + "\n"


def _template(tmp_path, changes):
    """Template repo with two commits: SYNCED_FILES (synced_sha) and the changes on top (the target SHA)."""
    tpl = tmp_path / "template"
    tpl.mkdir()
    _git(tpl, "init", "-q")
    _write(tpl, SYNCED_FILES)
    synced = _commit(tpl, "synced")
    _write(tpl, changes)
    return tpl, synced, _commit(tpl, "main")


def _downstream(tmp_path, synced, overrides=OVERRIDES):
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init", "-q")
    files = {k: v for k, v in SYNCED_FILES.items() if k != "VERSION"}
    files.update(LOCAL_EDITS)
    files[".agents/template.json"] = _cfg_text(synced, overrides)
    _write(root, files)
    _commit(root, "project")
    return root


def _cfg(root):
    return ts.parse_config((root / ".agents" / "template.json").read_text())


def _committed(root):
    return sorted(_git(root, "show", "--name-only", "--format=", "HEAD").split())


def _fake_gh(monkeypatch, tpl):
    """gh api for the template repo o/t: compare (SHA...SHA) and contents (?ref=SHA). A missing file raises."""
    def gh(*args):
        assert args[0] == "api", args
        endpoint = args[1]
        m = re.fullmatch(r"repos/o/t/compare/([0-9a-f]{40})\.\.\.([0-9a-f]{40})", endpoint)
        if m:
            out = _git(tpl, "diff", "--name-status", "--no-renames", *m.groups())
            files = [{"filename": path, "status": STATUS[code]}
                     for code, path in (line.split("\t", 1) for line in out.splitlines())]
            return json.dumps({"files": files, "ahead_by": 1, "html_url": ""})
        m = re.fullmatch(r"repos/o/t/contents/(.+)\?ref=([0-9a-f]{40})", endpoint)
        if m:
            return _git(tpl, "show", f"{m.group(2)}:{m.group(1)}")
        raise AssertionError(f"unexpected gh call: {args}")
    monkeypatch.setattr(ts, "gh", gh)


def _apply_args(root, sha, body):
    return ["--root", str(root), "--sha", sha, "--body-file", str(body), "--issue", "477"]


def test_acceptance_1_apply_then_materialize_end_to_end(tmp_path, monkeypatch, capsys):
    tpl, synced, main = _template(tmp_path, MAIN_CHANGES)
    root = _downstream(tmp_path, synced)
    _fake_gh(monkeypatch, tpl)
    body = tmp_path / "body.md"
    assert ts.cmd_apply(_apply_args(root, main, body)) == 0
    assert capsys.readouterr().out == f"Template sync {main[:7]} part 1\n"
    assert _committed(root) == FIVE  # one commit, five files: synced_sha is not bumped, so template.json is not in it
    assert body.read_text().splitlines()[-1] == "Refs #477"
    assert "`tools/over_conflict.py`" in body.read_text()
    cfg = _cfg(root)
    assert cfg["synced_sha"] == synced
    assert mg.pr_errors(cfg, "o/project", f"Template sync {main[:7]} part 1", _committed(root)) == []

    assert ts.cmd_materialize(["--root", str(root), main]) == 0
    out = root / ".template" / "tools"
    assert (out / "over_conflict.py.ours").read_text() == "mine\n"
    assert (out / "over_conflict.py.base").read_text() == "x\n"
    assert (out / "over_conflict.py.theirs").read_text() == "theirs\n"
    assert not (out / "over_ok.py.ours").exists()
    assert _git(root, "status", "--porcelain") == ""  # the three versions are never committed


def test_acceptance_1_without_the_conflict_file_bumps_synced_and_closes(tmp_path, monkeypatch, capsys):
    changes = {k: v for k, v in MAIN_CHANGES.items() if k != "tools/over_conflict.py"}
    tpl, synced, main = _template(tmp_path, changes)
    root = _downstream(tmp_path, synced)
    _fake_gh(monkeypatch, tpl)
    body = tmp_path / "body.md"
    assert ts.cmd_apply(_apply_args(root, main, body)) == 0
    assert capsys.readouterr().out == "Template sync 1.1\n"
    assert _committed(root) == sorted(FIVE + [".agents/template.json"])
    cfg = _cfg(root)
    assert (cfg["synced_sha"], cfg["synced_version"]) == (main, "1.1")
    assert body.read_text().splitlines()[-1] == "Closes #477"
    assert mg.pr_errors(cfg, "o/project", "Template sync 1.1", _committed(root)) == []


def test_acceptance_2_sync_touching_judge_settings_runs_no_model(tmp_path, monkeypatch):
    changes = {"VERSION": "1.1\n", ".github/claude-judge-settings.json": '{"permissions": {"allow": []}}\n'}
    tpl, synced, main = _template(tmp_path, changes)
    root = _downstream(tmp_path, synced, overrides=[])
    _fake_gh(monkeypatch, tpl)
    assert risk.classify(_git(tpl, "diff", synced, main)) in ("infra", "security")  # a gated level, not "none"

    commands = []
    real_run = subprocess.run

    def recording_run(argv, *args, **kwargs):
        commands.append(pathlib.Path(argv[0]).name)
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", recording_run)
    body = tmp_path / "body.md"
    assert ts.cmd_apply(_apply_args(root, main, body)) == 0
    assert set(commands) == {"git"}  # no claude, anthropic or other program: apply is a script
    monkeypatch.undo()
    assert _committed(root) == sorted([".github/claude-judge-settings.json", ".agents/template.json"])
    assert body.read_text().splitlines()[-1] == "Closes #477"


@pytest.mark.slow
@pytest.mark.template_only  # checks the template's own files, not a downstream project
def test_acceptance_3_fresh_downstream_passes_make_check_and_needs_the_marker(tmp_path, clean_env):
    sha = _git(ROOT, "rev-parse", "HEAD").strip()
    dst = tmp_path / "downstream"
    dst.mkdir()
    data = subprocess.run(["git", "archive", "--format=tar", sha], cwd=ROOT, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:  # the template at the target SHA
        tar.extractall(dst)
    (dst / "VERSION").unlink()
    (dst / ".agents" / "managed.json").unlink()
    shutil.rmtree(dst / "tests")  # the full suite would recurse into this test: keep the template-only tests only
    (dst / "tests" / "agent").mkdir(parents=True)
    for name in TEMPLATE_ONLY_TESTS:
        shutil.copy(ROOT / "tests" / "agent" / name, dst / "tests" / "agent" / name)
    (dst / ".agents" / "template.json").write_text(_cfg_text(sha, []))
    _git(dst, "init", "-q")
    _commit(dst, "downstream")
    env = clean_env

    make = subprocess.run(["make", "check"], check=False, cwd=dst, env=env, capture_output=True, text=True)
    assert make.returncode == 0, (make.stdout + make.stderr)[-4000:]

    (dst / "tests" / "agent" / "conftest.py").unlink()  # no marker, no skips: the template-only tests run and fail downstream
    red = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], check=False, cwd=dst, env=env,
                         capture_output=True, text=True)
    assert red.returncode != 0
