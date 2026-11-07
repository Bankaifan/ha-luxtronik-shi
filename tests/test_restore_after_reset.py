"""Restore after a device reset: re-apply values this integration wrote, only on evidence of a reset."""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik_shi import coordinator as coordinator_module
from custom_components.luxtronik_shi.const import CONF_SLAVE, DOMAIN
from custom_components.luxtronik_shi.coordinator import restore_store_key
from custom_components.luxtronik_shi.diagnostics import async_get_config_entry_diagnostics
from custom_components.luxtronik_shi.modbus_client import ModbusCommError
from custom_components.luxtronik_shi.registers import BY_KEY

from .fake_shi import FakeSHI
from .test_integration import _entity_id
from .test_repairs import Clock, Outage

MODE, SETPOINT, OFFSET, LEVEL, DHW_MODE, BLOCK, EXTRA_DHW = 10000, 10001, 10002, 10003, 10005, 10050, 10071
DHW_SETPOINT = 10006


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(coordinator_module.dt_util, "utcnow", fake)
    return fake


async def _setup(hass: HomeAssistant, shi: FakeSHI, *, restore: bool = True) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WP",
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
        options={"scan_interval": 30, "restore_after_reset": restore},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _write(entry: MockConfigEntry, key: str, raw: int) -> None:
    await entry.runtime_data.async_write(BY_KEY[key], raw)


def _writes(shi: FakeSHI, address: int | None = None) -> list:
    return [r for r in shi.requests if r[0] == 6 and (address is None or r[1] == address)]


async def _polls(entry: MockConfigEntry, count: int = 3) -> None:
    for _ in range(count):
        await entry.runtime_data.async_refresh()


async def _reboot(entry: MockConfigEntry, shi: FakeSHI, reset: dict[int, int]) -> None:
    """Connection drops, the controller resets the given holdings, the connection comes back."""
    coordinator = entry.runtime_data
    outage = Outage(coordinator)
    outage.down()
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    shi.holding.update(reset)
    outage.up()
    await _polls(entry)
    assert coordinator.last_update_success


async def test_reboot_restores_with_read_back(
    hass: HomeAssistant, shi: FakeSHI, caplog: pytest.LogCaptureFixture
) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    await _write(entry, "cfg_dhw_mode", 1)
    assert entry.runtime_data.remembered == {"cfg_heating_mode": 1, "cfg_heating_level": 2, "cfg_dhw_mode": 1}
    before = len(_writes(shi))

    with caplog.at_level(logging.WARNING):
        await _reboot(entry, shi, {MODE: 0, LEVEL: 0, DHW_MODE: 0})

    assert (shi.holding[MODE], shi.holding[LEVEL], shi.holding[DHW_MODE]) == (1, 2, 1)
    assert len(_writes(shi)) == before + 3  # one restore write per key
    reads = [r for r in shi.requests if r[0] == 3 and r[1] == MODE and r[2] == 1]
    assert reads, "restore must read the value back"
    data = entry.runtime_data.data
    assert data["cfg_heating_mode"] == 1 and data["cfg_heating_level"] == 2
    assert "restored cfg_dhw_mode=1, cfg_heating_level=2, cfg_heating_mode=1" in caplog.text
    await _polls(entry, 4)
    assert len(_writes(shi)) == before + 3  # once per reset


async def test_two_zeros_without_outage_count_as_reset(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    shi.holding.update({MODE: 0, LEVEL: 0})
    await _polls(entry)
    assert (shi.holding[MODE], shi.holding[LEVEL]) == (1, 2)


async def test_single_external_change_is_adopted_and_forgotten(
    hass: HomeAssistant, shi: FakeSHI, caplog: pytest.LogCaptureFixture
) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    before = len(_writes(shi))

    with caplog.at_level(logging.INFO):
        shi.holding[MODE] = 2  # someone else switched to offset
        await _polls(entry)
        shi.holding[LEVEL] = 0  # and later the level back to normal: one zero, no outage
        await _polls(entry)

    assert len(_writes(shi)) == before
    assert (shi.holding[MODE], shi.holding[LEVEL]) == (2, 0)
    assert entry.runtime_data.remembered == {}
    assert "cfg_heating_mode was changed outside this integration (1 -> 2)" in caplog.text
    assert "cfg_heating_level read 0 without evidence of a device reset" in caplog.text
    # A later reboot has nothing left to restore.
    await _reboot(entry, shi, {MODE: 0})
    assert len(_writes(shi)) == before


async def test_external_non_zero_change_during_reset_is_not_overwritten(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Level of the heating circuit changed by someone else: kept, and (group rule) its mode is not restored."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 450)
    await _reboot(entry, shi, {MODE: 0, LEVEL: 3, DHW_MODE: 0})
    assert (shi.holding[MODE], shi.holding[LEVEL], shi.holding[DHW_MODE]) == (0, 3, 1)
    assert entry.runtime_data.remembered == {"cfg_dhw_mode": 1, "cfg_dhw_setpoint": 450}


async def test_single_remembered_register_is_ambiguous(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    before = len(_writes(shi))
    await _reboot(entry, shi, {MODE: 0})
    assert shi.holding[MODE] == 0
    assert len(_writes(shi)) == before
    assert entry.runtime_data.remembered == {}


async def test_outage_with_one_zero_and_a_neutral_value_restores(hass: HomeAssistant, shi: FakeSHI) -> None:
    """The reference setup: mode offset with offset 0. The outage is the second piece of evidence."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 2)
    await _write(entry, "cfg_heating_offset", 0)
    await _reboot(entry, shi, {MODE: 0})
    assert shi.holding[MODE] == 2
    assert len(_writes(shi, OFFSET)) == 1  # the neutral offset is never written again


async def test_option_off_writes_nothing(hass: HomeAssistant, shi: FakeSHI, hass_storage) -> None:
    entry = await _setup(hass, shi, restore=False)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    before = len(_writes(shi))
    await _reboot(entry, shi, {MODE: 0, LEVEL: 0})
    assert len(_writes(shi)) == before
    assert (shi.holding[MODE], shi.holding[LEVEL]) == (0, 0)
    assert entry.runtime_data.remembered == {}
    assert restore_store_key(entry.entry_id) not in hass_storage


async def test_failed_restore_write_is_not_retried(hass: HomeAssistant, shi: FakeSHI, monkeypatch) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    attempts: list[int] = []

    async def failing(address, value):
        attempts.append(address)
        raise ModbusCommError("simulated write failure")

    monkeypatch.setattr(entry.runtime_data.client, "write_register", failing)
    await _reboot(entry, shi, {MODE: 0, LEVEL: 0})
    await _polls(entry, 4)
    assert len(attempts) == 1  # connection lost: the second key is not tried, nothing is retried
    assert entry.runtime_data.remembered == {}


async def test_wrong_read_back_is_not_retried(
    hass: HomeAssistant, shi: FakeSHI, monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    attempts: list[int] = []

    async def ignored(address, value):  # the controller accepts the request but keeps 0
        attempts.append(address)

    monkeypatch.setattr(entry.runtime_data.client, "write_register", ignored)
    with caplog.at_level(logging.WARNING):
        await _reboot(entry, shi, {MODE: 0, LEVEL: 0})
        await _polls(entry, 4)
    assert attempts == [LEVEL]  # the level failed, so the mode of the same circuit is not tried (modes last)
    assert entry.runtime_data.remembered == {}
    assert "could not restore cfg_heating_level, cfg_heating_mode" in caplog.text
    assert "restored" not in caplog.text


async def test_reset_again_within_cooldown_is_not_restored(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    await _reboot(entry, shi, {MODE: 0, LEVEL: 0})
    assert (shi.holding[MODE], shi.holding[LEVEL]) == (1, 2)
    before = len(_writes(shi))
    await _reboot(entry, shi, {MODE: 0, LEVEL: 0})
    assert len(_writes(shi)) == before
    assert entry.runtime_data.remembered == {}


async def test_restore_after_home_assistant_restart(hass: HomeAssistant, shi: FakeSHI, hass_storage) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    assert hass_storage[restore_store_key(entry.entry_id)]["data"]["values"] == {
        "cfg_heating_mode": 1,
        "cfg_heating_level": 2,
    }
    assert await hass.config_entries.async_unload(entry.entry_id)
    shi.holding.update({MODE: 0, LEVEL: 0})  # watchdog expired while Home Assistant was down

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert (shi.holding[MODE], shi.holding[LEVEL]) == (1, 2)
    assert entry.runtime_data.data["cfg_heating_mode"] == 1


async def test_value_set_back_to_neutral_is_not_restored(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    mode = _entity_id(hass, entry, "select", "cfg_heating_mode")
    level = _entity_id(hass, entry, "select", "cfg_heating_level")
    for entity_id, option in ((mode, "setpoint"), (level, "increased2"), (mode, "off"), (level, "normal")):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": entity_id, "option": option}, blocking=True
        )
    assert entry.runtime_data.remembered == {"cfg_heating_mode": 0, "cfg_heating_level": 0}
    before = len(_writes(shi))
    await _reboot(entry, shi, {MODE: 0, LEVEL: 0})
    assert len(_writes(shi)) == before


async def test_failed_user_write_forgets_key(hass: HomeAssistant, shi: FakeSHI, monkeypatch) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)

    async def failing(address, value):
        raise ModbusCommError("simulated write failure")

    monkeypatch.setattr(entry.runtime_data.client, "write_register", failing)
    with pytest.raises(HomeAssistantError):
        await _write(entry, "cfg_heating_mode", 2)
    assert entry.runtime_data.remembered == {}


async def test_diagnostics_list_remembered_values(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["restore_after_reset"] == {"enabled": True, "remembered": {"cfg_heating_mode": 1}}


async def test_options_flow_toggles_option_and_clears_store(
    hass: HomeAssistant, shi: FakeSHI, hass_storage
) -> None:
    entry = await _setup(hass, shi, restore=False)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["data_schema"]({"scan_interval": 30})["restore_after_reset"] is False  # default off
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 30, "restore_after_reset": True}
    )
    await hass.async_block_till_done()
    assert entry.runtime_data.restore_enabled
    await _write(entry, "cfg_heating_mode", 1)
    assert restore_store_key(entry.entry_id) in hass_storage

    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 30, "restore_after_reset": False}
    )
    await hass.async_block_till_done()
    assert not entry.runtime_data.restore_enabled
    assert restore_store_key(entry.entry_id) not in hass_storage


async def _restart(hass: HomeAssistant, entry: MockConfigEntry, shi: FakeSHI, clock: Clock, downtime: int) -> None:
    """Home Assistant is down for ``downtime`` seconds; the SHI is not polled and resets heating mode."""
    assert await hass.config_entries.async_unload(entry.entry_id)
    clock.tick(timedelta(seconds=downtime))
    shi.holding[MODE] = 0
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_long_downtime_counts_as_outage(hass: HomeAssistant, shi: FakeSHI, clock: Clock, hass_storage) -> None:
    """Over the SHI watchdog (600 s) without polls: one zero is enough, like after an observed outage."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 2)
    await _write(entry, "cfg_heating_offset", 0)
    assert "last_poll" in hass_storage[restore_store_key(entry.entry_id)]["data"]
    await _restart(hass, entry, shi, clock, 700)
    assert shi.holding[MODE] == 2
    assert entry.runtime_data.remembered == {"cfg_heating_mode": 2, "cfg_heating_offset": 0}


async def test_short_restart_is_not_an_outage(hass: HomeAssistant, shi: FakeSHI, clock: Clock) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 2)
    await _write(entry, "cfg_heating_offset", 0)
    before = len(_writes(shi))
    await _restart(hass, entry, shi, clock, 120)
    assert shi.holding[MODE] == 0
    assert len(_writes(shi)) == before
    assert "cfg_heating_mode" not in entry.runtime_data.remembered


async def test_last_poll_time_is_written_at_most_once_a_minute(
    hass: HomeAssistant, shi: FakeSHI, clock: Clock, hass_storage
) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 2)
    key = restore_store_key(entry.entry_id)
    first = hass_storage[key]["data"]["last_poll"]
    clock.tick(timedelta(seconds=30))
    await _polls(entry, 1)
    assert hass_storage[key]["data"]["last_poll"] == first  # throttled
    clock.tick(timedelta(seconds=31))
    await _polls(entry, 1)
    assert hass_storage[key]["data"]["last_poll"] != first


async def test_setpoint_reverted_by_a_reset_is_restored_with_its_mode(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Review probe p3, new intent: the reboot reverts the setpoint to a non-zero default (firmware: setpoints go
    to their persisted or default value, modes to 0). With reset evidence in the window it is part of the reset,
    so setpoint and mode are both restored (values first, mode last)."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_setpoint", 350)
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 450)
    await _reboot(entry, shi, {MODE: 0, SETPOINT: 200, DHW_MODE: 0})
    assert (shi.holding[MODE], shi.holding[SETPOINT], shi.holding[DHW_MODE]) == (1, 350, 1)
    writes = [r[1] for r in _writes(shi)[-3:]]
    assert writes.index(SETPOINT) < writes.index(MODE)


async def test_owner_case_dhw_setpoint_and_offset_mode(hass: HomeAssistant, shi: FakeSHI) -> None:
    """DHW mode `setpoint` with 54.0 °C, heating mode `offset` with offset 0. The reboot sets both modes to 0 and
    the DHW setpoint to a default of 50.0 °C: both modes and the DHW setpoint come back, the offset is untouched."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 540)
    await _write(entry, "cfg_heating_mode", 2)
    await _write(entry, "cfg_heating_offset", 0)
    before = len(_writes(shi))
    await _reboot(entry, shi, {DHW_MODE: 0, DHW_SETPOINT: 500, MODE: 0})
    assert (shi.holding[DHW_MODE], shi.holding[DHW_SETPOINT], shi.holding[MODE], shi.holding[OFFSET]) == (1, 540, 2, 0)
    assert sorted(r[1] for r in _writes(shi)[before:]) == [MODE, DHW_MODE, DHW_SETPOINT]
    assert entry.runtime_data.remembered == {
        "cfg_dhw_mode": 1, "cfg_dhw_setpoint": 540, "cfg_heating_mode": 2, "cfg_heating_offset": 0
    }


async def test_heating_setpoint_reverted_to_default_is_restored(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_setpoint", 300)
    before = len(_writes(shi))
    await _reboot(entry, shi, {MODE: 0, SETPOINT: 350})
    assert (shi.holding[MODE], shi.holding[SETPOINT]) == (1, 300)
    assert [r[1] for r in _writes(shi)[before:]] == [SETPOINT, MODE]


async def test_setpoint_change_without_reset_evidence_is_external(hass: HomeAssistant, shi: FakeSHI) -> None:
    """No outage and only one zero: the non-zero setpoint change is someone else's, forgotten with its mode."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_setpoint", 300)
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 450)
    before = len(_writes(shi))
    shi.holding.update({MODE: 0, SETPOINT: 350})
    await _polls(entry)
    assert (shi.holding[MODE], shi.holding[SETPOINT]) == (0, 350)
    assert len(_writes(shi)) == before
    assert entry.runtime_data.remembered == {"cfg_dhw_mode": 1, "cfg_dhw_setpoint": 450}


@pytest.mark.parametrize(("key", "address"), [("heating_block", BLOCK), ("extra_dhw", EXTRA_DHW)])
async def test_blocks_and_extra_dhw_are_never_remembered_or_restored(
    hass: HomeAssistant, shi: FakeSHI, key: str, address: int
) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, key, 1)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    assert key not in entry.runtime_data.remembered
    before = len(_writes(shi, address))
    await _reboot(entry, shi, {MODE: 0, LEVEL: 0, address: 0})
    assert shi.holding[address] == 0  # the watchdog fail-safe (released) stays
    assert len(_writes(shi, address)) == before
    assert (shi.holding[MODE], shi.holding[LEVEL]) == (1, 2)


async def test_allow_list_only_names_existing_writable_keys() -> None:
    from custom_components.luxtronik_shi.const import RESTORE_KEYS

    assert RESTORE_KEYS <= {k for k, r in BY_KEY.items() if r.kind == "holding" and r.platform != "sensor"}
    assert not RESTORE_KEYS & {"heating_block", "dhw_block", "cooling_block", "pool_block", "circulation", "extra_dhw"}


async def test_user_write_during_restore_waits_and_wins(hass: HomeAssistant, shi: FakeSHI, monkeypatch) -> None:
    """Review probe p5: a user write that arrives while a restore runs is serialised after it."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    original = coordinator.client.write_register
    tasks = []

    async def wrapped(address, value):
        await original(address, value)
        if address == MODE and not tasks:  # the user sets the level while the restore is running
            tasks.append(hass.async_create_task(coordinator.async_write(BY_KEY["cfg_heating_level"], 3)))

    monkeypatch.setattr(coordinator.client, "write_register", wrapped)
    await _reboot(entry, shi, {MODE: 0, LEVEL: 0})
    await tasks[0]
    assert shi.holding[LEVEL] == 3
    assert coordinator.remembered["cfg_heating_level"] == 3  # store and device agree


async def test_restore_skips_key_written_since_snapshot(hass: HomeAssistant, shi: FakeSHI, monkeypatch) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    original = coordinator.client.write_register
    written: list[int] = []

    async def wrapped(address, value):
        written.append(address)
        if address == LEVEL:  # meanwhile Home Assistant set the mode to 2 (store updated, device not yet)
            coordinator._remembered["cfg_heating_mode"] = 2
        await original(address, value)

    monkeypatch.setattr(coordinator.client, "write_register", wrapped)
    await _reboot(entry, shi, {MODE: 0, LEVEL: 0})
    assert LEVEL in written and MODE not in written


async def test_user_write_with_different_read_back_is_not_remembered(
    hass: HomeAssistant, shi: FakeSHI, monkeypatch
) -> None:
    """The controller clamps or ignores the value: what it holds was not written by us, so it is not remembered."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    original = coordinator.client.write_register

    async def clamping(address, value):
        await original(address, min(value, 1))

    monkeypatch.setattr(coordinator.client, "write_register", clamping)
    await _write(entry, "cfg_heating_level", 2)
    assert shi.holding[LEVEL] == 1
    assert "cfg_heating_level" not in coordinator.remembered


@pytest.mark.parametrize(("downtime", "restored"), [(660, False), (661, True), (24 * 3600, True), (24 * 3600 + 1, False)])
async def test_watchdog_gap_boundary(
    hass: HomeAssistant, shi: FakeSHI, clock: Clock, downtime: int, restored: bool
) -> None:
    """The gap must exceed 600 s plus the 60 s save interval; beyond 24 hours the values are dropped."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 2)
    await _write(entry, "cfg_heating_offset", 0)
    await _restart(hass, entry, shi, clock, downtime)
    assert (shi.holding[MODE] == 2) is restored


async def test_last_poll_not_saved_while_nothing_is_remembered(
    hass: HomeAssistant, shi: FakeSHI, clock: Clock, hass_storage
) -> None:
    entry = await _setup(hass, shi)
    clock.tick(timedelta(seconds=120))
    await _polls(entry, 2)
    assert restore_store_key(entry.entry_id) not in hass_storage


async def test_group_rule_holds_across_windows(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Review probe p8: the setpoint was changed by another client long before the reboot. The mode is dropped
    with it and not restored over the default setpoint, until it is written through Home Assistant again."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_setpoint", 350)
    await _write(entry, "cfg_heating_level", 2)
    shi.holding[SETPOINT] = 400  # other client
    await _polls(entry)
    assert entry.runtime_data.remembered == {"cfg_heating_level": 2}
    await _reboot(entry, shi, {MODE: 0, SETPOINT: 200, LEVEL: 0})
    assert (shi.holding[MODE], shi.holding[SETPOINT]) == (0, 200)
    await _write(entry, "cfg_heating_mode", 1)  # written again through Home Assistant: restorable again
    await _write(entry, "cfg_heating_setpoint", 350)
    assert {"cfg_heating_mode", "cfg_heating_setpoint"} <= entry.runtime_data.remembered.keys()


@pytest.mark.parametrize("age", [timedelta(days=30), timedelta(hours=25)])
async def test_stale_store_is_dropped(
    hass: HomeAssistant, shi: FakeSHI, clock: Clock, hass_storage, age: timedelta
) -> None:
    """Review probe p7: values older than 24 hours are dropped at setup, even if two zeros follow."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    assert await hass.config_entries.async_unload(entry.entry_id)
    clock.tick(age)
    shi.holding.update({MODE: 0, LEVEL: 0})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await _polls(entry)
    assert (shi.holding[MODE], shi.holding[LEVEL]) == (0, 0)
    assert entry.runtime_data.remembered == {}
    assert hass_storage[restore_store_key(entry.entry_id)]["data"]["values"] == {}


async def test_mode_not_restored_when_its_setpoint_restore_fails(
    hass: HomeAssistant, shi: FakeSHI, monkeypatch
) -> None:
    """Review probe p10: modes are restored last, and not at all if a value of their circuit failed."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_setpoint", 350)
    original = coordinator.client.write_register

    async def clamping(address, value):
        await original(address, min(value, 300) if address == SETPOINT else value)

    monkeypatch.setattr(coordinator.client, "write_register", clamping)
    before = len(_writes(shi, MODE))
    await _reboot(entry, shi, {MODE: 0, SETPOINT: 200})  # setpoints revert to a non-zero default
    assert shi.holding[SETPOINT] == 300
    assert shi.holding[MODE] == 0
    assert len(_writes(shi, MODE)) == before
    assert coordinator.remembered == {}


async def test_lone_zero_forgets_the_mode_of_its_circuit(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Review probe p11: a level set to 0 by someone else (no outage) also forgets the circuit's mode."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    before = len(_writes(shi))
    shi.holding[LEVEL] = 0
    await _polls(entry)
    assert entry.runtime_data.remembered == {}
    assert len(_writes(shi)) == before


async def test_offset_changed_in_a_reset_window_is_external(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Only setpoints are proven to revert to a non-zero default. An offset reading another non-zero value in a
    confirmed reset window is someone else's change: forgotten, not restored (and the group rule drops its mode)."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 2)
    await _write(entry, "cfg_heating_offset", 20)
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 450)
    await _reboot(entry, shi, {MODE: 0, OFFSET: 30, DHW_MODE: 0})
    assert (shi.holding[MODE], shi.holding[OFFSET], shi.holding[DHW_MODE]) == (0, 30, 1)
    assert entry.runtime_data.remembered == {"cfg_dhw_mode": 1, "cfg_dhw_setpoint": 450}


async def test_setpoints_reading_zero_are_external_not_evidence(hass: HomeAssistant, shi: FakeSHI) -> None:
    """A setpoint never resets to 0 (outside its range): two setpoints at 0 are no reset, both are forgotten."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_setpoint", 300)
    await _write(entry, "cfg_dhw_setpoint", 450)
    before = len(_writes(shi))
    shi.holding.update({SETPOINT: 0, DHW_SETPOINT: 0})
    await _polls(entry)
    assert (shi.holding[SETPOINT], shi.holding[DHW_SETPOINT]) == (0, 0)
    assert len(_writes(shi)) == before
    assert entry.runtime_data.remembered == {}
