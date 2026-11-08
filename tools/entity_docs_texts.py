"""Hand-written explanations for tools/gen_entity_docs.py (English and German).

Everything that can be derived from the code (names, keys, units, ranges, options, register addresses, devices,
default state) is NOT written here; ``gen_entity_docs.py`` reads it from ``registers.py``, ``binary_sensor.py``,
``const.py`` and the generated translations. This file only holds the prose: the section texts and one
explanation per entity key.

Rules for this file (same as for the register map, see CLAUDE.md "No invented register facts"):

* A statement about a register needs a source. ``src`` names it: ``PL`` python-luxtronik, ``FW`` the firmware
  analysis in docs/firmware-3.92.3-shi-analysis.md, ``M`` a measurement on the reference installation (alpha
  innotec LWDV 91-1/3, firmware 3.92.3) that is documented in the README or CHANGELOG, ``OBS`` observation only,
  ``INT`` a decision or calculation of this integration, ``WEB`` general background (see the source list of
  the page).
* What nobody has established is written as open ("unclear" / "ungeklärt"), never guessed.
* A new entity key needs an entry in ENTRIES (or a template) or ``tests/test_entity_docs.py`` fails.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    """Prose for one entity key."""

    section: str
    en: str
    de: str
    src: str = ""
    # Meaning of the raw number, shown only while the entity has no option texts of its own.
    vals_en: str = ""
    vals_de: str = ""


@dataclass(frozen=True)
class Section:
    """One topic of the page."""

    id: str
    title_en: str
    title_de: str
    intro_en: str
    intro_de: str


SOURCE_LEGEND = {
    "PL": (
        "python-luxtronik (Bouni/python-luxtronik, `luxtronik/definitions/{inputs,holdings}.py`, `datatypes.py`)",
        "python-luxtronik (Bouni/python-luxtronik, `luxtronik/definitions/{inputs,holdings}.py`, `datatypes.py`)",
    ),
    "FW": (
        "[firmware analysis](firmware-3.92.3-shi-analysis.md), [register meanings](firmware-3.92.3-register-meanings.md) and the [full analysis](firmware-3.92.3-shi-full-analysis.md) of V3.92.3 (proven = read from the firmware; likely = inferred; open = not determined)",
        "[Firmware-Analyse](firmware-3.92.3-shi-analysis.md), [Registerbedeutungen](firmware-3.92.3-register-meanings.md) und die [Vollanalyse](firmware-3.92.3-shi-full-analysis.de.md) von V3.92.3 (belegt = aus der Firmware gelesen; wahrscheinlich = geschlossen; offen = nicht bestimmt)",
    ),
    "M": (
        "measurement on the reference installation (LWDV 91-1/3, firmware 3.92.3), documented in the README or CHANGELOG",
        "Messung an der Referenzanlage (LWDV 91-1/3, Firmware 3.92.3), dokumentiert in README oder CHANGELOG",
    ),
    "OBS": (
        "observation only, no written source",
        "nur Beobachtung, keine schriftliche Quelle",
    ),
    "INT": (
        "decision or calculation of this integration",
        "Festlegung oder Berechnung dieser Integration",
    ),
    "WEB": (
        "general background, see the [sources](#sources) below",
        "allgemeiner Hintergrund, siehe die [Quellen](#quellen) unten",
    ),
}

SECTIONS: tuple[Section, ...] = (
    Section(
        "temps",
        "Temperatures of the heating circuit",
        "Temperaturen des Heizkreises",
        "**Background.** A heat pump warms the water that runs through the heating system (the *flow*, German "
        "*Vorlauf*) and gets it back cooler (the *return*, *Rücklauf*). The difference between the two is the "
        "*spread* (*Spreizung*). The controller has no spread register; the integration calculates it as "
        "`flow_return_difference` (flow minus return). The Luxtronik controller regulates on the **return** temperature: the heating setpoint of the "
        "SHI acts on it (see [Heating](#8-heating-circuit-control)). Its normal target comes from the *heating "
        "curve* (*Heizkurve*), which assigns a water temperature to every outside temperature: the *slope* says "
        "how strongly the water temperature follows the outside temperature, the *level* (or offset) shifts the "
        "whole curve up or down. Above the *heating limit* (*Heizgrenze*, an outside temperature) a heating curve "
        "controller stops heating. The lower the water temperature a heat pump has to deliver, the more "
        "efficient it is: the German Wikipedia article on heat pumps gives the example of a COP falling from 4.8 "
        "(B0/W35) to 3.6 (B0/W50).\n\n"
        "**Pitfall: return and return target.** The published register list names 10100 *return target* and "
        "10101 *return actual*. Measured on the reference installation it is the other way round, and the "
        "entities follow the measurement (`return` = 10100 follows the water, `return_target` = 10101 is the "
        "target). python-luxtronik agrees. Sources: PL, M, WEB ([Heizkurve](#sources), [Wärmepumpe](#sources)).",
        "**Hintergrund.** Eine Wärmepumpe erwärmt das Wasser, das durch die Heizungsanlage läuft (der *Vorlauf*), "
        "und bekommt es abgekühlt zurück (der *Rücklauf*). Der Unterschied beider Temperaturen ist die "
        "*Spreizung*. Die Regelung hat dafür kein Register; die Integration berechnet sie als "
        "`flow_return_difference` (Vorlauf minus Rücklauf). Die Luxtronik-Regelung regelt auf die **Rücklauftemperatur**: Der "
        "Heizungs-Sollwert der SHI wirkt auf sie (siehe [Heizen](#8-heizkreis-steuerung)). Ihr normaler Sollwert "
        "kommt aus der *Heizkurve*. Sie ordnet jeder Außentemperatur eine Wassertemperatur zu: Die *Steilheit* "
        "sagt, wie stark die Wassertemperatur der Außentemperatur folgt, das *Niveau* (oder die Anhebung) "
        "verschiebt die ganze Kurve nach oben oder unten. Oberhalb der *Heizgrenze* (einer Außentemperatur) "
        "schaltet ein Heizkurvenregler die Heizung ab. Je niedriger die Wassertemperatur, die eine Wärmepumpe "
        "liefern muss, desto effizienter arbeitet sie: Der deutsche Wikipedia-Artikel zur Wärmepumpe nennt als "
        "Beispiel eine Leistungszahl, die von 4,8 (B0/W35) auf 3,6 (B0/W50) fällt.\n\n"
        "**Fallstrick: Rücklauf und Rücklauf-Soll.** Die veröffentlichte Registerliste nennt 10100 *Rücklauf-Soll* "
        "und 10101 *Rücklauf-Ist*. An der Referenzanlage gemessen ist es umgekehrt, und die Entitäten folgen der "
        "Messung (`return` = 10100 folgt dem Wasser, `return_target` = 10101 ist der Sollwert). python-luxtronik "
        "sieht es genauso. Quellen: PL, M, WEB ([Heizkurve](#quellen), [Wärmepumpe](#quellen)).",
    ),
    Section(
        "dhw_temps",
        "Hot water temperatures",
        "Warmwassertemperaturen",
        "**Background.** Hot water is stored in a tank and heated up to a target. Like every two-point control it "
        "uses a *hysteresis* (*Schaltdifferenz*): the heat pump only starts again after the temperature has "
        "dropped a few kelvin below the target, otherwise it would switch on and off all the time. The SHI does "
        "not expose that value. **Legionella:** the German Umweltbundesamt recommends keeping the hot water "
        "permanently above 55 °C; for large systems DVGW W 551 requires at least 60 °C at the outlet of the "
        "heater. A heat pump with a lower hot water target depends on periodic heating above that (a "
        "*Legionellenschaltung*), which the UBA does not consider a safe variant on its own. This integration "
        "has no entity for such a function; the register map contains none. Sources: WEB "
        "([UBA factsheet](#sources), [Zweipunktregler](#sources)).",
        "**Hintergrund.** Warmwasser steckt in einem Speicher und wird auf einen Sollwert aufgeheizt. Wie jede "
        "Zweipunktregelung arbeitet das mit einer *Hysterese* (*Schaltdifferenz*): Die Wärmepumpe startet erst "
        "wieder, wenn die Temperatur einige Kelvin unter den Sollwert gefallen ist, sonst würde sie ständig "
        "ein- und ausschalten. Diesen Wert gibt die SHI nicht heraus. **Legionellen:** Das Umweltbundesamt "
        "empfiehlt, das Warmwasser durchgängig über 55 °C zu halten; für Großanlagen verlangt DVGW W 551 "
        "mindestens 60 °C am Austritt des Erwärmers. Eine Wärmepumpe mit niedrigerem Warmwasser-Sollwert ist "
        "auf regelmäßiges Aufheizen darüber angewiesen (eine *Legionellenschaltung*), die das UBA allein "
        "nicht als sichere Variante ansieht. Diese Integration hat für eine solche Funktion keine Entität; die "
        "Registerkarte enthält keine. Quellen: WEB ([UBA-Factsheet](#quellen), [Zweipunktregler](#quellen)).",
    ),
    Section(
        "mixing_temps",
        "Temperatures of the mixing circuits",
        "Temperaturen der Mischkreise",
        "**Background.** A *mixing circuit* (*Mischkreis*) has its own flow temperature, produced by a mixing "
        "valve that blends hot flow water with cooler return water. Typical use: a floor heating circuit that "
        "needs less than the radiator circuit. The SHI only provides temperatures, modes and setpoints of "
        "the circuits, no valve position. The circuits exist only if they are selected in the "
        "[equipment](../README.md#installation-equipment); circuits 2 and 3 are disabled by default. Sources: "
        "PL, INT.",
        "**Hintergrund.** Ein *Mischkreis* hat eine eigene Vorlauftemperatur, die ein Mischventil erzeugt, indem es "
        "heißes Vorlaufwasser mit kühlerem Rücklaufwasser mischt. Typisch: ein Fußbodenheizkreis, der weniger "
        "braucht als der Heizkörperkreis. Die SHI liefert nur Temperaturen, Betriebsarten und Sollwerte der "
        "Kreise, keine Ventilstellung. Die Kreise gibt es nur, wenn sie in der "
        "[Ausstattung](../README.de.md#ausstattung-der-anlage) gewählt sind; Kreis 2 und 3 sind standardmäßig "
        "deaktiviert. Quellen: PL, INT.",
    ),
    Section(
        "power",
        "Power and calculated COP",
        "Leistung und berechnete Leistungszahl",
        "**Background.** The *COP* (*Leistungszahl*) is the heat output divided by the electrical power used at "
        "the same moment. It is always above 1, because the heat includes what is taken from the environment, and "
        "it depends on the operating point: a small difference between source and heating water gives a high "
        "COP, a large one a low COP. A COP of 4.2 means 1 kW of electricity delivers 4.2 kW of heat. The "
        "COP sensor of this integration is calculated from two sensors that are read anyway, so it needs "
        "no extra Modbus traffic, and it is a value over the last 10 minutes, not an instant value. Both power registers have a **resolution of 100 W**, so a quotient at low "
        "power is mostly rounding noise; that is why the COP is shown as *unknown* instead of a number in the "
        "cases listed at the sensor. During **defrost** the heat pump takes heat from the heating system "
        "and the thermal power turns negative. Sources: WEB ([Leistungszahl](#sources)), INT, PL.",
        "**Hintergrund.** Die *Leistungszahl* (COP) ist die abgegebene Wärmeleistung geteilt durch die im selben "
        "Moment aufgenommene elektrische Leistung. Sie liegt immer über 1, weil die Wärme auch die der "
        "Umwelt entzogene enthält, und hängt vom Betriebspunkt ab: Ein kleiner Unterschied zwischen "
        "Wärmequelle und Heizwasser ergibt eine hohe, ein großer eine niedrige Leistungszahl. Eine COP von 4,2 "
        "heißt: 1 kW Strom liefern 4,2 kW Wärme. Die COP dieser Integration wird aus zwei ohnehin "
        "gelesenen Sensoren berechnet, verursacht keinen zusätzlichen Modbus-Verkehr und ist ein Wert über die "
        "letzten 10 Minuten, kein Augenblickswert. Beide "
        "Leistungsregister haben eine **Auflösung von 100 W**, daher ist ein Quotient bei kleiner Leistung "
        "überwiegend Rundungsrauschen; deshalb zeigt die COP in den beim Sensor genannten Fällen *unbekannt "
        "statt einer Zahl. Beim **Abtauen** entzieht die Wärmepumpe der Heizungsanlage Wärme, und die "
        "thermische Leistung wird negativ. Quellen: WEB ([Leistungszahl](#quellen)), INT, PL.",
    ),
    Section(
        "energy",
        "Energy counters, operating hours and overall COP",
        "Energiezähler, Betriebsstunden und Gesamt-Leistungszahl",
        "**Background.** The counters only ever go up (Home Assistant statistics class *total increasing*) and "
        "are meant for the Energy dashboard. Heat divided by electricity over a full year is the *annual "
        "performance factor* (*Jahresarbeitszahl*, JAZ). **The overall COP sensors of this integration are not a "
        "JAZ:** they divide the lifetime counters of the controller, so they average the whole life of the "
        "counters, not one year. For a JAZ take the change of both counters over a year from the Home Assistant "
        "statistics. Also note the system boundary: the usual JAZ definition leaves out auxiliary loads such as "
        "circulation pumps and electric defrost heaters. Whether the electrical counters of the controller "
        "include the auxiliary heater, and whether *total* equals the sum of the parts, is not documented "
        "(open). Sources: WEB ([Arbeitszahl](#sources), [Leistungszahl](#sources)), PL, INT.",
        "**Hintergrund.** Die Zähler laufen nur aufwärts (Statistikklasse *total increasing* in Home Assistant) "
        "und sind für das Energie-Dashboard gedacht. Wärme geteilt durch Strom über ein ganzes Jahr ist die "
        "*Jahresarbeitszahl* (JAZ). **Die Gesamt-COP-Sensoren dieser Integration sind keine JAZ:** Sie teilen die "
        "Lebensdauerzähler der Regelung und mitteln deshalb über das ganze Leben der Zähler, nicht über ein "
        "Jahr. Für eine JAZ nimmst du die Änderung beider Zähler über ein Jahr aus den Home-Assistant-"
        "Statistiken. Beachte auch die Systemgrenze: Die übliche JAZ-Definition lässt Hilfsverbraucher wie "
        "Umwälzpumpen und elektrische Abtauheizungen außen vor. Ob die Stromzähler der Regelung die "
        "Zusatzheizung enthalten und ob *gesamt* der Summe der Teile entspricht, ist nicht dokumentiert "
        "(ungeklärt). Quellen: WEB ([Arbeitszahl](#quellen), [Leistungszahl](#quellen)), PL, INT.",
    ),
    Section(
        "status",
        "Status and operating state",
        "Status und Betriebszustand",
        "**Background.** *VD1* and *VD2* are the controller's names for the compressors (*Verdichter*). *ZWE1* to "
        "*ZWE3* are additional heat generators, for example an electric heating element; direct electric heating "
        "has a COP of 1, so a running additional heater costs efficiency. On air-to-water heat pumps the "
        "evaporator ices up in cold, humid weather. The heat pump then **defrosts** by reversing the refrigerant "
        "circuit for a short time; the heat for it comes from the heating system, which is why the thermal power "
        "is negative and *operating mode* shows *defrost*. A **utility lockout** (*EVU-Sperre*) is a block by the "
        "grid operator for heat pumps on a special tariff; a supplier may switch off up to three times a day for "
        "up to two hours each. Heating, hot water, cooling and pool take turns: the *operating mode* is a "
        "single value and names only what the heat pump does right now. Sources: WEB ([Wärmepumpe](#sources), "
        "[EVU-Sperre](#sources)), PL.",
        "**Hintergrund.** *VD1* und *VD2* sind die Bezeichnungen der Regelung für die Verdichter. *ZWE1* bis "
        "*ZWE3* sind zusätzliche Wärmeerzeuger, zum Beispiel ein Elektro-Heizstab; direktes Heizen mit Strom "
        "hat eine COP von 1, ein laufender Zusatzheizer kostet also Effizienz. Bei Luft-Wasser-Wärmepumpen "
        "vereist der Verdampfer bei kalter, feuchter Witterung. Die Wärmepumpe **taut** dann **ab**, indem sie "
        "den Kältekreis kurz umkehrt; die Wärme dafür kommt aus der Heizungsanlage, deshalb ist die thermische "
        "Leistung negativ und die *Betriebsart* zeigt *Abtauen*. Eine **EVU-Sperre** ist eine Sperre des "
        "Netzbetreibers für Wärmepumpen mit Sondertarif; der Versorger darf bis zu dreimal täglich für "
        "jeweils bis zu zwei Stunden abschalten. Heizen, Warmwasser, Kühlen und Pool kommen nacheinander dran: "
        "Die *Betriebsart* ist ein einzelner Wert und nennt nur, was die Wärmepumpe gerade tut. Quellen: WEB "
        "([Wärmepumpe](#quellen), [EVU-Sperre](#quellen)), PL.",
    ),
    Section(
        "blocks",
        "Blocks (switches)",
        "Sperren (Schalter)",
        "**Background.** A *block* (*Sperre*) stops one function of the heat pump while the rest keeps running. "
        "Blocks are the tool of an optimizer such as the Heat Pump Optimizer: it blocks heating or hot water "
        "while electricity is expensive and releases them again. They are **volatile**: after a controller "
        "reboot or when the SHI watchdog expires (10 minutes without any Modbus access) they read *off* "
        "(not blocked), which is the safe state. The restore option of this integration deliberately does "
        "**not** restore blocks. Frequent switching of cooling or pool blocks may wear heat pump and hydraulic "
        "components (PL). Sources: PL, FW, INT.",
        "**Hintergrund.** Eine *Sperre* stoppt eine Funktion der Wärmepumpe, während der Rest weiterläuft. Sperren "
        "sind das Werkzeug eines Optimierers wie des Heat Pump Optimizer: Er sperrt Heizen oder Warmwasser, "
        "solange Strom teuer ist, und gibt sie wieder frei. Sie sind **flüchtig**: Nach einem Neustart der "
        "Regelung oder wenn der SHI-Watchdog abläuft (10 Minuten ohne Modbus-Zugriff), lesen sie *aus* (nicht "
        "gesperrt), also den sicheren Zustand. Die Wiederherstellungs-Option dieser Integration stellt Sperren "
        "bewusst **nicht** wieder her. Häufiges Schalten der Kühl- oder Pool-Sperre kann Wärmepumpe und "
        "Hydraulik belasten (PL). Quellen: PL, FW, INT.",
    ),
    Section(
        "heating",
        "Heating circuit control",
        "Heizkreis-Steuerung",
        "**Background: the four control modes.** The SHI does not replace the controller, it lays a correction on "
        "top of it. Every circuit has a *mode* (raw 0 to 3) that decides which of the three companion values "
        "counts:\n\n"
        "| Raw | Key | Effect |\n|---|---|---|\n"
        "| 0 | `off` | **No influence**: the controller uses its own values. This does **not** switch the circuit "
        "off, heating goes on. |\n"
        "| 1 | `setpoint` | The *setpoint* number replaces the controller's target. |\n"
        "| 2 | `offset` | The controller's target plus the *offset* in kelvin. |\n"
        "| 3 | `level` | The controller's target corrected by the *level*. |\n\n"
        "**The heating setpoint is a return temperature setpoint (tRL)**, not a flow target (PL, M). It applies "
        "**only in mode `setpoint`**; in every other mode the controller ignores it. The numbers still accept a "
        "write in any mode, because optimizers write the number and set the mode themselves; the *climate* "
        "entity refuses a target in another mode and names the mode select instead. The attributes "
        "`setpoint_active` and `effective_target` show whether the setpoint counts and what the controller really "
        "aims at. The heating curve itself (slope, level) is not accessible through the SHI; the *offset* is the "
        "SHI's way to shift the result. The value ranges are those of python-luxtronik; the controller applies "
        "its own limits on top. **Pitfall:** after a controller reboot or a watchdog expiry modes and levels "
        "read 0 and setpoints fall back to a stored or default value (not 0). The option *restore after a "
        "device reset* writes the values it set itself back (see [pitfalls](#pitfalls-and-things-to-know)). "
        "Do not let an optimizer and the climate entity write the same circuit at the same time. Sources: PL, "
        "FW, M, INT.",
        "**Hintergrund: die vier Betriebsarten.** Die SHI ersetzt die Regelung nicht, sie legt eine Korrektur "
        "darüber. Jeder Kreis hat eine *Betriebsart* (roh 0 bis 3), die entscheidet, welcher der drei "
        "zugehörigen Werte zählt:\n\n"
        "| Roh | Schlüssel | Wirkung |\n|---|---|---|\n"
        "| 0 | `off` | **Keine Vorgabe**: Die Regelung nutzt ihre eigenen Werte. Das schaltet den Kreis "
        "**nicht** ab, es wird weiter geheizt. |\n"
        "| 1 | `setpoint` | Die Zahl *Sollwert* ersetzt den Sollwert der Regelung. |\n"
        "| 2 | `offset` | Der Sollwert der Regelung plus die *Anhebung* in Kelvin. |\n"
        "| 3 | `level` | Der Sollwert der Regelung, um die *Stufe* korrigiert. |\n\n"
        "**Der Heizungs-Sollwert ist ein Rücklauf-Sollwert (tRL)**, kein Vorlauf-Sollwert (PL, M). Er gilt "
        "**nur in der Betriebsart `setpoint`**; in jeder anderen ignoriert ihn die Regelung. Die Zahlen "
        "nehmen einen Schreibzugriff trotzdem in jeder Betriebsart an, weil Optimierer die Zahl schreiben und "
        "die Betriebsart selbst setzen; die *Climate*-Entität lehnt einen Zielwert in anderer Betriebsart ab "
        "und nennt stattdessen die Auswahl der Betriebsart. Die Attribute `setpoint_active` und "
        "`effective_target` zeigen, ob der Sollwert zählt und was die Regelung tatsächlich anstrebt. Die "
        "Heizkurve selbst (Steilheit, Niveau) ist über die SHI nicht erreichbar; die *Anhebung* ist der Weg der "
        "SHI, das Ergebnis zu verschieben. Die Wertebereiche stammen aus python-luxtronik; die Regelung wendet "
        "zusätzlich ihre eigenen Grenzen an. **Fallstrick:** Nach einem Neustart der Regelung oder einem "
        "Watchdog-Ablauf lesen Betriebsarten und Stufen 0, Sollwerte fallen auf einen gespeicherten oder "
        "Standardwert zurück (nicht 0). Die Option *Werte nach einem Geräte-Reset wiederherstellen* schreibt die "
        "selbst gesetzten Werte zurück (siehe [Fallstricke](#fallstricke-und-wissenswertes)). Lass einen "
        "Optimierer und die Climate-Entität nicht gleichzeitig denselben Kreis schreiben. Quellen: PL, FW, M, INT.",
    ),
    Section(
        "hot_water",
        "Hot water control",
        "Warmwasser-Steuerung",
        "**Background.** Hot water has the same four control modes as the heating circuit (see "
        "[Heating circuit control](#8-heating-circuit-control)); the hot water setpoint is a plain hot water "
        "temperature and only counts in mode `setpoint`. **Pitfalls specific to hot water:**\n\n"
        "* **Deferred commit.** On firmware 3.92.3 writes to mode, setpoint, offset and level of hot water do not "
        "take effect at once; the controller commits them after about 10 s (inferred from the firmware, FW). The "
        "integration therefore checks a differing read-back again after 15 s and writes nothing to that "
        "register meanwhile. Writing the value that is currently stored cancels a pending write. Measured for the "
        "mode; the setpoint read back at once on the reference installation, so firmware and measurement "
        "disagree there (FW, M).\n"
        "* **Hot water block.** The owner measured that the hot water mode can only be set while the hot water "
        "block is not active; the mechanism is unknown (M). The restore after a reset therefore waits while the "
        "hot water block reads on.\n"
        "* The `water_heater` entity shows the mode as *no influence / setpoint / offset / level* and refuses a "
        "target outside mode `setpoint`.\n\n"
        "Sources: PL, FW, M, INT.",
        "**Hintergrund.** Warmwasser hat dieselben vier Betriebsarten wie der Heizkreis (siehe "
        "[Heizkreis-Steuerung](#8-heizkreis-steuerung)); der Warmwasser-Sollwert ist eine einfache "
        "Warmwassertemperatur und zählt nur in der Betriebsart `setpoint`. **Fallstricke beim Warmwasser:**\n\n"
        "* **Verzögerte Übernahme.** Auf Firmware 3.92.3 wirken Schreibzugriffe auf Betriebsart, Sollwert, "
        "Anhebung und Stufe des Warmwassers nicht sofort; die Regelung übernimmt sie nach etwa 10 s (aus der "
        "Firmware abgeleitet, FW). Die Integration prüft deshalb einen abweichenden Rücklesewert nach 15 s "
        "erneut und schreibt in der Zwischenzeit nichts in das Register. Das Schreiben des aktuell "
        "gespeicherten Wertes bricht einen ausstehenden Schreibzugriff ab. Gemessen für die Betriebsart; der "
        "Sollwert las an der Referenzanlage sofort zurück, Firmware und Messung widersprechen sich dort "
        "(FW, M).\n"
        "* **Warmwasser-Sperre.** Der Eigentümer hat gemessen, dass sich die Warmwasser-Betriebsart nur setzen "
        "lässt, solange die Warmwasser-Sperre nicht aktiv ist; der Mechanismus ist unbekannt (M). Die "
        "Wiederherstellung nach einem Reset wartet deshalb, solange die Warmwasser-Sperre an liest.\n"
        "* Die `water_heater`-Entität zeigt die Betriebsart als *keine Vorgabe / Sollwert / Anhebung / Stufe* und "
        "lehnt einen Zielwert außerhalb der Betriebsart `setpoint` ab.\n\n"
        "Quellen: PL, FW, M, INT.",
    ),
    Section(
        "mixing",
        "Mixing circuit control (heating)",
        "Mischkreis-Steuerung (Heizen)",
        "**Background.** Mixing circuits 1 to 3 have the same four control modes as the heating circuit (see "
        "[Heating circuit control](#8-heating-circuit-control)). In contrast to the main heating setpoint, "
        "their setpoint is a **flow temperature** of the circuit (PL). The ranges are narrower: setpoint "
        "20 to 65 °C, offset -5 to +5 K. The entities exist only for circuits that are selected in the "
        "equipment. Sources: PL, INT.",
        "**Hintergrund.** Die Mischkreise 1 bis 3 haben dieselben vier Betriebsarten wie der Heizkreis (siehe "
        "[Heizkreis-Steuerung](#8-heizkreis-steuerung)). Anders als beim Haupt-Heizungs-Sollwert ist ihr "
        "Sollwert eine **Vorlauftemperatur** des Kreises (PL). Die Bereiche sind enger: Sollwert 20 bis 65 °C, "
        "Anhebung -5 bis +5 K. Die Entitäten gibt es nur für Kreise, die in der Ausstattung gewählt sind. "
        "Quellen: PL, INT.",
    ),
    Section(
        "cooling_pool",
        "Cooling and pool",
        "Kühlen und Pool",
        "**Background.** Cooling and pool heating only exist if the installation has them (selected in the "
        "equipment; the *equipment* flags of the controller pre-select the answer). Cooling has no *level*: "
        "the controller offers mode, setpoint and offset per mixing circuit. The cooling setpoint is a flow "
        "temperature of the circuit. A *cooling release* is a condition of the controller; it only counts if "
        "cooling is configured (PL). Sources: PL, INT.",
        "**Hintergrund.** Kühlen und Pool-Heizen gibt es nur, wenn die Anlage sie hat (in der Ausstattung gewählt; "
        "die *Ausstattungs*-Flags der Regelung füllen die Antwort vor). Beim Kühlen gibt es keine *Stufe*: Die "
        "Regelung bietet Betriebsart, Sollwert und Anhebung je Mischkreis. Der Kühl-Sollwert ist eine "
        "Vorlauftemperatur des Kreises. Eine *Kühlfreigabe* ist eine Bedingung der Regelung; sie zählt nur, "
        "wenn Kühlen konfiguriert ist (PL). Quellen: PL, INT.",
    ),
    Section(
        "power_limit",
        "Power limit",
        "Leistungsbegrenzung",
        "**Background.** The power limit (*LPC*, limitation of power consumption) caps the electrical power of "
        "the heat pump. *Soft* is a recommendation that is meant for PV surplus: the heat pump tries to stay "
        "below the value, but ignores it if the actual temperature deviates too far from the target (outside "
        "its hysteresis). *Hard* limits the consumption regardless of the hysteresis and may reduce comfort; "
        "python-luxtronik recommends it only for §14a EnWG. §14a EnWG lets the grid operator reduce "
        "controllable consumers such as heat pumps; the lower bound is 4.2 kW (per device). Both entities are "
        "deliberately not restored after a reset: an optimizer owns them. Sources: PL, WEB ([§14a EnWG](#sources)).",
        "**Hintergrund.** Die Leistungsbegrenzung (*LPC*, limitation of power consumption) deckelt die elektrische "
        "Leistung der Wärmepumpe. *Weich* ist eine Empfehlung, gedacht für PV-Überschuss: Die Wärmepumpe "
        "versucht, unter dem Wert zu bleiben, ignoriert ihn aber, wenn die Ist-Temperatur zu weit vom Sollwert "
        "abweicht (außerhalb ihrer Hysterese). *Hart* begrenzt den Verbrauch unabhängig von der Hysterese und "
        "kann den Komfort mindern; python-luxtronik empfiehlt das nur für §14a EnWG. Nach §14a EnWG darf der "
        "Netzbetreiber steuerbare Verbraucher wie Wärmepumpen drosseln; die Untergrenze liegt bei 4,2 kW (je "
        "Gerät). Beide Entitäten werden nach einem Reset bewusst nicht wiederhergestellt: Ein Optimierer "
        "besitzt sie. Quellen: PL, WEB ([§14a EnWG](#quellen)).",
    ),
    Section(
        "overall",
        "Overall heating",
        "Gesamt-Heizen",
        "**Background.** The *overall* group (10065 to 10067) acts on all heating functions at once and "
        "overrides the per-circuit settings (PL: \"operating mode of all heating functions (no setpoint "
        "available)\"). Its effect is **not proven**: on the reference installation 10065 fell back to *no "
        "influence* about 2 seconds after a write (M). The entities are therefore disabled by default and not "
        "restored after a reset. Sources: PL, M, INT.",
        "**Hintergrund.** Die *Gesamt*-Gruppe (10065 bis 10067) wirkt auf alle Heizfunktionen zugleich und "
        "übersteuert die Einstellungen der einzelnen Kreise (PL: „Betriebsart aller Heizfunktionen (kein "
        "Sollwert verfügbar)“). Ihre Wirkung ist **nicht belegt**: An der Referenzanlage fiel 10065 etwa "
        "2 Sekunden nach dem Schreiben auf *keine Vorgabe* zurück (M). Die Entitäten sind deshalb standardmäßig "
        "deaktiviert und werden nach einem Reset nicht wiederhergestellt. Quellen: PL, M, INT.",
    ),
    Section(
        "system",
        "System, firmware and equipment",
        "Anlage, Firmware und Ausstattung",
        "**Background: buffer tank.** A *buffer tank* (*Pufferspeicher*) holds heating water between heat pump and "
        "heating circuits. A **series buffer** (*Reihenpuffer*) sits in the return and is flowed through by "
        "all of the water, so practically nothing is lost; it evens out the flow and gives a reserve for "
        "defrosting. A **separation buffer** (*Trennpuffer*) decouples the heat pump circuit from the heating "
        "circuits with separate pumps; flow and return mix a little in the tank, which costs about 2 to 5 K "
        "and with it some efficiency. A **multi-function buffer** combines more functions in one tank. "
        "Because a heat pump should not switch on and off too often, the controller also keeps a *minimum "
        "runtime* and a *switching lock* (minimum off time); on the reference installation the firmware "
        "returns both as constants (20 minutes, FW). The **equipment flags** (`cap_*`) are discrete inputs "
        "that tell which parts the installation has; the setup dialog uses them to pre-select the equipment. "
        "The firmware version is read from three registers and is only informational. Sources: PL, FW, OBS, WEB "
        "([Reihenpuffer und Trennpuffer](#sources)).",
        "**Hintergrund: Pufferspeicher.** Ein *Pufferspeicher* hält Heizwasser zwischen Wärmepumpe und "
        "Heizkreisen vor. Ein **Reihenpuffer** sitzt im Rücklauf und wird vom gesamten Wasser durchströmt, "
        "es geht praktisch nichts verloren; er gleicht den Volumenstrom aus und gibt eine Reserve für das "
        "Abtauen. Ein **Trennpuffer** entkoppelt den Wärmepumpenkreis mit getrennten Pumpen von den "
        "Heizkreisen; Vor- und Rücklauf vermischen sich im Speicher etwas, das kostet etwa 2 bis 5 K und damit "
        "etwas Effizienz. Ein **Multifunktionspuffer** vereint mehrere Funktionen in einem Speicher. Weil eine "
        "Wärmepumpe nicht zu oft ein- und ausschalten soll, hält die Regelung außerdem eine "
        "*Mindestlaufzeit* und eine *Schaltspielsperre* (Mindest-Ausschaltzeit) ein; an der Referenzanlage "
        "liefert die Firmware beide als Konstanten (20 Minuten, FW). Die **Ausstattungs-Flags** (`cap_*`) sind "
        "Discrete Inputs, die sagen, welche Teile die Anlage hat; der Einrichtungsdialog nutzt sie, um die "
        "Ausstattung vorzuwählen. Die Firmware-Version wird aus drei Registern gelesen und ist nur "
        "informativ. Quellen: PL, FW, OBS, WEB ([Reihen- und Trennpuffer](#quellen)).",
    ),
    Section(
        "raw",
        "Raw values",
        "Rohwerte",
        "**Background.** Registers whose meaning nobody has established are exposed as `raw_<address>` "
        "diagnostic sensors. A few have a meaning proven by the firmware since 0.11.0 (10113, 10350 to 10356, 10360 "
        "and 10361): they keep the key `raw_<address>` and only have a name, unit and scale. All of them are **disabled by default**, read only (never written), polled rarely, shown as the "
        "plain number (10113 is scaled to degrees). They exist for analysis and reverse engineering. Do not build automations on "
        "them. Sources: PL, FW.",
        "**Hintergrund.** Register, deren Bedeutung niemand geklärt hat, gibt es als Diagnose-Sensoren "
        "`raw_<Adresse>`. Einige haben seit 0.11.0 eine von der Firmware belegte Bedeutung (10113, 10350 bis 10356, "
        "10360 und 10361): Sie behalten den Schlüssel `raw_<Adresse>` und haben nur Name, Einheit und Skalierung. "
        "Alle sind **standardmäßig deaktiviert**, nur lesend (nie geschrieben), selten abgefragt, als "
        "einfache Zahl (10113 ist in Grad skaliert). Sie dienen der Analyse und dem Reverse Engineering. Baue keine Automationen "
        "darauf. Quellen: PL, FW.",
    ),
)


# ---------------------------------------------------------------------------------------------- page texts
PAGE = {
    "en": {
        "title": "Entity reference",
        "lead": (
            "Every entity of the Luxtronik SHI integration, sorted by topic, with what it measures or controls, "
            "its unit, value range and the pitfalls. Short background explanations of how heat pumps work stand "
            "at the start of each topic. German version: [entities.de.md](entities.de.md)."
        ),
        "generated": (
            "This page is generated by `tools/gen_entity_docs.py` from the register map, the platforms, the "
            "translations and `tools/entity_docs_texts.py` / `tools/entity_docs_entries.py`. Do not edit it by "
            "hand: change the sources and run `python tools/gen_entity_docs.py`. `tests/test_entity_docs.py` "
            "fails if the page is out of date or an entity has no explanation."
        ),
        "how_title": "How to read this page",
        "how": (
            "* **Name** is the name on the device page. Home Assistant puts the device name in front, for example "
            "\"Heat pump Heating Setpoint\".\n"
            "* **Key** is the stable identifier. The unique ID is `<entry_id>_<key>` and never changes; the entity "
            "ID is derived from device and name when the entity is first created. Below the key: the platform, "
            "the Modbus table with the register address, and the device it sits in.\n"
            "* **Range / values** shows the write range of numbers, the options of selects and enumerations "
            "(raw number, key, shown text) and the meaning of raw numbers.\n"
            "* **Sources** at the end of an explanation: {legend}.\n"
            "* The notes in italics below an explanation are generated from the code: disabled by default, "
            "category, needed equipment, polling rate, restore behaviour.\n"
            "* Registers are polled in tiers: the base interval (default 30 s) for measurements, every Nth "
            "interval for slow values; a write is read back at once.\n"
            "* A value the controller reports as *not available* is the raw number 32767 (0x7FFF), see the "
            "pitfalls."
        ),
        "contents": "Contents",
        "cols": ("Name", "Key", "Unit", "Range / values", "Explanation"),
        "overview_title": "Entities by platform",
        "overview_cols": ("Platform", "Count", "What it is"),
        "platform_text": {
            "sensor": "measurements, counters, calculated values, enumerations",
            "binary_sensor": "status bits, equipment flags, connection",
            "switch": "blocks, circulation pump, extra hot water (0/1 holding registers), on/off view of the blocks",
            "number": "writable setpoints, offsets, power limit",
            "select": "writable modes, levels, power limit mode, operating mode view of the blocks",
            "climate": "thermostat view of the heating circuit",
            "water_heater": "water heater view of hot water",
        },
        "no_name": "(named after the device)",
        "none": "-",
        "on_off": "on / off",
        "switch_values": "0 = off, 1 = on",
        "derived": "calculated, no register",
        "view": "view on several registers",
        "renamed_title": "Renamed keys",
        "renamed_text": (
            "These keys were renamed. The old key stays in the entity contract, the integration moves the "
            "registry entry, and the entity ID stays."
        ),
        "renamed_cols": ("Old key", "New key"),
        "index_title": "Index of all keys",
        "index_cols": ("Key", "Platform", "Topic"),
        "sources_title": "Sources",
        "devices": {
            None: "Heat pump", "heating": "Heating", "hot_water": "Hot water", "cooling": "Cooling", "pool": "Pool",
        },
        "features": {
            "mk1": "mixing circuit 1", "mk2": "mixing circuit 2", "mk3": "mixing circuit 3",
            "cooling": "cooling", "pool": "pool", "room_unit": "room unit", "solar": "solar",
        },
        "flags": {
            "disabled": "disabled by default",
            "diagnostic": "category Diagnostic",
            "config": "category Configuration",
            "needs": "needs {parts} in the equipment",
            "every": "read every {n} polls",
            "restored": "restored after a device reset (option)",
            "deferred": "deferred commit (about 10 s)",
            "writable": "writable",
        },
        "device_word": "device",
        "pitfalls_title": "Pitfalls and things to know",
    },
    "de": {
        "title": "Entitäten-Referenz",
        "lead": (
            "Jede Entität der Luxtronik-SHI-Integration, nach Themen sortiert, mit dem, was sie misst oder "
            "steuert, ihrer Einheit, dem Wertebereich und den Fallstricken. Kurze Hintergrunderklärungen zur "
            "Funktionsweise von Wärmepumpen stehen am Anfang jedes Themas. Englische Version: "
            "[entities.md](entities.md)."
        ),
        "generated": (
            "Diese Seite wird von `tools/gen_entity_docs.py` aus Registerkarte, Plattformen, Übersetzungen und "
            "`tools/entity_docs_texts.py` / `tools/entity_docs_entries.py` erzeugt. Nicht von Hand ändern: Ändere "
            "die Quellen und führe `python tools/gen_entity_docs.py` aus. `tests/test_entity_docs.py` schlägt "
            "fehl, wenn die Seite veraltet ist oder eine Entität keine Erklärung hat."
        ),
        "how_title": "So liest du diese Seite",
        "how": (
            "* **Name** ist der Name auf der Geräteseite. Home Assistant setzt den Gerätenamen davor, zum Beispiel "
            "„Wärmepumpe Heizung Sollwert“.\n"
            "* **Schlüssel** ist die stabile Kennung. Die Unique-ID ist `<entry_id>_<Schlüssel>` und ändert sich "
            "nie; die Entity-ID wird beim ersten Anlegen aus Gerät und Name gebildet. Unter dem Schlüssel: "
            "Plattform, Modbus-Tabelle mit Registeradresse und das Gerät, in dem die Entität liegt.\n"
            "* **Bereich / Werte** zeigt den Schreibbereich von Zahlen, die Optionen von Auswahlen und "
            "Aufzählungen (Rohzahl, Schlüssel, angezeigter Text) und die Bedeutung roher Zahlen.\n"
            "* **Quellen** am Ende einer Erklärung: {legend}.\n"
            "* Die kursiven Hinweise unter einer Erklärung werden aus dem Code erzeugt: standardmäßig "
            "deaktiviert, Kategorie, benötigte Ausstattung, Abfragetakt, Wiederherstellung.\n"
            "* Register werden gestaffelt abgefragt: im Basisintervall (Standard 30 s) die Messwerte, nur jedes "
            "N-te Intervall die langsamen Werte; ein Schreibzugriff wird sofort zurückgelesen.\n"
            "* Einen Wert, den die Regelung als *nicht verfügbar* meldet, liefert sie als Rohzahl 32767 (0x7FFF), "
            "siehe die Fallstricke."
        ),
        "contents": "Inhalt",
        "cols": ("Name", "Schlüssel", "Einheit", "Bereich / Werte", "Erklärung"),
        "overview_title": "Entitäten nach Plattform",
        "overview_cols": ("Plattform", "Anzahl", "Was es ist"),
        "platform_text": {
            "sensor": "Messwerte, Zähler, berechnete Werte, Aufzählungen",
            "binary_sensor": "Statusbits, Ausstattungs-Flags, Verbindung",
            "switch": "Sperren, Zirkulationspumpe, Extra-Warmwasser (0/1-Holding-Register), Ein/Aus-Sicht auf die Sperren",
            "number": "schreibbare Sollwerte, Anhebungen, Leistungsbegrenzung",
            "select": "schreibbare Betriebsarten, Stufen, Modus der Leistungsbegrenzung, Betriebsart-Sicht auf die Sperren",
            "climate": "Thermostat-Sicht auf den Heizkreis",
            "water_heater": "Water-Heater-Sicht auf das Warmwasser",
        },
        "no_name": "(trägt den Gerätenamen)",
        "none": "-",
        "on_off": "an / aus",
        "switch_values": "0 = aus, 1 = an",
        "derived": "berechnet, kein Register",
        "view": "Sicht auf mehrere Register",
        "renamed_title": "Umbenannte Schlüssel",
        "renamed_text": (
            "Diese Schlüssel wurden umbenannt. Der alte Schlüssel bleibt im Entitäten-Vertrag, die Integration "
            "verschiebt den Registry-Eintrag, und die Entity-ID bleibt."
        ),
        "renamed_cols": ("Alter Schlüssel", "Neuer Schlüssel"),
        "index_title": "Index aller Schlüssel",
        "index_cols": ("Schlüssel", "Plattform", "Thema"),
        "sources_title": "Quellen",
        "devices": {
            None: "Wärmepumpe", "heating": "Heizung", "hot_water": "Warmwasser", "cooling": "Kühlung", "pool": "Pool",
        },
        "features": {
            "mk1": "Mischkreis 1", "mk2": "Mischkreis 2", "mk3": "Mischkreis 3",
            "cooling": "Kühlung", "pool": "Pool", "room_unit": "Raumeinheit", "solar": "Solar",
        },
        "flags": {
            "disabled": "standardmäßig deaktiviert",
            "diagnostic": "Kategorie Diagnose",
            "config": "Kategorie Konfiguration",
            "needs": "braucht {parts} in der Ausstattung",
            "every": "gelesen alle {n} Abfragen",
            "restored": "wird nach einem Geräte-Reset wiederhergestellt (Option)",
            "deferred": "verzögerte Übernahme (etwa 10 s)",
            "writable": "schreibbar",
        },
        "device_word": "Gerät",
        "pitfalls_title": "Fallstricke und Wissenswertes",
    },
}

# Pitfalls. ``{restored}`` is filled with the keys of const.RESTORE_KEYS.
PITFALLS = {
    "en": (
        "1. **Values set over the SHI are volatile.** The controller discards every value set over Modbus when it "
        "reboots, and when nothing has accessed the SHI for 600 s (10 minutes); every Modbus access resets that "
        "timer, a pure read included. While the integration polls, the watchdog does not expire; the maximum "
        "update interval is therefore 300 s. After a reset **modes, levels, offsets, blocks and triggers read "
        "0**, the **setpoints read their firmware defaults** (heating and mixing circuits 35.0 °C, hot water "
        "40.0 °C, cooling 20.0 °C, power limit 30.0 kW) and the room setpoint its persisted controller value. "
        "Expiry and return are written to the controller's event log. A Home Assistant downtime of more than "
        "10 minutes has the same effect. Blocks reading 0 means *not blocked*: the heat pump falls back to its "
        "own control (FW, proven).\n"
        "2. **Restore after a device reset** is an option, off by default. When on, the integration writes back the "
        "values it set itself, but only after a connection outage and only if every one of them reads its reset "
        "value; a change seen during continuous polling counts as somebody else's. Restored keys: {restored}. "
        "Blocks, circulation pump, extra hot water, the power limit and the overall group are deliberately "
        "left out. Leave the option off if another system also writes these registers.\n"
        "3. **A setpoint only counts in its mode `setpoint`.** In `off`, `offset` and `level` the controller "
        "ignores it. The setpoint numbers still write in every mode; climate and water heater refuse. Check "
        "`setpoint_active` and `effective_target`.\n"
        "4. **Mode `off` is \"no influence\", not off.** To stop heating use the heating block; to stop hot water "
        "the hot water block.\n"
        "5. **Hot water writes are committed late** (about 10 s) and not while the hot water block is on, see "
        "[hot water control](#9-hot-water-control).\n"
        "6. **Two writers overwrite each other.** The Heat Pump Optimizer, OpenEMS, the native Luxtronik "
        "integration (port 8889), the controller panel and this integration write the same settings; the last "
        "write wins. A change that did not come from Home Assistant raises the repair issue *Value changed "
        "outside Home Assistant*; nothing is written back.\n"
        "7. **Not available.** A register the controller reports as unavailable reads the raw number 32767 "
        "(0x7FFF), for example 3276.7 on a temperature sensor. The temperature sensors and the error number show "
        "*unavailable* for it, and so do the calculated entities that use them; other registers are not "
        "translated, treat 32767 there as unknown. A register that does not exist at all makes the entity *unknown*.\n"
        "8. **Equipment decides which entities exist.** Parts that are switched off in the options are not polled "
        "and get no entities; their entity IDs stay reserved. Do not switch off a part that an optimizer reads "
        "or writes (for example mixing circuit 1).\n"
        "9. **Write ranges are the firmware's.** A write outside the range is acknowledged by the firmware, but "
        "the register is **reset to its default** instead of keeping the previous value (FW, proven). The "
        "integration therefore never sends such a value (number limits, climate, water heater and the restore "
        "refuse it). A read-back that shows the default after a write is reported as an error: the cause is "
        "then error 816 (more than two write sources within an hour) or a watchdog expiry. The controller "
        "clamps the effect on top: the heating setpoint to [return target minimum, return limit], the hot water "
        "target to the maximum hot water temperature.\n"
        "10. **The overall group takes precedence.** While `cfg_overall_mode` is not `off`, the heating mode and "
        "the mixing circuit modes are ignored; the overall mode has no setpoint (its mode `setpoint` acts like "
        "`off` and is refused). Levels: 1 and 2 both raise by the controller parameter *Erhöhung*, 3 lowers by "
        "*Absenkung* (menu *Offsets*, set at the control panel).\n"
        "11. **Enable SHI.** The controller parameter *Enable SHI* (1161, menu: Modbus TCP / myUplink / both) "
        "cannot be read over Modbus. While it is off, setpoints, offsets, levels and the power limit are read "
        "back correctly but have no effect; blocks, circulation and extra hot water work regardless. The "
        "diagnostics download names it (FW, proven).\n"
        "12. **Slow values** (counters, hours, settings, firmware) are read only every Nth poll, so they can lag "
        "by several update intervals."
    ),
    "de": (
        "1. **Über die SHI gesetzte Werte sind flüchtig.** Die Regelung verwirft jeden über Modbus gesetzten Wert, "
        "wenn sie neu startet und wenn 600 s (10 Minuten) lang niemand auf die SHI zugegriffen hat; jeder "
        "Modbus-Zugriff setzt diesen Zeitgeber zurück, auch ein reines Lesen. Solange die Integration abfragt, "
        "läuft der Watchdog nicht ab; das größte Aktualisierungsintervall ist deshalb 300 s. Nach einem Reset "
        "lesen **Betriebsarten, Stufen, Anhebungen, Sperren und Trigger 0**, die **Sollwerte ihre "
        "Firmware-Standardwerte** (Heizung und Mischkreise 35,0 °C, Warmwasser 40,0 °C, Kühlung 20,0 °C, "
        "Leistungsbegrenzung 30,0 kW) und der Raumsollwert seinen gespeicherten Reglerwert. Ablauf und "
        "Wiederkehr landen im Ereignisprotokoll der Regelung. Eine Auszeit von Home Assistant über 10 Minuten "
        "wirkt genauso. Sperren, die 0 lesen, heißt *nicht gesperrt*: Die Wärmepumpe fällt auf ihre eigene "
        "Regelung zurück (FW, belegt).\n"
        "2. **Wiederherstellung nach einem Geräte-Reset** ist eine Option, standardmäßig aus. Ist sie an, schreibt "
        "die Integration die selbst gesetzten Werte zurück, aber nur nach einem Verbindungsausfall und nur, wenn "
        "jeder davon seinen Reset-Wert liest; eine Änderung bei durchgehender Abfrage gilt als fremd. "
        "Wiederhergestellte Schlüssel: {restored}. Sperren, Zirkulationspumpe, Extra-Warmwasser, die "
        "Leistungsbegrenzung und die Gesamt-Gruppe sind bewusst ausgenommen. Lass die Option aus, wenn ein "
        "anderes System diese Register ebenfalls schreibt.\n"
        "3. **Ein Sollwert zählt nur in seiner Betriebsart `setpoint`.** In `off`, `offset` und `level` ignoriert "
        "ihn die Regelung. Die Sollwert-Zahlen schreiben trotzdem in jeder Betriebsart; Climate und Water "
        "Heater lehnen ab. Prüfe `setpoint_active` und `effective_target`.\n"
        "4. **Die Betriebsart `off` heißt „keine Vorgabe“, nicht aus.** Zum Stoppen des Heizens nimm die "
        "Heizungs-Sperre, für das Warmwasser die Warmwasser-Sperre.\n"
        "5. **Warmwasser-Schreibzugriffe werden spät übernommen** (etwa 10 s) und nicht, solange die "
        "Warmwasser-Sperre an ist, siehe [Warmwasser-Steuerung](#9-warmwasser-steuerung).\n"
        "6. **Zwei Schreiber überschreiben sich.** Heat Pump Optimizer, OpenEMS, die native "
        "Luxtronik-Integration (Port 8889), das Bedienteil und diese Integration schreiben dieselben "
        "Einstellungen; der letzte Schreibzugriff gewinnt. Eine Änderung, die nicht von Home Assistant kam, "
        "erzeugt den Reparaturhinweis *Wert außerhalb von Home Assistant geändert*; zurückgeschrieben wird "
        "nichts.\n"
        "7. **Nicht verfügbar.** Ein Register, das die Regelung als nicht verfügbar meldet, liest die Rohzahl "
        "32767 (0x7FFF), zum Beispiel 3276,7 an einem Temperatursensor. Die Temperatursensoren und die "
        "Fehlernummer zeigen dafür *nicht verfügbar*, ebenso die berechneten Entitäten, die sie nutzen; andere "
        "Register werden nicht übersetzt, behandle 32767 dort als unbekannt. Ein Register, das gar nicht existiert, macht die Entität "
        "*unbekannt*.\n"
        "8. **Die Ausstattung bestimmt, welche Entitäten es gibt.** Abgewählte Teile werden nicht abgefragt und "
        "bekommen keine Entitäten; ihre Entity-IDs bleiben reserviert. Wähle keinen Teil ab, den ein "
        "Optimierer liest oder schreibt (zum Beispiel Mischkreis 1).\n"
        "9. **Die Schreibbereiche sind die der Firmware.** Einen Wert außerhalb des Bereichs bestätigt die "
        "Firmware zwar, setzt das Register aber auf seinen **Standardwert zurück**, statt den vorherigen Wert zu "
        "behalten (FW, belegt). Die Integration schickt einen solchen Wert deshalb nie (Grenzen der Zahlen, "
        "Climate, Water Heater und die Wiederherstellung lehnen ab). Liest ein Register nach dem Schreiben "
        "seinen Standardwert, wird das als Fehler gemeldet: Ursache ist dann Fehler 816 (mehr als zwei "
        "Schreibquellen innerhalb einer Stunde) oder ein Ablauf des Wächters. Die Regelung begrenzt zusätzlich "
        "die Wirkung: den Heizungs-Sollwert auf [Rücklauf-Soll Minimum, Rücklauf-Begrenzung], das "
        "Warmwasser-Ziel auf die maximale Warmwassertemperatur.\n"
        "10. **Die Gesamt-Gruppe hat Vorrang.** Solange `cfg_overall_mode` nicht `off` ist, werden die "
        "Heizungs-Betriebsart und die Mischkreis-Betriebsarten ignoriert; die Gesamt-Betriebsart hat keinen "
        "Sollwert (ihre Betriebsart `setpoint` wirkt wie `off` und wird abgelehnt). Stufen: 1 und 2 erhöhen "
        "beide um den Reglerparameter *Erhöhung*, 3 senkt um *Absenkung* (Menü *Offsets*, am Bedienteil "
        "eingestellt).\n"
        "11. **Enable SHI.** Der Reglerparameter *Enable SHI* (1161, Menü: Modbus TCP / myUplink / beides) lässt "
        "sich über Modbus nicht lesen. Steht er aus, werden Sollwerte, Anhebungen, Stufen und die "
        "Leistungsbegrenzung korrekt zurückgelesen, wirken aber nicht; Sperren, Zirkulation und "
        "Extra-Warmwasser funktionieren trotzdem. Der Diagnose-Download nennt ihn (FW, belegt).\n"
        "12. **Langsame Werte** (Zähler, Stunden, Einstellungen, Firmware) werden nur jede N-te Abfrage gelesen "
        "und können deshalb mehrere Aktualisierungsintervalle hinterherhinken."
    ),
}

WEB_SOURCES = (
    ("Heizkurve", "https://de.wikipedia.org/wiki/Heizkurve", "Wikipedia: Heizkurve"),
    ("Wärmepumpe", "https://de.wikipedia.org/wiki/Wärmepumpe", "Wikipedia: Wärmepumpe"),
    ("Leistungszahl", "https://de.wikipedia.org/wiki/Leistungszahl", "Wikipedia: Leistungszahl"),
    ("Zweipunktregler", "https://de.wikipedia.org/wiki/Zweipunktregler", "Wikipedia: Zweipunktregler"),
    ("Arbeitszahl", "https://www.energiesparhaus.at/fachbegriffe/arbeitszahl.htm",
     "energiesparhaus.at: Arbeitszahl (Jahresarbeitszahl, JAZ)"),
    ("UBA factsheet", "https://www.umweltbundesamt.de/sites/default/files/medien/11850/publikationen/"
     "factsheet_trinkwarmwasserkonzepte.pdf", "Umweltbundesamt: Factsheet Trinkwarmwasserkonzepte"),
    ("Reihenpuffer und Trennpuffer", "https://elektronik-zeit.de/waermepumpe/reihenpuffer-trennpuffer-vergleich/",
     "elektronik-zeit.de: Reihenpuffer vs. Trennpuffer"),
    ("EVU-Sperre", "https://www.baunetzwissen.de/glossar/e/evu-sperre-9514499", "baunetzwissen.de: EVU-Sperre"),
    ("§14a EnWG", "https://42watt.de/magazin/paragraph-14a-enwg", "42watt.de: § 14a EnWG"),
)
