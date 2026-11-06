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
from .registers import Register


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxtronikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the capability flags and the connection sensor."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [LuxtronikOnline(coordinator)]
    entities.extend(
        LuxtronikFlag(coordinator, reg) for reg in coordinator.registers if reg.platform == "binary_sensor"
    )
    entities.extend(LuxtronikStatusBit(coordinator, bit) for bit in STATUS_BITS)
    async_add_entities(entities)


# Bit mask of the input register "heat_generator_state" (10000).
# Bit positions as in python-luxtronik (inputs.py, index 0, heatpump_status): VD1 = bit 0, VD2 = bit 1,
# ZWE1 = bit 2, ZWE2 = bit 3, ZWE3 = bit 4 (since 3.90.1). The first four entries predate the
# heatpump_* keys; the heatpump_* entries of the same bits are disabled by default.
STATUS_BITS: tuple[tuple[str, int, str, str], ...] = (
    ("compressor_1", 0, "Status: Verdichter 1 läuft", "Status: compressor 1 running"),
    ("compressor_2", 1, "Status: Verdichter 2 läuft", "Status: compressor 2 running"),
    ("aux_heater_1", 2, "Status: Zusatzheizung 1 (ZWE) aktiv", "Status: auxiliary heater 1 active"),
    ("aux_heater_2", 3, "Status: Zusatzheizung 2 (ZWE) aktiv", "Status: auxiliary heater 2 active"),
    ("heatpump_vd2_status", 1, "Status: VD2 läuft", "Status: VD2 running"),
    ("heatpump_zwe2_status", 3, "Status: ZWE2 aktiv", "Status: ZWE2 active"),
    ("heatpump_zwe3_status", 4, "Status: ZWE3 aktiv", "Status: ZWE3 active"),
)

# Status bits added without a previous entity: disabled by default so the existing UI does not change.
_DISABLED_BY_DEFAULT: frozenset[str] = frozenset(
    {"heatpump_vd2_status", "heatpump_zwe2_status", "heatpump_zwe3_status"}
)


class LuxtronikFlag(LuxtronikEntity, BinarySensorEntity):
    """A discrete input (or a 0/1 input register) of the heat pump."""

    def __init__(self, coordinator: LuxtronikCoordinator, reg: Register) -> None:
        super().__init__(coordinator, reg)

    @property
    def is_on(self) -> bool | None:
        """Return the flag."""
        value = self._value
        return None if value is None else bool(value)


class LuxtronikStatusBit(CoordinatorEntity[LuxtronikCoordinator], BinarySensorEntity):
    """One bit of the heat generator status mask."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LuxtronikCoordinator, bit: tuple[str, int, str, str]) -> None:
        super().__init__(coordinator)
        self._key, self._bit = bit[0], bit[1]
        self._attr_translation_key = self._key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{self._key}"
        self._attr_device_info = coordinator.device_info
        self._attr_entity_registry_enabled_default = self._key not in _DISABLED_BY_DEFAULT
        if self._key.startswith(("compressor", "heatpump_vd")):
            self._attr_device_class = BinarySensorDeviceClass.RUNNING
        else:
            self._attr_device_class = BinarySensorDeviceClass.HEAT

    @property
    def is_on(self) -> bool | None:
        """Return whether the bit is set."""
        mask = (self.coordinator.data or {}).get("heat_generator_state")
        return None if mask is None else bool(mask & (1 << self._bit))


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
