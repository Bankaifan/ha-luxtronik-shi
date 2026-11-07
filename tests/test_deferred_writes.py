"""Deferred writes of the hot water group and restore retries (firmware 3.92.3 pending map, fake SHI only)."""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.luxtronik_shi import coordinator as coordinator_module

from .fake_shi import FakeSHI
from .test_restore_after_reset import DHW_MODE, DHW_SETPOINT, MODE, _polls, _reboot, _setup, _write, _writes

DHW_BLOCK = 10051


class Mono:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def mono(monkeypatch: pytest.MonkeyPatch) -> Mono:
    fake = Mono()
    monkeypatch.setattr(coordinator_module, "_monotonic", fake)
    return fake


async def _later(hass: HomeAssistant, shi: FakeSHI, seconds: float) -> None:
    """Let ``seconds`` pass for the simulator (commits) and for Home Assistant timers (delayed read-back)."""
    shi.advance(seconds)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done()


def _deferred(shi: FakeSHI) -> FakeSHI:
    shi.deferred = {10005}  # measured: 10005 is taken with a delay; 10006 read back at once
    shi.block_refuses_dhw_mode = True
    return shi


async def test_user_write_committed_late_is_not_a_failure(hass: HomeAssistant, shi: FakeSHI) -> None:
    """The read-back right after the write still shows the old value; after 15 s the value is confirmed."""
    entry = await _setup(hass, _deferred(shi))
    coordinator = entry.runtime_data
    await _write(entry, "cfg_dhw_mode", 1)  # no error although the read-back reads 0
    assert shi.holding[DHW_MODE] == 0
    assert "cfg_dhw_mode" not in coordinator.remembered
    await _later(hass, shi, 16)
    assert shi.holding[DHW_MODE] == 1
    assert coordinator.data["cfg_dhw_mode"] == 1
    assert coordinator.remembered["cfg_dhw_mode"] == 1


async def test_same_value_is_not_written_again_while_pending(hass: HomeAssistant, shi: FakeSHI) -> None:
    """Cancel rule: writing while a write is pending could cancel it, so a repeated write is not sent."""
    entry = await _setup(hass, _deferred(shi))
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_mode", 1)  # e.g. a planner repeating its value
    assert len(_writes(shi, DHW_MODE)) == 1
    await _later(hass, shi, 16)
    assert shi.holding[DHW_MODE] == 1


async def test_restore_with_deferred_commit_reports_no_failure(
    hass: HomeAssistant, shi: FakeSHI, caplog: pytest.LogCaptureFixture
) -> None:
    entry = await _setup(hass, _deferred(shi))
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 540)
    await _later(hass, shi, 16)
    with caplog.at_level(logging.INFO):
        await _reboot(entry, shi, {DHW_MODE: 0, DHW_SETPOINT: 500})
        writes = len(_writes(shi, DHW_MODE))
        await _polls(entry, 2)  # polls while the commit is pending: nothing written to the register
        assert len(_writes(shi, DHW_MODE)) == writes
        await _later(hass, shi, 16)
    assert (shi.holding[DHW_MODE], shi.holding[DHW_SETPOINT]) == (1, 540)
    assert "could not restore" not in caplog.text
    assert "restored cfg_dhw_mode=1 (deferred)" in caplog.text
    assert entry.runtime_data.remembered == {"cfg_dhw_mode": 1, "cfg_dhw_setpoint": 540}


async def test_reboot_with_dhw_block_on_restores_after_release(hass: HomeAssistant, shi: FakeSHI) -> None:
    """The reference install on 2026-11-07: after the reboot the hot water block is on; the hot water mode can
    only be set once the block is off. It is restored after the block is released, not forgotten."""
    entry = await _setup(hass, _deferred(shi))
    await _write(entry, "cfg_heating_mode", 2)
    await _write(entry, "cfg_dhw_mode", 1)
    await _later(hass, shi, 16)
    shi.holding[DHW_BLOCK] = 1
    before = len(_writes(shi, DHW_MODE))
    await _reboot(entry, shi, {MODE: 0, DHW_MODE: 0})
    await _polls(entry, 2)
    assert shi.holding[MODE] == 2  # heating is not deferred
    assert len(_writes(shi, DHW_MODE)) == before  # nothing written while the block is on
    shi.holding[DHW_BLOCK] = 0
    await _polls(entry, 1)
    await _later(hass, shi, 16)
    assert shi.holding[DHW_MODE] == 1
    assert entry.runtime_data.remembered["cfg_dhw_mode"] == 1


async def test_pending_restore_forgotten_after_deadline(
    hass: HomeAssistant, shi: FakeSHI, mono: Mono, caplog: pytest.LogCaptureFixture
) -> None:
    entry = await _setup(hass, _deferred(shi))
    await _write(entry, "cfg_dhw_mode", 1)
    await _write(entry, "cfg_dhw_setpoint", 540)
    await _later(hass, shi, 16)
    shi.holding[DHW_BLOCK] = 1  # stays on
    await _reboot(entry, shi, {DHW_MODE: 0, DHW_SETPOINT: 500})
    assert "cfg_dhw_mode" in entry.runtime_data.remembered  # still pending, not forgotten
    with caplog.at_level(logging.WARNING):
        for _ in range(21):  # 30 s polls past the 10 minute deadline (no gap: polling continues)
            mono.now += 30
            await _polls(entry, 1)
    assert "could not restore cfg_dhw_mode, cfg_dhw_setpoint" in caplog.text
    assert entry.runtime_data.remembered == {}
    assert shi.holding[DHW_MODE] == 0


async def test_user_write_cancels_the_pending_restore(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, _deferred(shi))
    await _write(entry, "cfg_dhw_mode", 1)
    await _later(hass, shi, 16)
    shi.holding[DHW_BLOCK] = 1
    await _reboot(entry, shi, {DHW_MODE: 0})
    coordinator = entry.runtime_data
    assert "cfg_dhw_mode" in coordinator._pending_restore
    shi.holding[DHW_BLOCK] = 0
    await _write(entry, "cfg_dhw_mode", 2)  # the user decides otherwise
    assert coordinator._pending_restore == {}
    await _later(hass, shi, 16)
    await _polls(entry, 2)
    assert shi.holding[DHW_MODE] == 2
    assert [r[2] for r in _writes(shi, DHW_MODE)][-1] == 2  # the restore value 1 was not written afterwards
