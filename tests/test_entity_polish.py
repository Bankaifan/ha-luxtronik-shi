"""Readable status texts, the single firmware entity and the labels of the water heater (simulator only)."""

from __future__ import annotations

import json
import pathlib

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.luxtronik_shi.const import DOMAIN
from custom_components.luxtronik_shi.registers import (
    BY_KEY,
    FIRMWARE_PARTS,
    FUNCTION_STATUS,
    REMOVED_KEYS,
    firmware_version,
)

from .fake_shi import FakeSHI
from .test_integration import _entity_id, _setup
from .test_migration import _entry
from .test_repairs import _issue

TRANSLATIONS = pathlib.Path(__file__).parent.parent / "custom_components" / "luxtronik_shi" / "translations"


def _state(hass: HomeAssistant, entry, key: str) -> str:
    return hass.states.get(_entity_id(hass, entry, "sensor", key)).state


# ------------------------------------------------------------------ status texts


async def test_function_status_is_text_not_a_number(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.input[10003] = 2
    shi.input[10004] = 0
    entry = await _setup(hass, shi)
    assert _state(hass, entry, "heating_status") == "requested"
    assert _state(hass, entry, "hot_water_status") == "disabled"
    state = hass.states.get(_entity_id(hass, entry, "sensor", "heating_status"))
    assert state.attributes["device_class"] == "enum"
    assert state.attributes["options"][:4] == ["disabled", "no_request", "requested", "running"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0, "disabled"), (1, "no_request"), (2, "requested"), (3, "running"), (4, "unknown_4"), (15, "unknown_15"), (16, "unknown")],
)
async def test_function_status_values(hass: HomeAssistant, shi: FakeSHI, raw: int, expected: str) -> None:
    shi.input[10004] = raw
    entry = await _setup(hass, shi)
    assert _state(hass, entry, "hot_water_status") == expected


def test_function_status_table_follows_python_luxtronik() -> None:
    # python-luxtronik ModeStatus: 0 Disabled, 1 No request, 2 Requested, 3 Running; the rest is unknown
    assert FUNCTION_STATUS[:4] == ("disabled", "no_request", "requested", "running")
    assert all(name == f"unknown_{index}" for index, name in enumerate(FUNCTION_STATUS) if index >= 4)
    for key in ("heating_status", "hot_water_status", "cooling_status", "pool_status"):
        assert BY_KEY[key].options == FUNCTION_STATUS


@pytest.mark.parametrize(("lang", "ok", "unknown"), [("de", "Läuft", "Unbekannt (7)"), ("en", "Running", "Unknown (7)")])
def test_function_status_is_translated(lang: str, ok: str, unknown: str) -> None:
    states = json.loads((TRANSLATIONS / f"{lang}.json").read_text(encoding="utf-8"))["entity"]["sensor"]
    for key in ("heating_status", "hot_water_status", "cooling_status", "pool_status"):
        assert set(states[key]["state"]) == set(FUNCTION_STATUS)
        assert states[key]["state"]["running"] == ok
        assert states[key]["state"]["unknown_7"] == unknown


# ------------------------------------------------------------------ firmware


def test_firmware_version_text() -> None:
    assert firmware_version(dict(zip(FIRMWARE_PARTS, (3, 92, 3), strict=True))) == "3.92.3"
    assert firmware_version(dict(zip(FIRMWARE_PARTS, (3, 92, None), strict=True))) is None
    assert firmware_version({}) is None


async def test_one_firmware_entity(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    assert _state(hass, entry, "firmware_version") == "3.92.3"
    registry = er.async_get(hass)
    unique_ids = {e.unique_id.removeprefix(f"{entry.entry_id}_") for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    assert "firmware_version" in unique_ids
    assert not unique_ids & set(REMOVED_KEYS)
    assert not [uid for uid in unique_ids if uid.startswith("fw_")]  # the three version registers have no entity
    entity = registry.async_get(_entity_id(hass, entry, "sensor", "firmware_version"))
    assert entity.entity_category is er.EntityCategory.DIAGNOSTIC
    assert dr.async_get(hass).async_get(entity.device_id).sw_version == "3.92.3"


async def test_old_firmware_entities_are_removed_from_the_registry(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = _entry(hass, shi)
    registry = er.async_get(hass)
    old = [
        registry.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_{key}", config_entry=entry)
        for key in REMOVED_KEYS
    ]
    other = registry.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_outside", config_entry=entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for item in old:
        assert registry.async_get(item.entity_id) is None
        assert hass.states.get(item.entity_id) is None
    assert registry.async_get(other.entity_id) is not None  # nothing else is touched


async def test_firmware_follows_an_update_and_the_issue_uses_major_minor(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.set_firmware(3, 90, 1)  # the registers read major, minor, patch
    entry = await _setup(hass, shi)
    assert _state(hass, entry, "firmware_version") == "3.90.1"
    assert _issue(hass, entry, "firmware_old").translation_placeholders["version"] == "3.90"
    shi.set_firmware(3, 93, 2)
    coordinator = entry.runtime_data
    coordinator._tick = 120  # firmware is only polled every 120th cycle
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, entry, "firmware_version") == "3.93.2"
    assert _issue(hass, entry, "firmware_old") is None


# ------------------------------------------------------------------ water heater labels


@pytest.mark.parametrize(
    ("lang", "labels"),
    [
        ("de", {"no_influence": "Keine Vorgabe", "setpoint": "Sollwert", "offset": "Anhebung", "level": "Stufe"}),
        ("en", {"no_influence": "No influence", "setpoint": "Setpoint", "offset": "Offset", "level": "Level"}),
    ],
)
def test_water_heater_operations_have_short_capitalised_labels(lang: str, labels: dict[str, str]) -> None:
    water_heater = json.loads((TRANSLATIONS / f"{lang}.json").read_text(encoding="utf-8"))["entity"]["water_heater"]
    entity = water_heater["water_heater_dhw"]
    assert entity["state"] == labels
    assert entity["state_attributes"]["operation_mode"]["state"] == labels
    assert not any(label[0].islower() for label in labels.values())


def test_water_heater_has_no_off_operation() -> None:
    from custom_components.luxtronik_shi.water_heater import OPERATION_MODES

    # raw 0 is "no influence" (python-luxtronik ControlMode 0: the controller uses its own values), never "off"
    assert "off" not in OPERATION_MODES
    assert OPERATION_MODES[0] == "no_influence"
