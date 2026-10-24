"""Numbers of the Luxtronik SHI (writable heating curve offset)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LuxtronikConfigEntry
from .const import HEATING_OFFSET_MAX, HEATING_OFFSET_MIN, HEATING_OFFSET_STEP
from .coordinator import LuxtronikCoordinator
from .entity import LuxtronikEntity
from .registers import ALL_REGISTERS, Register, encode_int16


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxtronikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the number entities."""
    coordinator = entry.runtime_data
    async_add_entities(LuxtronikNumber(coordinator, reg) for reg in ALL_REGISTERS if reg.platform == "number")


class LuxtronikNumber(LuxtronikEntity, NumberEntity):
    """Heating curve offset in Kelvin (register 10002, int16, 0.1 K)."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = HEATING_OFFSET_MIN
    _attr_native_max_value = HEATING_OFFSET_MAX
    _attr_native_step = HEATING_OFFSET_STEP

    def __init__(self, coordinator: LuxtronikCoordinator, reg: Register) -> None:
        super().__init__(coordinator, reg)
        self._attr_native_unit_of_measurement = reg.unit

    @property
    def native_value(self) -> float | None:
        """Return the offset read back from the heat pump."""
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        """Write the new offset (negative values as two's complement)."""
        await self.coordinator.async_write(self._reg, encode_int16(value, self._reg.scale))
