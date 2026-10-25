"""Generate the equivalent plain Home Assistant YAML (modbus: hub + template entities) from the register map.

For people who prefer YAML over the integration. Usage:  python tools/gen_yaml.py HOST > modbus.yaml
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "luxtronik_shi"))
import registers as r  # noqa: E402

HUB = "lwdv_shi"
SLAVE = 1

# Entities that exist in a long-running installation got their IDs from their first names; the
# generated templates must reference those. Everything else is derived from the key.
SENSOR_ID_OVERRIDES = {
    "cfg_heating_mode": "einstellung_heizen_betriebsart_heating_mode",
    "cfg_heating_setpoint": "einstellung_heizen_sollwert_heating_setpoint",
    "cfg_heating_offset": "einstellung_heizen_anhebung_heating_offset",
    "cfg_heating_level": "einstellung_heizen_stufe_heating_level",
    "cfg_dhw_mode": "einstellung_warmwasser_betriebsart_dhw_mode",
    "cfg_dhw_setpoint": "einstellung_warmwasser_sollwert_dhw_setpoint",
    "cfg_dhw_offset": "einstellung_warmwasser_anhebung_dhw_offset",
    "cfg_dhw_level": "einstellung_warmwasser_stufe_dhw_level",
    "cfg_mk1_mode": "einstellung_mischkreis_1_betriebsart_mixer_1_mode",
    "cfg_mk1_setpoint": "einstellung_mischkreis_1_sollwert_mixer_1_setpoint",
    "cfg_mk1_offset": "einstellung_mischkreis_1_anhebung_mixer_1_offset",
    "cfg_mk1_level": "einstellung_mischkreis_1_stufe_mixer_1_level",
    "cfg_power_limit_mode": "einstellung_leistungsbegrenzung_modus_power_limit_mode",
    "cfg_power_limit": "einstellung_leistungsbegrenzung_wert_power_limit",
    "cfg_overall_mode": "einstellung_gesamt_heizung_betriebsart_overall_heating_mode",
    "cfg_overall_offset": "einstellung_gesamt_heizung_anhebung_overall_heating_offset",
    "cfg_overall_level": "einstellung_gesamt_heizung_stufe_overall_heating_level",
}


def sensor_id(reg) -> str:
    return "sensor." + SENSOR_ID_OVERRIDES.get(reg.key, f"{HUB}_{reg.key}")


def flow(d: dict) -> str:
    return "{" + ", ".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in d.items()) + "}"


def name(reg: r.Register, prefix: str = "") -> str:
    return f"{prefix}{reg.name_de} ({reg.name_en})"


def scan(reg: r.Register) -> int:
    return {1: 30, 2: 60, 4: 120, 10: 300, 30: 300, 120: 3600}.get(reg.every, 30 * reg.every)


def base(reg: r.Register, prefix: str = "") -> dict:
    d = {
        "name": name(reg, prefix),
        "unique_id": f"{HUB}_{reg.key}",
        "slave": SLAVE,
        "address": reg.address,
        "input_type": "input" if reg.kind == "input" else "holding",
        "data_type": reg.dtype,
    }
    if reg.scale != 1.0:
        d.update(scale=reg.scale, precision=reg.precision if reg.precision is not None else 0, offset=0)
    elif reg.precision is not None and reg.dtype == "uint32":
        d["precision"] = reg.precision
    if reg.unit:
        d["unit_of_measurement"] = reg.unit
    if reg.device_class in ("temperature", "power", "energy", "duration"):
        d["device_class"] = reg.device_class
    if reg.state_class:
        d["state_class"] = reg.state_class
    d["scan_interval"] = scan(reg)
    return d


def modbus(host: str, port: int = 502) -> str:
    out = [
        f"- name: {HUB}",
        "  type: tcp",
        f"  host: {host}",
        f"  port: {port}",
        "  delay: 2",
        "  timeout: 5",
        "  sensors:",
    ]
    sensors = [x for x in r.REGISTERS if x.platform not in ("switch", "binary_sensor") and x.enabled_default]
    for reg in sensors:
        prefix = "Einstellung " if reg.kind == "holding" else ""
        out.append("  - " + flow(base(reg, prefix)))
    for reg in r.RAW_REGISTERS:
        d = {
            "name": f"Diagnose Rohwert {reg.address}",
            "unique_id": f"{HUB}_{reg.key}",
            "slave": SLAVE,
            "address": reg.address,
            "input_type": "input",
            "data_type": "uint16",
            "scan_interval": 120,
        }
        out.append("  - " + flow(d))
    out.append("  binary_sensors:")
    for reg in r.CAPABILITIES:
        d = {
            "name": name(reg),
            "unique_id": f"{HUB}_{reg.key}",
            "slave": SLAVE,
            "address": reg.address,
            "input_type": "discrete_input",
            "scan_interval": 300,
        }
        out.append("  - " + flow(d))
    for reg in r.REGISTERS:
        if reg.platform == "binary_sensor" and reg.enabled_default:
            d = {
                "name": name(reg),
                "unique_id": f"{HUB}_{reg.key}",
                "slave": SLAVE,
                "address": reg.address,
                "input_type": "input",
                "scan_interval": scan(reg),
            }
            out.append("  - " + flow(d))
    out.append("  switches:")
    for reg in r.REGISTERS:
        if reg.platform == "switch":
            d = {
                "name": name(reg),
                "unique_id": f"{HUB}_{reg.key}",
                "slave": SLAVE,
                "address": reg.address,
                "write_type": "holding",
                "command_on": 1,
                "command_off": 0,
                "scan_interval": 30 if reg.key in ("heating_block", "dhw_block") else 60,
                "verify": {"input_type": "holding", "address": reg.address, "state_on": 1, "state_off": 0},
            }
            out.append("  - " + flow(d))
    return "\n".join(out) + "\n"


def template() -> str:
    """Writable numbers/selects (Modbus has no such platforms) and decoded status values."""
    out = []
    numbers, selects = [], []
    for reg in r.REGISTERS:
        if reg.platform not in ("number", "select") or not reg.enabled_default:
            continue
        sensor = sensor_id(reg)
        write = [
            {
                "action": "modbus.write_register",
                "data": {"hub": HUB, "slave": SLAVE, "address": reg.address, "value": None},
            },
            {"action": "homeassistant.update_entity", "target": {"entity_id": sensor}},
        ]
        if reg.platform == "number":
            write[0]["data"]["value"] = f"{{{{ ((value / {reg.scale}) | round(0) | int) % 65536 }}}}"
            numbers.append((reg, sensor, write))
        else:
            mapping = "{" + ", ".join(f"'{o}': {i}" for i, o in enumerate(reg.options)) + "}"
            write[0]["data"]["value"] = f"{{{{ {mapping}[option] }}}}"
            selects.append((reg, sensor, write, list(reg.options)))
    out.append("- number:")
    for reg, sensor, write in numbers:
        out.append(f"  - name: {json.dumps(name(reg, 'LWDV '), ensure_ascii=False)}")
        out.append(f"    unique_id: {HUB}_{reg.key}_set")
        out.append(f"    state: \"{{{{ states('{sensor}') | float(none) }}}}\"")
        out.append(f"    availability: \"{{{{ has_value('{sensor}') }}}}\"")
        out.append(f"    min: {reg.min_value}")
        out.append(f"    max: {reg.max_value}")
        out.append(f"    step: {reg.step}")
        out.append(f"    unit_of_measurement: {json.dumps(reg.unit, ensure_ascii=False)}")
        out.append("    set_value:")
        out.append("    - action: modbus.write_register")
        out.append(
            f'      data: {{hub: {HUB}, slave: {SLAVE}, address: {reg.address}, value: "{write[0]["data"]["value"]}"}}'
        )
        out.append("    - action: homeassistant.update_entity")
        out.append(f"      target: {{entity_id: {sensor}}}")
    out.append("- select:")
    for reg, sensor, write, options in selects:
        mapping = "{" + ", ".join(f"{i}: '{o}'" for i, o in enumerate(options)) + "}"
        out.append(f"  - name: {json.dumps(name(reg, 'LWDV '), ensure_ascii=False)}")
        out.append(f"    unique_id: {HUB}_{reg.key}_set")
        out.append(f"    state: \"{{{{ {mapping}.get(states('{sensor}') | int(-1)) }}}}\"")
        out.append(f"    availability: \"{{{{ has_value('{sensor}') }}}}\"")
        opts = "[" + ", ".join(f"'{o}'" for o in options) + "]"
        out.append(f'    options: "{{{{ {opts} }}}}"')
        out.append("    select_option:")
        out.append("    - action: modbus.write_register")
        out.append(
            f'      data: {{hub: {HUB}, slave: {SLAVE}, address: {reg.address}, value: "{write[0]["data"]["value"]}"}}'
        )
        out.append("    - action: homeassistant.update_entity")
        out.append(f"      target: {{entity_id: {sensor}}}")
    op = "{" + ", ".join(f"{i}: '{o}'" for i, o in enumerate(r._OPERATING_MODES)) + "}"
    out.append("- sensor:")
    out.append('  - name: "LWDV Betriebsart Text"')
    out.append(f"    unique_id: {HUB}_operating_mode_text")
    out.append(f"    state: \"{{{{ {op}.get(states('sensor.{HUB}_operating_mode') | int(-1)) }}}}\"")
    out.append(f"    availability: \"{{{{ has_value('sensor.{HUB}_operating_mode') }}}}\"")
    out.append("  binary_sensor:")
    for key, bit, de, _en in (
        ("compressor_1", 0, "Verdichter 1 läuft", ""),
        ("compressor_2", 1, "Verdichter 2 läuft", ""),
        ("aux_heater_1", 2, "Zusatzheizung 1 (ZWE) aktiv", ""),
        ("aux_heater_2", 3, "Zusatzheizung 2 (ZWE) aktiv", ""),
    ):
        out.append(f'  - name: "LWDV {de}"')
        out.append(f"    unique_id: {HUB}_{key}")
        out.append(
            f"    state: \"{{{{ (states('sensor.{HUB}_heat_generator_state') | int(0)) | bitwise_and({1 << bit}) > 0 }}}}\""
        )
        out.append(f"    availability: \"{{{{ has_value('sensor.{HUB}_heat_generator_state') }}}}\"")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.0.77"
    which = sys.argv[2] if len(sys.argv) > 2 else "all"
    if which in ("modbus", "all"):
        print("# ---- modbus: ----")
        print(modbus(host))
    if which in ("template", "all"):
        print("# ---- template: ----")
        print(template())
