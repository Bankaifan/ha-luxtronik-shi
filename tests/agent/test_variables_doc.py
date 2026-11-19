import pathlib
import re

import pytest

# The template's own docs/variables.md: a project has no synced copy (the file is not managed), so nothing here applies there.
pytestmark = pytest.mark.template_only
ROOT = pathlib.Path(__file__).parent.parent.parent
_DOC = ROOT / "docs" / "variables.md"
DOC = _DOC.read_text(encoding="utf-8") if _DOC.is_file() else ""
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
