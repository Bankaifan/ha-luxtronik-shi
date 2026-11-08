"""Restore after a device reset: re-apply values this integration wrote, only on evidence of a reset."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik_shi import coordinator as coordinator_module
from custom_components.luxtronik_shi.const import CONF_SLAVE, DOMAIN, RESTORE_RETRY_ATTEMPTS
from custom_components.luxtronik_shi.coordinator import restore_store_key
from custom_components.luxtronik_shi.diagnostics import async_get_config_entry_diagnostics
from custom_components.luxtronik_shi.modbus_client import ModbusCommError
from custom_components.luxtronik_shi.registers import BY_KEY

from .fake_shi import FakeSHI
from .test_integration import _entity_id
from .test_repairs import Clock, Outage

MODE, SETPOINT, OFFSET, LEVEL, DHW_MODE, BLOCK, EXTRA_DHW = 10000, 10001, 10002, 10003, 10005, 10050, 10071
DHW_SETPOINT = 10006
ROOM_SETPOINT = 10060


class Mono:
    """Controllable monotonic clock for the in-session gap (asyncio keeps the real one)."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def mono(monkeypatch: pytest.MonkeyPatch) -> Mono:
    fake = Mono()
    monkeypatch.setattr(coordinator_module, "_monotonic", fake)
    return fake


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


async def _drop_connections(shi: FakeSHI) -> None:
    for writer in list(shi._writers):
        writer.close()
    await asyncio.sleep(0.3)


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


async def test_two_zeros_without_outage_are_external(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Rule 1 (review probe p2): while polling continuously nothing can be reverted, so zeros are external."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    before = len(_writes(shi))
    shi.holding.update({MODE: 0, LEVEL: 0})
    await _polls(entry)
    assert (shi.holding[MODE], shi.holding[LEVEL]) == (0, 0)
    assert len(_writes(shi)) == before
    assert entry.runtime_data.remembered == {}


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
    assert "cfg_heating_level was changed outside this integration (2 -> 0)" in caplog.text
    # A later reboot has nothing left to restore.
    await _reboot(entry, shi, {MODE: 0})
    assert len(_writes(shi)) == before


async def test_partial_revert_after_outage_restores_nothing(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Rule 2: a real revert changes every SHI value at once. Here the level reads 3, not its reset value 0, so it
    is no reset: the changed values are forgotten (with their circuit's mode), nothing is restored."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 450)
    before = len(_writes(shi))
    await _reboot(entry, shi, {MODE: 0, LEVEL: 3, DHW_MODE: 0})
    assert (shi.holding[MODE], shi.holding[LEVEL], shi.holding[DHW_MODE]) == (0, 3, 0)
    assert len(_writes(shi)) == before
    assert entry.runtime_data.remembered == {"cfg_dhw_setpoint": 450}


async def test_single_remembered_mode_after_outage_is_restored(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Rule 2: outage plus all-of-one is the evidence; a single remembered mode reading 0 is restored."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _reboot(entry, shi, {MODE: 0})
    assert shi.holding[MODE] == 1
    assert entry.runtime_data.remembered == {"cfg_heating_mode": 1}


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


async def test_wrong_read_back_is_retried_then_forgotten(
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
        await _polls(entry, 8)
    # The level is retried once per poll, at most 5 times; the mode of its circuit waits and is never tried.
    assert attempts == [LEVEL] * RESTORE_RETRY_ATTEMPTS
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


async def test_restore_after_home_assistant_restart(
    hass: HomeAssistant, shi: FakeSHI, clock: Clock, hass_storage
) -> None:
    """Home Assistant down longer than the watchdog: the values are restored from the store."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    assert hass_storage[restore_store_key(entry.entry_id)]["data"]["values"] == {
        "cfg_heating_mode": 1,
        "cfg_heating_level": 2,
    }
    assert await hass.config_entries.async_unload(entry.entry_id)
    clock.tick(timedelta(seconds=900))
    shi.holding.update({MODE: 0, LEVEL: 0})  # watchdog expired while Home Assistant was down

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert (shi.holding[MODE], shi.holding[LEVEL]) == (1, 2)
    assert entry.runtime_data.data["cfg_heating_mode"] == 1


async def test_value_set_back_to_neutral_is_not_restored(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    mode = _entity_id(hass, entry, "select", "cfg_heating_mode")
    level = _entity_id(hass, entry, "select", "cfg_heating_level")
    for entity_id, option in ((mode, "setpoint"), (level, "decreased"), (mode, "no_influence"), (level, "normal")):
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
    assert diag["restore_after_reset"] == {"enabled": True, "remembered": {"cfg_heating_mode": 1}, "learned": {}}
    assert diag["connection"] == {"reconnects": 0, "last_reconnect": None, "reconnect_is_outage_signal": True}


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
    """Review probe p5: a user write that arrives while a restore runs is serialised after it. Deterministic: the
    user task is started inside the first restore write and given time to reach the lock before the restore goes on."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    original = coordinator.client.write_register
    tasks: list[asyncio.Task] = []
    order: list[tuple[int, int]] = []

    async def wrapped(address, value):
        order.append((address, value))
        await original(address, value)
        if not tasks:  # first restore write: the user sets the level now
            tasks.append(hass.async_create_task(coordinator.async_write(BY_KEY["cfg_heating_level"], 3)))
            for _ in range(10):
                await asyncio.sleep(0)
            assert not tasks[0].done()  # it waits for the lock

    monkeypatch.setattr(coordinator.client, "write_register", wrapped)
    await _reboot(entry, shi, {MODE: 0, LEVEL: 0})
    await tasks[0]
    assert order == [(LEVEL, 2), (MODE, 1), (LEVEL, 3)]  # restore (values, then mode), then the user write
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
    """Only the one-time adoption marker is written at setup; polls write nothing while nothing is remembered."""
    entry = await _setup(hass, shi)
    key = restore_store_key(entry.entry_id)
    stored = dict(hass_storage[key]["data"])
    clock.tick(timedelta(seconds=120))
    await _polls(entry, 2)
    assert hass_storage[key]["data"] == stored
    assert "last_poll" not in stored


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
    assert entry.runtime_data.remembered == {}  # dropped at load, before any poll could act
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
    await _polls(entry, 6)  # retried until the attempts run out
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


async def test_offset_changed_after_outage_is_external(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Offsets read 0 after a revert. An offset at another non-zero value means no reset: nothing is restored."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 2)
    await _write(entry, "cfg_heating_offset", 20)
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 450)
    before = len(_writes(shi))
    await _reboot(entry, shi, {MODE: 0, OFFSET: 30, DHW_MODE: 0})
    assert (shi.holding[MODE], shi.holding[OFFSET], shi.holding[DHW_MODE]) == (0, 30, 0)
    assert len(_writes(shi)) == before
    assert entry.runtime_data.remembered == {"cfg_dhw_setpoint": 450}


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


# ---------------------------------------------------------------- reset detection v2


async def test_network_blip_with_unchanged_values_does_nothing(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 450)
    before = len(_writes(shi))
    await _reboot(entry, shi, {})
    assert len(_writes(shi)) == before
    assert entry.runtime_data.remembered == {"cfg_heating_mode": 1, "cfg_dhw_setpoint": 450}


async def test_blip_with_one_external_change_is_forgotten(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Outage, but the hot water mode still reads 1: not every value reverted, so the zero is someone else's."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_dhw_mode", 1)
    before = len(_writes(shi))
    await _reboot(entry, shi, {MODE: 0})
    assert (shi.holding[MODE], shi.holding[DHW_MODE]) == (0, 1)
    assert len(_writes(shi)) == before
    assert entry.runtime_data.remembered == {"cfg_dhw_mode": 1}


async def test_reconnect_without_failed_poll_counts_as_outage(hass: HomeAssistant, shi: FakeSHI) -> None:
    """A reboot shorter than the poll interval: the TCP connection drops and is re-established before the next
    poll, which succeeds. The reconnect is the outage signal."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    reconnects = coordinator.client.reconnects
    shi.holding.update({MODE: 0, LEVEL: 0})
    await _drop_connections(shi)  # the controller drops every connection while rebooting
    await _polls(entry)
    assert coordinator.last_update_success
    assert coordinator.client.reconnects > reconnects
    assert (shi.holding[MODE], shi.holding[LEVEL]) == (1, 2)


async def test_setpoint_reset_value_is_learned_and_then_required(
    hass: HomeAssistant, shi: FakeSHI, clock: Clock, hass_storage, caplog: pytest.LogCaptureFixture
) -> None:
    """Rule 3: after a confirmed reset the value a setpoint reverted to is learned. A later reset is only one if
    the setpoint reads exactly that value; another value is an external change (and its mode is not restored)."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 540)
    await _reboot(entry, shi, {DHW_MODE: 0, DHW_SETPOINT: 500})
    assert (shi.holding[DHW_MODE], shi.holding[DHW_SETPOINT]) == (1, 540)
    assert coordinator._learned == {"cfg_dhw_setpoint": 500}
    assert hass_storage[restore_store_key(entry.entry_id)]["data"]["learned"] == {"cfg_dhw_setpoint": 500}

    clock.tick(timedelta(seconds=1000))  # past the cooldown
    await _reboot(entry, shi, {DHW_MODE: 0, DHW_SETPOINT: 500})  # same learned value: a reset
    assert (shi.holding[DHW_MODE], shi.holding[DHW_SETPOINT]) == (1, 540)

    clock.tick(timedelta(seconds=1000))
    before = len(_writes(shi))
    shi.holding.update({DHW_MODE: 0, DHW_SETPOINT: 480})  # not the learned value: someone else
    await _drop_connections(shi)  # only a reconnect, no failed poll: no relearning
    with caplog.at_level(logging.WARNING):
        await _polls(entry)
    assert (shi.holding[DHW_MODE], shi.holding[DHW_SETPOINT]) == (0, 480)
    assert len(_writes(shi)) == before
    assert coordinator.remembered == {}
    assert "cfg_dhw_setpoint=480 (learned 500)" in caplog.text
    assert coordinator.learned == {"cfg_dhw_setpoint": 500}


async def test_learned_value_survives_a_restart(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 540)
    await _reboot(entry, shi, {DHW_MODE: 0, DHW_SETPOINT: 500})
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data._learned == {"cfg_dhw_setpoint": 500}


# ---------------------------------------------------------------- review of v2


async def test_stale_learned_value_is_relearned_after_a_real_reboot(
    hass: HomeAssistant, shi: FakeSHI, clock: Clock, caplog: pytest.LogCaptureFixture
) -> None:
    """Review q3: a wrong learned value would block every later restore. A reboot with failed polls and every
    remembered mode at 0 is strong enough to restore anyway and replace the learned value."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    coordinator._learned = {"cfg_dhw_setpoint": 480}  # poisoned earlier
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 540)
    with caplog.at_level(logging.INFO):
        await _reboot(entry, shi, {DHW_MODE: 0, DHW_SETPOINT: 450})
    assert (shi.holding[DHW_MODE], shi.holding[DHW_SETPOINT]) == (1, 540)
    assert coordinator.learned == {"cfg_dhw_setpoint": 450}
    assert "relearned reset value of cfg_dhw_setpoint: 450 (was 480" in caplog.text


async def test_no_relearning_when_a_mode_did_not_revert(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    coordinator._learned = {"cfg_dhw_setpoint": 480}
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 540)
    await _write(entry, "cfg_heating_mode", 1)
    before = len(_writes(shi))
    await _reboot(entry, shi, {DHW_MODE: 0, DHW_SETPOINT: 450})  # heating mode still 1: no reset
    assert len(_writes(shi)) == before
    assert coordinator.learned == {"cfg_dhw_setpoint": 480}


async def test_reconnects_on_most_polls_stop_counting_as_outage(
    hass: HomeAssistant, shi: FakeSHI, caplog: pytest.LogCaptureFixture
) -> None:
    """Review q6: if the SHI closed the connection between polls, every poll would look like an outage. After 3
    reconnects in 5 polls the signal is switched off for the session (warned once)."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    await _write(entry, "cfg_heating_mode", 1)
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            await _drop_connections(shi)
            await _polls(entry, 1)
        assert not coordinator.reconnect_signal_active
        shi.holding[MODE] = 0  # external off while polls succeed, with a reconnect
        await _drop_connections(shi)
        await _polls(entry, 3)
    assert shi.holding[MODE] == 0
    assert coordinator.remembered == {}
    assert caplog.text.count("no longer treated as a device reset signal") == 1


async def test_unavailable_remembered_key_is_dropped(hass: HomeAssistant, shi: FakeSHI, hass_storage) -> None:
    """Review q7: a remembered register that becomes unavailable is forgotten (and persisted), so it cannot block
    the restore of the others."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_setpoint", 350)
    await _write(entry, "cfg_dhw_setpoint", 500)
    del shi.holding[DHW_SETPOINT]
    await _polls(entry, 2)
    assert "cfg_dhw_setpoint" not in entry.runtime_data.remembered
    assert "cfg_dhw_setpoint" not in hass_storage[restore_store_key(entry.entry_id)]["data"]["values"]
    await _reboot(entry, shi, {MODE: 0, SETPOINT: 200})
    assert (shi.holding[MODE], shi.holding[SETPOINT]) == (1, 350)


async def test_unseen_remembered_key_blocks_the_restore(hass: HomeAssistant, shi: FakeSHI, monkeypatch) -> None:
    """N3: a remembered register outside the heating block (room setpoint, 10060) is not read in the window: the
    window is incomplete, so no reset and nothing restored, although the heating mode alone would qualify."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_room_setpoint", 250)
    blocks = coordinator._blocks
    skipped = [b for b in blocks if any(r.key == "cfg_room_setpoint" for r in b.registers)]
    assert skipped and all(r.key != "cfg_heating_mode" for b in skipped for r in b.registers)
    monkeypatch.setattr(coordinator, "_blocks", [b for b in blocks if b not in skipped])
    before = len(_writes(shi))
    await _reboot(entry, shi, {MODE: 0, ROOM_SETPOINT: 210})
    assert shi.holding[MODE] == 0
    assert len(_writes(shi)) == before


async def test_7fff_is_never_a_reset_value(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Review q8: 0x7FFF means "not available"; it is neither a reverted setpoint nor learned."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_setpoint", 350)
    before = len(_writes(shi))
    await _reboot(entry, shi, {MODE: 0, SETPOINT: 0x7FFF})
    assert len(_writes(shi)) == before
    assert entry.runtime_data.learned == {}


async def test_setpoint_reading_zero_after_outage_is_not_reverted(hass: HomeAssistant, shi: FakeSHI) -> None:
    """N9: setpoints never revert to 0, so a zero setpoint after an outage means no reset."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_setpoint", 300)
    before = len(_writes(shi))
    await _reboot(entry, shi, {MODE: 0, SETPOINT: 0})
    assert len(_writes(shi)) == before
    assert entry.runtime_data.remembered == {}


@pytest.mark.parametrize(("interval", "restored"), [(500, False), (601, True)])
async def test_watchdog_between_two_polls_of_a_long_interval(
    hass: HomeAssistant, shi: FakeSHI, mono: Mono, interval: int, restored: bool
) -> None:
    """Review q9: the watchdog can expire between two successful polls; more than 600 s (monotonic) since the
    previous successful poll counts as an outage."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _polls(entry, 1)
    shi.holding[MODE] = 0
    mono.now += interval
    await _polls(entry, 2)
    assert (shi.holding[MODE] == 1) is restored


async def test_wall_clock_step_is_no_gap(hass: HomeAssistant, shi: FakeSHI, clock: Clock, mono: Mono) -> None:
    """Review q15: an NTP step of 15 minutes between two 30 s polls is no watchdog gap; the change is external."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _polls(entry, 1)
    shi.holding[MODE] = 0
    clock.tick(timedelta(minutes=15))
    mono.now += 30
    await _polls(entry, 2)
    assert shi.holding[MODE] == 0
    assert entry.runtime_data.remembered == {}


async def test_learned_values_are_exempt_from_the_age_limit(
    hass: HomeAssistant, shi: FakeSHI, clock: Clock
) -> None:
    """N8: remembered values older than 24 h are dropped, learned reset values are device facts and kept."""
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 540)
    await _reboot(entry, shi, {DHW_MODE: 0, DHW_SETPOINT: 500})
    assert await hass.config_entries.async_unload(entry.entry_id)
    clock.tick(timedelta(hours=25))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.remembered == {}
    assert entry.runtime_data.learned == {"cfg_dhw_setpoint": 500}



async def test_no_relearning_without_a_non_zero_mode(hass: HomeAssistant, shi: FakeSHI) -> None:
    """R2: relearning needs a remembered mode or level that was non-zero and reads 0. With the hot water mode
    remembered as `off`, a setpoint that differs from its learned value is not relearned and nothing is written."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    coordinator._learned = {"cfg_dhw_setpoint": 450}
    await _write(entry, "cfg_dhw_mode", 0)
    await _write(entry, "cfg_dhw_setpoint", 540)
    before = len(_writes(shi))
    await _reboot(entry, shi, {DHW_SETPOINT: 480})
    assert len(_writes(shi)) == before
    assert coordinator.learned == {"cfg_dhw_setpoint": 450}


# ---------------------------------------------------------------- maximum scan interval (5 minutes)


async def test_options_flow_caps_scan_interval_at_300(hass: HomeAssistant, shi: FakeSHI) -> None:
    """The SHI watchdog drops SHI values after 600 s without access, so polls at most every 300 s."""
    import voluptuous as vol
    from homeassistant.data_entry_flow import FlowResultType

    entry = await _setup(hass, shi, restore=False)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    with pytest.raises(vol.Invalid):
        await hass.config_entries.options.async_configure(result["flow_id"], {"scan_interval": 301})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"scan_interval": 300})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_longer_stored_interval_is_clamped_with_a_warning(
    hass: HomeAssistant, shi: FakeSHI, caplog: pytest.LogCaptureFixture
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WP",
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
        options={"scan_interval": 600, "restore_after_reset": True},
    )
    entry.add_to_hass(hass)
    with caplog.at_level(logging.WARNING):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.runtime_data.update_interval.total_seconds() == 300
    assert entry.options["scan_interval"] == 600  # stored option kept (no options migration)
    assert entry.runtime_data.restore_enabled
    assert "update interval 600 s is longer than the maximum of 300 s" in caplog.text
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["data_schema"]({})["scan_interval"] == 300  # the form offers the maximum


# ---------------------------------------------------------------- adopt the device values when switched on


async def test_adopts_device_values_when_switched_on(
    hass: HomeAssistant, shi: FakeSHI, caplog: pytest.LogCaptureFixture
) -> None:
    """Owner case: heating mode `offset` with offset 0, hot water mode `setpoint` at 54.0 °C. The modes and the
    hot water setpoint are adopted, the offset 0 is not (nothing to restore), the heating setpoint neither (its
    mode is not `setpoint`, so it may be an unset boot default)."""
    shi.holding.update({MODE: 2, OFFSET: 0, DHW_MODE: 1, DHW_SETPOINT: 540})
    with caplog.at_level(logging.INFO):
        entry = await _setup(hass, shi)
    assert entry.runtime_data.remembered == {"cfg_dhw_mode": 1, "cfg_dhw_setpoint": 540, "cfg_heating_mode": 2}
    assert "adopted the current device values: cfg_dhw_mode=1, cfg_dhw_setpoint=540, cfg_heating_mode=2" in caplog.text
    await _reboot(entry, shi, {MODE: 0, DHW_MODE: 0, DHW_SETPOINT: 500})
    assert (shi.holding[MODE], shi.holding[DHW_MODE], shi.holding[DHW_SETPOINT]) == (2, 1, 540)


async def test_setpoint_with_its_mode_off_is_not_adopted(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.holding.update({DHW_MODE: 0, DHW_SETPOINT: 540, MODE: 2, SETPOINT: 350})
    entry = await _setup(hass, shi)
    assert entry.runtime_data.remembered == {"cfg_heating_mode": 2}


async def test_no_second_adoption_after_reload(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.holding.update({DHW_MODE: 1, DHW_SETPOINT: 540})
    entry = await _setup(hass, shi)
    assert entry.runtime_data.remembered == {"cfg_dhw_mode": 1, "cfg_dhw_setpoint": 540}
    shi.holding[MODE] = 2  # set by someone else later
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert "cfg_heating_mode" not in entry.runtime_data.remembered


async def test_switching_on_in_the_options_adopts(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.holding.update({DHW_MODE: 1, DHW_SETPOINT: 540})
    entry = await _setup(hass, shi, restore=False)
    assert entry.runtime_data.remembered == {}
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 30, "restore_after_reset": True}
    )
    await hass.async_block_till_done()
    assert entry.runtime_data.remembered == {"cfg_dhw_mode": 1, "cfg_dhw_setpoint": 540}


async def test_option_off_adopts_and_stores_nothing(hass: HomeAssistant, shi: FakeSHI, hass_storage) -> None:
    shi.holding.update({MODE: 2, DHW_MODE: 1, DHW_SETPOINT: 540})
    entry = await _setup(hass, shi, restore=False)
    await _polls(entry)
    assert entry.runtime_data.remembered == {}
    assert restore_store_key(entry.entry_id) not in hass_storage
    assert [r for r in shi.requests if r[0] == 6] == []


async def test_7fff_is_never_adopted(hass: HomeAssistant, shi: FakeSHI) -> None:
    """A2: 0x7FFF means "not available"; it is not adopted (modes) and a setpoint at 0x7FFF is not either."""
    shi.holding.update({MODE: 0x7FFF, DHW_MODE: 1, DHW_SETPOINT: 0x7FFF, LEVEL: 2})
    entry = await _setup(hass, shi)
    assert entry.runtime_data.remembered == {"cfg_dhw_mode": 1, "cfg_heating_level": 2}


async def test_old_store_without_marker_keeps_its_values(
    hass: HomeAssistant, shi: FakeSHI, clock: Clock, hass_storage, monkeypatch
) -> None:
    """A5: a store from before adoption (values, no marker). The gap since its last poll opens a reset window that
    is still open when the adoption runs (the room setpoint is not read in that poll). The remembered heating mode 1
    must be kept, not replaced by the device value 2 the adoption would otherwise take."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="WP",
        unique_id=f"127.0.0.1:{shi.port}:1",
        data={CONF_HOST: "127.0.0.1", CONF_PORT: shi.port, CONF_SLAVE: 1},
        options={"scan_interval": 30, "restore_after_reset": True},
    )
    key = restore_store_key(entry.entry_id)
    last_poll = (clock.now - timedelta(minutes=15)).isoformat()
    hass_storage[key] = {
        "version": 1, "minor_version": 1, "key": key,
        "data": {"values": {"cfg_heating_mode": 1, "cfg_room_setpoint": 250}, "last_poll": last_poll},
    }
    shi.holding.update({MODE: 2, DHW_MODE: 1})
    original = coordinator_module.LuxtronikCoordinator._read_block
    skipped: list[int] = []

    async def first_poll_skips_room(self, block):
        if any(r.key == "cfg_room_setpoint" for r in block.registers) and not skipped:
            skipped.append(block.start)
            return
        await original(self, block)

    monkeypatch.setattr(coordinator_module.LuxtronikCoordinator, "_read_block", first_poll_skips_room)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    assert skipped and coordinator._window_left > 0  # the reset window is still open
    assert coordinator.remembered["cfg_heating_mode"] == 1  # kept, not replaced by the adoption
    assert coordinator.remembered["cfg_dhw_mode"] == 1  # other keys are adopted
    assert hass_storage[key]["data"]["adopted"] is True


async def test_overall_group_is_never_remembered_adopted_or_restored(hass: HomeAssistant, shi: FakeSHI) -> None:
    """cfg_overall_* (10065-10067) has unproven semantics and is out of the allow-list."""
    shi.holding.update({10065: 1, 10066: 20, 10067: 2})
    entry = await _setup(hass, shi)
    assert not any(k.startswith("cfg_overall") for k in entry.runtime_data.remembered)  # not adopted
    await _write(entry, "cfg_overall_mode", 2)
    await _write(entry, "cfg_overall_level", 1)
    await _write(entry, "cfg_heating_mode", 1)
    assert not any(k.startswith("cfg_overall") for k in entry.runtime_data.remembered)
    before = len(_writes(shi, 10065)) + len(_writes(shi, 10067))
    await _reboot(entry, shi, {MODE: 0, 10065: 0, 10066: 0, 10067: 0})
    assert shi.holding[MODE] == 1
    assert len(_writes(shi, 10065)) + len(_writes(shi, 10067)) == before
    assert (shi.holding[10065], shi.holding[10067]) == (0, 0)


# ---------------------------------------------------------------- info notice when base values change


def _notices(hass: HomeAssistant) -> dict:
    from homeassistant.components import persistent_notification

    return {
        k: v for k, v in persistent_notification._async_get_or_create_notifications(hass).items()
        if k.startswith("luxtronik_shi_base_values_changed")
    }


async def _relearn_both(entry, shi, heating: int, dhw: int) -> None:
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_setpoint", 300)
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 540)
    await _reboot(entry, shi, {MODE: 0, SETPOINT: heating, DHW_MODE: 0, DHW_SETPOINT: dhw})


async def test_relearn_of_two_setpoints_gives_one_notice(hass: HomeAssistant, shi: FakeSHI, clock: Clock) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    coordinator._learned = {"cfg_heating_setpoint": 350, "cfg_dhw_setpoint": 450}
    await _relearn_both(entry, shi, 360, 470)
    notices = _notices(hass)
    assert len(notices) == 1
    notice = next(iter(notices.values()))
    assert notice["title"] == "WP: base values of setpoints changed"
    message = notice["message"]
    assert "- WP Heating Setpoint: 35.0 °C -> 36.0 °C" in message
    assert "- WP Hot water Setpoint: 45.0 °C -> 47.0 °C" in message
    assert "- WP Hot water Setpoint: 54.0 °C" in message  # restored values listed
    assert "- WP Heating Mode: Setpoint" in message
    assert "No action is needed" in message
    assert "cfg_" not in message  # no raw keys

    clock.tick(timedelta(seconds=1000))  # a later relearn replaces the notice
    await _relearn_both(entry, shi, 370, 470)
    notices = _notices(hass)
    assert len(notices) == 1
    message = next(iter(notices.values()))["message"]
    assert "36.0 °C -> 37.0 °C" in message
    assert "Hot water Setpoint: 47.0" not in message  # only what changed this time


async def test_no_relearn_no_notice(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    await _relearn_both(entry, shi, 360, 470)  # first learning, nothing relearned
    assert entry.runtime_data.learned == {"cfg_heating_setpoint": 360, "cfg_dhw_setpoint": 470}
    assert _notices(hass) == {}


async def test_notice_in_german(hass: HomeAssistant, shi: FakeSHI) -> None:
    hass.config.language = "de"
    entry = await _setup(hass, shi)
    entry.runtime_data._learned = {"cfg_dhw_setpoint": 450}
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 540)
    await _reboot(entry, shi, {DHW_MODE: 0, DHW_SETPOINT: 470})
    notice = next(iter(_notices(hass).values()))
    assert notice["title"] == "WP: Grundwerte von Sollwerten geändert"
    assert "- WP Warmwasser Sollwert: 45,0 °C -> 47,0 °C" in notice["message"]
    assert "Es ist nichts zu tun" in notice["message"]
