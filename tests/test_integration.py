"""End-to-end tests: config flow, entities and writes against the simulated heat pump."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik_shi.const import CONF_SLAVE, DOMAIN
from custom_components.luxtronik_shi.registers import FEATURES, active_registers

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
    # Second step: equipment, pre-filled from the capability flags (fake = reference: only mixing circuit 1)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "equipment"
    defaults = {str(k): k.default() for k in result["data_schema"].schema}
    assert defaults == {
        "mk1": True, "mk2": False, "mk3": False, "cooling": False, "pool": False, "room_unit": False, "solar": False,
    }

    result = await hass.config_entries.flow.async_configure(result["flow_id"], defaults)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Wärmepumpe"
    assert result["data"] == {CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1}
    assert result["options"] == {"scan_interval": 30, "features": ["mk1"]}
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is ConfigEntryState.LOADED

    registry = er.async_get(hass)
    keys = {e.unique_id.removeprefix(f"{entry.entry_id}_") for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    assert {"flow", "cfg_mk1_setpoint", "heating_block", "dhw_block", "circulation"} <= keys
    assert not keys & {"pool_block", "cooling_block", "mk2_flow", "cfg_mk1_cool_mode", "room"}


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
    assert state("select", "cfg_heating_mode") == "no_influence"
    assert state("sensor", "operating_mode") == "hot_water"
    assert state("sensor", "mk1_flow") == "30.0"
    assert state("sensor", "heating_demand_border") == "22.8"
    assert state("sensor", "buffer_type") == "separation"
    assert state("binary_sensor", "cooling_release") == "on"
    assert state("binary_sensor", "compressor_1") == "off"  # status mask 4 = ZWE1 only
    assert state("binary_sensor", "aux_heater_1") == "on"
    assert state("button", "circulation") == "unknown"  # a button has no state of its own
    assert state("button", "circulation_stop") == "unknown"
    assert state("binary_sensor", "heating_available") == "on"
    assert state("binary_sensor", "cap_cooling") == "off"
    assert state("binary_sensor", "online") == "on"
    assert state("switch", "dhw_block") == "off"

    # entries without an equipment option get no raw values (the outputs of 0.17.x are gone, 10412/10413 came later)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", "luxtronik_shi", f"{entry.entry_id}_raw_10354") is None


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
    # the missing values are just unknown, the block was read register by register; the disabled raw value is
    # not polled at all
    data = entry.runtime_data.data
    assert "flow_calc_max" not in data
    assert data["dhw_demand_border"] is None
    assert data["heating_demand_border"] is None
    assert "max_flow_temp" not in data  # disabled by default, not polled
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


async def test_circulation_button(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "button", "circulation")
    await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
    assert shi.holding_value(10070) == 1


async def test_pool_block_and_power_limit_write_readback(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Pool lock (python-luxtronik ``lock_swimming_pool``, index 53, 0/1) and power limit (index 40/41).

    Ranges from python-luxtronik holdings.py: lpc_mode 0..2, pc_limit 0..300 (kW/10), lock_swimming_pool 0..1.
    """
    entry = await _setup(hass, shi)

    pool = _entity_id(hass, entry, "switch", "pool_block")
    await hass.services.async_call("switch", "turn_on", {"entity_id": pool}, blocking=True)
    assert shi.holding_value(10053) == 1
    assert hass.states.get(pool).state == "on"
    await hass.services.async_call("switch", "turn_off", {"entity_id": pool}, blocking=True)
    assert shi.holding_value(10053) == 0
    assert hass.states.get(pool).state == "off"

    limit = _entity_id(hass, entry, "number", "cfg_power_limit")
    await hass.services.async_call("number", "set_value", {"entity_id": limit, "value": 30}, blocking=True)
    assert shi.holding_value(10041) == 300
    assert float(hass.states.get(limit).state) == 30.0
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("number", "set_value", {"entity_id": limit, "value": 30.1}, blocking=True)
    assert shi.holding_value(10041) == 300

    select = _entity_id(hass, entry, "select", "cfg_power_limit_mode")
    await hass.services.async_call(
        "select", "select_option", {"entity_id": select, "option": "hard"}, blocking=True
    )
    assert shi.holding_value(10040) == 2
    assert hass.states.get(select).state == "hard"


async def test_unique_id_scheme(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Every entity uses <entry_id>_<key>; changing that scheme would change all entity IDs."""
    import json
    import pathlib

    entry = await _setup(hass, shi)
    contract = json.loads((pathlib.Path(__file__).parent / "fixtures" / "entity_contract.json").read_text())
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert entries
    prefix = f"{entry.entry_id}_"
    for reg_entry in entries:
        assert reg_entry.unique_id.startswith(prefix), reg_entry.unique_id
        key = reg_entry.unique_id.removeprefix(prefix)
        assert key in contract[reg_entry.domain], f"{reg_entry.domain}.{key} not in contract"


async def test_equipment_off_and_on_keeps_entity_ids(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Switching a part off removes its entities; switching it on again restores the same entity IDs."""
    entry = await _setup(hass, shi)
    pool_block = _entity_id(hass, entry, "switch", "pool_block")
    mk1_setpoint = _entity_id(hass, entry, "number", "cfg_mk1_setpoint")
    reads_before = len(active_registers(set(FEATURES)))  # everything the equipment can have

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 30, "mk1": True, "mk2": False, "mk3": False,
                            "cooling": False, "pool": False, "room_unit": False, "solar": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["features"] == ["mk1"]
    assert len(entry.runtime_data.registers) < reads_before
    assert "pool_block" not in {r.key for r in entry.runtime_data.registers}
    assert hass.states.get(pool_block) is None or hass.states.get(pool_block).state == "unavailable"
    assert hass.states.get(mk1_setpoint).state not in ("unavailable", "unknown")

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 30, "mk1": True, "mk2": False, "mk3": False,
                            "cooling": False, "pool": True, "room_unit": False, "solar": False}
    )
    await hass.async_block_till_done()
    assert _entity_id(hass, entry, "switch", "pool_block") == pool_block
    assert hass.states.get(pool_block).state in ("on", "off")


async def test_entry_without_equipment_option_keeps_everything(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Entries from before 0.3.0 have no equipment option and must not lose any entity."""
    import json
    import pathlib

    entry = await _setup(hass, shi)
    assert "features" not in entry.options
    contract = json.loads((pathlib.Path(__file__).parent / "fixtures" / "entity_contract.json").read_text())
    registry = er.async_get(hass)
    entries = er.async_entries_for_config_entry(registry, entry.entry_id)
    from custom_components.luxtronik_shi.registers import (
        _RAW_ADDED,
        ADDED_IN_0_4,
        OUTPUT_FLAGS,
        RENAMED_KEYS,
        RESOLVED_IN_0_17,
    )

    # everything from before 0.4.0, nothing that was added later (registers of 0.4.0, raw values added after 0.8.2,
    # output and input flags of 0.13.0, the resolved sensors and the solar flag of 0.17.0). The contract fixture
    # lists only current keys (renamed keys are gone from it, see tests/test_migration.py).
    added = {reg.key for reg in (*ADDED_IN_0_4, *_RAW_ADDED, *OUTPUT_FLAGS, *RESOLVED_IN_0_17)} | {"cap_solar"}
    assert not added & set(RENAMED_KEYS.values())
    assert len(entries) == sum(len(keys) for keys in contract.values()) - len(added)
    assert not {e.unique_id.removeprefix(f"{entry.entry_id}_") for e in entries} & added


async def _setup_with(hass: HomeAssistant, shi: FakeSHI, features: list[str]) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WP",
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
        options={"scan_interval": 30, "features": features},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_promoted_raw_values(hass: HomeAssistant, shi: FakeSHI) -> None:
    """10109/10110 are signed temperatures (python-luxtronik), 10111 is new; 10109 is now outside_temp_average."""
    entry = await _setup_with(hass, shi, ["mk1"])
    data = entry.runtime_data.data
    assert data["outside_temp_average"] == 0.5
    assert data["heat_source_input"] == 0.6
    assert data["heat_source_out"] == -1.0
    registry = er.async_get(hass)
    entity = registry.async_get(_entity_id(hass, entry, "sensor", "heat_source_input"))
    assert entity.disabled_by is None
    assert entity.unit_of_measurement == "°C"


async def test_mixing_circuit_2_write(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup_with(hass, shi, ["mk1", "mk2"])
    setpoint = _entity_id(hass, entry, "number", "cfg_mk2_setpoint")
    await hass.services.async_call("number", "set_value", {"entity_id": setpoint, "value": 32.5}, blocking=True)
    assert shi.holding_value(10021) == 325
    assert hass.states.get(setpoint).state == "32.5"

    offset = _entity_id(hass, entry, "number", "cfg_mk2_offset")
    await hass.services.async_call("number", "set_value", {"entity_id": offset, "value": -2}, blocking=True)
    assert shi.holding_value(10022) == 0x10000 - 20
    assert hass.states.get(offset).state == "-2.0"

    mode = _entity_id(hass, entry, "select", "cfg_mk2_mode")
    await hass.services.async_call("select", "select_option", {"entity_id": mode, "option": "setpoint"}, blocking=True)
    assert shi.holding_value(10020) == 1

    # mixing circuit 3 and cooling are not selected: no entities
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_cfg_mk3_setpoint") is None
    assert registry.async_get_entity_id("number", DOMAIN, f"{entry.entry_id}_cfg_mk2_cool_setpoint") is None


@pytest.mark.parametrize("n", [2, 3])
async def test_mixing_circuit_all_holdings_write_and_readback(hass: HomeAssistant, shi: FakeSHI, n: int) -> None:
    """Every writable holding of mixing circuits 2 and 3 (heating and cooling): write, raw word, read-back."""
    entry = await _setup_with(hass, shi, ["mk1", f"mk{n}", "cooling"])
    base = 10000 + 10 * n
    numbers = (
        # key, address, value, expected raw word (python-luxtronik: 0.1 scale, offsets are int16)
        ("setpoint", base + 1, 20.0, 200),
        ("setpoint", base + 1, 65.0, 650),
        ("offset", base + 2, 5.0, 50),
        ("offset", base + 2, -5.0, 0x10000 - 50),
        ("cool_setpoint", base + 6, 5.0, 50),
        ("cool_setpoint", base + 6, 25.0, 250),
        ("cool_offset", base + 7, 5.0, 50),
        ("cool_offset", base + 7, -5.0, 0x10000 - 50),
    )
    for suffix, address, value, raw in numbers:
        entity_id = _entity_id(hass, entry, "number", f"cfg_mk{n}_{suffix}")
        await hass.services.async_call(
            "number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
        )
        assert shi.holding_value(address) == raw
        assert float(hass.states.get(entity_id).state) == value
        # values outside the range of the source are rejected before anything is written
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "number", "set_value", {"entity_id": entity_id, "value": 1000}, blocking=True
            )
        assert shi.holding_value(address) == raw

    selects = (
        ("mode", base, "offset", 2),
        ("level", base + 3, "decreased", 3),
        ("cool_mode", base + 5, "level", 3),
    )
    for suffix, address, option, raw in selects:
        entity_id = _entity_id(hass, entry, "select", f"cfg_mk{n}_{suffix}")
        await hass.services.async_call(
            "select", "select_option", {"entity_id": entity_id, "option": option}, blocking=True
        )
        assert shi.holding_value(address) == raw
        assert hass.states.get(entity_id).state == option

    # there is no cooling level register for mixing circuits in the source
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("select", DOMAIN, f"{entry.entry_id}_cfg_mk{n}_cool_level") is None


async def test_cooling_and_pool_energy(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup_with(hass, shi, ["mk1", "cooling", "pool"])
    data = entry.runtime_data.data
    assert data["energy_el_cooling"] == 1.0
    assert data["energy_el_pool"] == 2.0
    assert data["energy_th_cooling"] == 3.0
    assert data["energy_th_pool"] == 4.0


async def test_sub_devices(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Entities are grouped into heat pump / heating / hot water (cooling and pool only if selected)."""
    from homeassistant.helpers import device_registry as dr

    entry = await _setup_with(hass, shi, ["mk1"])
    devices = dr.async_get(hass)
    entities = er.async_get(hass)

    def device(suffix: str = ""):
        ident = (DOMAIN, f"{entry.entry_id}{suffix}")
        if hasattr(devices, "async_get_device_by_identifier"):  # HA 2026.8+
            return devices.async_get_device_by_identifier(ident, entry.entry_id)
        return devices.async_get_device(identifiers={ident})

    main, heating, hot_water = device(), device("_heating"), device("_hot_water")
    assert main and heating and hot_water
    assert device("_cooling") is None
    assert device("_pool") is None
    assert heating.via_device_id == main.id and hot_water.via_device_id == main.id
    assert heating.name == "WP Heating"
    assert hot_water.name == "WP Hot water"
    assert main.sw_version == "3.92.3"

    def device_of(platform: str, key: str) -> str:
        return entities.async_get(_entity_id(hass, entry, platform, key)).device_id

    assert device_of("sensor", "flow") == main.id
    assert device_of("binary_sensor", "aux_heater_1") == main.id
    assert device_of("number", "cfg_heating_setpoint") == heating.id
    assert device_of("number", "cfg_mk1_setpoint") == heating.id
    assert device_of("switch", "heating_block") == heating.id
    assert device_of("sensor", "dhw") == hot_water.id
    assert device_of("button", "circulation") == hot_water.id
    assert device_of("button", "circulation_stop") == hot_water.id
    assert device_of("button", "extra_dhw_stop") == hot_water.id
    assert device_of("switch", "dhw_block") == hot_water.id


async def test_existing_entity_ids_survive_device_move(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Renamed entity IDs (as on the reference installation) stay when entities move to sub-devices."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WP",
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for platform, key, entity_id in (
        ("number", "cfg_heating_setpoint", "number.lwdv_heizen_sollwert_heating_setpoint"),
        ("switch", "heating_block", "switch.lwdv_shi_heating_block"),
        ("sensor", "dhw", "sensor.lwdv_shi_dhw"),
        ("sensor", "flow", "sensor.lwdv_shi_flow"),
    ):
        registry.async_get_or_create(
            platform, DOMAIN, f"{entry.entry_id}_{key}", config_entry=entry, suggested_object_id=entity_id.split(".")[1]
        )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for entity_id in (
        "number.lwdv_heizen_sollwert_heating_setpoint",
        "switch.lwdv_shi_heating_block",
        "sensor.lwdv_shi_dhw",
        "sensor.lwdv_shi_flow",
    ):
        state = hass.states.get(entity_id)
        assert state is not None and state.state not in ("unavailable", "unknown"), entity_id


# key, address, minimum, maximum (firmware V3.92.3 ranges, docs/firmware-3.92.3-shi-full-analysis.md; raw 0.1 scale)
_WRITE_RANGES = (
    ("cfg_heating_setpoint", 10001, 15.0, 75.0),
    ("cfg_heating_offset", 10002, -20.0, 20.0),
    ("cfg_dhw_setpoint", 10006, 30.0, 75.0),
    ("cfg_dhw_offset", 10007, -20.0, 20.0),
    ("cfg_mk1_setpoint", 10011, 20.0, 65.0),
    ("cfg_mk1_offset", 10012, -5.0, 5.0),
    ("cfg_mk1_cool_setpoint", 10016, 5.0, 25.0),
    ("cfg_mk1_cool_offset", 10017, -5.0, 5.0),
    ("cfg_overall_offset", 10066, -5.0, 5.0),  # firmware V3.92.3: -50 ... 50 (0.1 K), not python-luxtronik's +-20
    ("cfg_room_setpoint", 10060, 20.0, 40.0),
)


@pytest.mark.parametrize(("key", "address", "lo", "hi"), _WRITE_RANGES)
async def test_write_ranges_follow_source(
    hass: HomeAssistant, shi: FakeSHI, key: str, address: int, lo: float, hi: float
) -> None:
    """Both limits are written and read back; a step beyond either limit is rejected without a write."""
    entry = await _setup_with(hass, shi, ["mk1", "cooling", "room_unit"])
    registry = er.async_get(hass)
    entity_id = _entity_id(hass, entry, "number", key)
    if registry.async_get(entity_id).disabled_by is not None:  # cooling entities are disabled by default
        registry.async_update_entity(entity_id, disabled_by=None)
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert float(hass.states.get(entity_id).attributes["min"]) == lo
    assert float(hass.states.get(entity_id).attributes["max"]) == hi
    for value in (lo, hi):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
        )
        assert shi.holding_value(address) == round(value * 10) & 0xFFFF
        assert float(hass.states.get(entity_id).state) == value
    before = shi.holding_value(address)
    for value in (lo - 0.5, hi + 0.5):
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
            )
        assert shi.holding_value(address) == before


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0, "series"), (1, "separation"), (2, "multi"), (3, "unknown"), (0x7FFF, "unknown")],
)
async def test_buffer_type_mapping(hass: HomeAssistant, shi: FakeSHI, raw: int, expected: str) -> None:
    """Raw 0 series, 1 separation, 2 multi-function (python-luxtronik BufferType); other values have no state."""
    shi.input[10202] = raw
    entry = await _setup(hass, shi)
    assert hass.states.get(_entity_id(hass, entry, "sensor", "buffer_type")).state == expected


async def test_named_raw_values_decode(hass: HomeAssistant, shi: FakeSHI) -> None:
    """10113 is the calculated maximum flow in 0.1 degC (``flow_calc_max``)."""
    shi.input[10113] = 253
    registry = er.async_get(hass)
    entry = await _setup(hass, shi)
    data = entry.runtime_data.data
    assert "flow_calc_max" not in data  # disabled by default: not polled
    # Enabling an entity reads its register at once (the entry is reloaded by Home Assistant a bit later).
    registry.async_update_entity(_entity_id(hass, entry, "sensor", "flow_calc_max"), disabled_by=None)
    await hass.async_block_till_done()
    data = entry.runtime_data.data
    assert data["flow_calc_max"] == 25.3


async def test_default_name_follows_the_language(hass: HomeAssistant, shi: FakeSHI) -> None:
    from custom_components.luxtronik_shi.config_flow import default_name

    assert default_name("de") == "Wärmepumpe"
    assert default_name("de-AT") == "Wärmepumpe"
    assert default_name("en") == "Heat pump"
    assert default_name("fr") == "Heat pump"
    for language, expected in (("en", "Heat pump"), ("de", "Wärmepumpe")):
        hass.config.language = language
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        name = next(key for key in result["data_schema"].schema if key == "name")
        assert name.default() == expected
        hass.config_entries.flow.async_abort(result["flow_id"])
