"""One explanation per entity key for tools/gen_entity_docs.py (English and German).

See the header of entity_docs_texts.py for the rules. Mixing circuits 1 to 3 and the raw values are generated from
templates at the bottom.
"""

from __future__ import annotations

from entity_docs_texts import Entry

ENTRIES: dict[str, Entry] = {}


def _add(key: str, section: str, en: str, de: str, src: str = "", vals_en: str = "", vals_de: str = "") -> None:
    ENTRIES[key] = Entry(section, en, de, src, vals_en, vals_de)


# ------------------------------------------------------------------ temperatures of the heating circuit
_add("return", "temps",
     "Current return temperature of the heating water. The heat pump regulates on this value. Follows the water "
     "temperature (see the pitfall about 10100 and 10101 above).",
     "Aktuelle Rücklauftemperatur des Heizwassers. Auf diesen Wert regelt die Wärmepumpe. Folgt der "
     "Wassertemperatur (siehe den Fallstrick zu 10100 und 10101 oben).", "PL, M")
_add("return_target", "temps",
     "Target return temperature that the controller currently aims at (the heating curve result, or the heating "
     "setpoint in mode `setpoint`). It jumps while the heat pump heats. This is the `effective_target` of the "
     "heating setpoint.",
     "Rücklauf-Sollwert, den die Regelung gerade anstrebt (Ergebnis der Heizkurve oder der Heizungs-Sollwert in "
     "der Betriebsart `setpoint`). Er springt, während die Wärmepumpe heizt. Das ist das `effective_target` des "
     "Heizungs-Sollwerts.", "PL, M")
_add("return_external", "temps",
     "Value of the external return temperature sensor. Whether such a sensor exists depends on the "
     "installation; without one the value means nothing. Its use by the controller is not documented (open).",
     "Wert des externen Rücklauffühlers. Ob ein solcher Fühler existiert, hängt von der Anlage ab; ohne Fühler "
     "ist der Wert bedeutungslos. Seine Verwendung durch die Regelung ist nicht dokumentiert (ungeklärt).", "PL")
_add("return_limit", "temps",
     "Maximum allowed return temperature, as reported by the controller.",
     "Höchste zulässige Rücklauftemperatur laut Regelung.", "PL")
_add("return_min_target", "temps",
     "Minimum target return temperature, as reported by the controller.",
     "Niedrigster Rücklauf-Sollwert laut Regelung.", "PL")
_add("flow", "temps",
     "Current flow temperature, the temperature of the water leaving the heat pump towards the heating system.",
     "Aktuelle Vorlauftemperatur, also die Temperatur des Wassers, das die Wärmepumpe Richtung Heizungsanlage "
     "verlässt.", "PL")
_add("room", "temps",
     "Room temperature measured by the room control unit (RBE+). Only available with such a unit; the entity "
     "needs the *room unit* selected in the equipment and is disabled by default.",
     "Raumtemperatur, gemessen von der Raumeinheit (RBE+). Nur mit einer solchen Einheit vorhanden; die "
     "Entität braucht die gewählte *Raumeinheit* in der Ausstattung und ist standardmäßig deaktiviert.", "PL")
_add("heating_limit", "temps",
     "Limit temperature of heating. **Not the outside heating limit (Heizgrenze).** python-luxtronik describes it "
     "as: if the temperature falls below (heating curve setpoint minus hysteresis), the soft power limit is "
     "ignored. Its exact role beyond that is not documented (open).",
     "Grenztemperatur des Heizens. **Nicht die Heizgrenze (Außentemperatur).** python-luxtronik beschreibt sie so: "
     "Fällt die Temperatur unter (Heizkurven-Sollwert minus Hysterese), wird die weiche Leistungsbegrenzung "
     "ignoriert. Ihre genaue Rolle darüber hinaus ist nicht dokumentiert (ungeklärt).", "PL")
_add("outside", "temps",
     "Measured outside (outdoor) temperature. It drives the heating curve.",
     "Gemessene Außentemperatur. Sie bestimmt die Heizkurve.", "PL, WEB")
_add("outside_temp_average", "temps",
     "Average outside temperature. The averaging period is not documented (open). Needs firmware 3.92.0 or later. "
     "Was `raw_10109` up to 0.8.2; the entity ID stayed.",
     "Mittlere Außentemperatur. Der Mittelungszeitraum ist nicht dokumentiert (ungeklärt). Braucht Firmware 3.92.0 "
     "oder neuer. War bis 0.8.2 `raw_10109`; die Entity-ID blieb.", "PL")
_add("heat_source_input", "temps",
     "Temperature of the heat source at the heat pump inlet. What this means for an air-to-water unit is not "
     "documented (open). Was `raw_10110` up to 0.8.2.",
     "Temperatur der Wärmequelle am Eintritt der Wärmepumpe. Was das bei einem Luft-Wasser-Gerät bedeutet, ist "
     "nicht dokumentiert (ungeklärt). War bis 0.8.2 `raw_10110`.", "PL")
_add("heat_source_out", "temps",
     "Temperature of the heat source at the heat pump outlet. Same caveat as for the inlet. Not present on "
     "entries created before 0.3.0 until the equipment is saved once.",
     "Temperatur der Wärmequelle am Austritt der Wärmepumpe. Derselbe Vorbehalt wie beim Eintritt. Fehlt bei "
     "Einträgen, die vor 0.3.0 angelegt wurden, bis die Ausstattung einmal gespeichert wird.", "PL")
_add("max_flow_temp", "temps",
     "Maximum flow temperature as reported by the controller. python-luxtronik lists no unit; the integration "
     "reads it as °C with one decimal. Disabled by default. Was `raw_10112` up to 0.8.2.",
     "Maximale Vorlauftemperatur laut Regelung. python-luxtronik nennt keine Einheit; die Integration liest "
     "sie als °C mit einer Nachkommastelle. Standardmäßig deaktiviert. War bis 0.8.2 `raw_10112`.", "PL, INT")

# ------------------------------------------------------------------ hot water temperatures
_add("dhw", "dhw_temps",
     "Current hot water temperature (tank temperature as measured by the controller's hot water sensor).",
     "Aktuelle Warmwassertemperatur (Speichertemperatur laut Warmwasserfühler der Regelung).", "PL")
_add("dhw_target", "dhw_temps",
     "Hot water target temperature that the controller currently aims at. This is the `effective_target` of the "
     "hot water setpoint. The setpoint number only changes it in mode `setpoint`.",
     "Warmwasser-Zieltemperatur, die die Regelung gerade anstrebt. Das ist das `effective_target` des "
     "Warmwasser-Sollwerts. Die Zahl Sollwert ändert sie nur in der Betriebsart `setpoint`.", "PL")
_add("dhw_min", "dhw_temps",
     "Minimum adjustable hot water temperature. On the reference firmware the register returns a constant, "
     "30.0 °C, which is also the lower limit of the setpoint number.",
     "Niedrigste einstellbare Warmwassertemperatur. In der Referenz-Firmware liefert das Register eine Konstante, "
     "30,0 °C; das ist auch die Untergrenze der Zahl Sollwert.", "PL, FW")
_add("dhw_max", "dhw_temps",
     "Maximum adjustable hot water temperature, as reported by the controller.",
     "Höchste einstellbare Warmwassertemperatur laut Regelung.", "PL")
_add("dhw_limit", "dhw_temps",
     "Limit temperature of hot water. python-luxtronik describes it as: if the temperature falls below the desired "
     "regulation value, the soft power limit is ignored. Its exact role beyond that is not documented (open).",
     "Grenztemperatur des Warmwassers. python-luxtronik beschreibt sie so: Fällt die Temperatur unter den "
     "gewünschten Regelwert, wird die weiche Leistungsbegrenzung ignoriert. Ihre genaue Rolle darüber hinaus "
     "ist nicht dokumentiert (ungeklärt).", "PL")

# ------------------------------------------------------------------ power
_add("compressor_thermal_power", "power",
     "Current thermal (heating) power the heat pump delivers. Signed: **negative during defrost**. Resolution "
     "100 W. One of the keys the Heat Pump Optimizer depends on.",
     "Aktuelle thermische (Heiz-)Leistung der Wärmepumpe. Mit Vorzeichen: **negativ beim Abtauen**. Auflösung "
     "100 W. Einer der Schlüssel, auf die der Heat Pump Optimizer angewiesen ist.", "PL, INT")
_add("electric_power", "power",
     "Current electrical power consumption. Resolution 100 W. Whether it includes circulation pumps and the "
     "additional heater is not documented (open).",
     "Aktuelle elektrische Leistungsaufnahme. Auflösung 100 W. Ob Umwälzpumpen und Zusatzheizung enthalten sind, "
     "ist nicht dokumentiert (ungeklärt).", "PL")
_add("electric_power_min", "power",
     "Minimum predicted electrical power consumption. How the controller predicts it and for which state is not "
     "documented (open). ",
     "Minimale vorhergesagte elektrische Leistungsaufnahme. Wie die Regelung sie vorhersagt und für welchen "
     "Zustand, ist nicht dokumentiert (ungeklärt). ", "PL")
_add("cop", "power",
     "Instantaneous COP: `compressor_thermal_power` divided by `electric_power`. Shown as *unknown* when a value "
     "is missing, electric power is below the minimum, thermal power is zero or negative (for example defrost), "
     "or the result is implausibly high. The limits are a design choice of the integration, not a register fact.",
     "Momentan-COP: `compressor_thermal_power` geteilt durch `electric_power`. Wird als *unbekannt* gezeigt, wenn "
     "ein Wert fehlt, die elektrische Leistung unter dem Minimum liegt, die thermische Leistung null oder "
     "negativ ist (zum Beispiel beim Abtauen) oder das Ergebnis unplausibel hoch ist. Die Grenzen sind eine "
     "Festlegung der Integration, kein Registerfakt.", "INT")

# ------------------------------------------------------------------ energy
_energy = {
    "energy_el_total": ("Electrical energy consumed in total (all modes).",
                        "Insgesamt verbrauchte elektrische Energie (alle Betriebsarten)."),
    "energy_el_heating": ("Electrical energy consumed for heating. One of the keys the Heat Pump Optimizer "
                          "depends on.",
                          "Für das Heizen verbrauchte elektrische Energie. Einer der Schlüssel, auf die der Heat "
                          "Pump Optimizer angewiesen ist."),
    "energy_el_dhw": ("Electrical energy consumed for hot water.",
                      "Für das Warmwasser verbrauchte elektrische Energie."),
    "energy_el_cooling": ("Electrical energy consumed for cooling. Needs *cooling* in the equipment.",
                          "Für das Kühlen verbrauchte elektrische Energie. Braucht *Kühlung* in der Ausstattung."),
    "energy_el_pool": ("Electrical energy consumed for pool heating. Needs *pool* in the equipment.",
                       "Für die Pool-Heizung verbrauchte elektrische Energie. Braucht *Pool* in der Ausstattung."),
    "energy_th_total": ("Thermal energy produced in total (all modes). Needs firmware 3.92.0 or later.",
                        "Insgesamt erzeugte Wärmeenergie (alle Betriebsarten). Braucht Firmware 3.92.0 oder neuer."),
    "energy_th_heating": ("Thermal energy produced for heating.", "Für das Heizen erzeugte Wärmeenergie."),
    "energy_th_dhw": ("Thermal energy produced for hot water.", "Für das Warmwasser erzeugte Wärmeenergie."),
    "energy_th_cooling": ("Thermal energy produced for cooling. Needs *cooling* in the equipment.",
                          "Für das Kühlen erzeugte Energie. Braucht *Kühlung* in der Ausstattung."),
    "energy_th_pool": ("Thermal energy produced for pool heating. Needs *pool* in the equipment.",
                       "Für die Pool-Heizung erzeugte Wärmeenergie. Braucht *Pool* in der Ausstattung."),
}
for _k, (_en, _de) in _energy.items():
    _add(_k, "energy", _en + " Counter in steps of 0.1 kWh over two registers (32 bit).",
         _de + " Zähler in Schritten von 0,1 kWh über zwei Register (32 Bit).", "PL")
_add("cop_heating", "energy",
     "Overall COP of heating: `energy_th_heating` divided by `energy_el_heating`. Lifetime of the counters, **not** "
     "a JAZ. Shown as *unknown* with less than the minimum of electrical energy, a zero or negative result, an "
     "implausible result, or when a counter went backwards since the last reading (reset).",
     "Gesamt-COP des Heizens: `energy_th_heating` geteilt durch `energy_el_heating`. Lebensdauer der Zähler, "
     "**keine** JAZ. Wird als *unbekannt* gezeigt bei zu wenig elektrischer Energie, null oder negativem "
     "Ergebnis, unplausiblem Ergebnis oder wenn ein Zähler seit der letzten Messung rückwärts lief (Reset).", "INT")
_add("cop_dhw", "energy",
     "Overall COP of hot water: `energy_th_dhw` divided by `energy_el_dhw`. Same rules as the heating value.",
     "Gesamt-COP des Warmwassers: `energy_th_dhw` geteilt durch `energy_el_dhw`. Dieselben Regeln wie beim "
     "Heizen.", "INT")
_add("hours_hp", "energy",
     "Operating hours of the compressor. That 10404 is an hour counter is observation, "
     "python-luxtronik lists it as unknown.",
     "Betriebsstunden des Verdichters. Dass 10404 ein Stundenzähler ist, ist Beobachtung; "
     "python-luxtronik führt es als unbekannt.", "OBS")
_add("hours_heating", "energy",
     "Operating hours of heating. Interpretation as an hour counter is observation only.",
     "Betriebsstunden des Heizens. Die Deutung als Stundenzähler ist nur Beobachtung.", "OBS")
_add("hours_dhw", "energy",
     "Operating hours of hot water. Interpretation as an hour counter is observation only.",
     "Betriebsstunden des Warmwassers. Die Deutung als Stundenzähler ist nur Beobachtung.", "OBS")

# ------------------------------------------------------------------ status
_add("operating_mode", "status",
     "What the heat pump is doing right now. A single value: with several demands it names the one that is "
     "served. *No request* means the heat pump idles. *Utility lockout* is the EVU block.",
     "Was die Wärmepumpe gerade tut. Ein einzelner Wert: Bei mehreren Anforderungen nennt er die, die bedient "
     "wird. *Keine Anforderung* heißt, die Wärmepumpe ruht. *EVU-Sperre* ist die Sperre des Netzbetreibers.", "PL, FW")
_add("heat_generator_state", "status",
     "Bit mask of the running heat generators: 1 = VD1, 2 = VD2, 4 = ZWE1, 8 = ZWE2, 16 = ZWE3. 0 = all idle. The "
     "binary sensors below show the single bits; this sensor is the sum.",
     "Bitmaske der laufenden Wärmeerzeuger: 1 = VD1, 2 = VD2, 4 = ZWE1, 8 = ZWE2, 16 = ZWE3. 0 = alle aus. Die "
     "Binärsensoren darunter zeigen die einzelnen Bits; dieser Sensor ist die Summe.", "PL")
_add("compressor_1", "status",
     "Compressor 1 (VD1) runs. Bit 0 of the heat generator mask.",
     "Verdichter 1 (VD1) läuft. Bit 0 der Wärmeerzeuger-Maske.", "PL")
_add("compressor_2", "status",
     "Compressor 2 (VD2) runs. Bit 1. Only meaningful with a second compressor. The same bit as "
     "`heatpump_vd2_status`.",
     "Verdichter 2 (VD2) läuft. Bit 1. Nur mit einem zweiten Verdichter sinnvoll. Dasselbe Bit wie "
     "`heatpump_vd2_status`.", "PL")
_add("aux_heater_1", "status",
     "Additional heat generator 1 (ZWE1) is active. Bit 2. One of the keys the Heat Pump Optimizer depends on.",
     "Zusätzlicher Wärmeerzeuger 1 (ZWE1) ist aktiv. Bit 2. Einer der Schlüssel, auf die der Heat Pump "
     "Optimizer angewiesen ist.", "PL")
_add("aux_heater_2", "status",
     "Additional heat generator 2 (ZWE2) is active. Bit 3. The same bit as `heatpump_zwe2_status`.",
     "Zusätzlicher Wärmeerzeuger 2 (ZWE2) ist aktiv. Bit 3. Dasselbe Bit wie `heatpump_zwe2_status`.", "PL")
_add("heatpump_vd2_status", "status",
     "Compressor 2 (VD2) runs, with the python-luxtronik name. Bit 1, the same as `compressor_2`.",
     "Verdichter 2 (VD2) läuft, mit dem Namen aus python-luxtronik. Bit 1, dasselbe wie `compressor_2`.", "PL")
_add("heatpump_zwe2_status", "status",
     "ZWE2 is active, with the python-luxtronik name. Bit 3, the same as `aux_heater_2`.",
     "ZWE2 ist aktiv, mit dem Namen aus python-luxtronik. Bit 3, dasselbe wie `aux_heater_2`.", "PL")
_add("heatpump_zwe3_status", "status",
     "ZWE3 is active. Bit 4. Needs firmware 3.90.1 or later.",
     "ZWE3 ist aktiv. Bit 4. Braucht Firmware 3.90.1 oder neuer.", "PL")
_add("heating_status", "status",
     "State of heating as a request: disabled, no request, requested but not yet running, running.",
     "Zustand des Heizens als Anforderung: deaktiviert, keine Anforderung, angefordert aber noch nicht laufend, "
     "laufend.", "PL",
     "0 = disabled, 1 = no request, 2 = requested, 3 = running",
     "0 = deaktiviert, 1 = keine Anforderung, 2 = angefordert, 3 = laufend")
_add("hot_water_status", "status",
     "State of hot water as a request: disabled, no request, requested but not yet running, running.",
     "Zustand des Warmwassers als Anforderung: deaktiviert, keine Anforderung, angefordert aber noch nicht "
     "laufend, laufend.", "PL",
     "0 = disabled, 1 = no request, 2 = requested, 3 = running",
     "0 = deaktiviert, 1 = keine Anforderung, 2 = angefordert, 3 = laufend")
_add("cooling_status", "status",
     "State of cooling as a request: disabled, no request, requested but not yet running, running. Needs "
     "*cooling* in the equipment.",
     "Zustand des Kühlens als Anforderung: deaktiviert, keine Anforderung, angefordert aber noch nicht laufend, "
     "laufend. Braucht *Kühlung* in der Ausstattung.", "PL",
     "0 = disabled, 1 = no request, 2 = requested, 3 = running",
     "0 = deaktiviert, 1 = keine Anforderung, 2 = angefordert, 3 = laufend")
_add("pool_status", "status",
     "State of pool heating as a request: disabled, no request, requested but not yet running, running. Needs "
     "*pool* in the equipment.",
     "Zustand der Pool-Heizung als Anforderung: deaktiviert, keine Anforderung, angefordert aber noch nicht "
     "laufend, laufend. Braucht *Pool* in der Ausstattung.", "PL",
     "0 = disabled, 1 = no request, 2 = requested, 3 = running",
     "0 = deaktiviert, 1 = keine Anforderung, 2 = angefordert, 3 = laufend")
_add("error_number", "status",
     "Current error code of the controller. 0 means no error. The meaning of each code is listed in "
     "python-luxtronik (`Errorcode` in `datatypes.py`, for example 701 low pressure, 703 frost protection, "
     "705 motor protection).",
     "Aktueller Fehlercode der Regelung. 0 heißt kein Fehler. Die Bedeutung jedes Codes steht in "
     "python-luxtronik (`Errorcode` in `datatypes.py`, zum Beispiel 701 Niederdruck, 703 Frostschutz, 705 "
     "Motorschutz).", "PL",
     "0 = no error, otherwise the error code", "0 = kein Fehler, sonst der Fehlercode")
_add("online", "status",
     "On as long as the last poll of the heat pump succeeded. Unlike the other entities it never becomes "
     "unavailable: the state itself says whether the SHI answers. After 10 minutes of failed polls a repair "
     "issue is raised.",
     "An, solange die letzte Abfrage der Wärmepumpe erfolgreich war. Anders als die anderen Entitäten wird sie nie "
     "nicht verfügbar: Der Zustand selbst sagt, ob die SHI antwortet. Nach 10 Minuten fehlgeschlagener Abfragen "
     "entsteht ein Reparaturhinweis.", "INT")

# ------------------------------------------------------------------ blocks
_add("heating_block", "blocks",
     "Blocks heating. **Only heating:** hot water keeps running. Off (0) = normal operation. Read back after "
     "every write. One of the keys the Heat Pump Optimizer depends on. Not restored after a reset.",
     "Sperrt das Heizen. **Nur das Heizen:** Das Warmwasser läuft weiter. Aus (0) = Normalbetrieb. Wird nach jedem "
     "Schreiben zurückgelesen. Einer der Schlüssel, auf die der Heat Pump Optimizer angewiesen ist. Wird nach "
     "einem Reset nicht wiederhergestellt.", "PL, INT")
_add("dhw_block", "blocks",
     "Blocks hot water production. While it is on, the hot water mode cannot be set (owner measurement) and the "
     "restore of the hot water group waits. One of the keys the Heat Pump Optimizer depends on.",
     "Sperrt die Warmwasserbereitung. Solange sie an ist, lässt sich die Warmwasser-Betriebsart nicht setzen "
     "(Messung des Eigentümers), und die Wiederherstellung der Warmwasser-Gruppe wartet. Einer der Schlüssel, auf "
     "die der Heat Pump Optimizer angewiesen ist.", "PL, M")
_add("cooling_block", "blocks",
     "Blocks passive and active cooling. Needs *cooling* in the equipment. Frequent switching may wear heat pump "
     "and hydraulics.",
     "Sperrt passives und aktives Kühlen. Braucht *Kühlung* in der Ausstattung. Häufiges Schalten kann Wärmepumpe "
     "und Hydraulik belasten.", "PL")
_add("pool_block", "blocks",
     "Blocks pool heating. Needs *pool* in the equipment. Frequent switching may wear heat pump and hydraulics.",
     "Sperrt die Pool-Heizung. Braucht *Pool* in der Ausstattung. Häufiges Schalten kann Wärmepumpe und "
     "Hydraulik belasten.", "PL")

# ------------------------------------------------------------------ heating control
_add("climate_heating", "heating",
     "Thermostat view of the heating circuit. HVAC mode `auto` = control mode 0 (the heat pump controls itself, "
     "heating goes on); `heat` = setpoint, offset or level. **There is no `off`:** use the heating block to stop "
     "heating. The target is the heating setpoint, the current temperature is the **return** temperature. "
     "Attributes: control mode, `setpoint_active`, `effective_target`, heating blocked. Refuses a target outside "
     "mode `setpoint`. `hvac_action`: heating, idle, or off while blocked.",
     "Thermostat-Sicht auf den Heizkreis. HVAC-Modus `auto` = Betriebsart 0 (die Wärmepumpe regelt selbst, es wird "
     "weiter geheizt); `heat` = Sollwert, Anhebung oder Stufe. **Es gibt kein `off`:** Zum Stoppen des Heizens "
     "dient die Heizungs-Sperre. Der Zielwert ist der Heizungs-Sollwert, die aktuelle Temperatur ist die "
     "**Rücklauf**temperatur. Attribute: Betriebsart, `setpoint_active`, `effective_target`, Heizen gesperrt. "
     "Lehnt einen Zielwert außerhalb der Betriebsart `setpoint` ab. `hvac_action`: heating, idle, oder off bei "
     "Sperre.", "INT, PL, M")
_add("cfg_heating_mode", "heating",
     "Control mode of the heating circuit (see the table above). 0 does not switch heating off.",
     "Betriebsart des Heizkreises (siehe Tabelle oben). 0 schaltet das Heizen nicht aus.", "PL")
_add("cfg_heating_setpoint", "heating",
     "Heating setpoint, a **return temperature** (tRL) that replaces the controller's target. Only in mode "
     "`setpoint`. Measured: `return_target` followed the written value. The controller may limit it. After a reset "
     "it reads a stored or default value, not 0. One of the keys the Heat Pump Optimizer depends on.",
     "Heizungs-Sollwert, eine **Rücklauftemperatur** (tRL), die den Sollwert der Regelung ersetzt. Nur in der "
     "Betriebsart `setpoint`. Gemessen: `return_target` folgte dem geschriebenen Wert. Die Regelung kann ihn "
     "begrenzen. Nach einem Reset liest er einen gespeicherten oder Standardwert, nicht 0. Einer der Schlüssel, "
     "auf die der Heat Pump Optimizer angewiesen ist.", "PL, M, FW")
_add("cfg_heating_offset", "heating",
     "Offset in kelvin added to the controller's current return target, so in effect a parallel shift of the "
     "heating curve. Only in mode `offset`. Negative values are allowed.",
     "Anhebung in Kelvin auf den aktuellen Rücklauf-Sollwert der Regelung, wirkt also wie eine Parallelverschiebung "
     "der Heizkurve. Nur in der Betriebsart `offset`. Negative Werte sind erlaubt.", "PL, INT")
_add("cfg_heating_level", "heating",
     "Level correction of the heating target. 0 = normal (no correction). What *increased*, *increased 2* and "
     "*decreased* change, and by how much, is **open**: python-luxtronik marks it as not analysed, and the "
     "firmware only proves one increase and one decrease direction.",
     "Stufenkorrektur des Heiz-Sollwerts. 0 = normal (keine Korrektur). Was *erhöht*, *erhöht 2* und *abgesenkt* "
     "ändern und um wie viel, ist **ungeklärt**: python-luxtronik führt es als nicht analysiert, und die "
     "Firmware belegt nur eine Erhöhen- und eine Absenken-Richtung.", "PL, FW")
_add("cfg_room_setpoint", "heating",
     "Room temperature setpoint for the room control unit (RBE), the firmware's writable register "
     "`RBE_RT_Soll`. Needs the *room unit* in the equipment. The range 20 to 40 °C is a decision of the owner, "
     "not a register fact. What the controller does with the value is **not verified** (open).",
     "Raumtemperatur-Sollwert für die Raumeinheit (RBE), das schreibbare Firmware-Register `RBE_RT_Soll`. Braucht "
     "die *Raumeinheit* in der Ausstattung. Der Bereich 20 bis 40 °C ist eine Entscheidung des Eigentümers, "
     "kein Registerfakt. Was die Regelung mit dem Wert tut, ist **nicht überprüft** (ungeklärt).", "FW, INT")

# ------------------------------------------------------------------ hot water control
_add("water_heater_dhw", "hot_water",
     "Water heater view of hot water. Operations: no influence (raw 0), setpoint, offset, level; **no `off`**. "
     "Target = hot water setpoint, current = hot water temperature. Attributes `setpoint_active` and "
     "`effective_target`. Refuses a target outside mode `setpoint`. The Heat Pump Optimizer does not control hot "
     "water through it.",
     "Water-Heater-Sicht auf das Warmwasser. Betriebsarten: keine Vorgabe (roh 0), Sollwert, Anhebung, Stufe; "
     "**kein `off`**. Ziel = Warmwasser-Sollwert, aktuell = Warmwassertemperatur. Attribute `setpoint_active` und "
     "`effective_target`. Lehnt einen Zielwert außerhalb der Betriebsart `setpoint` ab. Der Heat Pump Optimizer "
     "steuert das Warmwasser nicht darüber.", "INT, PL")
_add("cfg_dhw_mode", "hot_water",
     "Control mode of hot water. 0 does not switch hot water off. Takes effect with a delay of about 10 s; can only "
     "be set while the hot water block is off (see above).",
     "Betriebsart des Warmwassers. 0 schaltet das Warmwasser nicht aus. Wirkt mit etwa 10 s Verzögerung; lässt "
     "sich nur setzen, solange die Warmwasser-Sperre aus ist (siehe oben).", "PL, FW, M")
_add("cfg_dhw_setpoint", "hot_water",
     "Hot water setpoint in °C. Only in mode `setpoint`. Deferred commit like the rest of the group. Mind the "
     "Legionella advice at the top of the hot water temperatures.",
     "Warmwasser-Sollwert in °C. Nur in der Betriebsart `setpoint`. Verzögerte Übernahme wie der Rest der Gruppe. "
     "Beachte den Legionellen-Hinweis bei den Warmwassertemperaturen.", "PL, FW, WEB")
_add("cfg_dhw_offset", "hot_water",
     "Offset in kelvin added to the controller's hot water target. Only in mode `offset`. Deferred commit.",
     "Anhebung in Kelvin auf den Warmwasser-Sollwert der Regelung. Nur in der Betriebsart `offset`. Verzögerte "
     "Übernahme.", "PL, FW")
_add("cfg_dhw_level", "hot_water",
     "Level correction of the hot water target. 0 = normal. The effect of the other levels is **open** (see "
     "heating level). Deferred commit.",
     "Stufenkorrektur des Warmwasser-Sollwerts. 0 = normal. Die Wirkung der anderen Stufen ist **ungeklärt** "
     "(siehe Heizungs-Stufe). Verzögerte Übernahme.", "PL, FW")
_add("circulation", "hot_water",
     "Switches the hot water circulation pump on, but only if no time schedule is set up for it in the "
     "controller. Needs firmware 3.92.0 or later. One of the keys the Heat Pump Optimizer depends on. The "
     "heating circulation pumps cannot be controlled through the SHI.",
     "Schaltet die Warmwasser-Zirkulationspumpe ein, aber nur, wenn in der Regelung kein Zeitprogramm dafür "
     "eingerichtet ist. Braucht Firmware 3.92.0 oder neuer. Einer der Schlüssel, auf die der Heat Pump "
     "Optimizer angewiesen ist. Die Heizungs-Umwälzpumpen lassen sich über die SHI nicht steuern.", "PL")
_add("extra_dhw", "hot_water",
     "Starts extra hot water: heating runs until the maximum temperature is reached. Needs firmware 3.92.0 or "
     "later. Whether the controller resets it by itself afterwards (a one-shot) is **open**; because of that it "
     "is neither restored after a reset nor counted as an external change.",
     "Startet Extra-Warmwasser: Es wird geheizt, bis die Höchsttemperatur erreicht ist. Braucht Firmware 3.92.0 "
     "oder neuer. Ob die Regelung es danach selbst zurücksetzt (Einmalschalter), ist **ungeklärt**; deshalb wird "
     "es nach einem Reset nicht wiederhergestellt und nicht als externe Änderung gezählt.", "PL, INT")

# ------------------------------------------------------------------ cooling / pool
_add("cooling_configured", "cooling_pool",
     "Cooling is configured in the controller.", "Kühlen ist in der Regelung konfiguriert.", "PL")
_add("pool_configured", "cooling_pool",
     "Pool heating is configured in the controller.", "Pool-Heizen ist in der Regelung konfiguriert.", "PL")
_add("cooling_release", "cooling_pool",
     "The cooling release condition of the controller is met. Only valid if cooling is configured.",
     "Die Kühlfreigabe-Bedingung der Regelung ist erfüllt. Nur gültig, wenn Kühlen konfiguriert ist.", "PL")

# ------------------------------------------------------------------ power limit
_add("cfg_power_limit_mode", "power_limit",
     "Power limit mode: no limit (normal operation), soft limit (recommended for PV surplus), hard limit (only "
     "for §14a EnWG, may reduce comfort). Needs a matching value.",
     "Modus der Leistungsbegrenzung: keine Begrenzung (Normalbetrieb), weiche Begrenzung (empfohlen bei "
     "PV-Überschuss), harte Begrenzung (nur für §14a EnWG, kann den Komfort mindern). Braucht einen passenden "
     "Wert.", "PL")
_add("cfg_power_limit", "power_limit",
     "Maximum allowed electrical power of the heat pump in kW, effective according to the limit mode. Not "
     "restored after a reset.",
     "Höchste zulässige elektrische Leistung der Wärmepumpe in kW, wirksam gemäß Modus. Wird nach einem Reset "
     "nicht wiederhergestellt.", "PL")

# ------------------------------------------------------------------ overall heating
_add("cfg_overall_mode", "overall",
     "Control mode of all heating functions at once (no setpoint available). Disabled by default; effect not "
     "proven.",
     "Betriebsart aller Heizfunktionen zugleich (kein Sollwert verfügbar). Standardmäßig deaktiviert; Wirkung "
     "nicht belegt.", "PL, M")
_add("cfg_overall_offset", "overall",
     "Temperature correction in kelvin for all heating functions. Disabled by default; effect not proven.",
     "Temperaturkorrektur in Kelvin für alle Heizfunktionen. Standardmäßig deaktiviert; Wirkung nicht belegt.",
     "PL, M")
_add("cfg_overall_level", "overall",
     "Level for all heating functions. Disabled by default; effect not proven, and the effect of the levels is "
     "open anyway.",
     "Stufe für alle Heizfunktionen. Standardmäßig deaktiviert; Wirkung nicht belegt, und die Wirkung der "
     "Stufen ist ohnehin ungeklärt.", "PL, M")

# ------------------------------------------------------------------ system
_add("buffer_type", "system",
     "Type of the buffer tank configured in the controller (see the background above). The assignment of the "
     "values is the one in the table.",
     "Typ des in der Regelung eingestellten Pufferspeichers (siehe Hintergrund oben). Die Zuordnung der Werte "
     "steht in der Tabelle.", "PL")
_add("switching_lock_minutes", "system",
     "Minimum off time before the heat pump may start again (*Schaltspielsperre*), in minutes. The reference "
     "firmware returns the constant 20.",
     "Mindest-Ausschaltzeit, bevor die Wärmepumpe wieder starten darf (*Schaltspielsperre*), in Minuten. Die "
     "Referenz-Firmware liefert die Konstante 20.", "PL, FW")
_add("min_runtime_minutes", "system",
     "Minimum runtime of the heat pump, in minutes. The reference firmware returns the constant 20.",
     "Mindestlaufzeit der Wärmepumpe in Minuten. Die Referenz-Firmware liefert die Konstante 20.", "PL, FW")
_add("fw_platform", "system",
     "First number of the firmware version. On the reference installation the three registers read 3, 92 and 3: "
     "firmware V3.92.3.",
     "Erste Zahl der Firmware-Version. An der Referenzanlage lesen die drei Register 3, 92 und 3: Firmware "
     "V3.92.3.", "FW, OBS")
_add("fw_major", "system",
     "Second number of the firmware version (92 on the reference installation). The integration needs 92 or "
     "newer for the circulation pump and extra hot water; with older firmware it raises a repair issue.",
     "Zweite Zahl der Firmware-Version (92 an der Referenzanlage). Die Integration braucht 92 oder neuer für "
     "Zirkulationspumpe und Extra-Warmwasser; bei älterer Firmware erzeugt sie einen Reparaturhinweis.",
     "FW, OBS")
_add("fw_minor", "system",
     "Third number of the firmware version (3 on the reference installation).",
     "Dritte Zahl der Firmware-Version (3 an der Referenzanlage).", "FW, OBS")

_caps = {
    "cap_heating": ("heating", "Heizen"),
    "cap_hot_water": ("hot water", "Warmwasser"),
    "cap_cooling": ("cooling", "Kühlen"),
    "cap_pool": ("pool", "Pool"),
    "cap_room_controller": ("a room controller", "ein Raumregler"),
    "cap_mk1_heating": ("heating of mixing circuit 1", "Heizen von Mischkreis 1"),
    "cap_mk1_cooling": ("cooling of mixing circuit 1", "Kühlen von Mischkreis 1"),
    "cap_mk2_heating": ("heating of mixing circuit 2", "Heizen von Mischkreis 2"),
    "cap_mk2_cooling": ("cooling of mixing circuit 2", "Kühlen von Mischkreis 2"),
    "cap_mk3_heating": ("heating of mixing circuit 3", "Heizen von Mischkreis 3"),
    "cap_mk3_cooling": ("cooling of mixing circuit 3", "Kühlen von Mischkreis 3"),
}
for _k, (_en, _de) in _caps.items():
    _add(_k, "system",
         f"Equipment flag: the installation has {_en}. Pre-selects the equipment in the setup dialog. Not in "
         "python-luxtronik, backed by observation only.",
         f"Ausstattungs-Flag: Die Anlage hat {_de}. Wählt die Ausstattung im Einrichtungsdialog vor. Nicht in "
         "python-luxtronik, nur durch Beobachtung belegt.", "OBS")

# ------------------------------------------------------------------ mixing circuits (templates)
for _n in (1, 2, 3):
    _k = f"mk{_n}"
    _add(f"{_k}_flow", "mixing_temps",
         f"Current flow temperature of mixing circuit {_n}.",
         f"Aktuelle Vorlauftemperatur von Mischkreis {_n}.", "PL")
    _add(f"{_k}_flow_target", "mixing_temps",
         f"Target flow temperature of mixing circuit {_n} (the `effective_target` of its setpoint).",
         f"Vorlauf-Sollwert von Mischkreis {_n} (das `effective_target` seines Sollwerts).", "PL")
    _add(f"{_k}_flow_min", "mixing_temps",
         f"Minimum flow temperature of mixing circuit {_n}.",
         f"Niedrigste Vorlauftemperatur von Mischkreis {_n}.", "PL")
    _add(f"{_k}_flow_max", "mixing_temps",
         f"Maximum flow temperature of mixing circuit {_n}.",
         f"Höchste Vorlauftemperatur von Mischkreis {_n}.", "PL")
    _add(f"cfg_{_k}_mode", "mixing",
         f"Control mode of mixing circuit {_n} heating. 0 does not switch the circuit off.",
         f"Betriebsart des Heizens von Mischkreis {_n}. 0 schaltet den Kreis nicht aus.", "PL")
    _add(f"cfg_{_k}_setpoint", "mixing",
         f"Flow temperature setpoint of mixing circuit {_n}. Only in mode `setpoint`. The controller may limit it.",
         f"Vorlauf-Sollwert von Mischkreis {_n}. Nur in der Betriebsart `setpoint`. Die Regelung kann ihn "
         "begrenzen.", "PL")
    _add(f"cfg_{_k}_offset", "mixing",
         f"Offset in kelvin on the flow temperature of mixing circuit {_n}. Only in mode `offset`.",
         f"Anhebung in Kelvin auf die Vorlauftemperatur von Mischkreis {_n}. Nur in der Betriebsart `offset`.", "PL")
    _add(f"cfg_{_k}_level", "mixing",
         f"Level correction of mixing circuit {_n}. 0 = normal; the effect of the other levels is **open**.",
         f"Stufenkorrektur von Mischkreis {_n}. 0 = normal; die Wirkung der anderen Stufen ist **ungeklärt**.",
         "PL")
    _add(f"cfg_{_k}_cool_mode", "cooling_pool",
         f"Control mode of mixing circuit {_n} cooling. 0 does not switch cooling off. Needs the circuit and "
         "*cooling* in the equipment.",
         f"Betriebsart des Kühlens von Mischkreis {_n}. 0 schaltet das Kühlen nicht aus. Braucht den Kreis und "
         "*Kühlung* in der Ausstattung.", "PL")
    _add(f"cfg_{_k}_cool_setpoint", "cooling_pool",
         f"Cooling flow temperature setpoint of mixing circuit {_n}. Only in mode `setpoint`.",
         f"Kühl-Vorlauf-Sollwert von Mischkreis {_n}. Nur in der Betriebsart `setpoint`.", "PL")
    _add(f"cfg_{_k}_cool_offset", "cooling_pool",
         f"Offset in kelvin on the cooling flow temperature of mixing circuit {_n}. Only in mode `offset`.",
         f"Anhebung in Kelvin auf die Kühl-Vorlauftemperatur von Mischkreis {_n}. Nur in der Betriebsart "
         "`offset`.", "PL")

# ------------------------------------------------------------------ raw values (template per address)
RAW_TEXT: dict[int, tuple[str, str, str]] = {
    10113: ("Unknown input register, function not analysed.", "Unbekanntes Eingangsregister, Funktion nicht "
            "analysiert.", "PL"),
    10352: ("Unknown input register, function not analysed.", "Unbekanntes Eingangsregister, Funktion nicht "
            "analysiert.", "PL"),
    10353: ("Unknown input register, function not analysed.", "Unbekanntes Eingangsregister, Funktion nicht "
            "analysiert.", "PL"),
    10410: ("High word of a 32-bit counter with the divisor 3600 on the wire (an hour counter). Together with "
            "10411. Meaning open.",
            "Oberes Wort eines 32-Bit-Zählers mit dem Teiler 3600 (ein Stundenzähler). Zusammen mit 10411. "
            "Bedeutung ungeklärt.", "FW"),
    10411: ("Low word of the 32-bit counter that starts at 10410. Meaning open.",
            "Unteres Wort des 32-Bit-Zählers, der bei 10410 beginnt. Bedeutung ungeklärt.", "FW"),
    10412: ("High word of a 32-bit counter with the unusual divisor 7200; the unit is unclear (open). Together "
            "with 10413.",
            "Oberes Wort eines 32-Bit-Zählers mit dem ungewöhnlichen Teiler 7200; die Einheit ist unklar "
            "(ungeklärt). Zusammen mit 10413.", "FW"),
    10413: ("Low word of the 32-bit counter that starts at 10412. Meaning open.",
            "Unteres Wort des 32-Bit-Zählers, der bei 10412 beginnt. Bedeutung ungeklärt.", "FW"),
    10416: ("High word of a 32-bit counter with the divisor 3600 (an hour counter). Together with 10417. "
            "Meaning open.",
            "Oberes Wort eines 32-Bit-Zählers mit dem Teiler 3600 (ein Stundenzähler). Zusammen mit 10417. "
            "Bedeutung ungeklärt.", "FW"),
    10417: ("Low word of the 32-bit counter that starts at 10416. Meaning open.",
            "Unteres Wort des 32-Bit-Zählers, der bei 10416 beginnt. Bedeutung ungeklärt.", "FW"),
    10500: ("Time value, meaning open.", "Zeitwert, Bedeutung ungeklärt.", "FW"),
    10501: ("Time value; the firmware divides seconds by 60, so the wire value is in minutes. Meaning open.",
            "Zeitwert; die Firmware teilt Sekunden durch 60, der Wert auf dem Bus ist also in Minuten. Bedeutung "
            "ungeklärt.", "FW"),
    10502: ("Time value; the firmware divides seconds by 60, so the wire value is in minutes. Meaning open.",
            "Zeitwert; die Firmware teilt Sekunden durch 60, der Wert auf dem Bus ist also in Minuten. Bedeutung "
            "ungeklärt.", "FW"),
}
RAW_DEFAULT = (
    "Unknown input register, function not analysed. Nothing is known beyond the address.",
    "Unbekanntes Eingangsregister, Funktion nicht analysiert. Außer der Adresse ist nichts bekannt.",
    "PL",
)
