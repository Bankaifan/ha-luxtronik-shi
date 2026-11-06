"""Climate and water heater define either the old or the new temperature attribute names, never both."""

from __future__ import annotations

import importlib

import pytest
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.water_heater import WaterHeaterEntity

from custom_components.luxtronik_shi import climate, compat, water_heater

OLD = ("_attr_temperature_unit", "current_temperature", "target_temperature")
NEW = ("_attr_native_temperature_unit", "native_current_temperature", "native_target_temperature")

CASES = [
    (climate, "LuxtronikHeatingClimate", ClimateEntity, "CLIMATE_NATIVE_TEMPERATURE"),
    (water_heater, "LuxtronikHotWaterHeater", WaterHeaterEntity, "WATER_HEATER_NATIVE_TEMPERATURE"),
]


def _defined(cls, names):
    return [n for n in names if n in vars(cls)]


@pytest.mark.parametrize(("module", "cls_name", "base", "flag"), CASES)
def test_flag_matches_base_class(module, cls_name, base, flag) -> None:
    assert getattr(compat, flag) == hasattr(base, "native_current_temperature")


@pytest.mark.parametrize(("module", "cls_name", "base", "flag"), CASES)
def test_only_one_set_of_names_is_defined(module, cls_name, base, flag) -> None:
    cls = getattr(module, cls_name)
    if getattr(compat, flag):
        assert _defined(cls, OLD) == []
        assert len(_defined(cls, NEW)) == 3
    else:
        assert _defined(cls, NEW) == []
        assert len(_defined(cls, OLD)) == 3


@pytest.mark.parametrize(("module", "cls_name", "base", "flag"), CASES)
def test_new_base_class_gets_no_deprecated_names(monkeypatch, module, cls_name, base, flag) -> None:
    """Simulate a Home Assistant with the native names: the entity must switch to them."""
    monkeypatch.setattr(base, "native_current_temperature", None, raising=False)
    importlib.reload(compat)
    importlib.reload(module)
    try:
        cls = getattr(module, cls_name)
        assert _defined(cls, OLD) == []
        assert len(_defined(cls, NEW)) == 3
    finally:
        monkeypatch.undo()
        importlib.reload(compat)
        importlib.reload(module)
