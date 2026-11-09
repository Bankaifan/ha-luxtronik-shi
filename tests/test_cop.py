"""Calculated COP sensors: instantaneous (power) and overall (energy counters), against the simulator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.luxtronik_shi import sensor as sensor_module
from custom_components.luxtronik_shi.registers import (
    COP_MAX_PLAUSIBLE,
    COP_MIN_ELECTRIC_ENERGY_KWH,
    WindowedCop,
    overall_cop,
)

from .fake_shi import FakeSHI
from .test_integration import _entity_id, _setup


class Clock:
    """Controllable replacement for dt_util.utcnow, which stamps the COP samples in the sensor module.

    The pytest freezer is not used: it also freezes the monotonic clock that asyncio and pymodbus rely on, and a
    real connection then never gives up its retry loop (pymodbus 3.9 hangs; see tests/test_repairs.py).
    """

    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

    def tick(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(sensor_module.dt_util, "utcnow", fake)
    return fake


async def _refresh(hass: HomeAssistant, entry) -> None:
    # energy counters are polled every 2nd cycle: two refreshes read everything at least once
    for _ in range(2):
        await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, entry, key: str) -> str:
    return hass.states.get(_entity_id(hass, entry, "sensor", key)).state


# ------------------------------------------------------------------ pure functions


def _run(cop: WindowedCop, samples, start=0.0, step=30.0):
    """Feed (thermal W, electric W) samples at a fixed step and return the list of results."""
    return [cop.add(start + i * step, th, el) for i, (th, el) in enumerate(samples)]


def test_window_steady_state_is_the_energy_ratio() -> None:
    result = _run(WindowedCop(), [(4800, 1200)] * 20)
    assert result[-1] == pytest.approx(4.0)


def test_window_hides_the_start_spike() -> None:
    # Measured pattern after a compressor start: thermal power is already high while electric power is small.
    start = [(8000, 1000), (6600, 1500), (5800, 1800)]
    steady = [(5000, 1200)] * 20
    # the old per-sample quotient showed 8.0 here
    assert _run(WindowedCop(), start + steady)[0] is None
    result = _run(WindowedCop(), start + steady)
    assert all(v is None or v <= 6.0 for v in result)
    assert result[-1] == pytest.approx(5000 / 1200, rel=0.02)


def test_window_unknown_until_enough_energy() -> None:
    result = _run(WindowedCop(), [(4800, 1200)] * 10)
    # 1200 W for 30 s are 10 Wh: 60 Wh need 6 intervals, i.e. the 7th sample
    assert result[:6] == [None] * 6
    assert result[6] == pytest.approx(4.0)


def test_window_smooths_the_100_w_resolution() -> None:
    # electric power flips between 1100 W and 1200 W, thermal between 4700 W and 4800 W
    samples = [(4700, 1100), (4800, 1200)] * 15
    result = [v for v in _run(WindowedCop(), samples) if v is not None]
    assert max(result) - min(result) < 0.05


def test_window_forgets_after_the_window_and_stays_unknown_when_idle() -> None:
    cop = WindowedCop()
    _run(cop, [(4800, 1200)] * 20)
    idle = _run(cop, [(0, 0)] * 40, start=600.0)
    assert idle[0] is not None  # a stopped compressor does not blank the value at once
    assert idle[-1] is None  # but 10 minutes later the window is empty



def test_window_does_not_bridge_a_gap() -> None:
    # samples 200 s apart (failed polls in between): no interval is interpolated, nothing to divide
    assert _run(WindowedCop(), [(4800, 1200)] * 20, step=200.0)[-1] is None


@pytest.mark.parametrize("bad", [(None, 500), (1200, None), (None, None)])
def test_window_missing_value_breaks_continuity(bad) -> None:
    cop = WindowedCop()
    _run(cop, [(4800, 1200)] * 20)
    cop.add(600.0, *bad)
    # the sample after the missing one starts a new chain: no interval over the hole (570 s -> 630 s)
    cop.add(630.0, 9600, 1200)
    value = cop.add(660.0, 4800, 1200)
    # 18 segments of 40 Wh / 10 Wh (ratio 4) from 60 s to 570 s plus 630 s -> 660 s: 60 Wh / 10 Wh
    assert value == pytest.approx((18 * 40 + 60) / (18 * 10 + 10))


def test_window_defrost_inside_a_run_counts() -> None:
    cop = WindowedCop()
    run = [(4800, 1200)] * 16 + [(-3000, 1000)] * 4 + [(4800, 1200)] * 4
    plain = _run(WindowedCop(), [(4800, 1200)] * 24)[-1]
    with_defrost = _run(cop, run)[-1]
    assert with_defrost < plain


def test_window_long_defrost_is_unknown() -> None:
    result = _run(WindowedCop(), [(-3000, 1000)] * 24)
    assert result[-1] is None  # net thermal energy negative


def test_window_upper_limit() -> None:
    assert _run(WindowedCop(), [(COP_MAX_PLAUSIBLE * 1000 + 1000, 1000)] * 24)[-1] is None
    assert _run(WindowedCop(), [(COP_MAX_PLAUSIBLE * 1000, 1000)] * 24)[-1] == pytest.approx(COP_MAX_PLAUSIBLE)


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


async def _run_entity(hass, entry, clock, polls: int) -> None:
    for _ in range(polls):
        clock.tick(30)
        await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_cop_entities_with_simulated_values(hass: HomeAssistant, shi: FakeSHI, clock) -> None:
    entry = await _setup(hass, shi)
    # 10300 = 12 -> 1200 W thermal, 10301 = 5 -> 500 W electric; the window needs 60 Wh = 7.2 minutes at 500 W
    assert _state(hass, entry, "cop") == "unknown"
    await _run_entity(hass, entry, clock, 30)
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


async def test_cop_entity_ignores_a_start_spike_and_goes_unknown_when_idle(
    hass: HomeAssistant, shi: FakeSHI, clock
) -> None:
    shi.input[10300] = 0
    shi.input[10301] = 0
    entry = await _setup(hass, shi)
    assert _state(hass, entry, "cop") == "unknown"
    shi.input[10300] = 80  # 8000 W thermal while electric power is still 1000 W: per-sample COP 8.0
    shi.input[10301] = 10
    await _run_entity(hass, entry, clock, 1)
    assert _state(hass, entry, "cop") == "unknown"
    shi.input[10300] = 50
    shi.input[10301] = 12
    for _ in range(20):
        await _run_entity(hass, entry, clock, 1)
        state = _state(hass, entry, "cop")
        assert state == "unknown" or float(state) < 6.0
    assert float(_state(hass, entry, "cop")) == pytest.approx(5000 / 1200, rel=0.05)
    shi.input[10300] = 0
    shi.input[10301] = 0
    await _run_entity(hass, entry, clock, 40)  # 20 minutes of standstill
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
