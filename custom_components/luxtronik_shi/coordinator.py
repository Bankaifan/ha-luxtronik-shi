"""Data update coordinator for the Luxtronik SHI."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from time import monotonic as _monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_RESTORE_AFTER_RESET,
    DEFAULT_RESTORE_AFTER_RESET,
    DOMAIN,
    ISSUE_FIRMWARE_OLD,
    ISSUE_UNREACHABLE,
    ISSUE_VALUES_CHANGED,
    LAST_POLL_SAVE_INTERVAL,
    MANUFACTURER,
    MIN_FIRMWARE,
    MODEL,
    OUTAGE_WATCH_KEYS,
    RECONNECT_GUARD_COUNT,
    RECONNECT_GUARD_POLLS,
    RESET_TO_DEFAULT_SUFFIXES,
    RESTORE_COOLDOWN,
    RESTORE_KEYS,
    RESTORE_MAX_GAP,
    SHI_NOT_AVAILABLE,
    SHI_WATCHDOG_TIMEOUT,
    STORE_VERSION,
    UNREACHABLE_AFTER,
)
from .modbus_client import LuxtronikModbusClient, ModbusCommError, ModbusIllegalAddress
from .registers import ALL_REGISTERS, AREAS, BY_KEY, Register, area_of, decode

_LOGGER = logging.getLogger(__name__)

MAX_GAP = 3  # registers that may be skipped inside one block read
MAX_BLOCK = 40  # maximum registers per request
WRITABLE_PLATFORMS = ("number", "select", "switch")


@dataclass
class Block:
    """A group of registers that is read with a single request."""

    kind: str
    every: int
    start: int
    count: int
    registers: list[Register] = field(default_factory=list)
    split: bool = False  # True once a block read was rejected -> read one by one


def plan_blocks(registers: tuple[Register, ...] | list[Register]) -> list[Block]:
    """Group registers of the same kind and poll rate into compact block reads."""
    groups: dict[tuple[str, int], list[Register]] = {}
    for reg in registers:
        groups.setdefault((reg.kind, reg.every), []).append(reg)

    blocks: list[Block] = []
    for (kind, every), regs in sorted(groups.items()):
        regs = sorted(regs, key=lambda r: r.address)
        current: Block | None = None
        for reg in regs:
            end = reg.address + reg.width
            if (
                current is not None
                and reg.address - (current.start + current.count) <= MAX_GAP
                and end - current.start <= MAX_BLOCK
            ):
                current.count = end - current.start
                current.registers.append(reg)
            else:
                current = Block(kind, every, reg.address, reg.width, [reg])
                blocks.append(current)
    return blocks


def restore_store_key(entry_id: str) -> str:
    """Storage key of the values remembered for a restore after a device reset."""
    return f"{DOMAIN}.restore.{entry_id}"


def restore_group(key: str) -> str:
    """Circuit a restorable key belongs to: ``cfg_mk1_cool_mode`` -> ``cfg_mk1_cool``."""
    for suffix in ("_mode", "_setpoint", "_offset", "_level"):
        if key.endswith(suffix):
            return key.removesuffix(suffix)
    return key


class LuxtronikCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls all registers and distributes the values to the entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: LuxtronikModbusClient,
        scan_interval: int,
        registers: tuple[Register, ...] = ALL_REGISTERS,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self._values: dict[str, Any] = {}
        self._tick = 0
        self.registers = registers
        self._blocks = plan_blocks(registers)
        self._missing: set[str] = set()
        # Entities only link to devices by identifier; the devices themselves are created in
        # async_setup_devices() through the device registry.
        self.device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})
        self._main_device_id: str | None = None
        self._sw_version: str | None = None
        self._first_failure: datetime | None = None  # start of the current run of failed polls
        # Outage notice: watched control values of the last successful poll. Deliberately in memory only, so
        # it is lost on a Home Assistant restart (a change during an outage over a restart is not noticed).
        self._snapshot: dict[str, Any] = {}
        # Pre-outage values while the "values changed" issue is active (the snapshot is frozen meanwhile).
        self._baseline: dict[str, Any] | None = None
        self._reported: dict[str, tuple[Any, Any]] = {}
        # Polls after an outage that still compare against the snapshot: settings are read every few polls
        # (``every``), so the changed value may only arrive with a later poll of the first full cycle.
        self._compare_left = 0
        # Set by async_setup_entry: whether new climate entities are enabled by default.
        self.climate_enabled_default = True
        # Same for the water heater entity.
        self.water_heater_enabled_default = True
        # Restore after a device reset (option): raw values this integration wrote and read back, per key.
        self.restore_enabled = bool(entry.options.get(CONF_RESTORE_AFTER_RESET, DEFAULT_RESTORE_AFTER_RESET))
        self._restore_store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, restore_store_key(entry.entry_id)
        )
        self._remembered: dict[str, int] = {}
        self._raw: dict[str, int] = {}  # last raw word read per holding key
        self._fresh: set[str] = set()  # holding keys read in the current poll
        # Comparison window: polls left until every remembered register was read once after the trigger.
        self._window_left = 0
        self._window_seen: set[str] = set()
        self._learned: dict[str, int] = {}  # setpoint key -> raw value it reverted to in a confirmed reset
        self._reconnects_seen = 0
        self._reconnect_history: deque[bool] = deque(maxlen=RECONNECT_GUARD_POLLS)
        self.reconnect_signal_active = True  # False once reconnects happen on most polls (see const.py)
        self._remembered_dirty = False
        self._adopt_pending = False
        self._last_poll_mono: float | None = None
        self._window_failed = False  # the current window followed failed polls (not only a reconnect or gap)
        self._last_restore: datetime | None = None
        # Last successful poll: in memory, and as persisted (throttled) for the gap check after a restart.
        self._last_poll: datetime | None = None
        self._last_poll_saved: datetime | None = None
        self._gap_checked = False
        self._write_lock = asyncio.Lock()

    # ------------------------------------------------------------------ devices
    def device_info_for(self, key: str) -> DeviceInfo:
        """Device an entity key belongs to (main device or one of the sub-devices)."""
        area = area_of(key)
        if area is None:
            return self.device_info
        return DeviceInfo(identifiers={(DOMAIN, f"{self.config_entry.entry_id}_{area}")})

    def async_setup_devices(self) -> None:
        """Create the main device and the sub-devices that have at least one entity.

        Works with and without the ``via_device_id`` parameter of newer Home Assistant versions.
        """
        entry = self.config_entry
        registry = dr.async_get(self.hass)
        main = registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )
        self._main_device_id = main.id
        via_kwarg = "via_device_id" in inspect.signature(registry.async_get_or_create).parameters
        used = {area_of(reg.key) for reg in self.registers}
        for area in AREAS:
            if area not in used:
                continue
            link = {"via_device_id": main.id} if via_kwarg else {"via_device": (DOMAIN, entry.entry_id)}
            registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"{entry.entry_id}_{area}")},
                manufacturer=MANUFACTURER,
                model=MODEL,
                translation_key=area,
                translation_placeholders={"name": entry.title},
                **link,
            )
        self._update_firmware()

    # ------------------------------------------------------------------ reading
    async def _async_update_data(self) -> dict[str, Any]:
        self._fresh = set()
        try:
            for block in self._blocks:
                if self._tick % block.every == 0:
                    await self._read_block(block)
        except ModbusCommError as err:
            self._update_unreachable_issue(failed=True)
            raise UpdateFailed(f"Keine Verbindung zur Wärmepumpe: {err}") from err
        self._tick += 1
        recovered = self._first_failure is not None
        self._update_unreachable_issue(failed=False)
        reconnected = self._reconnect_signal()
        await self._check_device_reset(
            outage=recovered or reconnected or self._watchdog_gap() or self._session_gap(),
            failed=recovered,
        )
        if self._remembered_dirty:
            self._remembered_dirty = False
            await self._save()
        if self.restore_enabled and self._adopt_pending:
            await self._adopt_device_values()
        await self._save_last_poll()
        self._check_outage_changes(recovered=recovered)
        self._update_firmware()
        return dict(self._values)

    async def _read_block(self, block: Block) -> None:
        if not block.split:
            try:
                words = await self.client.read(block.kind, block.start, block.count)
            except ModbusIllegalAddress:
                if len(block.registers) == 1:
                    self._mark_missing(block.registers[0])
                    return
                _LOGGER.debug(
                    "Blockabfrage %s %s+%s abgelehnt, lese einzeln", block.kind, block.start, block.count
                )
                block.split = True
            else:
                for reg in block.registers:
                    offset = reg.address - block.start
                    self._store(reg, words[offset : offset + reg.width])
                return
        for reg in block.registers:
            await self._read_single(reg)

    async def _read_single(self, reg: Register) -> None:
        try:
            words = await self.client.read(reg.kind, reg.address, reg.width)
        except ModbusIllegalAddress:
            self._mark_missing(reg)
            return
        self._store(reg, words)

    def _store(self, reg: Register, words: list[Any]) -> None:
        if reg.kind == "discrete":
            self._values[reg.key] = bool(words[0])
        else:
            self._values[reg.key] = decode(reg, words)  # type: ignore[arg-type]
            if reg.kind == "holding":
                self._raw[reg.key] = int(words[0])
                self._fresh.add(reg.key)
        self._missing.discard(reg.key)

    def _mark_missing(self, reg: Register) -> None:
        if reg.key not in self._missing:
            _LOGGER.debug("Register %s (%s %s) nicht vorhanden", reg.key, reg.kind, reg.address)
        self._missing.add(reg.key)
        self._values[reg.key] = None
        self._raw.pop(reg.key, None)
        if self._remembered.pop(reg.key, None) is not None:
            # A remembered register that is not available can never be compared: it would block every restore.
            _LOGGER.info(
                "%s: %s is not available on the SHI; it is forgotten and will not be restored",
                self.config_entry.title, reg.key,
            )
            self._remembered_dirty = True

    def _update_firmware(self) -> None:
        platform, major, minor = (self._values.get(k) for k in ("fw_platform", "fw_major", "fw_minor"))
        if None in (platform, major, minor) or self._main_device_id is None:
            return
        self._update_firmware_issue(int(major), int(minor))
        version = f"{major}.{minor} (Plattform {platform})"
        if version != self._sw_version:
            self._sw_version = version
            dr.async_get(self.hass).async_update_device(self._main_device_id, sw_version=version)

    # ------------------------------------------------------------------ repair issues
    def _issue_id(self, key: str) -> str:
        return f"{key}_{self.config_entry.entry_id}"

    def _update_firmware_issue(self, major: int, minor: int) -> None:
        """Raise a warning for firmware older than MIN_FIRMWARE, delete it when the condition ends."""
        issue_id = self._issue_id(ISSUE_FIRMWARE_OLD)
        if (major, minor) >= MIN_FIRMWARE:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_FIRMWARE_OLD,
            translation_placeholders={
                "name": self.config_entry.title,
                "version": f"{major}.{minor}",
                "minimum": ".".join(str(part) for part in MIN_FIRMWARE) + ".0",
            },
        )

    def _update_unreachable_issue(self, *, failed: bool) -> None:
        """Raise an error after UNREACHABLE_AFTER seconds of failed polls, delete it on the next success."""
        issue_id = self._issue_id(ISSUE_UNREACHABLE)
        if not failed:
            self._first_failure = None
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            return
        now = dt_util.utcnow()
        if self._first_failure is None:
            self._first_failure = now
        if (now - self._first_failure).total_seconds() < UNREACHABLE_AFTER:
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=ISSUE_UNREACHABLE,
            translation_placeholders={
                "name": self.config_entry.title,
                "host": self.client.host,
                "minutes": str(UNREACHABLE_AFTER // 60),
            },
        )

    def _watched_values(self) -> dict[str, Any]:
        """Current values of the watched keys that exist for the configured equipment."""
        enabled = {reg.key for reg in self.registers}
        return {
            key: self._values[key]
            for key in OUTAGE_WATCH_KEYS
            if key in enabled and self._values.get(key) is not None
        }

    def _format_value(self, key: str, value: Any) -> str:
        if key.endswith("_block"):
            return "blocked" if value == 1 else "released"
        reg = next((r for r in self.registers if r.key == key), None)
        if reg is not None and reg.options and isinstance(value, int) and 0 <= value < len(reg.options):
            return reg.options[value]
        return str(value)

    @staticmethod
    def _diff(before: dict[str, Any], now: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
        return {k: (before[k], now[k]) for k in before if k in now and before[k] != now[k]}

    def _check_outage_changes(self, *, recovered: bool) -> None:
        """Notice only: report control values that changed while the SHI was unreachable.

        Nothing is ever written back. While the issue is active the pre-outage values stay frozen as the
        reference; the issue is removed when the values match them again or when the user dismisses it.
        No extra Modbus reads: the values come from the normal poll.
        """
        issue_id = self._issue_id(ISSUE_VALUES_CHANGED)
        now = self._watched_values()
        if self._baseline is not None:
            issue = ir.async_get(self.hass).async_get_issue(DOMAIN, issue_id)
            diff = self._diff(self._baseline, now)
            if issue is None or issue.dismissed_version is not None:
                self._baseline = None  # dismissed (or removed): resume normal snapshots
            elif not diff:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
                self._baseline = None
            else:
                if diff != self._reported:
                    self._raise_values_changed(diff)
                return
        elif recovered or self._compare_left > 0:
            if recovered:
                watched = [reg.every for reg in self.registers if reg.key in OUTAGE_WATCH_KEYS]
                self._compare_left = max(watched, default=1)
            self._compare_left -= 1
            diff = self._diff(self._snapshot, now)
            if diff:
                self._baseline = dict(self._snapshot)
                self._compare_left = 0
                self._raise_values_changed(diff)
                return
            if self._compare_left > 0:
                return  # keep the snapshot frozen until the first full read cycle is through
        self._snapshot = now

    def _raise_values_changed(self, diff: dict[str, tuple[Any, Any]]) -> None:
        self._reported = diff
        changes = "\n".join(
            f"- {OUTAGE_WATCH_KEYS[key]}: {self._format_value(key, old)} -> {self._format_value(key, new)}"
            for key, (old, new) in diff.items()
        )
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self._issue_id(ISSUE_VALUES_CHANGED),
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_VALUES_CHANGED,
            translation_placeholders={"name": self.config_entry.title, "changes": changes},
        )

    def async_delete_issues(self) -> None:
        """Remove the repair issues of this entry (on unload)."""
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(ISSUE_FIRMWARE_OLD))
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(ISSUE_UNREACHABLE))
        ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(ISSUE_VALUES_CHANGED))

    # ------------------------------------------------------------------ writing
    async def async_write(self, reg: Register, raw: int) -> None:
        """Write a holding register and read the value back.

        With the restore option on, a key of RESTORE_KEYS is remembered once the read-back matches what was
        written (also a neutral value such as mode ``off``, which then leaves nothing to restore). A failed
        write or a different read-back forgets the key: the intended value is unknown, so it is not restored.
        Writes and restores are serialised by one lock, so a restore never interleaves with a user write.
        """
        if reg.kind != "holding":
            raise HomeAssistantError(f"Register {reg.key} ist nicht beschreibbar")
        async with self._write_lock:
            try:
                await self.client.write_register(reg.address, raw)
                await self._read_single(reg)
            except (ModbusCommError, ModbusIllegalAddress) as err:
                await self._remember(reg.key, None)
                raise HomeAssistantError(f"Schreiben von {reg.key} fehlgeschlagen: {err}") from err
            await self._remember(reg.key, raw if self._raw.get(reg.key) == raw else None)
        self.async_set_updated_data(dict(self._values))

    # ------------------------------------------------------------------ restore after a device reset
    def _restorable(self) -> set[str]:
        """RESTORE_KEYS that exist for the configured equipment."""
        return {
            r.key
            for r in self.registers
            if r.kind == "holding" and r.platform in WRITABLE_PLATFORMS and r.key in RESTORE_KEYS
        }

    async def async_load_remembered(self) -> None:
        """Load the remembered values (option on) or delete them (option off), before the first poll."""
        if not self.restore_enabled:
            await self._restore_store.async_remove()
            return
        data = await self._restore_store.async_load() or {}
        # Adopt the device values once when the option is switched on (no store yet, or one from before).
        self._adopt_pending = not data.get("adopted")
        try:
            self._last_poll_saved = datetime.fromisoformat(data["last_poll"])
        except (KeyError, TypeError, ValueError):
            self._last_poll_saved = None
        values = data.get("values") or {}
        # Learned setpoint reset values are facts about this device: kept regardless of age.
        self._learned = {
            k: v
            for k, v in (data.get("learned") or {}).items()
            if k in self._restorable() and isinstance(v, int) and not isinstance(v, bool)
        }
        if self._last_poll_saved is not None and values:
            age = (dt_util.utcnow() - self._last_poll_saved).total_seconds()
            if age > RESTORE_MAX_GAP:
                _LOGGER.info(
                    "%s: remembered values are %d h old (limit %d h); dropped, nothing will be restored",
                    self.config_entry.title, age // 3600, RESTORE_MAX_GAP // 3600,
                )
                self._remembered = {}
                await self._save(self._last_poll_saved)
                return
        restorable = self._restorable()
        # Keys of equipment that was switched off are dropped: their values may be stale when it comes back.
        self._remembered = {
            k: v
            for k, v in values.items()
            if k in restorable and isinstance(v, int) and not isinstance(v, bool)
        }
        if self._remembered != values:
            await self._save(self._last_poll_saved)

    @property
    def learned(self) -> dict[str, int]:
        """Raw values setpoints reverted to in confirmed resets, learned on this device (read only)."""
        return dict(self._learned)

    @property
    def remembered(self) -> dict[str, int]:
        """Raw values that would be restored after a device reset (read only)."""
        return dict(self._remembered)

    async def _save(self, last_poll: datetime | None = None) -> None:
        """Persist the remembered values and the time of the last successful poll."""
        last_poll = last_poll or self._last_poll or self._last_poll_saved
        data: dict[str, Any] = {
            "values": dict(self._remembered),
            "learned": dict(self._learned),
            "adopted": not self._adopt_pending,
        }
        if last_poll is not None:
            data["last_poll"] = last_poll.isoformat()
            self._last_poll_saved = last_poll
        await self._restore_store.async_save(data)

    def _watchdog_gap(self) -> bool:
        """First poll after setup: was the SHI left without any access longer than its watchdog allows?"""
        if self._gap_checked or not self.restore_enabled:
            return False
        self._gap_checked = True
        if self._last_poll_saved is None:
            return False
        gap = (dt_util.utcnow() - self._last_poll_saved).total_seconds()
        if gap <= SHI_WATCHDOG_TIMEOUT + LAST_POLL_SAVE_INTERVAL:
            return False
        if gap > RESTORE_MAX_GAP:
            _LOGGER.info(
                "%s: last successful poll %d s ago, more than %d h; not treated as evidence of a reset",
                self.config_entry.title, gap, RESTORE_MAX_GAP // 3600,
            )
            return False
        _LOGGER.info(
            "%s: no successful poll for %d s (SHI watchdog %d s); treated like a communication outage",
            self.config_entry.title, gap, SHI_WATCHDOG_TIMEOUT,
        )
        return True

    async def _save_last_poll(self) -> None:
        """Remember the time of this successful poll; written at most every LAST_POLL_SAVE_INTERVAL, and only
        while something is remembered (otherwise the gap does not matter)."""
        if not self.restore_enabled:
            return
        self._last_poll = dt_util.utcnow()
        self._last_poll_mono = _monotonic()
        if not self._remembered:
            return
        saved = self._last_poll_saved
        if saved is None or (self._last_poll - saved).total_seconds() >= LAST_POLL_SAVE_INTERVAL:
            await self._save()

    async def async_save_last_poll(self) -> None:
        """Write the exact time of the last successful poll (on unload, so a restart measures the gap)."""
        if self.restore_enabled and self._remembered and self._last_poll is not None:
            await self._save()

    async def _remember(self, key: str, raw: int | None) -> None:
        if not self.restore_enabled or key not in RESTORE_KEYS or self._remembered.get(key) == raw:
            return
        if raw is None:
            self._remembered.pop(key)
        else:
            self._remembered[key] = raw
        await self._save()

    def _reg(self, key: str) -> Register:
        return next(r for r in self.registers if r.key == key)

    def _forget_external(self, key: str, remembered: int, current: int | None) -> None:
        self._remembered.pop(key, None)
        _LOGGER.info(
            "%s: %s was changed outside this integration (%s -> %s) and will not be restored",
            self.config_entry.title, key, remembered, current,
        )
        self._forget_group_mode(key)

    def _forget_group_mode(self, key: str) -> None:
        """Group rule: once a member of a circuit changed outside this integration, its mode is not restored
        until it is written through Home Assistant again (otherwise a combination nobody set could result)."""
        mode = f"{restore_group(key)}_mode"
        if mode != key and self._remembered.pop(mode, None) is not None:
            _LOGGER.info(
                "%s: %s will not be restored, %s of the same circuit was changed outside this integration",
                self.config_entry.title, mode, key,
            )

    def _reads_reset_value(self, key: str, current: int | None) -> bool:
        """Whether ``current`` is what this key reads after a revert of the SHI values.

        Modes and levels read 0, offsets are assumed to (not proven). Setpoints read their persisted or
        default value, never 0: before one was observed any non-zero value counts, afterwards only the
        learned one (learned on this device).
        """
        if current is None or current == SHI_NOT_AVAILABLE:
            return False  # 0x7FFF means "not available", never a reset value
        if key.endswith(RESET_TO_DEFAULT_SUFFIXES):
            learned = self._learned.get(key)
            return current != 0 if learned is None else current == learned
        return current == 0

    def _reconnect_signal(self) -> bool:
        """Whether the Modbus connection was re-established since the last poll, as an outage signal.

        Assumption (not measured yet): the SHI keeps the TCP connection open between polls, so a reconnect
        means the controller dropped it. If reconnects happen on most polls, that does not hold for this
        setup: the signal is switched off for the session and only failed polls and gaps count.
        """
        reconnected = self.client.reconnects != self._reconnects_seen
        self._reconnects_seen = self.client.reconnects
        self._reconnect_history.append(reconnected)
        if self.reconnect_signal_active and sum(self._reconnect_history) >= RECONNECT_GUARD_COUNT:
            self.reconnect_signal_active = False
            _LOGGER.warning(
                "%s: the Modbus connection was re-established on %d of the last %d polls; reconnects are no "
                "longer treated as a device reset signal in this session (only failed polls and gaps)",
                self.config_entry.title, sum(self._reconnect_history), len(self._reconnect_history),
            )
        if not reconnected or not self.reconnect_signal_active:
            return False
        _LOGGER.info(
            "%s: connection to the SHI was re-established; treated as an outage", self.config_entry.title
        )
        return True

    async def _adopt_device_values(self) -> None:
        """Option switched on: remember what the device holds now, once, as if written by this integration.

        Runs on the first successful poll after setup, which reads every block. Modes, levels and offsets are
        adopted when they read non-zero (never 0x7FFF). A setpoint is adopted only if its circuit's mode is
        `setpoint`. That only makes it likely that the setpoint was meant: who set a value cannot be read over
        Modbus, so an adopted setpoint can also be a boot default or a controller parameter. After a reset in
        which that parameter changed, the adopted value is written back over the change, and the SHI then
        owns it.
        Adopted values may have been set by another client; they are restored like this integration's own.
        """
        adopted: dict[str, int] = {}
        for key in sorted(self._restorable()):
            raw = self._raw.get(key)
            if key in self._remembered or key not in self._fresh or raw in (None, 0, SHI_NOT_AVAILABLE):
                continue
            if key.endswith(RESET_TO_DEFAULT_SUFFIXES):
                mode = f"{restore_group(key)}_mode"
                mode_reg = BY_KEY.get(mode)
                if mode_reg is None or mode_reg.options is None:
                    continue
                if self._raw.get(mode) != mode_reg.options.index("setpoint"):
                    continue
            adopted[key] = raw
        self._remembered.update(adopted)
        self._adopt_pending = False
        await self._save()
        _LOGGER.info(
            "%s: restore option switched on; adopted the current device values: %s",
            self.config_entry.title, ", ".join(f"{k}={v}" for k, v in adopted.items()) or "none",
        )

    def _session_gap(self) -> bool:
        """Within a session: more than the watchdog time since the previous successful poll."""
        if not self.restore_enabled or self._last_poll_mono is None:
            return False
        # Monotonic: a wall-clock step (NTP) must not look like a gap. Wall-clock time is only used across a
        # restart (_watchdog_gap), where no monotonic reference survives.
        gap = _monotonic() - self._last_poll_mono
        if gap <= SHI_WATCHDOG_TIMEOUT:
            return False
        _LOGGER.info(
            "%s: %d s since the previous successful poll (SHI watchdog %d s); treated like an outage",
            self.config_entry.title, gap, SHI_WATCHDOG_TIMEOUT,
        )
        return True

    async def _check_device_reset(self, *, outage: bool, failed: bool = False) -> None:
        """Re-apply remembered values when the evidence shows that the device reverted them (option on).

        * Without an observed outage (failed polls, a reconnect, or a gap beyond the SHI watchdog) the values
          cannot have been reverted: any difference is an external change and is forgotten.
        * After an outage, the remembered registers are collected until each was read once (settings are only
          read every few polls). It is a reset only if every remembered register reads its reset value
          (all or nothing, because the controller reverts all SHI values at once); otherwise the registers
          that changed are external changes and nothing is restored.
        No extra Modbus reads: the values come from the normal poll.
        """
        if not self.restore_enabled or not self._remembered:
            self._window_left = 0
            return
        changed = False
        if outage:
            if self._window_left == 0:
                self._window_seen = set()
                self._window_failed = False
            self._window_failed |= failed
            self._window_left = max((self._reg(k).every for k in self._remembered), default=1)
        if self._window_left == 0:
            for key, remembered in list(self._remembered.items()):
                current = self._raw.get(key)
                if key in self._fresh and current not in (None, remembered) and key in self._remembered:
                    self._forget_external(key, remembered, current)
                    changed = True
        else:
            self._window_seen |= self._fresh & self._remembered.keys()
            self._window_left -= 1
            if self._window_left == 0 or self._remembered.keys() <= self._window_seen:
                self._window_left = 0
                changed |= await self._decide_reset()
        if changed:
            await self._save()

    async def _decide_reset(self) -> bool:
        """End of the window after an outage: restore all or nothing. Returns whether the store changed."""
        title = self.config_entry.title
        seen = {k: v for k, v in self._remembered.items() if k in self._window_seen}
        differ = {k: v for k, v in seen.items() if self._raw.get(k) != v}
        if not differ:
            return False  # nothing was reverted (e.g. a network blip): nothing to do
        unseen = self._remembered.keys() - seen.keys()
        # All or nothing: the controller reverts every SHI value at once, so each remembered register must
        # read its reset value (a remembered mode `off` or offset 0 trivially does).
        blockers = [k for k in seen if not self._reads_reset_value(k, self._raw.get(k))]
        reset = not unseen and not blockers
        relearn = False
        # Setpoints that only differ from their learned value (a wrong or stale learned value, or another
        # value after a firmware change). Relearned only under stricter evidence: failed polls and every
        # remembered mode and level at 0.
        stale = [
            k for k in blockers
            if k.endswith(RESET_TO_DEFAULT_SUFFIXES) and k in self._learned
            and self._raw.get(k) not in (None, 0, SHI_NOT_AVAILABLE)
        ]
        if not unseen and blockers and stale == blockers:
            modes = [k for k in seen if k.endswith(("_mode", "_level")) and self._remembered[k] != 0]
            if self._window_failed and modes and all(self._raw.get(k) == 0 for k in modes):
                reset = relearn = True
            else:
                _LOGGER.warning(
                    "%s: after the outage %s read a value other than the learned reset value; not treated "
                    "as a device reset",
                    title,
                    ", ".join(f"{k}={self._raw.get(k)} (learned {self._learned[k]})" for k in sorted(stale)),
                )
        now = dt_util.utcnow()
        if reset and self._last_restore is not None:
            if (now - self._last_restore).total_seconds() < RESTORE_COOLDOWN:
                _LOGGER.warning(
                    "%s: device reset again within %s minutes of the last restore; not restoring %s again, "
                    "these values are forgotten",
                    title, RESTORE_COOLDOWN // 60, ", ".join(sorted(differ)),
                )
                for key in differ:
                    self._remembered.pop(key, None)
                return True
        if not reset:
            _LOGGER.info(
                "%s: after the outage not every remembered value reads its reset value; no device reset, "
                "nothing is restored",
                title,
            )
            for key, remembered in differ.items():
                if key in self._remembered:
                    self._forget_external(key, remembered, self._raw.get(key))
            return True
        self._last_restore = now
        learned_changed = False
        for key in differ:
            if key.endswith(RESET_TO_DEFAULT_SUFFIXES) and self._learned.get(key) != self._raw[key]:
                old = self._learned.get(key)
                self._learned[key] = self._raw[key]
                learned_changed = True
                if relearn and old is not None:
                    _LOGGER.info(
                        "%s: relearned reset value of %s: %s (was %s; failed polls, all modes at 0)",
                        title, key, self._raw[key], old,
                    )
                else:
                    _LOGGER.info("%s: learned reset value of %s: %s", title, key, self._raw[key])
        restored: list[str] = []
        failed: list[str] = []
        lost = False  # connection lost: the remaining keys are not tried either
        # Modes last: a mode is only re-applied if every other restored value of its circuit came back.
        order = sorted(differ, key=lambda k: k.endswith("_mode"))
        async with self._write_lock:
            for key in order:
                raw = differ[key]
                if self._remembered.get(key) != raw:
                    continue  # written (or forgotten) through Home Assistant since the snapshot
                if lost or (
                    key.endswith("_mode") and any(restore_group(f) == restore_group(key) for f in failed)
                ):
                    failed.append(key)
                    continue
                reg = self._reg(key)
                try:
                    await self.client.write_register(reg.address, raw)
                    await self._read_single(reg)
                except ModbusCommError:
                    lost = True
                    failed.append(key)
                    continue
                except ModbusIllegalAddress:
                    failed.append(key)
                    continue
                (restored if self._raw.get(key) == raw else failed).append(key)
            for key in failed:
                self._remembered.pop(key, None)
        if restored:
            _LOGGER.warning(
                "%s: device reset detected, restored %s", title,
                ", ".join(f"{k}={differ[k]}" for k in sorted(restored)),
            )
        if failed:
            _LOGGER.warning(
                "%s: device reset detected, could not restore %s (write failed or read back a different "
                "value); they are forgotten and not retried",
                title, ", ".join(sorted(failed)),
            )
        return bool(failed) or learned_changed
