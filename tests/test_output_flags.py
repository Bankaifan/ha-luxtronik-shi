"""Binary sensors for the proven digital outputs and inputs (pumps, FP, EVU) next to the unchanged raw values."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.luxtronik_shi.registers import ALIAS_OF, BY_KEY

from .fake_shi import FakeSHI
from .test_integration import _entity_id, _setup_with

ENABLED = ("pump_heating", "pump_hot_water", "pump_circulation", "output_vbo", "output_fp1")
DISABLED = ("output_fp2", "output_fp3", "input_evu", "input_evu2")


async def test_pumps_and_outputs_follow_the_registers(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.input[10354] = 1  # HUP
    shi.input[10355] = 0  # BUP
    shi.input[10356] = 1  # ZIP
    shi.input[10350] = 1
    shi.input[10351] = 0
    entry = await _setup_with(hass, shi, ["mk1"])
    expected = {
        "pump_heating": "on",
        "pump_hot_water": "off",
        "pump_circulation": "on",
        "output_vbo": "on",
        "output_fp1": "off",
    }
    for key, state in expected.items():
        assert hass.states.get(_entity_id(hass, entry, "binary_sensor", key)).state == state, key
    assert hass.states.get(_entity_id(hass, entry, "binary_sensor", "pump_heating")).attributes[
        "device_class"
    ] == "running"


async def test_defaults_and_the_unchanged_raw_values(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup_with(hass, shi, ["mk1"])
    registry = er.async_get(hass)
    for key in ENABLED:
        assert registry.async_get(_entity_id(hass, entry, "binary_sensor", key)).disabled_by is None, key
    for key in DISABLED:
        entity = registry.async_get(_entity_id(hass, entry, "binary_sensor", key))
        assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION, key
    # the raw sensors keep key, platform and the disabled default
    for raw_key in ALIAS_OF.values():
        entity = registry.async_get(_entity_id(hass, entry, "sensor", raw_key))
        assert entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION, raw_key


async def test_evu_flag_shows_the_level_once_enabled(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.input[10360] = 1
    entry = await _setup_with(hass, shi, ["mk1"])
    coordinator = entry.runtime_data
    assert "input_evu" not in coordinator.data  # disabled: not polled
    registry = er.async_get(hass)
    registry.async_update_entity(_entity_id(hass, entry, "binary_sensor", "input_evu"), disabled_by=None)
    await hass.async_block_till_done()
    assert coordinator.data["input_evu"] == 1


async def test_a_shared_register_is_read_once(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Raw sensor and binary sensor on one address: one block, one read, both values."""
    for address in range(10350, 10362):
        shi.input[address] = 0  # the whole block exists, so it is read as one request
    entry = await _setup_with(hass, shi, ["mk1"])
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    registry.async_update_entity(_entity_id(hass, entry, "sensor", "raw_10354"), disabled_by=None)
    await hass.async_block_till_done()
    shi.input[10354] = 1
    coordinator._tick = 0
    shi.requests.clear()
    await coordinator.async_refresh()
    reads = [r for r in shi.requests if r[0] == 4 and r[1] <= 10354 < r[1] + r[2]]
    assert len(reads) == 1
    assert coordinator.data["raw_10354"] == coordinator.data["pump_heating"] == 1


def test_flags_are_proven_and_documented_as_such() -> None:
    for key in (*ENABLED, *DISABLED):
        reg = BY_KEY[key]
        assert reg.source and reg.source.startswith("proven:"), key  # rule 3: no invented register facts


async def test_a_shared_register_in_a_split_block_is_read_once(hass: HomeAssistant, shi: FakeSHI) -> None:
    """The simulator lacks some addresses of the block: it is split, and the shared address is still read once."""
    entry = await _setup_with(hass, shi, ["mk1"])
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    coordinator._tick = 0
    await coordinator.async_refresh()  # the block with the missing addresses is rejected and split
    registry.async_update_entity(_entity_id(hass, entry, "sensor", "raw_10354"), disabled_by=None)
    await hass.async_block_till_done()
    assert any(block.split for block in coordinator._blocks)  # the plan for the new set keeps it
    shi.input[10354] = 1
    coordinator._tick = 0
    shi.requests.clear()
    await coordinator.async_refresh()
    singles = [r for r in shi.requests if r == (4, 10354, 1)]
    assert len(singles) == 1
    assert coordinator.data["raw_10354"] == coordinator.data["pump_heating"] == 1
