import pathlib

ROLES = pathlib.Path(__file__).parent.parent / ".agents" / "roles"


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
