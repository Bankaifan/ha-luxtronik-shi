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
                "discovery_confirm": {
                    "title": "Heat pump found",
                    "description": "A Luxtronik heat pump with an active Smart Home Interface was found at {host}. Set it up?",
                    "data": {"name": "Name"},
                },
            },
            "flow_title": "Luxtronik SHI ({host})",
            "error": {
                "cannot_connect": "No connection to the heat pump. Check IP address, port and that Modbus/TCP is enabled.",
                "not_supported": "The device answered, but does not look like a Luxtronik SHI.",
            },
            "abort": {
                "already_configured": "This heat pump is already configured.",
                "not_supported": "The device does not answer as a Luxtronik Smart Home Interface.",
                "reconfigure_successful": "The connection data was updated.",
            },
        },
        "options": {
            "step": {
                "init": {
                    "title": "Options",
                    "data": {
                        "scan_interval": "Update interval (seconds)",
                        "restore_after_reset": "Restore values after a device reset",
                    },
                    "data_description": {
                        "scan_interval": "Base interval. Slowly changing values (counters, settings, firmware) are read less often automatically.",
                        "restore_after_reset": "The heat pump forgets values set over the Smart Home Interface when it restarts or nothing has accessed it for 10 minutes. When on, the integration writes the values it last set itself back, but only after a connection outage and only if every one of them reads its reset value; any change seen while polling continuously is treated as someone else's. Only modes, levels, offsets and setpoints are restored, never blocks. Leave this off if another system also writes these registers. Off by default.",
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
                "discovery_confirm": {
                    "title": "Wärmepumpe gefunden",
                    "description": "Unter {host} wurde eine Luxtronik-Wärmepumpe mit aktiver Smart-Home-Schnittstelle gefunden. Einrichten?",
                    "data": {"name": "Name"},
                },
            },
            "flow_title": "Luxtronik SHI ({host})",
            "error": {
                "cannot_connect": "Keine Verbindung zur Wärmepumpe. Prüfe IP-Adresse, Port und ob Modbus/TCP aktiviert ist.",
                "not_supported": "Das Gerät antwortet, sieht aber nicht nach einer Luxtronik SHI aus.",
            },
            "abort": {
                "already_configured": "Diese Wärmepumpe ist bereits eingerichtet.",
                "not_supported": "Das Gerät antwortet nicht als Luxtronik Smart-Home-Schnittstelle.",
                "reconfigure_successful": "Die Verbindungsdaten wurden aktualisiert.",
            },
        },
        "options": {
            "step": {
                "init": {
                    "title": "Optionen",
                    "data": {
                        "scan_interval": "Aktualisierungsintervall (Sekunden)",
                        "restore_after_reset": "Werte nach einem Geräte-Reset wiederherstellen",
                    },
                    "data_description": {
                        "scan_interval": "Basisintervall. Langsam veränderliche Werte (Zähler, Einstellungen, Firmware) werden automatisch seltener abgefragt.",
                        "restore_after_reset": "Die Wärmepumpe vergisst über die Smart-Home-Schnittstelle gesetzte Werte, wenn sie neu startet oder 10 Minuten lang niemand zugreift. Ist die Option an, schreibt die Integration die zuletzt selbst gesetzten Werte zurück – aber nur nach einem Verbindungsausfall und nur, wenn jeder davon seinen Reset-Wert liest; jede Änderung bei durchgehender Abfrage gilt als fremd. Wiederhergestellt werden nur Betriebsarten, Stufen, Offsets und Sollwerte, nie Sperren. Lass die Option aus, wenn ein anderes System diese Register ebenfalls schreibt. Standardmäßig aus.",
                    },
                }
            }
        },
    },
}

DEVICE_NAMES = {
    "en": {"heating": "{name} Heating", "hot_water": "{name} Hot water", "cooling": "{name} Cooling", "pool": "{name} Pool"},
    "de": {"heating": "{name} Heizung", "hot_water": "{name} Warmwasser", "cooling": "{name} Kühlung", "pool": "{name} Pool"},
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
        "increased": "Increased",
        "increased2": "Increased (step 2)",
        "decreased": "Decreased",
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
        "increased": "Anhebung",
        "increased2": "Anhebung (Stufe 2)",
        "decreased": "Absenkung",
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

ISSUES = {
    "en": {
        "firmware_old": {
            "title": "{name}: heat pump firmware is outdated",
            "description": "The heat pump reports firmware {version}. The circulation pump and extra hot water registers need firmware {minimum} or later, so these entities have no values. Everything else works. Update the heat pump firmware to remove this warning.",
        },
        "shi_unreachable": {
            "title": "{name}: Smart Home Interface not reachable",
            "description": "The heat pump at {host} has not answered for more than {minutes} minutes. Entities are unavailable and nothing can be written. Check power, network and that Modbus/TCP is still enabled in the controller. This issue disappears by itself as soon as the heat pump answers again.",
        },
        "values_changed_after_outage": {
            "title": "{name}: Values changed after connection outage",
            "description": "The Smart Home Interface was unreachable. Since it answers again, these values differ from those before the outage (old -> new):\n\n{changes}\n\nThe integration does not write anything back. Check the values and set them again yourself if needed. This issue disappears when the values match those from before the outage again, or when you dismiss it.",
        },
    },
    "de": {
        "firmware_old": {
            "title": "{name}: Firmware der Wärmepumpe ist veraltet",
            "description": "Die Wärmepumpe meldet Firmware {version}. Zirkulationspumpe und Zusatz-Warmwasser brauchen Firmware {minimum} oder neuer, diese Entitäten haben daher keine Werte. Alles andere funktioniert. Aktualisiere die Firmware der Wärmepumpe, dann verschwindet diese Warnung.",
        },
        "shi_unreachable": {
            "title": "{name}: Smart-Home-Schnittstelle nicht erreichbar",
            "description": "Die Wärmepumpe unter {host} antwortet seit mehr als {minutes} Minuten nicht. Die Entitäten sind nicht verfügbar und es kann nichts geschrieben werden. Prüfe Strom, Netzwerk und ob Modbus/TCP in der Regelung noch aktiviert ist. Dieser Hinweis verschwindet von selbst, sobald die Wärmepumpe wieder antwortet.",
        },
        "values_changed_after_outage": {
            "title": "{name}: Werte nach Verbindungsausfall geändert",
            "description": "Die Smart-Home-Schnittstelle war nicht erreichbar. Seit sie wieder antwortet, unterscheiden sich diese Werte von denen vor dem Ausfall (alt -> neu):\n\n{changes}\n\nDie Integration schreibt nichts zurück. Prüfe die Werte und stelle sie bei Bedarf selbst wieder ein. Dieser Hinweis verschwindet, sobald die Werte wieder denen vor dem Ausfall entsprechen, oder wenn du ihn schließt.",
        },
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
    for derived in registers.DERIVED_SENSORS:
        entity["sensor"][derived.key] = {"name": derived.name_en if lang == "en" else derived.name_de}
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
    data["issues"] = ISSUES[lang]
    data["device"] = {area: {"name": name} for area, name in DEVICE_NAMES[lang].items()}
    out = ROOT / "custom_components" / "luxtronik_shi" / "translations" / f"{lang}.json"
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", out)
