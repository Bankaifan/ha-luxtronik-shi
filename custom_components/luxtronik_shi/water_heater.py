"""Water heater entity for domestic hot water of the Luxtronik SHI.

It does not read or write anything of its own: it is a view on the existing registers ``cfg_dhw_mode``
(10005), ``cfg_dhw_setpoint`` (10006), the hot water temperature ``dhw`` (10120) and the hot water target
``dhw_target`` (10121), using the same write and read-back path as the number and select entities.

Operation modes are the control modes of the mode select (``registers.CONTROL_MODES``, the same option keys).
Raw 0 is ``no_influence`` (python-luxtronik ControlMode 0: the controller uses its own values), never "off":
hot water keeps working. The setpoint only applies in mode ``setpoint``; a target write in another mode is
refused.

Planners such as the Heat Pump Optimizer do not control hot water through this entity. Do not let a planner
and this entity write the same registers at the same time.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.water_heater import WaterHeaterEntity, WaterHeaterEntityFeature
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LuxtronikConfigEntry
from .compat import WATER_HEATER_NATIVE_TEMPERATURE
from .const import DOMAIN
from .coordinator import LuxtronikCoordinator
from .entity import set_english_entity_id
from .registers import BY_KEY, CONTROL_MODES, WATER_HEATER_DHW_KEY, encode_int16
from .setpoint import setpoint_attributes, validate_setpoint_write

_MODE_REG = BY_KEY["cfg_dhw_mode"]
_SETPOINT_REG = BY_KEY["cfg_dhw_setpoint"]
_TEMP_REG = BY_KEY["dhw"]
# Operation mode per raw value: the options of the mode select (raw value = position).
OPERATION_MODES: tuple[str, ...] = CONTROL_MODES
assert OPERATION_MODES == _MODE_REG.options

# One write at a time per platform; the Modbus client serialises access to the SHI anyway.
PARALLEL_UPDATES = 1


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
    _attr_translation_key = WATER_HEATER_DHW_KEY
    # Old or new attribute names depending on the Home Assistant base class (see compat.py).
    if WATER_HEATER_NATIVE_TEMPERATURE:
        _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    else:
        _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_operation_list = list(OPERATION_MODES)
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
        set_english_entity_id(self, coordinator, "water_heater", WATER_HEATER_DHW_KEY)
        self._attr_entity_registry_enabled_default = coordinator.water_heater_enabled_default

    def _data(self, reg):
        return (self.coordinator.data or {}).get(reg.key)

    @property
    def current_operation(self) -> str | None:
        """Control mode of the mode select: no_influence (raw 0) / setpoint / offset / level."""
        value = self._data(_MODE_REG)
        if value is None or not 0 <= value < len(OPERATION_MODES):
            return None
        return OPERATION_MODES[value]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Whether the setpoint applies and the controller's effective hot water target."""
        return setpoint_attributes(self.coordinator, _SETPOINT_REG.key)

    def _current_temperature(self) -> float | None:
        """Hot water temperature."""
        return self._data(_TEMP_REG)

    def _target_temperature(self) -> float | None:
        """Hot water setpoint read back from the heat pump."""
        return self._data(_SETPOINT_REG)

    if WATER_HEATER_NATIVE_TEMPERATURE:
        native_current_temperature = property(_current_temperature)
        native_target_temperature = property(_target_temperature)
    else:
        current_temperature = property(_current_temperature)
        target_temperature = property(_target_temperature)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Write the hot water setpoint (only in control mode ``setpoint``, range of the register, read back).
        """
        value = kwargs.get(ATTR_TEMPERATURE)
        if value is None:
            return
        if not _SETPOINT_REG.min_value <= value <= _SETPOINT_REG.max_value:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="setpoint_out_of_range",
                translation_placeholders={
                    "value": str(value),
                    "min": str(_SETPOINT_REG.min_value),
                    "max": str(_SETPOINT_REG.max_value),
                },
            )
        validate_setpoint_write(self.coordinator, _SETPOINT_REG.key)
        await self.coordinator.async_write(_SETPOINT_REG, encode_int16(value, _SETPOINT_REG.scale))

    async def async_set_operation_mode(self, operation_mode: str) -> None:
        """Write the hot water mode register (one of the options of the mode select)."""
        if operation_mode not in OPERATION_MODES:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_operation_mode",
                translation_placeholders={"mode": str(operation_mode)},
            )
        await self.coordinator.async_write(_MODE_REG, OPERATION_MODES.index(operation_mode))
