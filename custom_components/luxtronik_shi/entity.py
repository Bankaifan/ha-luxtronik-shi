"""Base entity for the Luxtronik SHI."""

from __future__ import annotations

import json
import pathlib
from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .coordinator import LuxtronikCoordinator
from .registers import RAW_KEYS, Register, area_of

_TRANSLATIONS = pathlib.Path(__file__).parent / "translations"
# Generated translations (names of devices and entities) by language, loaded once by ``load_names``.
_NAMES: dict[str, dict[str, Any]] = {}


def load_names() -> None:
    """Read the English and German names (blocking file access: run it in the executor)."""
    for lang in ("en", "de"):
        _NAMES[lang] = json.loads((_TRANSLATIONS / f"{lang}.json").read_text(encoding="utf-8"))


def generated_entity_id(lang: str, title: str, platform: str, key: str) -> str | None:
    """The entity ID Home Assistant derives from the device name and the entity name in language ``lang``.

    ``title`` is the device name the user chose (the config entry title). ``None`` if the key has no name.
    """
    data = _NAMES.get(lang)
    if data is None:
        return None
    if platform == "climate":
        area, name = "heating", None  # the entity carries the name of its device
    elif platform == "water_heater":
        area, name = "hot_water", None
    else:
        entry = data["entity"].get(platform, {}).get("raw" if key in RAW_KEYS else key)
        if entry is None or "name" not in entry:
            return None
        area, name = area_of(key), entry["name"].replace("{address}", key.removeprefix("raw_"))
    device = data["device"][area]["name"].replace("{name}", title) if area else title
    return f"{platform}.{slugify(device if name is None else f'{device} {name}')}"


def english_entity_id(coordinator: LuxtronikCoordinator, platform: str, key: str) -> str | None:
    """Entity ID of a new entity: the device name as chosen plus the English names (any system language)."""
    return generated_entity_id("en", coordinator.config_entry.title, platform, key)


def set_english_entity_id(entity: Any, coordinator: LuxtronikCoordinator, platform: str, key: str) -> None:
    """Suggest the English entity ID (a registry entry that already exists keeps its entity ID)."""
    entity_id = english_entity_id(coordinator, platform, key)
    if entity_id is not None:
        entity.entity_id = entity_id


class LuxtronikEntity(CoordinatorEntity[LuxtronikCoordinator]):
    """Entity that is backed by one register."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LuxtronikCoordinator, reg: Register) -> None:
        super().__init__(coordinator)
        self._reg = reg
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{reg.key}"
        self._attr_device_info = coordinator.device_info_for(reg.key)
        if reg.key in RAW_KEYS:
            self._attr_translation_key = "raw"
            self._attr_translation_placeholders = {"address": str(reg.address)}
        else:
            self._attr_translation_key = reg.key
        if reg.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif reg.config:
            self._attr_entity_category = EntityCategory.CONFIG
        self._attr_entity_registry_enabled_default = reg.enabled_default
        set_english_entity_id(self, coordinator, reg.platform, reg.key)

    @property
    def _value(self):
        return (self.coordinator.data or {}).get(self._reg.key)
