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
# At most 5 minutes: the SHI watchdog drops every value set over the SHI after 600 s without Modbus access
# (docs/firmware-3.92.3-shi-analysis.md, "SHI watchdog"), so a longer interval could lose them between polls.
MAX_SCAN_INTERVAL = 300

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
# Only these keys are remembered and restored: the mode, level, offset and setpoint of each circuit, and the
# room setpoint. Blocks (heating_block, dhw_block, cooling_block, pool_block), circulation, extra_dhw (effect
# open, may be one-shot) and the power limit are deliberately left out: an optimizer such as the Heat Pump
# Optimizer owns them live, and re-applying a block after a long downtime would invert the fail-safe of the
# SHI watchdog (all values released). The overall group (cfg_overall_*, 10065-10067) is left out too: its
# semantics are unproven (on the reference installation 10065 fell back to `off` about 2 s after a write, and
# python-luxtronik gives the overall mode no setpoint). Edit this set to change what is restored.
RESTORE_KEYS: frozenset[str] = frozenset(
    {
        "cfg_heating_mode",
        "cfg_heating_setpoint",
        "cfg_heating_offset",
        "cfg_heating_level",
        "cfg_dhw_mode",
        "cfg_dhw_setpoint",
        "cfg_dhw_offset",
        "cfg_dhw_level",
        "cfg_mk1_mode",
        "cfg_mk1_setpoint",
        "cfg_mk1_offset",
        "cfg_mk1_level",
        "cfg_mk1_cool_mode",
        "cfg_mk1_cool_setpoint",
        "cfg_mk1_cool_offset",
        "cfg_mk2_mode",
        "cfg_mk2_setpoint",
        "cfg_mk2_offset",
        "cfg_mk2_level",
        "cfg_mk2_cool_mode",
        "cfg_mk2_cool_setpoint",
        "cfg_mk2_cool_offset",
        "cfg_mk3_mode",
        "cfg_mk3_setpoint",
        "cfg_mk3_offset",
        "cfg_mk3_level",
        "cfg_mk3_cool_mode",
        "cfg_mk3_cool_setpoint",
        "cfg_mk3_cool_offset",
        "cfg_room_setpoint",
    }
)
# The SHI answers 0x7FFF for a register that is not available (docs/firmware-3.92.3-shi-analysis.md,
# dispatcher 0x000d9298). Never a reset value and never learned.
SHI_NOT_AVAILABLE = 0x7FFF
# A re-established Modbus connection counts as an outage signal. ASSUMPTION, not measured on the reference
# installation yet: the SHI keeps the TCP connection open between polls, so a reconnect means the controller
# dropped it. If reconnects happen on at least RECONNECT_GUARD_COUNT of the last RECONNECT_GUARD_POLLS polls,
# the assumption does not hold for this setup and the signal is switched off for the session.
RECONNECT_GUARD_POLLS = 5
RECONNECT_GUARD_COUNT = 3
# Keys whose reset value is not 0: on watchdog expiry and at boot the controller reverts setpoints to their
# persisted parameter or fixed default, while modes and levels read 0 (docs/firmware-3.92.3-shi-analysis.md,
# "SHI watchdog"). After an outage such a key counts as reverted if it reads any non-zero value, or exactly
# its learned value once one was observed in a confirmed reset. Offsets are *assumed* to revert to 0 (not
# proven): if not, a reset with a non-zero offset remembered is not recognised and nothing is overwritten.
RESET_TO_DEFAULT_SUFFIXES = ("_setpoint",)
# Remembered values older than this (time since the last successful poll) are dropped at setup: an optimizer
# such as the Heat Pump Optimizer rewrites modes and setpoints live, so a day-old value is no longer meant.
RESTORE_MAX_GAP = 24 * 3600  # seconds
# A device reset detected again within this time after a restore is not restored again (no write loops).
RESTORE_COOLDOWN = 900  # seconds

MANUFACTURER = "alpha innotec / Luxtronik"
MODEL = "Smart Home Interface (Modbus/TCP)"
