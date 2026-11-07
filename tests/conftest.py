"""Shared fixtures."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from .fake_shi import FakeSHI

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow the custom integration to be loaded in all tests."""


@pytest.fixture(autouse=True)
def no_poll_failure_tolerance(monkeypatch: pytest.MonkeyPatch) -> None:
    """The outage tests count every failed poll: switch the tolerance of one failed poll off.

    ``tests/test_poll_tolerance.py`` sets it back on and tests it.
    """
    from custom_components.luxtronik_shi import coordinator

    monkeypatch.setattr(coordinator, "POLL_FAILURES_TOLERATED", 0)


@pytest.fixture
async def shi(socket_enabled) -> AsyncGenerator[FakeSHI]:
    """A running simulated heat pump."""
    server = FakeSHI()
    await server.start()
    yield server
    await server.stop()
