"""Climate entity for the heating circuit of the Luxtronik SHI.

It does not read or write anything of its own: it is a view on the existing registers ``cfg_heating_mode``
(10000), ``cfg_heating_setpoint`` (10001), ``return`` (10100), ``return_target`` (10101), ``heating_block``
(10050), the operating mode and the heat generator bits, using the same write and read-back path as the number
and select entities.

HVAC modes (python-luxtronik ``ControlMode``):

* ``auto``: control mode 0 (``no_influence``). The heat pump controls itself with its own values. This is not
  "off": heating goes on. There is no ``off`` HVAC mode; blocking heating is the ``heating_block`` switch,
  which belongs to an optimizer such as the Heat Pump Optimizer.
* ``heat``: any other control mode (setpoint, offset, level). Choosing ``heat`` from ``auto`` writes
  ``setpoint``; an offset or level mode is left as it is.

The target is the heating setpoint, a return temperature setpoint (tRL), so the current temperature is the
return temperature. The setpoint only applies in control mode ``setpoint``; a target write in another mode is
refused.

Planners such as the Heat Pump Optimizer write the same registers. Do not use both at once.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LuxtronikConfigEntry
from .compat import CLIMATE_NATIVE_TEMPERATURE
from .const import DOMAIN
from .coordinator import LuxtronikCoordinator
from .entity import set_english_entity_id
from .registers import BY_KEY, CLIMATE_HEATING_KEY, MODE_NO_INFLUENCE, MODE_SETPOINT, encode_int16
from .setpoint import setpoint_attributes, validate_setpoint_write

_MODE_REG = BY_KEY["cfg_heating_mode"]
_SETPOINT_REG = BY_KEY["cfg_heating_setpoint"]
_RETURN_REG = BY_KEY["return"]
_BLOCK_REG = BY_KEY["heating_block"]
_OPERATING_REG = BY_KEY["operating_mode"]
# Heat generator bits VD1, VD2, ZWE1, ZWE2, ZWE3 of ``heat_generator_state`` (see binary_sensor.STATUS_BITS).
_GENERATOR_BITS = 0b11111

# One write at a time per platform; the Modbus client serialises access to the SHI anyway.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxtronikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the heating climate entity."""
    async_add_entities([LuxtronikHeatingClimate(entry.runtime_data)])


class LuxtronikHeatingClimate(CoordinatorEntity[LuxtronikCoordinator], ClimateEntity):
    """Heating circuit: control mode (auto / heat) and setpoint, current value is the return temperature."""

    _attr_has_entity_name = True
    _attr_name = None  # the entity carries the name of the heating device
    _attr_translation_key = CLIMATE_HEATING_KEY
    # Old or new attribute names depending on the Home Assistant base class (see compat.py).
    if CLIMATE_NATIVE_TEMPERATURE:
        _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    else:
        _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.AUTO, HVACMode.HEAT]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON
    _attr_min_temp = _SETPOINT_REG.min_value
    _attr_max_temp = _SETPOINT_REG.max_value
    _attr_target_temperature_step = _SETPOINT_REG.step
    _attr_precision = 0.1

    def __init__(self, coordinator: LuxtronikCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{CLIMATE_HEATING_KEY}"
        self._attr_device_info = coordinator.device_info_for(_SETPOINT_REG.key)
        set_english_entity_id(self, coordinator, "climate", CLIMATE_HEATING_KEY)
        self._attr_entity_registry_enabled_default = coordinator.climate_enabled_default

    def _data(self, reg):
        return (self.coordinator.data or {}).get(reg.key)

    def _mode(self) -> str | None:
        value = self._data(_MODE_REG)
        if value is None or not 0 <= value < len(_MODE_REG.options):
            return None
        return _MODE_REG.options[value]

    @property
    def hvac_mode(self) -> HVACMode | None:
        """``auto`` for control mode 0 (no influence), ``heat`` for setpoint, offset and level."""
        mode = self._mode()
        if mode is None:
            return None
        return HVACMode.AUTO if mode == MODE_NO_INFLUENCE else HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction | None:
        """``off`` while heating is blocked, ``heating`` while the heat pump heats, otherwise ``idle``."""
        block = self._data(_BLOCK_REG)
        if block == 1:
            return HVACAction.OFF
        operating = self._data(_OPERATING_REG)
        generators = (self.coordinator.data or {}).get("heat_generator_state")
        if block is None or operating is None or generators is None:
            return None
        heating = (
            0 <= operating < len(_OPERATING_REG.options)
            and _OPERATING_REG.options[operating] == "heating"
            and bool(generators & _GENERATOR_BITS)
        )
        return HVACAction.HEATING if heating else HVACAction.IDLE

    def _current_temperature(self) -> float | None:
        """Return temperature: the heating setpoint is a return temperature setpoint (tRL)."""
        return self._data(_RETURN_REG)

    def _target_temperature(self) -> float | None:
        """Heating setpoint read back from the heat pump."""
        return self._data(_SETPOINT_REG)

    if CLIMATE_NATIVE_TEMPERATURE:
        native_current_temperature = property(_current_temperature)
        native_target_temperature = property(_target_temperature)
    else:
        current_temperature = property(_current_temperature)
        target_temperature = property(_target_temperature)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Control mode as the mode select shows it, whether the setpoint applies, the effective target,
        block.
        """
        attrs: dict[str, Any] = setpoint_attributes(self.coordinator, _SETPOINT_REG.key)
        mode = self._mode()
        if mode is not None:
            attrs["controller_mode"] = mode
        block = self._data(_BLOCK_REG)
        attrs["heating_block"] = None if block is None else block == 1
        return attrs

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Write the heating setpoint (only in control mode ``setpoint``, range of the register, read back).
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

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """``auto`` writes mode 0 (no influence). ``heat`` writes ``setpoint`` only coming from mode 0."""
        if hvac_mode == HVACMode.AUTO:
            await self.coordinator.async_write(_MODE_REG, _MODE_REG.options.index(MODE_NO_INFLUENCE))
            return
        if hvac_mode != HVACMode.HEAT:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_hvac_mode",
                translation_placeholders={"mode": str(hvac_mode)},
            )
        mode = self._mode()
        if mode is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="control_mode_unknown")
        if mode != MODE_NO_INFLUENCE:
            return  # setpoint, offset or level already heat; an optimizer's offset or level stays
        await self.coordinator.async_write(_MODE_REG, _MODE_REG.options.index(MODE_SETPOINT))

    async def async_turn_on(self) -> None:
        """Same as choosing ``heat``."""
        await self.async_set_hvac_mode(HVACMode.HEAT)
