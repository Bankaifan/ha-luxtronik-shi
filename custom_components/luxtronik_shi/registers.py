"""Register map of the Luxtronik Smart Home Interface (SHI) via Modbus/TCP.

The map covers every documented register of the SHI (firmware 3.90 ... 3.92) that was
verified on a running installation (alpha innotec LWDV 91-1/3, firmware 3.92.3).
Everything that can be written through Modbus is exposed as number, select or switch.

Naming scheme of the keys: they are identical to the suffix of the entity IDs
that the former YAML ``modbus:`` configuration produced (``lwdv_shi_<key>``),
which makes a migration of existing automations and dashboards easy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RegKind = Literal["input", "holding", "discrete"]
DType = Literal["uint16", "int16", "uint32"]
Platform = Literal["sensor", "binary_sensor", "switch", "number", "select"]


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
    # Writable numbers: allowed range and step in physical units.
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    # Entity category "configuration" (settings that are normally not touched daily).
    config: bool = False
    # Enumerations: the raw value is the index into this tuple (select and enum sensors).
    options: tuple[str, ...] | None = None

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
_SETTING = {"config": True, "every": 2}
_MODES = ("off", "setpoint", "offset", "level")
_LEVELS = ("evu_lock", "reduced", "normal", "boost")
_OPERATING_MODES = (
    "heating",
    "hot_water",
    "pool",
    "evu_lock",
    "defrost",
    "off",
    "external_source",
    "cooling",
)
_BUFFER_TYPES = ("unknown", "series", "separation", "multi")


def _temp_in(key, address, de, en, *, signed=True, **kw) -> Register:
    return _s(key, address, de, en, dtype="int16" if signed else "uint16", scale=0.1, **{**_TEMP, **kw})


def _number(key, address, de, en, *, lo, hi, step, unit, signed=False, **kw) -> Register:
    return _h(
        key,
        address,
        de,
        en,
        dtype="int16" if signed else "uint16",
        scale=0.1,
        precision=1,
        unit=unit,
        platform="number",
        min_value=lo,
        max_value=hi,
        step=step,
        **{**_SETTING, **kw},
    )


def _select(key, address, de, en, options, **kw) -> Register:
    return _h(key, address, de, en, platform="select", options=options, **{**_SETTING, **kw})


REGISTERS: tuple[Register, ...] = (
    # ------------------------------------------------------------ measurements
    # NOTE: the published register lists name 10100 "RL-Soll" and 10101 "RL-Ist". Measured on a real
    # installation it is the other way round (10100 follows the water temperature, 10101 is the
    # target that jumps while the pump heats), so the names below follow the measurements.
    _s("return", 10100, "Rücklauftemperatur", "Return temperature", scale=0.1, **_TEMP),
    _s("return_target", 10101, "Rücklauf-Soll", "Return target temperature", scale=0.1, **_TEMP),
    _temp_in("return_external", 10102, "Rücklauf extern", "External return temperature", every=2),
    _temp_in("return_limit", 10103, "Rücklauf Begrenzung", "Return limit", every=10),
    _temp_in("return_min_target", 10104, "Rücklauf-Soll Minimum", "Return target minimum", every=10),
    _s("flow", 10105, "Vorlauftemperatur", "Flow temperature", scale=0.1, **_TEMP),
    _temp_in(
        "room",
        10106,
        "Raumtemperatur (Raumeinheit)",
        "Room temperature (room unit)",
        every=2,
        enabled_default=False,
    ),
    _temp_in("heating_limit", 10107, "Grenztemperatur Heizen", "Heating limit temperature", every=10),
    _s("outside", 10108, "Außentemperatur", "Outside temperature", dtype="int16", scale=0.1, **_TEMP),
    _s("dhw", 10120, "Warmwasser Temperatur", "Hot water temperature", dtype="int16", scale=0.1, **_TEMP),
    _s("dhw_target", 10121, "Warmwasser Soll", "Hot water target temperature", scale=0.1, every=2, **_TEMP),
    _temp_in("dhw_min", 10122, "Warmwasser Minimum", "Hot water minimum", every=10),
    _temp_in("dhw_max", 10123, "Warmwasser Maximum", "Hot water maximum", every=10),
    _temp_in("dhw_limit", 10124, "Grenztemperatur Warmwasser", "Hot water limit temperature", every=10),
    # mixing circuits (flow actual / target / minimum / maximum)
    _temp_in("mk1_flow", 10140, "Mischkreis 1 Vorlauf", "Mixing circuit 1 flow", every=1),
    _temp_in("mk1_flow_target", 10141, "Mischkreis 1 Vorlauf-Soll", "Mixing circuit 1 flow target", every=1),
    _temp_in(
        "mk1_flow_min", 10142, "Mischkreis 1 Vorlauf Minimum", "Mixing circuit 1 flow minimum", every=10
    ),
    _temp_in(
        "mk1_flow_max", 10143, "Mischkreis 1 Vorlauf Maximum", "Mixing circuit 1 flow maximum", every=10
    ),
    _temp_in("mk2_flow", 10150, "Mischkreis 2 Vorlauf", "Mixing circuit 2 flow", enabled_default=False),
    _temp_in(
        "mk2_flow_target",
        10151,
        "Mischkreis 2 Vorlauf-Soll",
        "Mixing circuit 2 flow target",
        enabled_default=False,
    ),
    _temp_in(
        "mk2_flow_min",
        10152,
        "Mischkreis 2 Vorlauf Minimum",
        "Mixing circuit 2 flow minimum",
        every=10,
        enabled_default=False,
    ),
    _temp_in(
        "mk2_flow_max",
        10153,
        "Mischkreis 2 Vorlauf Maximum",
        "Mixing circuit 2 flow maximum",
        every=10,
        enabled_default=False,
    ),
    _temp_in("mk3_flow", 10160, "Mischkreis 3 Vorlauf", "Mixing circuit 3 flow", enabled_default=False),
    _temp_in(
        "mk3_flow_target",
        10161,
        "Mischkreis 3 Vorlauf-Soll",
        "Mixing circuit 3 flow target",
        enabled_default=False,
    ),
    _temp_in(
        "mk3_flow_min",
        10162,
        "Mischkreis 3 Vorlauf Minimum",
        "Mixing circuit 3 flow minimum",
        every=10,
        enabled_default=False,
    ),
    _temp_in(
        "mk3_flow_max",
        10163,
        "Mischkreis 3 Vorlauf Maximum",
        "Mixing circuit 3 flow maximum",
        every=10,
        enabled_default=False,
    ),
    _s("error_number", 10201, "Fehlernummer", "Error number"),
    _s(
        "buffer_type",
        10202,
        "Puffertyp",
        "Buffer tank type",
        options=_BUFFER_TYPES,
        diagnostic=True,
        every=120,
    ),
    _s(
        "switching_lock_minutes",
        10203,
        "Schaltspielsperre",
        "Switching lock time",
        unit="min",
        diagnostic=True,
        every=30,
    ),
    _s(
        "min_runtime_minutes",
        10204,
        "Mindestlaufzeit Wärmepumpe",
        "Heat pump minimum runtime",
        unit="min",
        diagnostic=True,
        every=30,
    ),
    _s(
        "cooling_configured",
        10205,
        "Kühlung konfiguriert",
        "Cooling configured",
        platform="binary_sensor",
        diagnostic=True,
        every=30,
    ),
    _s(
        "pool_configured",
        10206,
        "Schwimmbad konfiguriert",
        "Pool configured",
        platform="binary_sensor",
        diagnostic=True,
        every=30,
    ),
    _s(
        "cooling_release",
        10207,
        "Kühlung freigegeben",
        "Cooling released",
        platform="binary_sensor",
        diagnostic=True,
        every=30,
    ),
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
    _s(
        "electric_power_min",
        10302,
        "Stromaufnahme Minimum",
        "Electric power minimum",
        scale=100,
        precision=0,
        unit="W",
        device_class="power",
        diagnostic=True,
        every=10,
    ),
    # status: bit mask (VD1, VD2, ZWE1, ZWE2 – decoded into binary sensors) and operating mode
    _s("heat_generator_state", 10000, "Zustand Wärmeerzeuger", "Heat generator state"),
    _s("operating_mode", 10002, "Betriebsart", "Operating mode", options=_OPERATING_MODES),
    _s("heating_status", 10003, "Status Heizen", "Heating status"),
    _s("hot_water_status", 10004, "Status Warmwasser", "Hot water status"),
    _s("cooling_status", 10006, "Status Kühlung", "Cooling status", diagnostic=True, every=2),
    _s("pool_status", 10007, "Status Schwimmbad", "Pool status", diagnostic=True, every=2),
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
    # ------------------------------------- settings (holding): numbers and selects
    # heating
    _select("cfg_heating_mode", 10000, "Heizen Betriebsart", "Heating mode", _MODES),
    _number(
        "cfg_heating_setpoint",
        10001,
        "Heizen Sollwert",
        "Heating setpoint",
        lo=10,
        hi=70,
        step=0.5,
        unit="°C",
    ),
    _number(
        "cfg_heating_offset",
        10002,
        "Heizkurven-Anhebung",
        "Heating curve offset",
        lo=-5,
        hi=5,
        step=0.5,
        unit="K",
        signed=True,
        config=False,
        every=1,
    ),
    _select("cfg_heating_level", 10003, "Heizen Stufe", "Heating level", _LEVELS),
    # hot water
    _select("cfg_dhw_mode", 10005, "Warmwasser Betriebsart", "Hot water mode", _MODES),
    _number(
        "cfg_dhw_setpoint",
        10006,
        "Warmwasser Sollwert",
        "Hot water setpoint",
        lo=10,
        hi=65,
        step=0.5,
        unit="°C",
    ),
    _number(
        "cfg_dhw_offset",
        10007,
        "Warmwasser Anhebung",
        "Hot water offset",
        lo=-10,
        hi=10,
        step=0.5,
        unit="K",
        signed=True,
    ),
    _select("cfg_dhw_level", 10008, "Warmwasser Stufe", "Hot water level", _LEVELS),
    # mixing circuit 1 heating / cooling
    _select(
        "cfg_mk1_mode", 10010, "Mischkreis 1 Heizen Betriebsart", "Mixing circuit 1 heating mode", _MODES
    ),
    _number(
        "cfg_mk1_setpoint",
        10011,
        "Mischkreis 1 Heizen Sollwert",
        "Mixing circuit 1 heating setpoint",
        lo=10,
        hi=70,
        step=0.5,
        unit="°C",
    ),
    _number(
        "cfg_mk1_offset",
        10012,
        "Mischkreis 1 Heizen Anhebung",
        "Mixing circuit 1 heating offset",
        lo=-10,
        hi=10,
        step=0.5,
        unit="K",
        signed=True,
    ),
    _select("cfg_mk1_level", 10013, "Mischkreis 1 Heizen Stufe", "Mixing circuit 1 heating level", _LEVELS),
    _select(
        "cfg_mk1_cool_mode",
        10015,
        "Mischkreis 1 Kühlen Betriebsart",
        "Mixing circuit 1 cooling mode",
        _MODES,
        enabled_default=False,
    ),
    _number(
        "cfg_mk1_cool_setpoint",
        10016,
        "Mischkreis 1 Kühlen Sollwert",
        "Mixing circuit 1 cooling setpoint",
        lo=5,
        hi=40,
        step=0.5,
        unit="°C",
        enabled_default=False,
    ),
    _number(
        "cfg_mk1_cool_offset",
        10017,
        "Mischkreis 1 Kühlen Anhebung",
        "Mixing circuit 1 cooling offset",
        lo=-10,
        hi=10,
        step=0.5,
        unit="K",
        signed=True,
        enabled_default=False,
    ),
    # power limit (LPC)
    _select(
        "cfg_power_limit_mode",
        10040,
        "Leistungsbegrenzung Modus",
        "Power limit mode",
        ("none", "soft", "hard"),
    ),
    _number(
        "cfg_power_limit", 10041, "Leistungsbegrenzung Wert", "Power limit", lo=0, hi=30, step=0.1, unit="kW"
    ),
    # overall heating (firmware 3.92.0 or later)
    _select("cfg_overall_mode", 10065, "Gesamt-Heizung Betriebsart", "Overall heating mode", _MODES),
    _number(
        "cfg_overall_offset",
        10066,
        "Gesamt-Heizung Anhebung",
        "Overall heating offset",
        lo=-10,
        hi=10,
        step=0.5,
        unit="K",
        signed=True,
    ),
    _select("cfg_overall_level", 10067, "Gesamt-Heizung Stufe", "Overall heating level", _LEVELS),
    # ------------------------------------------------------------------ firmware
    _s("fw_platform", 10400, "Firmware Plattform", "Firmware platform", diagnostic=True, every=120),
    _s("fw_major", 10401, "Firmware Version Haupt", "Firmware major version", diagnostic=True, every=120),
    _s("fw_minor", 10402, "Firmware Version Neben", "Firmware minor version", diagnostic=True, every=120),
    # ------------------------------------------------- switches (blocks, holding)
    _h("heating_block", 10050, "Heizung sperren", "Block heating", platform="switch"),
    _h("dhw_block", 10051, "Warmwasser sperren", "Block hot water", platform="switch"),
    _h("cooling_block", 10052, "Kühlung sperren", "Block cooling", platform="switch"),
    _h("pool_block", 10053, "Pool sperren", "Block pool", platform="switch"),
    # circulation pump and extra hot water (firmware 3.92.0 or later)
    _h("circulation", 10070, "Zirkulationspumpe", "Circulation pump", platform="switch"),
    _h("extra_dhw", 10071, "Extra-Warmwasser", "Extra hot water", platform="switch"),
)

# Raw values whose meaning is not documented. Disabled by default; handy for
# analysis and for reverse engineering of new firmware versions.
RAW_INPUT_ADDRESSES: tuple[int, ...] = (
    10109,
    10110,
    10112,
    10113,
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
