"""Buttons of the Luxtronik SHI: the trigger registers circulation run (10070) and extra hot water (10071).

Both registers are triggers (docs/firmware-3.92.3-shi-full-analysis.md, 3.2 and 3.3; proven): a write of 1
starts the action, and the firmware sets the register back to 0 by itself when the action is over
(circulation: once no run is active; extra hot water: when its timer ends). A trigger is not a state the
user holds, so it is a button. The running state is the binary sensor ``extra_dhw_running`` on 10071 and, for
circulation, the pump output ``pump_circulation`` (ZIP, 10356), which also covers runs of the controller's
time program. The write goes through the coordinator like every other write (own-write bookkeeping,
read-back); a read-back of 0 is the normal end and is not reported (``const.TRIGGER_KEYS``).

``extra_dhw_stop`` writes 0 to 10071, which sets the extra hot water timer to 0 (proven). ``circulation_stop``
writes 0 to 10070, which ends a circulation run at once unless the time program requests circulation at the
same time (firmware V3.92.3, FUN_00275f94; proven; see ``registers.TRIGGER_ACTIONS``). The circulation
trigger is not accepted while the controller's hot water operating mode is "off" or "holiday"; "off" is
visible as the flag ``hot_water_available`` (``registers.TRIGGER_REQUIRES``), so both circulation buttons
are unavailable then.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LuxtronikConfigEntry
from .const import DOMAIN
from .coordinator import LuxtronikCoordinator
from .entity import LuxtronikEntity, set_english_entity_id
from .registers import (
    BY_KEY,
    TRIGGER_ACTIONS,
    TRIGGER_FOLLOWUPS,
    TRIGGER_REQUIRES,
    Register,
    TriggerAction,
    usable,
)

# One write at a time per platform; the Modbus client serialises access to the SHI anyway.
PARALLEL_UPDATES = 1
# The word a trigger register is written with on press.
TRIGGER_START = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxtronikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the trigger buttons: one start button per trigger register, plus the fixed actions."""
    coordinator = entry.runtime_data
    keys = {reg.key for reg in coordinator.registers}
    entities: list[ButtonEntity] = [
        LuxtronikTriggerButton(coordinator, reg) for reg in coordinator.registers if reg.platform == "button"
    ]
    entities.extend(
        LuxtronikTriggerButton(coordinator, BY_KEY[action.register], action)
        for action in TRIGGER_ACTIONS
        if action.register in keys
    )
    async_add_entities(entities)


class LuxtronikTriggerButton(LuxtronikEntity, ButtonEntity):
    """Writes one word to a trigger register: 1 (start) for the register's own button, else the action's."""

    def __init__(
        self, coordinator: LuxtronikCoordinator, reg: Register, action: TriggerAction | None = None
    ) -> None:
        super().__init__(coordinator, reg)
        self._raw = TRIGGER_START if action is None else action.raw
        if action is not None:
            self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{action.key}"
            self._attr_translation_key = action.key
            set_english_entity_id(self, coordinator, "button", action.key)
        self._followups = TRIGGER_FOLLOWUPS.get(reg.key, ())
        self._requires = TRIGGER_REQUIRES.get(reg.key)

    def _blocked(self) -> bool:
        """Whether the controller would not accept the trigger (its equipment flag reads off)."""
        if self._requires is None:
            return False
        return (self.coordinator.data or {}).get(self._requires) is False

    @property
    def available(self) -> bool:
        """Unavailable while the register is missing or reads "not available" (0x7FFF), or the trigger is
        blocked by the controller's hot water operating mode."""
        if not super().available or usable(self._reg.key, self._value) is None:
            return False
        return not self._blocked()

    async def async_press(self) -> None:
        """Write the trigger word and read the register back."""
        if self._blocked():
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="trigger_blocked",
                translation_placeholders={"key": self._reg.key, "flag": self._requires or ""},
            )
        await self.coordinator.async_write(self._reg, self._raw)
        self.coordinator.schedule_reread(self._reg.key, self._followups)
