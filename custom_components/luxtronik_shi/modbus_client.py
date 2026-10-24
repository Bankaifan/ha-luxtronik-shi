"""Thin asynchronous Modbus/TCP wrapper around pymodbus for the Luxtronik SHI."""

from __future__ import annotations

import asyncio
import inspect
import logging

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException
from pymodbus.pdu import ExceptionResponse

from .registers import RegKind

_LOGGER = logging.getLogger(__name__)


class ModbusCommError(Exception):
    """The heat pump could not be reached or did not answer."""


class ModbusIllegalAddress(Exception):
    """The heat pump answered with a Modbus exception (e.g. address not available)."""


class LuxtronikModbusClient:
    """Serialised access to one Luxtronik SHI."""

    def __init__(self, host: str, port: int, slave: int, timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.slave = slave
        self._client = AsyncModbusTcpClient(host, port=port, timeout=timeout, retries=2)
        self._lock = asyncio.Lock()
        # pymodbus >= 3.10 calls the unit parameter ``device_id``, older ones ``slave``.
        params = inspect.signature(self._client.read_holding_registers).parameters
        self._unit_kw = "device_id" if "device_id" in params else "slave"

    async def _call(self, method: str, *args: int, **kwargs: int):
        async with self._lock:
            try:
                if not self._client.connected:
                    await self._client.connect()
                if not self._client.connected:
                    raise ModbusCommError(f"Verbindung zu {self.host}:{self.port} fehlgeschlagen")
                response = await getattr(self._client, method)(*args, **kwargs, **{self._unit_kw: self.slave})
            except (ModbusException, OSError, TimeoutError) as err:
                raise ModbusCommError(str(err) or type(err).__name__) from err

        if response.isError():
            if isinstance(response, ExceptionResponse):
                raise ModbusIllegalAddress(f"Modbus-Ausnahme {response}")
            raise ModbusCommError(f"Fehlerhafte Antwort: {response}")
        return response

    async def read(self, kind: RegKind, address: int, count: int) -> list[int] | list[bool]:
        """Read ``count`` registers (or discrete inputs) starting at ``address``."""
        if kind == "input":
            resp = await self._call("read_input_registers", address, count=count)
            return list(resp.registers)
        if kind == "holding":
            resp = await self._call("read_holding_registers", address, count=count)
            return list(resp.registers)
        resp = await self._call("read_discrete_inputs", address, count=count)
        return [bool(bit) for bit in resp.bits[:count]]

    async def write_register(self, address: int, value: int) -> None:
        """Write one holding register (function code 6)."""
        await self._call("write_register", address, value)

    async def close(self) -> None:
        """Close the connection."""
        async with self._lock:
            result = self._client.close()
            if inspect.isawaitable(result):
                await result
