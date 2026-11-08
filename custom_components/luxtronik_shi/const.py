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
# A poll that fails once is not shown as "unavailable" on every entity: the previous values stay for this many
# failed polls in a row (a short glitch of the network or a busy controller). The failure still counts for the
# unreachable issue and for the outage signal of the restore and the change notices.
POLL_FAILURES_TOLERATED = 1
UNREACHABLE_AFTER = 600  # seconds of consecutive failed polls before the "SHI unreachable" issue is raised
ISSUE_FIRMWARE_OLD = "firmware_old"
ISSUE_UNREACHABLE = "shi_unreachable"
ISSUE_VALUES_CHANGED = "values_changed_after_outage"
# A writable holding changed between two polls without a write through Home Assistant (another Modbus client,
# the native Luxtronik protocol on port 8889, OpenEMS, the controller panel). Notice only, nothing is written
# back.
ISSUE_EXTERNAL_CHANGE = "values_changed_externally"
# A polled value equal to a value this integration tried to write within this time counts as its own write
# (covers a write that reached the device although its answer was lost).
OWN_WRITE_WINDOW = 600  # seconds
# Triggers: writable keys the firmware sets back to 0 by itself (docs/firmware-3.92.3-shi-full-analysis.md,
# sections 3.2 and 3.3; proven). ``circulation`` (10070) starts a circulation run and reads 0 again once no
# run is active; ``extra_dhw`` (10071) starts extra hot water for the controller's duration (parameter 1147,
# sensor ``extra_dhw_duration``) and reads 0 again when the timer ends (``extra_dhw_remaining`` counts
# down). They are buttons (press = write 1; ``circulation_stop`` and ``extra_dhw_stop`` write 0), not switches
# (0.17.x); the running state is ``extra_dhw_running`` and the pump output ``pump_circulation``: a read-back
# of 0 is the normal end
# of the action, never a failed write, a device reset or another writer, so they are not restored after a
# reset, not compared for changes outside Home Assistant, and a default read-back after a write is not
# reported for them.
TRIGGER_KEYS: frozenset[str] = frozenset({"extra_dhw", "circulation"})
# Writable keys the controller changes by itself, so a change is no evidence of another writer: the triggers.
EXTERNAL_CHANGE_EXCLUDED: frozenset[str] = TRIGGER_KEYS
# Control keys compared before and after an outage (notice only, never written back), with issue text labels.
OUTAGE_WATCH_KEYS = {
    "heating_block": "heating block",
    "dhw_block": "hot water block",
    "cfg_heating_mode": "heating mode",
    "cfg_dhw_mode": "hot water mode",
}

# Restore after a device reset (option, off by default). The SHI drops every value set over Modbus when the
# controller reboots or its watchdog expires; the holding registers then read their default
# (``Register.reset_default``:
# 0 for modes, levels, offsets, blocks and triggers; 350 / 400 / 200 for the setpoints, 300 for the power
# limit).
DEFAULT_RESTORE_AFTER_RESET = False
STORE_VERSION = 1
# SHI watchdog: without any Modbus access (any function code, reads included) for this long the SHI reverts
# every value set over it: t2 items (the SHI holdings) to their defaults, t1 parameters (10060) to their
# persisted value. Expiry and the first access afterwards are written to the controller's event log (type
# 0x10),
# so both can be checked at the control panel (docs/firmware-3.92.3-shi-full-analysis.md, 4; proven). A longer
# gap since the last successful poll, e.g. a Home Assistant downtime, counts like an observed communication
# outage for the reset detection.
SHI_WATCHDOG_TIMEOUT = 600  # seconds
# The time of the last successful poll is persisted at most this often (no disk write on every poll). The gap
# is compared against SHI_WATCHDOG_TIMEOUT plus this interval, so the throttling never fakes an outage.
LAST_POLL_SAVE_INTERVAL = 60  # seconds
# Only these keys are remembered and restored: the mode, level, offset and setpoint of each circuit, and the
# room setpoint. Blocks (heating_block, dhw_block, cooling_block, pool_block), the triggers circulation and
# extra_dhw (TRIGGER_KEYS: the firmware ends them itself) and the power limit are deliberately left out: an
# optimizer such as the Heat Pump Optimizer owns them live, and re-applying a block after a long downtime
# would
# invert the fail-safe of the SHI watchdog (all values released). The overall group (cfg_overall_*,
# 10065-10067)
# is left out too: it is proven to override the heating and mixing circuit modes (full analysis, 3.1), so an
# automatic re-apply could silently override what an optimizer sets per circuit (owner decision; on the
# reference
# installation 10065 once fell back to `off` about 2 s after a write). Edit this set to change what is
# restored.
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
# dispatcher 0x000d9298) and silently skips a write to it. Never a reset value and never learned. Which
# equipment
# makes a register available is listed per register in docs/firmware-3.92.3-shi-full-analysis.md (visibility).
SHI_NOT_AVAILABLE = 0x7FFF
# The controller parameter 1161 "Enable SHI" (menu, options Modbus TCP / myUplink / both) is not readable over
# Modbus. While it is 0 the heating, hot water, mixing circuit and power limit registers are accepted and read
# back but ignored by the controller; the blocks 10050-10053, circulation and extra hot water work regardless
# (docs/firmware-3.92.3-shi-full-analysis.md, 5.6; proven). Named in the diagnostics download as a hint.
ENABLE_SHI_PARAMETER = 1161
# A re-established Modbus connection counts as an outage signal. ASSUMPTION, not measured on the reference
# installation yet: the SHI keeps the TCP connection open between polls, so a reconnect means the controller
# dropped it. If reconnects happen on at least RECONNECT_GUARD_COUNT of the last RECONNECT_GUARD_POLLS polls,
# the assumption does not hold for this setup and the signal is switched off for the session.
RECONNECT_GUARD_POLLS = 5
RECONNECT_GUARD_COUNT = 3
# Keys whose reset value is not 0: on watchdog expiry, at boot and after a write outside the range the
# controller
# reverts the setpoints to their fixed defaults (350 / 400 / 200 in 0.1 degC, ``Register.reset_default``; the
# room
# setpoint 10060 to its persisted parameter), while modes, levels, offsets, blocks and triggers read 0
# (docs/firmware-3.92.3-shi-full-analysis.md, 3.4 and 4; proven). After an outage such a key counts as
# reverted if
# it reads its proven default, any non-zero value while no reset was observed yet, or exactly its learned
# value
# once one was observed in a confirmed reset (the learned value covers a firmware that uses other defaults).
RESET_TO_DEFAULT_SUFFIXES = ("_setpoint",)
# Remembered values older than this (time since the last successful poll) are dropped at setup: an optimizer
# such as the Heat Pump Optimizer rewrites modes and setpoints live, so a day-old value is no longer meant.
RESTORE_MAX_GAP = 24 * 3600  # seconds
# A device reset detected again within this time after a restore is not restored again (no write loops).
RESTORE_COOLDOWN = 900  # seconds
# Deferred writes of the hot water group (docs/firmware-3.92.3-shi-full-analysis.md, 3.2; proven): SHI writes
# to
# exactly 10005-10008 (t2 items 5, 6, 7, 0x27) go into a pending map with a counter of 10 ticks and are
# committed
# by the 1 Hz tick about 10 s later; writing the value currently stored cancels a pending write. No other
# holding
# is deferred. A read-back that differs is checked again after DEFERRED_RECHECK s (one extra read of that
# register), and nothing is written to the register meanwhile.
DEFERRED_KEYS: frozenset[str] = frozenset(
    {"cfg_dhw_mode", "cfg_dhw_setpoint", "cfg_dhw_offset", "cfg_dhw_level"}
)
DEFERRED_RECHECK = 15  # seconds
# Hot water group writes wait while the hot water block reads on (owner measurement on the reference
# installation: the hot water mode can only be set while the block is not active; mechanism unknown).
DHW_BLOCK_KEY = "dhw_block"
# A restore value that did not read back is retried on later polls (once per poll) instead of being forgotten.
RESTORE_RETRY_DEADLINE = 600  # seconds
RESTORE_RETRY_ATTEMPTS = 5

MANUFACTURER = "alpha innotec / Luxtronik"
MODEL = "Smart Home Interface (Modbus/TCP)"
