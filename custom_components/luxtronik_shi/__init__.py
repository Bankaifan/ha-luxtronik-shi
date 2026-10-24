"""Luxtronik SHI (Modbus/TCP) – alpha innotec / Luxtronik heat pumps."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_SCAN_INTERVAL, CONF_SLAVE, DEFAULT_SCAN_INTERVAL
from .coordinator import LuxtronikCoordinator
from .modbus_client import LuxtronikModbusClient

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH, Platform.NUMBER]

type LuxtronikConfigEntry = ConfigEntry[LuxtronikCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: LuxtronikConfigEntry) -> bool:
    """Set up one heat pump."""
    client = LuxtronikModbusClient(entry.data[CONF_HOST], entry.data[CONF_PORT], entry.data[CONF_SLAVE])
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = LuxtronikCoordinator(hass, entry, client, scan_interval)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.close()
        raise

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LuxtronikConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.close()
    return unloaded
