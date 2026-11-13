import os
import pathlib
import subprocess

import pytest

SCRIPT = pathlib.Path(__file__).parent.parent.parent / "tools" / "check" / "check_drift.sh"

# Fake generator: writes the files named in GEN_FILES ("name=content" per line) into the repo root.
GENERATOR = """\
import os
for line in os.environ.get("GEN_FILES", "").splitlines():
    name, _, content = line.partition("=")
    with open(name, "w", encoding="utf-8") as f:
        f.write(content + "\\n")
"""


def _git(repo, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=repo, check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "gen_x.py").write_text(GENERATOR, encoding="utf-8")
    (tmp_path / "out.txt").write_text("v1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def _run(repo, gen_files="out.txt=v1"):
    env = {"PATH": os.environ["PATH"], "GEN_FILES": gen_files}
    return subprocess.run(["bash", str(SCRIPT)], cwd=repo, env=env, capture_output=True, text=True, check=False)


def test_clean_tree_passes(repo):
    r = _run(repo)
    assert r.returncode == 0, r.stderr
    assert "check_drift: ok" in r.stdout


def test_no_generators_passes(tmp_path):
    _git(tmp_path, "init", "-q")
    r = _run(tmp_path)
    assert r.returncode == 0
    assert "no generators" in r.stdout


def test_tracked_diff_fails(repo):
    r = _run(repo, "out.txt=v2")
    assert r.returncode == 1
    assert "out of date" in r.stderr
    assert "out.txt" in r.stderr


def test_untracked_file_fails_and_is_named(repo):
    r = _run(repo, "out.txt=v1\nstray.txt=new")
    assert r.returncode == 1
    assert "?? stray.txt" in r.stderr


def test_results_sarif_is_ignored(repo):
    r = _run(repo, "out.txt=v1\nresults.sarif={}")
    assert r.returncode == 0, r.stderr
    assert "check_drift: ok" in r.stdout
