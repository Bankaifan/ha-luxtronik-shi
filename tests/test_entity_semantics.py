"""Honest modes and setpoints: climate, water heater, number and select that share registers (simulator only)."""

from __future__ import annotations

import asyncio
import json
import pathlib

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from custom_components.luxtronik_shi.const import DOMAIN, ISSUE_EXTERNAL_CHANGE
from custom_components.luxtronik_shi.modbus_client import ModbusCommError
from custom_components.luxtronik_shi.registers import ALL_REGISTERS, CONTROL_MODES

from .fake_shi import FakeSHI
from .test_integration import _entity_id, _setup

TRANSLATIONS = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / DOMAIN / "translations"


def _texts(lang: str) -> dict:
    return json.loads((TRANSLATIONS / f"{lang}.json").read_text(encoding="utf-8"))


def _writes(shi: FakeSHI) -> list[tuple[int, int, int]]:
    return [r for r in shi.requests if r[0] == 6]


async def _poll_settings(hass: HomeAssistant, entry) -> None:
    """Two polls: settings are read every second poll."""
    for _ in range(2):
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()


# ------------------------------------------------------------------ F9: a write keeps the poll schedule
async def test_write_does_not_move_the_next_poll(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    number = _entity_id(hass, entry, "number", "cfg_heating_setpoint")
    before = coordinator._unsub_refresh.__self__.when()
    await asyncio.sleep(1.1)
    await hass.services.async_call("number", "set_value", {"entity_id": number, "value": 25}, blocking=True)
    assert coordinator._unsub_refresh.__self__.when() == before
    # ... and every entity of the register still got the read-back at once
    assert hass.states.get(number).state == "25.0"
    climate = _entity_id(hass, entry, "climate", "climate_heating")
    assert hass.states.get(climate).attributes["temperature"] == 25.0


# ------------------------------------------------------------------ F2: heat keeps offset and level
@pytest.mark.parametrize(("raw", "option"), [(2, "offset"), (3, "level"), (1, "setpoint")])
@pytest.mark.parametrize("service", ["set_hvac_mode", "turn_on"])
async def test_heat_keeps_an_active_control_mode(
    hass: HomeAssistant, shi: FakeSHI, raw: int, option: str, service: str
) -> None:
    shi.holding[10000] = raw
    entry = await _setup(hass, shi)
    climate = _entity_id(hass, entry, "climate", "climate_heating")
    data = {"entity_id": climate} | ({"hvac_mode": "heat"} if service == "set_hvac_mode" else {})
    await hass.services.async_call("climate", service, data, blocking=True)
    assert not _writes(shi)
    assert hass.states.get(_entity_id(hass, entry, "select", "cfg_heating_mode")).state == option


@pytest.mark.parametrize("service", ["set_hvac_mode", "turn_on"])
async def test_heat_from_auto_writes_setpoint(hass: HomeAssistant, shi: FakeSHI, service: str) -> None:
    entry = await _setup(hass, shi)
    climate = _entity_id(hass, entry, "climate", "climate_heating")
    data = {"entity_id": climate} | ({"hvac_mode": "heat"} if service == "set_hvac_mode" else {})
    await hass.services.async_call("climate", service, data, blocking=True)
    assert _writes(shi) == [(6, 10000, 1)]
    assert hass.states.get(climate).state == "heat"


async def test_climate_has_no_off(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.holding[10000] = 1
    entry = await _setup(hass, shi)
    climate = _entity_id(hass, entry, "climate", "climate_heating")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "off"}, blocking=True
        )
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("climate", "turn_off", {"entity_id": climate}, blocking=True)
    assert not _writes(shi)
    assert shi.holding_value(10050) == 0  # the block is never touched


# ------------------------------------------------------------------ F3: target only in mode setpoint
@pytest.mark.parametrize(("raw", "mode"), [(0, "no_influence"), (2, "offset"), (3, "level")])
@pytest.mark.parametrize(
    ("domain", "key", "mode_address", "select_key", "value"),
    [
        ("climate", "climate_heating", 10000, "cfg_heating_mode", 30),
        ("water_heater", "water_heater_dhw", 10005, "cfg_dhw_mode", 50),
    ],
)
async def test_target_write_outside_setpoint_mode_is_refused(
    hass: HomeAssistant,
    shi: FakeSHI,
    raw: int,
    mode: str,
    domain: str,
    key: str,
    mode_address: int,
    select_key: str,
    value: float,
) -> None:
    shi.holding[mode_address] = raw
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, domain, key)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            domain, "set_temperature", {"entity_id": entity_id, "temperature": value}, blocking=True
        )
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == f"setpoint_not_active_{mode}"
    assert err.value.translation_placeholders == {"select": _entity_id(hass, entry, "select", select_key)}
    assert not _writes(shi)
    assert hass.states.get(entity_id).attributes["setpoint_active"] is False


@pytest.mark.parametrize("lang", ["en", "de"])
def test_refusal_messages_exist_in_both_languages(lang: str) -> None:
    exceptions = _texts(lang)["exceptions"]
    for mode in ("no_influence", "offset", "level", "unknown"):
        assert "{select}" in exceptions[f"setpoint_not_active_{mode}"]["message"]
    expected = {"en": '"Setpoint"', "de": "„Sollwert“"}[lang]
    assert expected in exceptions["setpoint_not_active_no_influence"]["message"]
    assert {"en": '"No influence"', "de": "„Keine Vorgabe“"}[lang] in exceptions["setpoint_not_active_no_influence"]["message"]


@pytest.mark.parametrize(
    ("number_key", "mode_address", "address", "value", "raw", "target"),
    [
        ("cfg_heating_setpoint", 10000, 10001, 31, 310, 30.0),
        ("cfg_dhw_setpoint", 10005, 10006, 48, 480, 55.0),
    ],
)
async def test_number_still_writes_in_every_mode(
    hass: HomeAssistant,
    shi: FakeSHI,
    number_key: str,
    mode_address: int,
    address: int,
    value: float,
    raw: int,
    target: float,
) -> None:
    shi.holding[mode_address] = 2  # offset: an optimizer writes the setpoint before it switches the mode
    entry = await _setup(hass, shi)
    number = _entity_id(hass, entry, "number", number_key)
    await hass.services.async_call("number", "set_value", {"entity_id": number, "value": value}, blocking=True)
    assert shi.holding_value(address) == raw
    state = hass.states.get(number)
    assert state.attributes["setpoint_active"] is False
    assert state.attributes["effective_target"] == target


async def test_setpoint_attributes_follow_the_mode(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.holding[10000] = 1
    entry = await _setup(hass, shi)
    climate = _entity_id(hass, entry, "climate", "climate_heating")
    assert hass.states.get(climate).attributes["setpoint_active"] is True
    select = _entity_id(hass, entry, "select", "cfg_heating_mode")
    await hass.services.async_call("select", "select_option", {"entity_id": select, "option": "offset"}, blocking=True)
    assert hass.states.get(climate).attributes["setpoint_active"] is False
    other = hass.states.get(_entity_id(hass, entry, "number", "cfg_mk1_setpoint"))
    assert "setpoint_active" not in other.attributes  # only the two setpoints with a known effective target


# ------------------------------------------------------------------ F4: effective target read after the write
class _MirrorSHI(FakeSHI):
    """Models the controller taking over the hot water setpoint as its target in mode setpoint."""

    def _respond(self, unit, pdu):
        out = super()._respond(unit, pdu)
        if pdu[0] == 6 and self.holding[10005] == 1:
            self.input[10121] = self.holding[10006]
        return out


async def test_effective_target_is_read_once_after_a_setpoint_write(hass: HomeAssistant, socket_enabled) -> None:
    shi = _MirrorSHI()
    await shi.start()
    try:
        shi.holding[10005] = 1
        entry = await _setup(hass, shi)
        water_heater = _entity_id(hass, entry, "water_heater", "water_heater_dhw")
        shi.requests.clear()
        await hass.services.async_call(
            "water_heater", "set_temperature", {"entity_id": water_heater, "temperature": 48}, blocking=True
        )
        assert shi.requests == [(6, 10006, 480), (3, 10006, 1), (4, 10121, 1)]
        assert hass.states.get(_entity_id(hass, entry, "sensor", "dhw_target")).state == "48.0"
        assert hass.states.get(water_heater).attributes["effective_target"] == 48.0
        # other writes read nothing extra
        shi.requests.clear()
        select = _entity_id(hass, entry, "select", "cfg_dhw_mode")
        await hass.services.async_call(
            "select", "select_option", {"entity_id": select, "option": "offset"}, blocking=True
        )
        assert shi.requests == [(6, 10005, 2), (3, 10005, 1)]
    finally:
        await shi.stop()


# ------------------------------------------------------------------ F1 / F11: labels say what an option does
@pytest.mark.parametrize(("lang", "label"), [("en", "No influence"), ("de", "Keine Vorgabe")])
def test_mode_zero_is_no_influence_on_every_mode_select(lang: str, label: str) -> None:
    selects = _texts(lang)["entity"]["select"]
    mode_selects = [reg.key for reg in ALL_REGISTERS if reg.platform == "select" and reg.options == CONTROL_MODES]
    assert len(mode_selects) == 9  # heating, hot water, MK1-3 heating and cooling, overall heating
    for key in mode_selects:
        # the overall mode adds what "no influence" means for the circuits (tools/gen_translations.py)
        assert selects[key]["state"]["no_influence"].startswith(label), key
        assert set(selects[key]["state"]) == set(CONTROL_MODES)
        assert "off" not in selects[key]["state"]  # raw 0 does not switch the circuit off


@pytest.mark.parametrize("lang", ["en", "de"])
def test_climate_and_water_heater_states_are_translated(lang: str) -> None:
    entity = _texts(lang)["entity"]
    assert set(entity["climate"]["climate_heating"]["state"]) == {"auto", "heat"}
    states = entity["water_heater"]["water_heater_dhw"]["state"]
    assert set(states) == {"no_influence", "setpoint", "offset", "level"}
    assert states["no_influence"] == {"en": "No influence", "de": "Keine Vorgabe"}[lang]
    for attr in ("setpoint_active", "effective_target", "heating_block", "controller_mode"):
        assert entity["climate"]["climate_heating"]["state_attributes"][attr]["name"]
    # the operating mode sensor: raw 5 is "no request" (idle), not off
    assert entity["sensor"]["operating_mode"]["state"]["no_request"] == {"en": "No request", "de": "Keine Anforderung"}[lang]
    assert "off" not in entity["sensor"]["operating_mode"]["state"]


# ------------------------------------------------------------------ F10: return temperature, action, block
async def test_climate_action_and_block(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.input[10002] = 0  # operating mode heating
    shi.input[10000] = 1  # compressor 1 running
    entry = await _setup(hass, shi)
    climate = _entity_id(hass, entry, "climate", "climate_heating")
    state = hass.states.get(climate)
    assert state.attributes["hvac_action"] == "heating"
    assert state.attributes["current_temperature"] == 28.5  # return, not flow (35.1)
    shi.input[10000] = 0
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(climate).attributes["hvac_action"] == "idle"
    block = _entity_id(hass, entry, "switch", "heating_block")
    await hass.services.async_call("switch", "turn_on", {"entity_id": block}, blocking=True)
    state = hass.states.get(climate)
    assert state.attributes["hvac_action"] == "off"
    assert state.attributes["heating_block"] is True
    assert state.state == "auto"  # the block is no HVAC mode


# ------------------------------------------------------------------ F7: temperature device class only on °C
async def test_fahrenheit_number_matches_climate(hass: HomeAssistant, shi: FakeSHI) -> None:
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = await _setup(hass, shi)
    climate = hass.states.get(_entity_id(hass, entry, "climate", "climate_heating"))
    number = hass.states.get(_entity_id(hass, entry, "number", "cfg_heating_setpoint"))
    assert number.attributes["device_class"] == "temperature"
    assert number.attributes["unit_of_measurement"] == "°F"
    assert float(number.state) == pytest.approx(climate.attributes["temperature"], abs=0.1)
    offset = hass.states.get(_entity_id(hass, entry, "number", "cfg_heating_offset"))
    assert "device_class" not in offset.attributes
    assert offset.attributes["unit_of_measurement"] == "K"


# ------------------------------------------------------------------ F8: changes outside Home Assistant
def _issue(hass: HomeAssistant, entry):
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{ISSUE_EXTERNAL_CHANGE}_{entry.entry_id}")


def _logbook(hass: HomeAssistant) -> list[dict]:
    events: list[dict] = []
    hass.bus.async_listen("logbook_entry", lambda event: events.append(dict(event.data)))
    return events


async def test_external_change_raises_issue_and_logbook_entry(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    assert _issue(hass, entry) is None  # the first poll after setup reports nothing
    events = _logbook(hass)
    shi.holding[10001] = 250  # someone else writes the heating setpoint
    await _poll_settings(hass, entry)
    issue = _issue(hass, entry)
    assert issue is not None and issue.translation_key == ISSUE_EXTERNAL_CHANGE
    assert "- WP Heating Setpoint: 22.0 °C -> 25.0 °C (" in issue.translation_placeholders["changes"]
    number = _entity_id(hass, entry, "number", "cfg_heating_setpoint")
    assert events == [
        {
            "name": "WP",
            "message": "WP Heating Setpoint changed outside Home Assistant: 22.0 °C -> 25.0 °C",
            "domain": DOMAIN,
            "entity_id": number,
        }
    ]
    # further changes are merged into the open issue; the first old value stays
    shi.holding[10001] = 260
    shi.holding[10000] = 2
    await _poll_settings(hass, entry)
    changes = _issue(hass, entry).translation_placeholders["changes"]
    assert "WP Heating Setpoint: 22.0 °C -> 26.0 °C" in changes
    assert "WP Heating Mode: No influence (controller uses its own values) -> Offset (controller's target plus offset)" in changes
    # after a dismissal, a new change starts a fresh list
    ir.async_get(hass).async_ignore(DOMAIN, f"{ISSUE_EXTERNAL_CHANGE}_{entry.entry_id}", True)
    shi.holding[10051] = 1
    await _poll_settings(hass, entry)
    issue = _issue(hass, entry)
    assert issue.dismissed_version is None
    assert issue.translation_placeholders["changes"].startswith("- WP Hot water Block: off -> on")
    assert "Setpoint" not in issue.translation_placeholders["changes"]


async def test_external_change_logbook_in_german(hass: HomeAssistant, shi: FakeSHI) -> None:
    hass.config.language = "de"
    entry = await _setup(hass, shi)
    events = _logbook(hass)
    shi.holding[10006] = 450
    await _poll_settings(hass, entry)
    assert events[0]["message"] == "WP Warmwasser Sollwert außerhalb von Home Assistant geändert: 40,0 °C -> 45,0 °C"
    shi.holding[10005] = 1
    await _poll_settings(hass, entry)
    assert events[1]["message"] == (
        "WP Warmwasser Betriebsart außerhalb von Home Assistant geändert: Keine Vorgabe (Regelung nutzt ihre eigenen Werte) -> "
        "Sollwert (ersetzt den Sollwert der Regelung)"
    )


async def test_writes_through_home_assistant_are_not_external(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    events = _logbook(hass)
    climate = _entity_id(hass, entry, "climate", "climate_heating")
    await hass.services.async_call(
        "climate", "set_hvac_mode", {"entity_id": climate, "hvac_mode": "heat"}, blocking=True
    )
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": climate, "temperature": 33}, blocking=True
    )
    number = _entity_id(hass, entry, "number", "cfg_dhw_setpoint")
    await hass.services.async_call("number", "set_value", {"entity_id": number, "value": 47}, blocking=True)
    await _poll_settings(hass, entry)
    assert _issue(hass, entry) is None
    assert events == []


async def test_lost_write_answer_is_still_our_write(hass: HomeAssistant, shi: FakeSHI) -> None:
    """The write reached the heat pump but the answer was lost: the next poll's value is our own."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    real = coordinator.client.write_register

    async def write_then_fail(address: int, value: int) -> None:
        await real(address, value)
        raise ModbusCommError("answer lost")

    coordinator.client.write_register = write_then_fail
    number = _entity_id(hass, entry, "number", "cfg_heating_setpoint")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("number", "set_value", {"entity_id": number, "value": 27}, blocking=True)
    coordinator.client.write_register = real
    assert shi.holding_value(10001) == 270
    await _poll_settings(hass, entry)
    assert _issue(hass, entry) is None


async def test_device_reset_after_a_reconnect_is_not_an_external_change(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Same outage signal as the restore (v2): a re-established connection, then the reverted values."""
    shi.holding.update({10000: 1, 10005: 1, 10003: 2})
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    for _ in range(2):  # the reconnect guard needs a few quiet polls first
        await coordinator.async_refresh()
    shi.holding.update({10000: 0, 10005: 0, 10003: 0, 10001: 350})
    coordinator.client.reconnects += 1
    await _poll_settings(hass, entry)
    assert _issue(hass, entry) is None


async def test_session_gap_is_an_outage_also_without_the_restore_option(
    hass: HomeAssistant, shi: FakeSHI
) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    assert not coordinator.restore_enabled
    coordinator._last_poll_mono -= 700  # Home Assistant paused longer than the SHI watchdog
    shi.holding.update({10000: 0, 10001: 350})
    await _poll_settings(hass, entry)
    assert _issue(hass, entry) is None


async def test_zeros_without_an_outage_are_external(hass: HomeAssistant, shi: FakeSHI) -> None:
    """As in the restore (v2): without an outage the device cannot revert values, so this is someone's change."""
    shi.holding.update({10000: 1, 10005: 1})
    entry = await _setup(hass, shi)
    shi.holding.update({10000: 0, 10005: 0})
    await _poll_settings(hass, entry)
    changes = _issue(hass, entry).translation_placeholders["changes"]
    assert "WP Heating Mode: Setpoint (replaces the controller's target) -> No influence (controller uses its own values)" in changes
    assert "WP Hot water Mode" in changes


async def test_changes_during_an_outage_are_not_external(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    real = coordinator.client.read

    async def unreachable(*args, **kwargs):
        raise ModbusCommError("down")

    coordinator.client.read = unreachable
    await coordinator.async_refresh()
    coordinator.client.read = real
    shi.holding[10001] = 300  # changed while the SHI was unreachable (the outage notice covers it)
    for _ in range(3):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert _issue(hass, entry) is None
    # afterwards changes are reported again
    shi.holding[10001] = 310
    await _poll_settings(hass, entry)
    assert _issue(hass, entry) is not None


async def test_extra_dhw_reset_by_the_controller_is_not_external(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    button = _entity_id(hass, entry, "button", "extra_dhw")
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    shi.holding[10071] = 0  # the controller ends the extra hot water by itself
    await _poll_settings(hass, entry)
    assert _issue(hass, entry) is None


async def test_circulation_changed_by_the_controller_is_not_external(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    button = _entity_id(hass, entry, "button", "circulation")
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    shi.holding[10070] = 0  # a time schedule or the hot water run in the controller switches it
    await _poll_settings(hass, entry)
    assert _issue(hass, entry) is None
    shi.holding[10070] = 1
    await _poll_settings(hass, entry)
    assert _issue(hass, entry) is None
    # other keys are still reported
    shi.holding[10001] = 310
    await _poll_settings(hass, entry)
    assert _issue(hass, entry) is not None


async def test_external_change_with_restore_option_on(hass: HomeAssistant, shi: FakeSHI) -> None:
    from homeassistant.const import CONF_HOST, CONF_PORT
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.luxtronik_shi.const import CONF_RESTORE_AFTER_RESET, CONF_SLAVE

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WP",
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
        options={"scan_interval": 30, "features": ["mk1"], CONF_RESTORE_AFTER_RESET: True},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    number = _entity_id(hass, entry, "number", "cfg_heating_setpoint")
    await hass.services.async_call("number", "set_value", {"entity_id": number, "value": 27}, blocking=True)
    shi.holding[10001] = 290
    await _poll_settings(hass, entry)
    assert "WP Heating Setpoint: 27.0 °C -> 29.0 °C" in _issue(hass, entry).translation_placeholders["changes"]
    assert "cfg_heating_setpoint" not in entry.runtime_data.remembered  # restore forgets it as before


async def test_issue_removed_on_unload(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    shi.holding[10001] = 250
    await _poll_settings(hass, entry)
    assert _issue(hass, entry) is not None
    await hass.config_entries.async_unload(entry.entry_id)
    assert _issue(hass, entry) is None


# ------------------------------------------------------------------ remaining texts in both languages
async def test_poll_and_write_errors_are_translated(hass: HomeAssistant, shi: FakeSHI) -> None:
    from homeassistant.helpers.update_coordinator import UpdateFailed

    from custom_components.luxtronik_shi.registers import BY_KEY

    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data

    async def unreachable(*args, **kwargs):
        raise ModbusCommError("down")

    coordinator.client.read = unreachable
    with pytest.raises(UpdateFailed) as err:
        await coordinator._async_update_data()
    assert (err.value.translation_domain, err.value.translation_key) == (DOMAIN, "poll_failed")
    with pytest.raises(HomeAssistantError) as err:
        await coordinator.async_write(BY_KEY["flow"], 1)
    assert err.value.translation_key == "not_writable"
    for lang in ("en", "de"):
        exceptions = _texts(lang)["exceptions"]
        for key in ("poll_failed", "not_writable", "write_failed", "state_on", "state_off", "external_change_logbook"):
            assert exceptions[key]["message"], (lang, key)


async def test_overall_heating_is_disabled_by_default(hass: HomeAssistant, shi: FakeSHI) -> None:
    from homeassistant.helpers import entity_registry as er

    entry = await _setup(hass, shi)
    registry = er.async_get(hass)
    for platform, key in (
        ("select", "cfg_overall_mode"),
        ("number", "cfg_overall_offset"),
        ("select", "cfg_overall_level"),
    ):
        entity_id = _entity_id(hass, entry, platform, key)
        assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert registry.async_get(_entity_id(hass, entry, "select", "cfg_heating_mode")).disabled_by is None
