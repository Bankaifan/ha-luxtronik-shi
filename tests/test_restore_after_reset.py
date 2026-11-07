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

MODE, OFFSET, LEVEL, BLOCK = 10000, 10002, 10003, 10050


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
    await _write(entry, "heating_block", 1)
    assert entry.runtime_data.remembered == {"cfg_heating_mode": 1, "cfg_heating_level": 2, "heating_block": 1}
    before = len(_writes(shi))

    with caplog.at_level(logging.WARNING):
        await _reboot(entry, shi, {MODE: 0, LEVEL: 0, BLOCK: 0})

    assert (shi.holding[MODE], shi.holding[LEVEL], shi.holding[BLOCK]) == (1, 2, 1)
    assert len(_writes(shi)) == before + 3  # one restore write per key
    reads = [r for r in shi.requests if r[0] == 3 and r[1] == MODE and r[2] == 1]
    assert reads, "restore must read the value back"
    data = entry.runtime_data.data
    assert data["cfg_heating_mode"] == 1 and data["cfg_heating_level"] == 2
    assert "restored cfg_heating_level=2, cfg_heating_mode=1, heating_block=1" in caplog.text
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
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    await _write(entry, "heating_block", 1)
    await _reboot(entry, shi, {MODE: 0, LEVEL: 3, BLOCK: 0})
    assert (shi.holding[MODE], shi.holding[LEVEL], shi.holding[BLOCK]) == (1, 3, 1)
    assert "cfg_heating_level" not in entry.runtime_data.remembered


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


async def test_wrong_read_back_is_not_retried(hass: HomeAssistant, shi: FakeSHI, monkeypatch) -> None:
    entry = await _setup(hass, shi)
    await _write(entry, "cfg_heating_mode", 1)
    await _write(entry, "cfg_heating_level", 2)
    attempts: list[int] = []

    async def ignored(address, value):  # the controller accepts the request but keeps 0
        attempts.append(address)

    monkeypatch.setattr(entry.runtime_data.client, "write_register", ignored)
    await _reboot(entry, shi, {MODE: 0, LEVEL: 0})
    await _polls(entry, 4)
    assert sorted(attempts) == [MODE, LEVEL]
    assert entry.runtime_data.remembered == {}


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
