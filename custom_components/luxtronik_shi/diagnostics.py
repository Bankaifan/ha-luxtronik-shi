"""Diagnostics download for bug reports (no Modbus access, only data the coordinator already holds)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_MAC
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from . import LuxtronikConfigEntry
from .const import CONF_FEATURES
from .coordinator import plan_blocks
from .registers import FEATURE_CAPABILITY, FEATURES, Register

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
    for block in plan_blocks(coordinator.registers):
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
        "firmware": {k: data.get(k) for k in ("fw_platform", "fw_major", "fw_minor")},
        "last_update_success": coordinator.last_update_success,
        "blocks": blocks,
    }
    secrets = {str(v) for k, v in entry.data.items() if k in (CONF_HOST, CONF_MAC) and v}
    return _scrub(result, secrets)
