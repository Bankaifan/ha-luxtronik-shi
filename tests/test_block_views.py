"""Operating mode select and on/off switch derived from heating_block (10050) and dhw_block (10051)."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import pathlib
import re
import sys

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik_shi import block_views
from custom_components.luxtronik_shi.const import CONF_SLAVE, DOMAIN, RESTORE_KEYS
from custom_components.luxtronik_shi.modbus_client import ModbusCommError
from custom_components.luxtronik_shi.poll_plan import PLATFORM_SOURCE_KEYS, internal_keys
from custom_components.luxtronik_shi.registers import (
    BLOCK_MODE_DHW,
    BLOCK_MODE_HEATING,
    BLOCK_MODE_HEATING_DHW,
    BLOCK_MODE_KEY,
    BLOCK_MODES,
    BLOCK_POWER_KEY,
)

from .fake_shi import FakeSHI
from .test_entity_semantics import _issue, _logbook, _poll_settings
from .test_integration import _entity_id, _setup

HEATING, DHW = 10050, 10051
ROOT = pathlib.Path(__file__).resolve().parent.parent

# (heating block, hot water block) -> option shown. Written out by hand, not derived from the code under test.
STATES = {
    (0, 0): BLOCK_MODE_HEATING_DHW,
    (0, 1): BLOCK_MODE_HEATING,
    (1, 0): BLOCK_MODE_DHW,
    (1, 1): BLOCK_MODE_DHW,  # three options cannot show "both"; the switch does
}
TARGET = {BLOCK_MODE_HEATING_DHW: (0, 0), BLOCK_MODE_HEATING: (0, 1), BLOCK_MODE_DHW: (1, 0)}


def _start(shi: FakeSHI, state: tuple[int, int]) -> None:
    shi.holding[HEATING], shi.holding[DHW] = state


def _blocks(shi: FakeSHI) -> tuple[int, int]:
    return shi.holding[HEATING], shi.holding[DHW]


def _block_writes(shi: FakeSHI) -> list[tuple[int, int]]:
    return [(address, value) for func, address, value in shi.requests if func == 6]


def _replay(start: tuple[int, int], writes: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """The block state after each write."""
    heating, dhw = start
    states = []
    for address, value in writes:
        if address == HEATING:
            heating = value
        else:
            dhw = value
        states.append((heating, dhw))
    return states


async def _select(hass: HomeAssistant, entry, option: str) -> None:
    entity_id = _entity_id(hass, entry, "select", BLOCK_MODE_KEY)
    await hass.services.async_call(
        "select", "select_option", {"entity_id": entity_id, "option": option}, blocking=True
    )


async def _switch(hass: HomeAssistant, entry, service: str) -> None:
    entity_id = _entity_id(hass, entry, "switch", BLOCK_POWER_KEY)
    await hass.services.async_call("switch", service, {"entity_id": entity_id}, blocking=True)


# ------------------------------------------------------------------ state derivation
@pytest.mark.parametrize(("start", "option"), STATES.items())
async def test_state_is_derived_from_the_two_blocks(
    hass: HomeAssistant, shi: FakeSHI, start: tuple[int, int], option: str
) -> None:
    _start(shi, start)
    entry = await _setup(hass, shi)
    assert hass.states.get(_entity_id(hass, entry, "select", BLOCK_MODE_KEY)).state == option
    switch = hass.states.get(_entity_id(hass, entry, "switch", BLOCK_POWER_KEY))
    assert switch.state == ("off" if start == (1, 1) else "on")
    assert hass.states.get(_entity_id(hass, entry, "select", BLOCK_MODE_KEY)).attributes["options"] == list(
        BLOCK_MODES
    )


async def test_state_follows_the_blocks_on_every_poll(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    select = _entity_id(hass, entry, "select", BLOCK_MODE_KEY)
    switch = _entity_id(hass, entry, "switch", BLOCK_POWER_KEY)
    for state, option in STATES.items():
        _start(shi, state)
        await _poll_settings(hass, entry)
        assert hass.states.get(select).state == option
        assert hass.states.get(switch).state == ("off" if state == (1, 1) else "on")


# ------------------------------------------------------------------ select: every option from every start
@pytest.mark.parametrize("option", BLOCK_MODES)
@pytest.mark.parametrize("start", list(STATES))
async def test_select_option_from_every_start_state(
    hass: HomeAssistant, shi: FakeSHI, start: tuple[int, int], option: str
) -> None:
    _start(shi, start)
    entry = await _setup(hass, shi)
    shi.requests.clear()
    await _select(hass, entry, option)

    target = TARGET[option]
    assert _blocks(shi) == target  # read back from the simulator, not from the entity
    assert hass.states.get(_entity_id(hass, entry, "select", BLOCK_MODE_KEY)).state == option
    writes = _block_writes(shi)
    # both registers are written, with a value in range, nothing else is written
    assert sorted(address for address, _ in writes) == [HEATING, DHW]
    assert {value for _, value in writes} <= {0, 1}
    # releases before blocks
    values = [value for _, value in writes]
    assert values == sorted(values)
    # a half-done change never has more blocks than the start or the end state has
    limit = max(sum(start), sum(target))
    assert all(sum(state) <= limit for state in _replay(start, writes))
    if start != (1, 1):
        assert (1, 1) not in _replay(start, writes) or target == (1, 1)
    # every write is read back through the normal path
    assert (3, HEATING, 1) in shi.requests and (3, DHW, 1) in shi.requests


async def test_select_between_single_blocks_passes_through_nothing_blocked(
    hass: HomeAssistant, shi: FakeSHI
) -> None:
    """heating only <-> hot water only: the block that goes away is released first."""
    _start(shi, (0, 1))
    entry = await _setup(hass, shi)
    shi.requests.clear()
    await _select(hass, entry, BLOCK_MODE_DHW)
    assert _block_writes(shi) == [(DHW, 0), (HEATING, 1)]
    shi.requests.clear()
    await _select(hass, entry, BLOCK_MODE_HEATING)
    assert _block_writes(shi) == [(HEATING, 0), (DHW, 1)]


# ------------------------------------------------------------------ switch
@pytest.mark.parametrize("start", list(STATES))
async def test_switch_turn_off_blocks_both(hass: HomeAssistant, shi: FakeSHI, start: tuple[int, int]) -> None:
    _start(shi, start)
    entry = await _setup(hass, shi)
    shi.requests.clear()
    await _switch(hass, entry, "turn_off")
    assert _blocks(shi) == (1, 1)
    assert hass.states.get(_entity_id(hass, entry, "switch", BLOCK_POWER_KEY)).state == "off"
    writes = _block_writes(shi)
    assert writes == [(DHW, 1), (HEATING, 1)]  # hot water first: heating keeps running if the second write fails
    assert all(sum(state) <= 2 for state in _replay(start, writes))


@pytest.mark.parametrize("start", list(STATES))
async def test_switch_turn_on_releases_hot_water_only_if_both_are_blocked(
    hass: HomeAssistant, shi: FakeSHI, start: tuple[int, int]
) -> None:
    _start(shi, start)
    entry = await _setup(hass, shi)
    shi.requests.clear()
    await _switch(hass, entry, "turn_on")
    if start == (1, 1):
        assert _block_writes(shi) == [(DHW, 0)]
        assert _blocks(shi) == (1, 0)  # the heating block stays as the select left it
        assert hass.states.get(_entity_id(hass, entry, "switch", BLOCK_POWER_KEY)).state == "on"
        assert hass.states.get(_entity_id(hass, entry, "select", BLOCK_MODE_KEY)).state == BLOCK_MODE_DHW
    else:
        assert _block_writes(shi) == []  # any other state: nothing is written
        assert _blocks(shi) == start


async def test_switch_off_then_select_brings_heating_back(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    await _switch(hass, entry, "turn_off")
    await _switch(hass, entry, "turn_on")
    assert _blocks(shi) == (1, 0)
    await _select(hass, entry, BLOCK_MODE_HEATING_DHW)
    assert _blocks(shi) == (0, 0)


# ------------------------------------------------------------------ availability
async def test_unavailable_when_a_block_register_is_missing(hass: HomeAssistant, shi: FakeSHI) -> None:
    del shi.holding[DHW]
    entry = await _setup(hass, shi)
    assert hass.states.get(_entity_id(hass, entry, "select", BLOCK_MODE_KEY)).state == "unavailable"
    assert hass.states.get(_entity_id(hass, entry, "switch", BLOCK_POWER_KEY)).state == "unavailable"
    with pytest.raises(HomeAssistantError) as err:
        block_views.require_state(entry.runtime_data)
    assert err.value.translation_key == "block_state_unknown"
    # the heating block alone still works as the plain switch
    assert hass.states.get(_entity_id(hass, entry, "switch", "heating_block")).state == "off"


async def test_unavailable_while_the_heat_pump_is_unreachable(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)

    async def unreachable(*args, **kwargs):
        raise ModbusCommError("down")

    entry.runtime_data.client.read = unreachable
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(_entity_id(hass, entry, "select", BLOCK_MODE_KEY)).state == "unavailable"
    assert hass.states.get(_entity_id(hass, entry, "switch", BLOCK_POWER_KEY)).state == "unavailable"


# ------------------------------------------------------------------ no extra polling
async def test_block_registers_are_polled_for_other_reasons(hass: HomeAssistant, shi: FakeSHI) -> None:
    assert {"heating_block", "dhw_block"} <= internal_keys()
    assert {block_views.HEATING_BLOCK.key, block_views.DHW_BLOCK.key} <= PLATFORM_SOURCE_KEYS


async def test_the_new_entities_add_no_polled_register(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Disabling the select and the switch changes neither the poll plan nor a single Modbus read."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    with_entities = {reg.key for reg in coordinator.polled_registers}
    shi.requests.clear()
    coordinator._tick = 0
    await coordinator.async_refresh()
    reads_with = sorted(r for r in shi.requests if r[0] in (2, 3, 4))

    registry = er.async_get(hass)
    for platform, key in (("select", BLOCK_MODE_KEY), ("switch", BLOCK_POWER_KEY)):
        registry.async_update_entity(
            _entity_id(hass, entry, platform, key), disabled_by=er.RegistryEntryDisabler.USER
        )
    await hass.async_block_till_done()
    assert {reg.key for reg in coordinator.polled_registers} == with_entities
    shi.requests.clear()
    coordinator._tick = 0
    await coordinator.async_refresh()
    assert sorted(r for r in shi.requests if r[0] in (2, 3, 4)) == reads_with
    assert coordinator.data["heating_block"] == 0 and coordinator.data["dhw_block"] == 0


async def test_a_select_write_reads_back_exactly_the_two_blocks(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    shi.requests.clear()
    await _select(hass, entry, BLOCK_MODE_HEATING)
    assert shi.requests == [(6, HEATING, 0), (3, HEATING, 1), (6, DHW, 1), (3, DHW, 1)]


# ------------------------------------------------------------------ failures between the two writes
async def test_failed_second_write_of_a_change_leaves_nothing_blocked(
    hass: HomeAssistant, shi: FakeSHI
) -> None:
    """heating only -> hot water only: the release is done, the block is not; the result is the safe state."""
    _start(shi, (0, 1))
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    real = coordinator.client.write_register

    async def second_fails(address: int, value: int) -> None:
        if address == HEATING:
            raise ModbusCommError("connection lost")
        await real(address, value)

    coordinator.client.write_register = second_fails
    with pytest.raises(HomeAssistantError) as err:
        await _select(hass, entry, BLOCK_MODE_DHW)
    assert err.value.translation_key == "write_failed"
    assert _blocks(shi) == (0, 0)  # heating and hot water, never "both blocked"
    assert hass.states.get(_entity_id(hass, entry, "select", BLOCK_MODE_KEY)).state == BLOCK_MODE_HEATING_DHW


async def test_failed_second_write_of_turn_off_leaves_heating_running(
    hass: HomeAssistant, shi: FakeSHI
) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    real = coordinator.client.write_register

    async def heating_block_fails(address: int, value: int) -> None:
        if address == HEATING:
            raise ModbusCommError("connection lost")
        await real(address, value)

    coordinator.client.write_register = heating_block_fails
    with pytest.raises(HomeAssistantError):
        await _switch(hass, entry, "turn_off")
    assert _blocks(shi) == (0, 1)  # only hot water is blocked
    assert hass.states.get(_entity_id(hass, entry, "select", BLOCK_MODE_KEY)).state == BLOCK_MODE_HEATING


async def test_failed_first_write_writes_nothing_else(hass: HomeAssistant, shi: FakeSHI) -> None:
    _start(shi, (0, 1))
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data

    async def always_fails(address: int, value: int) -> None:
        raise ModbusCommError("connection lost")

    coordinator.client.write_register = always_fails
    shi.requests.clear()
    with pytest.raises(HomeAssistantError):
        await _select(hass, entry, BLOCK_MODE_DHW)
    assert _block_writes(shi) == []
    assert _blocks(shi) == (0, 1)


async def test_a_write_the_heat_pump_does_not_take_stops_the_sequence(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Error 816 makes the SHI drop writes without an error code: the read-back differs, the rest is not written."""
    _start(shi, (0, 1))
    shi.ignored_writes = {DHW}
    entry = await _setup(hass, shi)
    shi.requests.clear()
    with pytest.raises(HomeAssistantError) as err:
        await _select(hass, entry, BLOCK_MODE_DHW)  # first write: dhw_block = 0, ignored
    assert err.value.translation_key == "block_write_not_taken"
    assert err.value.translation_placeholders == {"key": "dhw_block", "expected": "0", "actual": "1"}
    assert _block_writes(shi) == [(DHW, 0)]  # the heating block was not set
    assert _blocks(shi) == (0, 1)


async def test_a_dropped_last_write_is_an_error_too(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.ignored_writes = {HEATING}
    entry = await _setup(hass, shi)
    with pytest.raises(HomeAssistantError) as err:
        await _switch(hass, entry, "turn_off")
    assert err.value.translation_key == "block_write_not_taken"
    assert _blocks(shi) == (0, 1)


async def test_values_outside_the_range_are_refused_before_any_write(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    shi.requests.clear()
    with pytest.raises(ValueError):
        await block_views.async_write_sequence(
            entry.runtime_data, [(block_views.DHW_BLOCK, 0), (block_views.HEATING_BLOCK, 2)]
        )
    assert _block_writes(shi) == []


def test_every_plan_stays_in_range() -> None:
    plans = [block_views.writes_for_mode(mode) for mode in BLOCK_MODES]
    plans.append(block_views.writes_for_off())
    plans.append(block_views.writes_for_on((1, 1)))
    assert block_views.writes_for_on((0, 0)) == [] and block_views.writes_for_on((1, 0)) == []
    for plan in plans:
        assert {reg.key for reg, _ in plan} <= {"heating_block", "dhw_block"}
        assert {raw for _, raw in plan} <= set(block_views.BLOCK_VALUES) == {0, 1}


# ------------------------------------------------------------------ write path, bookkeeping
async def test_writes_are_our_own_and_not_reported_as_external(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    events = _logbook(hass)
    await _select(hass, entry, BLOCK_MODE_HEATING)
    await _switch(hass, entry, "turn_off")
    await _switch(hass, entry, "turn_on")
    await _poll_settings(hass, entry)
    assert _issue(hass, entry) is None
    assert events == []


async def test_a_change_by_someone_else_is_still_reported(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Control: the bookkeeping above is not simply switched off for the blocks."""
    entry = await _setup(hass, shi)
    await _select(hass, entry, BLOCK_MODE_HEATING)
    shi.holding[HEATING] = 1
    await _poll_settings(hass, entry)
    assert _issue(hass, entry) is not None


async def test_blocks_are_not_restored_after_a_reset(hass: HomeAssistant, shi: FakeSHI) -> None:
    assert not {"heating_block", "dhw_block", BLOCK_MODE_KEY, BLOCK_POWER_KEY} & RESTORE_KEYS
    entry = await _setup(hass, shi)
    await _select(hass, entry, BLOCK_MODE_DHW)
    assert not {"heating_block", "dhw_block"} & set(entry.runtime_data.remembered)


async def test_commands_do_not_interleave(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    real = coordinator.async_write

    async def yielding_write(reg, raw) -> None:
        await real(reg, raw)
        await asyncio.sleep(0.02)  # gives the other command every chance to slip in between two writes

    coordinator.async_write = yielding_write
    shi.requests.clear()
    await asyncio.gather(
        block_views.async_write_sequence(coordinator, block_views.writes_for_mode(BLOCK_MODE_DHW)),
        block_views.async_write_sequence(coordinator, block_views.writes_for_off()),
    )
    writes = _block_writes(shi)
    mode_then_off = [(DHW, 0), (HEATING, 1), (DHW, 1), (HEATING, 1)]
    off_then_mode = [(DHW, 1), (HEATING, 1), (DHW, 0), (HEATING, 1)]
    assert writes in (mode_then_off, off_then_mode)
    assert _blocks(shi) == ((1, 1) if writes == mode_then_off else (1, 0))  # the last command wins


# ------------------------------------------------------------------ registry, devices, enablement
async def test_unique_ids_device_and_default_enablement(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    registry = er.async_get(hass)
    select = registry.async_get(_entity_id(hass, entry, "select", BLOCK_MODE_KEY))
    switch = registry.async_get(_entity_id(hass, entry, "switch", BLOCK_POWER_KEY))
    assert select.unique_id == f"{entry.entry_id}_block_mode"
    assert switch.unique_id == f"{entry.entry_id}_block_power"
    assert select.disabled_by is None and switch.disabled_by is None
    main = registry.async_get(_entity_id(hass, entry, "switch", "heating_block")).device_id
    assert select.device_id is not None
    block_device = registry.async_get(_entity_id(hass, entry, "sensor", "operating_mode")).device_id
    assert select.device_id == switch.device_id == block_device  # the main heat pump device
    assert main != select.device_id  # the heating block itself lives in the heating device


async def test_disabled_for_an_entry_that_existed_before(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WP",
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
    )
    entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create("switch", DOMAIN, f"{entry.entry_id}_heating_block", config_entry=entry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    for platform, key in (("select", BLOCK_MODE_KEY), ("switch", BLOCK_POWER_KEY)):
        entity_id = _entity_id(hass, entry, platform, key)
        assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entity_id) is None


# ------------------------------------------------------------------ translations (German and English)
@pytest.mark.parametrize("lang", ["en", "de"])
def test_translations(lang: str) -> None:
    data = json.loads(
        (ROOT / "custom_components" / "luxtronik_shi" / "translations" / f"{lang}.json").read_text(encoding="utf-8")
    )
    select = data["entity"]["select"][BLOCK_MODE_KEY]
    assert select["name"]
    assert set(select["state"]) == set(BLOCK_MODES)
    assert len(set(select["state"].values())) == 3 and all(select["state"].values())
    assert data["entity"]["switch"][BLOCK_POWER_KEY]["name"]
    for key, placeholders in (("block_write_not_taken", ("{key}", "{expected}", "{actual}")), ("block_state_unknown", ())):
        message = data["exceptions"][key]["message"]
        assert message and all(p in message for p in placeholders), (lang, key)


def test_hot_water_only_is_labelled_for_what_it_is() -> None:
    texts = {
        lang: json.loads(
            (ROOT / "custom_components" / "luxtronik_shi" / "translations" / f"{lang}.json").read_text(
                encoding="utf-8"
            )
        )["entity"]["select"][BLOCK_MODE_KEY]["state"]
        for lang in ("en", "de")
    }
    assert texts["en"] == {
        BLOCK_MODE_HEATING_DHW: "Heating and hot water",
        BLOCK_MODE_HEATING: "Heating only",
        BLOCK_MODE_DHW: "Hot water only",
    }
    assert texts["de"] == {
        BLOCK_MODE_HEATING_DHW: "Heizen und Warmwasser",
        BLOCK_MODE_HEATING: "Nur Heizen",
        BLOCK_MODE_DHW: "Nur Warmwasser",
    }


# ------------------------------------------------------------------ the Heat Pump Optimizer recognises the options
def _fold(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def test_option_keys_fold_to_the_labels_of_the_owners_template_select() -> None:
    """The optimizer matches on letters and digits only: the keys equal the labels the template select used."""
    assert [_fold(option) for option in BLOCK_MODES] == [
        _fold("Heating + DHW"),
        _fold("Heating"),
        _fold("DHW (Hot Water)"),
    ]


def _hpo_pump_mode():
    path = os.environ.get("HPO_REPO")
    if not path:
        pytest.skip("set HPO_REPO to a checkout of the Heat Pump Optimizer to run this check")
    file = pathlib.Path(path) / "custom_components" / "heatpump_optimizer" / "pump_mode.py"
    if not file.exists():
        pytest.skip(f"{file} not found")
    spec = importlib.util.spec_from_file_location("hpo_pump_mode", file)
    module = importlib.util.module_from_spec(spec)
    sys.modules["hpo_pump_mode"] = module
    spec.loader.exec_module(module)
    return module


def test_the_optimizer_maps_the_options_to_the_same_capability_as_the_old_strings() -> None:
    """Needs a checkout of the optimizer (HPO_REPO=...); read only, nothing is imported from it into the tests."""
    pump_mode = _hpo_pump_mode()
    from types import SimpleNamespace

    old = {BLOCK_MODE_HEATING_DHW: "Heating + DHW", BLOCK_MODE_HEATING: "Heating", BLOCK_MODE_DHW: "DHW (Hot Water)"}
    for option, label in old.items():
        new_cap, old_cap = pump_mode.capability(option), pump_mode.capability(label)
        assert new_cap.known and new_cap == old_cap, option
        state = SimpleNamespace(state=option, attributes={"options": list(BLOCK_MODES)})
        validator = pump_mode.validator_for(state)
        assert validator(option), option
    assert pump_mode.capability(BLOCK_MODE_HEATING_DHW).space_heat and pump_mode.capability(BLOCK_MODE_HEATING_DHW).dhw
    assert pump_mode.capability(BLOCK_MODE_HEATING).space_heat and not pump_mode.capability(BLOCK_MODE_HEATING).dhw
    assert not pump_mode.capability(BLOCK_MODE_DHW).space_heat and pump_mode.capability(BLOCK_MODE_DHW).dhw
