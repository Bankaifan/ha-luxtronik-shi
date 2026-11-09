"""Tests for the Modbus wrapper against the simulated heat pump."""

import pytest

from custom_components.luxtronik_shi.modbus_client import (
    LuxtronikModbusClient,
    ModbusCommError,
    ModbusIllegalAddress,
)

from .fake_shi import free_port


async def test_read_write(shi):
    client = LuxtronikModbusClient("127.0.0.1", shi.port, 1, timeout=2)
    try:
        assert await client.read("input", 10100, 1) == [285]
        assert await client.read("input", 10100, 6) == [285, 300, 50, 380, 150, 351]
        assert await client.read("discrete", 10000, 2) == [True, True]
        await client.write_register(10002, 65531)
        assert shi.holding_value(10002) == 65531
        assert await client.read("holding", 10002, 1) == [65531]
    finally:
        await client.close()


async def test_illegal_address(shi):
    client = LuxtronikModbusClient("127.0.0.1", shi.port, 1, timeout=2)
    try:
        with pytest.raises(ModbusIllegalAddress):
            await client.read("input", 10600, 1)
        # the connection stays usable
        assert await client.read("input", 10100, 1) == [285]
    finally:
        await client.close()


async def test_connection_refused(socket_enabled):
    client = LuxtronikModbusClient("127.0.0.1", free_port(), 1, timeout=1)
    try:
        with pytest.raises(ModbusCommError):
            await client.read("input", 10100, 1)
    finally:
        await client.close()


class _Response:
    """Minimal successful pymodbus response."""

    registers = [285]
    bits = [True]

    def isError(self) -> bool:  # noqa: N802 - pymodbus API name
        return False


class _Pymodbus39:
    """pymodbus 3.9 API as Home Assistant 2025.8 ships it: the unit keyword is ``slave``, no ``trace_connect``."""

    instances: list = []

    def __init__(self, host, port=502, timeout=3, retries=3):
        self.connected = False
        self.unit_kwargs: list[dict] = []
        _Pymodbus39.instances.append(self)

    async def connect(self):
        self.connected = True
        return True

    def close(self):
        self.connected = False

    async def read_holding_registers(self, address, *, count=1, slave=1):
        self.unit_kwargs.append({"slave": slave})
        return _Response()


class _Pymodbus3Latest:
    """Newer pymodbus API: the unit keyword is ``device_id`` and connects are reported through ``trace_connect``."""

    instances: list = []

    def __init__(self, host, port=502, timeout=3, retries=3, trace_connect=None):
        self.connected = False
        self.trace_connect = trace_connect
        self.unit_kwargs: list[dict] = []
        _Pymodbus3Latest.instances.append(self)

    async def connect(self):
        self.connected = True
        if self.trace_connect:
            self.trace_connect(True)
        return True

    def close(self):
        self.connected = False

    async def read_holding_registers(self, address, *, count=1, device_id=1):
        self.unit_kwargs.append({"device_id": device_id})
        return _Response()


async def test_pymodbus39_api_uses_slave_keyword_and_counts_reconnects(monkeypatch):
    from custom_components.luxtronik_shi import modbus_client

    _Pymodbus39.instances.clear()
    monkeypatch.setattr(modbus_client, "AsyncModbusTcpClient", _Pymodbus39)
    client = LuxtronikModbusClient("192.0.2.1", 502, 7)
    try:
        assert client._unit_kw == "slave"
        assert await client.read("holding", 1, 1) == [285]
        assert _Pymodbus39.instances[0].unit_kwargs == [{"slave": 7}]
        assert client.reconnects == 0

        # Connection lost: without a connect trace the client must count the reconnect itself.
        _Pymodbus39.instances[0].connected = False
        assert await client.read("holding", 1, 1) == [285]
        assert client.reconnects == 1
        assert client.last_reconnect is not None
    finally:
        await client.close()


async def test_latest_api_uses_device_id_and_connect_trace(monkeypatch):
    from custom_components.luxtronik_shi import modbus_client

    _Pymodbus3Latest.instances.clear()
    monkeypatch.setattr(modbus_client, "AsyncModbusTcpClient", _Pymodbus3Latest)
    client = LuxtronikModbusClient("192.0.2.1", 502, 7)
    try:
        assert client._unit_kw == "device_id"
        assert client._traced
        assert await client.read("holding", 1, 1) == [285]
        assert _Pymodbus3Latest.instances[0].unit_kwargs == [{"device_id": 7}]
        assert client.reconnects == 0

        # The connect trace reports the reconnect; it must be counted exactly once.
        _Pymodbus3Latest.instances[0].connected = False
        assert await client.read("holding", 1, 1) == [285]
        assert client.reconnects == 1
    finally:
        await client.close()
