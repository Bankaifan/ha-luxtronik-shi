"""Guards for the main ruleset file (design 0003, section 8 item 5): the strict flip."""

import json
from pathlib import Path

RULESET = Path(__file__).resolve().parent.parent.parent / ".github" / "rulesets" / "main.json"


def _rule(name: str) -> dict:
    rules = json.loads(RULESET.read_text(encoding="utf-8"))["rules"]
    return next(r for r in rules if r["type"] == name)


def test_strict_status_checks_policy_is_true():
    assert _rule("required_status_checks")["parameters"]["strict_required_status_checks_policy"] is True


def test_required_checks_unchanged():
    checks = _rule("required_status_checks")["parameters"]["required_status_checks"]
    assert [c["context"] for c in checks] == ["validate", "agent-smoke", "risk", "security-review"]
