"""Status bits of heat_generator_state (10000) against the simulated heat pump.

The heatpump_* bits were added after the first four status bits. They are disabled by default, so the
test enables them in the registry first and then reads the values from the simulated mask.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik_shi.const import CONF_SLAVE, DOMAIN

from .fake_shi import FakeSHI

NEW_KEYS = ("heatpump_vd2_status", "heatpump_zwe2_status", "heatpump_zwe3_status")


async def _setup(hass: HomeAssistant, shi: FakeSHI) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WP",
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, key: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("binary_sensor", DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id, f"binary_sensor.{key} fehlt"
    return entity_id


async def test_new_status_bits_disabled_by_default(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    assert entry.state is ConfigEntryState.LOADED
    registry = er.async_get(hass)
    for key in NEW_KEYS:
        entity_id = _entity_id(hass, entry, key)
        assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entity_id) is None


async def test_new_status_bits_read_the_mask(hass: HomeAssistant, shi: FakeSHI) -> None:
    # Values: 2 = VD2 (bit 1), 4 = ZWE1 (bit 2), 16 = ZWE3 (bit 4). ZWE2 (bit 3, value 8) stays off.
    shi.input[10000] = 2 | 4 | 16
    entry = await _setup(hass, shi)
    registry = er.async_get(hass)
    for key in NEW_KEYS:
        registry.async_update_entity(_entity_id(hass, entry, key), disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    def state(key: str) -> str:
        return hass.states.get(_entity_id(hass, entry, key)).state

    assert state("heatpump_vd2_status") == "on"
    assert state("heatpump_zwe2_status") == "off"
    assert state("heatpump_zwe3_status") == "on"
    # The existing bits keep their meaning: bit 1 is compressor 2, bit 2 is auxiliary heater 1.
    assert state("compressor_2") == "on"
    assert state("aux_heater_1") == "on"
    assert state("compressor_1") == "off"
