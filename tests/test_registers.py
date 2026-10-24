"""Tests for the register map and the block planning (no Home Assistant needed)."""

from custom_components.luxtronik_shi.coordinator import MAX_BLOCK, plan_blocks
from custom_components.luxtronik_shi.registers import (
    ALL_REGISTERS,
    BY_KEY,
    decode,
    encode_int16,
)


def test_keys_and_addresses_are_unique():
    assert len(BY_KEY) == len(ALL_REGISTERS)
    seen = set()
    for reg in ALL_REGISTERS:
        ident = (reg.kind, reg.address)
        assert ident not in seen, ident
        seen.add(ident)


def test_decode():
    assert decode(BY_KEY["return"], [285]) == 28.5
    assert decode(BY_KEY["outside"], [0xFFEC]) == -2.0
    assert decode(BY_KEY["dhw_min"], [0xFFFF]) == -0.1
    assert decode(BY_KEY["energy_el_total"], [0x0001, 0x0002]) == 6553.8
    assert decode(BY_KEY["hours_hp"], [0, 1234]) == 1234
    assert decode(BY_KEY["electric_power"], [5]) == 500
    assert decode(BY_KEY["error_number"], [816]) == 816


def test_encode_negative_offset():
    assert encode_int16(0.0, 0.1) == 0
    assert encode_int16(1.5, 0.1) == 15
    assert encode_int16(-0.5, 0.1) == 65531
    assert encode_int16(-5.0, 0.1) == 65486
    assert decode(BY_KEY["cfg_heating_offset"], [65531]) == -0.5


def test_blocks_cover_every_register_exactly_once():
    blocks = plan_blocks(ALL_REGISTERS)
    covered = [reg.key for block in blocks for reg in block.registers]
    assert sorted(covered) == sorted(reg.key for reg in ALL_REGISTERS)
    for block in blocks:
        assert block.count <= MAX_BLOCK
        for reg in block.registers:
            assert block.start <= reg.address
            assert reg.address + reg.width <= block.start + block.count
            assert reg.kind == block.kind
            assert reg.every == block.every
