"""Which registers are polled: those with an enabled entity, plus everything the integration uses itself."""

from __future__ import annotations

from collections.abc import Iterable

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DEFERRED_KEYS, DHW_BLOCK_KEY, DOMAIN, OUTAGE_WATCH_KEYS, RESTORE_KEYS
from .registers import (
    CAPABILITIES,
    DERIVED_SENSORS,
    FIRMWARE_PARTS,
    SETPOINT_GROUPS,
    Register,
)

# Registers read by the climate and water heater entities (see climate.py, water_heater.py) and by the status
# bit binary sensors (bits of ``heat_generator_state``). Those entities are not registers of their own, so a
# disabled register entity must not stop their values. ``tests/test_poll_plan.py`` checks this list against
# the platform modules.
PLATFORM_SOURCE_KEYS: frozenset[str] = frozenset(
    {
        "cfg_heating_mode",
        "cfg_heating_setpoint",
        "return",
        "heating_block",
        "operating_mode",
        "heat_generator_state",
        "cfg_dhw_mode",
        "cfg_dhw_setpoint",
        "dhw",
    }
)


def internal_keys() -> frozenset[str]:
    """Keys that are polled whether or not their entity is enabled.

    Whatever the coordinator itself reads is in here: the firmware parts (version, repair issue), the control
    values compared after an outage, every key that can be restored, is deferred or blocked (reset detection,
    write read-back, hot water rules), the setpoint groups (mode and effective target), the inputs of the COP
    sensors, the equipment flags (diagnostics) and the sources of the climate, water heater and status bit
    entities. When in doubt a key belongs here: reading it costs a little traffic, missing it breaks logic.
    """
    keys: set[str] = set(FIRMWARE_PARTS)
    keys |= set(OUTAGE_WATCH_KEYS)
    keys |= RESTORE_KEYS
    keys |= DEFERRED_KEYS
    keys.add(DHW_BLOCK_KEY)
    for setpoint, (mode, target) in SETPOINT_GROUPS.items():
        keys |= {setpoint, mode, target}
    for sensor in DERIVED_SENSORS:
        keys |= {sensor.thermal, sensor.electric}
    keys |= {reg.key for reg in CAPABILITIES}
    keys |= PLATFORM_SOURCE_KEYS
    return frozenset(keys)


def entity_enabled(registry: er.EntityRegistry, entry_id: str, reg: Register) -> bool:
    """Whether the entity of a register is enabled; before it exists, whether it will be created enabled."""
    entity_id = registry.async_get_entity_id(reg.platform, DOMAIN, f"{entry_id}_{reg.key}")
    entity = registry.async_get(entity_id) if entity_id else None
    if entity is None:
        return reg.enabled_default
    return entity.disabled_by is None


def select_polled(
    hass: HomeAssistant, entry_id: str, registers: Iterable[Register]
) -> tuple[Register, ...]:
    """The registers to poll: enabled entities and internal keys, in the order of ``registers``."""
    registry = er.async_get(hass)
    internal = internal_keys()
    return tuple(
        reg for reg in registers if reg.key in internal or entity_enabled(registry, entry_id, reg)
    )
