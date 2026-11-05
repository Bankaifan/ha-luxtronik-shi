"""Calculated COP sensors: instantaneous (power) and overall (energy counters), against the simulator."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.luxtronik_shi.registers import (
    COP_MAX_PLAUSIBLE,
    COP_MIN_ELECTRIC_ENERGY_KWH,
    COP_MIN_ELECTRIC_POWER_W,
    instantaneous_cop,
    overall_cop,
)

from .fake_shi import FakeSHI
from .test_integration import _entity_id, _setup


async def _refresh(hass: HomeAssistant, entry) -> None:
    # energy counters are polled every 2nd cycle: two refreshes read everything at least once
    for _ in range(2):
        await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, entry, key: str) -> str:
    return hass.states.get(_entity_id(hass, entry, "sensor", key)).state


# ------------------------------------------------------------------ pure functions


def test_instantaneous_normal_value() -> None:
    assert instantaneous_cop(1200, 500) == pytest.approx(2.4)


@pytest.mark.parametrize(
    ("thermal", "electric"),
    [
        (None, 500),
        (1200, None),
        (1200, 0),  # division by zero
        (1200, COP_MIN_ELECTRIC_POWER_W - 100),  # below threshold
        (-800, 500),  # defrost: negative thermal power
        (0, 500),
        (1200 * 100, 500),  # implausibly high
    ],
)
def test_instantaneous_unknown(thermal, electric) -> None:
    assert instantaneous_cop(thermal, electric) is None


def test_instantaneous_upper_limit() -> None:
    assert instantaneous_cop(COP_MAX_PLAUSIBLE * 1000, 1000) == pytest.approx(COP_MAX_PLAUSIBLE)
    assert instantaneous_cop(COP_MAX_PLAUSIBLE * 1000 + 1, 1000) is None


def test_overall_normal_value() -> None:
    assert overall_cop(15.0, 10.0) == pytest.approx(1.5)
    assert overall_cop(30.0, 10.0, previous=(15.0, 10.0)) == pytest.approx(3.0)
    assert overall_cop(30.0, 10.0, previous=(30.0, 10.0)) == pytest.approx(3.0)  # idle: counters unchanged


@pytest.mark.parametrize(
    ("thermal", "electric", "previous"),
    [
        (None, 10.0, None),
        (15.0, None, None),
        (15.0, 0.0, None),  # division by zero
        (0.0, 10.0, None),
        (15.0, COP_MIN_ELECTRIC_ENERGY_KWH / 2, None),  # too little electric energy
        (500.0, 10.0, None),  # implausible
        (15.0, 10.0, (16.0, 10.0)),  # thermal counter went backwards
        (15.0, 10.0, (15.0, 11.0)),  # electric counter went backwards
    ],
)
def test_overall_unknown(thermal, electric, previous) -> None:
    assert overall_cop(thermal, electric, previous) is None


# ------------------------------------------------------------------ entities


async def test_cop_entities_with_simulated_values(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    # 10300 = 12 -> 1200 W thermal, 10301 = 5 -> 500 W electric
    assert float(_state(hass, entry, "cop")) == pytest.approx(2.4)
    # heating: 15.0 kWh thermal / 10.0 kWh electric; hot water: 7.0 / 5.0
    assert float(_state(hass, entry, "cop_heating")) == pytest.approx(1.5)
    assert float(_state(hass, entry, "cop_dhw")) == pytest.approx(1.4)


async def test_cop_entities_live_in_the_expected_devices(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    registry = er.async_get(hass)
    device = lambda platform, key: registry.async_get(_entity_id(hass, entry, platform, key)).device_id  # noqa: E731
    assert device("sensor", "cop") == device("sensor", "electric_power")  # main device
    assert device("sensor", "cop_heating") == device("sensor", "energy_el_heating")  # Heating
    assert device("sensor", "cop_dhw") == device("sensor", "energy_el_dhw")  # Hot water
    assert device("sensor", "cop_heating") != device("sensor", "cop_dhw")


def test_cop_sources_are_existing_registers_and_add_none() -> None:
    from custom_components.luxtronik_shi.registers import BY_KEY, DERIVED_SENSORS

    for sensor in DERIVED_SENSORS:
        assert sensor.key not in BY_KEY  # calculated, nothing of its own is read
        assert sensor.thermal in BY_KEY
        assert sensor.electric in BY_KEY


async def test_instantaneous_cop_unknown_without_electric_power(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    shi.input[10301] = 0  # compressor off
    await _refresh(hass, entry)
    assert _state(hass, entry, "cop") == "unknown"
    shi.input[10301] = 1  # 100 W, below the threshold
    await _refresh(hass, entry)
    assert _state(hass, entry, "cop") == "unknown"
    shi.input[10301] = 5
    await _refresh(hass, entry)
    assert float(_state(hass, entry, "cop")) == pytest.approx(2.4)


async def test_instantaneous_cop_unknown_during_defrost(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    shi.input[10300] = 0xFFF8  # -800 W (int16)
    await _refresh(hass, entry)
    assert _state(hass, entry, "cop") == "unknown"


async def test_overall_cop_unknown_for_zero_or_reset_counters(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    shi.input[10313] = 0  # electric heating counter 0 kWh
    await _refresh(hass, entry)
    assert _state(hass, entry, "cop_heating") == "unknown"
    assert float(_state(hass, entry, "cop_dhw")) == pytest.approx(1.4)  # hot water not affected
    shi.input[10313] = 100
    shi.input[10323] = 300  # 30 kWh thermal
    await _refresh(hass, entry)
    assert float(_state(hass, entry, "cop_heating")) == pytest.approx(3.0)
    shi.input[10323] = 100  # thermal counter went backwards (reset): unknown for this reading
    await _refresh(hass, entry)
    assert _state(hass, entry, "cop_heating") == "unknown"
    await _refresh(hass, entry)  # next reading builds on the new baseline
    assert float(_state(hass, entry, "cop_heating")) == pytest.approx(1.0)
