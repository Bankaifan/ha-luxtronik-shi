"""Selects of the Luxtronik SHI (operating modes, levels, power limit mode, block mode)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LuxtronikConfigEntry
from .block_views import MODE_BLOCKS, async_write_sequence, blocks, mode_for, writes_for_mode
from .const import DOMAIN
from .coordinator import LuxtronikCoordinator
from .entity import LuxtronikEntity
from .registers import BLOCK_MODE_KEY, BLOCK_MODES, OVERALL_MODE_KEY, Register

# One write at a time per platform; the Modbus client serialises access to the SHI anyway.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxtronikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the select entities."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            *(LuxtronikSelect(coordinator, reg) for reg in coordinator.registers if reg.platform == "select"),
            LuxtronikBlockModeSelect(coordinator),
        ]
    )


class LuxtronikSelect(LuxtronikEntity, SelectEntity):
    """An enumeration stored in a holding register (the raw value is the option index)."""

    def __init__(self, coordinator: LuxtronikCoordinator, reg: Register) -> None:
        super().__init__(coordinator, reg)
        assert reg.options
        self._attr_options = list(reg.options)

    @property
    def current_option(self) -> str | None:
        """Return the option that is set in the heat pump."""
        value = self._value
        if value is None or not 0 <= value < len(self._reg.options):
            return None
        return self._reg.options[value]

    async def async_select_option(self, option: str) -> None:
        """Write the index of the chosen option.

        The overall mode (10065) has no setpoint: the firmware does not implement mode 1 there and treats it
        like
        0 (docs/firmware-3.92.3-shi-full-analysis.md, 3.1). Writing it would only look like a setting, so it
        is
        refused; the option stays in the list so that a value another client wrote is still shown.
        """
        if self._reg.key == OVERALL_MODE_KEY and option == "setpoint":
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="overall_setpoint_not_implemented"
            )
        await self.coordinator.async_write(self._reg, self._reg.options.index(option))


class LuxtronikBlockModeSelect(CoordinatorEntity[LuxtronikCoordinator], SelectEntity):
    """Operating mode as a view on the heating and hot water blocks (see block_views.py)."""

    _attr_has_entity_name = True
    _attr_translation_key = BLOCK_MODE_KEY
    _attr_options = list(BLOCK_MODES)

    def __init__(self, coordinator: LuxtronikCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{BLOCK_MODE_KEY}"
        self._attr_device_info = coordinator.device_info_for(BLOCK_MODE_KEY)
        self._attr_entity_registry_enabled_default = coordinator.block_views_enabled_default

    @property
    def available(self) -> bool:
        """Unavailable while one of the two block registers has no usable value."""
        return super().available and blocks(self.coordinator) is not None

    @property
    def current_option(self) -> str | None:
        """Heating and hot water, heating only, or hot water only (also shown while both are blocked)."""
        return mode_for(blocks(self.coordinator))

    async def async_select_option(self, option: str) -> None:
        """Write both blocks, releases before blocks (see block_views.py)."""
        if option not in MODE_BLOCKS:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unsupported_operation_mode",
                translation_placeholders={"mode": str(option)},
            )
        await async_write_sequence(self.coordinator, writes_for_mode(option))
