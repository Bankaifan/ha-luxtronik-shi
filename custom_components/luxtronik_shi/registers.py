"""Register map of the Luxtronik Smart Home Interface (SHI) via Modbus/TCP.

The map was taken over from a running installation (alpha innotec LWDV 91-1/3
with Luxtronik SHI) and covers every register that was in productive use.

Naming scheme of the keys: they are identical to the suffix of the entity IDs
that the former YAML ``modbus:`` configuration produced (``lwdv_shi_<key>``),
which makes a migration of existing automations and dashboards easy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RegKind = Literal["input", "holding", "discrete"]
DType = Literal["uint16", "int16", "uint32"]
Platform = Literal["sensor", "binary_sensor", "switch", "number"]


@dataclass(frozen=True, kw_only=True)
class Register:
    """Description of one value that is read from (and maybe written to) the heat pump."""

    key: str
    address: int
    kind: RegKind
    name_de: str
    name_en: str
    dtype: DType = "uint16"
    scale: float = 1.0
    precision: int | None = None
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    # Poll this register every N-th update cycle (base cycle = scan interval).
    every: int = 1
    diagnostic: bool = False
    enabled_default: bool = True
    platform: Platform = "sensor"

    @property
    def width(self) -> int:
        """Number of 16 bit registers occupied."""
        return 2 if self.dtype == "uint32" else 1

    @property
    def unique_key(self) -> str:
        """Key used for unique IDs (raw values need the address)."""
        return self.key


def decode(reg: Register, words: list[int]) -> float | int:
    """Convert raw register words into the physical value."""
    if reg.dtype == "uint32":
        raw = (words[0] << 16) | words[1]
    elif reg.dtype == "int16":
        raw = words[0] - 0x10000 if words[0] >= 0x8000 else words[0]
    else:
        raw = words[0]
    if reg.scale == 1.0:
        return raw
    return round(raw * reg.scale, 3)


def encode_int16(value: float, scale: float) -> int:
    """Convert a physical value into a raw 16 bit word (two's complement)."""
    return int(round(value / scale)) % 0x10000


def _s(key, address, de, en, **kw) -> Register:
    return Register(key=key, address=address, kind="input", name_de=de, name_en=en, **kw)


def _h(key, address, de, en, **kw) -> Register:
    return Register(key=key, address=address, kind="holding", name_de=de, name_en=en, **kw)


_TEMP = {"unit": "°C", "device_class": "temperature", "state_class": "measurement", "precision": 1}
_ENERGY = {
    "unit": "kWh",
    "device_class": "energy",
    "state_class": "total_increasing",
    "dtype": "uint32",
    "scale": 0.1,
    "precision": 1,
    "every": 2,
}
_HOURS = {
    "unit": "h",
    "device_class": "duration",
    "state_class": "total_increasing",
    "dtype": "uint32",
    "precision": 0,
    "every": 10,
}
_SETTING = {"diagnostic": True, "every": 2}
_TEMP_SETTING = {**_SETTING, "unit": "°C", "scale": 0.1, "precision": 1}
_K_SETTING = {**_SETTING, "unit": "K", "scale": 0.1, "precision": 1}

REGISTERS: tuple[Register, ...] = (
    # ------------------------------------------------------------ measurements
    _s("return", 10100, "Rücklauftemperatur", "Return temperature", scale=0.1, **_TEMP),
    _s("return_target", 10101, "Rücklauf-Soll", "Return target temperature", scale=0.1, **_TEMP),
    _s("flow", 10105, "Vorlauftemperatur", "Flow temperature", scale=0.1, **_TEMP),
    _s("outside", 10108, "Außentemperatur", "Outside temperature", dtype="int16", scale=0.1, **_TEMP),
    _s("dhw", 10120, "Warmwasser Temperatur", "Hot water temperature", dtype="int16", scale=0.1, **_TEMP),
    _s("dhw_target", 10121, "Warmwasser Soll", "Hot water target temperature", scale=0.1, every=2, **_TEMP),
    _s(
        "dhw_min",
        10122,
        "Warmwasser Minimum",
        "Hot water minimum",
        dtype="int16",
        scale=0.1,
        every=10,
        **_TEMP,
    ),
    _s(
        "dhw_max",
        10123,
        "Warmwasser Maximum",
        "Hot water maximum",
        dtype="int16",
        scale=0.1,
        every=10,
        **_TEMP,
    ),
    _s("error_number", 10201, "Fehlernummer", "Error number"),
    _s(
        "compressor_thermal_power",
        10300,
        "Heizleistung thermisch",
        "Thermal power",
        dtype="int16",
        scale=100,
        precision=0,
        unit="W",
        device_class="power",
        state_class="measurement",
    ),
    _s(
        "electric_power",
        10301,
        "Stromaufnahme",
        "Electric power",
        scale=100,
        precision=0,
        unit="W",
        device_class="power",
        state_class="measurement",
    ),
    _s("heat_generator_state", 10000, "Zustand Wärmeerzeuger", "Heat generator state"),
    _s("operating_mode", 10002, "Betriebsart", "Operating mode"),
    _s("heating_status", 10003, "Status Heizen", "Heating status"),
    _s("hot_water_status", 10004, "Status Warmwasser", "Hot water status"),
    # ----------------------------------------------------------------- counters
    _s("energy_el_total", 10310, "Strom gesamt", "Electric energy total", **_ENERGY),
    _s("energy_el_heating", 10312, "Strom Heizen", "Electric energy heating", **_ENERGY),
    _s("energy_el_dhw", 10314, "Strom Warmwasser", "Electric energy hot water", **_ENERGY),
    _s("energy_th_total", 10320, "Wärme gesamt", "Thermal energy total", **_ENERGY),
    _s("energy_th_heating", 10322, "Wärme Heizen", "Thermal energy heating", **_ENERGY),
    _s("energy_th_dhw", 10324, "Wärme Warmwasser", "Thermal energy hot water", **_ENERGY),
    _s("hours_hp", 10404, "Betriebsstunden Verdichter", "Compressor operating hours", **_HOURS),
    _s("hours_heating", 10406, "Betriebsstunden Heizen", "Heating operating hours", **_HOURS),
    _s("hours_dhw", 10408, "Betriebsstunden Warmwasser", "Hot water operating hours", **_HOURS),
    # ----------------------------------------------- settings (holding, read back)
    _h("cfg_heating_mode", 10000, "Einstellung Heizen Betriebsart", "Setting heating mode", **_SETTING),
    _h(
        "cfg_heating_setpoint",
        10001,
        "Einstellung Heizen Sollwert",
        "Setting heating setpoint",
        **_TEMP_SETTING,
    ),
    _h(
        "cfg_heating_offset",
        10002,
        "Heizkurven-Anhebung",
        "Heating curve offset",
        dtype="int16",
        scale=0.1,
        precision=1,
        unit="K",
        platform="number",
        every=1,
    ),
    _h("cfg_heating_level", 10003, "Einstellung Heizen Stufe", "Setting heating level", **_SETTING),
    _h("cfg_dhw_mode", 10005, "Einstellung Warmwasser Betriebsart", "Setting hot water mode", **_SETTING),
    _h(
        "cfg_dhw_setpoint",
        10006,
        "Einstellung Warmwasser Sollwert",
        "Setting hot water setpoint",
        **_TEMP_SETTING,
    ),
    _h(
        "cfg_dhw_offset",
        10007,
        "Einstellung Warmwasser Anhebung",
        "Setting hot water offset",
        dtype="int16",
        **_K_SETTING,
    ),
    _h("cfg_dhw_level", 10008, "Einstellung Warmwasser Stufe", "Setting hot water level", **_SETTING),
    _h(
        "cfg_mk1_mode",
        10010,
        "Einstellung Mischkreis 1 Betriebsart",
        "Setting mixing circuit 1 mode",
        **_SETTING,
    ),
    _h(
        "cfg_mk1_setpoint",
        10011,
        "Einstellung Mischkreis 1 Sollwert",
        "Setting mixing circuit 1 setpoint",
        **_TEMP_SETTING,
    ),
    _h(
        "cfg_mk1_offset",
        10012,
        "Einstellung Mischkreis 1 Anhebung",
        "Setting mixing circuit 1 offset",
        dtype="int16",
        **_K_SETTING,
    ),
    _h(
        "cfg_mk1_level", 10013, "Einstellung Mischkreis 1 Stufe", "Setting mixing circuit 1 level", **_SETTING
    ),
    _h(
        "cfg_power_limit_mode",
        10040,
        "Einstellung Leistungsbegrenzung Modus",
        "Setting power limit mode",
        **_SETTING,
    ),
    _h(
        "cfg_power_limit",
        10041,
        "Einstellung Leistungsbegrenzung Wert",
        "Setting power limit",
        scale=0.1,
        precision=1,
        unit="kW",
        **_SETTING,
    ),
    _h(
        "cfg_overall_mode",
        10065,
        "Einstellung Gesamt-Heizung Betriebsart",
        "Setting overall heating mode",
        **_SETTING,
    ),
    _h(
        "cfg_overall_offset",
        10066,
        "Einstellung Gesamt-Heizung Anhebung",
        "Setting overall heating offset",
        **_SETTING,
    ),
    _h(
        "cfg_overall_level",
        10067,
        "Einstellung Gesamt-Heizung Stufe",
        "Setting overall heating level",
        **_SETTING,
    ),
    _h(
        "cfg_circulation",
        10070,
        "Einstellung Zirkulationspumpe Start",
        "Setting circulation pump start",
        **_SETTING,
    ),
    # ------------------------------------------------------------------ firmware
    _s("fw_platform", 10400, "Firmware Plattform", "Firmware platform", diagnostic=True, every=120),
    _s("fw_major", 10401, "Firmware Version Haupt", "Firmware major version", diagnostic=True, every=120),
    _s("fw_minor", 10402, "Firmware Version Neben", "Firmware minor version", diagnostic=True, every=120),
    # ------------------------------------------------- switches (blocks, holding)
    _h("heating_block", 10050, "Heizung sperren", "Block heating", platform="switch"),
    _h("dhw_block", 10051, "Warmwasser sperren", "Block hot water", platform="switch"),
    _h("cooling_block", 10052, "Kühlung sperren", "Block cooling", platform="switch"),
    _h("pool_block", 10053, "Pool sperren", "Block pool", platform="switch"),
    _h("extra_dhw", 10071, "Extra-Warmwasser", "Extra hot water", platform="switch"),
)

# Raw values whose meaning is not documented. Disabled by default; handy for
# analysis and for reverse engineering of new firmware versions.
RAW_INPUT_ADDRESSES: tuple[int, ...] = (
    10102,
    10103,
    10104,
    10109,
    10110,
    10112,
    10113,
    10124,
    10140,
    10141,
    10142,
    10143,
    10202,
    10203,
    10204,
    10205,
    10206,
    10302,
    10350,
    10351,
    10354,
    10355,
    10356,
    10360,
    10361,
)

RAW_REGISTERS: tuple[Register, ...] = tuple(
    Register(
        key=f"raw_{address}",
        address=address,
        kind="input",
        name_de=f"Diagnose Rohwert {address}",
        name_en=f"Diagnostic raw value {address}",
        diagnostic=True,
        enabled_default=False,
        every=4,
    )
    for address in RAW_INPUT_ADDRESSES
)

# Capability flags (discrete inputs) – tell which parts the installation has.
CAPABILITIES: tuple[Register, ...] = tuple(
    Register(
        key=f"cap_{suffix}",
        address=address,
        kind="discrete",
        name_de=f"Ausstattung {de} vorhanden",
        name_en=f"Capability {en}",
        platform="binary_sensor",
        diagnostic=True,
        every=10,
    )
    for address, suffix, de, en in (
        (10000, "heating", "Heizen", "heating"),
        (10001, "hot_water", "Warmwasser", "hot water"),
        (10002, "cooling", "Kühlen", "cooling"),
        (10003, "pool", "Pool", "pool"),
        (10005, "room_controller", "Raumregler", "room controller"),
        (10006, "mk1_heating", "Mischkreis 1 Heizen", "mixing circuit 1 heating"),
        (10007, "mk1_cooling", "Mischkreis 1 Kühlen", "mixing circuit 1 cooling"),
        (10008, "mk2_heating", "Mischkreis 2 Heizen", "mixing circuit 2 heating"),
        (10009, "mk2_cooling", "Mischkreis 2 Kühlen", "mixing circuit 2 cooling"),
        (10010, "mk3_heating", "Mischkreis 3 Heizen", "mixing circuit 3 heating"),
        (10011, "mk3_cooling", "Mischkreis 3 Kühlen", "mixing circuit 3 cooling"),
    )
)

ALL_REGISTERS: tuple[Register, ...] = REGISTERS + RAW_REGISTERS + CAPABILITIES

BY_KEY: dict[str, Register] = {reg.key: reg for reg in ALL_REGISTERS}
