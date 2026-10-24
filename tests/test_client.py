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
        assert await client.read("input", 10100, 6) == [285, 300, 1, 2, 3, 351]
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
            await client.read("input", 10500, 1)
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
