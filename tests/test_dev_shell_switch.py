"""Design 0017 step 6: the DEV_SHELL switch gives dev and fix runs a free shell (bare Bash) only when the repo variable is "free".

Unset keeps the command list; the 0004 deny settings stay in both cases. The switch is wired only in the two model jobs."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
PATCHES = ROOT / ".agents" / "workflow-patches"
MODEL_JOBS = ("agent-dev.yml", "agent-fix.yml")
# A bare Bash tool: "Bash" not followed by "(" (a scoped form) or another word character.
BARE_BASH = re.compile(r"Bash(?![(\w])")
# The switch expression inside --allowedTools: free -> 'Bash', otherwise the command list (group 1).
SWITCH = re.compile(r"\$\{\{ vars\.DEV_SHELL == 'free' && 'Bash' \|\| '([^']*)' \}\}")
PREFIX = "Read,Edit,Write,Glob,Grep,"


def allowed_tools_values(name):
    text = (WORKFLOWS / name).read_text()
    return re.findall(r'--allowedTools "([^"]*)"', text)


def render(value, shell):
    """Return the --allowedTools value GitHub Actions produces for DEV_SHELL = shell ("" when unset)."""
    match = SWITCH.search(value)
    assert match, f"no DEV_SHELL switch in {value!r}"
    replacement = "Bash" if shell == "free" else match.group(1)
    return value[: match.start()] + replacement + value[match.end():]


def test_switch_is_wired_only_in_model_jobs():
    for path in WORKFLOWS.glob("*.yml"):
        if path.name in MODEL_JOBS:
            assert "DEV_SHELL" in path.read_text(), path.name
        else:
            assert "DEV_SHELL" not in path.read_text(), path.name


def test_unset_keeps_the_command_list():
    for name in MODEL_JOBS:
        values = allowed_tools_values(name)
        assert len(values) == 1, f"{name}: expected one --allowedTools"
        unset = render(values[0], "")
        assert unset.startswith(PREFIX), name
        assert not BARE_BASH.search(unset), f"{name}: bare Bash without DEV_SHELL=free"
        assert "Bash(git:*)" in unset and "Bash(make:*)" in unset, name


def test_free_gives_bare_bash():
    for name in MODEL_JOBS:
        (value,) = allowed_tools_values(name)
        assert render(value, "free") == PREFIX + "Bash", name


def test_deny_settings_stay_in_model_jobs():
    for name in MODEL_JOBS:
        text = (WORKFLOWS / name).read_text()
        assert "--settings .github/claude-judge-settings.json" in text, name


def test_no_patch_grants_bare_bash():
    for patch in PATCHES.glob("*.patch"):
        for line in patch.read_text().splitlines():
            if line.startswith("+") and "--allowedTools" in line:
                # The switch itself names 'Bash' for DEV_SHELL=free; only a bare Bash outside it is a grant.
                assert not BARE_BASH.search(SWITCH.sub("", line)), f"{patch.name}: bare Bash grant"
