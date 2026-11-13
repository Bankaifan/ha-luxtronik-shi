import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent / "tools"))

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def is_downstream(root=ROOT):
    """A downstream project has .agents/template.json (design 0011 section 2); the template repo does not."""
    return (root / ".agents" / "template.json").is_file()


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "template_only: test of template-only files; skipped in downstream projects (design 0014 section 4.4)",
    )


def pytest_collection_modifyitems(config, items):
    if not is_downstream():
        return
    skip = pytest.mark.skip(reason="template_only: this is a downstream project (.agents/template.json exists)")
    for item in items:
        if item.get_closest_marker("template_only"):
            item.add_marker(skip)


@pytest.fixture
def clean_env():
    """The outer environment minus everything a CI run sets per event (PR_*, GH_*, GITHUB_*, ...): the inner make check
    of a fresh downstream must behave the same in a push run, an owner run and an app run."""
    drop = ("PR_", "GH_", "GITHUB_", "NIGHTLY_", "VERSION_", "RUNNER_", "RUN_")
    return {k: v for k, v in os.environ.items() if not k.startswith(drop)}
