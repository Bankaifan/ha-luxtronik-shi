"""The entity set of the integration as ``platform -> keys``, without importing Home Assistant.

Shared by ``tests/test_contract.py`` and ``tools/gen_contract.py``. Unique IDs are ``<entry_id>_<key>``, so this
set (together with the platform of each key) decides which entity IDs exist.
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PKG = ROOT / "custom_components" / "luxtronik_shi"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))
import registers  # noqa: E402  (plain import, no Home Assistant needed)


def status_bits() -> list[str]:
    """Keys of the status bit binary sensors (``binary_sensor.STATUS_BITS``), read without Home Assistant."""
    tree = ast.parse((PKG / "binary_sensor.py").read_text(encoding="utf-8"))
    bits = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "STATUS_BITS"
    )
    return [bit[0] for bit in bits]


def current_entities() -> dict[str, set[str]]:
    """Every entity key per platform that the current code creates."""
    current: dict[str, set[str]] = {}
    for reg in registers.ALL_REGISTERS:
        if reg.platform == "internal":
            continue  # read only, no entity
        current.setdefault(reg.platform, set()).add(reg.key)
    current["climate"] = set(registers.CLIMATE_KEYS)
    current["water_heater"] = set(registers.WATER_HEATER_KEYS)
    current["select"] |= set(registers.BLOCK_SELECT_KEYS)
    current["switch"] |= set(registers.BLOCK_SWITCH_KEYS)
    current.setdefault("button", set()).update(registers.TRIGGER_ACTION_KEYS)
    current["sensor"] |= set(registers.DERIVED_SENSOR_KEYS) | {registers.FIRMWARE_SENSOR_KEY}
    current.setdefault("binary_sensor", set()).update([*status_bits(), *registers.DERIVED_FLAG_KEYS, "online"])
    return current
