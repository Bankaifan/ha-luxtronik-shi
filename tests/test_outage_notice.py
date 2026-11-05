"""Repair issue: control values changed during an outage (notice only, never written back)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.luxtronik_shi.const import DOMAIN

from .fake_shi import FakeSHI
from .test_integration import _setup
from .test_repairs import Outage

ISSUE = "values_changed_after_outage"
HEATING_BLOCK, DHW_MODE = 10050, 10005


def _issue(hass, entry):
    return ir.async_get(hass).async_get_issue(DOMAIN, f"{ISSUE}_{entry.entry_id}")


def _writes(shi: FakeSHI) -> list:
    return [r for r in shi.requests if r[0] == 6]


async def _outage(hass, shi, entry, change: dict[int, int]) -> None:
    coordinator = entry.runtime_data
    outage = Outage(coordinator)
    outage.down()
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    shi.holding.update(change)
    outage.up()
    await coordinator.async_refresh()
    assert coordinator.last_update_success


async def test_changed_value_raises_issue_with_old_and_new(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    await _outage(hass, shi, entry, {HEATING_BLOCK: 1, DHW_MODE: 2})
    await entry.runtime_data.async_refresh()  # settings are read every 2nd poll
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.translation_key == ISSUE
    assert not issue.is_fixable
    changes = issue.translation_placeholders["changes"]
    assert "heating block: released -> blocked" in changes
    assert "hot water mode: off -> offset" in changes
    assert "heating mode" not in changes


async def test_no_difference_no_issue(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    await _outage(hass, shi, entry, {})
    assert _issue(hass, entry) is None


async def test_never_writes(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    await _outage(hass, shi, entry, {HEATING_BLOCK: 1})
    await entry.runtime_data.async_refresh()
    assert _issue(hass, entry) is not None
    assert _writes(shi) == []
    assert shi.holding_value(HEATING_BLOCK) == 1  # left as the controller reports it


async def test_issue_cleared_when_values_match_again(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    await _outage(hass, shi, entry, {HEATING_BLOCK: 1})
    await entry.runtime_data.async_refresh()
    assert _issue(hass, entry) is not None  # stays while the values differ
    shi.holding[HEATING_BLOCK] = 0
    await entry.runtime_data.async_refresh()
    assert _issue(hass, entry) is None
    assert _writes(shi) == []


async def test_dismissed_issue_resumes_snapshots(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    await _outage(hass, shi, entry, {HEATING_BLOCK: 1})
    ir.async_ignore_issue(hass, DOMAIN, f"{ISSUE}_{entry.entry_id}", True)
    await entry.runtime_data.async_refresh()
    shi.holding[HEATING_BLOCK] = 0  # would "match" the old baseline, but the issue is dismissed
    await entry.runtime_data.async_refresh()
    assert entry.runtime_data._baseline is None
    assert entry.runtime_data._snapshot["heating_block"] == 0
