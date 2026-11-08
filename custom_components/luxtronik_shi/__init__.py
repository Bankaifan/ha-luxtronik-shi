"""Luxtronik SHI (Modbus/TCP) – alpha innotec / Luxtronik heat pumps."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import (
    CONF_FEATURES,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    STORE_VERSION,
)
from .coordinator import LuxtronikCoordinator, restore_store_key
from .modbus_client import LuxtronikModbusClient
from .registers import (
    BLOCK_SELECT_KEYS,
    BLOCK_SWITCH_KEYS,
    CLIMATE_KEYS,
    REMOVED_ENTITIES,
    REMOVED_KEYS,
    RENAMED_KEYS,
    WATER_HEATER_KEYS,
    active_registers,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
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


def async_remove_obsolete_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the registry entries of entities that no longer exist.

    ``REMOVED_KEYS``: keys without any entity (on every platform). ``REMOVED_ENTITIES``: keys that moved to
    another platform; only the entry of the old platform goes (the switches ``circulation`` and ``extra_dhw``
    of 0.16.x, which are buttons since 0.17.0). Without this, a dead entity would stay in the registry
    forever.
    """
    registry = er.async_get(hass)
    obsolete = {f"{entry.entry_id}_{key}" for key in REMOVED_KEYS}
    moved = {(domain, f"{entry.entry_id}_{key}") for domain, key in REMOVED_ENTITIES}
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.platform != DOMAIN:
            continue
        if entity.unique_id in obsolete or (entity.domain, entity.unique_id) in moved:
            _LOGGER.info("%s: removing the obsolete entity %s", entry.title, entity.entity_id)
            registry.async_remove(entity.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: LuxtronikConfigEntry) -> bool:
    """Set up one heat pump."""
    await async_migrate_renamed_keys(hass, entry)
    async_remove_obsolete_entities(hass, entry)
    client = LuxtronikModbusClient(entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data[CONF_SLAVE])
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    if scan_interval > MAX_SCAN_INTERVAL:
        # Entries from before the 5 minute limit keep their stored option (no options migration exists); the
        # coordinator polls at the maximum. Saving the options once stores the new value.
        _LOGGER.warning(
            "%s: update interval %d s is longer than the maximum of %d s (SHI watchdog); polling every %d s",
            entry.title, scan_interval, MAX_SCAN_INTERVAL, MAX_SCAN_INTERVAL,
        )
        scan_interval = MAX_SCAN_INTERVAL
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
    # And for the block select and switch (added after 0.14.0): an entry that already has entities keeps them
    # disabled until the owner enables them.
    has_block_views = any(
        (e.domain == Platform.SELECT and e.unique_id.endswith(f"_{BLOCK_SELECT_KEYS[0]}"))
        or (e.domain == Platform.SWITCH and e.unique_id.endswith(f"_{BLOCK_SWITCH_KEYS[0]}"))
        for e in known
    )
    coordinator.block_views_enabled_default = not known or has_block_views

    entry.runtime_data = coordinator
    coordinator.async_setup_devices()
    entry.async_on_unload(coordinator.async_track_entity_enablement())
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: LuxtronikConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Let the user delete a sub-device the configured equipment no longer has (cooling or pool switched off).

    The main device and every sub-device that still has entities cannot be deleted.
    """
    active = {f"{entry.entry_id}_{area}" for area in entry.runtime_data.active_areas() if area}
    active.add(entry.entry_id)
    in_use = (domain == DOMAIN and identifier in active for domain, identifier in device_entry.identifiers)
    return not any(in_use)


async def async_unload_entry(hass: HomeAssistant, entry: LuxtronikConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data.async_delete_issues()
        entry.runtime_data.async_cancel_rechecks()
        await entry.runtime_data.async_save_last_poll()
        await entry.runtime_data.client.close()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: LuxtronikConfigEntry) -> None:
    """Delete the values remembered for a restore after a device reset."""
    await Store(hass, STORE_VERSION, restore_store_key(entry.entry_id)).async_remove()
