"""Binary sensors of the Luxtronik SHI."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LuxtronikConfigEntry
from .coordinator import LuxtronikCoordinator
from .entity import LuxtronikEntity
from .registers import ALL_REGISTERS, Register


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxtronikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the capability flags and the connection sensor."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [LuxtronikOnline(coordinator)]
    entities.extend(
        LuxtronikFlag(coordinator, reg) for reg in ALL_REGISTERS if reg.platform == "binary_sensor"
    )
    async_add_entities(entities)


class LuxtronikFlag(LuxtronikEntity, BinarySensorEntity):
    """A discrete input of the heat pump."""

    def __init__(self, coordinator: LuxtronikCoordinator, reg: Register) -> None:
        super().__init__(coordinator, reg)

    @property
    def is_on(self) -> bool | None:
        """Return the flag."""
        return self._value


class LuxtronikOnline(CoordinatorEntity[LuxtronikCoordinator], BinarySensorEntity):
    """True as long as the heat pump answers."""

    _attr_has_entity_name = True
    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: LuxtronikCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_online"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        """Always available – the state itself carries the information."""
        return True

    @property
    def is_on(self) -> bool:
        """Return whether the last poll succeeded."""
        return self.coordinator.last_update_success
