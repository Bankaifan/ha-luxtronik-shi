"""Constants for the Luxtronik SHI (Modbus) integration."""

from __future__ import annotations

DOMAIN = "luxtronik_shi"

CONF_SLAVE = "slave"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_FEATURES = "features"
CONF_RESTORE_AFTER_RESET = "restore_after_reset"

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

# Restore after a device reset (option, off by default). The SHI drops every value set over Modbus when the
# controller reboots or its watchdog expires; the holding registers then read their reset value 0.
DEFAULT_RESTORE_AFTER_RESET = False
STORE_VERSION = 1
# SHI watchdog: without any Modbus access for this long the SHI discards every value set over it
# (docs/firmware-3.92.3-shi-analysis.md, section "SHI watchdog"). A longer gap since the last successful poll,
# e.g. a Home Assistant downtime, counts like an observed communication outage for the reset detection.
SHI_WATCHDOG_TIMEOUT = 600  # seconds
# The time of the last successful poll is persisted at most this often (no disk write on every poll). The gap
# is compared against SHI_WATCHDOG_TIMEOUT plus this interval, so the throttling never fakes an outage.
LAST_POLL_SAVE_INTERVAL = 60  # seconds
# A device reset detected again within this time after a restore is not restored again (no write loops).
RESTORE_COOLDOWN = 900  # seconds

MANUFACTURER = "alpha innotec / Luxtronik"
MODEL = "Smart Home Interface (Modbus/TCP)"
