"""Data update coordinator for the Luxtronik SHI."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, MANUFACTURER, MODEL
from .modbus_client import LuxtronikModbusClient, ModbusCommError, ModbusIllegalAddress
from .registers import ALL_REGISTERS, Register, decode

_LOGGER = logging.getLogger(__name__)

MAX_GAP = 3  # registers that may be skipped inside one block read
MAX_BLOCK = 40  # maximum registers per request


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


class LuxtronikCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls all registers and distributes the values to the entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: LuxtronikModbusClient,
        scan_interval: int,
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
        self._blocks = plan_blocks(ALL_REGISTERS)
        self._missing: set[str] = set()
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
            configuration_url=None,
        )

    # ------------------------------------------------------------------ reading
    async def _async_update_data(self) -> dict[str, Any]:
        try:
            for block in self._blocks:
                if self._tick % block.every == 0:
                    await self._read_block(block)
        except ModbusCommError as err:
            raise UpdateFailed(f"Keine Verbindung zur Wärmepumpe: {err}") from err
        self._tick += 1
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
        self._missing.discard(reg.key)

    def _mark_missing(self, reg: Register) -> None:
        if reg.key not in self._missing:
            _LOGGER.debug("Register %s (%s %s) nicht vorhanden", reg.key, reg.kind, reg.address)
        self._missing.add(reg.key)
        self._values[reg.key] = None

    def _update_firmware(self) -> None:
        platform, major, minor = (self._values.get(k) for k in ("fw_platform", "fw_major", "fw_minor"))
        if None not in (platform, major, minor):
            self.device_info["sw_version"] = f"{major}.{minor} (Plattform {platform})"

    # ------------------------------------------------------------------ writing
    async def async_write(self, reg: Register, raw: int) -> None:
        """Write a holding register and read the value back."""
        if reg.kind != "holding":
            raise HomeAssistantError(f"Register {reg.key} ist nicht beschreibbar")
        try:
            await self.client.write_register(reg.address, raw)
            await self._read_single(reg)
        except (ModbusCommError, ModbusIllegalAddress) as err:
            raise HomeAssistantError(f"Schreiben von {reg.key} fehlgeschlagen: {err}") from err
        self.async_set_updated_data(dict(self._values))
