"""Only registers with an enabled entity are polled; what the integration uses itself is always read."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.luxtronik_shi import climate, water_heater
from custom_components.luxtronik_shi import coordinator as coordinator_module
from custom_components.luxtronik_shi.const import OUTAGE_WATCH_KEYS, RESTORE_KEYS
from custom_components.luxtronik_shi.coordinator import plan_blocks
from custom_components.luxtronik_shi.poll_plan import PLATFORM_SOURCE_KEYS, derived_consumers, internal_keys
from custom_components.luxtronik_shi.registers import (
    ALL_REGISTERS,
    BY_KEY,
    DERIVED_FLAGS,
    DERIVED_SENSORS,
    DIFFERENCE_SENSORS,
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
    assert {key for key in BY_KEY if key.startswith("cap_")} | {"heating_available", "hot_water_available"} <= keys


def test_derived_sources_follow_their_entities_not_the_internal_keys() -> None:
    consumers = derived_consumers()
    for sensor in DERIVED_SENSORS:
        for source in (sensor.thermal, sensor.electric):
            assert ("sensor", sensor.key) in consumers[source]
    for difference in DIFFERENCE_SENSORS:
        for source in (difference.minuend, difference.subtrahend):
            assert ("sensor", difference.key) in consumers[source]
    for flag in DERIVED_FLAGS:
        assert ("binary_sensor", flag.key) in consumers[flag.source]
    # only what another rule keeps anyway (platform sources) is in the static set
    assert set(consumers) & internal_keys() <= PLATFORM_SOURCE_KEYS


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
    assert "max_flow_temp" not in entry.runtime_data.data
    assert "flow" in polled
    shi.requests.clear()
    await _cycle(entry)
    assert not _requested(shi, 4, 10112)  # maximum flow, disabled by default
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
    shi.input[10112] = 10
    shi.input[10113] = 10
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    assert "max_flow_temp" not in coordinator.data
    registry = er.async_get(hass)

    shi.requests.clear()
    registry.async_update_entity(_entity_id(hass, entry, "sensor", "max_flow_temp"), disabled_by=None)
    registry.async_update_entity(_entity_id(hass, entry, "sensor", "flow_calc_max"), disabled_by=None)
    await hass.async_block_till_done()

    assert coordinator.data["max_flow_temp"] == 1.0  # no poll in between: read by the enablement itself
    assert coordinator.data["flow_calc_max"] == 1.0
    assert {"max_flow_temp", "flow_calc_max"} <= _polled_keys(entry)
    # two neighbouring registers: at most two reads, not a whole poll
    assert len(shi.requests) <= 2
    # from now on the regular poll reads them (every 4th cycle)
    shi.input[10112] = 0
    shi.requests.clear()
    await _cycle(entry)
    assert _requested(shi, 4, 10112)
    assert coordinator.data["max_flow_temp"] == 0


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

    shi.input[10112] = 1
    coordinator.client.read = broken
    er.async_get(hass).async_update_entity(_entity_id(hass, entry, "sensor", "max_flow_temp"), disabled_by=None)
    await hass.async_block_till_done()
    assert "max_flow_temp" in _polled_keys(entry)  # in the plan, value follows with a poll


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


# ------------------------------------------------------------------ sources of calculated entities

_SOURCES_BY_ENTITY = {
    ("binary_sensor", "fault"): ["error_number"],
    ("binary_sensor", "heating_running"): ["heating_status"],
    ("binary_sensor", "dhw_running"): ["hot_water_status"],
    ("binary_sensor", "power_limit_configured"): ["cfg_power_limit_mode"],
    ("sensor", "flow_return_difference"): ["flow"],
    ("sensor", "cop_total"): ["energy_th_total", "energy_el_total"],
}
_REGISTER_ADDRESS = {"error_number": 10201, "heating_status": 10003, "hot_water_status": 10004,
                     "cfg_power_limit_mode": 10040, "flow": 10105, "energy_th_total": 10320, "energy_el_total": 10310}


async def _disable(hass: HomeAssistant, entry, entities) -> None:
    registry = er.async_get(hass)
    for platform, key in entities:
        registry.async_update_entity(
            _entity_id(hass, entry, platform, key), disabled_by=er.RegistryEntryDisabler.USER
        )
    await hass.async_block_till_done()


async def test_default_installation_polls_exactly_the_same_registers(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    assert len(entry.runtime_data.polled_registers) == 79
    assert set(_REGISTER_ADDRESS) <= _polled_keys(entry)


async def test_sources_leave_the_plan_when_their_entities_are_disabled_and_return(
    hass: HomeAssistant, shi: FakeSHI
) -> None:
    entry = await _setup(hass, shi)
    # the calculated entities that use the sources
    users = [
        ("binary_sensor", "fault"), ("binary_sensor", "heating_running"), ("binary_sensor", "dhw_running"),
        ("binary_sensor", "power_limit_configured"), ("sensor", "flow_return_difference"),
        ("sensor", "cop_total"),
    ]
    sources = set(_REGISTER_ADDRESS)
    registry = er.async_get(hass)
    # step 1: only the source entities disabled -> the calculated entities still need them
    await _disable(hass, entry, {(BY_KEY[k].platform, k) for k in sources})
    assert sources <= _polled_keys(entry)
    # step 2: the calculated entities too -> no entity needs them any more
    await _disable(hass, entry, users)
    left = sources & _polled_keys(entry)
    assert left == set()
    shi.requests.clear()
    await _cycle(entry)
    assert not _requested(shi, 4, 10201)  # error_number
    assert not _requested(shi, 4, 10003) and not _requested(shi, 4, 10004)
    assert not _requested(shi, 3, 10040)
    # flow sits between neighbours that are read: the block may bridge it, but it is not planned
    assert "flow" not in {reg.key for block in entry.runtime_data._blocks for reg in block.registers}
    assert "error_number" not in entry.runtime_data.data
    # the fault entity is gone from the plan together with its source, the others still work
    assert _requested(shi, 4, 10100)

    # re-enable the fault entity only: its source is requested again at the next plan
    registry.async_update_entity(_entity_id(hass, entry, "binary_sensor", "fault"), disabled_by=None)
    await hass.async_block_till_done()
    assert "error_number" in _polled_keys(entry)
    assert {"flow", "heating_status", "cfg_power_limit_mode"}.isdisjoint(_polled_keys(entry))
    shi.requests.clear()
    await _cycle(entry)
    assert _requested(shi, 4, 10201)


async def test_one_enabled_consumer_keeps_the_source_in_the_plan(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    # flow: its own sensor is disabled, flow_return_difference still uses it
    await _disable(hass, entry, [("sensor", "flow")])
    assert "flow" in _polled_keys(entry)
    await _disable(hass, entry, [("sensor", "flow_return_difference")])
    assert "flow" not in _polled_keys(entry)
    # error_number: disabled sensor, enabled fault flag
    await _disable(hass, entry, [("sensor", "error_number")])
    assert "error_number" in _polled_keys(entry)


async def test_cop_sources_follow_the_cop_entities(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    cop_entities = [("sensor", "cop"), ("sensor", "cop_heating"), ("sensor", "cop_dhw"), ("sensor", "cop_total")]
    sources = {"compressor_thermal_power", "electric_power", "energy_th_heating", "energy_el_heating",
               "energy_th_dhw", "energy_el_dhw", "energy_th_total", "energy_el_total"}
    await _disable(hass, entry, [(BY_KEY[k].platform, k) for k in sources])
    assert sources <= _polled_keys(entry)  # the COP entities need them
    await _disable(hass, entry, cop_entities)
    assert not sources & _polled_keys(entry)
    er.async_get(hass).async_update_entity(_entity_id(hass, entry, "sensor", "cop_total"), disabled_by=None)
    await hass.async_block_till_done()
    assert {"energy_th_total", "energy_el_total"} <= _polled_keys(entry)
    assert not {"energy_th_heating", "compressor_thermal_power"} & _polled_keys(entry)
