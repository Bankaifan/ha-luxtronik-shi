"""Calculated entities: flow-return difference, overall COP, fault, defrost, running flags, power limit mode.

They are derived from registers that are polled anyway: no register of their own, no additional poll.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.luxtronik_shi.poll_plan import internal_keys
from custom_components.luxtronik_shi.registers import (
    ALL_REGISTERS,
    BY_KEY,
    DERIVED_FLAGS,
    DIFFERENCE_SENSORS,
    FUNCTION_STATUS,
    active_registers,
)

from .fake_shi import FakeSHI
from .test_integration import _entity_id, _setup


def _state(hass: HomeAssistant, entry, platform: str, key: str) -> str:
    return hass.states.get(_entity_id(hass, entry, platform, key)).state


async def _push(hass: HomeAssistant, entry, **values) -> None:
    """Replace values in the coordinator data and notify the entities (a missing value is ``None``)."""
    coordinator = entry.runtime_data
    coordinator.async_set_updated_data({**coordinator.data, **values})
    await hass.async_block_till_done()


# ------------------------------------------------------------------ no additional polling


def test_new_entities_have_no_register_of_their_own() -> None:
    new = {s.key for s in DIFFERENCE_SENSORS} | {f.key for f in DERIVED_FLAGS} | {"cop_total"}
    assert new.isdisjoint({reg.key for reg in ALL_REGISTERS})


def test_sources_are_existing_registers_that_a_default_installation_polls_anyway() -> None:
    sources = {f.source for f in DERIVED_FLAGS}
    for sensor in DIFFERENCE_SENSORS:
        sources |= {sensor.minuend, sensor.subtrahend}
    sources |= {BY_KEY["energy_th_total"].key, BY_KEY["energy_el_total"].key}
    assert sources <= set(BY_KEY)
    default_polled = {reg.key for reg in active_registers(None) if reg.enabled_default}
    # nothing is added to the poll plan of a default installation ...
    assert sources <= default_polled
    # ... and the sources stay in the plan if their own entity is disabled
    assert sources <= internal_keys()


async def test_the_poll_reads_no_register_beyond_the_registers(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    polled = {reg.key for reg in entry.runtime_data.polled_registers}
    assert polled <= set(BY_KEY)


# ------------------------------------------------------------------ flow-return difference


async def test_difference_value_unit_and_unavailable(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    # simulator: flow 35.1, return 28.5
    assert float(_state(hass, entry, "sensor", "flow_return_difference")) == pytest.approx(6.6)
    state = hass.states.get(_entity_id(hass, entry, "sensor", "flow_return_difference"))
    assert state.attributes["unit_of_measurement"] == "K"
    assert "device_class" not in state.attributes  # no conversion like an absolute temperature
    assert state.attributes["state_class"] == "measurement"
    await _push(hass, entry, flow=20.0, **{"return": 25.0})
    assert float(_state(hass, entry, "sensor", "flow_return_difference")) == pytest.approx(-5.0)  # not clamped
    await _push(hass, entry, flow=None)
    assert _state(hass, entry, "sensor", "flow_return_difference") == "unavailable"
    await _push(hass, entry, flow=30.0, **{"return": None})
    assert _state(hass, entry, "sensor", "flow_return_difference") == "unavailable"


# ------------------------------------------------------------------ overall COP of all modes


async def test_cop_total_value_and_unknown(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    # the simulator's counters read 6553.8 kWh electric and 20.0 kWh thermal (a ratio of 0.003)
    await _push(hass, entry, energy_th_total=21000.0, energy_el_total=7000.0)
    assert float(_state(hass, entry, "sensor", "cop_total")) == pytest.approx(3.0)
    await _push(hass, entry, energy_th_total=21000.0, energy_el_total=0.0)  # no electric energy
    assert _state(hass, entry, "sensor", "cop_total") == "unknown"
    await _push(hass, entry, energy_th_total=None, energy_el_total=7000.0)
    assert _state(hass, entry, "sensor", "cop_total") == "unknown"
    await _push(hass, entry, energy_th_total=21000.0, energy_el_total=7000.0)
    await _push(hass, entry, energy_th_total=20000.0, energy_el_total=7100.0)  # thermal counter went backwards
    assert _state(hass, entry, "sensor", "cop_total") == "unknown"


async def test_cop_total_is_in_the_main_device(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    registry = er.async_get(hass)
    device = lambda key: registry.async_get(_entity_id(hass, entry, "sensor", key)).device_id  # noqa: E731
    assert device("cop_total") == device("electric_power") == device("cop")
    assert device("cop_total") != device("cop_heating")


# ------------------------------------------------------------------ flags


async def test_fault(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    assert _state(hass, entry, "binary_sensor", "fault") == "off"
    await _push(hass, entry, error_number=701)
    assert _state(hass, entry, "binary_sensor", "fault") == "on"
    state = hass.states.get(_entity_id(hass, entry, "binary_sensor", "fault"))
    assert state.attributes["device_class"] == "problem"
    await _push(hass, entry, error_number=None)
    assert _state(hass, entry, "binary_sensor", "fault") == "unavailable"


async def test_defrost(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    assert _state(hass, entry, "binary_sensor", "defrost") == "off"  # simulator: hot water
    await _push(hass, entry, operating_mode=BY_KEY["operating_mode"].options.index("defrost"))
    assert _state(hass, entry, "binary_sensor", "defrost") == "on"
    await _push(hass, entry, operating_mode=BY_KEY["operating_mode"].options.index("heating"))
    assert _state(hass, entry, "binary_sensor", "defrost") == "off"
    await _push(hass, entry, operating_mode=None)
    assert _state(hass, entry, "binary_sensor", "defrost") == "unavailable"


@pytest.mark.parametrize(("flag", "source"), [("heating_running", "heating_status"), ("dhw_running", "hot_water_status")])
async def test_running_flags_only_for_running(hass: HomeAssistant, shi: FakeSHI, flag: str, source: str) -> None:
    entry = await _setup(hass, shi)
    for index, option in enumerate(FUNCTION_STATUS[:4]):
        await _push(hass, entry, **{source: index})
        assert _state(hass, entry, "binary_sensor", flag) == ("on" if option == "running" else "off"), option
    await _push(hass, entry, **{source: 3})
    assert _state(hass, entry, "binary_sensor", flag) == "on"  # value 3 as in the status enumeration
    await _push(hass, entry, **{source: 9})  # unknown_9
    assert _state(hass, entry, "binary_sensor", flag) == "off"
    await _push(hass, entry, **{source: None})
    assert _state(hass, entry, "binary_sensor", flag) == "unavailable"


async def test_running_flags_live_in_their_devices(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    registry = er.async_get(hass)
    device = lambda key: registry.async_get(_entity_id(hass, entry, "binary_sensor", key)).device_id  # noqa: E731
    sensor_device = lambda key: registry.async_get(_entity_id(hass, entry, "sensor", key)).device_id  # noqa: E731
    assert device("heating_running") == sensor_device("heating_status")
    assert device("dhw_running") == sensor_device("hot_water_status")
    assert device("fault") == device("defrost") == sensor_device("error_number")


async def test_power_limit_flag_reports_the_configured_mode(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    modes = BY_KEY["cfg_power_limit_mode"].options
    assert _state(hass, entry, "binary_sensor", "power_limit_configured") == "off"  # simulator: none
    for option, expected in (("none", "off"), ("soft", "on"), ("hard", "on")):
        await _push(hass, entry, cfg_power_limit_mode=modes.index(option))
        assert _state(hass, entry, "binary_sensor", "power_limit_configured") == expected, option
    await _push(hass, entry, cfg_power_limit_mode=None)
    assert _state(hass, entry, "binary_sensor", "power_limit_configured") == "unavailable"


async def test_unique_ids_follow_the_scheme(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    registry = er.async_get(hass)
    for key in ("flow_return_difference", "cop_total"):
        assert registry.async_get_entity_id("sensor", "luxtronik_shi", f"{entry.entry_id}_{key}")
    for flag in DERIVED_FLAGS:
        assert registry.async_get_entity_id("binary_sensor", "luxtronik_shi", f"{entry.entry_id}_{flag.key}")
