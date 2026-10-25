"""Selects of the Luxtronik SHI (operating modes, levels, power limit mode)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
    """Create the select entities."""
    coordinator = entry.runtime_data
    async_add_entities(LuxtronikSelect(coordinator, reg) for reg in ALL_REGISTERS if reg.platform == "select")


class LuxtronikSelect(LuxtronikEntity, SelectEntity):
    """An enumeration stored in a holding register (the raw value is the option index)."""

    def __init__(self, coordinator: LuxtronikCoordinator, reg: Register) -> None:
        super().__init__(coordinator, reg)
        assert reg.options
        self._attr_options = list(reg.options)

    @property
    def current_option(self) -> str | None:
        """Return the option that is set in the heat pump."""
        value = self._value
        if value is None or not 0 <= value < len(self._reg.options):
            return None
        return self._reg.options[value]

    async def async_select_option(self, option: str) -> None:
        """Write the index of the chosen option."""
        await self.coordinator.async_write(self._reg, self._reg.options.index(option))
