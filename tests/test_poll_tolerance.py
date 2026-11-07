"""One failed poll does not make every entity unavailable; a second one in a row does."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.luxtronik_shi import coordinator as coordinator_module
from custom_components.luxtronik_shi.const import DOMAIN, UNREACHABLE_AFTER

from .fake_shi import FakeSHI
from .test_integration import _setup
from .test_repairs import Clock, Outage, _issue


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(coordinator_module.dt_util, "utcnow", fake)
    return fake


@pytest.fixture(autouse=True)
def tolerate_one_failed_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coordinator_module, "POLL_FAILURES_TOLERATED", 1)


def _state(hass: HomeAssistant, entry, key: str):
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id is not None
    return hass.states.get(entity_id)


async def test_one_failed_poll_keeps_the_values(hass: HomeAssistant, shi: FakeSHI, clock: Clock) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    before = _state(hass, entry, "flow").state
    assert before not in ("unavailable", "unknown")

    outage = Outage(coordinator)
    outage.down()
    await coordinator.async_refresh()
    assert coordinator.last_update_success  # the previous values are served
    assert _state(hass, entry, "flow").state == before

    await coordinator.async_refresh()  # the second failed poll in a row
    assert not coordinator.last_update_success
    assert _state(hass, entry, "flow").state == "unavailable"

    outage.up()
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert _state(hass, entry, "flow").state == before


async def test_a_tolerated_failure_still_counts_as_an_outage(
    hass: HomeAssistant, shi: FakeSHI, clock: Clock
) -> None:
    """The failure clock of the unreachable issue starts with the first failed poll, tolerated or not."""
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    outage = Outage(coordinator)
    outage.down()
    await coordinator.async_refresh()  # tolerated
    clock.tick(timedelta(seconds=UNREACHABLE_AFTER + 60))
    await coordinator.async_refresh()  # not tolerated: the run is older than the threshold
    assert _issue(hass, entry, "shi_unreachable") is not None
    outage.up()
    await coordinator.async_refresh()
    assert _issue(hass, entry, "shi_unreachable") is None


async def test_failures_in_a_row_are_counted_from_the_last_success(
    hass: HomeAssistant, shi: FakeSHI, clock: Clock
) -> None:
    entry = await _setup(hass, shi)
    coordinator = entry.runtime_data
    outage = Outage(coordinator)
    for _ in range(3):
        outage.down()
        await coordinator.async_refresh()
        assert coordinator.last_update_success  # always only one failure since the last success
        outage.up()
        await coordinator.async_refresh()
    outage.down()
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert not coordinator.last_update_success


async def test_first_refresh_still_fails_without_values(hass: HomeAssistant, socket_enabled) -> None:
    """There is nothing to keep before the first successful poll: setup is retried."""
    from .test_integration import test_setup_retry_when_offline

    await test_setup_retry_when_offline(hass, socket_enabled)
