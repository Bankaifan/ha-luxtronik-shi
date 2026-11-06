"""Compatibility switches for Home Assistant versions between the minimum (hacs.json) and the newest.

Newer Home Assistant releases deprecate ``_attr_temperature_unit``, ``current_temperature`` and
``target_temperature`` on climate and water heater entities in favour of ``_attr_native_temperature_unit``,
``native_current_temperature`` and ``native_target_temperature``. Older releases only know the old names.
The flags below are computed from the base classes, so an entity defines exactly one set of names and never
triggers the deprecation warning.
"""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.water_heater import WaterHeaterEntity

CLIMATE_NATIVE_TEMPERATURE = hasattr(ClimateEntity, "native_current_temperature")
WATER_HEATER_NATIVE_TEMPERATURE = hasattr(WaterHeaterEntity, "native_current_temperature")
