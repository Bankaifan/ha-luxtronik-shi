"""Tests for tools/check_version.py (run against a temporary fake repo root)."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "tools" / "check_version.py"


def run(tmp_path: pathlib.Path, version: str, changelog: str, *args: str):
    manifest = tmp_path / "custom_components" / "luxtronik_shi" / "manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"version": version}))
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    env = {**os.environ, "CHECK_VERSION_ROOT": str(tmp_path)}
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env, check=False)


def log(version: str) -> str:
    return f"# Changelog\n\n## [Unreleased]\n\n## [{version}] – 2026-11-06\n\n### Added\n- Thing\n"


def test_stable_ok(tmp_path):
    r = run(tmp_path, "0.8.0", log("0.8.0"), "refs/tags/v0.8.0")
    assert r.returncode == 0, r.stdout
    assert run(tmp_path, "0.8.0", log("0.8.0"), "--prerelease").stdout.strip() == "false"


def test_beta_ok(tmp_path):
    r = run(tmp_path, "0.8.0-beta.1", log("0.8.0-beta.1"), "refs/tags/v0.8.0-beta.1")
    assert r.returncode == 0, r.stdout
    assert "beta pre-release" in r.stdout
    assert run(tmp_path, "0.8.0-beta.1", log("0.8.0-beta.1"), "--prerelease").stdout.strip() == "true"
    assert run(tmp_path, "0.8.0-beta.1", log("0.8.0-beta.1"), "--version").stdout.strip() == "0.8.0-beta.1"
    assert "Thing" in run(tmp_path, "0.8.0-beta.1", log("0.8.0-beta.1"), "--notes").stdout


def test_beta_missing_changelog_section_fails(tmp_path):
    r = run(tmp_path, "0.8.0-beta.1", log("0.8.0"))
    assert r.returncode == 1
    assert "no section" in r.stdout


def test_beta_not_matched_by_stable_section(tmp_path):
    r = run(tmp_path, "0.8.0", log("0.8.0-beta.1"))
    assert r.returncode == 1


def test_tag_mismatch_fails(tmp_path):
    r = run(tmp_path, "0.8.0-beta.1", log("0.8.0-beta.1"), "refs/tags/v0.8.0")
    assert r.returncode == 1
    assert "does not match" in r.stdout


def test_beta_release_requires_date(tmp_path):
    r = run(tmp_path, "0.8.0-beta.1", log("0.8.0-beta.1").replace(" – 2026-11-06", " – unreleased"), "--release")
    assert r.returncode == 1


@pytest.mark.parametrize("bad", ["0.8", "0.8.0-beta", "0.8.0-rc.1", "0.8.0-beta.x"])
def test_invalid_format_fails(tmp_path, bad):
    r = run(tmp_path, bad, log(bad))
    assert r.returncode == 1
    assert "not X.Y.Z" in r.stdout
