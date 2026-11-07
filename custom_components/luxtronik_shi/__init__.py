"""Luxtronik SHI (Modbus/TCP) – alpha innotec / Luxtronik heat pumps."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import CONF_FEATURES, CONF_SCAN_INTERVAL, CONF_SLAVE, DEFAULT_SCAN_INTERVAL, DOMAIN, STORE_VERSION
from .coordinator import LuxtronikCoordinator, restore_store_key
from .modbus_client import LuxtronikModbusClient
from .registers import CLIMATE_KEYS, RENAMED_KEYS, WATER_HEATER_KEYS, active_registers

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.CLIMATE,
    Platform.WATER_HEATER,
]

type LuxtronikConfigEntry = ConfigEntry[LuxtronikCoordinator]


async def async_migrate_renamed_keys(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Move registry entries of renamed keys (``RENAMED_KEYS``) to the new unique ID.

    Only the unique ID changes. The entity ID, the name chosen by the user, the area and the enabled/disabled
    state stay as they are. If the new unique ID already exists, the old entry is left alone.
    """
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_"

    @callback
    def _migrate(entity: er.RegistryEntry) -> dict[str, str] | None:
        if entity.platform != DOMAIN or not entity.unique_id.startswith(prefix):
            return None
        new_key = RENAMED_KEYS.get(entity.unique_id.removeprefix(prefix))
        if new_key is None:
            return None
        new_unique_id = f"{prefix}{new_key}"
        if registry.async_get_entity_id(entity.domain, DOMAIN, new_unique_id):
            return None
        return {"new_unique_id": new_unique_id}

    await er.async_migrate_entries(hass, entry.entry_id, _migrate)


async def async_setup_entry(hass: HomeAssistant, entry: LuxtronikConfigEntry) -> bool:
    """Set up one heat pump."""
    await async_migrate_renamed_keys(hass, entry)
    client = LuxtronikModbusClient(entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data[CONF_SLAVE])
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    # Entries created before 0.3.0 have no equipment option: keep every entity.
    registers = active_registers(entry.options.get(CONF_FEATURES))
    coordinator = LuxtronikCoordinator(hass, entry, client, scan_interval, registers)
    await coordinator.async_load_remembered()
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.close()
        raise

    # The climate entity is enabled by default only on new installations: an entry that already has
    # entities but no climate entity yet was set up before the platform existed.
    known = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    has_climate = any(e.domain == Platform.CLIMATE and e.unique_id.endswith(CLIMATE_KEYS[0]) for e in known)
    coordinator.climate_enabled_default = not known or has_climate
    # Same rule for the water heater entity (added later than the climate entity).
    has_water_heater = any(
        e.domain == Platform.WATER_HEATER and e.unique_id.endswith(WATER_HEATER_KEYS[0]) for e in known
    )
    coordinator.water_heater_enabled_default = not known or has_water_heater

    entry.runtime_data = coordinator
    coordinator.async_setup_devices()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LuxtronikConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data.async_delete_issues()
        await entry.runtime_data.client.close()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: LuxtronikConfigEntry) -> None:
    """Delete the values remembered for a restore after a device reset."""
    await Store(hass, STORE_VERSION, restore_store_key(entry.entry_id)).async_remove()
