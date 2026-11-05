"""Climate entity for the heating circuit of the Luxtronik SHI.

It does not read or write anything of its own: it is a view on the existing registers
``cfg_heating_mode`` (10000), ``cfg_heating_setpoint`` (10001) and the ``flow`` temperature, using the
same write and read-back path as the number and select entities.

Planners such as the Heat Pump Optimizer write the same registers. Do not use both at once.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LuxtronikConfigEntry
from .coordinator import LuxtronikCoordinator
from .registers import BY_KEY, CLIMATE_HEATING_KEY, encode_int16

_MODE_REG = BY_KEY["cfg_heating_mode"]
_SETPOINT_REG = BY_KEY["cfg_heating_setpoint"]
_FLOW_REG = BY_KEY["flow"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxtronikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the heating climate entity."""
    async_add_entities([LuxtronikHeatingClimate(entry.runtime_data)])


class LuxtronikHeatingClimate(CoordinatorEntity[LuxtronikCoordinator], ClimateEntity):
    """Heating circuit: mode (off / heat) and setpoint, current value is the flow temperature."""

    _attr_has_entity_name = True
    _attr_name = None  # the entity carries the name of the heating device
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )
    _attr_min_temp = _SETPOINT_REG.min_value
    _attr_max_temp = _SETPOINT_REG.max_value
    _attr_target_temperature_step = _SETPOINT_REG.step
    _attr_precision = 0.1

    def __init__(self, coordinator: LuxtronikCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{CLIMATE_HEATING_KEY}"
        self._attr_device_info = coordinator.device_info_for(_SETPOINT_REG.key)
        self._attr_entity_registry_enabled_default = coordinator.climate_enabled_default

    def _data(self, reg):
        return (self.coordinator.data or {}).get(reg.key)

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Off for mode ``off``; every other controller mode (setpoint, offset, level) counts as heating."""
        value = self._data(_MODE_REG)
        if value is None or not 0 <= value < len(_MODE_REG.options):
            return None
        return HVACMode.OFF if _MODE_REG.options[value] == "off" else HVACMode.HEAT

    @property
    def current_temperature(self) -> float | None:
        """Flow temperature of the heat pump."""
        return self._data(_FLOW_REG)

    @property
    def target_temperature(self) -> float | None:
        """Heating setpoint read back from the heat pump."""
        return self._data(_SETPOINT_REG)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """The controller mode as shown by the mode select (off / setpoint / offset / level)."""
        value = self._data(_MODE_REG)
        if value is None or not 0 <= value < len(_MODE_REG.options):
            return {}
        return {"controller_mode": _MODE_REG.options[value]}

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Write the heating setpoint (range of the register, read back afterwards)."""
        value = kwargs.get(ATTR_TEMPERATURE)
        if value is None:
            return
        if not _SETPOINT_REG.min_value <= value <= _SETPOINT_REG.max_value:
            raise ServiceValidationError(
                f"Setpoint {value} is outside {_SETPOINT_REG.min_value} ... {_SETPOINT_REG.max_value} °C"
            )
        await self.coordinator.async_write(_SETPOINT_REG, encode_int16(value, _SETPOINT_REG.scale))

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """``off`` writes mode ``off``, ``heat`` writes mode ``setpoint`` (the mode the setpoint acts in)."""
        if hvac_mode == HVACMode.OFF:
            option = "off"
        elif hvac_mode == HVACMode.HEAT:
            option = "setpoint"
        else:
            raise HomeAssistantError(f"Unsupported HVAC mode {hvac_mode}")
        await self.coordinator.async_write(_MODE_REG, _MODE_REG.options.index(option))
