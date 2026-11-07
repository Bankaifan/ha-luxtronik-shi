"""Generate custom_components/luxtronik_shi/icons.json (run from repo root).

Icons live in icons.json (Home Assistant icon translations), not in the entity classes, so a state can change
the icon. Only entities where an icon says something are listed; everything else keeps the icon of its device
class. Keys must exist in the register map (``tests/test_icons.py`` checks the file against this script).
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "luxtronik_shi"))
import registers  # noqa: E402

OUTPUT = ROOT / "custom_components" / "luxtronik_shi" / "icons.json"

_OPERATING_MODE_ICONS = {
    "heating": "mdi:radiator",
    "hot_water": "mdi:water-boiler",
    "pool": "mdi:pool",
    "evu_lock": "mdi:transmission-tower-off",
    "defrost": "mdi:snowflake-melt",
    "off": "mdi:power-off",
    "external_source": "mdi:source-branch",
    "cooling": "mdi:snowflake",
}
_STATUS_ICONS = {
    "disabled": "mdi:cancel",
    "no_request": "mdi:sleep",
    "requested": "mdi:timer-sand",
    "running": "mdi:play-circle-outline",
}
_STATUS_KEYS = ("heating_status", "hot_water_status", "cooling_status", "pool_status")


def build() -> dict:
    """The content of icons.json."""
    sensor: dict[str, dict] = {
        "operating_mode": {"default": "mdi:heat-pump", "state": dict(_OPERATING_MODE_ICONS)},
        "error_number": {"default": "mdi:alert-circle-outline"},
        "firmware_version": {"default": "mdi:chip"},
    }
    for key in _STATUS_KEYS:
        sensor[key] = {"default": "mdi:information-outline", "state": dict(_STATUS_ICONS)}
    for derived in registers.DERIVED_SENSORS:
        sensor[derived.key] = {"default": "mdi:gauge"}
    binary_sensor: dict[str, dict] = {}
    for key in ("pump_heating", "pump_hot_water", "pump_circulation"):
        binary_sensor[key] = {"default": "mdi:pump-off", "state": {"on": "mdi:pump", "off": "mdi:pump-off"}}
    for key in ("output_vbo", "output_fp1", "output_fp2", "output_fp3"):
        binary_sensor[key] = {"default": "mdi:electric-switch"}
    for key in ("input_evu", "input_evu2"):
        binary_sensor[key] = {"default": "mdi:transmission-tower"}
    return {"entity": {"sensor": sensor, "binary_sensor": binary_sensor}}


def main() -> None:
    OUTPUT.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", OUTPUT)


if __name__ == "__main__":
    main()
