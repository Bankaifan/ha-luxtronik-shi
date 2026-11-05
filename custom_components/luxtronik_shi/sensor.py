"""Sensors of the Luxtronik SHI."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LuxtronikConfigEntry
from .coordinator import LuxtronikCoordinator
from .entity import LuxtronikEntity
from .registers import DERIVED_SENSORS, DerivedSensor, Register, instantaneous_cop, overall_cop


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LuxtronikConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one sensor per measurement register plus the calculated COP sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        LuxtronikSensor(coordinator, reg) for reg in coordinator.registers if reg.platform == "sensor"
    )
    async_add_entities(LuxtronikCopSensor(coordinator, sensor) for sensor in DERIVED_SENSORS)


class LuxtronikSensor(LuxtronikEntity, SensorEntity):
    """A numeric value of the heat pump."""

    def __init__(self, coordinator: LuxtronikCoordinator, reg: Register) -> None:
        super().__init__(coordinator, reg)
        self._attr_native_unit_of_measurement = reg.unit
        if reg.device_class:
            self._attr_device_class = SensorDeviceClass(reg.device_class)
        if reg.state_class:
            self._attr_state_class = SensorStateClass(reg.state_class)
        if reg.precision is not None:
            self._attr_suggested_display_precision = reg.precision
        if reg.options:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(reg.options)

    @property
    def native_value(self) -> float | int | None:
        """Return the current value (enumerations as their option key)."""
        value = self._value
        options = self._reg.options
        if options is None or value is None:
            return value
        return options[value] if 0 <= value < len(options) else None


class LuxtronikCopSensor(CoordinatorEntity[LuxtronikCoordinator], SensorEntity):
    """COP calculated from registers that are read anyway (no extra Modbus traffic).

    Unknown instead of a number whenever the inputs are missing, zero, negative or implausible.
    """

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: LuxtronikCoordinator, sensor: DerivedSensor) -> None:
        super().__init__(coordinator)
        self._sensor = sensor
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{sensor.key}"
        self._attr_translation_key = sensor.key
        self._attr_device_info = coordinator.device_info_for(sensor.key)
        self._previous: tuple[float, float] | None = None
        self._attr_native_value = None
        self._recalculate()

    def _recalculate(self) -> None:
        data = self.coordinator.data or {}
        thermal = data.get(self._sensor.thermal)
        electric = data.get(self._sensor.electric)
        if not self._sensor.cumulative:
            self._attr_native_value = instantaneous_cop(thermal, electric)
            return
        self._attr_native_value = overall_cop(thermal, electric, self._previous)
        if thermal is not None and electric is not None:
            self._previous = (thermal, electric)

    def _handle_coordinator_update(self) -> None:
        self._recalculate()
        super()._handle_coordinator_update()
