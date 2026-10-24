"""A tiny simulated Luxtronik SHI (Modbus/TCP server) for the tests."""

from __future__ import annotations

import asyncio
import socket
import struct

# address -> raw value, as seen on the real installation
INPUT = {
    10000: 4,
    10002: 1,
    10003: 2,
    10004: 0,
    10100: 285,
    10101: 300,
    10102: 1,
    10103: 2,
    10104: 3,
    10105: 351,
    10108: 0xFFEC,  # -2.0 °C (int16)
    10109: 5,
    10110: 6,
    10112: 7,
    10113: 8,
    10120: 482,
    10121: 550,
    10122: 0xFFFF,
    10123: 600,
    10124: 9,
    10201: 0,
    10300: 12,
    10301: 5,
    10310: 0x0001,
    10311: 0x0002,  # uint32 -> 65538 * 0.1 = 6553.8 kWh
    10312: 0,
    10313: 100,
    10314: 0,
    10315: 50,
    10320: 0,
    10321: 200,
    10322: 0,
    10323: 150,
    10324: 0,
    10325: 70,
    10400: 3,
    10401: 3,
    10402: 1,
    10404: 0,
    10405: 1234,
    10406: 0,
    10407: 1000,
    10408: 0,
    10409: 234,
}
HOLDING = {
    10000: 0,
    10001: 220,
    10002: 0,
    10003: 0,
    10005: 0,
    10006: 400,
    10007: 0,
    10008: 0,
    10010: 0,
    10011: 0,
    10012: 0,
    10013: 0,
    10040: 0,
    10041: 0,
    10065: 0,
    10066: 0,
    10067: 0,
    10070: 0,
    10050: 0,
    10051: 0,
    10052: 0,
    10053: 0,
    10071: 0,
}
DISCRETE = {
    10000: True,
    10001: True,
    10002: False,
    10003: False,
    10005: False,
    10006: True,
    10007: False,
    10008: False,
    10009: False,
    10010: False,
    10011: False,
}


def free_port() -> int:
    """Find a free TCP port."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FakeSHI:
    """Minimal Modbus/TCP server (function codes 2, 3, 4, 6).

    Like the real SHI it only knows the registers that exist and answers all other
    addresses with exception code 2 (illegal data address).
    """

    def __init__(self, slave: int = 1) -> None:
        self.slave = slave
        self.port = free_port()
        self.input = dict(INPUT)
        self.holding = dict(HOLDING)
        self.discrete = dict(DISCRETE)
        self.requests: list[tuple[int, int, int]] = []  # (function, address, count/value)
        self._server: asyncio.Server | None = None
        self._writers: set[asyncio.StreamWriter] = set()

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", self.port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            for writer in list(self._writers):
                writer.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), 2)
            except TimeoutError:
                pass

    def holding_value(self, address: int) -> int:
        """Current raw value of a holding register in the simulator."""
        return self.holding[address]

    def _respond(self, unit: int, pdu: bytes) -> bytes:
        func = pdu[0]
        if func in (2, 3, 4):
            address, count = struct.unpack(">HH", pdu[1:5])
            self.requests.append((func, address, count))
            table = {2: self.discrete, 3: self.holding, 4: self.input}[func]
            if not all(address + i in table for i in range(count)):
                return bytes([func | 0x80, 2])
            values = [table[address + i] for i in range(count)]
            if func == 2:
                bits = bytearray((count + 7) // 8)
                for i, value in enumerate(values):
                    if value:
                        bits[i // 8] |= 1 << (i % 8)
                return bytes([func, len(bits)]) + bytes(bits)
            return bytes([func, 2 * count]) + b"".join(struct.pack(">H", v) for v in values)
        if func == 6:
            address, value = struct.unpack(">HH", pdu[1:5])
            self.requests.append((func, address, value))
            if address not in self.holding:
                return bytes([func | 0x80, 2])
            self.holding[address] = value
            return pdu[:5]
        return bytes([func | 0x80, 1])

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.add(writer)
        try:
            while True:
                header = await reader.readexactly(7)
                tid, _proto, length, unit = struct.unpack(">HHHB", header)
                pdu = await reader.readexactly(length - 1)
                if unit != self.slave:
                    continue  # no answer for a wrong unit id -> client timeout
                body = self._respond(unit, pdu)
                writer.write(struct.pack(">HHHB", tid, 0, len(body) + 1, unit) + body)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self._writers.discard(writer)
            writer.close()
