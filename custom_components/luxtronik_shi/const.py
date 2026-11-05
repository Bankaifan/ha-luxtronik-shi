"""Constants for the Luxtronik SHI (Modbus) integration."""

from __future__ import annotations

DOMAIN = "luxtronik_shi"

CONF_SLAVE = "slave"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_FEATURES = "features"

DEFAULT_PORT = 502
DEFAULT_SLAVE = 1
DEFAULT_SCAN_INTERVAL = 30  # seconds, base cycle
MIN_SCAN_INTERVAL = 10
MAX_SCAN_INTERVAL = 600

# Repair issues (issue #24)
# First firmware with the circulation pump and extra hot water registers (README note on the features).
MIN_FIRMWARE = (3, 92)  # firmware 3.92.0
UNREACHABLE_AFTER = 600  # seconds of consecutive failed polls before the "SHI unreachable" issue is raised
ISSUE_FIRMWARE_OLD = "firmware_old"
ISSUE_UNREACHABLE = "shi_unreachable"
ISSUE_VALUES_CHANGED = "values_changed_after_outage"
# Control keys compared before and after an outage (notice only, never written back), with issue text labels.
OUTAGE_WATCH_KEYS = {
    "heating_block": "heating block",
    "dhw_block": "hot water block",
    "cfg_heating_mode": "heating mode",
    "cfg_dhw_mode": "hot water mode",
}

MANUFACTURER = "alpha innotec / Luxtronik"
MODEL = "Smart Home Interface (Modbus/TCP)"
