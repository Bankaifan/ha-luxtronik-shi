"""Guards for the main ruleset file: the strict flag (decision 0010, turned off again by decision 0020)."""

import json
from pathlib import Path

import pytest

RULESET = Path(__file__).resolve().parent.parent.parent / ".github" / "rulesets" / "main.json"


def _rule(name: str) -> dict:
    rules = json.loads(RULESET.read_text(encoding="utf-8"))["rules"]
    return next(r for r in rules if r["type"] == name)


def test_strict_status_checks_policy_is_off_by_decision_0020():
    """A PR no longer has to be on the newest main to merge: every merge sent all other approved PRs through rebase,
    CI and approval again. The checks themselves stay required; main is checked after each merge."""
    assert _rule("required_status_checks")["parameters"]["strict_required_status_checks_policy"] is False


@pytest.mark.template_only  # docs/decisions/ is not a managed path: a downstream project does not get it by sync
def test_decision_0020_records_the_flag():
    decision = (RULESET.parent.parent.parent / "docs" / "decisions" / "0020-parallel-merge.md").read_text(encoding="utf-8")
    assert "strict_required_status_checks_policy" in decision and "0010" in decision


def test_required_checks_unchanged():
    checks = _rule("required_status_checks")["parameters"]["required_status_checks"]
    assert [c["context"] for c in checks] == ["validate", "agent-smoke", "risk", "security-review"]
