"""Numbers of the Luxtronik SHI (writable setpoints, offsets and limits)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LuxtronikConfigEntry
from .coordinator import LuxtronikCoordinator
from .entity import LuxtronikEntity
from .registers import SETPOINT_GROUPS, Register, encode_int16
from .setpoint import setpoint_attributes

# One write at a time per platform; the Modbus client serialises access to the SHI anyway.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxtronikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the number entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        LuxtronikNumber(coordinator, reg) for reg in coordinator.registers if reg.platform == "number"
    )


class LuxtronikNumber(LuxtronikEntity, NumberEntity):
    """A writable holding register (0.1 steps, negative values as two's complement)."""

    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: LuxtronikCoordinator, reg: Register) -> None:
        super().__init__(coordinator, reg)
        self._attr_native_unit_of_measurement = reg.unit
        self._attr_native_min_value = reg.min_value
        self._attr_native_max_value = reg.max_value
        self._attr_native_step = reg.step
        if reg.unit == "kW":
            self._attr_device_class = NumberDeviceClass.POWER
        elif reg.unit == "°C":
            # Absolute temperatures only, so Home Assistant converts them like the climate entity does. Never
            # on the K offsets: Home Assistant would convert a difference as an absolute temperature.
            self._attr_device_class = NumberDeviceClass.TEMPERATURE

    @property
    def native_value(self) -> float | None:
        """Return the value read back from the heat pump."""
        return self._value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Heating and hot water setpoint: whether the setpoint applies and the controller's effective target.
        """
        if self._reg.key not in SETPOINT_GROUPS:
            return None
        return setpoint_attributes(self.coordinator, self._reg.key)

    async def async_set_native_value(self, value: float) -> None:
        """Write the new value (encoded like the register, negative values as two's complement).

        A setpoint is written in every control mode: optimizers write it and set the mode themselves.
        """
        await self.coordinator.async_write(self._reg, encode_int16(value, self._reg.scale))
