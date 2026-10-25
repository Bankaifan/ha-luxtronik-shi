"""End-to-end tests: config flow, entities and writes against the simulated heat pump."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik_shi.const import CONF_SLAVE, DOMAIN

from .fake_shi import FakeSHI, free_port


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


def _entity_id(hass: HomeAssistant, entry: MockConfigEntry, platform: str, key: str) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id, f"{platform}.{key} fehlt"
    return entity_id


async def test_config_flow(hass: HomeAssistant, shi: FakeSHI) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Wärmepumpe", CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Wärmepumpe"
    assert result["data"] == {CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1}
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED


async def test_config_flow_cannot_connect(hass: HomeAssistant, socket_enabled) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "WP", CONF_HOST: "127.0.0.1", CONF_PORT: free_port(), CONF_SLAVE: 1},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_config_flow_duplicate(hass: HomeAssistant, shi: FakeSHI) -> None:
    await _setup(hass, shi)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "WP", CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_values(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    assert entry.state is ConfigEntryState.LOADED

    def state(platform: str, key: str) -> str:
        return hass.states.get(_entity_id(hass, entry, platform, key)).state

    assert state("sensor", "return") == "28.5"
    assert state("sensor", "flow") == "35.1"
    assert state("sensor", "outside") == "-2.0"
    assert state("sensor", "dhw") == "48.2"
    assert state("sensor", "dhw_target") == "55.0"
    assert state("sensor", "electric_power") == "500"
    assert state("sensor", "energy_el_total") == "6553.8"
    assert state("sensor", "hours_hp") == "1234"
    assert state("sensor", "error_number") == "0"
    assert state("number", "cfg_heating_setpoint") == "22.0"
    assert state("number", "cfg_heating_offset") == "0.0"
    assert state("number", "cfg_dhw_setpoint") == "40.0"
    assert state("select", "cfg_heating_mode") == "off"
    assert state("sensor", "operating_mode") == "hot_water"
    assert state("sensor", "mk1_flow") == "30.0"
    assert state("sensor", "heating_limit") == "22.8"
    assert state("sensor", "buffer_type") == "separation"
    assert state("binary_sensor", "cooling_release") == "on"
    assert state("binary_sensor", "compressor_1") == "off"  # status mask 4 = ZWE1 only
    assert state("binary_sensor", "aux_heater_1") == "on"
    assert state("switch", "circulation") == "off"
    assert state("binary_sensor", "cap_heating") == "on"
    assert state("binary_sensor", "cap_cooling") == "off"
    assert state("binary_sensor", "online") == "on"
    assert state("switch", "dhw_block") == "off"

    # raw diagnostic values are registered but disabled by default
    registry = er.async_get(hass)
    raw = registry.async_get(_entity_id(hass, entry, "sensor", "raw_10109"))
    assert raw.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_heating_offset_write(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "number", "cfg_heating_offset")

    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": -0.5}, blocking=True
    )
    assert shi.holding_value(10002) == 65531  # two's complement of -5
    assert hass.states.get(entity_id).state == "-0.5"

    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": 1.5}, blocking=True
    )
    assert shi.holding_value(10002) == 15
    assert hass.states.get(entity_id).state == "1.5"


async def test_switch_write(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "switch", "heating_block")

    await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
    assert shi.holding_value(10050) == 1
    assert hass.states.get(entity_id).state == "on"

    await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
    assert shi.holding_value(10050) == 0
    assert hass.states.get(entity_id).state == "off"


async def test_missing_register_inside_block(hass: HomeAssistant, shi: FakeSHI) -> None:
    """A register the device does not have must not break its neighbours."""
    del shi.input[10124]  # lies inside the block 10100..10124
    del shi.input[10113]
    del shi.input[10107]
    entry = await _setup(hass, shi)
    assert entry.state is ConfigEntryState.LOADED

    assert hass.states.get(_entity_id(hass, entry, "sensor", "dhw")).state == "48.2"
    assert hass.states.get(_entity_id(hass, entry, "sensor", "return")).state == "28.5"
    # the missing raw values are just unknown, the block was read register by register
    data = entry.runtime_data.data
    assert data["raw_10113"] is None
    assert data["dhw_limit"] is None
    assert data["heating_limit"] is None
    assert data["raw_10112"] == 7
    assert any(block.split for block in entry.runtime_data._blocks)


async def test_unload(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retry_when_offline(hass: HomeAssistant, socket_enabled) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WP",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: free_port(), CONF_SLAVE: 1},
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_options_flow_reloads(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    assert entry.runtime_data.update_interval.total_seconds() == 30

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"scan_interval": 60})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.update_interval.total_seconds() == 60


async def test_reconfigure(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_number_and_select_write(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)

    number = _entity_id(hass, entry, "number", "cfg_dhw_setpoint")
    await hass.services.async_call("number", "set_value", {"entity_id": number, "value": 52.5}, blocking=True)
    assert shi.holding_value(10006) == 525
    assert hass.states.get(number).state == "52.5"

    offset = _entity_id(hass, entry, "number", "cfg_mk1_offset")
    await hass.services.async_call("number", "set_value", {"entity_id": offset, "value": -2}, blocking=True)
    assert shi.holding_value(10012) == 65516
    assert hass.states.get(offset).state == "-2.0"

    limit = _entity_id(hass, entry, "number", "cfg_power_limit")
    await hass.services.async_call("number", "set_value", {"entity_id": limit, "value": 2.5}, blocking=True)
    assert shi.holding_value(10041) == 25

    select = _entity_id(hass, entry, "select", "cfg_power_limit_mode")
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select, "option": "soft"}, blocking=True
    )
    assert shi.holding_value(10040) == 1
    assert hass.states.get(select).state == "soft"

    mode = _entity_id(hass, entry, "select", "cfg_dhw_mode")
    await hass.services.async_call(
        "select", "select_option", {"entity_id": mode, "option": "setpoint"}, blocking=True
    )
    assert shi.holding_value(10005) == 1


async def test_circulation_switch(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "switch", "circulation")
    await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
    assert shi.holding_value(10070) == 1
    assert hass.states.get(entity_id).state == "on"
