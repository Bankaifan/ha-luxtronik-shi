"""Constants for the Luxtronik SHI (Modbus) integration."""

from __future__ import annotations

DOMAIN = "luxtronik_shi"

CONF_SLAVE = "slave"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_PORT = 502
DEFAULT_SLAVE = 1
DEFAULT_SCAN_INTERVAL = 30  # seconds, base cycle
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 600

# Heating curve offset, writable via register 10002 (int16, 0.1 K)
HEATING_OFFSET_MIN = -5.0
HEATING_OFFSET_MAX = 5.0
HEATING_OFFSET_STEP = 0.5

MANUFACTURER = "alpha innotec / Luxtronik"
MODEL = "Smart Home Interface (Modbus/TCP)"
