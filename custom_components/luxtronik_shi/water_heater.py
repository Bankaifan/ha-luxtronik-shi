"""Water heater entity for domestic hot water of the Luxtronik SHI.

It does not read or write anything of its own: it is a view on the existing registers
``cfg_dhw_mode`` (10005), ``cfg_dhw_setpoint`` (10006) and the hot water temperature ``dhw`` (10120),
using the same write and read-back path as the number and select entities.

Planners such as the Heat Pump Optimizer do not control hot water through this entity. Do not let a planner
and this entity write the same registers at the same time.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.water_heater import WaterHeaterEntity, WaterHeaterEntityFeature
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LuxtronikConfigEntry
from .coordinator import LuxtronikCoordinator
from .registers import BY_KEY, WATER_HEATER_DHW_KEY, encode_int16

_MODE_REG = BY_KEY["cfg_dhw_mode"]
_SETPOINT_REG = BY_KEY["cfg_dhw_setpoint"]
_TEMP_REG = BY_KEY["dhw"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxtronikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the hot water entity."""
    async_add_entities([LuxtronikHotWaterHeater(entry.runtime_data)])


class LuxtronikHotWaterHeater(CoordinatorEntity[LuxtronikCoordinator], WaterHeaterEntity):
    """Hot water: controller mode and setpoint, current value is the hot water temperature."""

    _attr_has_entity_name = True
    _attr_name = None  # the entity carries the name of the hot water device
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_operation_list = list(_MODE_REG.options)
    _attr_supported_features = (
        WaterHeaterEntityFeature.TARGET_TEMPERATURE | WaterHeaterEntityFeature.OPERATION_MODE
    )
    _attr_min_temp = _SETPOINT_REG.min_value
    _attr_max_temp = _SETPOINT_REG.max_value
    _attr_target_temperature_step = _SETPOINT_REG.step
    _attr_precision = 0.1

    def __init__(self, coordinator: LuxtronikCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{WATER_HEATER_DHW_KEY}"
        self._attr_device_info = coordinator.device_info_for(_SETPOINT_REG.key)
        self._attr_entity_registry_enabled_default = coordinator.water_heater_enabled_default

    def _data(self, reg):
        return (self.coordinator.data or {}).get(reg.key)

    @property
    def current_operation(self) -> str | None:
        """Controller mode as shown by the mode select (off / setpoint / offset / level)."""
        value = self._data(_MODE_REG)
        if value is None or not 0 <= value < len(_MODE_REG.options):
            return None
        return _MODE_REG.options[value]

    @property
    def current_temperature(self) -> float | None:
        """Hot water temperature."""
        return self._data(_TEMP_REG)

    @property
    def target_temperature(self) -> float | None:
        """Hot water setpoint read back from the heat pump."""
        return self._data(_SETPOINT_REG)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Write the hot water setpoint (range of the register, read back afterwards)."""
        value = kwargs.get(ATTR_TEMPERATURE)
        if value is None:
            return
        if not _SETPOINT_REG.min_value <= value <= _SETPOINT_REG.max_value:
            raise ServiceValidationError(
                f"Setpoint {value} is outside {_SETPOINT_REG.min_value} ... {_SETPOINT_REG.max_value} °C"
            )
        await self.coordinator.async_write(_SETPOINT_REG, encode_int16(value, _SETPOINT_REG.scale))

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Write the hot water mode register (one of the options of the mode select)."""
        if operation_mode not in _MODE_REG.options:
            raise HomeAssistantError(f"Unsupported operation mode {operation_mode}")
        await self.coordinator.async_write(_MODE_REG, _MODE_REG.options.index(operation_mode))
