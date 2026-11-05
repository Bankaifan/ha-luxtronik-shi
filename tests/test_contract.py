"""Entity contract: unique IDs and platforms must never change.

Consumers such as the Heat Pump Optimizer address entities by entity ID. Home Assistant keeps an
entity ID only as long as (platform, unique_id) stays the same. The unique ID is
``<entry_id>_<key>``, so every key in ``fixtures/entity_contract.json`` must keep existing on the
same platform. New keys are fine; add them to the fixture with ``python tools/gen_contract.py``.
Removing or renaming a key, or moving it to another platform, is a breaking change.
"""

from __future__ import annotations

import ast
import json
import pathlib

from custom_components.luxtronik_shi.registers import ALL_REGISTERS

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONTRACT = json.loads((ROOT / "tests" / "fixtures" / "entity_contract.json").read_text(encoding="utf-8"))


def _status_bits() -> list[str]:
    tree = ast.parse((ROOT / "custom_components" / "luxtronik_shi" / "binary_sensor.py").read_text(encoding="utf-8"))
    bits = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "STATUS_BITS"
    )
    return [bit[0] for bit in bits]


def _current() -> dict[str, set[str]]:
    current: dict[str, set[str]] = {}
    for reg in ALL_REGISTERS:
        current.setdefault(reg.platform, set()).add(reg.key)
    current.setdefault("binary_sensor", set()).update([*_status_bits(), "online"])
    return current


def test_no_contract_key_removed_or_moved():
    current = _current()
    broken = [
        f"{platform}.{key}"
        for platform, keys in CONTRACT.items()
        for key in keys
        if key not in current.get(platform, set())
    ]
    assert not broken, f"Entity-Vertrag verletzt (Key entfernt, umbenannt oder Plattform gewechselt): {broken}"


def test_new_keys_are_registered_in_contract():
    current = _current()
    missing = [
        f"{platform}.{key}"
        for platform, keys in current.items()
        for key in keys
        if key not in CONTRACT.get(platform, [])
    ]
    assert not missing, f"Neue Keys in tests/fixtures/entity_contract.json eintragen (tools/gen_contract.py): {missing}"
