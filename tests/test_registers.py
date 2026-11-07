"""Tests for the register map and the block planning (no Home Assistant needed)."""

from custom_components.luxtronik_shi.coordinator import MAX_BLOCK, plan_blocks
from custom_components.luxtronik_shi.registers import (
    ALIAS_OF,
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
        if reg.key in ALIAS_OF:
            continue  # shares the register of a raw value, checked in test_aliases_share_their_register
        assert ident not in seen, ident
        seen.add(ident)


def test_aliases_share_their_register():
    """A binary sensor for a proven output or input reads the register of its raw twin, nothing else."""
    assert ALIAS_OF
    for key, raw_key in ALIAS_OF.items():
        alias, raw = BY_KEY[key], BY_KEY[raw_key]
        assert alias.platform == "binary_sensor" and raw.platform == "sensor"
        assert (alias.kind, alias.address, alias.dtype, alias.scale, alias.every) == (
            raw.kind, raw.address, raw.dtype, raw.scale, raw.every
        )
        assert alias.source and alias.source == raw.source  # same proof as the raw value
        assert not raw.enabled_default  # the raw twin stays as it was (disabled diagnostics)


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


def test_level_options_follow_python_luxtronik():
    # python-luxtronik LevelMode: 0 Normal, 1 Increased, 2 Increased2, 3 Decreased.
    expected = ("normal", "increased", "increased2", "decreased")
    for key in ("cfg_heating_level", "cfg_dhw_level", "cfg_mk1_level", "cfg_overall_level"):
        assert BY_KEY[key].options == expected


def test_room_setpoint_is_writable_number():
    reg = BY_KEY["cfg_room_setpoint"]
    assert reg.kind == "holding" and reg.platform == "number"
    assert reg.address == 10060
    assert (reg.min_value, reg.max_value) == (20, 40)


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


def test_buffer_type_options_follow_python_luxtronik():
    # python-luxtronik BufferType: 0 series, 1 separation, 2 multifunction. The raw value is the index; an extra
    # leading option shifted every value by one (a separation buffer showed as "series").
    assert BY_KEY["buffer_type"].options == ("series", "separation", "multi")


def test_raw_meanings_keep_key_and_stay_disabled():
    # Rule 3: a meaning needs a source; the key stays raw_<address> and the entity stays disabled diagnostics.
    from custom_components.luxtronik_shi.registers import RAW_KEYS, RAW_MEANINGS

    for address, meaning in RAW_MEANINGS.items():
        reg = BY_KEY[f"raw_{address}"]
        assert reg.source and reg.source.startswith("proven:")
        assert reg.name_de == meaning["name_de"] and reg.name_en == meaning["name_en"]
        assert not reg.enabled_default and reg.diagnostic
        assert reg.key not in RAW_KEYS
    assert BY_KEY["raw_10113"].scale == 0.1 and BY_KEY["raw_10113"].dtype == "int16"
    assert decode(BY_KEY["raw_10113"], [253]) == 25.3
    assert BY_KEY["raw_10500"].source is None and BY_KEY["raw_10500"].key in RAW_KEYS  # still open
