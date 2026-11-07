"""Diagnostics download for bug reports (no Modbus access, only data the coordinator already holds)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from . import LuxtronikConfigEntry
from .const import CONF_FEATURES
from .coordinator import plan_blocks
from .registers import FEATURE_CAPABILITY, FEATURES, FIRMWARE_PARTS, Register, firmware_version

# Host, MAC address and everything that identifies the installation (unique ID contains the host).
TO_REDACT = {CONF_HOST, CONF_MAC, "unique_id", "serial", "serial_number", "title"}
REDACTED = "**REDACTED**"


def _raw(reg: Register, value: Any) -> int | bool | None:
    """Raw register value reconstructed from the decoded one (the coordinator only stores decoded values)."""
    if value is None:
        return None
    if reg.kind == "discrete":
        return bool(value)
    raw = int(round(value / reg.scale))
    if reg.dtype == "uint32":
        return raw % 0x100000000
    return raw % 0x10000


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _scrub(value: Any, secrets: set[str]) -> Any:
    """Remove secret strings that might be embedded in free text (e.g. a title that contains the IP)."""
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, REDACTED)
        return value
    if isinstance(value, dict):
        return {k: _scrub(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v, secrets) for v in value]
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LuxtronikConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    integration = await async_get_integration(hass, entry.domain)

    blocks: dict[str, Any] = {}
    for block in plan_blocks(coordinator.polled_registers):
        name = f"{block.kind}_{block.start}_{block.count}"
        blocks[name] = {
            "kind": block.kind,
            "start": block.start,
            "count": block.count,
            "every": block.every,
            "registers": {
                reg.key: {
                    "address": reg.address,
                    "raw": _raw(reg, data.get(reg.key)),
                    "value": data.get(reg.key),
                }
                for reg in block.registers
            },
        }

    features = entry.options.get(CONF_FEATURES)
    stats = coordinator.poll_stats
    interval = coordinator.update_interval
    flags = {feature: data.get(cap) for feature, cap in FEATURE_CAPABILITY.items()}
    result = {
        "integration_version": str(integration.version),
        "home_assistant_version": HA_VERSION,
        "config_entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
            "unique_id": REDACTED,
            "title": REDACTED,
        },
        "features": {
            # None: entry created before 0.3.0, all registers are polled
            "selected": list(features) if features is not None else None,
            "available": list(FEATURES),
            "capability_flags": flags,
        },
        "firmware": {k: data.get(k) for k in FIRMWARE_PARTS} | {"version": firmware_version(data)},
        "last_update_success": coordinator.last_update_success,
        # Raw values this integration wrote and would re-apply after a device reset (option on).
        "restore_after_reset": {
            "enabled": coordinator.restore_enabled,
            "remembered": coordinator.remembered,
            "learned": coordinator.learned,
        },
        "connection": {
            "reconnects": coordinator.client.reconnects,
            "last_reconnect": (
                coordinator.client.last_reconnect.isoformat() if coordinator.client.last_reconnect else None
            ),
            "reconnect_is_outage_signal": coordinator.reconnect_signal_active,
        },
        "polling": {
            "interval_seconds": interval.total_seconds() if interval else None,
            "polls": stats.polls,
            "failed_polls": stats.failed,
            "failed_in_a_row": coordinator.failed_in_a_row,
            "last_poll_seconds": stats.last_duration,
            "last_success": _iso(stats.last_success),
            "last_failure": _iso(stats.last_failure),
            "last_error": stats.last_error,
            "registers_polled": len(coordinator.polled_registers),
            # Registers of disabled entities are not read until their entity is enabled.
            "registers_not_polled": sorted(
                reg.key for reg in coordinator.registers if reg not in coordinator.polled_registers
            ),
        },
        "blocks": blocks,
    }
    secrets = {str(v) for k, v in entry.data.items() if k in (CONF_HOST, CONF_MAC) and v}
    return _scrub(result, secrets)
