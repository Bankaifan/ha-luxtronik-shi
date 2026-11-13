import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).parent.parent.parent
if not (ROOT / "docs" / "decisions" / "0012-orchestrator-events.md").exists():
    pytest.skip("template ADR 0012 is not part of this project", allow_module_level=True)
PREFILTER = (ROOT / "tools" / "prefilter.py").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "orchestrator.yml").read_text(encoding="utf-8")
ROLE = (ROOT / ".agents" / "roles" / "orchestrator.md").read_text(encoding="utf-8")
ADR = (ROOT / "docs" / "decisions" / "0012-orchestrator-events.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def reasons():
    """Every reason `event_reason` can return with work=True (the names the model sees in the log)."""
    return set(re.findall(r'return True, "([a-z-]+)"', PREFILTER))


def test_every_prefilter_reason_is_documented_in_role_and_adr():
    found = reasons()
    assert len(found) == 11, found
    for name in found:
        assert f"`{name}`" in ROLE, name
        assert f"`{name}`" in ADR, name


def test_adr_table_lists_the_same_reasons_as_the_code():
    table = ADR.split("| Event (action)", 1)[1].split("Any other combination", 1)[0]
    # Reason names are the backticked words followed by a colon (`startable-issue`: ...); `needs-human` is not one.
    assert set(re.findall(r"`([a-z-]+)`:", table)) == reasons()


def test_adr_names_the_triggers_that_exist_in_the_workflow():
    for trigger in ("issue_comment", "pull_request_target", "pull_request_review"):
        assert f"  {trigger}:" in WORKFLOW, trigger
        assert f"`{trigger}`" in ADR, trigger
    assert "types: [opened, edited, closed, labeled]" in WORKFLOW
    assert "`issues` opened, edited, closed, labeled" in ADR


def test_switch_is_documented_where_operators_look():
    assert "vars.ORCHESTRATOR_EVENTS == 'on'" in WORKFLOW
    for text in (ROLE, ADR, README):
        assert "ORCHESTRATOR_EVENTS" in text
    assert "`ORCHESTRATOR_EVENTS=off`" in ADR
