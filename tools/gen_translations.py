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
                    "data_description": {
                        "name": "Shown in Home Assistant and part of the entity IDs.",
                        "host": "IP address or host name of the heat pump.",
                        "port": "Modbus/TCP port of the Smart Home Interface. The default is 502.",
                        "slave": "Modbus unit ID of the Smart Home Interface. The default is 1.",
                    },
                },
                "reconfigure": {
                    "title": "Change connection",
                    "data": {"host": "Host", "port": "Port", "slave": "Unit ID (slave)"},
                    "data_description": {
                        "host": "IP address or host name of the heat pump.",
                        "port": "Modbus/TCP port of the Smart Home Interface. The default is 502.",
                        "slave": "Modbus unit ID of the Smart Home Interface. The default is 1.",
                    },
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
                        "scan_interval": "Base interval, at most 300 seconds (5 minutes): the heat pump drops values set over the Smart Home Interface after 10 minutes without access. Slowly changing values (counters, settings, firmware) are read less often automatically.",
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
                    "data_description": {
                        "name": "Wird in Home Assistant angezeigt und steckt in den Entitäts-IDs.",
                        "host": "IP-Adresse oder Hostname der Wärmepumpe.",
                        "port": "Modbus/TCP-Port der Smart-Home-Schnittstelle. Standard ist 502.",
                        "slave": "Modbus-Geräte-ID der Smart-Home-Schnittstelle. Standard ist 1.",
                    },
                },
                "reconfigure": {
                    "title": "Verbindung ändern",
                    "data": {"host": "Host", "port": "Port", "slave": "Geräte-ID (Slave)"},
                    "data_description": {
                        "host": "IP-Adresse oder Hostname der Wärmepumpe.",
                        "port": "Modbus/TCP-Port der Smart-Home-Schnittstelle. Standard ist 502.",
                        "slave": "Modbus-Geräte-ID der Smart-Home-Schnittstelle. Standard ist 1.",
                    },
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
                        "scan_interval": "Basisintervall, höchstens 300 Sekunden (5 Minuten): Die Wärmepumpe verwirft über die Smart-Home-Schnittstelle gesetzte Werte nach 10 Minuten ohne Zugriff. Langsam veränderliche Werte (Zähler, Einstellungen, Firmware) werden automatisch seltener abgefragt.",
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
        "disabled": "Disabled",
        "no_request": "No request",
        "requested": "Requested",
        "running": "Running",
        **{f"unknown_{n}": f"Unknown ({n})" for n in range(4, 16)},
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
        "increased": "Erhöht",
        "increased2": "Erhöht (Stufe 2)",
        "decreased": "Abgesenkt",
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
        "disabled": "Deaktiviert",
        "no_request": "Keine Anforderung",
        "requested": "Angefordert",
        "running": "Läuft",
        **{f"unknown_{n}": f"Unbekannt ({n})" for n in range(4, 16)},
    },
}

# Information notices (persistent notifications, not repair issues). Stored under "exceptions", the translation
# category Home Assistant provides for backend-generated messages.
NOTICES = {
    "en": {
        "base_values_changed_title": {"message": "{name}: base values of setpoints changed"},
        "base_values_changed": {
            "message": "After a restart of the heat pump, the base values these setpoints fall back to have changed "
            "(learned before -> now):\n\n{changes}\n\nThe values set in Home Assistant remain valid and were "
            "restored:\n\n{restored}\n\nNo action is needed. This is information only."
        },
    },
    "de": {
        "base_values_changed_title": {"message": "{name}: Grundwerte von Sollwerten geändert"},
        "base_values_changed": {
            "message": "Nach einem Neustart der Wärmepumpe haben sich die Grundwerte geändert, auf die diese "
            "Sollwerte zurückfallen (bisher gelernt -> jetzt):\n\n{changes}\n\nDie in Home Assistant gesetzten "
            "Werte gelten weiter und wurden wiederhergestellt:\n\n{restored}\n\nEs ist nichts zu tun. Das ist "
            "nur ein Hinweis."
        },
    },
}

# Labels per option tuple where one option key means different things in different registers. Each label says what
# the option does (sources: python-luxtronik datatypes ControlMode, LevelMode, OperationMode).
OPTION_OVERRIDES = {
    # ControlMode of every mode select: raw 0 is "no influence" (the controller uses its own values), never "off".
    registers.CONTROL_MODES: {
        "en": {
            "off": "No influence",
            "setpoint": "Setpoint (replaces the controller's target)",
            "offset": "Offset (controller's target plus offset)",
            "level": "Level (controller's target corrected by the level)",
        },
        "de": {
            "off": "Keine Vorgabe",
            "setpoint": "Sollwert (ersetzt den Sollwert der Regelung)",
            "offset": "Anhebung (Sollwert der Regelung plus Anhebung)",
            "level": "Stufe (Sollwert der Regelung, um die Stufe korrigiert)",
        },
    },
    # LevelMode 0 is "Normal": no correction.
    registers._LEVELS: {
        "en": {"normal": "Normal (no correction)"},
        "de": {"normal": "Normal (keine Korrektur)"},
    },
    # OperationMode: 5 is "no request", 2 "swimming pool/solar", 6 "heating external source".
    registers._OPERATING_MODES: {
        "en": {"off": "No request", "pool": "Pool / solar", "external_source": "Heating (external source)"},
        "de": {"off": "Keine Anforderung", "pool": "Schwimmbad / Solar", "external_source": "Heizen (externe Quelle)"},
    },
}


def option_label(lang: str, options: tuple[str, ...], option: str) -> str:
    return OPTION_OVERRIDES.get(options, {}).get(lang, {}).get(option, STATES[lang][option])


# Operation modes of the water heater (water_heater.OPERATION_MODES), raw value order of the mode select.
WATER_HEATER_OPERATIONS = ("no_influence", "setpoint", "offset", "level")

FIRMWARE_NAME = {"en": "Firmware version", "de": "Firmware-Version"}

ATTRIBUTES = {
    "en": {
        "setpoint_active": "Setpoint in effect",
        "effective_target": "Effective target",
        "controller_mode": "Control mode",
        "heating_block": "Heating blocked",
    },
    "de": {
        "setpoint_active": "Sollwert wirksam",
        "effective_target": "Wirksamer Sollwert",
        "controller_mode": "Betriebsart der Schnittstelle",
        "heating_block": "Heizen gesperrt",
    },
}

CLIMATE_STATES = {
    "en": {"auto": "Heat pump controls itself", "heat": "Set by Home Assistant"},
    "de": {"auto": "Wärmepumpe regelt selbst", "heat": "Vorgabe durch Home Assistant"},
}

_SETPOINT_HINT = {
    "en": 'The setpoint only applies in mode "{setpoint}". {{select}} is in mode "{mode}", so nothing was written. Set {{select}} to "{setpoint}" first.',
    "de": 'Der Sollwert wirkt nur in der Betriebsart „{setpoint}“. {{select}} steht auf „{mode}“, deshalb wurde nichts geschrieben. Stelle {{select}} zuerst auf „{setpoint}“.',
}
_UNKNOWN_MODE = {"en": "unknown", "de": "unbekannt"}


def exceptions(lang: str) -> dict[str, dict[str, str]]:
    # Short labels (the part before the explanation in brackets): the select shows the long label starting with it.
    labels = {k: v.split(" (")[0] for k, v in OPTION_OVERRIDES[registers.CONTROL_MODES][lang].items()}
    out = {
        f"setpoint_not_active_{mode}": {
            "message": _SETPOINT_HINT[lang].format(
                setpoint=labels["setpoint"], mode=labels[mode] if mode in labels else _UNKNOWN_MODE[lang]
            )
        }
        for mode in ("off", "offset", "level", "unknown")
    }
    out.update(EXCEPTIONS[lang])
    return out


# Block select and switch (views on heating_block and dhw_block, see block_views.py). "Hot water only" is also
# shown while both blocks are set; the switch shows the real off.
BLOCK_VIEWS = {
    "en": {
        "mode": "Operating mode (blocks)",
        "power": "On/off (blocks)",
        "options": {
            registers.BLOCK_MODE_HEATING_DHW: "Heating and hot water",
            registers.BLOCK_MODE_HEATING: "Heating only",
            registers.BLOCK_MODE_DHW: "Hot water only",
        },
    },
    "de": {
        "mode": "Betriebsart (Sperren)",
        "power": "Ein/Aus (Sperren)",
        "options": {
            registers.BLOCK_MODE_HEATING_DHW: "Heizen und Warmwasser",
            registers.BLOCK_MODE_HEATING: "Nur Heizen",
            registers.BLOCK_MODE_DHW: "Nur Warmwasser",
        },
    },
}

EXCEPTIONS = {
    "en": {
        "block_write_not_taken": {
            "message": "The heat pump did not take {key} = {expected} (it reads {actual}). The remaining block writes were not made."
        },
        "block_state_unknown": {
            "message": "The heating and hot water blocks have no value yet. Try again after the next update."
        },
        "setpoint_out_of_range": {"message": "Setpoint {value} is outside {min} … {max} °C."},
        "unsupported_hvac_mode": {"message": "HVAC mode {mode} is not supported. Use auto or heat."},
        "unsupported_operation_mode": {"message": "Operation mode {mode} is not supported."},
        "control_mode_unknown": {"message": "The heating control mode is not known yet. Try again after the next update."},
        "external_change_logbook": {"message": "{name} changed outside Home Assistant: {old} -> {new}"},
        "write_failed": {"message": "Writing {key} failed: {error}"},
        "not_writable": {"message": "Register {key} cannot be written."},
        "poll_failed": {"message": "No connection to the heat pump: {error}"},
        "state_on": {"message": "on"},
        "state_off": {"message": "off"},
    },
    "de": {
        "block_write_not_taken": {
            "message": "Die Wärmepumpe hat {key} = {expected} nicht übernommen (sie liest {actual}). Die weiteren Schreibzugriffe auf die Sperren wurden nicht ausgeführt."
        },
        "block_state_unknown": {
            "message": "Für die Sperren von Heizung und Warmwasser liegt noch kein Wert vor. Versuche es nach der nächsten Aktualisierung erneut."
        },
        "setpoint_out_of_range": {"message": "Sollwert {value} liegt außerhalb von {min} … {max} °C."},
        "unsupported_hvac_mode": {"message": "HVAC-Modus {mode} wird nicht unterstützt. Verwende auto oder heat."},
        "unsupported_operation_mode": {"message": "Betriebsart {mode} wird nicht unterstützt."},
        "control_mode_unknown": {"message": "Die Betriebsart der Heizung ist noch nicht bekannt. Versuche es nach der nächsten Aktualisierung erneut."},
        "external_change_logbook": {"message": "{name} außerhalb von Home Assistant geändert: {old} -> {new}"},
        "write_failed": {"message": "Schreiben von {key} fehlgeschlagen: {error}"},
        "not_writable": {"message": "Register {key} kann nicht geschrieben werden."},
        "poll_failed": {"message": "Keine Verbindung zur Wärmepumpe: {error}"},
        "state_on": {"message": "an"},
        "state_off": {"message": "aus"},
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
        "values_changed_externally": {
            "title": "{name}: Value changed outside Home Assistant",
            "description": "These settings of the heat pump changed without a write through Home Assistant, for example by another Modbus client, the native Luxtronik protocol (port 8889), OpenEMS or the controller panel (setting: old -> new, time of the last change):\n\n{changes}\n\nThe integration does not write anything back. If another system writes the same settings, they overwrite each other; the last write wins. Further changes are added while this issue is open. Dismiss it once you have checked the values.",
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
        "values_changed_externally": {
            "title": "{name}: Wert außerhalb von Home Assistant geändert",
            "description": "Diese Einstellungen der Wärmepumpe haben sich geändert, ohne dass Home Assistant geschrieben hat, zum Beispiel durch einen anderen Modbus-Client, das native Luxtronik-Protokoll (Port 8889), OpenEMS oder das Bedienteil (Einstellung: alt -> neu, Zeit der letzten Änderung):\n\n{changes}\n\nDie Integration schreibt nichts zurück. Schreibt ein anderes System dieselben Einstellungen, überschreiben sie sich gegenseitig; der letzte Schreibzugriff gewinnt. Weitere Änderungen werden ergänzt, solange dieser Hinweis offen ist. Schließe ihn, wenn du die Werte geprüft hast.",
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
        if reg.platform == "internal":
            continue  # read only to compose another entity, no entity of its own
        entry = {"name": name}
        if reg.options and reg.platform in ("sensor", "select"):
            entry["state"] = {opt: option_label(lang, reg.options, opt) for opt in reg.options}
        if reg.key in registers.SETPOINT_GROUPS:
            entry["state_attributes"] = {
                attr: {"name": ATTRIBUTES[lang][attr]} for attr in ("setpoint_active", "effective_target")
            }
        entity[reg.platform][reg.key] = entry
    attrs = ATTRIBUTES[lang]
    mode_labels = {
        opt: option_label(lang, registers.CONTROL_MODES, opt) for opt in registers.CONTROL_MODES
    }
    entity["climate"] = {
        registers.CLIMATE_HEATING_KEY: {
            "state": dict(CLIMATE_STATES[lang]),
            "state_attributes": {
                "controller_mode": {"name": attrs["controller_mode"], "state": mode_labels},
                **{a: {"name": attrs[a]} for a in ("setpoint_active", "effective_target", "heating_block")},
            },
        }
    }
    # Short labels (the part before the explanation in brackets): the water heater card is narrow, the mode
    # selects keep the long text.
    operation_labels = {
        op: mode_labels[opt].split(" (")[0]
        for op, opt in zip(WATER_HEATER_OPERATIONS, registers.CONTROL_MODES, strict=True)
    }
    entity["water_heater"] = {
        registers.WATER_HEATER_DHW_KEY: {
            "state": dict(operation_labels),
            "state_attributes": {
                "operation_mode": {"state": dict(operation_labels)},
                **{a: {"name": attrs[a]} for a in ("setpoint_active", "effective_target")},
            },
        }
    }
    block_text = BLOCK_VIEWS[lang]
    entity["select"][registers.BLOCK_MODE_KEY] = {
        "name": block_text["mode"],
        "state": {opt: block_text["options"][opt] for opt in registers.BLOCK_MODES},
    }
    entity["switch"][registers.BLOCK_POWER_KEY] = {"name": block_text["power"]}
    entity["sensor"][registers.FIRMWARE_SENSOR_KEY] = {"name": FIRMWARE_NAME[lang]}
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
    data["exceptions"] = {**NOTICES[lang], **exceptions(lang)}
    data["device"] = {area: {"name": name} for area, name in DEVICE_NAMES[lang].items()}
    out = ROOT / "custom_components" / "luxtronik_shi" / "translations" / f"{lang}.json"
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", out)
