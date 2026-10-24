"""Shared fixtures."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

from .fake_shi import FakeSHI

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow the custom integration to be loaded in all tests."""


@pytest.fixture
async def shi(socket_enabled) -> AsyncGenerator[FakeSHI]:
    """A running simulated heat pump."""
    server = FakeSHI()
    await server.start()
    yield server
    await server.stop()
