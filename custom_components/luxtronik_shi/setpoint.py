"""Shared setpoint semantics of the climate, water heater and number entities.

A heating or hot water setpoint only applies in its circuit's control mode ``setpoint`` (python-luxtronik
holdings.py). The entities show whether it applies and the controller's effective target, and climate and
water heater refuse a target write in another mode. The number entities keep writing in every mode, because
optimizers write them and set the mode themselves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .registers import CONTROL_MODES, SETPOINT_GROUPS

if TYPE_CHECKING:
    from .coordinator import LuxtronikCoordinator

ATTR_SETPOINT_ACTIVE = "setpoint_active"
ATTR_EFFECTIVE_TARGET = "effective_target"


def setpoint_attributes(coordinator: LuxtronikCoordinator, key: str) -> dict[str, Any]:
    """``setpoint_active`` and ``effective_target`` of a setpoint of SETPOINT_GROUPS."""
    return {
        ATTR_SETPOINT_ACTIVE: coordinator.setpoint_active(key),
        ATTR_EFFECTIVE_TARGET: (coordinator.data or {}).get(SETPOINT_GROUPS[key][1]),
    }


def validate_setpoint_write(coordinator: LuxtronikCoordinator, key: str) -> None:
    """Raise a translated ServiceValidationError unless the circuit's control mode is ``setpoint``."""
    if coordinator.setpoint_active(key):
        return
    mode_key = SETPOINT_GROUPS[key][0]
    value = (coordinator.data or {}).get(mode_key)
    mode = CONTROL_MODES[value] if isinstance(value, int) and 0 <= value < len(CONTROL_MODES) else "unknown"
    select = er.async_get(coordinator.hass).async_get_entity_id(
        "select", DOMAIN, f"{coordinator.config_entry.entry_id}_{mode_key}"
    )
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=f"setpoint_not_active_{mode}",
        translation_placeholders={"select": select or mode_key},
    )
