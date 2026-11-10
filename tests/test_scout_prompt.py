"""The scout prompt and its allowedTools agree on the call form (issue #330)."""

from pathlib import Path

SCOUT = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "scout.yml").read_text(encoding="utf-8")
REPO = "${{ github.repository }}"


def test_alert_calls_unquoted_and_allowed():
    for src in ("dependabot", "code-scanning"):
        assert f"`gh api repos/{REPO}/{src}/alerts?state=open`" in SCOUT
        assert f"Bash(gh api repos/{REPO}/{src}/alerts?state=open)" in SCOUT
        assert f'gh api "repos/{REPO}/{src}' not in SCOUT


def test_prompt_forbids_chaining_and_label_create_is_single():
    assert "never chain with `;`, `&&` or pipes" in SCOUT
    assert "as its own single call" in SCOUT
    assert "Bash(gh label create:*)" in SCOUT
