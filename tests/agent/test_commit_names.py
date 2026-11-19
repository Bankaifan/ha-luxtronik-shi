import subprocess
import sys
from pathlib import Path

import commit_names

TOOL = Path(commit_names.__file__)


def test_renamed_replaces_a_wrong_prefix_and_adds_a_missing_one():
    assert commit_names.renamed("V0-FOO: add x\n\nbody V1-X: y\n", "0.12", "FOO") == "V0.12-FOO: add x\n\nbody V1-X: y\n"
    assert commit_names.renamed("V1.101-OTHER: add x", "1.102", "FOO") == "V1.102-FOO: add x"
    assert commit_names.renamed("add x", "1.102", "FOO") == "V1.102-FOO: add x"


def test_branch_commits_get_the_version_of_the_base(tmp_path):
    def g(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True).stdout

    g("init", "-q", "-b", "main")
    g("config", "user.name", "Daniel")
    g("config", "user.email", "d@example.invalid")
    (tmp_path / "VERSION").write_text("0.12\n")
    g("add", "-A")
    g("commit", "-q", "-m", "base")
    g("checkout", "-q", "-b", "agent/1-foo")
    for n, subject in enumerate(("V0-FOO: first", "second")):
        (tmp_path / f"f{n}").write_text("x")
        g("add", "-A")
        g("commit", "-q", "-m", subject)
    tree = g("rev-parse", "HEAD^{tree}")
    done = subprocess.run([sys.executable, str(TOOL), "FOO", "main"], cwd=tmp_path, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    assert g("log", "--format=%s", "main..HEAD").split("\n")[:2] == ["V0.12-FOO: second", "V0.12-FOO: first"]
    assert g("rev-parse", "HEAD^{tree}") == tree and g("log", "-1", "--format=%s", "main") == "base\n"
