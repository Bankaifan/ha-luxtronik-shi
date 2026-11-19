import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).parent.parent.parent
SCRIPT = ROOT / "tools" / "ci" / "install_tools.sh"


def test_requirements_are_read_from_the_script_root_not_the_cwd(tmp_path):
    """template-sync runs base/tools/ci/install_tools.sh from the workspace root, which has no requirements files."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "pip.log"
    pip = bin_dir / "pip"
    pip.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\n')
    pip.chmod(0o755)
    for name in ("curl", "tar", "sha256sum"):
        stub = bin_dir / name
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "RUNNER_TEMP": str(tmp_path / "tmp"), "HOME": str(tmp_path)}
    r = subprocess.run(["bash", str(SCRIPT)], check=False, cwd=cwd, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert f"-r {ROOT / 'requirements_test.txt'}" in log.read_text()
