import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).parent.parent.parent
SCRIPT = ROOT / "tools" / "ci" / "install_tools.sh"


def _run(tmp_path, extra_env, project_env=None):
    """Run install_tools.sh with stubbed pip/curl/tar so nothing is installed."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("pip", "curl", "tar", "sha256sum"):
        stub = bin_dir / name
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
    work = tmp_path / "work"
    (work / ".agents").mkdir(parents=True)
    if project_env is not None:
        (work / ".agents" / "project.env").write_text(project_env)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path / "tmp"),
        "HOME": str(tmp_path),
    }
    env.update(extra_env)
    return subprocess.run(["bash", str(SCRIPT)], check=False, cwd=work, env=env, capture_output=True, text=True)


def test_unset_runs_no_extra_command(tmp_path):
    r = _run(tmp_path, {})
    assert r.returncode == 0, r.stderr


def test_empty_runs_no_extra_command(tmp_path):
    marker = tmp_path / "marker"
    r = _run(tmp_path, {"EXTRA_INSTALL": ""})
    assert r.returncode == 0, r.stderr
    assert not marker.exists()


def test_env_command_runs(tmp_path):
    marker = tmp_path / "marker"
    r = _run(tmp_path, {"EXTRA_INSTALL": f"touch {marker}"})
    assert r.returncode == 0, r.stderr
    assert marker.exists()


def test_project_env_file_is_ignored(tmp_path):
    marker = tmp_path / "marker"
    r = _run(tmp_path, {}, project_env=f"EXTRA_INSTALL=touch {marker}\n")
    assert r.returncode == 0, r.stderr
    assert not marker.exists()
