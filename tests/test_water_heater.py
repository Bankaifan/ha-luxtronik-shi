"""Water heater entity for hot water (registers 10005 mode / 10006 setpoint / 10120 temperature) against the simulator."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik_shi.const import DOMAIN

from .fake_shi import FakeSHI
from .test_integration import _entity_id, _setup


async def test_water_heater_new_installation_is_enabled(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "water_heater", "water_heater_dhw")
    assert er.async_get(hass).async_get(entity_id).disabled_by is None
    state = hass.states.get(entity_id)
    assert state.state == "no_influence"  # holding 10005 = 0: the controller uses its own values
    assert state.attributes["temperature"] == 40.0  # holding 10006 = 400
    assert state.attributes["current_temperature"] == 48.2  # input 10120 = 482
    assert state.attributes["min_temp"] == 30
    assert state.attributes["max_temp"] == 75
    assert state.attributes["operation_list"] == ["no_influence", "setpoint", "offset", "level"]
    assert state.attributes["setpoint_active"] is False
    assert state.attributes["effective_target"] == 55.0  # input 10121 = 550
    # lives in the hot water device, next to the existing hot water entities
    registry = er.async_get(hass)
    number = registry.async_get(_entity_id(hass, entry, "number", "cfg_dhw_setpoint"))
    assert registry.async_get(entity_id).device_id == number.device_id


async def test_water_heater_disabled_for_entry_that_existed_before(hass: HomeAssistant, shi: FakeSHI) -> None:
    from homeassistant.const import CONF_HOST, CONF_PORT

    from custom_components.luxtronik_shi.const import CONF_SLAVE

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WP",
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
    )
    entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "number", DOMAIN, f"{entry.entry_id}_cfg_dhw_setpoint", config_entry=entry
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = _entity_id(hass, entry, "water_heater", "water_heater_dhw")
    assert er.async_get(hass).async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(entity_id) is None


async def test_water_heater_set_temperature_writes_and_reads_back(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.holding[10005] = 1  # mode setpoint
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "water_heater", "water_heater_dhw")
    await hass.services.async_call(
        "water_heater", "set_temperature", {"entity_id": entity_id, "temperature": 52.5}, blocking=True
    )
    assert shi.holding_value(10006) == 525
    assert (6, 10006, 525) in shi.requests
    assert hass.states.get(entity_id).attributes["temperature"] == 52.5
    number = _entity_id(hass, entry, "number", "cfg_dhw_setpoint")
    assert hass.states.get(number).state == "52.5"
    assert shi.holding_value(10005) == 1  # mode untouched


@pytest.mark.parametrize("value", [29.5, 75.5, 0, 100, -5])
async def test_water_heater_set_temperature_out_of_range_is_rejected(
    hass: HomeAssistant, shi: FakeSHI, value: float
) -> None:
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "water_heater", "water_heater_dhw")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "water_heater", "set_temperature", {"entity_id": entity_id, "temperature": value}, blocking=True
        )
    assert shi.holding_value(10006) == 400
    assert not [r for r in shi.requests if r[0] == 6]


@pytest.mark.parametrize(("value", "expected"), [(30, 300), (75, 750)])
async def test_water_heater_set_temperature_limits_are_accepted(
    hass: HomeAssistant, shi: FakeSHI, value: float, expected: int
) -> None:
    shi.holding[10005] = 1
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "water_heater", "water_heater_dhw")
    await hass.services.async_call(
        "water_heater", "set_temperature", {"entity_id": entity_id, "temperature": value}, blocking=True
    )
    assert shi.holding_value(10006) == expected
    assert hass.states.get(entity_id).attributes["temperature"] == value


@pytest.mark.parametrize(
    ("mode", "raw", "option"),
    [("setpoint", 1, "setpoint"), ("offset", 2, "offset"), ("level", 3, "level"), ("no_influence", 0, "off")],
)
async def test_water_heater_operation_mode_writes_mode_register(
    hass: HomeAssistant, shi: FakeSHI, mode: str, raw: int, option: str
) -> None:
    shi.holding[10005] = 2 if raw != 2 else 1
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "water_heater", "water_heater_dhw")
    await hass.services.async_call(
        "water_heater", "set_operation_mode", {"entity_id": entity_id, "operation_mode": mode}, blocking=True
    )
    assert shi.holding_value(10005) == raw
    assert (6, 10005, raw) in shi.requests
    assert hass.states.get(entity_id).state == mode
    select = _entity_id(hass, entry, "select", "cfg_dhw_mode")
    assert hass.states.get(select).state == option  # select option keys are unchanged
    assert shi.holding_value(10006) == 400  # setpoint untouched


async def test_water_heater_unknown_operation_mode_is_rejected(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "water_heater", "water_heater_dhw")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "water_heater", "set_operation_mode", {"entity_id": entity_id, "operation_mode": "turbo"}, blocking=True
        )
    assert not [r for r in shi.requests if r[0] == 6]
