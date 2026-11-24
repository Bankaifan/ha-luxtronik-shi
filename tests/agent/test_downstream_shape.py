"""The tests under tests/agent/ are synced to every project, but only managed paths travel with them.

A test that reads a file outside the managed paths (docs/decisions/, docs/variables.md, ...) passes in the template and
fails in every project after the next sync, where it stops the scripted sync (template 1.106 and 1.110 did exactly
that). This test builds what a project has of the template: the managed paths of the working tree, its config
`.agents/template.json` and the two files every project keeps itself. Then it runs the suite there.
A test that needs a template-only file is marked `@pytest.mark.template_only` and is skipped in that tree.
"""
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
PROJECT_OWNED = ("AGENTS.project.md",)  # not managed, but CLAUDE.md imports it: every project has one


def managed_paths():
    return json.loads((ROOT / ".agents" / "managed.json").read_text(encoding="utf-8"))["managed"]


def is_managed(path, managed):
    return any(path.startswith(m) if m.endswith("/") else path == m for m in managed)


def project_tree(dst):
    """The managed files as they are in the working tree (tracked and new ones), plus what a project owns."""
    managed = managed_paths()
    listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout.splitlines()
    for name in listed:
        src = ROOT / name
        if src.is_file() and (is_managed(name, managed) or name in PROJECT_OWNED):
            (dst / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst / name)
    (dst / ".agents").mkdir(exist_ok=True)
    (dst / ".agents" / "template.json").write_text(json.dumps(
        {"template": "Bankaifan/agent-template", "synced_sha": "0" * 40, "synced_version": "1.0", "managed": managed,
         "overrides": []}), encoding="utf-8")
    (dst / "VERSION").write_text("0.1\n", encoding="utf-8")
    return dst


@pytest.mark.slow
@pytest.mark.template_only  # it copies the template's own tree; in a project there is nothing to compare with
def test_the_suite_passes_in_a_tree_that_holds_only_the_managed_paths(tmp_path, clean_env):
    dst = project_tree(tmp_path / "project")
    assert not (dst / "docs" / "decisions").exists() and not (dst / "docs" / "variables.md").exists()
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qm", "project"]):
        subprocess.run(cmd, cwd=dst, check=True, capture_output=True)
    # not slow: the slow tests build trees of their own (this one included) and would recurse
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-m", "not slow", "-p", "no:cacheprovider",
                          "--timeout=120", "tests/agent"], cwd=dst, env=clean_env, capture_output=True, text=True,
                         check=False)
    assert run.returncode == 0, ("a test reads a file projects do not get by sync; mark it template_only or read a "
                                 "managed path:\n" + run.stdout[-3000:] + run.stderr[-500:])
