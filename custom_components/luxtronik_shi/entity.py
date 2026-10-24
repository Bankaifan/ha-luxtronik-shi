"""Base entity for the Luxtronik SHI."""

from __future__ import annotations

from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import LuxtronikCoordinator
from .registers import Register


class LuxtronikEntity(CoordinatorEntity[LuxtronikCoordinator]):
    """Entity that is backed by one register."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LuxtronikCoordinator, reg: Register) -> None:
        super().__init__(coordinator)
        self._reg = reg
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{reg.key}"
        self._attr_device_info = coordinator.device_info
        if reg.key.startswith("raw_"):
            self._attr_translation_key = "raw"
            self._attr_translation_placeholders = {"address": str(reg.address)}
        else:
            self._attr_translation_key = reg.key
        if reg.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_entity_registry_enabled_default = reg.enabled_default

    @property
    def _value(self):
        return (self.coordinator.data or {}).get(self._reg.key)
