import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).parent.parent.parent
if not (ROOT / "docs" / "variables.md").exists():
    pytest.skip("template docs/variables.md is not part of this project", allow_module_level=True)
DOC = (ROOT / "docs" / "variables.md").read_text(encoding="utf-8")
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def workflow_variables():
    names = set()
    for path in WORKFLOWS:
        names |= set(re.findall(r"\bvars\.([A-Z][A-Z0-9_]*)", path.read_text(encoding="utf-8")))
    return names


def table_names():
    return set(re.findall(r"^\| `([A-Z][A-Z0-9_]*)` \|", DOC, re.MULTILINE))


def test_every_workflow_variable_has_a_row():
    assert workflow_variables(), "no vars.X found: the scan is broken"
    assert workflow_variables() <= table_names(), sorted(workflow_variables() - table_names())


def test_readmes_link_the_table():
    for name in ("README.md", "README.de.md"):
        assert "[docs/variables.md](docs/variables.md)" in (ROOT / name).read_text(encoding="utf-8"), name
