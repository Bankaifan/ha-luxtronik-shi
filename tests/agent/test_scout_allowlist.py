"""The scout's allowedTools lets the exact alert calls through, query string included (issue #338)."""

import re
from pathlib import Path

SCOUT = (Path(__file__).resolve().parent.parent.parent / ".github" / "workflows" / "scout.yml").read_text(encoding="utf-8")
REPO = "${{ github.repository }}"
ALLOWED = re.search(r'--allowedTools "([^"]+)"', SCOUT).group(1).split(",")


def test_alert_calls_allowed_exactly_with_query_string():
    for src in ("dependabot", "code-scanning"):
        call = f"gh api repos/{REPO}/{src}/alerts?state=open"
        assert f"Bash({call})" in ALLOWED
        # The prompt sends exactly the allowed call, nothing appended.
        assert f"`{call}`" in SCOUT


def test_no_prefix_rule_left_for_alert_paths():
    # The old `alerts:*` prefix rule never matched `alerts?state=open` (no word boundary).
    for src in ("dependabot", "code-scanning"):
        assert not any(rule.startswith(f"Bash(gh api repos/{REPO}/{src}/alerts") and ":*" in rule for rule in ALLOWED)


def test_prompt_names_denied_calls():
    assert "A call denied by the tool is not a read" in SCOUT
    assert "skipped (denied: gh api ...)" in SCOUT
