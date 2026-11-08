"""Sensors of the Luxtronik SHI."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import LuxtronikConfigEntry
from .coordinator import LuxtronikCoordinator
from .entity import LuxtronikEntity
from .registers import (
    DERIVED_SENSORS,
    DIFFERENCE_SENSORS,
    FIRMWARE_SENSOR_KEY,
    DerivedSensor,
    DifferenceSensor,
    Register,
    WindowedCop,
    firmware_version,
    overall_cop,
)

# Read-only platform: the coordinator delivers the values, nothing to limit.
PARALLEL_UPDATES = 0


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
    async_add_entities(LuxtronikDifferenceSensor(coordinator, sensor) for sensor in DIFFERENCE_SENSORS)
    async_add_entities([LuxtronikFirmwareSensor(coordinator)])


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

    The power based COP is the energy ratio of a trailing window (see ``WindowedCop``), the overall values the
    ratio of the energy counters. Unknown instead of a number whenever the inputs are missing or implausible.
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
        self._window = WindowedCop()
        self._attr_native_value = None
        self._recalculate()

    def _recalculate(self) -> None:
        data = self.coordinator.data or {}
        thermal = data.get(self._sensor.thermal)
        electric = data.get(self._sensor.electric)
        if not self._sensor.cumulative:
            self._attr_native_value = self._window.add(dt_util.utcnow().timestamp(), thermal, electric)
            return
        self._attr_native_value = overall_cop(thermal, electric, self._previous)
        if thermal is not None and electric is not None:
            self._previous = (thermal, electric)

    def _handle_coordinator_update(self) -> None:
        self._recalculate()
        super()._handle_coordinator_update()


class LuxtronikDifferenceSensor(CoordinatorEntity[LuxtronikCoordinator], SensorEntity):
    """Difference of two registers that are read anyway (flow minus return); unknown if either is missing."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: LuxtronikCoordinator, sensor: DifferenceSensor) -> None:
        super().__init__(coordinator)
        self._sensor = sensor
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{sensor.key}"
        self._attr_translation_key = sensor.key
        self._attr_device_info = coordinator.device_info_for(sensor.key)
        # No temperature device class: Home Assistant would convert a difference like an absolute temperature.
        self._attr_native_unit_of_measurement = sensor.unit

    def _operands(self) -> tuple[float | None, float | None]:
        data = self.coordinator.data or {}
        return data.get(self._sensor.minuend), data.get(self._sensor.subtrahend)

    @property
    def available(self) -> bool:
        """Unavailable while either source has no value."""
        return super().available and None not in self._operands()

    @property
    def native_value(self) -> float | None:
        """Minuend minus subtrahend, rounded to the 0.1 K of the sources."""
        minuend, subtrahend = self._operands()
        if minuend is None or subtrahend is None:
            return None
        return round(minuend - subtrahend, 1)


class LuxtronikFirmwareSensor(CoordinatorEntity[LuxtronikCoordinator], SensorEntity):
    """Firmware version of the heat pump as one text, e.g. ``3.92.3`` (the three version registers joined)."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: LuxtronikCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{FIRMWARE_SENSOR_KEY}"
        self._attr_device_info = coordinator.device_info_for(FIRMWARE_SENSOR_KEY)
        self._attr_translation_key = FIRMWARE_SENSOR_KEY

    @property
    def native_value(self) -> str | None:
        """The version, ``None`` until all three parts have been read."""
        return firmware_version(self.coordinator.data or {})
