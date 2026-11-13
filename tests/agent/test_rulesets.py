"""Guards for the agent ruleset files (design 0017, section 8 step 2): refs confined to agent/**, no tag creation by the app."""

import json
from pathlib import Path

RULESETS = Path(__file__).resolve().parent.parent.parent / ".github" / "rulesets"
REFS = RULESETS / "agent-refs.json"
TAGS = RULESETS / "agent-tags.json"
MAIN = RULESETS / "main.json"
ADMIN_BYPASS = [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_refs_ruleset_covers_all_branches_but_default_and_agent():
    ruleset = _load(REFS)
    assert ruleset["target"] == "branch"
    assert ruleset["enforcement"] == "active"
    ref_name = ruleset["conditions"]["ref_name"]
    assert ref_name["include"] == ["~ALL"]
    assert sorted(ref_name["exclude"]) == ["refs/heads/agent/**", "~DEFAULT_BRANCH"]


def test_refs_ruleset_restricts_creation_update_and_deletion():
    assert sorted(r["type"] for r in _load(REFS)["rules"]) == ["creation", "deletion", "update"]


def test_refs_ruleset_has_the_same_bypass_as_main():
    assert _load(REFS)["bypass_actors"] == _load(MAIN)["bypass_actors"] == ADMIN_BYPASS


def test_tag_ruleset_blocks_tag_creation():
    ruleset = _load(TAGS)
    assert ruleset["target"] == "tag"
    assert ruleset["enforcement"] == "active"
    assert ruleset["conditions"]["ref_name"] == {"include": ["~ALL"], "exclude": []}
    assert [r["type"] for r in ruleset["rules"]] == ["creation"]
    assert ruleset["bypass_actors"] == ADMIN_BYPASS
