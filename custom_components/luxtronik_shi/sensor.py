"""Sensors of the Luxtronik SHI."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LuxtronikConfigEntry
from .coordinator import LuxtronikCoordinator
from .entity import LuxtronikEntity
from .registers import ALL_REGISTERS, Register


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxtronikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one sensor per measurement register."""
    coordinator = entry.runtime_data
    async_add_entities(LuxtronikSensor(coordinator, reg) for reg in ALL_REGISTERS if reg.platform == "sensor")


class LuxtronikSensor(LuxtronikEntity, SensorEntity):
    """A numeric value of the heat pump."""

    def __init__(self, coordinator: LuxtronikCoordinator, reg: Register) -> None:
        super().__init__(coordinator, reg)
        self._attr_native_unit_of_measurement = reg.unit
        if reg.device_class:
            self._attr_device_class = SensorDeviceClass(reg.device_class)
        if reg.state_class:
            self._attr_state_class = SensorStateClass(reg.state_class)
        if reg.precision is not None:
            self._attr_suggested_display_precision = reg.precision

    @property
    def native_value(self) -> float | int | None:
        """Return the current value."""
        return self._value
