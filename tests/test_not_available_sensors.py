"""The plain sensors show the SHI "not available" word 0x7FFF as unavailable, never as 3276.7 K or 32767."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant

from custom_components.luxtronik_shi.registers import ALL_REGISTERS, BY_KEY, reports_not_available

from .fake_shi import FakeSHI
from .test_integration import _entity_id, _setup

# Enabled by default on the reference installation and read from an input register of 16 bit.
_PLAIN = [
    reg
    for reg in ALL_REGISTERS
    if reports_not_available(reg) and reg.enabled_default and reg.kind == "input"
]
_NORMAL = {"flow": "35.1", "return": "28.5", "outside": "-2.0", "dhw": "48.2", "error_number": "0"}


def test_the_affected_registers_are_input_temperatures_and_the_error_number() -> None:
    affected = {reg.key for reg in ALL_REGISTERS if reports_not_available(reg)}
    assert {"flow", "return", "outside", "dhw", "error_number"} <= affected
    for key in affected:
        reg = BY_KEY[key]
        assert reg.kind == "input" and reg.platform == "sensor" and reg.dtype != "uint32"
        assert reg.device_class == "temperature" or key == "error_number"
    # counters, enumerations and everything that is not a temperature keep their number
    assert not {"energy_th_heating", "operating_mode", "heating_status", "compressor_thermal_power"} & affected


@pytest.mark.parametrize("key", sorted(_NORMAL))
async def test_not_available_word_is_unavailable_and_a_normal_value_is_unchanged(
    hass: HomeAssistant, shi: FakeSHI, key: str
) -> None:
    entry = await _setup(hass, shi)
    entity_id = _entity_id(hass, entry, "sensor", key)
    assert hass.states.get(entity_id).state == _NORMAL[key]

    shi.input[BY_KEY[key].address] = 0x7FFF
    entry.runtime_data._tick = 0
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unavailable"

    shi.input[BY_KEY[key].address] = {"flow": 351, "return": 285, "outside": 0xFFEC, "dhw": 482, "error_number": 0}[key]
    entry.runtime_data._tick = 0
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == _NORMAL[key]


async def test_every_default_plain_sensor_goes_unavailable_on_the_marker(hass: HomeAssistant, shi: FakeSHI) -> None:
    entry = await _setup(hass, shi)
    present = {reg.key for reg in entry.runtime_data.registers}  # equipment decides which entities exist
    keys = [reg.key for reg in _PLAIN if reg.key in present]
    assert len(keys) > 5
    for key in keys:
        shi.input[BY_KEY[key].address] = 0x7FFF
    for _ in range(max(reg.every for reg in ALL_REGISTERS)):  # slow registers need their cycle
        await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    for key in keys:
        assert hass.states.get(_entity_id(hass, entry, "sensor", key)).state == "unavailable", key
