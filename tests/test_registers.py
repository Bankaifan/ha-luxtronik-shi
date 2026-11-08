"""Tests for the register map and the block planning (no Home Assistant needed)."""

from custom_components.luxtronik_shi.coordinator import MAX_BLOCK, plan_blocks
from custom_components.luxtronik_shi.registers import (
    ALL_REGISTERS,
    BY_KEY,
    LEVEL_OPTIONS,
    decode,
    encode_int16,
)


def test_keys_and_addresses_are_unique():
    assert len(BY_KEY) == len(ALL_REGISTERS)
    seen = set()
    for reg in ALL_REGISTERS:
        ident = (reg.kind, reg.address)
        assert ident not in seen, ident  # a register has one entity (0.18.0: no raw twin of an output flag)
        seen.add(ident)


def test_no_word_of_a_32_bit_register_has_a_second_entity():
    """A proven value has one entity: no raw word sensor next to a counter or an extra hot water value."""
    wide = {reg.address + i for reg in ALL_REGISTERS if reg.width == 2 for i in range(2)}
    for reg in ALL_REGISTERS:
        if reg.width == 1 and reg.kind == "input":
            assert reg.address not in wide, reg.key


def test_output_flags_are_standalone_registers():
    """The proven outputs and inputs are binary sensors of their own (0.18.0): same address and poll interval as
    the removed raw twins, the firmware proof as source, and the raw keys are deleted from the registry."""
    from custom_components.luxtronik_shi.registers import REMOVED_KEYS

    expected = {
        "output_vbo": (10350, 4), "output_fp1": (10351, 4), "output_fp2": (10352, 30), "output_fp3": (10353, 30),
        "pump_heating": (10354, 4), "pump_hot_water": (10355, 4), "pump_circulation": (10356, 4),
        "input_evu": (10360, 4), "input_evu2": (10361, 4),
    }
    for key, (address, every) in expected.items():
        reg = BY_KEY[key]
        assert (reg.platform, reg.kind, reg.address, reg.every) == ("binary_sensor", "input", address, every), key
        assert reg.source and reg.source.startswith("proven: firmware"), key
        assert f"raw_{address}" not in BY_KEY and f"raw_{address}" in REMOVED_KEYS


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


def test_level_options_follow_the_firmware():
    # Firmware V3.92.3 (full analysis, 3.1): raw 1 and 2 both use the parameter "Erhöhung", so they are one option;
    # python-luxtronik's "Increased2" is not a separate value. Raw value = position, "increased" is written as 1.
    expected = ("normal", "increased", "increased", "decreased")
    for key in ("cfg_heating_level", "cfg_dhw_level", "cfg_mk1_level", "cfg_overall_level"):
        assert BY_KEY[key].options == expected
        assert BY_KEY[key].options.index("increased") == 1
    assert LEVEL_OPTIONS == ("normal", "increased", "decreased")


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
    # 10113 is the proper sensor flow_calc_max since 0.18.0 (was raw_10113)
    assert "raw_10113" not in BY_KEY
    assert BY_KEY["flow_calc_max"].scale == 0.1 and BY_KEY["flow_calc_max"].dtype == "int16"
    assert decode(BY_KEY["flow_calc_max"], [253]) == 25.3
    # the pool counter stays a raw value because its divisor 7200 is only likely; the other resolved addresses
    # have proper sensors and no raw twin
    assert BY_KEY["raw_10412"].source.startswith("proven:") and "likely" in BY_KEY["raw_10412"].source
    assert not {"raw_10410", "raw_10416", "raw_10500", "raw_10501", "raw_10502"} & set(BY_KEY)
    # no raw value without a meaning is left (the outputs/inputs are binary sensors only since 0.18.0)
    assert RAW_KEYS == set()
