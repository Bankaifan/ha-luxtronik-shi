"""install_tools.sh reads optional pins from .agents/tool-pins.env (design 0016 step 3)."""
import os
import pathlib
import subprocess

import pytest

pytestmark = pytest.mark.template_only  # the project keeps its own install_tools.sh

ROOT = pathlib.Path(__file__).parent.parent.parent
SCRIPT = ROOT / "tools" / "ci" / "install_tools.sh"


def _run(tmp_path, pins=None):
    """Run install_tools.sh with pip, curl and tar stubbed; returns (result, logged tool calls)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    for name in ("pip", "curl", "tar"):
        stub = bin_dir / name
        stub.write_text(f'#!/bin/sh\necho "{name} $@" >> "{log}"\n')
        stub.chmod(0o755)
    work = tmp_path / "work"
    (work / ".agents").mkdir(parents=True)
    if pins is not None:
        (work / ".agents" / "tool-pins.env").write_text(pins)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "RUNNER_TEMP": str(tmp_path / "tmp"),
        "HOME": str(tmp_path),
    }
    r = subprocess.run(["bash", str(SCRIPT)], check=False, cwd=work, env=env, capture_output=True, text=True)
    calls = log.read_text().splitlines() if log.exists() else []
    return r, calls


def test_without_file_uses_the_script_versions(tmp_path):
    r, calls = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "ruff==0.17.4" in calls[0]
    assert "zizmor==1.32.0" in calls[0]
    assert "v1.7.7/" in calls[1]


def test_empty_file_keeps_the_script_versions(tmp_path):
    r, calls = _run(tmp_path, pins="")
    assert r.returncode == 0, r.stderr
    assert "ruff==0.17.4" in calls[0]


def test_pins_override_the_three_tools(tmp_path):
    r, calls = _run(tmp_path, pins="RUFF=9.9.9\nZIZMOR=2.0.1\nACTIONLINT=1.8.0\n")
    assert r.returncode == 0, r.stderr
    assert "ruff==9.9.9" in calls[0]
    assert "zizmor==2.0.1" in calls[0]
    assert "ruff==0.17.4" not in calls[0]
    assert "v1.8.0/" in calls[1]


REFUSED = [
    "PYTEST=8.0.0",
    "ruff=0.17.4",
    "RUFF = 0.17.4",
    "RUFF=",
    "RUFF=abc",
    "RUFF=0.17.4 ",
    "RUFF=0.17.4;touch MARK",
    "RUFF=$(touch MARK)",
    "RUFF=`touch MARK`",
    "RUFF=0.17.4\n\nZIZMOR=1.0.0",
]


@pytest.mark.parametrize("pins", REFUSED)
def test_refused_line_fails_before_anything_is_installed(tmp_path, pins):
    marker = tmp_path / "marker"
    r, calls = _run(tmp_path, pins=pins.replace("MARK", str(marker)) + "\n")
    assert r.returncode != 0
    assert "tool-pins: refused" in r.stderr
    assert calls == []
    assert not marker.exists()
