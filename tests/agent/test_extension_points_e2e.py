"""Downstream project with the four extension-point files and no overrides (design 0016, step 8).

A template sync lands as a clean copy beside the project files, a fresh downstream with those files passes make check,
and the project's checks.json is accepted by the template's ruleset builder. Only `gh` is replaced, as in
test_template_sync_e2e.py; apply, the guard and make check run as in production.
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
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS / "ci"))
sys.path.insert(0, str(TOOLS))
import ruleset  # tools/ruleset.py, imported as in test_ruleset_build.py


def _load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ts = _load(TOOLS / "template_sync.py")
mg = _load(TOOLS / "managed_guard.py")

TEMPLATE_CHECKS = {"validate", "agent-smoke", "risk", "security-review"}
TEMPLATE_ONLY_TESTS = ["conftest.py", "test_check_version_bump.py", "test_managed_guard.py"]
MANAGED = ["tools/", "AGENTS.md"]
SYNCED = {  # the template at synced_sha
    "VERSION": "1.0\n",
    "AGENTS.md": "template rules\n",
    "tools/a.py": "one\ntwo\n",
    "tools/gone.py": "bye\n",
}
MAIN_CHANGES = {  # what the template changed up to the target SHA; None deletes the file
    "VERSION": "1.1\n",
    "AGENTS.md": "template rules, v2\n",
    "tools/a.py": "one\nTWO\n",
    "tools/gone.py": None,
    "tools/b.py": "new b\n",
}
COMMITTED = sorted(["AGENTS.md", "tools/a.py", "tools/b.py", "tools/gone.py", ".agents/template.json"])
PROJECT_FILES = {  # the four files of design 0016 (none of them is a managed path)
    "project.mk": "project-check::\n\t@echo PROJECT_CHECK_RAN\n",
    "AGENTS.project.md": "# Project rules\n\nNo project rule yet.\n",
    ".agents/checks.json": '{"required": ["lint-docs"]}\n',
    ".agents/tool-pins.env": "RUFF=0.9.10\n",
}


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


def _cfg_text(synced):
    cfg = {"template": "o/t", "synced_sha": synced, "synced_version": "1.0", "managed": MANAGED, "overrides": []}
    return json.dumps(cfg, indent=2) + "\n"


def _template(tmp_path):
    """Template repo: SYNCED (synced_sha), then MAIN_CHANGES on top (the target SHA)."""
    tpl = tmp_path / "template"
    tpl.mkdir()
    _git(tpl, "init", "-q")
    _write(tpl, SYNCED)
    synced = _commit(tpl, "synced")
    _write(tpl, MAIN_CHANGES)
    return tpl, synced, _commit(tpl, "main")


def _downstream(tmp_path, synced):
    """Downstream repo: the template's files at synced_sha, the four project files, no overrides."""
    root = tmp_path / "project"
    root.mkdir()
    _git(root, "init", "-q")
    files = {k: v for k, v in SYNCED.items() if k != "VERSION"}
    files.update(PROJECT_FILES)
    files[".agents/template.json"] = _cfg_text(synced)
    _write(root, files)
    _commit(root, "project")
    return root


def _committed(root):
    return sorted(_git(root, "show", "--name-only", "--format=", "HEAD").split())


def _fake_gh(monkeypatch, tpl):
    """gh api for the template repo o/t: compare (SHA...SHA) and contents (?ref=SHA). A missing file raises."""
    status = {"A": "added", "M": "modified", "D": "removed"}

    def gh(*args):
        assert args[0] == "api", args
        endpoint = args[1]
        m = re.fullmatch(r"repos/o/t/compare/([0-9a-f]{40})\.\.\.([0-9a-f]{40})", endpoint)
        if m:
            out = _git(tpl, "diff", "--name-status", "--no-renames", *m.groups())
            files = [{"filename": path, "status": status[code]}
                     for code, path in (line.split("\t", 1) for line in out.splitlines())]
            return json.dumps({"files": files, "ahead_by": 1, "html_url": ""})
        m = re.fullmatch(r"repos/o/t/contents/(.+)\?ref=([0-9a-f]{40})", endpoint)
        if m:
            return _git(tpl, "show", f"{m.group(2)}:{m.group(1)}")
        raise AssertionError(f"unexpected gh call: {args}")
    monkeypatch.setattr(ts, "gh", gh)


def test_sync_lands_as_a_clean_copy_beside_the_project_files(tmp_path, monkeypatch, capsys):
    tpl, synced, main = _template(tmp_path)
    root = _downstream(tmp_path, synced)
    _fake_gh(monkeypatch, tpl)
    body = tmp_path / "body.md"
    assert ts.cmd_apply(["--root", str(root), "--sha", main, "--body-file", str(body), "--issue", "533"]) == 0
    assert capsys.readouterr().out == "Template sync 1.1\n"  # no conflict: the clean title, not part 1
    assert _committed(root) == COMMITTED
    assert not (root / ".template").exists()  # nothing conflicted, so no three-way versions
    for path, text in PROJECT_FILES.items():
        assert (root / path).read_text() == text, path  # the sync never touches the project files
    cfg = ts.parse_config((root / ".agents" / "template.json").read_text())
    assert cfg["overrides"] == []
    assert (cfg["synced_sha"], cfg["synced_version"]) == (main, "1.1")
    assert body.read_text().splitlines()[-1] == "Closes #533"
    assert mg.pr_errors(cfg, "o/project", "Template sync 1.1", _committed(root)) == []


def test_checks_file_adds_its_name_to_the_template_set(tmp_path):
    checks = tmp_path / "checks.json"
    checks.write_text(PROJECT_FILES[".agents/checks.json"], encoding="utf-8")
    ruleset_path = str(ROOT / ".github" / "rulesets" / "main.json")
    assert ruleset.contexts(ruleset_path, str(checks)) == TEMPLATE_CHECKS | {"lint-docs"}


@pytest.mark.slow
@pytest.mark.template_only  # checks the template's own files, not a downstream project
def test_fresh_downstream_with_the_project_files_passes_make_check(tmp_path, clean_env):
    sha = _git(ROOT, "rev-parse", "HEAD").strip()
    dst = tmp_path / "downstream"
    dst.mkdir()
    data = subprocess.run(["git", "archive", "--format=tar", sha], cwd=ROOT, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:  # the template at the target SHA
        tar.extractall(dst)
    (dst / "VERSION").unlink()
    (dst / ".agents" / "managed.json").unlink()
    shutil.rmtree(dst / "tests")  # keep the template-only tests, as in test_template_sync_e2e.py
    (dst / "tests" / "agent").mkdir(parents=True)
    for name in TEMPLATE_ONLY_TESTS:
        shutil.copy(ROOT / "tests" / "agent" / name, dst / "tests" / "agent" / name)
    (dst / ".agents" / "template.json").write_text(_cfg_text(sha))
    _write(dst, PROJECT_FILES)
    _git(dst, "init", "-q")
    _commit(dst, "downstream")
    env = clean_env

    make = subprocess.run(["make", "check"], check=False, cwd=dst, env=env, capture_output=True, text=True)
    assert make.returncode == 0, (make.stdout + make.stderr)[-4000:]
    assert "PROJECT_CHECK_RAN" in make.stdout  # the project.mk recipe ran through the template's Makefile
