"""Switches of the Luxtronik SHI: the four blocks and the on/off view of the blocks.

A block (10050 ... 10053) is a state the writer holds: it stays as written until it is changed or the SHI
watchdog releases it (docs/firmware-3.92.3-shi-full-analysis.md, 3.3 and 4; proven), so a switch is the right
model. The triggers circulation and extra hot water are buttons (button.py), not switches, since 0.18.0.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LuxtronikConfigEntry
from .block_views import (
    async_write_sequence,
    blocks,
    power_for,
    require_state,
    writes_for_off,
    writes_for_on,
)
from .coordinator import LuxtronikCoordinator
from .entity import LuxtronikEntity, set_english_entity_id
from .registers import BLOCK_POWER_KEY

# One write at a time per platform; the Modbus client serialises access to the SHI anyway.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxtronikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the switches."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            *(LuxtronikSwitch(coordinator, reg) for reg in coordinator.registers if reg.platform == "switch"),
            LuxtronikBlockPowerSwitch(coordinator),
        ]
    )


class LuxtronikSwitch(LuxtronikEntity, SwitchEntity):
    """A 0/1 holding register that stays as written (a block): on = 1 = blocked."""

    @property
    def is_on(self) -> bool | None:
        """Return the state read back from the heat pump."""
        value = self._value
        return None if value is None else value == 1

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the register to 1."""
        await self.coordinator.async_write(self._reg, 1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Set the register to 0."""
        await self.coordinator.async_write(self._reg, 0)


class LuxtronikBlockPowerSwitch(CoordinatorEntity[LuxtronikCoordinator], SwitchEntity):
    """On/off as a view on the heating and hot water blocks: off means both are set (see block_views.py)."""

    _attr_has_entity_name = True
    _attr_translation_key = BLOCK_POWER_KEY

    def __init__(self, coordinator: LuxtronikCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{BLOCK_POWER_KEY}"
        self._attr_device_info = coordinator.device_info_for(BLOCK_POWER_KEY)
        set_english_entity_id(self, coordinator, "switch", BLOCK_POWER_KEY)
        self._attr_entity_registry_enabled_default = coordinator.block_views_enabled_default

    @property
    def available(self) -> bool:
        """Unavailable while one of the two block registers has no usable value."""
        return super().available and blocks(self.coordinator) is not None

    @property
    def is_on(self) -> bool | None:
        """Off while both blocks are set."""
        return power_for(blocks(self.coordinator))

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Block hot water, then heating."""
        await async_write_sequence(self.coordinator, writes_for_off())

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Release the hot water block if both blocks are set; do nothing in any other state."""
        # Decided under the sequence lock on a fresh read of both blocks, not on the state before the lock.
        await async_write_sequence(
            self.coordinator, lambda: writes_for_on(require_state(self.coordinator)), read_first=True
        )
