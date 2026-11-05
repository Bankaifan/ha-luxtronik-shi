"""Generate translations/{de,en}.json from the register map (run from repo root)."""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "custom_components" / "luxtronik_shi"))
# STATUS_BITS lives next to the binary sensor platform; read it without importing Home Assistant.
import ast  # noqa: E402

import registers  # noqa: E402  (plain import, no HA needed)

_tree = ast.parse(
    (ROOT / "custom_components" / "luxtronik_shi" / "binary_sensor.py").read_text(encoding="utf-8")
)
_bits = next(
    ast.literal_eval(node.value)
    for node in _tree.body
    if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "STATUS_BITS"
)


class binary_sensor:  # noqa: N801 - tiny namespace for the loop below
    STATUS_BITS = _bits


STATIC = {
    "en": {
        "config": {
            "step": {
                "user": {
                    "title": "Luxtronik SHI (Modbus/TCP)",
                    "description": "Connect to the Smart Home Interface of your alpha innotec / Luxtronik heat pump. Modbus/TCP must be enabled in the controller.",
                    "data": {"name": "Name", "host": "Host", "port": "Port", "slave": "Unit ID (slave)"},
                },
                "reconfigure": {
                    "title": "Change connection",
                    "data": {"host": "Host", "port": "Port", "slave": "Unit ID (slave)"},
                },
            },
            "error": {
                "cannot_connect": "No connection to the heat pump. Check IP address, port and that Modbus/TCP is enabled.",
                "not_supported": "The device answered, but does not look like a Luxtronik SHI.",
            },
            "abort": {
                "already_configured": "This heat pump is already configured.",
                "reconfigure_successful": "The connection data was updated.",
            },
        },
        "options": {
            "step": {
                "init": {
                    "title": "Options",
                    "data": {"scan_interval": "Update interval (seconds)"},
                    "data_description": {
                        "scan_interval": "Base interval. Slowly changing values (counters, settings, firmware) are read less often automatically."
                    },
                }
            }
        },
    },
    "de": {
        "config": {
            "step": {
                "user": {
                    "title": "Luxtronik SHI (Modbus/TCP)",
                    "description": "Verbindung zur Smart-Home-Schnittstelle deiner alpha innotec / Luxtronik Wärmepumpe. Modbus/TCP muss in der Regelung aktiviert sein.",
                    "data": {"name": "Name", "host": "Host", "port": "Port", "slave": "Geräte-ID (Slave)"},
                },
                "reconfigure": {
                    "title": "Verbindung ändern",
                    "data": {"host": "Host", "port": "Port", "slave": "Geräte-ID (Slave)"},
                },
            },
            "error": {
                "cannot_connect": "Keine Verbindung zur Wärmepumpe. Prüfe IP-Adresse, Port und ob Modbus/TCP aktiviert ist.",
                "not_supported": "Das Gerät antwortet, sieht aber nicht nach einer Luxtronik SHI aus.",
            },
            "abort": {
                "already_configured": "Diese Wärmepumpe ist bereits eingerichtet.",
                "reconfigure_successful": "Die Verbindungsdaten wurden aktualisiert.",
            },
        },
        "options": {
            "step": {
                "init": {
                    "title": "Optionen",
                    "data": {"scan_interval": "Aktualisierungsintervall (Sekunden)"},
                    "data_description": {
                        "scan_interval": "Basisintervall. Langsam veränderliche Werte (Zähler, Einstellungen, Firmware) werden automatisch seltener abgefragt."
                    },
                }
            }
        },
    },
}

FEATURE_LABELS = {
    "en": {
        "mk1": "Mixing circuit 1",
        "mk2": "Mixing circuit 2",
        "mk3": "Mixing circuit 3",
        "cooling": "Cooling",
        "pool": "Pool / swimming pool",
        "room_unit": "Room unit (room temperature)",
    },
    "de": {
        "mk1": "Mischkreis 1",
        "mk2": "Mischkreis 2",
        "mk3": "Mischkreis 3",
        "cooling": "Kühlung",
        "pool": "Pool / Schwimmbad",
        "room_unit": "Raumeinheit (Raumtemperatur)",
    },
}
EQUIPMENT_TEXT = {
    "en": {
        "title": "Installation equipment",
        "description": "Pre-filled from what the heat pump reports. Parts that are switched off are not polled and get no entities. Can be changed later in the options.",
        "options": "Parts of the installation that are switched off are not polled and get no entities. Their entity IDs stay reserved and come back when the part is switched on again.",
    },
    "de": {
        "title": "Ausstattung der Anlage",
        "description": "Vorausgefüllt mit dem, was die Wärmepumpe meldet. Abgewählte Teile werden nicht abgefragt und bekommen keine Entitäten. Später in den Optionen änderbar.",
        "options": "Abgewählte Teile der Anlage werden nicht abgefragt und bekommen keine Entitäten. Ihre Entity-IDs bleiben reserviert und kommen beim Wiedereinschalten zurück.",
    },
}

STATES = {
    "en": {
        "off": "Off",
        "setpoint": "Setpoint",
        "offset": "Offset",
        "level": "Level",
        "evu_lock": "Utility lockout",
        "reduced": "Reduced",
        "normal": "Normal",
        "boost": "Boost",
        "none": "No limit",
        "soft": "Soft limit",
        "hard": "Hard limit",
        "heating": "Heating",
        "hot_water": "Hot water",
        "pool": "Pool",
        "defrost": "Defrost",
        "external_source": "External source",
        "cooling": "Cooling",
        "unknown": "Unknown",
        "series": "Series buffer",
        "separation": "Separation buffer",
        "multi": "Multi-function buffer",
    },
    "de": {
        "off": "Aus",
        "setpoint": "Sollwert",
        "offset": "Anhebung",
        "level": "Stufe",
        "evu_lock": "EVU-Sperre",
        "reduced": "Absenkung",
        "normal": "Normal",
        "boost": "Boost",
        "none": "Keine Begrenzung",
        "soft": "Weiche Begrenzung",
        "hard": "Harte Begrenzung",
        "heating": "Heizen",
        "hot_water": "Warmwasser",
        "pool": "Schwimmbad",
        "defrost": "Abtauen",
        "external_source": "Externe Quelle",
        "cooling": "Kühlen",
        "unknown": "Unbekannt",
        "series": "Reihenpuffer",
        "separation": "Trennpuffer",
        "multi": "Multifunktionspuffer",
    },
}

for lang in ("en", "de"):
    entity: dict[str, dict] = {"sensor": {}, "binary_sensor": {}, "switch": {}, "number": {}, "select": {}}
    for reg in registers.ALL_REGISTERS:
        name = reg.name_en if lang == "en" else reg.name_de
        if reg.key in registers.RAW_KEYS:
            entity["sensor"]["raw"] = {
                "name": "Raw value: {address}" if lang == "en" else "Rohwert: {address}"
            }
            continue
        entry = {"name": name}
        if reg.options and reg.platform in ("sensor", "select"):
            entry["state"] = {opt: STATES[lang][opt] for opt in reg.options}
        entity[reg.platform][reg.key] = entry
    for key, _bit, de, en in binary_sensor.STATUS_BITS:
        entity["binary_sensor"][key] = {"name": en if lang == "en" else de}
    entity["binary_sensor"]["online"] = {"name": "Status: connection" if lang == "en" else "Status: Verbindung"}
    data = json.loads(json.dumps(STATIC[lang]))
    labels = FEATURE_LABELS[lang]
    text = EQUIPMENT_TEXT[lang]
    data["config"]["step"]["equipment"] = {"title": text["title"], "description": text["description"], "data": dict(labels)}
    data["options"]["step"]["init"]["data"].update(labels)
    data["options"]["step"]["init"]["description"] = EQUIPMENT_TEXT[lang]["options"]
    data["entity"] = entity
    out = ROOT / "custom_components" / "luxtronik_shi" / "translations" / f"{lang}.json"
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", out)
