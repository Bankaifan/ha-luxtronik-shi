"""Register map of the Luxtronik Smart Home Interface (SHI) via Modbus/TCP.

The map covers every documented register of the SHI (firmware 3.90 ... 3.92) that was
verified on a running installation (alpha innotec LWDV 91-1/3, firmware 3.92.3).
Everything that can be written through Modbus is exposed as number, select or switch; the two trigger
registers (circulation run, extra hot water) as button plus a "running" binary sensor.

Naming scheme of the keys: they are identical to the suffix of the entity IDs
that the former YAML ``modbus:`` configuration produced (``lwdv_shi_<key>``),
which makes a migration of existing automations and dashboards easy.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

RegKind = Literal["input", "holding", "discrete"]
DType = Literal["uint16", "int16", "uint32", "int32"]
# The SHI word for "not available" (const.SHI_NOT_AVAILABLE; this module has no package imports, tools load it
# standalone, tests pin that both agree).
_NOT_AVAILABLE_WORD = 0x7FFF
Platform = Literal["sensor", "binary_sensor", "switch", "button", "number", "select", "internal"]


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
    # Enumerations: the raw value is the index into this tuple (select and enum sensors). The same option may
    # appear at several positions when the firmware treats those raw values alike (``_LEVELS``: raw 1 and 2 both
    # mean "increased"); a write uses the first position.
    options: tuple[str, ...] | None = None
    # Selects only: options that exist as raw values but are not offered for writing because the firmware does
    # not implement them (``cfg_overall_mode``: ``setpoint``). Read back, the select shows no state for them.
    unselectable: frozenset[str] = frozenset()
    # Where the register facts come from (shown in docs/registers.md). ``None`` = no source recorded (open).
    source: str | None = None
    # Writable holdings only: the raw word the firmware resets the register to at boot, on watchdog expiry and
    # after a write outside its range (FW 3.92.3 full analysis, section 3.4; proven). ``None`` = no fixed default
    # (10060 is a persisted controller parameter and reverts to its persisted value).
    reset_default: int | None = None

    @property
    def width(self) -> int:
        """Number of 16 bit registers occupied."""
        return 2 if self.dtype in ("uint32", "int32") else 1

    @property
    def unique_key(self) -> str:
        """Key used for unique IDs (raw values need the address)."""
        return self.key


def decode(reg: Register, words: list[int]) -> float | int:
    """Convert raw register words into the physical value."""
    if reg.dtype in ("uint32", "int32"):
        # MultiByte registers of the SHI: high word at the lower address (FW 3.92.3 full analysis, 1.1; proven).
        raw = (words[0] << 16) | words[1]
        if reg.dtype == "int32" and raw >= 0x80000000:
            raw -= 0x100000000
    elif reg.dtype == "int16":
        raw = words[0] - 0x10000 if words[0] >= 0x8000 else words[0]
    else:
        raw = words[0]
    if reg.scale == 1.0:
        return raw
    return round(raw * reg.scale, 3)


def usable(key: str, value: float | None) -> float | None:
    """The decoded value of a 16 bit register, ``None`` if missing or the "not available" marker 0x7FFF.

    Values arrive scaled, so the marker of a scaled register is ``0x7FFF * scale`` (3276.7 for 0.1 K).
    """
    if value is None:
        return None
    reg = BY_KEY[key]
    if reg.width == 1 and value == (_NOT_AVAILABLE_WORD if reg.scale == 1.0 else round(_NOT_AVAILABLE_WORD * reg.scale, 3)):
        return None
    return value


def reports_not_available(reg: Register) -> bool:
    """Whether a plain sensor shows the "not available" word 0x7FFF as unavailable instead of as a number.

    The SHI answers 0x7FFF for every register whose availability check fails (docs/firmware-3.92.3-shi-analysis.md,
    proven). It is applied only where a measured quantity can never legitimately read 0x7FFF: the 16 bit input
    temperatures and the error number. Counters, raw values (low words of 32 bit counters) and enumerations
    are left alone (enumerations already show no state for a value outside their options).
    """
    return (
        reg.platform == "sensor"
        and reg.kind == "input"
        and reg.width == 1
        and reg.options is None
        and (reg.device_class == "temperature" or reg.key == "error_number")
    )


def encode_int16(value: float, scale: float) -> int:
    """Convert a physical value into a raw 16 bit word (two's complement)."""
    return int(round(value / scale)) % 0x10000


def raw_in_range(reg: Register, raw: int) -> bool:
    """Whether a raw holding word is inside the range the firmware accepts for ``reg``.

    The SHI firmware answers a write outside the range of a register with a normal Modbus acknowledgement but
    resets the register to its default instead of storing the value (FW 3.92.3 full analysis, 1.4; proven). So
    nothing outside the range may ever be sent. Numbers: ``min_value`` ... ``max_value`` in physical units
    (negative values as two's complement). Selects: an index of ``options`` that is not ``unselectable``.
    Switches and buttons (triggers): 0 or 1 (the firmware treats every value other than 0 as 1, but only 0 and 1
    are written). Holdings without a range accept every word.
    """
    if reg.platform == "select" and reg.options is not None:
        return 0 <= raw < len(reg.options) and reg.options[raw] not in reg.unselectable
    if reg.platform in ("switch", "button"):
        return raw in (0, 1)
    if reg.min_value is None or reg.max_value is None:
        return True
    value = decode(reg, [raw])
    return reg.min_value <= value <= reg.max_value


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
# The heat quantity counters are signed in the firmware (MultiByte INT32, full analysis 2.2; proven), the electric
# counters unsigned. A negative total is not expected; the type only decides how a word >= 0x8000 is read.
_ENERGY_TH = {**_ENERGY, "dtype": "int32"}
_HOURS = {
    "unit": "h",
    "device_class": "duration",
    "state_class": "total_increasing",
    "dtype": "uint32",
    "precision": 0,
    "every": 10,
}
_SETTING = {"config": True, "every": 2}
# Control mode of a circuit (python-luxtronik ``ControlMode``, FW 3.92.3 full analysis, 3.1; proven). Raw 0 is
# "no influence": the controller uses its own values (heating curve, time programme). It does NOT switch the
# circuit off, so the option is called ``no_influence`` (up to 0.17.x ``off``, which misled automations). 1 =
# setpoint (replaces the controller's target), 2 = offset (controller's target plus the offset register), 3 = level
# (controller's target corrected by the level parameter).
_MODES = ("no_influence", "setpoint", "offset", "level")
CONTROL_MODES: tuple[str, ...] = _MODES
MODE_NO_INFLUENCE = "no_influence"
MODE_SETPOINT = "setpoint"
# Level of a circuit (FW 3.92.3 full analysis, 3.1; proven): 0 normal, 1 and 2 both raise the target by the
# controller parameter "Erhöhung <circuit>" (the same parameter for both, so raw 2 IS "increased"), 3 lowers it by
# the parameter "Absenkung <circuit>". The amounts are the device parameters 1187 ... 1198 (menu "Offsets",
# -20 ... +20 K in 0.5 K steps), not anything the SHI can read or write. Raw 1 and 2 therefore share one option;
# the select offers ``increased`` once and writes raw 1 (python-luxtronik's ``Increased2`` is not a separate value
# in the firmware; the option ``increased2`` of 0.17.x is gone).
_LEVELS = ("normal", "increased", "increased", "decreased")
LEVEL_OPTIONS: tuple[str, ...] = tuple(dict.fromkeys(_LEVELS))
# The overall group (10065 ... 10067) takes precedence over the heating and the mixing circuit modes; its mode 1
# (setpoint) is not implemented in the firmware and acts like 0 (full analysis, 3.1; proven). The raw values are
# the same as CONTROL_MODES; ``setpoint`` is ``unselectable`` there (not offered, shown as no state when read).
OVERALL_MODE_KEY = "cfg_overall_mode"
OVERALL_UNSELECTABLE: frozenset[str] = frozenset({MODE_SETPOINT})
# The two trigger registers (buttons; see their entries in REGISTERS and const.TRIGGER_KEYS).
CIRCULATION_KEY = "circulation"
EXTRA_DHW_KEY = "extra_dhw"
# Raw defaults of the writable holdings (full analysis, 3.4; proven): setpoints 350 / 400 / 200 (0.1 degC), the power
# limit 300 (0.1 kW), everything else 0. These are also the values a register reads after a watchdog expiry, a
# reboot and a write outside its range.
_SETPOINT_DEFAULT = 350
_DHW_SETPOINT_DEFAULT = 400
_COOL_SETPOINT_DEFAULT = 200
_POWER_LIMIT_DEFAULT = 300
_FW = "proven: firmware V3.92.3 (docs/firmware-3.92.3-shi-full-analysis.md)"
# State of a function (heating, hot water, cooling, pool), python-luxtronik ``ModeStatus`` (inputs 3, 4, 6, 7,
# range 0 ... 3): 0 disabled, 1 no request, 2 requested but not running yet, 3 running. A value outside the
# documented range is shown as "Unknown (<n>)": the keys ``unknown_4`` ... ``unknown_15`` exist for that, nothing
# is known about them. Larger raw values read as unknown.
_STATUS_UNKNOWN_FROM = 4
_STATUS_UNKNOWN_TO = 15
FUNCTION_STATUS = ("disabled", "no_request", "requested", "running") + tuple(
    f"unknown_{n}" for n in range(_STATUS_UNKNOWN_FROM, _STATUS_UNKNOWN_TO + 1)
)
# Operating state of the heat pump (input 10002, python-luxtronik ``OperationMode``): 0 heating, 1 hot water,
# 2 swimming pool / solar, 3 utility lock (EVU), 4 defrost, 5 no request (idle; up to 0.17.x the option was
# called ``off``, which it is not: the heat pump is ready and waits for a demand), 6 heating with the external
# source, 7 cooling.
_OPERATING_MODES = (
    "heating",
    "hot_water",
    "pool",
    "evu_lock",
    "defrost",
    "no_request",
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


def _number(key, address, de, en, *, lo, hi, step, unit, signed=False, reset_default=0, source=_FW, **kw) -> Register:
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
        reset_default=reset_default,
        source=source,
        **{**_SETTING, **kw},
    )


def _select(key, address, de, en, options, source=_FW, **kw) -> Register:
    return _h(
        key, address, de, en, platform="select", options=options, reset_default=0, source=source, **{**_SETTING, **kw}
    )


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
    # Parameters 87 (Einst_TRBegr) and 979: the firmware clamps the heating setpoint 10001 to [10104, 10103]
    # (full analysis, 3.1; proven).
    _temp_in(
        "return_limit", 10103, "Temperatur: Rücklauf-Begrenzung", "Temperature: return limit", every=10,
        source="proven: firmware parameter 87 Einst_TRBegr; upper clamp of the heating setpoint",
    ),
    _temp_in(
        "return_min_target",
        10104,
        "Temperatur: Rücklauf-Soll Minimum",
        "Temperature: return target minimum",
        every=10,
        source="proven: firmware parameter 979; lower clamp of the heating setpoint and target while heating is blocked",
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
    # t0/0x57 "Heating demand border": the effective request threshold (return target minus the hysteresis
    # Einst_HRHyst_akt), tracked by the firmware, not a parameter (full analysis, 2.2; proven). Key unchanged.
    _temp_in(
        "heating_demand_border", 10107, "Anforderungsgrenze", "Demand border", every=10,
        source="proven: firmware t0/0x57 'Heating demand border' (effective target minus hysteresis)",
    ),
    _s("outside", 10108, "Temperatur: Außen", "Temperature: outside", dtype="int16", scale=0.1, **_TEMP),
    _s("dhw", 10120, "Temperatur", "Temperature", dtype="int16", scale=0.1, **_TEMP),
    _s("dhw_target", 10121, "Soll", "Target", scale=0.1, every=2, **_TEMP),
    # Fixed firmware constant (300 = 30.0 degC, SHI analysis), not a measurement: disabled for new installations.
    _temp_in("dhw_min", 10122, "Minimum", "Minimum", every=10, enabled_default=False),
    _temp_in(
        "dhw_max", 10123, "Maximum", "Maximum", every=10,
        source="proven: firmware parameter 973 Einst_BW_max; upper limit of every hot water target",
    ),
    # t0/0x58 "DHW Demand border", analogous to 10107 (full analysis, 2.2; proven). Key unchanged.
    _temp_in(
        "dhw_demand_border", 10124, "Anforderungsgrenze", "Demand border", every=10,
        source="proven: firmware t0/0x58 'DHW Demand border' (effective target minus hysteresis)",
    ),
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
        enabled_default=False,  # fixed firmware constant (20), not a measurement
        every=30,
    ),
    _s(
        "min_runtime_minutes",
        10204,
        "Anlage: Mindestlaufzeit",
        "System: minimum runtime",
        unit="min",
        diagnostic=True,
        enabled_default=False,  # fixed firmware constant (20), not a measurement
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
    _s("heating_status", 10003, "Status", "Status", options=FUNCTION_STATUS),
    _s("hot_water_status", 10004, "Status", "Status", options=FUNCTION_STATUS),
    _s("cooling_status", 10006, "Status", "Status", diagnostic=True, every=2, options=FUNCTION_STATUS),
    _s("pool_status", 10007, "Status", "Status", diagnostic=True, every=2, options=FUNCTION_STATUS),
    # ----------------------------------------------------------------- counters
    _s("energy_el_total", 10310, "Energie: Strom gesamt", "Energy: electric total", **_ENERGY),
    _s("energy_el_heating", 10312, "Energie: Strom", "Energy: electric", **_ENERGY),
    _s("energy_el_dhw", 10314, "Energie: Strom", "Energy: electric", **_ENERGY),
    _s("energy_th_total", 10320, "Energie: Wärme gesamt", "Energy: thermal total", **_ENERGY_TH),
    _s("energy_th_heating", 10322, "Energie: Wärme", "Energy: thermal", **_ENERGY_TH),
    _s("energy_th_dhw", 10324, "Energie: Wärme", "Energy: thermal", **_ENERGY_TH),
    # Operating hour counters: parameters 668 / 728 / 729 (Zaehler_BetrZeitWP/Hz/BW), seconds / 3600 on the wire
    # (full analysis, 2.2; proven).
    _s("hours_hp", 10404, "Betriebsstunden: Verdichter", "Operating hours: compressor", source=_FW, **_HOURS),
    _s("hours_heating", 10406, "Betriebsstunden", "Operating hours", source=_FW, **_HOURS),
    _s("hours_dhw", 10408, "Betriebsstunden", "Operating hours", source=_FW, **_HOURS),
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
        step=0.1,
        unit="°C",
        reset_default=_SETPOINT_DEFAULT,
    ),
    _number(
        "cfg_heating_offset",
        10002,
        "Heizkurven-Anhebung",
        "Curve offset",
        lo=-20,
        hi=20,
        step=0.1,
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
        step=0.1,
        unit="°C",
        reset_default=_DHW_SETPOINT_DEFAULT,
    ),
    _number(
        "cfg_dhw_offset",
        10007,
        "Anhebung",
        "Offset",
        lo=-20,
        hi=20,
        step=0.1,
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
        step=0.1,
        unit="°C",
        reset_default=_SETPOINT_DEFAULT,
    ),
    _number(
        "cfg_mk1_offset",
        10012,
        "Mischkreis 1: Anhebung",
        "Mixing circuit 1: offset",
        lo=-5,
        hi=5,
        step=0.1,
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
        source="likely: firmware V3.92.3 enum; consumer not traced (docs/firmware-3.92.3-shi-full-analysis.md)",
    ),
    _number(
        "cfg_mk1_cool_setpoint",
        10016,
        "Mischkreis 1: Sollwert",
        "Mixing circuit 1: setpoint",
        lo=5,
        hi=25,
        step=0.1,
        unit="°C",
        reset_default=_COOL_SETPOINT_DEFAULT,
        enabled_default=False,
        source="likely: firmware V3.92.3 range and default; consumer not traced (docs/firmware-3.92.3-shi-full-analysis.md)",
    ),
    _number(
        "cfg_mk1_cool_offset",
        10017,
        "Mischkreis 1: Anhebung",
        "Mixing circuit 1: offset",
        lo=-5,
        hi=5,
        step=0.1,
        unit="K",
        signed=True,
        enabled_default=False,
        source="likely: firmware V3.92.3 range; consumer not traced (docs/firmware-3.92.3-shi-full-analysis.md)",
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
        reset_default=_POWER_LIMIT_DEFAULT,
    ),
    # Overall heating (10065-10067, firmware 3.92.0 or later): proven by the firmware (full analysis, 3.1). A mode
    # other than 0 takes precedence over the heating mode (10000) AND the mixing circuit modes; mode 1 (setpoint) is
    # not implemented there and acts like 0, so the select does not offer it (``unselectable``). The level uses
    # the parameters "Hz. allg." 1187/1188. The offset range is -5.0 ... +5.0 K (not -20 ... 20 as python-luxtronik
    # lists: a larger value resets the register to 0). The entities stay disabled by default (owner decision): an
    # active overall mode silently overrides what an optimizer writes to the heating circuit.
    _select(
        OVERALL_MODE_KEY, 10065, "Gesamt: Betriebsart", "Overall: mode", _MODES, enabled_default=False,
        unselectable=OVERALL_UNSELECTABLE,
    ),
    _number(
        "cfg_overall_offset",
        10066,
        "Gesamt: Anhebung",
        "Overall: offset",
        lo=-5,
        hi=5,
        step=0.1,
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
    # Range is not a register fact: 20-40 C are plausible room temperatures (owner decision). The register binds the
    # persisted parameter 1148 (full analysis, 3.3), so it has no fixed default: a watchdog expiry restores the
    # persisted value, and the firmware range (the parameter's own bounds) is open.
    _number(
        "cfg_room_setpoint",
        10060,
        "Raumtemperatur-Sollwert",
        "Room temperature setpoint",
        lo=20,
        hi=40,
        step=0.5,
        unit="°C",
        reset_default=None,
        source="proven: firmware V3.92.3 writable parameter 1148; range open (owner decision 20-40)",
    ),
    # ------------------------------------------------------------------ firmware
    # Firmware version a.b.c (python-luxtronik ``version``, index 400, count 3, FullVersion = "a.b.c"; the
    # reference installation reads 3 / 92 / 3 = 3.92.3, see docs/firmware-3.92.3-shi-analysis.md). Read only to
    # compose the ``firmware_version`` sensor; these three have no entities of their own ("internal").
    _s("fw_version_major", 10400, "Firmware: Version 1", "Firmware: version part 1", platform="internal", every=120),
    _s("fw_version_minor", 10401, "Firmware: Version 2", "Firmware: version part 2", platform="internal", every=120),
    _s("fw_version_patch", 10402, "Firmware: Version 3", "Firmware: version part 3", platform="internal", every=120),
    # ------------------------------------------------- switches (blocks, holding)
    _h("heating_block", 10050, "Sperren", "Block", platform="switch", reset_default=0, source=_FW),
    _h("dhw_block", 10051, "Sperren", "Block", platform="switch", reset_default=0, source=_FW),
    _h("cooling_block", 10052, "Sperren", "Block", platform="switch", reset_default=0, source=_FW),
    _h("pool_block", 10053, "Sperren", "Block", platform="switch", reset_default=0, source=_FW),
    # Circulation pump and extra hot water (firmware 3.92.0 or later). Both are triggers (full analysis, 3.2 and
    # 3.3; proven): 10070 starts a circulation run (run and pause times of the controller, Einst_Zirk_Ein/Aus) and
    # is set back to 0 by the firmware once no run is active; 10071 starts extra hot water for the controller's
    # duration (parameter 1147, shown by ``extra_dhw_duration``) and is set back to 0 by the firmware when the timer
    # runs out. Up to 0.17.x both were switches, which suggested a state the user holds; a trigger is a button
    # (press = write 1, read-back 0 is the normal end; ``TRIGGER_ACTIONS`` add the stop buttons, press = write 0).
    # Running state: extra hot water is the binary sensor ``extra_dhw_running`` on 10071; circulation is the pump
    # output ``pump_circulation`` (ZIP), which also shows runs of the time program. See const.TRIGGER_KEYS.
    _h(
        CIRCULATION_KEY,
        10070,
        "Zirkulation: Lauf starten",
        "Circulation: start run",
        platform="button",
        reset_default=0,
        source=_FW + "; trigger, reset to 0 by the firmware once no run is active",
    ),
    _h(
        EXTRA_DHW_KEY, 10071, "Extra: starten", "Extra: start", platform="button", reset_default=0,
        source=_FW + "; trigger, reset to 0 by the firmware when the timer ends",
    ),
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
    # t0/0x67 "TVL calc max": the calculated maximum flow temperature (return target + moving average of the
    # flow-return spread, 0x0019ac68), firmware text "TVL calc max", visibility 0x165; INT16, 0.1 degC (full
    # analysis, 2.2; proven, measured 25.7 degC at a return target of 20.0). Whether the controller uses it as a
    # setpoint or as an upper limit is open. Was ``raw_10113`` up to 0.17.x (RENAMED_KEYS: the entity ID stays).
    _temp_in(
        "flow_calc_max",
        10113,
        "Vorlauf: berechnetes Maximum (TVL calc max)",
        "Flow: calculated maximum (TVL calc max)",
        diagnostic=True,
        enabled_default=False,
        every=4,
        source="proven: firmware t0/0x67 'TVL calc max' (return target + moving average of the flow-return spread); measured",
    ),
)


_COOL_LIKELY = "likely: firmware V3.92.3 range and default; consumer not traced (docs/firmware-3.92.3-shi-full-analysis.md)"


def _mixing_circuit_holdings(n: int) -> tuple[Register, ...]:
    """Holdings of mixing circuit 2 or 3: same layout as circuit 1, ranges and defaults from the firmware."""
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
            step=0.1,
            unit="°C",
            reset_default=_SETPOINT_DEFAULT,
        ),
        _number(
            f"{k}_offset",
            base + 2,
            f"{de}: Anhebung",
            f"{en}: offset",
            lo=-5,
            hi=5,
            step=0.1,
            unit="K",
            signed=True,
        ),
        _select(f"{k}_level", base + 3, f"{de}: Stufe", f"{en}: level", _LEVELS),
        _select(f"{k}_cool_mode", base + 5, f"{de}: Betriebsart", f"{en}: mode", _MODES, source=_COOL_LIKELY),
        _number(
            f"{k}_cool_setpoint",
            base + 6,
            f"{de}: Sollwert",
            f"{en}: setpoint",
            lo=5,
            hi=25,
            step=0.1,
            unit="°C",
            reset_default=_COOL_SETPOINT_DEFAULT,
            source=_COOL_LIKELY,
        ),
        _number(
            f"{k}_cool_offset",
            base + 7,
            f"{de}: Anhebung",
            f"{en}: offset",
            lo=-5,
            hi=5,
            step=0.1,
            unit="K",
            signed=True,
            source=_COOL_LIKELY,
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
    _s("energy_th_cooling", 10326, "Energie: Wärme", "Energy: thermal", **_ENERGY_TH),
    _s("energy_th_pool", 10328, "Energie: Wärme", "Energy: thermal", **_ENERGY_TH),
)
REGISTERS = REGISTERS + ADDED_IN_0_4

# Resolved by the firmware analysis of V3.92.3 (docs/firmware-3.92.3-shi-full-analysis.md, section 2.2; proven).
# The ``raw_<address>`` sensors that used to show the same addresses word by word (raw_10410/10411, raw_10416/10417,
# raw_10500 ... raw_10502) were removed in 0.18.0 (REMOVED_KEYS): a proven value has one entity, not a disabled
# twin. 10412 (operating hours pool, divisor 7200 instead of 3600) gets no counter entity: the firmware most likely
# shows half the hours on the wire, which is not proven, so it stays a raw value.
_EXTRA_DHW = "proven: firmware V3.92.3 ExtraDHW (docs/firmware-3.92.3-shi-full-analysis.md)"
RESOLVED_IN_0_17: tuple[Register, ...] = (
    # Zaehler_BetrZeitKue, parameter 730; BSTD_Solar, parameter 882 (visibility ID_Visi_Solar).
    _s("hours_cooling", 10410, "Betriebsstunden", "Operating hours", source=_FW, **_HOURS),
    _s("hours_solar", 10416, "Betriebsstunden: Solar", "Operating hours: solar", source=_FW, **_HOURS),
    # Extra hot water: setpoint (parameter 1146, 0.1 degC), duration (parameter 1147, seconds / 60 on the wire) and
    # the remaining time of a running extra hot water (ExtraDHW::timer, seconds / 60 on the wire).
    _temp_in(
        "extra_dhw_setpoint", 10500, "Extra: Sollwert", "Extra: setpoint", every=10, diagnostic=True,
        source=_EXTRA_DHW,
    ),
    _s(
        "extra_dhw_duration", 10501, "Extra: Dauer", "Extra: duration", dtype="int16", unit="min",
        device_class="duration", every=10, diagnostic=True, source=_EXTRA_DHW,
    ),
    _s(
        "extra_dhw_remaining", 10502, "Extra: Restlaufzeit", "Extra: remaining time", dtype="int16", unit="min",
        device_class="duration", state_class="measurement", every=2, source=_EXTRA_DHW,
    ),
)
REGISTERS = REGISTERS + RESOLVED_IN_0_17

# Keys that were renamed: old key -> new key (same platform, same address). ``async_setup_entry`` moves the
# registry entries over, so the entity IDs stay. The old keys are no longer in the entity contract fixture;
# ``tests/test_contract.py`` checks that each new key exists on the platform of the old one.
RENAMED_KEYS: dict[str, str] = {
    "raw_10109": "outside_temp_average",
    "raw_10110": "heat_source_input",
    "raw_10112": "max_flow_temp",
    "raw_10113": "flow_calc_max",
    # 0.18.0: named after what they are (the demand border of heating and hot water), not a "limit".
    "heating_limit": "heating_demand_border",
    "dhw_limit": "dhw_demand_border",
    # 0.18.0: discrete 10000/10001 mean "equipped AND the controller's mode is not off", not just "equipped".
    "cap_heating": "heating_available",
    "cap_hot_water": "hot_water_available",
}

# Raw values are disabled by default; handy for analysis and for reverse engineering of new firmware versions.
# The proven digital outputs and inputs 10350-10356, 10360 and 10361 were raw values up to 0.17.x; since 0.18.0
# they are only the binary sensors ``OUTPUT_FLAGS`` (REMOVED_KEYS).

# Further undocumented values of python-luxtronik (``unknown_input_*`` and ``unknown_holding_60``, "function
# unknown"), added after 0.8.2. They are polled rarely, because nobody knows what they mean yet, and entries
# without an equipment option (created before 0.3.0) do not get them (see ``_LEGACY_EXCLUDED``).
RAW_INPUT_ADDRESSES_ADDED: tuple[int, ...] = (
    10412,
    10413,
)
# Holding registers that only python-luxtronik lists as read-only and with unknown function. Read, never written.
# (10060 was briefly here but is the writable RBE room-temperature setpoint, now exposed as cfg_room_setpoint.)
RAW_HOLDING_ADDRESSES_ADDED: tuple[int, ...] = ()


# Raw values whose meaning is proven by the firmware (V3.92.3, bin/Controller; function addresses in
# docs/firmware-3.92.3-register-meanings.md) and confirmed by a measurement on the reference installation where the
# equipment exists. They keep the key ``raw_<address>`` and stay disabled by default (diagnostic); only the display
# name, unit and scale are filled in. Other raw values stay open.
RAW_MEANINGS: dict[int, dict] = {
    # Operating hour counter of the pool (32 bit, two words): Zaehler_BetrZeitSW with divisor 7200 instead of the
    # 3600 of every other hour counter: the wire value is most likely hours / 2 (likely, not measured: the
    # reference installation has no pool). Stays a raw value until a pool installation confirms the factor.
    10412: {
        "name_de": "Betriebsstunden Schwimmbad: Wort 1 (Teiler 7200)",
        "name_en": "Operating hours pool: word 1 (divisor 7200)",
        "source": "proven: firmware Zaehler_BetrZeitSW; divisor 7200 (likely hours / 2, not measured)",
    },
    10413: {
        "name_de": "Betriebsstunden Schwimmbad: Wort 2 (Teiler 7200)",
        "name_en": "Operating hours pool: word 2 (divisor 7200)",
        "source": "proven: firmware Zaehler_BetrZeitSW; divisor 7200 (likely hours / 2, not measured)",
    },
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
RAW_REGISTERS: tuple[Register, ...] = _RAW_ADDED

# Capability flags (discrete inputs) – tell which parts the installation has. 10000 and 10001 are more than that:
# they read 1 only while the part is equipped AND the controller's operating mode of it is not "off" (Ba_Hz_akt != 4,
# Ba_Bw_akt != 4; full analysis, 2.3; proven), so their keys say "available" (``cap_heating`` / ``cap_hot_water`` up
# to 0.17.x, RENAMED_KEYS).
HEATING_AVAILABLE_KEY = "heating_available"
HOT_WATER_AVAILABLE_KEY = "hot_water_available"
CAPABILITIES: tuple[Register, ...] = tuple(
    Register(
        key=key,
        address=address,
        kind="discrete",
        name_de=de,
        name_en=en,
        platform="binary_sensor",
        diagnostic=True,
        every=10,
    )
    for address, key, de, en in (
        (
            10000, HEATING_AVAILABLE_KEY, "Heizen verfügbar (ausgestattet, Betriebsart nicht Aus)",
            "Heating available (equipped, mode not off)",
        ),
        (
            10001, HOT_WATER_AVAILABLE_KEY, "Warmwasser verfügbar (ausgestattet, Betriebsart nicht Aus)",
            "Hot water available (equipped, mode not off)",
        ),
        *(
            (address, f"cap_{suffix}", f"Ausstattung: {de}", f"Equipment: {en}")
            for address, suffix, de, en in (
                (10002, "cooling", "Kühlen", "cooling"),
                (10003, "pool", "Pool", "pool"),
                # 10004: solar equipment (visibility ID_Visi_Solar; full analysis, 2.3; proven). Added in 0.17.0.
                (10004, "solar", "Solar", "solar"),
                (10005, "room_controller", "Raumregler", "room controller"),
                (10006, "mk1_heating", "Mischkreis 1 Heizen", "mixing circuit 1 heating"),
                (10007, "mk1_cooling", "Mischkreis 1 Kühlen", "mixing circuit 1 cooling"),
                (10008, "mk2_heating", "Mischkreis 2 Heizen", "mixing circuit 2 heating"),
                (10009, "mk2_cooling", "Mischkreis 2 Kühlen", "mixing circuit 2 cooling"),
                (10010, "mk3_heating", "Mischkreis 3 Heizen", "mixing circuit 3 heating"),
                (10011, "mk3_cooling", "Mischkreis 3 Kühlen", "mixing circuit 3 cooling"),
            )
        ),
    )
)

# Limits and minimum/maximum values: rarely needed day to day, so they live in the
# "Diagnose" section of the device page. Only the entity category changes, never the key.
_SECONDARY_KEYS = frozenset(
    {
        "return_external",
        "return_limit",
        "return_min_target",
        "heating_demand_border",
        "dhw_min",
        "dhw_max",
        "dhw_demand_border",
        "mk1_flow_min",
        "mk1_flow_max",
        "mk2_flow_min",
        "mk2_flow_max",
        "mk3_flow_min",
        "mk3_flow_max",
    }
)
REGISTERS = tuple(replace(reg, diagnostic=True) if reg.key in _SECONDARY_KEYS else reg for reg in REGISTERS)

# Binary sensors for the digital outputs and inputs of the controller whose meaning the firmware analysis proves
# (V3.92.3, bin/Controller; variable names of the firmware, outputs at 0x0008bef8, inputs at 0x0009833c). Up to
# 0.17.x they shared their register with a ``raw_<address>`` sensor; since 0.18.0 they are the only entity of their
# register (REMOVED_KEYS). They poll as the raw values did (every 4th cycle, FP2/FP3 every 30th). The level is shown
# as read (on = 1). For the EVU inputs only the name is proven; that 1 means "released" is inferred from one
# measured state, so they stay disabled and say "level".


def _flag(key: str, address: int, de: str, en: str, every: int, source: str, **kw) -> Register:
    return Register(
        key=key,
        address=address,
        kind="input",
        name_de=de,
        name_en=en,
        platform="binary_sensor",
        every=every,
        source=source,
        **kw,
    )


OUTPUT_FLAGS: tuple[Register, ...] = (
    _flag(
        "pump_heating", 10354, "Pumpe: Heizung (HUP)", "Pump: heating (HUP)", 4,
        "proven: firmware HUPout (t0/0x20); measured", device_class="running",
    ),
    _flag(
        "pump_hot_water", 10355, "Pumpe: Warmwasser (BUP)", "Pump: hot water (BUP)", 4,
        "proven: firmware BUPout (t0/0x44); measured", device_class="running",
    ),
    _flag(
        "pump_circulation", 10356, "Pumpe: Zirkulation (ZIP)", "Pump: circulation (ZIP)", 4,
        "proven: firmware ZIPout (t0/0x48); measured", device_class="running",
    ),
    _flag(
        "output_vbo", 10350, "Ausgang: VBO", "Output: VBO", 4,
        "proven: firmware VBOout (t0/0x45); measured: runs with the compressor", diagnostic=True,
    ),
    _flag(
        "output_fp1", 10351, "Ausgang: FP1", "Output: FP1", 4,
        "proven: firmware FP1out (t0/0x6d); measured: follows the heating pump", diagnostic=True,
    ),
    _flag(
        "output_fp2", 10352, "Ausgang: FP2", "Output: FP2", 30,
        "proven: firmware FP2out (t0/0x4c); not measured (no second circuit)",
        diagnostic=True, enabled_default=False,
    ),
    _flag(
        "output_fp3", 10353, "Ausgang: FP3", "Output: FP3", 30,
        "proven: firmware FP3out (t0/0x4d); not measured (no third circuit)",
        diagnostic=True, enabled_default=False,
    ),
    _flag(
        "input_evu", 10360, "Eingang: EVU (Pegel 1 = an)", "Input: EVU (level 1 = on)", 4,
        "proven: firmware EVUin (t0/0x2a); measured: 1 while the utility lock is released",
        diagnostic=True, enabled_default=False,
    ),
    _flag(
        "input_evu2", 10361, "Eingang: EVU 2 (Pegel 1 = an)", "Input: EVU 2 (level 1 = on)", 4,
        "proven: firmware EVU2in (t0/0x2b); measured: 0 on the reference installation",
        diagnostic=True, enabled_default=False,
    ),
)

ALL_REGISTERS: tuple[Register, ...] = REGISTERS + RAW_REGISTERS + OUTPUT_FLAGS + CAPABILITIES

# Keys of undocumented raw values (shown with a generic "Raw value: <address>" name).
# Raw values without a known meaning (they share the generic "Raw value: <address>" entity name).
RAW_KEYS: frozenset[str] = frozenset(reg.key for reg in RAW_REGISTERS if reg.address not in RAW_MEANINGS)
_LEGACY_EXCLUDED: frozenset[str] = frozenset(
    reg.key for reg in (*ADDED_IN_0_4, *_RAW_ADDED, *OUTPUT_FLAGS, *RESOLVED_IN_0_17)
) | {"cap_solar"}

# -------------------------------------------------------------- installation equipment
# Optional parts of an installation. Registers of a part that is switched off in the options are
# neither polled nor turned into entities. Their registry entries (and entity IDs) stay, so
# switching the part on again restores the very same entities.
FEATURES: tuple[str, ...] = ("mk1", "mk2", "mk3", "cooling", "pool", "room_unit", "solar")

# Capability flag (discrete input) used to pre-fill each option during setup.
FEATURE_CAPABILITY: dict[str, str] = {
    "mk1": "cap_mk1_heating",
    "mk2": "cap_mk2_heating",
    "mk3": "cap_mk3_heating",
    "cooling": "cap_cooling",
    "pool": "cap_pool",
    "room_unit": "cap_room_controller",
    "solar": "cap_solar",
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
    "hours_cooling": ("cooling",),
    "hours_solar": ("solar",),
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


# ------------------------------------------------------------------- trigger buttons
@dataclass(frozen=True)
class TriggerAction:
    """A button that writes one fixed word to a trigger register (next to the register's own start button)."""

    key: str
    name_de: str
    name_en: str
    register: str  # key of the trigger register
    raw: int  # the word written on press


# Writing 0 to 10071 sets the extra hot water timer to 0 (full analysis, 3.2; proven), so the run can be ended
# early. Writing 0 to 10070 ends a circulation run (full analysis, 3.3; proven from firmware V3.92.3): the
# circulation logic (FUN_00275f94) computes its request every 1 s cycle as (10070 != 0) OR the request of the
# controller's own circulation time program (FUN_00252f54) and passes it to the ZIP state machine (object at
# DAT_00a17c7c; the setter FUN_00276488 stores the request flag; FUN_0028a5d4 reports "running" only if enabled
# AND FUN_0028a4a0 is true). FUN_0028a4a0 returns false at once while the request flag is 0, so the pump output
# stops immediately. The run counter is frozen, not reset: the next start resumes the remaining on-time instead of
# a full one. While the time program requests circulation at the same time, the pump keeps running.
TRIGGER_ACTIONS: tuple[TriggerAction, ...] = (
    TriggerAction("circulation_stop", "Zirkulation: beenden", "Circulation: end", CIRCULATION_KEY, 0),
    TriggerAction("extra_dhw_stop", "Extra: beenden", "Extra: end", EXTRA_DHW_KEY, 0),
)
TRIGGER_ACTION_KEYS: tuple[str, ...] = tuple(action.key for action in TRIGGER_ACTIONS)
# The circulation trigger is not accepted while the controller's hot water operating mode is "holiday" (3) or
# "off" (4) (full analysis, 3.3; proven). Over the SHI only "off" is visible: discrete input 10001 (``hot_water_available``)
# reads 0 while hot water is not equipped or its operating mode is "off" (full analysis, 2.3; proven). The button
# is unavailable while that flag is off; "holiday" cannot be read, a press is then silently without effect.
TRIGGER_REQUIRES: dict[str, str] = {CIRCULATION_KEY: HOT_WATER_AVAILABLE_KEY}

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

# Block views: a select and a switch that are views on the two registers ``heating_block`` (10050) and
# ``dhw_block`` (10051); they poll nothing of their own (see ``block_views.py``). The option keys are chosen so
# that the Heat Pump Optimizer recognises them as pump modes: after folding to letters and digits they equal the
# option labels the optimizer's reference integration publishes (tests/test_block_views.py checks this against
# the optimizer's vocabulary).
BLOCK_MODE_KEY = "block_mode"
BLOCK_POWER_KEY = "block_power"
BLOCK_MODE_HEATING_DHW = "heating_dhw"  # no block
BLOCK_MODE_HEATING = "heating"  # hot water blocked
BLOCK_MODE_DHW = "dhw_hot_water"  # heating blocked (also shown while both are blocked)
BLOCK_MODES: tuple[str, ...] = (BLOCK_MODE_HEATING_DHW, BLOCK_MODE_HEATING, BLOCK_MODE_DHW)
BLOCK_SELECT_KEYS: tuple[str, ...] = (BLOCK_MODE_KEY,)
BLOCK_SWITCH_KEYS: tuple[str, ...] = (BLOCK_POWER_KEY,)

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
    DerivedSensor("cop", "COP (10 min)", "COP (10 min)", "compressor_thermal_power", "electric_power", cumulative=False),
    DerivedSensor("cop_heating", "COP gesamt", "COP overall", "energy_th_heating", "energy_el_heating", True),
    DerivedSensor("cop_dhw", "COP gesamt", "COP overall", "energy_th_dhw", "energy_el_dhw", True),
    # Counters of all modes together (the thermal total needs firmware 3.92.0, see its entity text).
    DerivedSensor("cop_total", "COP gesamt", "COP overall", "energy_th_total", "energy_el_total", True),
)


@dataclass(frozen=True)
class DifferenceSensor:
    """A sensor that is the difference of two existing registers (``minuend`` minus ``subtrahend``)."""

    key: str
    name_de: str
    name_en: str
    minuend: str
    subtrahend: str
    unit: str


# The controller has no spread register (docs/entities.md); this is flow minus return, calculated from the two
# temperatures that are polled anyway. Negative values are real (defrost reverses the flow of heat) and are not
# clamped. The unit is a plain "K" without a temperature device class on purpose: with the class, Home Assistant
# would convert it like an absolute temperature (a difference of 5 K would show as -268 degC).
DIFFERENCE_SENSORS: tuple[DifferenceSensor, ...] = (
    DifferenceSensor(
        "flow_return_difference", "Temperatur: Differenz Vorlauf/Rücklauf", "Temperature: flow-return difference",
        "flow", "return", "K",
    ),
)
DERIVED_SENSOR_KEYS: tuple[str, ...] = tuple(sensor.key for sensor in DERIVED_SENSORS) + tuple(
    sensor.key for sensor in DIFFERENCE_SENSORS
)


@dataclass(frozen=True)
class DerivedFlag:
    """A binary sensor that is on when a status register holds one of ``on_values``.

    ``on_values`` are raw register values (positions in the option tuple of the source for enumerations);
    ``None`` means any value except 0. An unknown source value gives an unavailable entity, never a guess.
    """

    key: str
    name_de: str
    name_en: str
    source: str
    on_values: frozenset[int] | None
    device_class: str | None = None


def _option(source: str, option: str) -> int:
    """Raw value of an option of an enumeration register."""
    return BY_KEY[source].options.index(option)


DERIVED_FLAGS: tuple[DerivedFlag, ...] = (
    DerivedFlag("fault", "Status: Störung", "Status: fault", "error_number", None, "problem"),
    DerivedFlag(
        "defrost", "Status: Abtauung läuft", "Status: defrost active", "operating_mode",
        frozenset({_option("operating_mode", "defrost")}),
    ),
    DerivedFlag(
        "heating_running", "Läuft", "Running", "heating_status",
        frozenset({_option("heating_status", "running")}), "running",
    ),
    DerivedFlag(
        "dhw_running", "Läuft", "Running", "hot_water_status",
        frozenset({_option("hot_water_status", "running")}), "running",
    ),
    # The configured mode, NOT whether the limit currently reduces the power (the controller's reaction is open).
    DerivedFlag(
        "power_limit_configured", "Leistungsbegrenzung: Modus eingestellt", "Power limit: mode set",
        "cfg_power_limit_mode",
        frozenset({_option("cfg_power_limit_mode", "soft"), _option("cfg_power_limit_mode", "hard")}),
    ),
    # Running state of the extra hot water trigger, read from the trigger register itself (full analysis, 3.2;
    # proven): 10071 reads 1 while the extra hot water timer runs (``extra_dhw_remaining`` shows the minutes left)
    # and 0 when the firmware ended it. Circulation has no derived flag: the running indicator is the pump output
    # ``pump_circulation`` (ZIP, 10356; proven and measured), which also covers runs of the time program.
    DerivedFlag("extra_dhw_running", "Extra: läuft", "Extra: running", EXTRA_DHW_KEY, None, "running"),
)
DERIVED_FLAG_KEYS: tuple[str, ...] = tuple(flag.key for flag in DERIVED_FLAGS)

# The one firmware entity: a text sensor composed of the three version registers ``FIRMWARE_PARTS``. Its key is
# part of the entity contract.
FIRMWARE_SENSOR_KEY = "firmware_version"
FIRMWARE_PARTS: tuple[str, str, str] = ("fw_version_major", "fw_version_minor", "fw_version_patch")
# Entities of earlier versions that no longer exist (CHANGELOG 0.11.0 and 0.18.0): the integration deletes their
# registry entries at setup. Keys listed here have no entity on any platform and are out of the entity contract.
# 0.18.0: the raw word sensors of registers that have a proper entity (``hours_cooling``, ``hours_solar``,
# ``extra_dhw_setpoint``, ``extra_dhw_duration``, ``extra_dhw_remaining``).
REMOVED_KEYS: tuple[str, ...] = (
    "fw_platform",
    "fw_major",
    "fw_minor",
    "raw_10410",
    "raw_10411",
    "raw_10416",
    "raw_10417",
    "raw_10500",
    "raw_10501",
    "raw_10502",
    # 0.18.0: raw twins of the proven outputs and inputs (binary sensors ``OUTPUT_FLAGS``).
    "raw_10350",
    "raw_10351",
    "raw_10352",
    "raw_10353",
    "raw_10354",
    "raw_10355",
    "raw_10356",
    "raw_10360",
    "raw_10361",
)
# Entities whose key moved to another platform (CHANGELOG 0.18.0): (old platform, key). The key lives on; the
# registry entry of the old platform is an orphan and is deleted at setup. The triggers ``circulation`` and
# ``extra_dhw`` were switches up to 0.17.x and are buttons now.
REMOVED_ENTITIES: tuple[tuple[str, str], ...] = (("switch", CIRCULATION_KEY), ("switch", EXTRA_DHW_KEY))


def firmware_version(values: dict[str, float | int | None]) -> str | None:
    """Firmware version as text ("3.92.3"), ``None`` until all three parts are known."""
    parts = [values.get(key) for key in FIRMWARE_PARTS]
    if any(part is None for part in parts):
        return None
    return ".".join(str(int(part)) for part in parts)

# The following limits are a design choice of this integration, NOT a register fact and not documented by the
# manufacturer. They only decide when a calculated COP is shown as "unknown" instead of a misleading number.
#
# The instantaneous COP is the quotient of two power registers that both have a resolution of 100 W and are not
# sampled at the same instant. Measured on the reference installation (history of 2026-11-06/07): the first
# readings after a compressor start gave 8.0, 6.3, 9.3 and 10.3 (thermal power already high, electric power still
# small), and the steady state flipped between neighbouring ratios of whole numbers (4.32 / 4.37). Therefore the
# COP is the ratio of the energy of a trailing window: integral of thermal power / integral of electric power.
COP_WINDOW_S = 600.0
# A gap between two samples longer than this (failed polls, Home Assistant down) is not interpolated.
COP_MAX_SAMPLE_GAP_S = 150.0
# The window needs at least this much electric energy before it says anything. At the typical 1 to 2 kW of the
# compressor this hides the first 2 to 4 minutes of a run, where the thermal power register still ramps up.
COP_MIN_WINDOW_ENERGY_WH = 60.0
# Overall values need some electric energy before the quotient says anything (e.g. a fresh counter).
COP_MIN_ELECTRIC_ENERGY_KWH = 1.0
# Heat pumps do not reach more than this; anything above is a measurement or timing artefact.
COP_MAX_PLAUSIBLE = 12.0


def _plausible(cop: float) -> float | None:
    return cop if 0 < cop <= COP_MAX_PLAUSIBLE else None


class WindowedCop:
    """COP over a trailing time window from power samples (thermal W, electric W).

    Every pair of consecutive samples contributes the trapezoid of both powers over its duration. The value is
    unknown while the window holds less than ``COP_MIN_WINDOW_ENERGY_WH`` of electric energy (compressor not
    running, or just started) and when the result is implausible, which includes a net thermal energy that is
    not positive (long defrost). Defrost with negative thermal power inside a run counts: it is real consumption.
    """

    def __init__(
        self,
        window_s: float = COP_WINDOW_S,
        max_gap_s: float = COP_MAX_SAMPLE_GAP_S,
        min_energy_wh: float = COP_MIN_WINDOW_ENERGY_WH,
    ) -> None:
        self._window_s = window_s
        self._max_gap_s = max_gap_s
        self._min_energy_wh = min_energy_wh
        self._last: tuple[float, float, float] | None = None  # time, thermal W, electric W
        self._segments: list[tuple[float, float, float]] = []  # end time, thermal Wh, electric Wh

    def add(self, now: float, thermal_w: float | None, electric_w: float | None) -> float | None:
        """Add a sample (``now`` in seconds, any monotonic scale) and return the COP of the window."""
        if thermal_w is None or electric_w is None:
            self._last = None  # a missing value breaks the continuity
        else:
            last = self._last
            if last is not None and 0 < now - last[0] <= self._max_gap_s:
                hours = (now - last[0]) / 3600
                self._segments.append(
                    (now, (last[1] + thermal_w) / 2 * hours, (last[2] + electric_w) / 2 * hours)
                )
            self._last = (now, thermal_w, electric_w)
        self._segments = [seg for seg in self._segments if seg[0] >= now - self._window_s]
        electric_wh = sum(seg[2] for seg in self._segments)
        thermal_wh = sum(seg[1] for seg in self._segments)
        if electric_wh < self._min_energy_wh:
            return None
        return _plausible(thermal_wh / electric_wh)


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
_COOLING_KEYS = frozenset(
    {"cooling_block", "cooling_status", "energy_el_cooling", "energy_th_cooling", "hours_cooling"}
)
_POOL_KEYS = frozenset({"pool_block", "pool_status", "energy_el_pool", "energy_th_pool"})
_HOT_WATER_KEYS = frozenset(
    {
        CIRCULATION_KEY,
        "circulation_stop",
        EXTRA_DHW_KEY,
        "hot_water_status",
        "energy_el_dhw",
        "energy_th_dhw",
        "hours_dhw",
        "cop_dhw",
        "pump_hot_water",
        "pump_circulation",
    }
)
_HEATING_KEYS = frozenset(
    {
        "heating_demand_border",
        "heating_block",
        "heating_status",
        "room",
        "energy_el_heating",
        "energy_th_heating",
        "hours_heating",
        "cop_heating",
        "heating_running",
        "pump_heating",
    }
)


def area_of(key: str) -> str | None:
    """Sub-device of an entity key, ``None`` for the main heat pump device."""
    if key in _COOLING_KEYS or (key.startswith("cfg_mk") and "_cool_" in key):
        return "cooling"
    if key in _POOL_KEYS:
        return "pool"
    if key in _HOT_WATER_KEYS or key.startswith(("dhw", "cfg_dhw", "extra_dhw")):
        return "hot_water"
    if key in _HEATING_KEYS or key.startswith(
        ("cfg_heating", "cfg_overall", "cfg_mk", "mk1_", "mk2_", "mk3_")
    ):
        return "heating"
    return None
