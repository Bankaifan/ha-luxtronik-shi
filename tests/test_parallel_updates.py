"""Every platform declares PARALLEL_UPDATES (Home Assistant quality scale, silver)."""

from __future__ import annotations

import importlib

import pytest

from custom_components.luxtronik_shi import PLATFORMS

_READ_ONLY = {"binary_sensor", "sensor"}
_WRITABLE = {"switch", "button", "number", "select", "climate", "water_heater"}


@pytest.mark.parametrize("platform", sorted(_READ_ONLY | _WRITABLE))
def test_platform_declares_parallel_updates(platform: str) -> None:
    module = importlib.import_module(f"custom_components.luxtronik_shi.{platform}")
    assert module.PARALLEL_UPDATES == (0 if platform in _READ_ONLY else 1)


def test_known_platforms_are_covered() -> None:
    covered = _READ_ONLY | _WRITABLE
    assert {str(p) for p in PLATFORMS} <= covered
