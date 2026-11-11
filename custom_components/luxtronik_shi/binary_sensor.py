"""Binary sensors of the Luxtronik SHI."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LuxtronikConfigEntry
from .coordinator import LuxtronikCoordinator
from .entity import LuxtronikEntity, set_english_entity_id
from .registers import BY_KEY, DERIVED_FLAGS, DerivedFlag, Register, usable

# Read-only platform: the coordinator delivers the values, nothing to limit.
PARALLEL_UPDATES = 0


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
    entities.extend(LuxtronikDerivedFlag(coordinator, flag) for flag in DERIVED_FLAGS)
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
        if reg.device_class:
            self._attr_device_class = BinarySensorDeviceClass(reg.device_class)

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
        set_english_entity_id(self, coordinator, "binary_sensor", self._key)
        if self._key.startswith(("compressor", "heatpump_vd")):
            self._attr_device_class = BinarySensorDeviceClass.RUNNING
        else:
            self._attr_device_class = BinarySensorDeviceClass.HEAT

    @property
    def is_on(self) -> bool | None:
        """Return whether the bit is set."""
        mask = (self.coordinator.data or {}).get("heat_generator_state")
        return None if mask is None else bool(mask & (1 << self._bit))


class LuxtronikDerivedFlag(CoordinatorEntity[LuxtronikCoordinator], BinarySensorEntity):
    """A flag calculated from a status register that is read anyway (no extra Modbus traffic)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LuxtronikCoordinator, flag: DerivedFlag) -> None:
        super().__init__(coordinator)
        self._flag = flag
        self._attr_translation_key = flag.key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{flag.key}"
        self._attr_device_info = coordinator.device_info_for(flag.key)
        set_english_entity_id(self, coordinator, "binary_sensor", flag.key)
        if flag.device_class:
            self._attr_device_class = BinarySensorDeviceClass(flag.device_class)

    @property
    def _source(self) -> int | None:
        """The source value, ``None`` if missing, 0x7FFF ("not available") or outside the option tuple."""
        value = usable(self._flag.source, (self.coordinator.data or {}).get(self._flag.source))
        if value is None:
            return None
        options = BY_KEY[self._flag.source].options
        if options is not None and not 0 <= value < len(options):
            return None
        return int(value)

    @property
    def available(self) -> bool:
        """Unavailable while the source register has no usable value."""
        return super().available and self._source is not None

    @property
    def is_on(self) -> bool | None:
        """Whether the source holds one of the values that switch the flag on."""
        value = self._source
        if value is None:
            return None
        if self._flag.on_values is None:
            return value != 0
        return value in self._flag.on_values


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
        set_english_entity_id(self, coordinator, "binary_sensor", "online")

    @property
    def available(self) -> bool:
        """Always available – the state itself carries the information."""
        return True

    @property
    def is_on(self) -> bool:
        """Return whether the last poll succeeded."""
        return self.coordinator.last_update_success
