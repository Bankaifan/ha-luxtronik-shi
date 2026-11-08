"""Entity contract: a change detector for the entity set, to be updated deliberately.

Consumers such as the Heat Pump Optimizer address entities by entity ID. Home Assistant keeps an entity ID only as
long as (platform, unique_id) stays the same; the unique ID is ``<entry_id>_<key>``. ``fixtures/entity_contract.json``
lists every entity as ``platform -> keys`` and must equal what the code creates, in both directions:

* a new key is added with ``python tools/gen_contract.py``;
* a removed, renamed or moved key is edited into the fixture by hand, listed in ``REMOVED_KEYS`` (no entity left),
  ``REMOVED_ENTITIES`` (moved to another platform; the old registry entry is deleted at setup) or ``RENAMED_KEYS``
  (the registry entry is migrated, the entity ID stays), and documented under *Action required* in the CHANGELOG
  (CLAUDE.md, hard rule 1). This test makes sure none of that happens by accident.
"""

from __future__ import annotations

import json
import pathlib

from custom_components.luxtronik_shi.registers import (
    BY_KEY,
    REMOVED_ENTITIES,
    REMOVED_KEYS,
    RENAMED_KEYS,
)

from .contract import current_entities

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTRACT: dict[str, list[str]] = json.loads(
    (ROOT / "tests" / "fixtures" / "entity_contract.json").read_text(encoding="utf-8")
)


def test_fixture_equals_the_code() -> None:
    """Every entity in the fixture exists on its platform and every entity of the code is in the fixture."""
    current = current_entities()
    gone = [
        f"{platform}.{key}"
        for platform, keys in CONTRACT.items()
        for key in keys
        if key not in current.get(platform, set())
    ]
    assert not gone, (
        f"Entities in the fixture no longer exist (removed, renamed or moved to another platform): {gone}. "
        "If intended: edit tests/fixtures/entity_contract.json, list the key in REMOVED_KEYS / REMOVED_ENTITIES / "
        "RENAMED_KEYS and document it under 'Action required' in the CHANGELOG."
    )
    missing = [
        f"{platform}.{key}"
        for platform, keys in current.items()
        for key in keys
        if key not in CONTRACT.get(platform, [])
    ]
    assert not missing, f"Add new keys to tests/fixtures/entity_contract.json (python tools/gen_contract.py): {missing}"


def test_fixture_is_sorted_and_unique() -> None:
    for platform, keys in CONTRACT.items():
        assert keys == sorted(set(keys)), platform
    assert list(CONTRACT) == sorted(CONTRACT)


def test_renamed_keys_are_consistent() -> None:
    """A rename keeps the platform: the new key exists, the old one is gone from the code and the fixture."""
    current = current_entities()
    for old, new in RENAMED_KEYS.items():
        platforms = [platform for platform, keys in current.items() if new in keys]
        assert len(platforms) == 1, f"{old} -> {new}: the new key must exist on exactly one platform"
        assert all(old not in keys for keys in current.values()), f"{old} is still defined next to {new}"
        assert all(old not in keys for keys in CONTRACT.values()), f"{old} is still in the contract fixture"
        assert new not in RENAMED_KEYS, "chained renames are not supported"
        assert new in BY_KEY, f"{new} is not a register"


def test_removed_keys_are_gone_everywhere() -> None:
    """A removal is a deliberate exception (CHANGELOG): the key is out of the contract and out of the code."""
    current = current_entities()
    for key in REMOVED_KEYS:
        assert all(key not in keys for keys in CONTRACT.values()), f"{key} is still in the contract fixture"
        assert all(key not in keys for keys in current.values()), f"{key} still defines an entity"
        assert key not in RENAMED_KEYS


def test_moved_entities_live_on_another_platform() -> None:
    """A key that moved platform: gone from the old platform, present on exactly one other."""
    current = current_entities()
    for old_platform, key in REMOVED_ENTITIES:
        assert key not in current.get(old_platform, set()), f"{old_platform}.{key} still exists"
        assert key not in CONTRACT.get(old_platform, []), f"{old_platform}.{key} is still in the fixture"
        platforms = [platform for platform, keys in current.items() if key in keys]
        assert len(platforms) == 1 and platforms[0] != old_platform, (old_platform, key, platforms)
        assert key not in REMOVED_KEYS
