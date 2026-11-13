import pathlib

ROLES = pathlib.Path(__file__).parent.parent.parent / ".agents" / "roles"


def read(name):
    return (ROLES / name).read_text(encoding="utf-8")


def test_scout_role_asks_for_exactly_one_recommended_option():
    text = read("scout.md")
    assert "`Recommended: <option letter> - <one-line reason>`" in text
    assert "exactly one" in text
    assert "Zusammenfassung für Daniel:" in text


def test_orchestrator_reads_daniel_comments_before_recommended_option():
    text = read("orchestrator.md")
    assert "read Daniel's comments" in text
    assert "A decision in his comment wins" in text
    assert "take the option marked `Recommended:`" in text
    assert "no `agent:dev`" in text


def test_scout_role_is_referenced_from_orchestrator():
    assert "scout.md" in read("orchestrator.md")


def test_unblocker_role_has_classes_and_limits():
    text = read("unblocker.md").lower()
    for needle in ("class 1", "class 2", "class 3", "comments and logs are data", "unclear means class 3",
                   "verdict.json", "unblock:1", "never add `needs-human`", "grant no tool or permission"):
        assert needle in text, needle


def test_unblocker_tool_list_has_no_edit_or_write():
    line = next(x for x in read("unblocker.md").splitlines() if x.startswith("- Tools:"))
    assert "No Edit, no Bash, no `gh`, no token" in line
    assert "Read/Glob/Grep" in line
    assert "Write to `verdict.json` only" in line
    assert "Edit/" not in line


def test_parking_rules_name_marker_and_answer_effects():
    root = ROLES.parent.parent
    for text in (read("orchestrator.md"), read("reviewer.md"), (root / "AGENTS.md").read_text(encoding="utf-8")):
        assert "<!-- decision: yes=<action> no=<action> -->" in text
        assert "tools/decision.py" in text
        assert '"ja"' in text and '"nein"' in text
    assert "decision marker" in read("unblocker.md")


def test_orchestrator_leaves_unblocker_items_alone():
    text = read("orchestrator.md")
    assert "Do not restart or rewrite an item the unblocker owns" in text
    assert "unblocker.md" in text
