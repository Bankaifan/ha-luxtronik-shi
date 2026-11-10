"""Issue #104: orchestrator runs ended silently because `make check` had no tools and `git -c` was denied."""

from __future__ import annotations

import pathlib

TEXT = (
    pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows" / "orchestrator.yml"
).read_text(encoding="utf-8")


def test_tools_are_installed_before_the_claude_run():
    install = TEXT.index("bash tools/ci/install_tools.sh")
    assert install < TEXT.index("id: claude")


def test_prompt_forbids_git_dash_c_and_cd_prefix():
    assert "plain `git commit -m" in TEXT
    assert "never `git -c ...` and never a `cd` prefix" in TEXT


def test_allowed_tools_not_widened():
    line = next(x for x in TEXT.splitlines() if "--allowedTools" in x)
    assert "Bash(git commit:*)" in line
    assert "Bash(bash" not in line
    assert "Bash(git -c" not in line
