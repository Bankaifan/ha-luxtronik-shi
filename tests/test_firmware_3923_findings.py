"""Behaviour that follows the full analysis of the SHI firmware V3.92.3 (docs/firmware-3.92.3-shi-full-analysis.md).

Fake SHI only. Covered: firmware ranges and defaults of the writable holdings, the revert to the default on a write
outside the range (never sent), the default read-back reported as an error, the triggers circulation and extra hot
water (buttons with a running flag), the overall group (no setpoint option), the level options (raw 1 and 2 are one
option), the resolved registers (operating hours cooling/solar, extra hot water values, solar equipment flag, the
calculated maximum flow) and the signed heat quantity counters.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.luxtronik_shi.const import (
    DEFERRED_KEYS,
    ENABLE_SHI_PARAMETER,
    EXTERNAL_CHANGE_EXCLUDED,
    ISSUE_EXTERNAL_CHANGE,
    RESTORE_KEYS,
    TRIGGER_KEYS,
)
from custom_components.luxtronik_shi.diagnostics import async_get_config_entry_diagnostics
from custom_components.luxtronik_shi.registers import (
    ALL_REGISTERS,
    BY_KEY,
    CONTROL_MODES,
    DERIVED_FLAGS,
    LEVEL_OPTIONS,
    OVERALL_MODE_KEY,
    REMOVED_ENTITIES,
    REMOVED_KEYS,
    RENAMED_KEYS,
    RESOLVED_IN_0_17,
    TRIGGER_ACTIONS,
    TRIGGER_REQUIRES,
    TriggerAction,
    decode,
    encode_int16,
    raw_in_range,
)

from .fake_shi import HOLDING_RANGES, FakeSHI
from .test_integration import _entity_id, _setup_with
from .test_repairs import Clock, Outage
from .test_restore_after_reset import _polls, _reboot, _setup, _write, _writes


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    from custom_components.luxtronik_shi import coordinator as coordinator_module

    fake = Clock()
    monkeypatch.setattr(coordinator_module.dt_util, "utcnow", fake)
    return fake


ALL_FEATURES = ["mk1", "mk2", "mk3", "cooling", "pool", "room_unit", "solar"]


# ------------------------------------------------------------------ ranges and defaults (register map)
def test_every_writable_holding_has_the_firmware_range_and_default() -> None:
    """Table 2.1 / 3.4 of the full analysis: ranges in 0.1 units and the raw defaults."""
    for address, (lo, hi, default) in HOLDING_RANGES.items():
        reg = next(r for r in ALL_REGISTERS if r.kind == "holding" and r.address == address)
        assert reg.reset_default == default, reg.key
        if reg.platform == "number":
            assert (round(reg.min_value / reg.scale), round(reg.max_value / reg.scale)) == (lo, hi), reg.key
        else:
            assert reg.options is not None and (lo, hi) == (0, len(reg.options) - 1), reg.key
    assert BY_KEY["cfg_overall_offset"].min_value == -5.0 and BY_KEY["cfg_overall_offset"].max_value == 5.0
    for key in ("heating_block", "dhw_block", "cooling_block", "pool_block", "circulation", "extra_dhw"):
        assert BY_KEY[key].reset_default == 0
    # the levels: raw 0 ... 3 are all inside the range, raw 1 and 2 are the same option
    assert raw_in_range(BY_KEY["cfg_heating_level"], 2) and not raw_in_range(BY_KEY["cfg_heating_level"], 4)
    # 10060 binds a persisted controller parameter: no fixed default, the range is open (owner decision 20-40)
    assert BY_KEY["cfg_room_setpoint"].reset_default is None


def test_raw_in_range_covers_numbers_selects_and_switches() -> None:
    offset = BY_KEY["cfg_overall_offset"]
    assert raw_in_range(offset, encode_int16(5.0, 0.1)) and raw_in_range(offset, encode_int16(-5.0, 0.1))
    assert not raw_in_range(offset, encode_int16(5.5, 0.1)) and not raw_in_range(offset, encode_int16(-5.5, 0.1))
    setpoint = BY_KEY["cfg_heating_setpoint"]
    assert raw_in_range(setpoint, 150) and raw_in_range(setpoint, 750) and not raw_in_range(setpoint, 900)
    mode = BY_KEY["cfg_heating_mode"]
    assert raw_in_range(mode, 3) and not raw_in_range(mode, 4)
    # the overall mode's raw 1 (setpoint) is not implemented by the firmware: never written
    assert raw_in_range(BY_KEY[OVERALL_MODE_KEY], 2) and not raw_in_range(BY_KEY[OVERALL_MODE_KEY], 1)
    block = BY_KEY["heating_block"]
    assert raw_in_range(block, 1) and not raw_in_range(block, 2)
    for key in ("circulation", "extra_dhw"):
        assert raw_in_range(BY_KEY[key], 1) and raw_in_range(BY_KEY[key], 0) and not raw_in_range(BY_KEY[key], 2)
    # 10060: the firmware range is open, the owner's 20-40 degC of the number entity is applied as the range
    room = BY_KEY["cfg_room_setpoint"]
    assert raw_in_range(room, 200) and raw_in_range(room, 400) and not raw_in_range(room, 100)


async def test_fake_shi_reverts_out_of_range_writes_to_the_default(shi: FakeSHI) -> None:
    """The simulator behaves like the firmware (1.4): acknowledged, register reset to its default."""
    shi.holding[10001] = 220
    shi._respond(1, bytes([6]) + (10001).to_bytes(2, "big") + (900).to_bytes(2, "big"))
    assert shi.holding[10001] == 350 and shi.reverted == [(10001, 900)]
    shi._respond(1, bytes([6]) + (10000).to_bytes(2, "big") + (5).to_bytes(2, "big"))
    assert shi.holding[10000] == 0


# ------------------------------------------------------------------ writes outside the range are never sent
@pytest.mark.parametrize(
    ("key", "raw"),
    [
        ("cfg_heating_setpoint", 900),  # 90.0 degC, above 75.0
        ("cfg_heating_setpoint", 100),  # 10.0 degC, below 15.0
        ("cfg_overall_offset", encode_int16(10.0, 0.1)),  # python-luxtronik allowed +-20, the firmware +-5
        ("cfg_dhw_offset", encode_int16(-25.0, 0.1)),
        ("cfg_power_limit", 301),
        ("cfg_heating_mode", 4),
    ],
)
async def test_out_of_range_raw_is_refused_before_the_write(
    hass: HomeAssistant, shi: FakeSHI, key: str, raw: int
) -> None:
    entry = await _setup_with(hass, shi, ALL_FEATURES)
    before = shi.holding[BY_KEY[key].address]
    shi.requests.clear()
    with pytest.raises(ServiceValidationError) as err:
        await _write(entry, key, raw)
    assert err.value.translation_key == "write_out_of_range"
    assert err.value.translation_placeholders["key"] == key
    assert _writes(shi) == []  # nothing reached the device, so nothing was reset to its default
    assert shi.holding[BY_KEY[key].address] == before


async def test_number_entity_limits_follow_the_firmware(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup_with(hass, shi, ALL_FEATURES)
    registry = er.async_get(hass)
    entity_id = _entity_id(hass, entry, "number", "cfg_overall_offset")
    registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert (float(state.attributes["min"]), float(state.attributes["max"])) == (-5.0, 5.0)
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": -5.0}, blocking=True
    )
    assert shi.holding[10066] == 0x10000 - 50
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number", "set_value", {"entity_id": entity_id, "value": 6.0}, blocking=True
        )
    assert shi.holding[10066] == 0x10000 - 50  # not reset to 0 by the firmware: never sent


async def test_restore_never_writes_a_value_outside_the_range(
    hass: HomeAssistant, shi: FakeSHI, caplog: pytest.LogCaptureFixture
) -> None:
    """A remembered value that is outside the range (e.g. from an older version) is dropped, not written."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_setpoint", 300)
    coordinator._remembered["cfg_heating_setpoint"] = 900  # poisoned store from before the range check
    with caplog.at_level(logging.WARNING):
        await _reboot(entry, shi, {10000: 0, 10001: 350})
    assert (10001, 900) not in _writes(shi)
    assert shi.holding[10001] == 350  # untouched: no revert-to-default by a bad restore
    assert shi.holding[10000] == 0  # the mode waits for its circuit and is dropped with the setpoint
    assert "cfg_heating_setpoint" not in coordinator.remembered


# ------------------------------------------------------------------ default read back after a write
async def test_default_read_back_after_a_write_is_an_error(
    hass: HomeAssistant, shi: FakeSHI, caplog: pytest.LogCaptureFixture
) -> None:
    """Error 816 or a watchdog expiry: the firmware acknowledges and the register reads its default."""
    entry = await _setup(hass, shi)
    shi.enforce_ranges = False  # let an out-of-range word through to provoke the firmware revert path
    shi.ignored_writes = {10001}
    shi.holding[10001] = 350  # the default is what the register reads afterwards
    with caplog.at_level(logging.WARNING), pytest.raises(HomeAssistantError) as err:
        await _write(entry, "cfg_heating_setpoint", 300)
    assert err.value.translation_key == "write_reverted_to_default"
    assert err.value.translation_placeholders == {"key": "cfg_heating_setpoint", "value": "30.0 °C", "default": "35.0 °C"}
    assert "reset the register to its default 350" in caplog.text
    assert entry.runtime_data.data["cfg_heating_setpoint"] == 35.0  # the read-back is published
    assert "cfg_heating_setpoint" not in entry.runtime_data.remembered


async def test_other_read_back_mismatch_is_only_logged(
    hass: HomeAssistant, shi: FakeSHI, caplog: pytest.LogCaptureFixture
) -> None:
    entry = await _setup(hass, shi)
    shi.ignored_writes = {10001}
    shi.holding[10001] = 220  # not the default: another client's value stays
    with caplog.at_level(logging.WARNING):
        await _write(entry, "cfg_heating_setpoint", 300)  # no error
    assert "cfg_heating_setpoint=300 was not taken by the controller (it reads 220)" in caplog.text


async def test_deferred_hot_water_write_is_not_reported_as_reverted(hass: HomeAssistant, shi: FakeSHI) -> None:
    """The hot water group commits about 10 s later; the first read-back shows the old value, which may be the
    default. That is the pending map, not a revert."""
    entry = await _setup(hass, shi)
    shi.deferred = {10006}
    shi.holding[10006] = 400  # the default
    await _write(entry, "cfg_dhw_setpoint", 500)  # no error
    assert shi.pending[10006][0] == 500


async def test_proven_default_counts_as_a_reset_value(hass: HomeAssistant, shi: FakeSHI, clock: Clock) -> None:
    """A learned value does not hide the proven default: reading 400 after an outage is a reset too."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 540)
    coordinator._learned = {"cfg_dhw_setpoint": 500}  # learned on a firmware with another default
    await _reboot(entry, shi, {10005: 0, 10006: 400})
    assert (shi.holding[10005], shi.holding[10006]) == (1, 540)
    assert coordinator.learned == {"cfg_dhw_setpoint": 400}


# ------------------------------------------------------------------ triggers (buttons + running flags)
def test_triggers_are_buttons_with_running_flags() -> None:
    """A trigger is a button (write 1) and a binary sensor on the same register, never a switch."""
    assert TRIGGER_KEYS == {"circulation", "extra_dhw"}
    assert not TRIGGER_KEYS & RESTORE_KEYS
    assert TRIGGER_KEYS <= EXTERNAL_CHANGE_EXCLUDED
    flags = {flag.key: flag for flag in DERIVED_FLAGS}
    for key in TRIGGER_KEYS:
        assert BY_KEY[key].platform == "button" and BY_KEY[key].reset_default == 0
        assert "trigger" in BY_KEY[key].source
        running = flags[f"{key}_running"]
        assert running.source == key and running.on_values is None and running.device_class == "running"
    assert ("switch", "circulation") in REMOVED_ENTITIES and ("switch", "extra_dhw") in REMOVED_ENTITIES
    assert TRIGGER_ACTIONS == (TriggerAction("extra_dhw_stop", "Extra: beenden", "Extra: end", "extra_dhw", 0),)
    assert TRIGGER_REQUIRES == {"circulation": "cap_hot_water"}


@pytest.mark.parametrize("key", sorted(TRIGGER_KEYS))
async def test_pressing_the_button_starts_the_trigger_and_the_flag_follows(
    hass: HomeAssistant, shi: FakeSHI, key: str, caplog: pytest.LogCaptureFixture
) -> None:
    entry = await _setup(hass, shi)
    address = BY_KEY[key].address
    button = _entity_id(hass, entry, "button", key)
    running = _entity_id(hass, entry, "binary_sensor", f"{key}_running")
    assert hass.states.get(running).state == "off"
    with caplog.at_level(logging.WARNING):
        await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    assert _writes(shi, address) == [(6, address, 1)]
    assert shi.holding[address] == 1
    assert hass.states.get(running).state == "on"  # the read-back of the write feeds the flag
    assert "was not taken" not in caplog.text
    shi.holding[address] = 0  # the firmware ended the run / the timer
    await _polls(entry, 3)
    assert hass.states.get(running).state == "off"


@pytest.mark.parametrize("key", sorted(TRIGGER_KEYS))
async def test_trigger_ending_at_once_is_not_an_error(
    hass: HomeAssistant, shi: FakeSHI, key: str, caplog: pytest.LogCaptureFixture
) -> None:
    """The firmware sets the trigger back to 0 itself; a read-back of 0 right after the press is the normal end."""
    entry = await _setup(hass, shi)
    address = BY_KEY[key].address
    shi.instant_triggers = {address}
    button = _entity_id(hass, entry, "button", key)
    with caplog.at_level(logging.WARNING):
        await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    assert _writes(shi, address) == [(6, address, 1)]
    assert hass.states.get(_entity_id(hass, entry, "binary_sensor", f"{key}_running")).state == "off"
    assert "was not taken" not in caplog.text and "reset the register" not in caplog.text


async def test_extra_dhw_stop_ends_the_timer(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Writing 0 to 10071 sets the extra hot water timer to 0 (proven)."""
    entry = await _setup(hass, shi)
    await hass.services.async_call(
        "button", "press", {"entity_id": _entity_id(hass, entry, "button", "extra_dhw")}, blocking=True
    )
    assert shi.holding[10071] == 1
    await hass.services.async_call(
        "button", "press", {"entity_id": _entity_id(hass, entry, "button", "extra_dhw_stop")}, blocking=True
    )
    assert _writes(shi, 10071) == [(6, 10071, 1), (6, 10071, 0)]
    assert shi.holding[10071] == 0
    assert hass.states.get(_entity_id(hass, entry, "binary_sensor", "extra_dhw_running")).state == "off"


async def test_circulation_button_is_unavailable_while_hot_water_is_off(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Discrete input 10001 reads 0 while hot water is not equipped or its controller mode is off; the firmware
    does not accept the circulation trigger then (full analysis, 3.3)."""
    shi.discrete[10001] = False
    entry = await _setup(hass, shi)
    button = _entity_id(hass, entry, "button", "circulation")
    assert hass.states.get(button).state == "unavailable"
    assert hass.states.get(_entity_id(hass, entry, "button", "extra_dhw")).state != "unavailable"
    # Home Assistant skips a service call on an unavailable entity; the press itself refuses as well
    await hass.services.async_call("button", "press", {"entity_id": button}, blocking=True)
    assert _writes(shi, 10070) == []
    from custom_components.luxtronik_shi.button import LuxtronikTriggerButton

    with pytest.raises(ServiceValidationError) as err:
        await LuxtronikTriggerButton(entry.runtime_data, BY_KEY["circulation"]).async_press()
    assert err.value.translation_key == "trigger_blocked"
    assert _writes(shi, 10070) == []
    shi.discrete[10001] = True
    entry.runtime_data._tick = 0
    await _polls(entry, 1)
    assert hass.states.get(button).state != "unavailable"


async def test_circulation_blocked_by_holiday_is_silent(hass: HomeAssistant, shi: FakeSHI, caplog) -> None:
    """Holiday mode (3) is not readable over the SHI: the write is accepted, nothing starts, no error (open)."""
    entry = await _setup(hass, shi)
    shi.circulation_blocked = True
    with caplog.at_level(logging.WARNING):
        await hass.services.async_call(
            "button", "press", {"entity_id": _entity_id(hass, entry, "button", "circulation")}, blocking=True
        )
    assert shi.holding[10070] == 0 and "was not taken" not in caplog.text
    assert hass.states.get(_entity_id(hass, entry, "binary_sensor", "circulation_running")).state == "off"


async def test_trigger_not_available_makes_button_and_flag_unavailable(hass: HomeAssistant, shi: FakeSHI) -> None:
    """0x7FFF: the SHI has no circulation pump in this installation (visibility ID_Visi_Zirkulation)."""
    shi.holding[10070] = 0x7FFF
    entry = await _setup(hass, shi)
    assert hass.states.get(_entity_id(hass, entry, "button", "circulation")).state == "unavailable"
    assert hass.states.get(_entity_id(hass, entry, "binary_sensor", "circulation_running")).state == "unavailable"
    assert hass.states.get(_entity_id(hass, entry, "button", "extra_dhw")).state != "unavailable"


async def test_trigger_running_then_ended_by_the_firmware_is_no_external_change(
    hass: HomeAssistant, shi: FakeSHI
) -> None:
    from homeassistant.helpers import issue_registry as ir

    entry = await _setup(hass, shi)
    await _write(entry, "extra_dhw", 1)
    assert shi.holding[10071] == 1
    shi.holding[10071] = 0  # the timer ran out
    await _polls(entry, 5)
    assert entry.runtime_data.data["extra_dhw"] == 0
    assert not [i for i in ir.async_get(hass).issues.values() if i.domain == "luxtronik_shi"]


async def test_old_trigger_switches_are_removed_from_the_registry(hass: HomeAssistant, shi: FakeSHI) -> None:
    """0.16.x created switch entities for the triggers; their registry entries are orphans and are deleted."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain="luxtronik_shi", title="WP", unique_id=f"127.0.0.1:{shi.port}:1",
        data={"host": "127.0.0.1", "port": shi.port, "slave": 1}, options={"scan_interval": 30, "features": ["mk1"]},
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old_switch = registry.async_get_or_create(
        "switch", "luxtronik_shi", f"{entry.entry_id}_circulation", config_entry=entry,
        suggested_object_id="zirkulationspumpe_circulation_pump",
    )
    old_raw = registry.async_get_or_create(
        "sensor", "luxtronik_shi", f"{entry.entry_id}_raw_10502", config_entry=entry
    )
    kept = registry.async_get_or_create(
        "sensor", "luxtronik_shi", f"{entry.entry_id}_raw_10113", config_entry=entry,
        suggested_object_id="warmepumpe_diagnose_rohwert_10113",
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(old_switch.entity_id) is None
    assert registry.async_get(old_raw.entity_id) is None
    # the renamed raw value keeps its entity ID under the new key
    assert registry.async_get_entity_id("sensor", "luxtronik_shi", f"{entry.entry_id}_flow_calc_max") == kept.entity_id
    assert registry.async_get_entity_id("button", "luxtronik_shi", f"{entry.entry_id}_circulation")


# ------------------------------------------------------------------ overall group and levels
async def test_overall_mode_does_not_offer_setpoint(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Mode 1 is not implemented for the overall group: the option is not in the list, a write is refused by
    Home Assistant, and a foreign raw 1 shows no state (the diagnostics still show the raw value)."""
    entry = await _setup_with(hass, shi, ALL_FEATURES)
    registry = er.async_get(hass)
    entity_id = _entity_id(hass, entry, "select", OVERALL_MODE_KEY)
    registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).attributes["options"] == ["no_influence", "offset", "level"]
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": entity_id, "option": "setpoint"}, blocking=True
        )
    assert shi.holding[10065] == 0
    await hass.services.async_call(
        "select", "select_option", {"entity_id": entity_id, "option": "offset"}, blocking=True
    )
    assert shi.holding[10065] == 2
    shi.holding[10065] = 1  # another client wrote the unimplemented mode
    await _polls(entry, 3)
    assert hass.states.get(entity_id).state == "unknown"
    assert entry.runtime_data.data[OVERALL_MODE_KEY] == 1
    # the other mode selects offer all four options
    assert hass.states.get(_entity_id(hass, entry, "select", "cfg_heating_mode")).attributes["options"] == list(
        CONTROL_MODES
    )


async def test_level_select_offers_increased_once_and_shows_raw_2_as_increased(
    hass: HomeAssistant, shi: FakeSHI
) -> None:
    """Raw 1 and 2 use the same controller parameter (proven): one option, written as 1."""
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "select", "cfg_heating_level")
    assert hass.states.get(entity_id).attributes["options"] == list(LEVEL_OPTIONS) == [
        "normal", "increased", "decreased"
    ]
    await hass.services.async_call(
        "select", "select_option", {"entity_id": entity_id, "option": "increased"}, blocking=True
    )
    assert shi.holding[10003] == 1
    shi.holding[10003] = 2  # another client wrote python-luxtronik's "Increased2"
    await _polls(entry, 3)
    assert hass.states.get(entity_id).state == "increased"
    await hass.services.async_call(
        "select", "select_option", {"entity_id": entity_id, "option": "decreased"}, blocking=True
    )
    assert shi.holding[10003] == 3


async def test_level_raw_1_to_2_is_no_external_change(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Raw 1 and 2 are the same option: a switch between them is not reported; a real change still is."""
    from homeassistant.helpers import issue_registry as ir

    from .test_entity_semantics import _poll_settings

    entry = await _setup(hass, shi)
    shi.holding[10003] = 1
    await _poll_settings(hass, entry)  # someone else selected increased: reported
    issues = ir.async_get(hass)
    issue_id = f"{ISSUE_EXTERNAL_CHANGE}_{entry.entry_id}"
    assert issues.async_get_issue("luxtronik_shi", issue_id) is not None
    issues.async_delete("luxtronik_shi", issue_id)
    shi.holding[10003] = 2  # python-luxtronik's Increased2: the same parameter
    await _poll_settings(hass, entry)
    assert issues.async_get_issue("luxtronik_shi", issue_id) is None


@pytest.mark.parametrize("lang", ["en", "de"])
def test_level_and_overall_labels_say_what_the_firmware_does(lang: str) -> None:
    import json
    import pathlib

    texts = json.loads(
        (pathlib.Path(__file__).parent.parent / "custom_components/luxtronik_shi/translations" / f"{lang}.json")
        .read_text(encoding="utf-8")
    )["entity"]["select"]
    for key in ("cfg_heating_level", "cfg_dhw_level", "cfg_mk1_level", "cfg_overall_level"):
        states = texts[key]["state"]
        assert set(states) == {"normal", "increased", "decreased"}  # no "increased2"
        assert "Erhöhung" in states["increased"] and "Erhöhung" not in states["decreased"]
        assert "Absenkung" in states["decreased"]
    overall = texts[OVERALL_MODE_KEY]["state"]
    assert ("nicht umgesetzt" if lang == "de" else "not implemented") in overall["setpoint"]  # notices only
    assert ("Vorrang" if lang == "de" else "overrides") in overall["offset"]
    assert texts["cfg_heating_mode"]["state"]["setpoint"] != overall["setpoint"]
    for key in ("cfg_heating_mode", "cfg_dhw_mode", OVERALL_MODE_KEY):
        assert "off" not in texts[key]["state"] and texts[key]["state"]["no_influence"].startswith(
            "Keine Vorgabe" if lang == "de" else "No influence"
        )


# ------------------------------------------------------------------ resolved registers
def test_resolved_registers_follow_the_firmware_table() -> None:
    by_key = {reg.key: reg for reg in RESOLVED_IN_0_17}
    assert set(by_key) == {
        "hours_cooling", "hours_solar", "extra_dhw_setpoint", "extra_dhw_duration", "extra_dhw_remaining"
    }
    assert (by_key["hours_cooling"].address, by_key["hours_cooling"].dtype, by_key["hours_cooling"].unit) == (
        10410, "uint32", "h"
    )
    assert (by_key["hours_solar"].address, by_key["hours_solar"].device_class) == (10416, "duration")
    assert by_key["extra_dhw_setpoint"].address == 10500 and by_key["extra_dhw_setpoint"].scale == 0.1
    assert by_key["extra_dhw_setpoint"].device_class == "temperature"
    for key in ("extra_dhw_duration", "extra_dhw_remaining"):
        assert (by_key[key].dtype, by_key[key].unit, by_key[key].device_class) == ("int16", "min", "duration")
    assert by_key["extra_dhw_remaining"].state_class == "measurement"
    assert by_key["extra_dhw_duration"].state_class is None  # a setting, not a measurement
    for reg in RESOLVED_IN_0_17:
        assert reg.source and reg.source.startswith("proven:")
    # the raw word sensors of the same addresses are gone: one entity per proven value
    for key in ("raw_10410", "raw_10411", "raw_10416", "raw_10417", "raw_10500", "raw_10501", "raw_10502"):
        assert key not in BY_KEY and key in REMOVED_KEYS
    assert len({reg.address for reg in ALL_REGISTERS if reg.address in (10410, 10416, 10500, 10501, 10502)}) == 5
    # 10412 (pool hours, divisor 7200) stays a raw value until the factor is proven
    assert "raw_10412" in BY_KEY and not any(reg.address == 10412 for reg in RESOLVED_IN_0_17)
    # 10113 is a proper sensor now; the registry entry of raw_10113 is migrated to it
    assert "raw_10113" not in BY_KEY and RENAMED_KEYS["raw_10113"] == "flow_calc_max"
    calc = BY_KEY["flow_calc_max"]
    assert (calc.address, calc.dtype, calc.scale, calc.device_class) == (10113, "int16", 0.1, "temperature")
    assert calc.name_en.startswith("Flow: calculated maximum") and not calc.enabled_default and calc.diagnostic
    assert BY_KEY["heating_limit"].name_en == "Demand border" and BY_KEY["dhw_limit"].name_en == "Demand border"


def test_heat_quantity_counters_are_signed_32_bit() -> None:
    for key in ("energy_th_total", "energy_th_heating", "energy_th_dhw", "energy_th_cooling", "energy_th_pool"):
        assert BY_KEY[key].dtype == "int32" and BY_KEY[key].width == 2
    assert decode(BY_KEY["energy_th_total"], [0xFFFF, 0xFFFF]) == -0.1
    assert decode(BY_KEY["energy_th_total"], [0, 200]) == 20.0
    for key in ("energy_el_total", "energy_el_heating"):
        assert BY_KEY[key].dtype == "uint32"
    assert decode(BY_KEY["energy_el_total"], [0xFFFF, 0xFFFF]) == 429496729.5


async def test_resolved_sensors_read_the_fake_values(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.input.update({10410: 0, 10411: 12, 10416: 0, 10417: 7, 10500: 550, 10501: 60, 10502: 15})
    entry = await _setup_with(hass, shi, ALL_FEATURES)
    registry = er.async_get(hass)
    for key in ("hours_cooling", "hours_solar", "extra_dhw_setpoint", "extra_dhw_duration"):
        registry.async_update_entity(_entity_id(hass, entry, "sensor", key), disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    expected = {
        "hours_cooling": "12",
        "hours_solar": "7",
        "extra_dhw_setpoint": "55.0",
        "extra_dhw_duration": "60",
        "extra_dhw_remaining": "15",
    }
    for key, value in expected.items():
        assert hass.states.get(_entity_id(hass, entry, "sensor", key)).state == value, key
    # no raw twin exists for these addresses any more
    for raw_key in ("raw_10410", "raw_10411", "raw_10416", "raw_10500", "raw_10502"):
        assert registry.async_get_entity_id("sensor", "luxtronik_shi", f"{entry.entry_id}_{raw_key}") is None
    assert [reg.address for reg in entry.runtime_data.polled_registers if reg.address == 10502] == [10502]


async def test_flow_calc_max_reads_the_fake_value(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.input[10113] = 257
    entry = await _setup(hass, shi)
    registry = er.async_get(hass)
    entity_id = _entity_id(hass, entry, "sensor", "flow_calc_max")
    assert registry.async_get(entity_id).disabled_by is not None  # diagnostic, disabled by default
    registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "25.7"


async def test_solar_equipment_flag_and_option(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.discrete[10004] = True
    entry = await _setup_with(hass, shi, ALL_FEATURES)
    assert hass.states.get(_entity_id(hass, entry, "binary_sensor", "cap_solar")).state == "on"
    assert "hours_solar" in {reg.key for reg in entry.runtime_data.registers}
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["features"]["capability_flags"]["solar"] is True
    assert diag["controller_parameters_not_readable"]["enable_shi"]["parameter"] == ENABLE_SHI_PARAMETER == 1161


async def test_without_solar_the_hour_counter_is_not_polled(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup_with(hass, shi, ["mk1"])
    keys = {reg.key for reg in entry.runtime_data.registers}
    assert "hours_solar" not in keys and "hours_cooling" not in keys
    assert "cap_solar" in keys  # the flag itself is always read (pre-fills the option)


def test_deferred_keys_are_exactly_the_hot_water_group() -> None:
    """The pending map covers t2 items 5, 6, 7 and 0x27 only (10005-10008)."""
    assert {BY_KEY[key].address for key in DEFERRED_KEYS} == {10005, 10006, 10007, 10008}


async def test_watchdog_outage_reverts_to_proven_defaults(hass: HomeAssistant, shi: FakeSHI, clock: Clock) -> None:
    """The restore recognises the proven defaults of every group member (mode 0, setpoint 350) as a reset."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_setpoint", 300)
    await _write(entry, "cfg_heating_offset", 0x10000 - 20)
    outage = Outage(entry.runtime_data)
    outage.down()
    await entry.runtime_data.async_refresh()
    shi.holding.update({10000: 0, 10001: 350, 10002: 0})
    clock.tick(timedelta(seconds=1))
    outage.up()
    await _polls(entry)
    assert (shi.holding[10000], shi.holding[10001], shi.holding[10002]) == (1, 300, 0x10000 - 20)


_WRITABLE_WITH_DEFAULT = sorted(
    reg.key for reg in ALL_REGISTERS if reg.kind == "holding" and reg.reset_default is not None
)


@pytest.mark.parametrize("key", _WRITABLE_WITH_DEFAULT)
async def test_writing_exactly_the_default_is_never_reported_as_reverted(
    hass: HomeAssistant, shi: FakeSHI, caplog: pytest.LogCaptureFixture, key: str
) -> None:
    """A legitimate write of the firmware default (DHW 40.0 degC, heating 35.0 degC, cooling 20.0 degC, power
    limit 30.0 kW, any mode/offset/level/block/switch 0) reads back the default and must not raise; neither when
    the write is ignored (error 816: the previous value stays) nor while the hot water group defers it."""
    reg = BY_KEY[key]
    entry = await _setup(hass, shi)
    other = reg.reset_default + 1 if reg.platform != "number" else encode_int16(reg.max_value, reg.scale)
    for case in ("taken", "ignored", "deferred"):
        shi.ignored_writes = {reg.address} if case == "ignored" else set()
        shi.deferred = {reg.address} if case == "deferred" and key in DEFERRED_KEYS else set()
        shi.pending.pop(reg.address, None)
        shi.holding[reg.address] = other
        with caplog.at_level(logging.WARNING):
            await _write(entry, key, reg.reset_default)  # never raises
        assert "reset the register to its default" not in caplog.text
        if case == "taken":
            assert shi.holding[reg.address] == reg.reset_default
