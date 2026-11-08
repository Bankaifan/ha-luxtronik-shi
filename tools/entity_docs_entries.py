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
     "Maximum allowed return temperature (controller parameter *Einst_TRBegr*). The firmware clamps the heating "
     "setpoint to this value: the SHI cannot raise the return target above it (proven).",
     "Höchste zulässige Rücklauftemperatur (Reglerparameter *Einst_TRBegr*). Die Firmware begrenzt den "
     "Heizungs-Sollwert auf diesen Wert: Die SHI kann den Rücklauf-Sollwert nicht darüber heben (belegt).", "PL, FW")
_add("return_min_target", "temps",
     "Minimum target return temperature (controller parameter 979). The firmware clamps the heating setpoint to "
     "this value, and uses it as the target while heating is blocked (`heating_block`), the heating mode is *off* "
     "at the controller or the heating limit is active (proven).",
     "Niedrigster Rücklauf-Sollwert (Reglerparameter 979). Die Firmware begrenzt den Heizungs-Sollwert auf diesen "
     "Wert und nutzt ihn als Sollwert, solange das Heizen gesperrt ist (`heating_block`), die Betriebsart Heizung "
     "am Regler *Aus* ist oder die Heizgrenze greift (belegt).", "PL, FW")
_add("flow", "temps",
     "Current flow temperature, the temperature of the water leaving the heat pump towards the heating system.",
     "Aktuelle Vorlauftemperatur, also die Temperatur des Wassers, das die Wärmepumpe Richtung Heizungsanlage "
     "verlässt.", "PL")
_add("room", "temps",
     "Room temperature measured by the room control unit (RBE+). Only available with such a unit; the entity "
     "needs the *room unit* selected in the equipment and is disabled by default.",
     "Raumtemperatur, gemessen von der Raumeinheit (RBE+). Nur mit einer solchen Einheit vorhanden; die "
     "Entität braucht die gewählte *Raumeinheit* in der Ausstattung und ist standardmäßig deaktiviert.", "PL")
_add("heating_demand_border", "temps",
     "Demand border of heating (firmware item *Heating demand border*). **Not the outside heating limit "
     "(Heizgrenze) and not a parameter:** the firmware tracks it as the effective return target minus the heating "
     "hysteresis (in mode `setpoint` it follows the SHI setpoint). Below it heating is requested; python-luxtronik "
     "adds that the soft power limit is ignored below it. Name changed in 0.17.0, key `heating_limit` renamed in "
     "0.18.0 (the entity ID stays) (proven).",
     "Anforderungsgrenze des Heizens (Firmware-Item *Heating demand border*). **Nicht die Heizgrenze "
     "(Außentemperatur) und kein Parameter:** Die Firmware führt sie als wirksamen Rücklauf-Sollwert minus "
     "Heiz-Hysterese nach (in der Betriebsart `setpoint` folgt sie dem SHI-Sollwert). Darunter wird Heizen "
     "angefordert; laut python-luxtronik wird darunter die weiche Leistungsbegrenzung ignoriert. Name seit 0.17.0 "
     "geändert, Schlüssel `heating_limit` in 0.18.0 umbenannt (die Entity-ID bleibt) (belegt).", "FW, PL")
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
     "30.0 °C (a fixed firmware constant, not a measurement), which is also the lower limit of the setpoint number. "
     "Disabled by default for new installations.",
     "Niedrigste einstellbare Warmwassertemperatur. In der Referenz-Firmware liefert das Register eine Konstante, "
     "30,0 °C (eine feste Firmware-Konstante, kein Messwert); das ist auch die Untergrenze der Zahl Sollwert. Für "
     "neue Installationen standardmäßig deaktiviert.", "PL, FW")
_add("dhw_max", "dhw_temps",
     "Maximum hot water temperature (controller parameter *Einst_BW_max*). Every hot water target is limited to it, "
     "the SHI setpoint included: a setpoint above it is accepted but has no effect beyond this value (proven).",
     "Maximale Warmwassertemperatur (Reglerparameter *Einst_BW_max*). Jedes Warmwasser-Ziel wird darauf begrenzt, "
     "auch der SHI-Sollwert: Ein Sollwert darüber wird angenommen, wirkt aber nur bis zu diesem Wert (belegt).",
     "PL, FW")
_add("dhw_demand_border", "dhw_temps",
     "Demand border of hot water (firmware item *DHW Demand border*): the effective hot water target minus the "
     "hysteresis, tracked by the firmware, not a parameter. Below it hot water is requested; python-luxtronik adds "
     "that the soft power limit is ignored below it. Name changed in 0.17.0, key `dhw_limit` renamed in 0.18.0 (the "
     "entity ID stays) (proven).",
     "Anforderungsgrenze des Warmwassers (Firmware-Item *DHW Demand border*): der wirksame Warmwasser-Sollwert "
     "minus Hysterese, von der Firmware nachgeführt, kein Parameter. Darunter wird Warmwasser angefordert; laut "
     "python-luxtronik wird darunter die weiche Leistungsbegrenzung ignoriert. Name seit 0.17.0 geändert, "
     "Schlüssel `dhw_limit` in 0.18.0 umbenannt (die Entity-ID bleibt) (belegt).", "FW, PL")

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
     "COP over the last 10 minutes: thermal energy divided by electrical energy, both integrated from the "
     "two power sensors over a trailing window. A window instead of one quotient, because both registers "
     "have a resolution of 100 W and are not sampled at the same instant, which made the instantaneous "
     "ratio jump (8.0 or more right after a compressor start). Shown as *unknown* while the window holds "
     "too little electrical energy (compressor off or just started), after a gap in the readings, and "
     "when the result is not plausible, which includes a net thermal energy that is not positive (a long "
     "defrost). Defrost inside a run counts, it is real consumption. The window and limits are a design "
     "choice of the integration, not a register fact.",
     "COP der letzten 10 Minuten: Wärmeenergie geteilt durch elektrische Energie, beide aus den zwei "
     "Leistungssensoren über ein mitlaufendes Fenster aufsummiert. Ein Fenster statt eines einzelnen "
     "Quotienten, weil beide Register 100 W Auflösung haben und nicht im selben Augenblick abgetastet "
     "werden; das ließ den Momentanwert springen (8,0 oder mehr direkt nach dem Verdichterstart). Wird als "
     "*unbekannt* gezeigt, solange das Fenster zu wenig elektrische Energie enthält (Verdichter aus oder "
     "gerade gestartet), nach einer Lücke in den Messwerten und wenn das Ergebnis nicht plausibel ist, "
     "wozu eine nicht positive Netto-Wärmeenergie gehört (langes Abtauen). Abtauen innerhalb eines Laufs "
     "zählt, es ist echter Verbrauch. Fenster und Grenzen sind eine Festlegung der Integration, kein "
     "Registerfakt.", "INT")

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
     "Operating hours of the compressor: firmware counter *Zaehler_BetrZeitWP* (parameter 668), seconds divided "
     "by 3600 on the wire (proven; python-luxtronik lists 10404 as unknown).",
     "Betriebsstunden des Verdichters: Firmware-Zähler *Zaehler_BetrZeitWP* (Parameter 668), Sekunden geteilt "
     "durch 3600 auf dem Bus (belegt; python-luxtronik führt 10404 als unbekannt).", "FW, OBS")
_add("hours_heating", "energy",
     "Operating hours of heating: firmware counter *Zaehler_BetrZeitHz* (parameter 728), hours (proven).",
     "Betriebsstunden des Heizens: Firmware-Zähler *Zaehler_BetrZeitHz* (Parameter 728), Stunden (belegt).",
     "FW, OBS")
_add("hours_dhw", "energy",
     "Operating hours of hot water: firmware counter *Zaehler_BetrZeitBW* (parameter 729), hours (proven).",
     "Betriebsstunden des Warmwassers: Firmware-Zähler *Zaehler_BetrZeitBW* (Parameter 729), Stunden (belegt).",
     "FW, OBS")
_add("hours_cooling", "energy",
     "Operating hours of cooling: firmware counter *Zaehler_BetrZeitKue* (parameter 730), hours. Needs *cooling* "
     "in the equipment. Same two registers as the raw values `raw_10410`/`raw_10411`, which keep their keys; "
     "the register is read once. New in 0.17.0 (proven, not measured: the reference installation does not cool).",
     "Betriebsstunden des Kühlens: Firmware-Zähler *Zaehler_BetrZeitKue* (Parameter 730), Stunden. Braucht "
     "*Kühlung* in der Ausstattung. Dieselben zwei Register wie die Rohwerte `raw_10410`/`raw_10411`, die ihre "
     "Schlüssel behalten; das Register wird einmal gelesen. Neu in 0.17.0 (belegt, nicht gemessen: die "
     "Referenzanlage kühlt nicht).", "FW")
_add("hours_solar", "energy",
     "Operating hours of the solar function: firmware counter *BSTD_Solar* (parameter 882), hours. Needs *solar* "
     "in the equipment (new option, pre-filled from the equipment flag `cap_solar`). Same registers as "
     "`raw_10416`/`raw_10417`. New in 0.17.0 (proven, not measured: no solar on the reference installation).",
     "Betriebsstunden der Solarfunktion: Firmware-Zähler *BSTD_Solar* (Parameter 882), Stunden. Braucht *Solar* "
     "in der Ausstattung (neue Option, vorbelegt aus dem Ausstattungs-Flag `cap_solar`). Dieselben Register wie "
     "`raw_10416`/`raw_10417`. Neu in 0.17.0 (belegt, nicht gemessen: keine Solaranlage an der Referenzanlage).",
     "FW")

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
_STATUS_EN = (" Reported as text, not as a number (the table shows the assignment); a value outside 0 to 3 is "
              "`unknown_<n>` and nothing is known about it.")
_STATUS_DE = (" Wird als Text gemeldet, nicht als Zahl (die Tabelle zeigt die Zuordnung); ein Wert außerhalb von 0 "
              "bis 3 ist `unknown_<n>`, darüber ist nichts bekannt.")
_add("heating_status", "status",
     "State of heating as a request: disabled, no request, requested but not yet running, running." + _STATUS_EN,
     "Zustand des Heizens als Anforderung: deaktiviert, keine Anforderung, angefordert aber noch nicht laufend, "
     "laufend." + _STATUS_DE, "PL")
_add("hot_water_status", "status",
     "State of hot water as a request: disabled, no request, requested but not yet running, running." + _STATUS_EN,
     "Zustand des Warmwassers als Anforderung: deaktiviert, keine Anforderung, angefordert aber noch nicht "
     "laufend, laufend." + _STATUS_DE, "PL")
_add("cooling_status", "status",
     "State of cooling as a request: disabled, no request, requested but not yet running, running. Needs "
     "*cooling* in the equipment." + _STATUS_EN,
     "Zustand des Kühlens als Anforderung: deaktiviert, keine Anforderung, angefordert aber noch nicht laufend, "
     "laufend. Braucht *Kühlung* in der Ausstattung." + _STATUS_DE, "PL")
_add("pool_status", "status",
     "State of pool heating as a request: disabled, no request, requested but not yet running, running. Needs "
     "*pool* in the equipment." + _STATUS_EN,
     "Zustand der Pool-Heizung als Anforderung: deaktiviert, keine Anforderung, angefordert aber noch nicht "
     "laufend, laufend. Braucht *Pool* in der Ausstattung." + _STATUS_DE, "PL")
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

_add("flow_return_difference", "temps",
     "Flow temperature minus return temperature, in K. The controller has no spread register, so this is "
     "calculated from `flow` and `return`, which are read anyway (no extra polling). Unavailable while either "
     "value is unavailable. It can be **negative or near zero** while the heat pump defrosts or when the "
     "circuit stands still; it is not clamped. Both sources have a resolution of 0.1 K and are not sampled at "
     "the same instant, so short jumps are noise. Unit K without a temperature class, so Home Assistant never "
     "converts it like an absolute temperature.",
     "Vorlauftemperatur minus Rücklauftemperatur, in K. Die Regelung hat kein Spreizungs-Register, daher wird der "
     "Wert aus `flow` und `return` berechnet, die ohnehin gelesen werden (keine zusätzliche Abfrage). Nicht "
     "verfügbar, solange einer der beiden Werte nicht verfügbar ist. Er kann beim Abtauen oder im Stillstand "
     "**negativ oder nahe null** sein und wird nicht begrenzt. Beide Quellen haben 0,1 K Auflösung und werden "
     "nicht im selben Augenblick abgetastet, kurze Sprünge sind daher Rauschen. Einheit K ohne Temperaturklasse, "
     "damit Home Assistant sie nie wie eine absolute Temperatur umrechnet.", "INT",
     "flow minus return (K), can be negative", "Vorlauf minus Rücklauf (K), kann negativ sein")
_add("cop_total", "energy",
     "Overall COP of all modes: `energy_th_total` divided by `energy_el_total`. Lifetime of the counters, **not** "
     "a JAZ, and different from the 10-minute `cop`: that one is the energy ratio of a trailing window of the "
     "power sensors and reacts within minutes, this one moves slowly and only shows the long-term average. Same "
     "rules as the heating value (*unknown* with too little electrical energy, an implausible result, or after "
     "a counter went backwards). `energy_th_total` needs firmware 3.92.0 or later.",
     "Gesamt-COP aller Betriebsarten: `energy_th_total` geteilt durch `energy_el_total`. Lebensdauer der Zähler, "
     "**keine** JAZ, und etwas anderes als der 10-Minuten-`cop`: Dieser ist das Energieverhältnis eines "
     "mitlaufenden Fensters der Leistungssensoren und reagiert binnen Minuten, dieser hier bewegt sich langsam "
     "und zeigt nur den langfristigen Durchschnitt. Dieselben Regeln wie beim Heizen (*unbekannt* bei zu wenig "
     "elektrischer Energie, unplausiblem Ergebnis oder wenn ein Zähler rückwärts lief). `energy_th_total` "
     "braucht Firmware 3.92.0 oder neuer.", "INT")
_add("fault", "status",
     "On when the error code `error_number` is not 0 (problem class). Calculated from that register, no extra "
     "polling; unavailable while it has no value. Which codes are real faults and which are warnings or "
     "lockouts is not distinguished: every code other than 0 switches it on (see `error_number` for the "
     "code list).",
     "An, wenn der Fehlercode `error_number` nicht 0 ist (Geräteklasse Problem). Aus diesem Register berechnet, "
     "keine zusätzliche Abfrage; nicht verfügbar, solange es keinen Wert hat. Ob ein Code eine echte Störung, "
     "eine Warnung oder eine Sperre ist, wird nicht unterschieden: Jeder Code außer 0 schaltet ihn ein (die "
     "Codeliste steht bei `error_number`).", "INT")
_add("defrost", "status",
     "On while `operating_mode` is `defrost`. Calculated, no extra polling. It follows the controller's "
     "operating mode, not an output: whether it switches at exactly the same time as the defrost valve output "
     "of the native Luxtronik interface has not been measured (open).",
     "An, solange `operating_mode` den Wert `defrost` hat. Berechnet, keine zusätzliche Abfrage. Er folgt der "
     "Betriebsart der Regelung, nicht einem Ausgang: Ob er genau gleichzeitig mit dem Abtauventil-Ausgang der "
     "nativen Luxtronik-Schnittstelle schaltet, wurde nicht gemessen (ungeklärt).", "INT")
_add("heating_running", "status",
     "On while `heating_status` is `running` (value 3). Calculated, no extra polling; unavailable while the "
     "status has no value. `requested` (a demand that is not served yet) is off.",
     "An, solange `heating_status` den Wert `running` (3) hat. Berechnet, keine zusätzliche Abfrage; nicht "
     "verfügbar, solange der Status keinen Wert hat. `requested` (Anforderung, die noch nicht bedient wird) "
     "ist aus.", "INT")
_add("dhw_running", "status",
     "On while `hot_water_status` is `running` (value 3). Calculated, no extra polling; unavailable while the "
     "status has no value. `requested` is off.",
     "An, solange `hot_water_status` den Wert `running` (3) hat. Berechnet, keine zusätzliche Abfrage; nicht "
     "verfügbar, solange der Status keinen Wert hat. `requested` ist aus.", "INT")
_add("power_limit_configured", "power_limit",
     "On when `cfg_power_limit_mode` is `soft` or `hard`, off for `none`. This reports the **configured mode**, "
     "not whether the limit currently reduces the power: how the controller reacts to the limit is not "
     "documented (open). Calculated, no extra polling; unavailable while the mode has no value.",
     "An, wenn `cfg_power_limit_mode` auf `soft` oder `hard` steht, aus bei `none`. Das meldet den "
     "**eingestellten Modus**, nicht, ob die Begrenzung die Leistung gerade tatsächlich senkt: Wie die "
     "Regelung auf die Begrenzung reagiert, ist nicht dokumentiert (ungeklärt). Berechnet, keine zusätzliche "
     "Abfrage; nicht verfügbar, solange der Modus keinen Wert hat.", "INT")

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

_add("block_mode", "blocks",
     "Operating mode as a view on the two blocks `heating_block` and `dhw_block`, for the Heat Pump Optimizer "
     "(point its *heat pump mode* option at this entity; it replaces a hand-written template select). Options: "
     "`heating_dhw` = no block, `heating` = hot water blocked, `dhw_hot_water` = heating blocked. **`dhw_hot_water` "
     "is also shown while both blocks are set**: three options cannot express that state, so use "
     "`block_power` for the real off. Choosing an option writes both blocks, releases first and then blocks, so a "
     "failure between the two writes leaves fewer blocks, never more. A write the heat pump does not take (read "
     "back differs) stops the sequence with an error. The option keys fold to the same letters as the labels "
     "`Heating + DHW`, `Heating` and `DHW (Hot Water)` that the optimizer knows. No extra polling. Not restored "
     "after a reset, like the blocks. Enabled by default on new installations only; on an existing installation "
     "enable it in the entity settings.",
     "Betriebsart als Sicht auf die beiden Sperren `heating_block` und `dhw_block`, für den Heat Pump Optimizer "
     "(dessen Option *Wärmepumpen-Modus* auf diese Entität zeigen lassen; sie ersetzt ein selbst geschriebenes "
     "Template-Select). Optionen: `heating_dhw` = keine Sperre, `heating` = Warmwasser gesperrt, "
     "`dhw_hot_water` = Heizen gesperrt. **`dhw_hot_water` wird auch angezeigt, wenn beide Sperren gesetzt "
     "sind**: Drei Optionen können diesen Zustand nicht ausdrücken, das echte Aus zeigt `block_power`. Eine "
     "Auswahl schreibt beide Sperren, erst Freigaben, dann Sperren; ein Fehler zwischen den beiden Schreibzugriffen "
     "lässt also weniger Sperren stehen, nie mehr. Übernimmt die Wärmepumpe einen Wert nicht (Rücklesen weicht "
     "ab), bricht die Folge mit einer Fehlermeldung ab. Die Optionsschlüssel ergeben gefaltet dieselben Buchstaben "
     "wie die Beschriftungen `Heating + DHW`, `Heating` und `DHW (Hot Water)`, die der Optimizer kennt. Kein "
     "zusätzliches Abfragen. Wird nach einem Reset nicht wiederhergestellt, wie die Sperren. Nur bei neuen "
     "Installationen standardmäßig aktiv; bei einer bestehenden Installation in den Entitäts-Einstellungen "
     "aktivieren.", "INT")
_add("block_power", "blocks",
     "On/off as a view on the two blocks: **off exactly when both `heating_block` and `dhw_block` are set**. "
     "Turning off sets both (hot water first, so heating still runs if the second write fails). Turning on "
     "releases only the hot water block, and only while both are set; the heating block stays as the "
     "`block_mode` select left it, so after turning on the select usually reads *hot water only* until the "
     "optimizer sets a mode. In any other state turning on does nothing. Replaces a hand-written template "
     "switch. No extra polling; not restored after a reset. Enabled by default on new installations only.",
     "Ein/Aus als Sicht auf die beiden Sperren: **aus genau dann, wenn `heating_block` und `dhw_block` beide "
     "gesetzt sind**. Ausschalten setzt beide (erst Warmwasser, damit bei einem Fehler des zweiten "
     "Schreibzugriffs weiter geheizt wird). Einschalten gibt nur die Warmwasser-Sperre frei, und nur solange "
     "beide gesetzt sind; die Heizungs-Sperre bleibt, wie das Select `block_mode` sie hinterlassen hat, das "
     "Select zeigt nach dem Einschalten also meist *Nur Warmwasser*, bis der Optimizer eine Betriebsart setzt. "
     "In jedem anderen Zustand tut Einschalten nichts. Ersetzt einen selbst geschriebenen Template-Schalter. "
     "Kein zusätzliches Abfragen; wird nach einem Reset nicht wiederhergestellt. Nur bei neuen Installationen "
     "standardmäßig aktiv.", "INT")

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
     "Heating setpoint, a **return temperature** (tRL) that replaces the heating curve. Only in mode `setpoint` and "
     "only while `cfg_overall_mode` is `no_influence`. Measured: `return_target` followed the written value. The firmware "
     "clamps the effect to [`return_min_target`, `return_limit`]; while heating is blocked (`heating_block`) the "
     "target is the minimum regardless. Firmware range 15.0 … 75.0 °C; a value outside it would reset the "
     "register to its default 35.0 °C, so the integration never sends one. After a reset it reads 35.0 °C. One "
     "of the keys the Heat Pump Optimizer depends on.",
     "Heizungs-Sollwert, eine **Rücklauftemperatur** (tRL), die die Heizkurve ersetzt. Nur in der Betriebsart "
     "`setpoint` und nur, solange `cfg_overall_mode` auf `no_influence` steht. Gemessen: `return_target` folgte dem "
     "geschriebenen Wert. Die Firmware begrenzt die Wirkung auf [`return_min_target`, `return_limit`]; bei "
     "gesperrtem Heizen (`heating_block`) gilt ohnehin das Minimum. Firmware-Bereich 15,0 … 75,0 °C; ein Wert "
     "außerhalb würde das Register auf den Standardwert 35,0 °C zurücksetzen, deshalb schickt die Integration "
     "keinen. Nach einem Reset liest er 35,0 °C. Einer der Schlüssel, auf die der Heat Pump Optimizer angewiesen "
     "ist.", "PL, M, FW")
_add("cfg_heating_offset", "heating",
     "Offset in kelvin added to the heating curve result, so in effect a parallel shift of the heating curve. "
     "Only in mode `offset` and while the overall mode is `no_influence`. Firmware range -20.0 … 20.0 K (proven); the "
     "result is clamped like the setpoint.",
     "Anhebung in Kelvin auf das Ergebnis der Heizkurve, wirkt also wie eine Parallelverschiebung der Heizkurve. "
     "Nur in der Betriebsart `offset` und solange die Gesamt-Betriebsart `no_influence` ist. Firmware-Bereich -20,0 … "
     "20,0 K (belegt); das Ergebnis wird wie der Sollwert begrenzt.", "PL, FW")
_add("cfg_heating_level", "heating",
     "Level correction of the heating target (proven): `normal` = raw 0 (no correction); `increased` **raises** "
     "the heating curve result by the controller parameter *Erhöhung Heizen* (written as raw 1; raw 2 uses the "
     "same parameter and shows as `increased` too, the former option `increased2` is gone); `decreased` = raw 3 "
     "**lowers** it by *Absenkung Heizen*. The amounts are set at the control panel (menu *Offsets*, -20 … "
     "+20 K in 0.5 K steps, parameters 1189/1190) and cannot be read or written over the SHI. Only in mode "
     "`level` and while the overall mode is `no_influence`.",
     "Stufenkorrektur des Heiz-Sollwerts (belegt): `normal` = roh 0 (keine Korrektur); `increased` **erhöht** das "
     "Heizkurven-Ergebnis um den Reglerparameter *Erhöhung Heizen* (geschrieben als roh 1; roh 2 nutzt denselben "
     "Parameter und zeigt ebenfalls `increased`, die frühere Option `increased2` gibt es nicht mehr); `decreased` "
     "= roh 3 **senkt** es um *Absenkung Heizen*. Die Beträge werden am Bedienteil eingestellt (Menü *Offsets*, "
     "-20 … +20 K in 0,5-K-Schritten, Parameter 1189/1190) und sind über die SHI weder lesbar noch schreibbar. "
     "Nur in der Betriebsart `level` und solange die Gesamt-Betriebsart `no_influence` ist.", "FW, PL")
_add("cfg_room_setpoint", "heating",
     "Room temperature setpoint for the room control unit (RBE), the firmware's writable register "
     "`RBE_RT_Soll`. Needs the *room unit* in the equipment. The range 20 to 40 °C is a decision of the owner, "
     "not a register fact. What the controller does with the value is **not verified** (open). The register binds "
     "the persisted parameter 1148: after a watchdog expiry it reads the persisted value, not a fixed default; "
     "available only with a connected room unit and an influence factor > 0 (proven).",
     "Raumtemperatur-Sollwert für die Raumeinheit (RBE), das schreibbare Firmware-Register `RBE_RT_Soll`. Braucht "
     "die *Raumeinheit* in der Ausstattung. Der Bereich 20 bis 40 °C ist eine Entscheidung des Eigentümers, "
     "kein Registerfakt. Was die Regelung mit dem Wert tut, ist **nicht überprüft** (ungeklärt). Das Register "
     "bindet den gespeicherten Parameter 1148: Nach einem Wächterablauf liest es den gespeicherten Wert, nicht "
     "einen festen Standard; nur verfügbar mit angeschlossener Raumeinheit und Einflussfaktor > 0 (belegt).",
     "FW, INT")

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
     "Hot water setpoint in °C. Only in mode `setpoint` (the overall group does not affect hot water). Deferred "
     "commit like the rest of the group. The firmware limits the effect to `dhw_max` and to the coverage of the "
     "heat pump; extra hot water, thermal disinfection and reheating take precedence. Firmware range 30.0 … "
     "75.0 °C, default after a reset 40.0 °C (proven). Mind the Legionella advice at the top of the hot water "
     "temperatures.",
     "Warmwasser-Sollwert in °C. Nur in der Betriebsart `setpoint` (die Gesamt-Gruppe wirkt nicht auf das "
     "Warmwasser). Verzögerte Übernahme wie der Rest der Gruppe. Die Firmware begrenzt die Wirkung auf `dhw_max` "
     "und auf die Deckung der Wärmepumpe; Extra-Warmwasser, thermische Desinfektion und Nachheizung haben "
     "Vorrang. Firmware-Bereich 30,0 … 75,0 °C, Standardwert nach einem Reset 40,0 °C (belegt). Beachte den "
     "Legionellen-Hinweis bei den Warmwassertemperaturen.", "PL, FW, WEB")
_add("cfg_dhw_offset", "hot_water",
     "Offset in kelvin added to the controller's hot water target. Only in mode `offset`. Deferred commit.",
     "Anhebung in Kelvin auf den Warmwasser-Sollwert der Regelung. Nur in der Betriebsart `offset`. Verzögerte "
     "Übernahme.", "PL, FW")
_add("cfg_dhw_level", "hot_water",
     "Level correction of the hot water target (proven): 1 and 2 raise by the controller parameter *Erhöhung "
     "Warmwasser*, 3 lowers by *Absenkung Warmwasser* (parameters 1197/1198, set at the control panel). "
     "Deferred commit.",
     "Stufenkorrektur des Warmwasser-Sollwerts (belegt): 1 und 2 erhöhen um den Reglerparameter *Erhöhung "
     "Warmwasser*, 3 senkt um *Absenkung Warmwasser* (Parameter 1197/1198, am Bedienteil eingestellt). "
     "Verzögerte Übernahme.", "FW, PL")
_add("circulation", "hot_water",
     "**Button** that starts a hot water circulation run (register 10070, a trigger; proven). The run follows the "
     "controller's run and pause times (*Einst_Zirk_Ein/Aus*); once no run is active any more the firmware sets "
     "the register back to 0 itself; `circulation_stop` ends it early. Whether the pump runs (also for runs of the "
     "controller's own time program) is `pump_circulation` (ZIP output). Not accepted while the "
     "hot water operating mode of the controller is *holiday* or *off*: *off* also clears the equipment flag "
     "`hot_water_available`, so the button is unavailable then; *holiday* cannot be read over the SHI, a press is then "
     "silently without effect. Needs firmware 3.92.0 or later. One of the keys the Heat Pump Optimizer depends on "
     "(**since 0.18.0 a button, up to 0.17.x a switch**: call `button.press` instead of `switch.turn_on`). The "
     "heating circulation pumps cannot be controlled through the SHI. Because the controller ends the run itself, "
     "a read-back of 0 is not a failed write and not a change outside Home Assistant, and it is not restored after "
     "a reset. The *Enable SHI* parameter does not apply to it.",
     "**Taster**, der einen Zirkulationslauf des Warmwassers startet (Register 10070, ein Trigger; belegt). Der "
     "Lauf folgt den Lauf- und Pausenzeiten der Regelung (*Einst_Zirk_Ein/Aus*); sobald kein Lauf mehr aktiv ist, "
     "setzt die Firmware das Register selbst auf 0; `circulation_stop` beendet ihn vorzeitig. Ob die Pumpe läuft "
     "(auch bei Läufen des eigenen Zeitprogramms der Regelung), zeigt `pump_circulation` (ZIP-Ausgang). Nicht "
     "angenommen, solange die Warmwasser-Betriebsart der Regelung *Ferien* oder *Aus* ist: *Aus* löscht auch das "
     "Flag `hot_water_available`, der Taster ist dann nicht verfügbar; *Ferien* ist über die SHI nicht "
     "lesbar, ein Druck bleibt dann stillschweigend ohne Wirkung. Braucht Firmware 3.92.0 oder neuer. Einer der "
     "Schlüssel, auf die der Heat Pump Optimizer angewiesen ist (**seit 0.18.0 ein Taster, bis 0.17.x ein "
     "Schalter**: `button.press` statt `switch.turn_on` aufrufen). Die Heizungs-Umwälzpumpen lassen sich über die "
     "SHI nicht steuern. Weil die Regelung den Lauf selbst beendet, ist ein Rücklesen von 0 kein fehlgeschlagener "
     "Schreibzugriff und keine Änderung außerhalb von Home Assistant, und er wird nach einem Reset nicht "
     "wiederhergestellt. Der Parameter *Enable SHI* gilt für ihn nicht.", "FW, PL")
_add("circulation_stop", "hot_water",
     "**Button** that ends a running circulation run: writes 0 to register 10070 (proven from firmware V3.92.3). The "
     "circulation logic computes its request every second as *register 10070 is not 0* **or** *the controller's own "
     "circulation time program requests a run*; with the request at 0 the pump output (`pump_circulation`) stops at "
     "once. The run counter is frozen, not reset: the next start resumes the remaining on-time instead of a full "
     "one. While the time program requests circulation at the same time, the pump keeps running. Unavailable like "
     "the `circulation` button (hot water *off*, no circulation pump). Harmless while no run is active.",
     "**Taster**, der einen laufenden Zirkulationslauf beendet: schreibt 0 in Register 10070 (aus der Firmware "
     "V3.92.3 belegt). Die Zirkulationslogik bildet ihre Anforderung jede Sekunde als *Register 10070 ist nicht 0* "
     "**oder** *das eigene Zirkulations-Zeitprogramm der Regelung fordert einen Lauf*; ist die Anforderung 0, stoppt "
     "der Pumpenausgang (`pump_circulation`) sofort. Der Laufzähler wird eingefroren, nicht zurückgesetzt: Der "
     "nächste Start setzt die restliche Laufzeit fort statt einer vollen. Fordert das Zeitprogramm gleichzeitig "
     "Zirkulation an, läuft die Pumpe weiter. Nicht verfügbar wie der Taster `circulation` (Warmwasser *Aus*, keine "
     "Zirkulationspumpe). Ohne laufenden Lauf wirkungslos.", "FW")
_add("extra_dhw", "hot_water",
     "**Button** that starts extra hot water (register 10071, a trigger; proven): the controller's extra hot water "
     "timer starts with the duration `extra_dhw_duration` (parameter 1147); while it runs the hot water target is "
     "raised to `extra_dhw_setpoint` (parameter 1146, limited to `dhw_max`), `extra_dhw_running` is on and "
     "`extra_dhw_remaining` counts down. When the timer ends the firmware sets the register back to 0 by itself; "
     "`extra_dhw_stop` ends it early. Needs firmware 3.92.0 or later. **Since 0.18.0 a button, up to 0.17.x a "
     "switch** (`button.press` instead of `switch.turn_on`). A read-back of 0 is the normal end, so it is not "
     "restored after a reset and not counted as an external change. The *Enable SHI* parameter does not apply to "
     "it.",
     "**Taster**, der Extra-Warmwasser startet (Register 10071, ein Trigger; belegt): Der Extra-Warmwasser-Timer "
     "der Regelung startet mit der Dauer `extra_dhw_duration` (Parameter 1147); solange er läuft, wird das "
     "Warmwasser-Ziel auf `extra_dhw_setpoint` (Parameter 1146, begrenzt auf `dhw_max`) angehoben, "
     "`extra_dhw_running` ist an und `extra_dhw_remaining` zählt herunter. Läuft der Timer ab, setzt die Firmware "
     "das Register selbst auf 0; `extra_dhw_stop` beendet ihn vorzeitig. Braucht Firmware 3.92.0 oder neuer. "
     "**Seit 0.18.0 ein Taster, bis 0.17.x ein Schalter** (`button.press` statt `switch.turn_on`). Ein Rücklesen "
     "von 0 ist das normale Ende, deshalb wird er nach einem Reset nicht wiederhergestellt und nicht als externe "
     "Änderung gezählt. Der Parameter *Enable SHI* gilt für ihn nicht.", "FW, PL")
_add("extra_dhw_stop", "hot_water",
     "**Button** that ends a running extra hot water early: writes 0 to register 10071, which sets the controller's "
     "extra hot water timer to 0 (proven). Harmless while none runs. Replaces turning the 0.17.x switch off.",
     "**Taster**, der ein laufendes Extra-Warmwasser vorzeitig beendet: schreibt 0 in Register 10071, was den "
     "Extra-Warmwasser-Timer der Regelung auf 0 setzt (belegt). Ohne laufendes Extra-Warmwasser wirkungslos. "
     "Ersetzt das Ausschalten des Schalters von 0.17.x.", "FW")
_add("extra_dhw_running", "hot_water",
     "On while extra hot water started over the SHI runs: register 10071 reads 1 until the timer ends and the "
     "firmware sets it back to 0 (proven); `extra_dhw_remaining` shows the minutes left. Same register as the "
     "`extra_dhw` button, read once.",
     "An, solange über die SHI gestartetes Extra-Warmwasser läuft: Register 10071 liest 1, bis der Timer abläuft "
     "und die Firmware es selbst auf 0 setzt (belegt); `extra_dhw_remaining` zeigt die verbleibenden Minuten. "
     "Dasselbe Register wie der Taster `extra_dhw`, nur einmal gelesen.", "FW")
_add("extra_dhw_setpoint", "dhw_temps",
     "Target temperature of extra hot water (controller parameter 1146, firmware `ExtraDHW::temperatureSetpoint`): "
     "while `extra_dhw` runs, the hot water target is raised to this value (limited to `dhw_max`). Set at the "
     "control panel, read only here. Same register as `raw_10500`. New in 0.17.0 (proven).",
     "Soll-Temperatur des Extra-Warmwassers (Reglerparameter 1146, Firmware `ExtraDHW::temperatureSetpoint`): "
     "Solange `extra_dhw` läuft, wird das Warmwasser-Ziel auf diesen Wert angehoben (begrenzt auf `dhw_max`). Am "
     "Bedienteil eingestellt, hier nur lesbar. Dasselbe Register wie `raw_10500`. Neu in 0.17.0 (belegt).", "FW")
_add("extra_dhw_duration", "dhw_temps",
     "Duration of extra hot water in minutes (controller parameter 1147, seconds divided by 60 on the wire): how "
     "long the `extra_dhw` trigger runs. Same register as `raw_10501`. New in 0.17.0 (proven).",
     "Dauer des Extra-Warmwassers in Minuten (Reglerparameter 1147, Sekunden geteilt durch 60 auf dem Bus): wie "
     "lange der Trigger `extra_dhw` läuft. Dasselbe Register wie `raw_10501`. Neu in 0.17.0 (belegt).", "FW")
_add("extra_dhw_remaining", "dhw_temps",
     "Remaining time of a running extra hot water in minutes (firmware `ExtraDHW::timer`, counts down once per "
     "second, seconds divided by 60 on the wire). 0 while none runs. Same register as `raw_10502`. New in 0.17.0 "
     "(proven).",
     "Restlaufzeit eines laufenden Extra-Warmwassers in Minuten (Firmware `ExtraDHW::timer`, zählt sekündlich "
     "herunter, Sekunden geteilt durch 60 auf dem Bus). 0, solange keines läuft. Dasselbe Register wie "
     "`raw_10502`. Neu in 0.17.0 (belegt).", "FW")

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
     "Maximum allowed electrical power of the heat pump in kW, effective according to the limit mode. Firmware "
     "range 0 … 30.0 kW, default after a reset 30.0 kW (proven). Not restored after a reset. Only while the "
     "controller parameter *Enable SHI* is on.",
     "Höchste zulässige elektrische Leistung der Wärmepumpe in kW, wirksam gemäß Modus. Firmware-Bereich 0 … "
     "30,0 kW, Standardwert nach einem Reset 30,0 kW (belegt). Wird nach einem Reset nicht wiederhergestellt. Nur "
     "wirksam, solange der Reglerparameter *Enable SHI* an ist.", "PL, FW")

# ------------------------------------------------------------------ overall heating
_add("cfg_overall_mode", "overall",
     "Control mode of the heating circuit **and** all mixing circuits at once (proven). While it is not "
     "`no_influence`, the modes `cfg_heating_mode` and `cfg_mk*_mode` are ignored: `offset` applies "
     "`cfg_overall_offset`, `level` applies `cfg_overall_level`. **Raw 1 (setpoint) is not implemented** by the "
     "firmware for this group, it acts like `no_influence`: since 0.18.0 the select offers only `no_influence`, "
     "`offset` and `level`; a raw 1 another client wrote shows as *unknown* (the raw value is in the diagnostics "
     "and in the change notice). Hot water is not affected. Disabled by default (owner decision: an active "
     "overall mode silently overrides what an optimizer sets per circuit); not restored after a reset.",
     "Betriebsart des Heizkreises **und** aller Mischkreise zugleich (belegt). Solange sie nicht `no_influence` "
     "ist, werden `cfg_heating_mode` und `cfg_mk*_mode` ignoriert: `offset` wendet `cfg_overall_offset` an, "
     "`level` `cfg_overall_level`. **Roh 1 (Sollwert) ist von der Firmware nicht umgesetzt** für diese Gruppe, "
     "es wirkt wie `no_influence`: Seit 0.18.0 bietet das Select nur `no_influence`, `offset` und `level` an; "
     "eine von einem anderen Client geschriebene 1 zeigt *unbekannt* (der Rohwert steht in der Diagnose und im "
     "Änderungshinweis). Warmwasser ist nicht betroffen. Standardmäßig deaktiviert (Entscheidung des "
     "Eigentümers: Eine aktive Gesamt-Betriebsart überschreibt stillschweigend, was ein Optimierer je Kreis "
     "setzt); nach einem Reset nicht wiederhergestellt.", "FW, PL, M")
_add("cfg_overall_offset", "overall",
     "Offset in kelvin for the heating circuit and all mixing circuits in overall mode `offset`. **Firmware range "
     "-5.0 … 5.0 K** (python-luxtronik lists -20 … 20: a value beyond ±5 K would reset the register to 0, so the "
     "range was narrowed in 0.17.0). Disabled by default.",
     "Anhebung in Kelvin für den Heizkreis und alle Mischkreise in der Gesamt-Betriebsart `offset`. "
     "**Firmware-Bereich -5,0 … 5,0 K** (python-luxtronik nennt -20 … 20: Ein Wert über ±5 K würde das Register "
     "auf 0 zurücksetzen, deshalb wurde der Bereich in 0.17.0 verengt). Standardmäßig deaktiviert.", "FW, PL")
_add("cfg_overall_level", "overall",
     "Level for the heating circuit and all mixing circuits in overall mode `level` (proven): 1 and 2 raise by the "
     "controller parameter *Erhöhung Hz. allg.*, 3 lowers by *Absenkung Hz. allg.* (parameters 1187/1188, set at "
     "the control panel). Disabled by default.",
     "Stufe für den Heizkreis und alle Mischkreise in der Gesamt-Betriebsart `level` (belegt): 1 und 2 erhöhen um "
     "den Reglerparameter *Erhöhung Hz. allg.*, 3 senkt um *Absenkung Hz. allg.* (Parameter 1187/1188, am "
     "Bedienteil eingestellt). Standardmäßig deaktiviert.", "FW, PL")

# ------------------------------------------------------------------ system
_add("buffer_type", "system",
     "Type of the buffer tank configured in the controller (see the background above): raw value 0 series buffer, "
     "1 separation buffer (*Trennpuffer*), 2 multi-function buffer, as in python-luxtronik `BufferType`. Any other "
     "raw value has no state. Versions before 0.11.0 shifted the assignment by one and showed a separation buffer "
     "as a series buffer.",
     "Typ des in der Regelung eingestellten Pufferspeichers (siehe Hintergrund oben): Rohwert 0 Reihenpuffer, "
     "1 Trennpuffer, 2 Multifunktionspuffer, wie in python-luxtronik `BufferType`. Jeder andere Rohwert hat "
     "keinen Zustand. Vor Version 0.11.0 war die Zuordnung um eins verschoben, ein Trennpuffer wurde als "
     "Reihenpuffer angezeigt.", "PL, M")
_add("switching_lock_minutes", "system",
     "Minimum off time before the heat pump may start again (*Schaltspielsperre*), in minutes. The reference "
     "firmware returns the constant 20 (a fixed value, not a measurement). Disabled by default for new "
     "installations.",
     "Mindest-Ausschaltzeit, bevor die Wärmepumpe wieder starten darf (*Schaltspielsperre*), in Minuten. Die "
     "Referenz-Firmware liefert die Konstante 20 (ein fester Wert, kein Messwert). Für neue Installationen "
     "standardmäßig deaktiviert.", "PL, FW")
_add("min_runtime_minutes", "system",
     "Minimum runtime of the heat pump, in minutes. The reference firmware returns the constant 20 (a fixed value, "
     "not a measurement). Disabled by default for new installations.",
     "Mindestlaufzeit der Wärmepumpe in Minuten. Die Referenz-Firmware liefert die Konstante 20 (ein fester Wert, "
     "kein Messwert). Für neue Installationen standardmäßig deaktiviert.", "PL, FW")
_caps = {
    "cap_cooling": ("cooling (`cooling_configured`)", "Kühlen (`cooling_configured`)"),
    "cap_pool": ("pool (`pool_configured`)", "Pool (`pool_configured`)"),
    "cap_solar": ("a solar function (new in 0.17.0, pre-fills the *solar* option)",
                  "eine Solarfunktion (neu in 0.17.0, belegt die Option *Solar* vor)"),
    "cap_room_controller": ("a room controller (controller setting *RFV* = 4)",
                            "ein Raumregler (Reglereinstellung *RFV* = 4)"),
    "cap_mk1_heating": ("heating of mixing circuit 1", "Heizen von Mischkreis 1"),
    "cap_mk1_cooling": ("cooling of mixing circuit 1", "Kühlen von Mischkreis 1"),
    "cap_mk2_heating": ("heating of mixing circuit 2", "Heizen von Mischkreis 2"),
    "cap_mk2_cooling": ("cooling of mixing circuit 2", "Kühlen von Mischkreis 2"),
    "cap_mk3_heating": ("heating of mixing circuit 3", "Heizen von Mischkreis 3"),
    "cap_mk3_cooling": ("cooling of mixing circuit 3", "Kühlen von Mischkreis 3"),
}
for _k, (_en, _de) in _caps.items():
    _add(_k, "system",
         f"Equipment flag (discrete input, function code 2): the installation has {_en}. Pre-selects the equipment "
         "in the setup dialog. Not in python-luxtronik; the conditions are proven by the firmware (full analysis, "
         "section 2.3): the mixing circuit flags follow the visibility of the circuit.",
         f"Ausstattungs-Flag (Discrete Input, Funktionscode 2): Die Anlage hat {_de}. Wählt die Ausstattung im "
         "Einrichtungsdialog vor. Nicht in python-luxtronik; die Bedingungen sind durch die Firmware belegt "
         "(Vollanalyse, Abschnitt 2.3): Die Mischkreis-Flags folgen der Sichtbarkeit des Kreises.", "FW, OBS")

for _k, _en, _de in (
    ("heating_available", "heating", "Heizen"),
    ("hot_water_available", "hot water", "Warmwasser"),
):
    _add(_k, "system",
         f"Availability flag (discrete input, function code 2): on while {_en} is equipped **and** the controller's "
         f"operating mode for it is not *off* (proven, full analysis, section 2.3). So it is not a pure equipment "
         f"flag: it goes off when the mode is set to *off* at the control panel. For hot water it gates the "
         f"circulation buttons. Key up to 0.17.x `cap_{_en.replace(' ', '_')}`, renamed in 0.18.0 (the entity ID stays).",
         f"Verfügbarkeits-Flag (Discrete Input, Funktionscode 2): an, solange {_de} ausgestattet **und** die "
         f"Betriebsart der Regelung dafür nicht *Aus* ist (belegt, Vollanalyse, Abschnitt 2.3). Es ist also kein "
         f"reines Ausstattungs-Flag: Es geht aus, wenn am Bedienteil *Aus* eingestellt wird. Beim Warmwasser "
         f"sperrt es die Zirkulations-Taster. Schlüssel bis 0.17.x `cap_{_en.replace(' ', '_')}`, in 0.18.0 umbenannt (die "
         f"Entity-ID bleibt).", "FW, OBS")

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
         f"Flow temperature setpoint of mixing circuit {_n}. Only in mode `setpoint` and while the overall mode is "
         f"`no_influence`. The firmware limits the result to `mk{_n}_flow_min` … `mk{_n}_flow_max`. Firmware range 20.0 … "
         "65.0 °C, default after a reset 35.0 °C (proven).",
         f"Vorlauf-Sollwert von Mischkreis {_n}. Nur in der Betriebsart `setpoint` und solange die "
         f"Gesamt-Betriebsart `no_influence` ist. Die Firmware begrenzt das Ergebnis auf `mk{_n}_flow_min` … "
         f"`mk{_n}_flow_max`. Firmware-Bereich 20,0 … 65,0 °C, Standardwert nach einem Reset 35,0 °C (belegt).",
         "FW, PL")
    _add(f"cfg_{_k}_offset", "mixing",
         f"Offset in kelvin on the flow target of mixing circuit {_n}. Only in mode `offset` and while the overall "
         "mode is `no_influence`. Firmware range -5.0 … 5.0 K (proven).",
         f"Anhebung in Kelvin auf den Vorlauf-Sollwert von Mischkreis {_n}. Nur in der Betriebsart `offset` und "
         "solange die Gesamt-Betriebsart `no_influence` ist. Firmware-Bereich -5,0 … 5,0 K (belegt).", "FW, PL")
    _add(f"cfg_{_k}_level", "mixing",
         f"Level correction of mixing circuit {_n} (proven): 1 and 2 raise the flow target by the controller "
         f"parameter *Erhöhung MK{_n}*, 3 lowers it by *Absenkung MK{_n}* (menu *Offsets*). Only while the "
         "overall mode is `no_influence`.",
         f"Stufenkorrektur von Mischkreis {_n} (belegt): 1 und 2 erhöhen den Vorlauf-Sollwert um den "
         f"Reglerparameter *Erhöhung MK{_n}*, 3 senkt ihn um *Absenkung MK{_n}* (Menü *Offsets*). Nur solange "
         "die Gesamt-Betriebsart `no_influence` ist.", "FW, PL")
    _add(f"cfg_{_k}_cool_mode", "cooling_pool",
         f"Control mode of mixing circuit {_n} cooling. 0 does not switch cooling off. Needs the circuit and "
         "*cooling* in the equipment.",
         f"Betriebsart des Kühlens von Mischkreis {_n}. 0 schaltet das Kühlen nicht aus. Braucht den Kreis und "
         "*Kühlung* in der Ausstattung.", "PL")
    _add(f"cfg_{_k}_cool_setpoint", "cooling_pool",
         f"Cooling flow temperature setpoint of mixing circuit {_n}. Only in mode `setpoint`. Firmware range 5.0 … "
         "25.0 °C, default after a reset 20.0 °C (proven); the consumer in the firmware was not traced, the "
         "effect is assumed analogous to heating (likely).",
         f"Kühl-Vorlauf-Sollwert von Mischkreis {_n}. Nur in der Betriebsart `setpoint`. Firmware-Bereich 5,0 … "
         "25,0 °C, Standardwert nach einem Reset 20,0 °C (belegt); der Verbraucher in der Firmware wurde nicht "
         "verfolgt, die Wirkung gilt analog zum Heizen als wahrscheinlich.", "FW, PL")
    _add(f"cfg_{_k}_cool_offset", "cooling_pool",
         f"Offset in kelvin on the cooling flow temperature of mixing circuit {_n}. Only in mode `offset`. Firmware "
         "range -5.0 … 5.0 K (proven); effect analogous to heating (likely).",
         f"Anhebung in Kelvin auf die Kühl-Vorlauftemperatur von Mischkreis {_n}. Nur in der Betriebsart "
         "`offset`. Firmware-Bereich -5,0 … 5,0 K (belegt); Wirkung analog zum Heizen (wahrscheinlich).", "FW, PL")

# ------------------------------------------------------------------ raw values (template per address)
RAW_TEXT: dict[int, tuple[str, str, str]] = {}
RAW_DEFAULT = (
    "Undocumented input register (python-luxtronik: function unknown). No vendor source for its meaning; a "
    "register source below, if any, is a derived observation, not a specification.",
    "Undokumentiertes Eingangsregister (python-luxtronik: Funktion unbekannt). Keine Herstellerquelle für die "
    "Bedeutung; eine Registerquelle darunter ist, falls vorhanden, eine abgeleitete Beobachtung, keine "
    "Spezifikation.",
    "PL",
)

# ------------------------------------------------------------------ raw values with a proven meaning (RAW_MEANINGS)
# The keys stay ``raw_<address>`` and the entities stay disabled diagnostics; only the name, unit and scale changed.
# Source for all of them: docs/firmware-3.92.3-register-meanings.md (firmware names, grades, measurements).
_add("flow_calc_max", "temps",
     "Firmware item *TVL calc max* (t0/0x67): the calculated maximum flow temperature, the return target plus the "
     "moving average of the flow minus return spread, in 0.1 °C (wire value 253 = 25.3 °C). Proven by the firmware "
     "(formula and text); whether the controller uses it as a setpoint or as an upper limit is open. Measured: 253 "
     "with a return target of 20.0 and an average spread of 5.3 K. Was `raw_10113` up to 0.17.x (named *heating "
     "target (calculated)* before 0.17.0); the entity ID stays. Disabled by default.",
     "Firmware-Item *TVL calc max* (t0/0x67): die berechnete maximale Vorlauftemperatur, Rücklauf-Sollwert plus "
     "gleitender Mittelwert der Differenz Vorlauf minus Rücklauf, in 0,1 °C (Rohwert 253 = 25,3 °C). Von der "
     "Firmware belegt (Formel und Text); ob die Regelung ihn als Sollwert oder als Obergrenze nutzt, ist "
     "ungeklärt. Gemessen: 253 bei einem Rücklauf-Sollwert von 20,0 und einer mittleren Spreizung von 5,3 K. War "
     "bis 0.17.x `raw_10113` (davor *Vorlauf: Soll Heizen (berechnet)* genannt); die Entity-ID bleibt. "
     "Standardmäßig deaktiviert.", "FW, M")
_POOL_HOURS_EN = ("the 32-bit operating hour counter of the pool `Zaehler_BetrZeitSW` (parameter 859) that starts at "
                  "10412. The SHI divides by **7200** instead of 3600 (the control panel shows the same counter with "
                  "1/3600), so the wire value is most likely half the hours (likely, not measured: no pool on the "
                  "reference installation). No hour sensor is derived until that is proven. Disabled by default.")
_POOL_HOURS_DE = ("des 32-Bit-Betriebsstundenzählers des Schwimmbads `Zaehler_BetrZeitSW` (Parameter 859), der bei "
                  "10412 beginnt. Die SHI teilt durch **7200** statt 3600 (das Bedienteil zeigt denselben Zähler mit "
                  "1/3600), der Wert auf dem Bus ist also wahrscheinlich die halbe Stundenzahl (wahrscheinlich, nicht "
                  "gemessen: kein Pool an der Referenzanlage). Bis das belegt ist, wird kein Stundensensor abgeleitet. "
                  "Standardmäßig deaktiviert.")
_add("raw_10412", "raw", "High word of " + _POOL_HOURS_EN, "Oberes Wort " + _POOL_HOURS_DE, "FW")
_add("raw_10413", "raw", "Low word of " + _POOL_HOURS_EN, "Unteres Wort " + _POOL_HOURS_DE, "FW")
# ------------------------------------------------------------------ outputs and inputs (binary sensors on proven registers)
# Up to 0.17.x each of these registers also had a disabled raw sensor `raw_<address>`; since 0.18.0 the binary sensor
# is the only entity of its register.
_FLAG_EN = (" Register {raw}; up to 0.17.x also the raw sensor `raw_{raw}`, removed in 0.18.0. Proven by the firmware "
            "(`{var}`, item `{item}`). {meas}")
_FLAG_DE = (" Register {raw}; bis 0.17.x zusätzlich der Rohwert-Sensor `raw_{raw}`, in 0.18.0 entfernt. Von der "
            "Firmware belegt (`{var}`, Item `{item}`). {meas}")
for _key, _raw, _var, _item, _en, _de, _meas_en, _meas_de in (
    ("pump_heating", "10354", "HUPout", "t0/0x20", "Heating circulation pump (HUP) runs.",
     "Heizungsumwälzpumpe (HUP) läuft.", "Measured.", "Gemessen."),
    ("pump_hot_water", "10355", "BUPout", "t0/0x44", "Hot water pump (BUP) runs.",
     "Brauchwasserpumpe (BUP) läuft.", "Measured.", "Gemessen."),
    ("pump_circulation", "10356", "ZIPout", "t0/0x48", "Circulation pump (ZIP) runs: the running indicator of "
     "circulation, for runs started with the `circulation` button and runs of the controller's time program alike.",
     "Zirkulationspumpe (ZIP) läuft: die Laufanzeige der Zirkulation, für Läufe über den Taster `circulation` "
     "ebenso wie für Läufe des Zeitprogramms der Regelung.", "Measured: pulses of 2 minutes.", "Gemessen: Pulse von 2 Minuten."),
    ("output_vbo", "10350", "VBOout", "t0/0x45", "Digital output VBO is on. What it switches is not "
     "documented (open).", "Digitaler Ausgang VBO ist an. Was er schaltet, ist nicht dokumentiert (ungeklärt).",
     "Measured: coincides with the compressor runs.", "Gemessen: deckt sich mit den Verdichterläufen."),
    ("output_fp1", "10351", "FP1out", "t0/0x6d", "Digital output FP1 is on.",
     "Digitaler Ausgang FP1 ist an.", "Measured: follows the heating circulation pump.",
     "Gemessen: folgt der Heizungsumwälzpumpe."),
    ("output_fp2", "10352", "FP2out", "t0/0x4c", "Digital output FP2 is on. Disabled by default.",
     "Digitaler Ausgang FP2 ist an. Standardmäßig deaktiviert.",
     "Not measured (the reference installation has no second circuit).",
     "Nicht gemessen (die Referenzanlage hat keinen zweiten Kreis)."),
    ("output_fp3", "10353", "FP3out", "t0/0x4d", "Digital output FP3 is on. Disabled by default.",
     "Digitaler Ausgang FP3 ist an. Standardmäßig deaktiviert.",
     "Not measured (the reference installation has no third circuit).",
     "Nicht gemessen (die Referenzanlage hat keinen dritten Kreis)."),
):
    _add(_key, "status", _en + _FLAG_EN.format(raw=_raw, var=_var, item=_item, meas=_meas_en),
         _de + _FLAG_DE.format(raw=_raw, var=_var, item=_item, meas=_meas_de), "FW, M")
_add("input_evu", "status",
     "Level of the digital input EVU (utility lock): on = level 1. **Which level means a lock is not proven.** "
     "Measured: constant 1 while the native `evu_unlocked` of the Luxtronik integration is on, so 1 most likely "
     "means released; that is inferred from one state only, a real lock has not been measured. Use the operating "
     "mode *Utility lockout* for the lock itself. Register 10360 (up to 0.17.x also the raw "
     "sensor `raw_10360`, removed in 0.18.0); disabled by default.",
     "Pegel des digitalen Eingangs EVU (EVU-Sperre): an = Pegel 1. **Welcher Pegel eine Sperre bedeutet, ist nicht "
     "belegt.** Gemessen: konstant 1, solange das native `evu_unlocked` der Luxtronik-Integration an ist; 1 heißt "
     "also wahrscheinlich freigegeben, aus diesem einen Zustand abgeleitet, eine echte Sperre wurde nicht "
     "gemessen. Für die Sperre selbst die Betriebsart *EVU-Sperre* verwenden. Register 10360 (bis 0.17.x "
     "zusätzlich der Rohwert-Sensor `raw_10360`, in 0.18.0 entfernt); standardmäßig deaktiviert.", "FW, M")
_add("input_evu2", "status",
     "Level of the digital input EVU 2: on = level 1. The name is proven by the firmware (`EVU2in`, item "
     "`t0/0x2b`); the meaning of the levels is not. Measured: constant 0 on the reference installation (the native "
     "`evu2` is off), so nothing is known about the other state. Register 10361 (up to 0.17.x also "
     "`raw_10361`, removed in 0.18.0); disabled by default.",
     "Pegel des digitalen Eingangs EVU 2: an = Pegel 1. Der Name ist von der Firmware belegt (`EVU2in`, Item "
     "`t0/0x2b`), die Bedeutung der Pegel nicht. Gemessen: konstant 0 an der Referenzanlage (das native `evu2` "
     "ist aus), über den anderen Zustand ist also nichts bekannt. Register 10361 (bis 0.17.x "
     "zusätzlich `raw_10361`, in 0.18.0 entfernt); standardmäßig deaktiviert.", "FW, M")

_add("firmware_version", "system",
     "Firmware version of the controller as text, for example `3.92.3`, composed of the registers 10400, 10401 and "
     "10402 (they read 3, 92 and 3 on the reference installation). Unknown until all three are read. The three "
     "registers have no entities of their own. The integration needs 3.92 or newer for the circulation pump and "
     "extra hot water; with older firmware it raises a repair issue.",
     "Firmware-Version der Regelung als Text, zum Beispiel `3.92.3`, zusammengesetzt aus den Registern 10400, 10401 "
     "und 10402 (sie lesen an der Referenzanlage 3, 92 und 3). Unbekannt, bis alle drei gelesen sind. Die drei "
     "Register haben keine eigenen Entitäten. Die Integration braucht 3.92 oder neuer für Zirkulationspumpe und "
     "Extra-Warmwasser; bei älterer Firmware erzeugt sie einen Reparaturhinweis.", "PL, M")
