"""Repair issues: old firmware and unreachable SHI (issue #24)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.luxtronik_shi import coordinator as coordinator_module
from custom_components.luxtronik_shi.const import DOMAIN, UNREACHABLE_AFTER
from custom_components.luxtronik_shi.modbus_client import ModbusCommError

from .fake_shi import FakeSHI
from .test_integration import _setup


class Clock:
    """Controllable replacement for dt_util.utcnow in the coordinator.

    The pytest freezer is not used: it also freezes the monotonic clock that asyncio and pymodbus rely on.
    """

    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, 12, 0, 0)

    def tick(self, delta: timedelta) -> None:
        self.now += delta

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(coordinator_module.dt_util, "utcnow", fake)
    return fake


class Outage:
    """Switch the simulated SHI between reachable and unreachable.

    Every read fails like a refused or timed-out connection. The simulator itself keeps running: stopping it
    makes pymodbus retry with real reconnect delays, which makes the tests take minutes.
    """

    def __init__(self, coordinator) -> None:
        self._client = coordinator.client
        self._read = coordinator.client.read

    def down(self) -> None:
        async def failing(*args, **kwargs):
            raise ModbusCommError("simulated outage")

        self._client.read = failing

    def up(self) -> None:
        self._client.read = self._read


def _issue(hass: HomeAssistant, entry: MockConfigEntry, key: str):
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{key}_{entry.entry_id}")


async def test_unreachable_issue_after_threshold_and_removed_on_recovery(
    hass: HomeAssistant, shi: FakeSHI, clock: Clock
) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    assert _issue(hass, entry, "shi_unreachable") is None

    outage = Outage(coordinator)
    outage.down()
    await coordinator.async_refresh()  # first failed poll starts the clock
    assert not coordinator.last_update_success
    assert _issue(hass, entry, "shi_unreachable") is None

    clock.tick(timedelta(seconds=UNREACHABLE_AFTER - 30))
    await coordinator.async_refresh()
    assert _issue(hass, entry, "shi_unreachable") is None  # still below the threshold

    clock.tick(timedelta(seconds=60))
    await coordinator.async_refresh()
    issue = _issue(hass, entry, "shi_unreachable")
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.ERROR
    assert issue.translation_key == "shi_unreachable"
    assert not issue.is_fixable

    outage.up()
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert _issue(hass, entry, "shi_unreachable") is None


async def test_short_outage_resets_the_clock(hass: HomeAssistant, shi: FakeSHI, clock: Clock) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    outage = Outage(coordinator)
    outage.down()
    await coordinator.async_refresh()
    outage.up()
    await coordinator.async_refresh()  # success: the failure counter resets
    assert coordinator.last_update_success
    clock.tick(timedelta(seconds=UNREACHABLE_AFTER + 60))
    outage.down()
    await coordinator.async_refresh()  # a new run of failures starts now, not 10 minutes ago
    assert _issue(hass, entry, "shi_unreachable") is None


async def test_issue_removed_when_entry_is_unloaded(hass: HomeAssistant, shi: FakeSHI, clock: Clock) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    Outage(coordinator).down()
    await coordinator.async_refresh()
    clock.tick(timedelta(seconds=UNREACHABLE_AFTER + 60))
    await coordinator.async_refresh()
    assert _issue(hass, entry, "shi_unreachable") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert _issue(hass, entry, "shi_unreachable") is None


async def test_old_firmware_raises_warning(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.set_firmware(3, 90)
    entry = await _setup(hass, shi)
    issue = _issue(hass, entry, "firmware_old")
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.translation_key == "firmware_old"
    assert issue.translation_placeholders["version"] == "3.90"
    assert issue.translation_placeholders["minimum"] == "3.92.0"
    assert not issue.is_fixable


@pytest.mark.parametrize("firmware", [(3, 92), (3, 93), (4, 0)])
async def test_no_firmware_issue_for_current_firmware(
    hass: HomeAssistant, shi: FakeSHI, firmware: tuple[int, int]
) -> None:
    shi.set_firmware(*firmware)
    entry = await _setup(hass, shi)
    assert _issue(hass, entry, "firmware_old") is None


async def test_firmware_issue_disappears_after_update(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.set_firmware(3, 1)
    entry = await _setup(hass, shi)
    assert _issue(hass, entry, "firmware_old") is not None
    shi.set_firmware(3, 92)
    coordinator = entry.runtime_data
    coordinator._tick = 120  # firmware is only polled every 120th cycle
    await coordinator.async_refresh()
    assert _issue(hass, entry, "firmware_old") is None


async def test_firmware_issue_removed_when_entry_is_unloaded(hass: HomeAssistant, shi: FakeSHI) -> None:
    shi.set_firmware(3, 1)
    entry = await _setup(hass, shi)
    assert _issue(hass, entry, "firmware_old") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert _issue(hass, entry, "firmware_old") is None
