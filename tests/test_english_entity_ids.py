"""English entity IDs regardless of the Home Assistant language (1.1.0), their migration, and the status
re-read after a trigger button press."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.luxtronik_shi import async_migrate_english_entity_ids
from custom_components.luxtronik_shi.const import CONF_SLAVE, DOMAIN, TRIGGER_REREAD_DELAY
from custom_components.luxtronik_shi.registers import BY_KEY, TRIGGER_FOLLOWUPS

from .fake_shi import FakeSHI
from .test_integration import _entity_id
from .test_restore_after_reset import _writes


def _entry(hass: HomeAssistant, shi: FakeSHI) -> MockConfigEntry:
    from homeassistant.const import CONF_HOST, CONF_PORT

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Wärmepumpe",
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
        options={"scan_interval": 30, "features": ["mk1"]},
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _id(hass: HomeAssistant, entry: MockConfigEntry, domain: str, key: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{key}")


async def test_german_language_creates_english_entity_ids(hass: HomeAssistant, shi: FakeSHI) -> None:
    hass.config.language = "de"
    entry = _entry(hass, shi)
    await _setup(hass, entry)
    assert _id(hass, entry, "sensor", "flow") == "sensor.warmepumpe_temperature_flow"
    assert _id(hass, entry, "binary_sensor", "pump_hot_water") == "binary_sensor.warmepumpe_hot_water_pump_hot_water_bup"
    assert _id(hass, entry, "button", "extra_dhw") == "button.warmepumpe_hot_water_extra_start"
    assert _id(hass, entry, "climate", "climate_heating") == "climate.warmepumpe_heating"
    assert _id(hass, entry, "water_heater", "water_heater_dhw") == "water_heater.warmepumpe_hot_water"
    # the display names stay translated, the unique IDs are unchanged
    state = hass.states.get("sensor.warmepumpe_temperature_flow")
    assert state is not None and "Vorlauf" in state.attributes["friendly_name"]
    ids = er.async_get(hass).entities
    assert all(
        e.unique_id.startswith(f"{entry.entry_id}_") for e in ids.values() if e.platform == DOMAIN
    )


async def test_german_generated_entity_id_is_migrated(hass: HomeAssistant, shi: FakeSHI) -> None:
    hass.config.language = "de"
    entry = _entry(hass, shi)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_flow", config_entry=entry,
        suggested_object_id="warmepumpe_temperatur_vorlauf",
    )
    hand = registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_return", config_entry=entry,
        suggested_object_id="my_return_temperature",
    )
    await _setup(hass, entry)
    assert _id(hass, entry, "sensor", "flow") == "sensor.warmepumpe_temperature_flow"
    assert registry.async_get("sensor.warmepumpe_temperature_flow").id == old.id
    assert registry.async_get("sensor.warmepumpe_temperatur_vorlauf") is None
    assert registry.async_get(hand.entity_id).unique_id == f"{entry.entry_id}_return"  # user's ID untouched
    # a second run finds nothing to do
    async_migrate_english_entity_ids(hass, entry)
    assert _id(hass, entry, "sensor", "flow") == "sensor.warmepumpe_temperature_flow"


async def test_migration_skips_a_taken_target_and_logs(
    hass: HomeAssistant, shi: FakeSHI, caplog: pytest.LogCaptureFixture
) -> None:
    hass.config.language = "de"
    entry = _entry(hass, shi)
    registry = er.async_get(hass)
    registry.async_get_or_create("sensor", "other", "x", suggested_object_id="warmepumpe_temperature_flow")
    registry.async_get_or_create(
        "sensor", DOMAIN, f"{entry.entry_id}_flow", config_entry=entry,
        suggested_object_id="warmepumpe_temperatur_vorlauf",
    )
    await _setup(hass, entry)
    assert _id(hass, entry, "sensor", "flow") == "sensor.warmepumpe_temperatur_vorlauf"
    assert "already taken" in caplog.text


async def test_trigger_press_rereads_only_the_affected_status_registers(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = _entry(hass, shi)
    await _setup(hass, entry)
    followups = [BY_KEY[key].address for key in TRIGGER_FOLLOWUPS["extra_dhw"]]
    button = _entity_id(hass, entry, "button", "extra_dhw")
    shi.requests.clear()
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    assert _writes(shi) == [(6, 10071, 1)]
    before = list(shi.requests)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=TRIGGER_REREAD_DELAY + 1))
    await hass.async_block_till_done()
    extra = shi.requests[len(before):]
    polled = {reg.address for reg in entry.runtime_data.polled_registers}
    assert {address for _func, address, _count in extra} == {a for a in followups if a in polled}
    assert len(extra) == len([a for a in followups if a in polled]) >= 1
    assert all(func in (2, 4) for func, _address, _count in extra)  # reads only, no write
