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
from .registers import BLOCK_MODE_KEY, BLOCK_MODES, Register

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


def select_options(reg: Register) -> list[str]:
    """The options a select offers: each option once (raw values the firmware treats alike share one
    option, ``registers._LEVELS``), without the options the firmware does not implement (``unselectable``)."""
    assert reg.options
    return [option for option in dict.fromkeys(reg.options) if option not in reg.unselectable]


class LuxtronikSelect(LuxtronikEntity, SelectEntity):
    """An enumeration stored in a holding register (the raw value is the position in ``Register.options``).

    A raw value whose option is not offered (``unselectable``: the overall mode's ``setpoint``, which the
    firmware does not implement) shows no state; the register value is still visible in the diagnostics and in
    the notice about changes outside Home Assistant.
    """

    def __init__(self, coordinator: LuxtronikCoordinator, reg: Register) -> None:
        super().__init__(coordinator, reg)
        self._attr_options = select_options(reg)

    @property
    def current_option(self) -> str | None:
        """Return the option that is set in the heat pump."""
        value = self._value
        if value is None or not 0 <= value < len(self._reg.options):
            return None
        option = self._reg.options[value]
        return None if option in self._reg.unselectable else option

    async def async_select_option(self, option: str) -> None:
        """Write the raw value of the chosen option (its first position in the register's option tuple)."""
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
