"""Switches of the Luxtronik SHI (blocks and extra hot water)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LuxtronikConfigEntry
from .entity import LuxtronikEntity
from .registers import ALL_REGISTERS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxtronikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the switches."""
    coordinator = entry.runtime_data
    async_add_entities(LuxtronikSwitch(coordinator, reg) for reg in ALL_REGISTERS if reg.platform == "switch")


class LuxtronikSwitch(LuxtronikEntity, SwitchEntity):
    """A 0/1 holding register."""

    @property
    def is_on(self) -> bool | None:
        """Return the state read back from the heat pump."""
        value = self._value
        return None if value is None else value == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the register to 1."""
        await self.coordinator.async_write(self._reg, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Set the register to 0."""
        await self.coordinator.async_write(self._reg, 0)
