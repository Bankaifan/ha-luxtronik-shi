"""Register map of the Luxtronik Smart Home Interface (SHI) via Modbus/TCP.

The map covers every documented register of the SHI (firmware 3.90 ... 3.92) that was
verified on a running installation (alpha innotec LWDV 91-1/3, firmware 3.92.3).
Everything that can be written through Modbus is exposed as number, select or switch.

Naming scheme of the keys: they are identical to the suffix of the entity IDs
that the former YAML ``modbus:`` configuration produced (``lwdv_shi_<key>``),
which makes a migration of existing automations and dashboards easy.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
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
    # Where the register facts come from (shown in docs/registers.md). ``None`` = no source recorded (open).
    source: str | None = None

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
# Control mode of a circuit (python-luxtronik ``ControlMode``). Raw 0 ("off") means "no influence": the controller
# uses its own values. It does NOT switch the circuit off. The option keys stay for compatibility; the display text
# says what each option does (tools/gen_translations.py).
_MODES = ("off", "setpoint", "offset", "level")
CONTROL_MODES: tuple[str, ...] = _MODES
_LEVELS = ("normal", "increased", "increased2", "decreased")
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
# Buffer tank type (input 10202). The raw value is the index: 0 series, 1 separation, 2 multi-function buffer
# (python-luxtronik ``BufferType``, inputs.py index 202; confirmed on the reference installation, a separation
# buffer, which reads raw 1). Up to 0.10.1 the tuple started with "unknown", which shifted every value by one
# (a separation buffer showed as "series"). Values outside 0..2 read as unknown (no state).
_BUFFER_TYPES = ("series", "separation", "multi")


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
    _s("return", 10100, "Temperatur: Rücklauf", "Temperature: return", scale=0.1, **_TEMP),
    _s("return_target", 10101, "Temperatur: Rücklauf-Soll", "Temperature: return target", scale=0.1, **_TEMP),
    _temp_in(
        "return_external", 10102, "Temperatur: Rücklauf extern", "Temperature: return external", every=2
    ),
    _temp_in("return_limit", 10103, "Temperatur: Rücklauf-Begrenzung", "Temperature: return limit", every=10),
    _temp_in(
        "return_min_target",
        10104,
        "Temperatur: Rücklauf-Soll Minimum",
        "Temperature: return target minimum",
        every=10,
    ),
    _s("flow", 10105, "Temperatur: Vorlauf", "Temperature: flow", scale=0.1, **_TEMP),
    _temp_in(
        "room",
        10106,
        "Temperatur: Raum (Raumeinheit)",
        "Temperature: room (room unit)",
        every=2,
        enabled_default=False,
    ),
    _temp_in("heating_limit", 10107, "Grenztemperatur", "Limit temperature", every=10),
    _s("outside", 10108, "Temperatur: Außen", "Temperature: outside", dtype="int16", scale=0.1, **_TEMP),
    _s("dhw", 10120, "Temperatur", "Temperature", dtype="int16", scale=0.1, **_TEMP),
    _s("dhw_target", 10121, "Soll", "Target", scale=0.1, every=2, **_TEMP),
    _temp_in("dhw_min", 10122, "Minimum", "Minimum", every=10),
    _temp_in("dhw_max", 10123, "Maximum", "Maximum", every=10),
    _temp_in("dhw_limit", 10124, "Grenztemperatur", "Limit temperature", every=10),
    # mixing circuits (flow actual / target / minimum / maximum)
    _temp_in("mk1_flow", 10140, "Mischkreis 1: Vorlauf", "Mixing circuit 1: flow", every=1),
    _temp_in(
        "mk1_flow_target", 10141, "Mischkreis 1: Vorlauf-Soll", "Mixing circuit 1: flow target", every=1
    ),
    _temp_in(
        "mk1_flow_min", 10142, "Mischkreis 1: Vorlauf Minimum", "Mixing circuit 1: flow minimum", every=10
    ),
    _temp_in(
        "mk1_flow_max", 10143, "Mischkreis 1: Vorlauf Maximum", "Mixing circuit 1: flow maximum", every=10
    ),
    _temp_in("mk2_flow", 10150, "Mischkreis 2: Vorlauf", "Mixing circuit 2: flow", enabled_default=False),
    _temp_in(
        "mk2_flow_target",
        10151,
        "Mischkreis 2: Vorlauf-Soll",
        "Mixing circuit 2: flow target",
        enabled_default=False,
    ),
    _temp_in(
        "mk2_flow_min",
        10152,
        "Mischkreis 2: Vorlauf Minimum",
        "Mixing circuit 2: flow minimum",
        every=10,
        enabled_default=False,
    ),
    _temp_in(
        "mk2_flow_max",
        10153,
        "Mischkreis 2: Vorlauf Maximum",
        "Mixing circuit 2: flow maximum",
        every=10,
        enabled_default=False,
    ),
    _temp_in("mk3_flow", 10160, "Mischkreis 3: Vorlauf", "Mixing circuit 3: flow", enabled_default=False),
    _temp_in(
        "mk3_flow_target",
        10161,
        "Mischkreis 3: Vorlauf-Soll",
        "Mixing circuit 3: flow target",
        enabled_default=False,
    ),
    _temp_in(
        "mk3_flow_min",
        10162,
        "Mischkreis 3: Vorlauf Minimum",
        "Mixing circuit 3: flow minimum",
        every=10,
        enabled_default=False,
    ),
    _temp_in(
        "mk3_flow_max",
        10163,
        "Mischkreis 3: Vorlauf Maximum",
        "Mixing circuit 3: flow maximum",
        every=10,
        enabled_default=False,
    ),
    _s("error_number", 10201, "Status: Fehlernummer", "Status: error number"),
    _s(
        "buffer_type",
        10202,
        "Anlage: Puffertyp",
        "System: buffer tank type",
        options=_BUFFER_TYPES,
        diagnostic=True,
        every=120,
        source="python-luxtronik inputs.py (BufferType); measured",
    ),
    _s(
        "switching_lock_minutes",
        10203,
        "Anlage: Schaltspielsperre",
        "System: switching lock time",
        unit="min",
        diagnostic=True,
        every=30,
    ),
    _s(
        "min_runtime_minutes",
        10204,
        "Anlage: Mindestlaufzeit",
        "System: minimum runtime",
        unit="min",
        diagnostic=True,
        every=30,
    ),
    _s(
        "cooling_configured",
        10205,
        "Kühlen: konfiguriert",
        "Cooling: configured",
        platform="binary_sensor",
        diagnostic=True,
        every=30,
    ),
    _s(
        "pool_configured",
        10206,
        "Pool: konfiguriert",
        "Pool: configured",
        platform="binary_sensor",
        diagnostic=True,
        every=30,
    ),
    _s(
        "cooling_release",
        10207,
        "Kühlen: freigegeben",
        "Cooling: released",
        platform="binary_sensor",
        diagnostic=True,
        every=30,
    ),
    _s(
        "compressor_thermal_power",
        10300,
        "Leistung: thermisch",
        "Power: thermal",
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
        "Leistung: elektrisch",
        "Power: electric",
        scale=100,
        precision=0,
        unit="W",
        device_class="power",
        state_class="measurement",
    ),
    _s(
        "electric_power_min",
        10302,
        "Leistung: elektrisch Minimum",
        "Power: electric minimum",
        scale=100,
        precision=0,
        unit="W",
        device_class="power",
        diagnostic=True,
        every=10,
    ),
    # status: bit mask (VD1, VD2, ZWE1, ZWE2 – decoded into binary sensors) and operating mode
    _s(
        "heat_generator_state", 10000, "Status: Wärmeerzeuger (Bitmaske)", "Status: heat generator (bit mask)"
    ),
    _s("operating_mode", 10002, "Status: Betriebsart", "Status: operating mode", options=_OPERATING_MODES),
    _s("heating_status", 10003, "Status", "Status"),
    _s("hot_water_status", 10004, "Status", "Status"),
    _s("cooling_status", 10006, "Status", "Status", diagnostic=True, every=2),
    _s("pool_status", 10007, "Status", "Status", diagnostic=True, every=2),
    # ----------------------------------------------------------------- counters
    _s("energy_el_total", 10310, "Energie: Strom gesamt", "Energy: electric total", **_ENERGY),
    _s("energy_el_heating", 10312, "Energie: Strom", "Energy: electric", **_ENERGY),
    _s("energy_el_dhw", 10314, "Energie: Strom", "Energy: electric", **_ENERGY),
    _s("energy_th_total", 10320, "Energie: Wärme gesamt", "Energy: thermal total", **_ENERGY),
    _s("energy_th_heating", 10322, "Energie: Wärme", "Energy: thermal", **_ENERGY),
    _s("energy_th_dhw", 10324, "Energie: Wärme", "Energy: thermal", **_ENERGY),
    _s("hours_hp", 10404, "Betriebsstunden: Verdichter", "Operating hours: compressor", **_HOURS),
    _s("hours_heating", 10406, "Betriebsstunden", "Operating hours", **_HOURS),
    _s("hours_dhw", 10408, "Betriebsstunden", "Operating hours", **_HOURS),
    # ------------------------------------- settings (holding): numbers and selects
    # heating
    _select("cfg_heating_mode", 10000, "Betriebsart", "Mode", _MODES),
    _number(
        "cfg_heating_setpoint",
        10001,
        "Sollwert",
        "Setpoint",
        lo=15,
        hi=75,
        step=0.5,
        unit="°C",
    ),
    _number(
        "cfg_heating_offset",
        10002,
        "Heizkurven-Anhebung",
        "Curve offset",
        lo=-20,
        hi=20,
        step=0.5,
        unit="K",
        signed=True,
        config=False,
        every=1,
    ),
    _select("cfg_heating_level", 10003, "Stufe", "Level", _LEVELS),
    # hot water
    _select("cfg_dhw_mode", 10005, "Betriebsart", "Mode", _MODES),
    _number(
        "cfg_dhw_setpoint",
        10006,
        "Sollwert",
        "Setpoint",
        lo=30,
        hi=75,
        step=0.5,
        unit="°C",
    ),
    _number(
        "cfg_dhw_offset",
        10007,
        "Anhebung",
        "Offset",
        lo=-20,
        hi=20,
        step=0.5,
        unit="K",
        signed=True,
    ),
    _select("cfg_dhw_level", 10008, "Stufe", "Level", _LEVELS),
    # mixing circuit 1 heating / cooling
    _select("cfg_mk1_mode", 10010, "Mischkreis 1: Betriebsart", "Mixing circuit 1: mode", _MODES),
    _number(
        "cfg_mk1_setpoint",
        10011,
        "Mischkreis 1: Sollwert",
        "Mixing circuit 1: setpoint",
        lo=20,
        hi=65,
        step=0.5,
        unit="°C",
    ),
    _number(
        "cfg_mk1_offset",
        10012,
        "Mischkreis 1: Anhebung",
        "Mixing circuit 1: offset",
        lo=-5,
        hi=5,
        step=0.5,
        unit="K",
        signed=True,
    ),
    _select("cfg_mk1_level", 10013, "Mischkreis 1: Stufe", "Mixing circuit 1: level", _LEVELS),
    _select(
        "cfg_mk1_cool_mode",
        10015,
        "Mischkreis 1: Betriebsart",
        "Mixing circuit 1: mode",
        _MODES,
        enabled_default=False,
    ),
    _number(
        "cfg_mk1_cool_setpoint",
        10016,
        "Mischkreis 1: Sollwert",
        "Mixing circuit 1: setpoint",
        lo=5,
        hi=25,
        step=0.5,
        unit="°C",
        enabled_default=False,
    ),
    _number(
        "cfg_mk1_cool_offset",
        10017,
        "Mischkreis 1: Anhebung",
        "Mixing circuit 1: offset",
        lo=-5,
        hi=5,
        step=0.5,
        unit="K",
        signed=True,
        enabled_default=False,
    ),
    # power limit (LPC)
    _select(
        "cfg_power_limit_mode",
        10040,
        "Leistungsbegrenzung: Modus",
        "Power limit: mode",
        ("none", "soft", "hard"),
    ),
    _number(
        "cfg_power_limit",
        10041,
        "Leistungsbegrenzung: Wert",
        "Power limit: value",
        lo=0,
        hi=30,
        step=0.1,
        unit="kW",
    ),
    # overall heating (firmware 3.92.0 or later)
# Overall heating (10065-10067) acts on all heating functions and overrides the per-circuit settings
    # (python-luxtronik: "Operating mode of all heating functions"). Its effect is not proven on the reference
    # installation, so the entities are disabled by default (owner decision).
        _select(
        "cfg_overall_mode", 10065, "Gesamt: Betriebsart", "Overall: mode", _MODES, enabled_default=False
    ),
    _number(
        "cfg_overall_offset",
        10066,
        "Gesamt: Anhebung",
        "Overall: offset",
        lo=-20,
        hi=20,
        step=0.5,
        unit="K",
        signed=True,
        enabled_default=False,
    ),
    _select(
        "cfg_overall_level", 10067, "Gesamt: Stufe", "Overall: level", _LEVELS, enabled_default=False
    ),
    # room temperature setpoint of the room control unit (RBE). Firmware V3.92.3 exposes this as the
    # writable holding RBE_RoomTemperatureSetpointRegister (target RBE_RT_Soll); see
    # docs/firmware-3.92.3-shi-analysis.md. python-luxtronik lists 10060 only as read-only "unknown".
    # Range is not a register fact: 20-40 C are plausible room temperatures (owner decision).
    _number(
        "cfg_room_setpoint",
        10060,
        "Raumtemperatur-Sollwert",
        "Room temperature setpoint",
        lo=20,
        hi=40,
        step=0.5,
        unit="°C",
    ),
    # ------------------------------------------------------------------ firmware
    _s("fw_platform", 10400, "Firmware: Plattform", "Firmware: platform", diagnostic=True, every=120),
    _s("fw_major", 10401, "Firmware: Version Haupt", "Firmware: major version", diagnostic=True, every=120),
    _s("fw_minor", 10402, "Firmware: Version Neben", "Firmware: minor version", diagnostic=True, every=120),
    # ------------------------------------------------- switches (blocks, holding)
    _h("heating_block", 10050, "Sperren", "Block", platform="switch"),
    _h("dhw_block", 10051, "Sperren", "Block", platform="switch"),
    _h("cooling_block", 10052, "Sperren", "Block", platform="switch"),
    _h("pool_block", 10053, "Sperren", "Block", platform="switch"),
    # circulation pump and extra hot water (firmware 3.92.0 or later)
    _h(
        "circulation",
        10070,
        "Zirkulationspumpe",
        "Circulation pump",
        platform="switch",
    ),
    _h("extra_dhw", 10071, "Extra", "Extra", platform="switch"),
    # --------------------------------------- formerly raw values, meaning from python-luxtronik
    # 10109, 10110 and 10112 were ``raw_10109``, ``raw_10110`` and ``raw_10112`` up to 0.8.2; see RENAMED_KEYS.
    # python-luxtronik: ``outside_temp_average`` (index 109, CelsiusInt16, 0.1 °C).
    _temp_in("outside_temp_average", 10109, "Temperatur: Außen Mittelwert", "Temperature: outside average", every=4),
    # python-luxtronik: ``heat_source_input`` (index 110, CelsiusInt16, 0.1 °C).
    _temp_in(
        "heat_source_input", 10110, "Temperatur: Wärmequelle Eintritt", "Temperature: heat source inlet", every=2
    ),
    # python-luxtronik: ``max_flow_temp`` (index 112, CelsiusUInt16, 0.1 °C).
    _temp_in(
        "max_flow_temp",
        10112,
        "Temperatur: Vorlauf Maximum",
        "Temperature: flow maximum",
        signed=False,
        diagnostic=True,
        enabled_default=False,
        every=4,
    ),
)


def _mixing_circuit_holdings(n: int) -> tuple[Register, ...]:
    """Holdings of mixing circuit 2 or 3: same layout as circuit 1, ranges from python-luxtronik."""
    base = 10000 + 10 * n
    de, en, k = f"Mischkreis {n}", f"Mixing circuit {n}", f"cfg_mk{n}"
    return (
        _select(f"{k}_mode", base, f"{de}: Betriebsart", f"{en}: mode", _MODES),
        _number(
            f"{k}_setpoint",
            base + 1,
            f"{de}: Sollwert",
            f"{en}: setpoint",
            lo=20,
            hi=65,
            step=0.5,
            unit="°C",
        ),
        _number(
            f"{k}_offset",
            base + 2,
            f"{de}: Anhebung",
            f"{en}: offset",
            lo=-5,
            hi=5,
            step=0.5,
            unit="K",
            signed=True,
        ),
        _select(f"{k}_level", base + 3, f"{de}: Stufe", f"{en}: level", _LEVELS),
        _select(f"{k}_cool_mode", base + 5, f"{de}: Betriebsart", f"{en}: mode", _MODES),
        _number(
            f"{k}_cool_setpoint",
            base + 6,
            f"{de}: Sollwert",
            f"{en}: setpoint",
            lo=5,
            hi=25,
            step=0.5,
            unit="°C",
        ),
        _number(
            f"{k}_cool_offset",
            base + 7,
            f"{de}: Anhebung",
            f"{en}: offset",
            lo=-5,
            hi=5,
            step=0.5,
            unit="K",
            signed=True,
        ),
    )


# Added in 0.4.0 (source: python-luxtronik definitions). Entries created before 0.3.0 without an equipment
# option do not get these, so their polling load and entity list stay as they were.
ADDED_IN_0_4: tuple[Register, ...] = (
    *_mixing_circuit_holdings(2),
    *_mixing_circuit_holdings(3),
    _temp_in(
        "heat_source_out",
        10111,
        "Temperatur: Wärmequelle Austritt",
        "Temperature: heat source outlet",
        every=2,
    ),
    _s("energy_el_cooling", 10316, "Energie: Strom", "Energy: electric", **_ENERGY),
    _s("energy_el_pool", 10318, "Energie: Strom", "Energy: electric", **_ENERGY),
    _s("energy_th_cooling", 10326, "Energie: Wärme", "Energy: thermal", **_ENERGY),
    _s("energy_th_pool", 10328, "Energie: Wärme", "Energy: thermal", **_ENERGY),
)
REGISTERS = REGISTERS + ADDED_IN_0_4

# Keys that were renamed with the owner's approval: old key -> new key (same platform, same address).
# ``async_setup_entry`` moves the registry entries over, so the entity IDs stay. The old keys stay in the entity
# contract fixture, and ``tests/test_contract.py`` accepts them as long as the new key exists.
RENAMED_KEYS: dict[str, str] = {
    "raw_10109": "outside_temp_average",
    "raw_10110": "heat_source_input",
    "raw_10112": "max_flow_temp",
}

# Raw values whose meaning is not documented. Disabled by default; handy for
# analysis and for reverse engineering of new firmware versions.
RAW_INPUT_ADDRESSES: tuple[int, ...] = (
    10113,
    10350,
    10351,
    10354,
    10355,
    10356,
    10360,
    10361,
)

# Further undocumented values of python-luxtronik (``unknown_input_*`` and ``unknown_holding_60``, "function
# unknown"), added after 0.8.2. They are polled rarely, because nobody knows what they mean yet, and entries
# without an equipment option (created before 0.3.0) do not get them (see ``_LEGACY_EXCLUDED``).
RAW_INPUT_ADDRESSES_ADDED: tuple[int, ...] = (
    10352,
    10353,
    10410,
    10411,
    10412,
    10413,
    10416,
    10417,
    10500,
    10501,
    10502,
)
# Holding registers that only python-luxtronik lists as read-only and with unknown function. Read, never written.
# (10060 was briefly here but is the writable RBE room-temperature setpoint, now exposed as cfg_room_setpoint.)
RAW_HOLDING_ADDRESSES_ADDED: tuple[int, ...] = ()


# Raw values whose meaning is proven by the firmware (V3.92.3, bin/Controller; function addresses in
# docs/firmware-3.92.3-register-meanings.md) and confirmed by a measurement on the reference installation where the
# equipment exists. They keep the key ``raw_<address>`` and stay disabled by default (diagnostic); only the display
# name, unit and scale are filled in. Other raw values stay open.
RAW_MEANINGS: dict[int, dict] = {
    # t0/0x67: Sollwert_TRL_HZ + MovingAverage::spread (0x0019ac68). Wire value in 0.1 degC (INT16, divisor 1).
    10113: {
        "name_de": "Vorlauf: Soll Heizen (berechnet)",
        "name_en": "Flow: heating target (calculated)",
        "dtype": "int16",
        **_TEMP,
        "scale": 0.1,
        "source": "proven: firmware 0x0019ac68 (return target + moving average of flow-return spread); measured",
    },
    # Digital outputs of the controller (0 = off, 1 = on). Variable names are those of the firmware (0x0008bef8).
    10350: {"name_de": "Ausgang: VBO", "name_en": "Output: VBO", "source": "proven: firmware VBOout (t0/0x45); measured: runs with the compressor"},
    10351: {"name_de": "Ausgang: FP1", "name_en": "Output: FP1", "source": "proven: firmware FP1out (t0/0x6d); measured: follows the heating pump"},
    10352: {"name_de": "Ausgang: FP2", "name_en": "Output: FP2", "source": "proven: firmware FP2out (t0/0x4c); not measured (no second circuit)"},
    10353: {"name_de": "Ausgang: FP3", "name_en": "Output: FP3", "source": "proven: firmware FP3out (t0/0x4d); not measured (no third circuit)"},
    10354: {"name_de": "Ausgang: Heizungsumwälzpumpe (HUP)", "name_en": "Output: heating circulation pump (HUP)", "source": "proven: firmware HUPout (t0/0x20); measured"},
    10355: {"name_de": "Ausgang: Brauchwasserumwälzpumpe (BUP)", "name_en": "Output: DHW pump (BUP)", "source": "proven: firmware BUPout (t0/0x44); measured"},
    10356: {"name_de": "Ausgang: Zirkulationspumpe (ZIP)", "name_en": "Output: circulation pump (ZIP)", "source": "proven: firmware ZIPout (t0/0x48); measured"},
    # Digital inputs (0 = off, 1 = on), firmware 0x0009833c.
    10360: {"name_de": "Eingang: EVU", "name_en": "Input: EVU", "source": "proven: firmware EVUin (t0/0x2a); measured: 1 while the utility lock is released"},
    10361: {"name_de": "Eingang: EVU 2", "name_en": "Input: EVU 2", "source": "proven: firmware EVU2in (t0/0x2b); measured: 0 on the reference installation"},
}


def _raw(address: int, kind: RegKind, every: int) -> Register:
    meaning = RAW_MEANINGS.get(address, {})
    return Register(
        key=f"raw_{address}",
        address=address,
        kind=kind,
        **{"name_de": f"Rohwert: {address}", "name_en": f"Raw value: {address}", **meaning},
        diagnostic=True,
        enabled_default=False,
        every=every,
    )


_RAW_ADDED: tuple[Register, ...] = (
    *(_raw(address, "input", 30) for address in RAW_INPUT_ADDRESSES_ADDED),
    *(_raw(address, "holding", 30) for address in RAW_HOLDING_ADDRESSES_ADDED),
)
RAW_REGISTERS: tuple[Register, ...] = (
    *(_raw(address, "input", 4) for address in RAW_INPUT_ADDRESSES),
    *_RAW_ADDED,
)

# Capability flags (discrete inputs) – tell which parts the installation has.
CAPABILITIES: tuple[Register, ...] = tuple(
    Register(
        key=f"cap_{suffix}",
        address=address,
        kind="discrete",
        name_de=f"Ausstattung: {de}",
        name_en=f"Equipment: {en}",
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

# Limits and minimum/maximum values: rarely needed day to day, so they live in the
# "Diagnose" section of the device page. Only the entity category changes, never the key.
_SECONDARY_KEYS = frozenset(
    {
        "return_external",
        "return_limit",
        "return_min_target",
        "heating_limit",
        "dhw_min",
        "dhw_max",
        "dhw_limit",
        "mk1_flow_min",
        "mk1_flow_max",
        "mk2_flow_min",
        "mk2_flow_max",
        "mk3_flow_min",
        "mk3_flow_max",
    }
)
REGISTERS = tuple(replace(reg, diagnostic=True) if reg.key in _SECONDARY_KEYS else reg for reg in REGISTERS)

ALL_REGISTERS: tuple[Register, ...] = REGISTERS + RAW_REGISTERS + CAPABILITIES

# Keys of undocumented raw values (shown with a generic "Raw value: <address>" name).
# Raw values without a known meaning (they share the generic "Raw value: <address>" entity name).
RAW_KEYS: frozenset[str] = frozenset(reg.key for reg in RAW_REGISTERS if reg.address not in RAW_MEANINGS)
_LEGACY_EXCLUDED: frozenset[str] = frozenset(reg.key for reg in (*ADDED_IN_0_4, *_RAW_ADDED))

# -------------------------------------------------------------- installation equipment
# Optional parts of an installation. Registers of a part that is switched off in the options are
# neither polled nor turned into entities. Their registry entries (and entity IDs) stay, so
# switching the part on again restores the very same entities.
FEATURES: tuple[str, ...] = ("mk1", "mk2", "mk3", "cooling", "pool", "room_unit")

# Capability flag (discrete input) used to pre-fill each option during setup.
FEATURE_CAPABILITY: dict[str, str] = {
    "mk1": "cap_mk1_heating",
    "mk2": "cap_mk2_heating",
    "mk3": "cap_mk3_heating",
    "cooling": "cap_cooling",
    "pool": "cap_pool",
    "room_unit": "cap_room_controller",
}

# A register belongs to every listed part (all of them must be switched on).
_FEATURES_OF: dict[str, tuple[str, ...]] = {
    **{k: ("mk1",) for k in ("mk1_flow", "mk1_flow_target", "mk1_flow_min", "mk1_flow_max")},
    **{k: ("mk1",) for k in ("cfg_mk1_mode", "cfg_mk1_setpoint", "cfg_mk1_offset", "cfg_mk1_level")},
    **{k: ("mk1", "cooling") for k in ("cfg_mk1_cool_mode", "cfg_mk1_cool_setpoint", "cfg_mk1_cool_offset")},
    **{k: ("mk2",) for k in ("mk2_flow", "mk2_flow_target", "mk2_flow_min", "mk2_flow_max")},
    **{k: ("mk3",) for k in ("mk3_flow", "mk3_flow_target", "mk3_flow_min", "mk3_flow_max")},
    **{k: ("cooling",) for k in ("cooling_block", "cooling_status")},
    **{k: ("pool",) for k in ("pool_block", "pool_status")},
    "room": ("room_unit",),
    "cfg_room_setpoint": ("room_unit",),
    **{f"cfg_mk{n}_{s}": (f"mk{n}",) for n in (2, 3) for s in ("mode", "setpoint", "offset", "level")},
    **{f"cfg_mk{n}_cool_{s}": (f"mk{n}", "cooling") for n in (2, 3) for s in ("mode", "setpoint", "offset")},
    **{k: ("cooling",) for k in ("energy_el_cooling", "energy_th_cooling")},
    **{k: ("pool",) for k in ("energy_el_pool", "energy_th_pool")},
}


def features_of(reg: Register) -> tuple[str, ...]:
    """Optional parts a register depends on (empty: always present)."""
    return _FEATURES_OF.get(reg.key, ())


def active_registers(features: list[str] | tuple[str, ...] | set[str] | None) -> tuple[Register, ...]:
    """Registers to poll for the given parts. ``None`` means: everything (entries created before 0.3.0)."""
    if features is None:
        return tuple(reg for reg in ALL_REGISTERS if reg.key not in _LEGACY_EXCLUDED)
    enabled = set(features)
    return tuple(reg for reg in ALL_REGISTERS if enabled.issuperset(features_of(reg)))


BY_KEY: dict[str, Register] = {reg.key: reg for reg in ALL_REGISTERS}

# Entities of the climate platform. They are not registers of their own: they combine existing registers
# (``cfg_heating_mode``, ``cfg_heating_setpoint``, ``flow``). Their keys are part of the entity contract.
CLIMATE_HEATING_KEY = "climate_heating"
CLIMATE_KEYS: tuple[str, ...] = (CLIMATE_HEATING_KEY,)

# Setpoint registers whose value only applies in control mode ``setpoint`` (python-luxtronik holdings.py:
# "Requires heating_mode = setpoint" / "Requires dhw_mode = setpoint"): setpoint key -> (mode key, key of the
# controller's effective target). 10101 is the return target the heating setpoint (tRL) overrides; 10121 is the hot
# water target.
SETPOINT_GROUPS: dict[str, tuple[str, str]] = {
    "cfg_heating_setpoint": ("cfg_heating_mode", "return_target"),
    "cfg_dhw_setpoint": ("cfg_dhw_mode", "dhw_target"),
}

# Entities of the water_heater platform: a view on ``cfg_dhw_mode``, ``cfg_dhw_setpoint`` and ``dhw``.
WATER_HEATER_DHW_KEY = "water_heater_dhw"
WATER_HEATER_KEYS: tuple[str, ...] = (WATER_HEATER_DHW_KEY,)

# ------------------------------------------------------------------- derived sensors
# Sensors that are calculated from registers that are polled anyway (no extra Modbus reads). Their keys are
# part of the entity contract. ``cop`` lives in the main device; the overall values live in the device of the
# circuit they describe (see ``area_of``).


@dataclass(frozen=True)
class DerivedSensor:
    """A sensor that is the quotient of two existing registers."""

    key: str
    name_de: str
    name_en: str
    thermal: str  # key of the thermal register (power or energy)
    electric: str  # key of the electric register (power or energy)
    cumulative: bool  # True: energy counters (overall value), False: instantaneous power


DERIVED_SENSORS: tuple[DerivedSensor, ...] = (
    DerivedSensor("cop", "COP", "COP", "compressor_thermal_power", "electric_power", cumulative=False),
    DerivedSensor("cop_heating", "COP gesamt", "COP overall", "energy_th_heating", "energy_el_heating", True),
    DerivedSensor("cop_dhw", "COP gesamt", "COP overall", "energy_th_dhw", "energy_el_dhw", True),
)
DERIVED_SENSOR_KEYS: tuple[str, ...] = tuple(sensor.key for sensor in DERIVED_SENSORS)

# The following limits are a design choice of this integration, NOT a register fact and not documented by the
# manufacturer. They only decide when a calculated COP is shown as "unknown" instead of a misleading number.
# The electric power register has a resolution of 100 W, so below this value the quotient is mostly rounding noise.
COP_MIN_ELECTRIC_POWER_W = 200.0
# Overall values need some electric energy before the quotient says anything (e.g. a fresh counter).
COP_MIN_ELECTRIC_ENERGY_KWH = 1.0
# Heat pumps do not reach more than this; anything above is a measurement or timing artefact.
COP_MAX_PLAUSIBLE = 12.0


def _plausible(cop: float) -> float | None:
    return cop if 0 < cop <= COP_MAX_PLAUSIBLE else None


def instantaneous_cop(thermal_w: float | None, electric_w: float | None) -> float | None:
    """Thermal power / electric power, ``None`` when the value cannot be trusted.

    Unknown for missing values, electric power below ``COP_MIN_ELECTRIC_POWER_W``, thermal power of zero or
    below (e.g. defrost, where the thermal power is negative) and implausibly high results.
    """
    if thermal_w is None or electric_w is None:
        return None
    if electric_w < COP_MIN_ELECTRIC_POWER_W or thermal_w <= 0:
        return None
    return _plausible(thermal_w / electric_w)


def overall_cop(
    thermal_kwh: float | None,
    electric_kwh: float | None,
    previous: tuple[float, float] | None = None,
) -> float | None:
    """Thermal energy / electric energy of two counters, ``None`` when the value cannot be trusted.

    ``previous`` is the (thermal, electric) pair of the reading before. If a counter went backwards since then
    (reset or replaced controller), the quotient mixes two different histories and is unknown for this reading.
    """
    if thermal_kwh is None or electric_kwh is None:
        return None
    if previous is not None and (thermal_kwh < previous[0] or electric_kwh < previous[1]):
        return None
    if electric_kwh < COP_MIN_ELECTRIC_ENERGY_KWH or thermal_kwh <= 0:
        return None
    return _plausible(thermal_kwh / electric_kwh)


# ---------------------------------------------------------------------- devices
# Entities are grouped into sub-devices like the menus of the Luxtronik controller. The main device
# ("heat pump") keeps everything that is not listed here. Moving an entity between devices never changes
# its entity ID.
AREAS: tuple[str, ...] = ("heating", "hot_water", "cooling", "pool")

# The "configured"/"released" flags stay on the main device: they tell whether cooling or a pool exists at all.
_COOLING_KEYS = frozenset({"cooling_block", "cooling_status", "energy_el_cooling", "energy_th_cooling"})
_POOL_KEYS = frozenset({"pool_block", "pool_status", "energy_el_pool", "energy_th_pool"})
_HOT_WATER_KEYS = frozenset(
    {"circulation", "extra_dhw", "hot_water_status", "energy_el_dhw", "energy_th_dhw", "hours_dhw", "cop_dhw"}
)
_HEATING_KEYS = frozenset(
    {
        "heating_limit",
        "heating_block",
        "heating_status",
        "room",
        "energy_el_heating",
        "energy_th_heating",
        "hours_heating",
        "cop_heating",
    }
)


def area_of(key: str) -> str | None:
    """Sub-device of an entity key, ``None`` for the main heat pump device."""
    if key in _COOLING_KEYS or (key.startswith("cfg_mk") and "_cool_" in key):
        return "cooling"
    if key in _POOL_KEYS:
        return "pool"
    if key in _HOT_WATER_KEYS or key.startswith(("dhw", "cfg_dhw")):
        return "hot_water"
    if key in _HEATING_KEYS or key.startswith(
        ("cfg_heating", "cfg_overall", "cfg_mk", "mk1_", "mk2_", "mk3_")
    ):
        return "heating"
    return None
