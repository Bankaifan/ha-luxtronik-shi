"""Workflow changes of agent runs travel as a patch file and are applied by script after the security review."""
import importlib.util
import pathlib
import subprocess

import pytest

pytestmark = pytest.mark.template_only

ROOT = pathlib.Path(__file__).parent.parent.parent
_spec = importlib.util.spec_from_file_location("workflow_patch", ROOT / "tools" / "workflow_patch.py")
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def run(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def header(path):
    return f"diff --git a/{path} b/{path}\n"


def test_refusal():
    assert mod.refusal(header(".github/workflows/a.yml")) is None
    assert "outside" in mod.refusal(header("tools/a.py"))
    assert "outside" in mod.refusal(header(".github/workflows/../CODEOWNERS"))
    assert "owner or gate" in mod.refusal(header(".github/workflows/risk.yml"))
    assert "owner or gate" in mod.refusal(header(".github/workflows/workflow-apply.yml"))
    for line in ("rename from .github/CODEOWNERS", "new file mode 120000", "new mode 100755", "GIT binary patch"):
        assert "unsupported" in mod.refusal(header(".github/workflows/a.yml") + line + "\n")
    assert mod.refusal(header(".github/workflows/a.yml") + "new file mode 100644\n") is None
    assert mod.refusal("") == "no file in the patch"


def test_stash_then_apply(tmp_path, monkeypatch):
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    run(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    run(tmp_path, "clone", "-q", str(remote), str(work))
    run(work, "config", "user.name", "Daniel")
    run(work, "config", "user.email", "d@example.com")
    (work / ".github" / "workflows").mkdir(parents=True)
    (work / ".github" / "workflows" / "a.yml").write_text("on: push\n")
    run(work, "add", ".")
    run(work, "commit", "-q", "-m", "base")
    run(work, "push", "-q", "origin", "main")
    run(work, "checkout", "-q", "-b", "agent/7-x")
    (work / ".github" / "workflows" / "a.yml").write_text("on: pull_request\n")
    (work / ".github" / "workflows" / "b.yml").write_text("on: push\n")
    (work / "t.py").write_text("x = 1\n")
    run(work, "add", ".")
    run(work, "commit", "-q", "-m", "Change a workflow")
    monkeypatch.chdir(work)

    assert mod.stash("agent/7-*") == ["agent/7-x"]
    pushed = run(work, "ls-tree", "-r", "--name-only", "origin/agent/7-x")
    assert ".agents/workflow-patches/7.patch" in pushed and "t.py" in pushed
    assert ".github/workflows/b.yml" not in pushed
    assert run(work, "show", "origin/agent/7-x:.github/workflows/a.yml") == "on: push"
    assert run(work, "rev-list", "--count", "origin/main..origin/agent/7-x") == "1"

    sha = run(work, "rev-parse", "origin/agent/7-x")
    assert mod.apply("agent/7-x", sha) == 0
    run(work, "fetch", "-q", "origin")
    files = run(work, "ls-tree", "-r", "--name-only", "origin/agent/7-x")
    assert ".agents/workflow-patches/7.patch" not in files and ".github/workflows/b.yml" in files
    assert run(work, "show", "origin/agent/7-x:.github/workflows/a.yml") == "on: pull_request"
    assert run(work, "log", "-1", "--format=%an %s", "origin/agent/7-x") == "Daniel Change a workflow"
    assert run(work, "rev-list", "--count", "origin/main..origin/agent/7-x") == "1"


def test_apply_refuses_a_patch_that_reaches_other_files(tmp_path, monkeypatch):
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    run(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    run(tmp_path, "clone", "-q", str(remote), str(work))
    run(work, "config", "user.name", "Daniel")
    run(work, "config", "user.email", "d@example.com")
    (work / "t.py").write_text("x = 1\n")
    run(work, "add", ".")
    run(work, "commit", "-q", "-m", "base")
    run(work, "push", "-q", "origin", "main")
    run(work, "checkout", "-q", "-b", "agent/8-x")
    (work / ".agents" / "workflow-patches").mkdir(parents=True)
    smuggled = ("diff --git a/.github/workflows/a.yml b/.github/workflows/a.yml\nnew file mode 100644\n"
                "--- /dev/null\n+++ b/.github/workflows/a.yml\n@@ -0,0 +1 @@\n+on: push\n"
                "--- a/t.py\n+++ b/t.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n")
    (work / ".agents" / "workflow-patches" / "8.patch").write_text(smuggled)
    run(work, "add", ".")
    run(work, "commit", "-q", "-m", "Smuggle")
    run(work, "push", "-q", "origin", "agent/8-x")
    monkeypatch.chdir(work)
    sha = run(work, "rev-parse", "HEAD")
    assert mod.apply("agent/8-x", sha) == 3
    assert run(work, "rev-parse", "origin/agent/8-x") == sha
