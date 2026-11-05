"""Climate entity for the heating circuit (registers 10000 mode / 10001 setpoint) against the simulator."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik_shi.const import DOMAIN

from .fake_shi import FakeSHI
from .test_integration import _entity_id, _setup


async def test_climate_new_installation_is_enabled(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "climate", "climate_heating")
    registry_entry = er.async_get(hass).async_get(entity_id)
    assert registry_entry.disabled_by is None
    state = hass.states.get(entity_id)
    assert state.state == "off"  # holding 10000 = 0 (off)
    assert state.attributes["temperature"] == 22.0  # holding 10001 = 220
    assert state.attributes["current_temperature"] == 35.1  # input flow, 10105 = 351
    assert state.attributes["min_temp"] == 10
    assert state.attributes["max_temp"] == 70
    assert state.attributes["controller_mode"] == "off"
    assert set(state.attributes["hvac_modes"]) == {"off", "heat"}


async def test_climate_disabled_for_entry_that_existed_before(hass: HomeAssistant, shi: FakeSHI) -> None:
    from homeassistant.const import CONF_HOST, CONF_PORT

    from custom_components.luxtronik_shi.const import CONF_SLAVE

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WP",
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
    )
    entry.add_to_hass(hass)
    # An entity of an earlier version is already in the registry; the climate entity is new.
    er.async_get(hass).async_get_or_create(
        "number", DOMAIN, f"{entry.entry_id}_cfg_heating_setpoint", config_entry=entry
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = _entity_id(hass, entry, "climate", "climate_heating")
    assert er.async_get(hass).async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(entity_id) is None


async def test_climate_set_temperature_writes_and_reads_back(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "climate", "climate_heating")
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": entity_id, "temperature": 35.5}, blocking=True
    )
    assert shi.holding_value(10001) == 355
    assert (6, 10001, 355) in shi.requests
    assert hass.states.get(entity_id).attributes["temperature"] == 35.5
    # the number entity shows the same read-back value
    number = _entity_id(hass, entry, "number", "cfg_heating_setpoint")
    assert hass.states.get(number).state == "35.5"
    # the mode register was not touched
    assert shi.holding_value(10000) == 0


@pytest.mark.parametrize("value", [9.5, 70.5, 0, 100, -5])
async def test_climate_set_temperature_out_of_range_is_rejected(
    hass: HomeAssistant, shi: FakeSHI, value: float
) -> None:
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "climate", "climate_heating")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "climate", "set_temperature", {"entity_id": entity_id, "temperature": value}, blocking=True
        )
    assert shi.holding_value(10001) == 220
    assert not [r for r in shi.requests if r[0] == 6]


@pytest.mark.parametrize(("value", "expected"), [(10, 100), (70, 700)])
async def test_climate_set_temperature_limits_are_accepted(
    hass: HomeAssistant, shi: FakeSHI, value: float, expected: int
) -> None:
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "climate", "climate_heating")
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": entity_id, "temperature": value}, blocking=True
    )
    assert shi.holding_value(10001) == expected
    assert hass.states.get(entity_id).attributes["temperature"] == value


async def test_climate_hvac_mode_writes_mode_register(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "climate", "climate_heating")

    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "heat"}, blocking=True
    )
    assert shi.holding_value(10000) == 1  # "setpoint"
    state = hass.states.get(entity_id)
    assert state.state == "heat"
    assert state.attributes["controller_mode"] == "setpoint"
    select = _entity_id(hass, entry, "select", "cfg_heating_mode")
    assert hass.states.get(select).state == "setpoint"

    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": entity_id, "hvac_mode": "off"}, blocking=True
    )
    assert shi.holding_value(10000) == 0
    assert hass.states.get(entity_id).state == "off"


async def test_climate_other_controller_modes_count_as_heat(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.holding[10000] = 3  # "level", set on the controller itself
    entry = await _setup(hass, shi)
    state = hass.states.get(_entity_id(hass, entry, "climate", "climate_heating"))
    assert state.state == "heat"
    assert state.attributes["controller_mode"] == "level"
