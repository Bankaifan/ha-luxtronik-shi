import re
from pathlib import Path

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "orchestrator.yml"

# Calls the orchestrator tried in runs that ended silently (issue #57); none may be allowed.
DENIED = ["gh issue close", "gh workflow list", "gh api", "git checkout", "git switch", "git fetch", "git -c"]


def test_prompt_names_the_calls_that_are_not_allowed():
    text = WF.read_text(encoding="utf-8")
    for call in DENIED:
        assert f"`{call}" in text, call


def test_allow_list_does_not_contain_the_denied_calls():
    text = WF.read_text(encoding="utf-8")
    allowed = re.search(r'--allowedTools "([^"]*)"', text).group(1)
    for call in DENIED:
        assert f"Bash({call}" not in allowed, call
