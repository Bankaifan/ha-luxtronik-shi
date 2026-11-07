"""Only registers with an enabled entity are polled; what the integration uses itself is always read."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.luxtronik_shi import climate, water_heater
from custom_components.luxtronik_shi import coordinator as coordinator_module
from custom_components.luxtronik_shi.const import OUTAGE_WATCH_KEYS, RESTORE_KEYS
from custom_components.luxtronik_shi.coordinator import plan_blocks
from custom_components.luxtronik_shi.poll_plan import PLATFORM_SOURCE_KEYS, internal_keys
from custom_components.luxtronik_shi.registers import (
    ALL_REGISTERS,
    BY_KEY,
    DERIVED_SENSORS,
    FIRMWARE_PARTS,
    SETPOINT_GROUPS,
    active_registers,
)

from .fake_shi import FakeSHI
from .test_integration import _entity_id, _setup


def _polled_keys(entry) -> set[str]:
    return {reg.key for reg in entry.runtime_data.polled_registers}


def _requested(shi: FakeSHI, kind_func: int, address: int) -> bool:
    return any(f == kind_func and a <= address < a + n for f, a, n in shi.requests)


async def _cycle(entry) -> None:
    """A poll that reads every block (tick 0 of a cycle), as the first one does."""
    entry.runtime_data._tick = 0
    await entry.runtime_data.async_refresh()


def test_internal_keys_exist() -> None:
    assert internal_keys() <= set(BY_KEY)


def test_internal_keys_cover_what_the_code_uses() -> None:
    keys = internal_keys()
    assert set(FIRMWARE_PARTS) <= keys
    assert set(OUTAGE_WATCH_KEYS) <= keys
    assert RESTORE_KEYS <= keys
    for setpoint, (mode, target) in SETPOINT_GROUPS.items():
        assert {setpoint, mode, target} <= keys
    for sensor in DERIVED_SENSORS:
        assert {sensor.thermal, sensor.electric} <= keys
    assert {key for key in BY_KEY if key.startswith("cap_")} <= keys


def test_platform_source_keys_match_the_platform_modules() -> None:
    used = {
        climate._MODE_REG.key,
        climate._SETPOINT_REG.key,
        climate._RETURN_REG.key,
        climate._BLOCK_REG.key,
        climate._OPERATING_REG.key,
        water_heater._MODE_REG.key,
        water_heater._SETPOINT_REG.key,
        water_heater._TEMP_REG.key,
        "heat_generator_state",  # status bits and the generator check of the climate entity
    }
    assert used <= PLATFORM_SOURCE_KEYS


async def test_disabled_entities_are_not_polled(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    polled = _polled_keys(entry)
    disabled = {reg.key for reg in active_registers(None) if not reg.enabled_default} - internal_keys()
    assert disabled and not (disabled & polled)
    assert "raw_10354" not in entry.runtime_data.data
    assert "flow" in polled
    shi.requests.clear()
    await _cycle(entry)
    assert not _requested(shi, 4, 10354)  # HUP output, disabled by default
    assert _requested(shi, 4, 10100)  # a normal block is still read


async def test_internal_keys_are_polled_without_an_enabled_entity(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Disabling the entity of a register the integration uses itself must not stop the reads."""
    entry = await _setup(hass, shi)
    registry = er.async_get(hass)
    keys = ("electric_power", "cfg_heating_mode", "heating_block", "dhw")
    for key in keys:
        domain = BY_KEY[key].platform
        registry.async_update_entity(
            _entity_id(hass, entry, domain, key), disabled_by=er.RegistryEntryDisabler.USER
        )
    await hass.async_block_till_done()
    assert set(keys) <= _polled_keys(entry)
    address = BY_KEY["cfg_heating_mode"].address
    shi.holding[address] = 1
    await _cycle(entry)
    assert entry.runtime_data.data["cfg_heating_mode"] == 1


async def test_enabling_at_runtime_reads_at_once(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.input[10354] = 1
    shi.input[10360] = 1
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    assert "raw_10354" not in coordinator.data
    registry = er.async_get(hass)

    shi.requests.clear()
    registry.async_update_entity(_entity_id(hass, entry, "sensor", "raw_10354"), disabled_by=None)
    registry.async_update_entity(_entity_id(hass, entry, "sensor", "raw_10360"), disabled_by=None)
    await hass.async_block_till_done()

    assert coordinator.data["raw_10354"] == 1  # no poll in between: read by the enablement itself
    assert coordinator.data["raw_10360"] == 1
    assert {"raw_10354", "raw_10360"} <= _polled_keys(entry)
    # the two registers are neighbours with a gap of 5: two reads, not a whole poll
    assert len(shi.requests) <= 2
    # from now on the regular poll reads them (raw inputs: every 4th cycle)
    shi.input[10354] = 0
    shi.requests.clear()
    await _cycle(entry)
    assert _requested(shi, 4, 10354)
    assert coordinator.data["raw_10354"] == 0


async def test_disabling_at_runtime_stops_polling(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    entity_id = _entity_id(hass, entry, "sensor", "outside")
    assert "outside" in _polled_keys(entry)
    registry.async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    await hass.async_block_till_done()
    assert "outside" not in _polled_keys(entry)
    assert "outside" not in {reg.key for block in coordinator._blocks for reg in block.registers}


async def test_failed_read_of_enabled_register_is_left_to_the_poll(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data

    async def broken(*args, **kwargs):
        raise coordinator_module.ModbusCommError("down")

    shi.input[10354] = 1
    coordinator.client.read = broken
    er.async_get(hass).async_update_entity(_entity_id(hass, entry, "sensor", "raw_10354"), disabled_by=None)
    await hass.async_block_till_done()
    assert "raw_10354" in _polled_keys(entry)  # in the plan, value follows with a poll


async def test_fewer_requests_than_polling_everything(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    cycle = max(reg.every for reg in ALL_REGISTERS)

    async def requests_per_poll() -> float:
        shi.requests.clear()
        coordinator._tick = 0
        for _ in range(cycle):
            await coordinator.async_refresh()
        return len(shi.requests) / cycle

    polled = await requests_per_poll()
    coordinator._blocks = plan_blocks(coordinator.registers)  # what polling every register costs
    everything = await requests_per_poll()
    assert polled < everything
