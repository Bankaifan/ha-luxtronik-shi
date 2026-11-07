# Entitäten-Referenz

Jede Entität der Luxtronik-SHI-Integration, nach Themen sortiert, mit dem, was sie misst oder steuert, ihrer Einheit, dem Wertebereich und den Fallstricken. Kurze Hintergrunderklärungen zur Funktionsweise von Wärmepumpen stehen am Anfang jedes Themas. Englische Version: [entities.md](entities.md).

> Diese Seite wird von `tools/gen_entity_docs.py` aus Registerkarte, Plattformen, Übersetzungen und `tools/entity_docs_texts.py` / `tools/entity_docs_entries.py` erzeugt. Nicht von Hand ändern: Ändere die Quellen und führe `python tools/gen_entity_docs.py` aus. `tests/test_entity_docs.py` schlägt fehl, wenn die Seite veraltet ist oder eine Entität keine Erklärung hat.

## So liest du diese Seite

* **Name** ist der Name auf der Geräteseite. Home Assistant setzt den Gerätenamen davor, zum Beispiel „Wärmepumpe Heizung Sollwert“.
* **Schlüssel** ist die stabile Kennung. Die Unique-ID ist `<entry_id>_<Schlüssel>` und ändert sich nie; die Entity-ID wird beim ersten Anlegen aus Gerät und Name gebildet. Unter dem Schlüssel: Plattform, Modbus-Tabelle mit Registeradresse und das Gerät, in dem die Entität liegt.
* **Bereich / Werte** zeigt den Schreibbereich von Zahlen, die Optionen von Auswahlen und Aufzählungen (Rohzahl, Schlüssel, angezeigter Text) und die Bedeutung roher Zahlen.
* **Quellen** am Ende einer Erklärung: **PL** python-luxtronik (Bouni/python-luxtronik, `luxtronik/definitions/{inputs,holdings}.py`, `datatypes.py`); **FW** [Firmware-Analyse](firmware-3.92.3-shi-analysis.md) von V3.92.3 (englisch); **M** Messung an der Referenzanlage (LWDV 91-1/3, Firmware 3.92.3), dokumentiert in README oder CHANGELOG; **OBS** nur Beobachtung, keine schriftliche Quelle; **INT** Festlegung oder Berechnung dieser Integration; **WEB** allgemeiner Hintergrund, siehe die [Quellen](#quellen) unten.
* Die kursiven Hinweise unter einer Erklärung werden aus dem Code erzeugt: standardmäßig deaktiviert, Kategorie, benötigte Ausstattung, Abfragetakt, Wiederherstellung.
* Register werden gestaffelt abgefragt: im Basisintervall (Standard 30 s) die Messwerte, nur jedes N-te Intervall die langsamen Werte; ein Schreibzugriff wird sofort zurückgelesen.
* Einen Wert, den die Regelung als *nicht verfügbar* meldet, liefert sie als Rohzahl 32767 (0x7FFF), siehe die Fallstricke.

## Entitäten nach Plattform

| Plattform | Anzahl | Was es ist |
|---|---|---|
| `sensor` | 81 | Messwerte, Zähler, berechnete Werte, Aufzählungen |
| `binary_sensor` | 22 | Statusbits, Ausstattungs-Flags, Verbindung |
| `switch` | 6 | Sperren, Zirkulationspumpe, Extra-Warmwasser (0/1-Holding-Register) |
| `number` | 19 | schreibbare Sollwerte, Anhebungen, Leistungsbegrenzung |
| `select` | 16 | schreibbare Betriebsarten, Stufen, Modus der Leistungsbegrenzung |
| `climate` | 1 | Thermostat-Sicht auf den Heizkreis |
| `water_heater` | 1 | Water-Heater-Sicht auf das Warmwasser |

## Inhalt

1. [Temperaturen des Heizkreises](#1-temperaturen-des-heizkreises)
2. [Warmwassertemperaturen](#2-warmwassertemperaturen)
3. [Temperaturen der Mischkreise](#3-temperaturen-der-mischkreise)
4. [Leistung und berechnete Leistungszahl](#4-leistung-und-berechnete-leistungszahl)
5. [Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl)
6. [Status und Betriebszustand](#6-status-und-betriebszustand)
7. [Sperren (Schalter)](#7-sperren-schalter)
8. [Heizkreis-Steuerung](#8-heizkreis-steuerung)
9. [Warmwasser-Steuerung](#9-warmwasser-steuerung)
10. [Mischkreis-Steuerung (Heizen)](#10-mischkreis-steuerung-heizen)
11. [Kühlen und Pool](#11-kühlen-und-pool)
12. [Leistungsbegrenzung](#12-leistungsbegrenzung)
13. [Gesamt-Heizen](#13-gesamt-heizen)
14. [Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung)
15. [Rohwerte](#15-rohwerte)
- [Fallstricke und Wissenswertes](#fallstricke-und-wissenswertes)
- [Umbenannte Schlüssel](#umbenannte-schlüssel)
- [Index aller Schlüssel](#index-aller-schlüssel)
- [Quellen](#quellen)

## 1. Temperaturen des Heizkreises

**Hintergrund.** Eine Wärmepumpe erwärmt das Wasser, das durch die Heizungsanlage läuft (der *Vorlauf*), und bekommt es abgekühlt zurück (der *Rücklauf*). Der Unterschied beider Temperaturen ist die *Spreizung*. Die Integration hat dafür keine eigene Entität; Vorlauf minus Rücklauf in einem Template-Sensor liefert sie. Die Luxtronik-Regelung regelt auf die **Rücklauftemperatur**: Der Heizungs-Sollwert der SHI wirkt auf sie (siehe [Heizen](#8-heizkreis-steuerung)). Ihr normaler Sollwert kommt aus der *Heizkurve*. Sie ordnet jeder Außentemperatur eine Wassertemperatur zu: Die *Steilheit* sagt, wie stark die Wassertemperatur der Außentemperatur folgt, das *Niveau* (oder die Anhebung) verschiebt die ganze Kurve nach oben oder unten. Oberhalb der *Heizgrenze* (einer Außentemperatur) schaltet ein Heizkurvenregler die Heizung ab. Je niedriger die Wassertemperatur, die eine Wärmepumpe liefern muss, desto effizienter arbeitet sie: Der deutsche Wikipedia-Artikel zur Wärmepumpe nennt als Beispiel eine Leistungszahl, die von 4,8 (B0/W35) auf 3,6 (B0/W50) fällt.

**Fallstrick: Rücklauf und Rücklauf-Soll.** Die veröffentlichte Registerliste nennt 10100 *Rücklauf-Soll* und 10101 *Rücklauf-Ist*. An der Referenzanlage gemessen ist es umgekehrt, und die Entitäten folgen der Messung (`return` = 10100 folgt dem Wasser, `return_target` = 10101 ist der Sollwert). python-luxtronik sieht es genauso. Quellen: PL, M, WEB ([Heizkurve](#quellen), [Wärmepumpe](#quellen)).

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| Temperatur: Rücklauf | `return`<br>sensor · input 10100 · Gerät Wärmepumpe | °C | - | Aktuelle Rücklauftemperatur des Heizwassers. Auf diesen Wert regelt die Wärmepumpe. Folgt der Wassertemperatur (siehe den Fallstrick zu 10100 und 10101 oben). *(PL, M)* |
| Temperatur: Rücklauf-Soll | `return_target`<br>sensor · input 10101 · Gerät Wärmepumpe | °C | - | Rücklauf-Sollwert, den die Regelung gerade anstrebt (Ergebnis der Heizkurve oder der Heizungs-Sollwert in der Betriebsart `setpoint`). Er springt, während die Wärmepumpe heizt. Das ist das `effective_target` des Heizungs-Sollwerts. *(PL, M)* |
| Temperatur: Rücklauf extern | `return_external`<br>sensor · input 10102 · Gerät Wärmepumpe | °C | - | Wert des externen Rücklauffühlers. Ob ein solcher Fühler existiert, hängt von der Anlage ab; ohne Fühler ist der Wert bedeutungslos. Seine Verwendung durch die Regelung ist nicht dokumentiert (ungeklärt). *(PL)*<br>*Kategorie Diagnose; gelesen alle 2 Abfragen* |
| Temperatur: Rücklauf-Begrenzung | `return_limit`<br>sensor · input 10103 · Gerät Wärmepumpe | °C | - | Höchste zulässige Rücklauftemperatur laut Regelung. *(PL)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Temperatur: Rücklauf-Soll Minimum | `return_min_target`<br>sensor · input 10104 · Gerät Wärmepumpe | °C | - | Niedrigster Rücklauf-Sollwert laut Regelung. *(PL)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Temperatur: Vorlauf | `flow`<br>sensor · input 10105 · Gerät Wärmepumpe | °C | - | Aktuelle Vorlauftemperatur, also die Temperatur des Wassers, das die Wärmepumpe Richtung Heizungsanlage verlässt. *(PL)* |
| Temperatur: Raum (Raumeinheit) | `room`<br>sensor · input 10106 · Gerät Heizung | °C | - | Raumtemperatur, gemessen von der Raumeinheit (RBE+). Nur mit einer solchen Einheit vorhanden; die Entität braucht die gewählte *Raumeinheit* in der Ausstattung und ist standardmäßig deaktiviert. *(PL)*<br>*standardmäßig deaktiviert; braucht Raumeinheit in der Ausstattung; gelesen alle 2 Abfragen* |
| Grenztemperatur | `heating_limit`<br>sensor · input 10107 · Gerät Heizung | °C | - | Grenztemperatur des Heizens. **Nicht die Heizgrenze (Außentemperatur).** python-luxtronik beschreibt sie so: Fällt die Temperatur unter (Heizkurven-Sollwert minus Hysterese), wird die weiche Leistungsbegrenzung ignoriert. Ihre genaue Rolle darüber hinaus ist nicht dokumentiert (ungeklärt). *(PL)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Temperatur: Außen | `outside`<br>sensor · input 10108 · Gerät Wärmepumpe | °C | - | Gemessene Außentemperatur. Sie bestimmt die Heizkurve. *(PL, WEB)* |
| Temperatur: Außen Mittelwert | `outside_temp_average`<br>sensor · input 10109 · Gerät Wärmepumpe | °C | - | Mittlere Außentemperatur. Der Mittelungszeitraum ist nicht dokumentiert (ungeklärt). Braucht Firmware 3.92.0 oder neuer. War bis 0.8.2 `raw_10109`; die Entity-ID blieb. *(PL)*<br>*gelesen alle 4 Abfragen* |
| Temperatur: Wärmequelle Eintritt | `heat_source_input`<br>sensor · input 10110 · Gerät Wärmepumpe | °C | - | Temperatur der Wärmequelle am Eintritt der Wärmepumpe. Was das bei einem Luft-Wasser-Gerät bedeutet, ist nicht dokumentiert (ungeklärt). War bis 0.8.2 `raw_10110`. *(PL)*<br>*gelesen alle 2 Abfragen* |
| Temperatur: Vorlauf Maximum | `max_flow_temp`<br>sensor · input 10112 · Gerät Wärmepumpe | °C | - | Maximale Vorlauftemperatur laut Regelung. python-luxtronik nennt keine Einheit; die Integration liest sie als °C mit einer Nachkommastelle. Standardmäßig deaktiviert. War bis 0.8.2 `raw_10112`. *(PL, INT)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 4 Abfragen* |
| Temperatur: Wärmequelle Austritt | `heat_source_out`<br>sensor · input 10111 · Gerät Wärmepumpe | °C | - | Temperatur der Wärmequelle am Austritt der Wärmepumpe. Derselbe Vorbehalt wie beim Eintritt. Fehlt bei Einträgen, die vor 0.3.0 angelegt wurden, bis die Ausstattung einmal gespeichert wird. *(PL)*<br>*gelesen alle 2 Abfragen* |

## 2. Warmwassertemperaturen

**Hintergrund.** Warmwasser steckt in einem Speicher und wird auf einen Sollwert aufgeheizt. Wie jede Zweipunktregelung arbeitet das mit einer *Hysterese* (*Schaltdifferenz*): Die Wärmepumpe startet erst wieder, wenn die Temperatur einige Kelvin unter den Sollwert gefallen ist, sonst würde sie ständig ein- und ausschalten. Diesen Wert gibt die SHI nicht heraus. **Legionellen:** Das Umweltbundesamt empfiehlt, das Warmwasser durchgängig über 55 °C zu halten; für Großanlagen verlangt DVGW W 551 mindestens 60 °C am Austritt des Erwärmers. Eine Wärmepumpe mit niedrigerem Warmwasser-Sollwert ist auf regelmäßiges Aufheizen darüber angewiesen (eine *Legionellenschaltung*), die das UBA allein nicht als sichere Variante ansieht. Diese Integration hat für eine solche Funktion keine Entität; die Registerkarte enthält keine. Quellen: WEB ([UBA-Factsheet](#quellen), [Zweipunktregler](#quellen)).

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| Temperatur | `dhw`<br>sensor · input 10120 · Gerät Warmwasser | °C | - | Aktuelle Warmwassertemperatur (Speichertemperatur laut Warmwasserfühler der Regelung). *(PL)* |
| Soll | `dhw_target`<br>sensor · input 10121 · Gerät Warmwasser | °C | - | Warmwasser-Zieltemperatur, die die Regelung gerade anstrebt. Das ist das `effective_target` des Warmwasser-Sollwerts. Die Zahl Sollwert ändert sie nur in der Betriebsart `setpoint`. *(PL)*<br>*gelesen alle 2 Abfragen* |
| Minimum | `dhw_min`<br>sensor · input 10122 · Gerät Warmwasser | °C | - | Niedrigste einstellbare Warmwassertemperatur. In der Referenz-Firmware liefert das Register eine Konstante, 30,0 °C; das ist auch die Untergrenze der Zahl Sollwert. *(PL, FW)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Maximum | `dhw_max`<br>sensor · input 10123 · Gerät Warmwasser | °C | - | Höchste einstellbare Warmwassertemperatur laut Regelung. *(PL)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Grenztemperatur | `dhw_limit`<br>sensor · input 10124 · Gerät Warmwasser | °C | - | Grenztemperatur des Warmwassers. python-luxtronik beschreibt sie so: Fällt die Temperatur unter den gewünschten Regelwert, wird die weiche Leistungsbegrenzung ignoriert. Ihre genaue Rolle darüber hinaus ist nicht dokumentiert (ungeklärt). *(PL)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |

## 3. Temperaturen der Mischkreise

**Hintergrund.** Ein *Mischkreis* hat eine eigene Vorlauftemperatur, die ein Mischventil erzeugt, indem es heißes Vorlaufwasser mit kühlerem Rücklaufwasser mischt. Typisch: ein Fußbodenheizkreis, der weniger braucht als der Heizkörperkreis. Die SHI liefert nur Temperaturen, Betriebsarten und Sollwerte der Kreise, keine Ventilstellung. Die Kreise gibt es nur, wenn sie in der [Ausstattung](../README.de.md#ausstattung-der-anlage) gewählt sind; Kreis 2 und 3 sind standardmäßig deaktiviert. Quellen: PL, INT.

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| Mischkreis 1: Vorlauf | `mk1_flow`<br>sensor · input 10140 · Gerät Heizung | °C | - | Aktuelle Vorlauftemperatur von Mischkreis 1. *(PL)*<br>*braucht Mischkreis 1 in der Ausstattung* |
| Mischkreis 1: Vorlauf-Soll | `mk1_flow_target`<br>sensor · input 10141 · Gerät Heizung | °C | - | Vorlauf-Sollwert von Mischkreis 1 (das `effective_target` seines Sollwerts). *(PL)*<br>*braucht Mischkreis 1 in der Ausstattung* |
| Mischkreis 1: Vorlauf Minimum | `mk1_flow_min`<br>sensor · input 10142 · Gerät Heizung | °C | - | Niedrigste Vorlauftemperatur von Mischkreis 1. *(PL)*<br>*Kategorie Diagnose; braucht Mischkreis 1 in der Ausstattung; gelesen alle 10 Abfragen* |
| Mischkreis 1: Vorlauf Maximum | `mk1_flow_max`<br>sensor · input 10143 · Gerät Heizung | °C | - | Höchste Vorlauftemperatur von Mischkreis 1. *(PL)*<br>*Kategorie Diagnose; braucht Mischkreis 1 in der Ausstattung; gelesen alle 10 Abfragen* |
| Mischkreis 2: Vorlauf | `mk2_flow`<br>sensor · input 10150 · Gerät Heizung | °C | - | Aktuelle Vorlauftemperatur von Mischkreis 2. *(PL)*<br>*standardmäßig deaktiviert; braucht Mischkreis 2 in der Ausstattung* |
| Mischkreis 2: Vorlauf-Soll | `mk2_flow_target`<br>sensor · input 10151 · Gerät Heizung | °C | - | Vorlauf-Sollwert von Mischkreis 2 (das `effective_target` seines Sollwerts). *(PL)*<br>*standardmäßig deaktiviert; braucht Mischkreis 2 in der Ausstattung* |
| Mischkreis 2: Vorlauf Minimum | `mk2_flow_min`<br>sensor · input 10152 · Gerät Heizung | °C | - | Niedrigste Vorlauftemperatur von Mischkreis 2. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; braucht Mischkreis 2 in der Ausstattung; gelesen alle 10 Abfragen* |
| Mischkreis 2: Vorlauf Maximum | `mk2_flow_max`<br>sensor · input 10153 · Gerät Heizung | °C | - | Höchste Vorlauftemperatur von Mischkreis 2. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; braucht Mischkreis 2 in der Ausstattung; gelesen alle 10 Abfragen* |
| Mischkreis 3: Vorlauf | `mk3_flow`<br>sensor · input 10160 · Gerät Heizung | °C | - | Aktuelle Vorlauftemperatur von Mischkreis 3. *(PL)*<br>*standardmäßig deaktiviert; braucht Mischkreis 3 in der Ausstattung* |
| Mischkreis 3: Vorlauf-Soll | `mk3_flow_target`<br>sensor · input 10161 · Gerät Heizung | °C | - | Vorlauf-Sollwert von Mischkreis 3 (das `effective_target` seines Sollwerts). *(PL)*<br>*standardmäßig deaktiviert; braucht Mischkreis 3 in der Ausstattung* |
| Mischkreis 3: Vorlauf Minimum | `mk3_flow_min`<br>sensor · input 10162 · Gerät Heizung | °C | - | Niedrigste Vorlauftemperatur von Mischkreis 3. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; braucht Mischkreis 3 in der Ausstattung; gelesen alle 10 Abfragen* |
| Mischkreis 3: Vorlauf Maximum | `mk3_flow_max`<br>sensor · input 10163 · Gerät Heizung | °C | - | Höchste Vorlauftemperatur von Mischkreis 3. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; braucht Mischkreis 3 in der Ausstattung; gelesen alle 10 Abfragen* |

## 4. Leistung und berechnete Leistungszahl

**Hintergrund.** Die *Leistungszahl* (COP) ist die abgegebene Wärmeleistung geteilt durch die im selben Moment aufgenommene elektrische Leistung. Sie liegt immer über 1, weil die Wärme auch die der Umwelt entzogene enthält, und hängt vom Betriebspunkt ab: Ein kleiner Unterschied zwischen Wärmequelle und Heizwasser ergibt eine hohe, ein großer eine niedrige Leistungszahl. Eine COP von 4,2 heißt: 1 kW Strom liefern 4,2 kW Wärme. Die Momentan-COP dieser Integration wird aus zwei ohnehin gelesenen Sensoren berechnet und verursacht keinen zusätzlichen Modbus-Verkehr. Beide Leistungsregister haben eine **Auflösung von 100 W**, daher ist ein Quotient bei kleiner Leistung überwiegend Rundungsrauschen; deshalb zeigt die COP in den beim Sensor genannten Fällen *unbekannt statt einer Zahl. Beim **Abtauen** entzieht die Wärmepumpe der Heizungsanlage Wärme, und die thermische Leistung wird negativ. Quellen: WEB ([Leistungszahl](#quellen)), INT, PL.

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| Leistung: thermisch | `compressor_thermal_power`<br>sensor · input 10300 · Gerät Wärmepumpe | W | - | Aktuelle thermische (Heiz-)Leistung der Wärmepumpe. Mit Vorzeichen: **negativ beim Abtauen**. Auflösung 100 W. Einer der Schlüssel, auf die der Heat Pump Optimizer angewiesen ist. *(PL, INT)* |
| Leistung: elektrisch | `electric_power`<br>sensor · input 10301 · Gerät Wärmepumpe | W | - | Aktuelle elektrische Leistungsaufnahme. Auflösung 100 W. Ob Umwälzpumpen und Zusatzheizung enthalten sind, ist nicht dokumentiert (ungeklärt). *(PL)* |
| Leistung: elektrisch Minimum | `electric_power_min`<br>sensor · input 10302 · Gerät Wärmepumpe | W | - | Minimale vorhergesagte elektrische Leistungsaufnahme. Wie die Regelung sie vorhersagt und für welchen Zustand, ist nicht dokumentiert (ungeklärt). *(PL)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| COP | `cop`<br>sensor · berechnet, kein Register · Gerät Wärmepumpe | - | 0 … 12 | Momentan-COP: `compressor_thermal_power` geteilt durch `electric_power`. Wird als *unbekannt* gezeigt, wenn ein Wert fehlt, die elektrische Leistung unter dem Minimum liegt, die thermische Leistung null oder negativ ist (zum Beispiel beim Abtauen) oder das Ergebnis unplausibel hoch ist. Die Grenzen sind eine Festlegung der Integration, kein Registerfakt. *(INT)* |

## 5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl

**Hintergrund.** Die Zähler laufen nur aufwärts (Statistikklasse *total increasing* in Home Assistant) und sind für das Energie-Dashboard gedacht. Wärme geteilt durch Strom über ein ganzes Jahr ist die *Jahresarbeitszahl* (JAZ). **Die Gesamt-COP-Sensoren dieser Integration sind keine JAZ:** Sie teilen die Lebensdauerzähler der Regelung und mitteln deshalb über das ganze Leben der Zähler, nicht über ein Jahr. Für eine JAZ nimmst du die Änderung beider Zähler über ein Jahr aus den Home-Assistant-Statistiken. Beachte auch die Systemgrenze: Die übliche JAZ-Definition lässt Hilfsverbraucher wie Umwälzpumpen und elektrische Abtauheizungen außen vor. Ob die Stromzähler der Regelung die Zusatzheizung enthalten und ob *gesamt* der Summe der Teile entspricht, ist nicht dokumentiert (ungeklärt). Quellen: WEB ([Arbeitszahl](#quellen), [Leistungszahl](#quellen)), PL, INT.

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| Energie: Strom gesamt | `energy_el_total`<br>sensor · input 10310 · Gerät Wärmepumpe | kWh | - | Insgesamt verbrauchte elektrische Energie (alle Betriebsarten). Zähler in Schritten von 0,1 kWh über zwei Register (32 Bit). *(PL)*<br>*gelesen alle 2 Abfragen* |
| Energie: Strom | `energy_el_heating`<br>sensor · input 10312 · Gerät Heizung | kWh | - | Für das Heizen verbrauchte elektrische Energie. Einer der Schlüssel, auf die der Heat Pump Optimizer angewiesen ist. Zähler in Schritten von 0,1 kWh über zwei Register (32 Bit). *(PL)*<br>*gelesen alle 2 Abfragen* |
| Energie: Strom | `energy_el_dhw`<br>sensor · input 10314 · Gerät Warmwasser | kWh | - | Für das Warmwasser verbrauchte elektrische Energie. Zähler in Schritten von 0,1 kWh über zwei Register (32 Bit). *(PL)*<br>*gelesen alle 2 Abfragen* |
| Energie: Wärme gesamt | `energy_th_total`<br>sensor · input 10320 · Gerät Wärmepumpe | kWh | - | Insgesamt erzeugte Wärmeenergie (alle Betriebsarten). Braucht Firmware 3.92.0 oder neuer. Zähler in Schritten von 0,1 kWh über zwei Register (32 Bit). *(PL)*<br>*gelesen alle 2 Abfragen* |
| Energie: Wärme | `energy_th_heating`<br>sensor · input 10322 · Gerät Heizung | kWh | - | Für das Heizen erzeugte Wärmeenergie. Zähler in Schritten von 0,1 kWh über zwei Register (32 Bit). *(PL)*<br>*gelesen alle 2 Abfragen* |
| Energie: Wärme | `energy_th_dhw`<br>sensor · input 10324 · Gerät Warmwasser | kWh | - | Für das Warmwasser erzeugte Wärmeenergie. Zähler in Schritten von 0,1 kWh über zwei Register (32 Bit). *(PL)*<br>*gelesen alle 2 Abfragen* |
| Betriebsstunden: Verdichter | `hours_hp`<br>sensor · input 10404 · Gerät Wärmepumpe | h | - | Betriebsstunden des Verdichters. Dass 10404 ein Stundenzähler ist, ist Beobachtung; python-luxtronik führt es als unbekannt. *(OBS)*<br>*gelesen alle 10 Abfragen* |
| Betriebsstunden | `hours_heating`<br>sensor · input 10406 · Gerät Heizung | h | - | Betriebsstunden des Heizens. Die Deutung als Stundenzähler ist nur Beobachtung. *(OBS)*<br>*gelesen alle 10 Abfragen* |
| Betriebsstunden | `hours_dhw`<br>sensor · input 10408 · Gerät Warmwasser | h | - | Betriebsstunden des Warmwassers. Die Deutung als Stundenzähler ist nur Beobachtung. *(OBS)*<br>*gelesen alle 10 Abfragen* |
| Energie: Strom | `energy_el_cooling`<br>sensor · input 10316 · Gerät Kühlung | kWh | - | Für das Kühlen verbrauchte elektrische Energie. Braucht *Kühlung* in der Ausstattung. Zähler in Schritten von 0,1 kWh über zwei Register (32 Bit). *(PL)*<br>*braucht Kühlung in der Ausstattung; gelesen alle 2 Abfragen* |
| Energie: Strom | `energy_el_pool`<br>sensor · input 10318 · Gerät Pool | kWh | - | Für die Pool-Heizung verbrauchte elektrische Energie. Braucht *Pool* in der Ausstattung. Zähler in Schritten von 0,1 kWh über zwei Register (32 Bit). *(PL)*<br>*braucht Pool in der Ausstattung; gelesen alle 2 Abfragen* |
| Energie: Wärme | `energy_th_cooling`<br>sensor · input 10326 · Gerät Kühlung | kWh | - | Für das Kühlen erzeugte Energie. Braucht *Kühlung* in der Ausstattung. Zähler in Schritten von 0,1 kWh über zwei Register (32 Bit). *(PL)*<br>*braucht Kühlung in der Ausstattung; gelesen alle 2 Abfragen* |
| Energie: Wärme | `energy_th_pool`<br>sensor · input 10328 · Gerät Pool | kWh | - | Für die Pool-Heizung erzeugte Wärmeenergie. Braucht *Pool* in der Ausstattung. Zähler in Schritten von 0,1 kWh über zwei Register (32 Bit). *(PL)*<br>*braucht Pool in der Ausstattung; gelesen alle 2 Abfragen* |
| COP gesamt | `cop_heating`<br>sensor · berechnet, kein Register · Gerät Heizung | - | 0 … 12 | Gesamt-COP des Heizens: `energy_th_heating` geteilt durch `energy_el_heating`. Lebensdauer der Zähler, **keine** JAZ. Wird als *unbekannt* gezeigt bei zu wenig elektrischer Energie, null oder negativem Ergebnis, unplausiblem Ergebnis oder wenn ein Zähler seit der letzten Messung rückwärts lief (Reset). *(INT)* |
| COP gesamt | `cop_dhw`<br>sensor · berechnet, kein Register · Gerät Warmwasser | - | 0 … 12 | Gesamt-COP des Warmwassers: `energy_th_dhw` geteilt durch `energy_el_dhw`. Dieselben Regeln wie beim Heizen. *(INT)* |

## 6. Status und Betriebszustand

**Hintergrund.** *VD1* und *VD2* sind die Bezeichnungen der Regelung für die Verdichter. *ZWE1* bis *ZWE3* sind zusätzliche Wärmeerzeuger, zum Beispiel ein Elektro-Heizstab; direktes Heizen mit Strom hat eine COP von 1, ein laufender Zusatzheizer kostet also Effizienz. Bei Luft-Wasser-Wärmepumpen vereist der Verdampfer bei kalter, feuchter Witterung. Die Wärmepumpe **taut** dann **ab**, indem sie den Kältekreis kurz umkehrt; die Wärme dafür kommt aus der Heizungsanlage, deshalb ist die thermische Leistung negativ und die *Betriebsart* zeigt *Abtauen*. Eine **EVU-Sperre** ist eine Sperre des Netzbetreibers für Wärmepumpen mit Sondertarif; der Versorger darf bis zu dreimal täglich für jeweils bis zu zwei Stunden abschalten. Heizen, Warmwasser, Kühlen und Pool kommen nacheinander dran: Die *Betriebsart* ist ein einzelner Wert und nennt nur, was die Wärmepumpe gerade tut. Quellen: WEB ([Wärmepumpe](#quellen), [EVU-Sperre](#quellen)), PL.

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| Status: Fehlernummer | `error_number`<br>sensor · input 10201 · Gerät Wärmepumpe | - | 0 = kein Fehler, sonst der Fehlercode | Aktueller Fehlercode der Regelung. 0 heißt kein Fehler. Die Bedeutung jedes Codes steht in python-luxtronik (`Errorcode` in `datatypes.py`, zum Beispiel 701 Niederdruck, 703 Frostschutz, 705 Motorschutz). *(PL)* |
| Status: Wärmeerzeuger (Bitmaske) | `heat_generator_state`<br>sensor · input 10000 · Gerät Wärmepumpe | - | - | Bitmaske der laufenden Wärmeerzeuger: 1 = VD1, 2 = VD2, 4 = ZWE1, 8 = ZWE2, 16 = ZWE3. 0 = alle aus. Die Binärsensoren darunter zeigen die einzelnen Bits; dieser Sensor ist die Summe. *(PL)* |
| Status: Betriebsart | `operating_mode`<br>sensor · input 10002 · Gerät Wärmepumpe | - | 0 = `heating`: Heizen<br>1 = `hot_water`: Warmwasser<br>2 = `pool`: Schwimmbad / Solar<br>3 = `evu_lock`: EVU-Sperre<br>4 = `defrost`: Abtauen<br>5 = `off`: Keine Anforderung<br>6 = `external_source`: Heizen (externe Quelle)<br>7 = `cooling`: Kühlen | Was die Wärmepumpe gerade tut. Ein einzelner Wert: Bei mehreren Anforderungen nennt er die, die bedient wird. *Keine Anforderung* heißt, die Wärmepumpe ruht. *EVU-Sperre* ist die Sperre des Netzbetreibers. *(PL, FW)* |
| Status | `heating_status`<br>sensor · input 10003 · Gerät Heizung | - | 0 = deaktiviert, 1 = keine Anforderung, 2 = angefordert, 3 = laufend | Zustand des Heizens als Anforderung: deaktiviert, keine Anforderung, angefordert aber noch nicht laufend, laufend. *(PL)* |
| Status | `hot_water_status`<br>sensor · input 10004 · Gerät Warmwasser | - | 0 = deaktiviert, 1 = keine Anforderung, 2 = angefordert, 3 = laufend | Zustand des Warmwassers als Anforderung: deaktiviert, keine Anforderung, angefordert aber noch nicht laufend, laufend. *(PL)* |
| Status | `cooling_status`<br>sensor · input 10006 · Gerät Kühlung | - | 0 = deaktiviert, 1 = keine Anforderung, 2 = angefordert, 3 = laufend | Zustand des Kühlens als Anforderung: deaktiviert, keine Anforderung, angefordert aber noch nicht laufend, laufend. Braucht *Kühlung* in der Ausstattung. *(PL)*<br>*Kategorie Diagnose; braucht Kühlung in der Ausstattung; gelesen alle 2 Abfragen* |
| Status | `pool_status`<br>sensor · input 10007 · Gerät Pool | - | 0 = deaktiviert, 1 = keine Anforderung, 2 = angefordert, 3 = laufend | Zustand der Pool-Heizung als Anforderung: deaktiviert, keine Anforderung, angefordert aber noch nicht laufend, laufend. Braucht *Pool* in der Ausstattung. *(PL)*<br>*Kategorie Diagnose; braucht Pool in der Ausstattung; gelesen alle 2 Abfragen* |
| Status: Verdichter 1 läuft | `compressor_1`<br>binary_sensor · heat_generator_state, bit 0 · Gerät Wärmepumpe | - | an / aus | Verdichter 1 (VD1) läuft. Bit 0 der Wärmeerzeuger-Maske. *(PL)* |
| Status: Verdichter 2 läuft | `compressor_2`<br>binary_sensor · heat_generator_state, bit 1 · Gerät Wärmepumpe | - | an / aus | Verdichter 2 (VD2) läuft. Bit 1. Nur mit einem zweiten Verdichter sinnvoll. Dasselbe Bit wie `heatpump_vd2_status`. *(PL)* |
| Status: Zusatzheizung 1 (ZWE) aktiv | `aux_heater_1`<br>binary_sensor · heat_generator_state, bit 2 · Gerät Wärmepumpe | - | an / aus | Zusätzlicher Wärmeerzeuger 1 (ZWE1) ist aktiv. Bit 2. Einer der Schlüssel, auf die der Heat Pump Optimizer angewiesen ist. *(PL)* |
| Status: Zusatzheizung 2 (ZWE) aktiv | `aux_heater_2`<br>binary_sensor · heat_generator_state, bit 3 · Gerät Wärmepumpe | - | an / aus | Zusätzlicher Wärmeerzeuger 2 (ZWE2) ist aktiv. Bit 3. Dasselbe Bit wie `heatpump_zwe2_status`. *(PL)* |
| Status: VD2 läuft | `heatpump_vd2_status`<br>binary_sensor · heat_generator_state, bit 1 · Gerät Wärmepumpe | - | an / aus | Verdichter 2 (VD2) läuft, mit dem Namen aus python-luxtronik. Bit 1, dasselbe wie `compressor_2`. *(PL)*<br>*standardmäßig deaktiviert* |
| Status: ZWE2 aktiv | `heatpump_zwe2_status`<br>binary_sensor · heat_generator_state, bit 3 · Gerät Wärmepumpe | - | an / aus | ZWE2 ist aktiv, mit dem Namen aus python-luxtronik. Bit 3, dasselbe wie `aux_heater_2`. *(PL)*<br>*standardmäßig deaktiviert* |
| Status: ZWE3 aktiv | `heatpump_zwe3_status`<br>binary_sensor · heat_generator_state, bit 4 · Gerät Wärmepumpe | - | an / aus | ZWE3 ist aktiv. Bit 4. Braucht Firmware 3.90.1 oder neuer. *(PL)*<br>*standardmäßig deaktiviert* |
| Status: Verbindung | `online`<br>binary_sensor · - · Gerät Wärmepumpe | - | an / aus | An, solange die letzte Abfrage der Wärmepumpe erfolgreich war. Anders als die anderen Entitäten wird sie nie nicht verfügbar: Der Zustand selbst sagt, ob die SHI antwortet. Nach 10 Minuten fehlgeschlagener Abfragen entsteht ein Reparaturhinweis. *(INT)*<br>*Kategorie Diagnose* |

## 7. Sperren (Schalter)

**Hintergrund.** Eine *Sperre* stoppt eine Funktion der Wärmepumpe, während der Rest weiterläuft. Sperren sind das Werkzeug eines Optimierers wie des Heat Pump Optimizer: Er sperrt Heizen oder Warmwasser, solange Strom teuer ist, und gibt sie wieder frei. Sie sind **flüchtig**: Nach einem Neustart der Regelung oder wenn der SHI-Watchdog abläuft (10 Minuten ohne Modbus-Zugriff), lesen sie *aus* (nicht gesperrt), also den sicheren Zustand. Die Wiederherstellungs-Option dieser Integration stellt Sperren bewusst **nicht** wieder her. Häufiges Schalten der Kühl- oder Pool-Sperre kann Wärmepumpe und Hydraulik belasten (PL). Quellen: PL, FW, INT.

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| Sperren | `heating_block`<br>switch · holding 10050 · Gerät Heizung | - | 0 = aus, 1 = an | Sperrt das Heizen. **Nur das Heizen:** Das Warmwasser läuft weiter. Aus (0) = Normalbetrieb. Wird nach jedem Schreiben zurückgelesen. Einer der Schlüssel, auf die der Heat Pump Optimizer angewiesen ist. Wird nach einem Reset nicht wiederhergestellt. *(PL, INT)* |
| Sperren | `dhw_block`<br>switch · holding 10051 · Gerät Warmwasser | - | 0 = aus, 1 = an | Sperrt die Warmwasserbereitung. Solange sie an ist, lässt sich die Warmwasser-Betriebsart nicht setzen (Messung des Eigentümers), und die Wiederherstellung der Warmwasser-Gruppe wartet. Einer der Schlüssel, auf die der Heat Pump Optimizer angewiesen ist. *(PL, M)* |
| Sperren | `cooling_block`<br>switch · holding 10052 · Gerät Kühlung | - | 0 = aus, 1 = an | Sperrt passives und aktives Kühlen. Braucht *Kühlung* in der Ausstattung. Häufiges Schalten kann Wärmepumpe und Hydraulik belasten. *(PL)*<br>*braucht Kühlung in der Ausstattung* |
| Sperren | `pool_block`<br>switch · holding 10053 · Gerät Pool | - | 0 = aus, 1 = an | Sperrt die Pool-Heizung. Braucht *Pool* in der Ausstattung. Häufiges Schalten kann Wärmepumpe und Hydraulik belasten. *(PL)*<br>*braucht Pool in der Ausstattung* |

## 8. Heizkreis-Steuerung

**Hintergrund: die vier Betriebsarten.** Die SHI ersetzt die Regelung nicht, sie legt eine Korrektur darüber. Jeder Kreis hat eine *Betriebsart* (roh 0 bis 3), die entscheidet, welcher der drei zugehörigen Werte zählt:

| Roh | Schlüssel | Wirkung |
|---|---|---|
| 0 | `off` | **Keine Vorgabe**: Die Regelung nutzt ihre eigenen Werte. Das schaltet den Kreis **nicht** ab, es wird weiter geheizt. |
| 1 | `setpoint` | Die Zahl *Sollwert* ersetzt den Sollwert der Regelung. |
| 2 | `offset` | Der Sollwert der Regelung plus die *Anhebung* in Kelvin. |
| 3 | `level` | Der Sollwert der Regelung, um die *Stufe* korrigiert. |

**Der Heizungs-Sollwert ist ein Rücklauf-Sollwert (tRL)**, kein Vorlauf-Sollwert (PL, M). Er gilt **nur in der Betriebsart `setpoint`**; in jeder anderen ignoriert ihn die Regelung. Die Zahlen nehmen einen Schreibzugriff trotzdem in jeder Betriebsart an, weil Optimierer die Zahl schreiben und die Betriebsart selbst setzen; die *Climate*-Entität lehnt einen Zielwert in anderer Betriebsart ab und nennt stattdessen die Auswahl der Betriebsart. Die Attribute `setpoint_active` und `effective_target` zeigen, ob der Sollwert zählt und was die Regelung tatsächlich anstrebt. Die Heizkurve selbst (Steilheit, Niveau) ist über die SHI nicht erreichbar; die *Anhebung* ist der Weg der SHI, das Ergebnis zu verschieben. Die Wertebereiche stammen aus python-luxtronik; die Regelung wendet zusätzlich ihre eigenen Grenzen an. **Fallstrick:** Nach einem Neustart der Regelung oder einem Watchdog-Ablauf lesen Betriebsarten und Stufen 0, Sollwerte fallen auf einen gespeicherten oder Standardwert zurück (nicht 0). Die Option *Werte nach einem Geräte-Reset wiederherstellen* schreibt die selbst gesetzten Werte zurück (siehe [Fallstricke](#fallstricke-und-wissenswertes)). Lass einen Optimierer und die Climate-Entität nicht gleichzeitig denselben Kreis schreiben. Quellen: PL, FW, M, INT.

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| (trägt den Gerätenamen) | `climate_heating`<br>climate · Sicht auf mehrere Register · Gerät Heizung | - | `auto`: Wärmepumpe regelt selbst<br>`heat`: Vorgabe durch Home Assistant | Thermostat-Sicht auf den Heizkreis. HVAC-Modus `auto` = Betriebsart 0 (die Wärmepumpe regelt selbst, es wird weiter geheizt); `heat` = Sollwert, Anhebung oder Stufe. **Es gibt kein `off`:** Zum Stoppen des Heizens dient die Heizungs-Sperre. Der Zielwert ist der Heizungs-Sollwert, die aktuelle Temperatur ist die **Rücklauf**temperatur. Attribute: Betriebsart, `setpoint_active`, `effective_target`, Heizen gesperrt. Lehnt einen Zielwert außerhalb der Betriebsart `setpoint` ab. `hvac_action`: heating, idle, oder off bei Sperre. *(INT, PL, M)* |
| Betriebsart | `cfg_heating_mode`<br>select · holding 10000 · Gerät Heizung | - | 0 = `off`: Keine Vorgabe<br>1 = `setpoint`: Sollwert (ersetzt den Sollwert der Regelung)<br>2 = `offset`: Anhebung (Sollwert der Regelung plus Anhebung)<br>3 = `level`: Stufe (Sollwert der Regelung, um die Stufe korrigiert) | Betriebsart des Heizkreises (siehe Tabelle oben). 0 schaltet das Heizen nicht aus. *(PL)*<br>*Kategorie Konfiguration; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Sollwert | `cfg_heating_setpoint`<br>number · holding 10001 · Gerät Heizung | °C | 15 … 75 °C<br>Schritt 0,5 | Heizungs-Sollwert, eine **Rücklauftemperatur** (tRL), die den Sollwert der Regelung ersetzt. Nur in der Betriebsart `setpoint`. Gemessen: `return_target` folgte dem geschriebenen Wert. Die Regelung kann ihn begrenzen. Nach einem Reset liest er einen gespeicherten oder Standardwert, nicht 0. Einer der Schlüssel, auf die der Heat Pump Optimizer angewiesen ist. *(PL, M, FW)*<br>*Kategorie Konfiguration; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Heizkurven-Anhebung | `cfg_heating_offset`<br>number · holding 10002 · Gerät Heizung | K | -20 … 20 K<br>Schritt 0,5 | Anhebung in Kelvin auf den aktuellen Rücklauf-Sollwert der Regelung, wirkt also wie eine Parallelverschiebung der Heizkurve. Nur in der Betriebsart `offset`. Negative Werte sind erlaubt. *(PL, INT)*<br>*wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Stufe | `cfg_heating_level`<br>select · holding 10003 · Gerät Heizung | - | 0 = `normal`: Normal (keine Korrektur)<br>1 = `increased`: Erhöht<br>2 = `increased2`: Erhöht (Stufe 2)<br>3 = `decreased`: Abgesenkt | Stufenkorrektur des Heiz-Sollwerts. 0 = normal (keine Korrektur). Was *erhöht*, *erhöht 2* und *abgesenkt* ändern und um wie viel, ist **ungeklärt**: python-luxtronik führt es als nicht analysiert, und die Firmware belegt nur eine Erhöhen- und eine Absenken-Richtung. *(PL, FW)*<br>*Kategorie Konfiguration; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Raumtemperatur-Sollwert | `cfg_room_setpoint`<br>number · holding 10060 · Gerät Wärmepumpe | °C | 20 … 40 °C<br>Schritt 0,5 | Raumtemperatur-Sollwert für die Raumeinheit (RBE), das schreibbare Firmware-Register `RBE_RT_Soll`. Braucht die *Raumeinheit* in der Ausstattung. Der Bereich 20 bis 40 °C ist eine Entscheidung des Eigentümers, kein Registerfakt. Was die Regelung mit dem Wert tut, ist **nicht überprüft** (ungeklärt). *(FW, INT)*<br>*Kategorie Konfiguration; braucht Raumeinheit in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |

## 9. Warmwasser-Steuerung

**Hintergrund.** Warmwasser hat dieselben vier Betriebsarten wie der Heizkreis (siehe [Heizkreis-Steuerung](#8-heizkreis-steuerung)); der Warmwasser-Sollwert ist eine einfache Warmwassertemperatur und zählt nur in der Betriebsart `setpoint`. **Fallstricke beim Warmwasser:**

* **Verzögerte Übernahme.** Auf Firmware 3.92.3 wirken Schreibzugriffe auf Betriebsart, Sollwert, Anhebung und Stufe des Warmwassers nicht sofort; die Regelung übernimmt sie nach etwa 10 s (aus der Firmware abgeleitet, FW). Die Integration prüft deshalb einen abweichenden Rücklesewert nach 15 s erneut und schreibt in der Zwischenzeit nichts in das Register. Das Schreiben des aktuell gespeicherten Wertes bricht einen ausstehenden Schreibzugriff ab. Gemessen für die Betriebsart; der Sollwert las an der Referenzanlage sofort zurück, Firmware und Messung widersprechen sich dort (FW, M).
* **Warmwasser-Sperre.** Der Eigentümer hat gemessen, dass sich die Warmwasser-Betriebsart nur setzen lässt, solange die Warmwasser-Sperre nicht aktiv ist; der Mechanismus ist unbekannt (M). Die Wiederherstellung nach einem Reset wartet deshalb, solange die Warmwasser-Sperre an liest.
* Die `water_heater`-Entität zeigt die Betriebsart als *keine Vorgabe / Sollwert / Anhebung / Stufe* und lehnt einen Zielwert außerhalb der Betriebsart `setpoint` ab.

Quellen: PL, FW, M, INT.

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| (trägt den Gerätenamen) | `water_heater_dhw`<br>water_heater · Sicht auf mehrere Register · Gerät Warmwasser | - | `no_influence`: Keine Vorgabe<br>`setpoint`: Sollwert (ersetzt den Sollwert der Regelung)<br>`offset`: Anhebung (Sollwert der Regelung plus Anhebung)<br>`level`: Stufe (Sollwert der Regelung, um die Stufe korrigiert) | Water-Heater-Sicht auf das Warmwasser. Betriebsarten: keine Vorgabe (roh 0), Sollwert, Anhebung, Stufe; **kein `off`**. Ziel = Warmwasser-Sollwert, aktuell = Warmwassertemperatur. Attribute `setpoint_active` und `effective_target`. Lehnt einen Zielwert außerhalb der Betriebsart `setpoint` ab. Der Heat Pump Optimizer steuert das Warmwasser nicht darüber. *(INT, PL)* |
| Betriebsart | `cfg_dhw_mode`<br>select · holding 10005 · Gerät Warmwasser | - | 0 = `off`: Keine Vorgabe<br>1 = `setpoint`: Sollwert (ersetzt den Sollwert der Regelung)<br>2 = `offset`: Anhebung (Sollwert der Regelung plus Anhebung)<br>3 = `level`: Stufe (Sollwert der Regelung, um die Stufe korrigiert) | Betriebsart des Warmwassers. 0 schaltet das Warmwasser nicht aus. Wirkt mit etwa 10 s Verzögerung; lässt sich nur setzen, solange die Warmwasser-Sperre aus ist (siehe oben). *(PL, FW, M)*<br>*Kategorie Konfiguration; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option); verzögerte Übernahme (etwa 10 s)* |
| Sollwert | `cfg_dhw_setpoint`<br>number · holding 10006 · Gerät Warmwasser | °C | 30 … 75 °C<br>Schritt 0,5 | Warmwasser-Sollwert in °C. Nur in der Betriebsart `setpoint`. Verzögerte Übernahme wie der Rest der Gruppe. Beachte den Legionellen-Hinweis bei den Warmwassertemperaturen. *(PL, FW, WEB)*<br>*Kategorie Konfiguration; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option); verzögerte Übernahme (etwa 10 s)* |
| Anhebung | `cfg_dhw_offset`<br>number · holding 10007 · Gerät Warmwasser | K | -20 … 20 K<br>Schritt 0,5 | Anhebung in Kelvin auf den Warmwasser-Sollwert der Regelung. Nur in der Betriebsart `offset`. Verzögerte Übernahme. *(PL, FW)*<br>*Kategorie Konfiguration; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option); verzögerte Übernahme (etwa 10 s)* |
| Stufe | `cfg_dhw_level`<br>select · holding 10008 · Gerät Warmwasser | - | 0 = `normal`: Normal (keine Korrektur)<br>1 = `increased`: Erhöht<br>2 = `increased2`: Erhöht (Stufe 2)<br>3 = `decreased`: Abgesenkt | Stufenkorrektur des Warmwasser-Sollwerts. 0 = normal. Die Wirkung der anderen Stufen ist **ungeklärt** (siehe Heizungs-Stufe). Verzögerte Übernahme. *(PL, FW)*<br>*Kategorie Konfiguration; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option); verzögerte Übernahme (etwa 10 s)* |
| Zirkulationspumpe | `circulation`<br>switch · holding 10070 · Gerät Warmwasser | - | 0 = aus, 1 = an | Schaltet die Warmwasser-Zirkulationspumpe ein, aber nur, wenn in der Regelung kein Zeitprogramm dafür eingerichtet ist. Braucht Firmware 3.92.0 oder neuer. Einer der Schlüssel, auf die der Heat Pump Optimizer angewiesen ist. Die Heizungs-Umwälzpumpen lassen sich über die SHI nicht steuern. *(PL)* |
| Extra | `extra_dhw`<br>switch · holding 10071 · Gerät Warmwasser | - | 0 = aus, 1 = an | Startet Extra-Warmwasser: Es wird geheizt, bis die Höchsttemperatur erreicht ist. Braucht Firmware 3.92.0 oder neuer. Ob die Regelung es danach selbst zurücksetzt (Einmalschalter), ist **ungeklärt**; deshalb wird es nach einem Reset nicht wiederhergestellt und nicht als externe Änderung gezählt. *(PL, INT)* |

## 10. Mischkreis-Steuerung (Heizen)

**Hintergrund.** Die Mischkreise 1 bis 3 haben dieselben vier Betriebsarten wie der Heizkreis (siehe [Heizkreis-Steuerung](#8-heizkreis-steuerung)). Anders als beim Haupt-Heizungs-Sollwert ist ihr Sollwert eine **Vorlauftemperatur** des Kreises (PL). Die Bereiche sind enger: Sollwert 20 bis 65 °C, Anhebung -5 bis +5 K. Die Entitäten gibt es nur für Kreise, die in der Ausstattung gewählt sind. Quellen: PL, INT.

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| Mischkreis 1: Betriebsart | `cfg_mk1_mode`<br>select · holding 10010 · Gerät Heizung | - | 0 = `off`: Keine Vorgabe<br>1 = `setpoint`: Sollwert (ersetzt den Sollwert der Regelung)<br>2 = `offset`: Anhebung (Sollwert der Regelung plus Anhebung)<br>3 = `level`: Stufe (Sollwert der Regelung, um die Stufe korrigiert) | Betriebsart des Heizens von Mischkreis 1. 0 schaltet den Kreis nicht aus. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 1 in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 1: Sollwert | `cfg_mk1_setpoint`<br>number · holding 10011 · Gerät Heizung | °C | 20 … 65 °C<br>Schritt 0,5 | Vorlauf-Sollwert von Mischkreis 1. Nur in der Betriebsart `setpoint`. Die Regelung kann ihn begrenzen. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 1 in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 1: Anhebung | `cfg_mk1_offset`<br>number · holding 10012 · Gerät Heizung | K | -5 … 5 K<br>Schritt 0,5 | Anhebung in Kelvin auf die Vorlauftemperatur von Mischkreis 1. Nur in der Betriebsart `offset`. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 1 in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 1: Stufe | `cfg_mk1_level`<br>select · holding 10013 · Gerät Heizung | - | 0 = `normal`: Normal (keine Korrektur)<br>1 = `increased`: Erhöht<br>2 = `increased2`: Erhöht (Stufe 2)<br>3 = `decreased`: Abgesenkt | Stufenkorrektur von Mischkreis 1. 0 = normal; die Wirkung der anderen Stufen ist **ungeklärt**. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 1 in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 2: Betriebsart | `cfg_mk2_mode`<br>select · holding 10020 · Gerät Heizung | - | 0 = `off`: Keine Vorgabe<br>1 = `setpoint`: Sollwert (ersetzt den Sollwert der Regelung)<br>2 = `offset`: Anhebung (Sollwert der Regelung plus Anhebung)<br>3 = `level`: Stufe (Sollwert der Regelung, um die Stufe korrigiert) | Betriebsart des Heizens von Mischkreis 2. 0 schaltet den Kreis nicht aus. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 2 in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 2: Sollwert | `cfg_mk2_setpoint`<br>number · holding 10021 · Gerät Heizung | °C | 20 … 65 °C<br>Schritt 0,5 | Vorlauf-Sollwert von Mischkreis 2. Nur in der Betriebsart `setpoint`. Die Regelung kann ihn begrenzen. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 2 in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 2: Anhebung | `cfg_mk2_offset`<br>number · holding 10022 · Gerät Heizung | K | -5 … 5 K<br>Schritt 0,5 | Anhebung in Kelvin auf die Vorlauftemperatur von Mischkreis 2. Nur in der Betriebsart `offset`. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 2 in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 2: Stufe | `cfg_mk2_level`<br>select · holding 10023 · Gerät Heizung | - | 0 = `normal`: Normal (keine Korrektur)<br>1 = `increased`: Erhöht<br>2 = `increased2`: Erhöht (Stufe 2)<br>3 = `decreased`: Abgesenkt | Stufenkorrektur von Mischkreis 2. 0 = normal; die Wirkung der anderen Stufen ist **ungeklärt**. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 2 in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 3: Betriebsart | `cfg_mk3_mode`<br>select · holding 10030 · Gerät Heizung | - | 0 = `off`: Keine Vorgabe<br>1 = `setpoint`: Sollwert (ersetzt den Sollwert der Regelung)<br>2 = `offset`: Anhebung (Sollwert der Regelung plus Anhebung)<br>3 = `level`: Stufe (Sollwert der Regelung, um die Stufe korrigiert) | Betriebsart des Heizens von Mischkreis 3. 0 schaltet den Kreis nicht aus. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 3 in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 3: Sollwert | `cfg_mk3_setpoint`<br>number · holding 10031 · Gerät Heizung | °C | 20 … 65 °C<br>Schritt 0,5 | Vorlauf-Sollwert von Mischkreis 3. Nur in der Betriebsart `setpoint`. Die Regelung kann ihn begrenzen. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 3 in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 3: Anhebung | `cfg_mk3_offset`<br>number · holding 10032 · Gerät Heizung | K | -5 … 5 K<br>Schritt 0,5 | Anhebung in Kelvin auf die Vorlauftemperatur von Mischkreis 3. Nur in der Betriebsart `offset`. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 3 in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 3: Stufe | `cfg_mk3_level`<br>select · holding 10033 · Gerät Heizung | - | 0 = `normal`: Normal (keine Korrektur)<br>1 = `increased`: Erhöht<br>2 = `increased2`: Erhöht (Stufe 2)<br>3 = `decreased`: Abgesenkt | Stufenkorrektur von Mischkreis 3. 0 = normal; die Wirkung der anderen Stufen ist **ungeklärt**. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 3 in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |

## 11. Kühlen und Pool

**Hintergrund.** Kühlen und Pool-Heizen gibt es nur, wenn die Anlage sie hat (in der Ausstattung gewählt; die *Ausstattungs*-Flags der Regelung füllen die Antwort vor). Beim Kühlen gibt es keine *Stufe*: Die Regelung bietet Betriebsart, Sollwert und Anhebung je Mischkreis. Der Kühl-Sollwert ist eine Vorlauftemperatur des Kreises. Eine *Kühlfreigabe* ist eine Bedingung der Regelung; sie zählt nur, wenn Kühlen konfiguriert ist (PL). Quellen: PL, INT.

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| Kühlen: konfiguriert | `cooling_configured`<br>binary_sensor · input 10205 · Gerät Wärmepumpe | - | an / aus | Kühlen ist in der Regelung konfiguriert. *(PL)*<br>*Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Pool: konfiguriert | `pool_configured`<br>binary_sensor · input 10206 · Gerät Wärmepumpe | - | an / aus | Pool-Heizen ist in der Regelung konfiguriert. *(PL)*<br>*Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Kühlen: freigegeben | `cooling_release`<br>binary_sensor · input 10207 · Gerät Wärmepumpe | - | an / aus | Die Kühlfreigabe-Bedingung der Regelung ist erfüllt. Nur gültig, wenn Kühlen konfiguriert ist. *(PL)*<br>*Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Mischkreis 1: Betriebsart | `cfg_mk1_cool_mode`<br>select · holding 10015 · Gerät Kühlung | - | 0 = `off`: Keine Vorgabe<br>1 = `setpoint`: Sollwert (ersetzt den Sollwert der Regelung)<br>2 = `offset`: Anhebung (Sollwert der Regelung plus Anhebung)<br>3 = `level`: Stufe (Sollwert der Regelung, um die Stufe korrigiert) | Betriebsart des Kühlens von Mischkreis 1. 0 schaltet das Kühlen nicht aus. Braucht den Kreis und *Kühlung* in der Ausstattung. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Konfiguration; braucht Mischkreis 1 + Kühlung in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 1: Sollwert | `cfg_mk1_cool_setpoint`<br>number · holding 10016 · Gerät Kühlung | °C | 5 … 25 °C<br>Schritt 0,5 | Kühl-Vorlauf-Sollwert von Mischkreis 1. Nur in der Betriebsart `setpoint`. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Konfiguration; braucht Mischkreis 1 + Kühlung in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 1: Anhebung | `cfg_mk1_cool_offset`<br>number · holding 10017 · Gerät Kühlung | K | -5 … 5 K<br>Schritt 0,5 | Anhebung in Kelvin auf die Kühl-Vorlauftemperatur von Mischkreis 1. Nur in der Betriebsart `offset`. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Konfiguration; braucht Mischkreis 1 + Kühlung in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 2: Betriebsart | `cfg_mk2_cool_mode`<br>select · holding 10025 · Gerät Kühlung | - | 0 = `off`: Keine Vorgabe<br>1 = `setpoint`: Sollwert (ersetzt den Sollwert der Regelung)<br>2 = `offset`: Anhebung (Sollwert der Regelung plus Anhebung)<br>3 = `level`: Stufe (Sollwert der Regelung, um die Stufe korrigiert) | Betriebsart des Kühlens von Mischkreis 2. 0 schaltet das Kühlen nicht aus. Braucht den Kreis und *Kühlung* in der Ausstattung. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 2 + Kühlung in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 2: Sollwert | `cfg_mk2_cool_setpoint`<br>number · holding 10026 · Gerät Kühlung | °C | 5 … 25 °C<br>Schritt 0,5 | Kühl-Vorlauf-Sollwert von Mischkreis 2. Nur in der Betriebsart `setpoint`. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 2 + Kühlung in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 2: Anhebung | `cfg_mk2_cool_offset`<br>number · holding 10027 · Gerät Kühlung | K | -5 … 5 K<br>Schritt 0,5 | Anhebung in Kelvin auf die Kühl-Vorlauftemperatur von Mischkreis 2. Nur in der Betriebsart `offset`. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 2 + Kühlung in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 3: Betriebsart | `cfg_mk3_cool_mode`<br>select · holding 10035 · Gerät Kühlung | - | 0 = `off`: Keine Vorgabe<br>1 = `setpoint`: Sollwert (ersetzt den Sollwert der Regelung)<br>2 = `offset`: Anhebung (Sollwert der Regelung plus Anhebung)<br>3 = `level`: Stufe (Sollwert der Regelung, um die Stufe korrigiert) | Betriebsart des Kühlens von Mischkreis 3. 0 schaltet das Kühlen nicht aus. Braucht den Kreis und *Kühlung* in der Ausstattung. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 3 + Kühlung in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 3: Sollwert | `cfg_mk3_cool_setpoint`<br>number · holding 10036 · Gerät Kühlung | °C | 5 … 25 °C<br>Schritt 0,5 | Kühl-Vorlauf-Sollwert von Mischkreis 3. Nur in der Betriebsart `setpoint`. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 3 + Kühlung in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |
| Mischkreis 3: Anhebung | `cfg_mk3_cool_offset`<br>number · holding 10037 · Gerät Kühlung | K | -5 … 5 K<br>Schritt 0,5 | Anhebung in Kelvin auf die Kühl-Vorlauftemperatur von Mischkreis 3. Nur in der Betriebsart `offset`. *(PL)*<br>*Kategorie Konfiguration; braucht Mischkreis 3 + Kühlung in der Ausstattung; gelesen alle 2 Abfragen; wird nach einem Geräte-Reset wiederhergestellt (Option)* |

## 12. Leistungsbegrenzung

**Hintergrund.** Die Leistungsbegrenzung (*LPC*, limitation of power consumption) deckelt die elektrische Leistung der Wärmepumpe. *Weich* ist eine Empfehlung, gedacht für PV-Überschuss: Die Wärmepumpe versucht, unter dem Wert zu bleiben, ignoriert ihn aber, wenn die Ist-Temperatur zu weit vom Sollwert abweicht (außerhalb ihrer Hysterese). *Hart* begrenzt den Verbrauch unabhängig von der Hysterese und kann den Komfort mindern; python-luxtronik empfiehlt das nur für §14a EnWG. Nach §14a EnWG darf der Netzbetreiber steuerbare Verbraucher wie Wärmepumpen drosseln; die Untergrenze liegt bei 4,2 kW (je Gerät). Beide Entitäten werden nach einem Reset bewusst nicht wiederhergestellt: Ein Optimierer besitzt sie. Quellen: PL, WEB ([§14a EnWG](#quellen)).

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| Leistungsbegrenzung: Modus | `cfg_power_limit_mode`<br>select · holding 10040 · Gerät Wärmepumpe | - | 0 = `none`: Keine Begrenzung<br>1 = `soft`: Weiche Begrenzung<br>2 = `hard`: Harte Begrenzung | Modus der Leistungsbegrenzung: keine Begrenzung (Normalbetrieb), weiche Begrenzung (empfohlen bei PV-Überschuss), harte Begrenzung (nur für §14a EnWG, kann den Komfort mindern). Braucht einen passenden Wert. *(PL)*<br>*Kategorie Konfiguration; gelesen alle 2 Abfragen* |
| Leistungsbegrenzung: Wert | `cfg_power_limit`<br>number · holding 10041 · Gerät Wärmepumpe | kW | 0 … 30 kW<br>Schritt 0,1 | Höchste zulässige elektrische Leistung der Wärmepumpe in kW, wirksam gemäß Modus. Wird nach einem Reset nicht wiederhergestellt. *(PL)*<br>*Kategorie Konfiguration; gelesen alle 2 Abfragen* |

## 13. Gesamt-Heizen

**Hintergrund.** Die *Gesamt*-Gruppe (10065 bis 10067) wirkt auf alle Heizfunktionen zugleich und übersteuert die Einstellungen der einzelnen Kreise (PL: „Betriebsart aller Heizfunktionen (kein Sollwert verfügbar)“). Ihre Wirkung ist **nicht belegt**: An der Referenzanlage fiel 10065 etwa 2 Sekunden nach dem Schreiben auf *keine Vorgabe* zurück (M). Die Entitäten sind deshalb standardmäßig deaktiviert und werden nach einem Reset nicht wiederhergestellt. Quellen: PL, M, INT.

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| Gesamt: Betriebsart | `cfg_overall_mode`<br>select · holding 10065 · Gerät Heizung | - | 0 = `off`: Keine Vorgabe<br>1 = `setpoint`: Sollwert (ersetzt den Sollwert der Regelung)<br>2 = `offset`: Anhebung (Sollwert der Regelung plus Anhebung)<br>3 = `level`: Stufe (Sollwert der Regelung, um die Stufe korrigiert) | Betriebsart aller Heizfunktionen zugleich (kein Sollwert verfügbar). Standardmäßig deaktiviert; Wirkung nicht belegt. *(PL, M)*<br>*standardmäßig deaktiviert; Kategorie Konfiguration; gelesen alle 2 Abfragen* |
| Gesamt: Anhebung | `cfg_overall_offset`<br>number · holding 10066 · Gerät Heizung | K | -20 … 20 K<br>Schritt 0,5 | Temperaturkorrektur in Kelvin für alle Heizfunktionen. Standardmäßig deaktiviert; Wirkung nicht belegt. *(PL, M)*<br>*standardmäßig deaktiviert; Kategorie Konfiguration; gelesen alle 2 Abfragen* |
| Gesamt: Stufe | `cfg_overall_level`<br>select · holding 10067 · Gerät Heizung | - | 0 = `normal`: Normal (keine Korrektur)<br>1 = `increased`: Erhöht<br>2 = `increased2`: Erhöht (Stufe 2)<br>3 = `decreased`: Abgesenkt | Stufe für alle Heizfunktionen. Standardmäßig deaktiviert; Wirkung nicht belegt, und die Wirkung der Stufen ist ohnehin ungeklärt. *(PL, M)*<br>*standardmäßig deaktiviert; Kategorie Konfiguration; gelesen alle 2 Abfragen* |

## 14. Anlage, Firmware und Ausstattung

**Hintergrund: Pufferspeicher.** Ein *Pufferspeicher* hält Heizwasser zwischen Wärmepumpe und Heizkreisen vor. Ein **Reihenpuffer** sitzt im Rücklauf und wird vom gesamten Wasser durchströmt, es geht praktisch nichts verloren; er gleicht den Volumenstrom aus und gibt eine Reserve für das Abtauen. Ein **Trennpuffer** entkoppelt den Wärmepumpenkreis mit getrennten Pumpen von den Heizkreisen; Vor- und Rücklauf vermischen sich im Speicher etwas, das kostet etwa 2 bis 5 K und damit etwas Effizienz. Ein **Multifunktionspuffer** vereint mehrere Funktionen in einem Speicher. Weil eine Wärmepumpe nicht zu oft ein- und ausschalten soll, hält die Regelung außerdem eine *Mindestlaufzeit* und eine *Schaltspielsperre* (Mindest-Ausschaltzeit) ein; an der Referenzanlage liefert die Firmware beide als Konstanten (20 Minuten, FW). Die **Ausstattungs-Flags** (`cap_*`) sind Discrete Inputs, die sagen, welche Teile die Anlage hat; der Einrichtungsdialog nutzt sie, um die Ausstattung vorzuwählen. Die Firmware-Version wird aus drei Registern gelesen und ist nur informativ. Quellen: PL, FW, OBS, WEB ([Reihen- und Trennpuffer](#quellen)).

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| Anlage: Puffertyp | `buffer_type`<br>sensor · input 10202 · Gerät Wärmepumpe | - | 0 = `unknown`: Unbekannt<br>1 = `series`: Reihenpuffer<br>2 = `separation`: Trennpuffer<br>3 = `multi`: Multifunktionspuffer | Typ des in der Regelung eingestellten Pufferspeichers (siehe Hintergrund oben). Die Zuordnung der Werte steht in der Tabelle. *(PL)*<br>*Kategorie Diagnose; gelesen alle 120 Abfragen* |
| Anlage: Schaltspielsperre | `switching_lock_minutes`<br>sensor · input 10203 · Gerät Wärmepumpe | min | - | Mindest-Ausschaltzeit, bevor die Wärmepumpe wieder starten darf (*Schaltspielsperre*), in Minuten. Die Referenz-Firmware liefert die Konstante 20. *(PL, FW)*<br>*Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Anlage: Mindestlaufzeit | `min_runtime_minutes`<br>sensor · input 10204 · Gerät Wärmepumpe | min | - | Mindestlaufzeit der Wärmepumpe in Minuten. Die Referenz-Firmware liefert die Konstante 20. *(PL, FW)*<br>*Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Firmware: Plattform | `fw_platform`<br>sensor · input 10400 · Gerät Wärmepumpe | - | - | Erste Zahl der Firmware-Version. An der Referenzanlage lesen die drei Register 3, 92 und 3: Firmware V3.92.3. *(FW, OBS)*<br>*Kategorie Diagnose; gelesen alle 120 Abfragen* |
| Firmware: Version Haupt | `fw_major`<br>sensor · input 10401 · Gerät Wärmepumpe | - | - | Zweite Zahl der Firmware-Version (92 an der Referenzanlage). Die Integration braucht 92 oder neuer für Zirkulationspumpe und Extra-Warmwasser; bei älterer Firmware erzeugt sie einen Reparaturhinweis. *(FW, OBS)*<br>*Kategorie Diagnose; gelesen alle 120 Abfragen* |
| Firmware: Version Neben | `fw_minor`<br>sensor · input 10402 · Gerät Wärmepumpe | - | - | Dritte Zahl der Firmware-Version (3 an der Referenzanlage). *(FW, OBS)*<br>*Kategorie Diagnose; gelesen alle 120 Abfragen* |
| Ausstattung: Heizen | `cap_heating`<br>binary_sensor · discrete input 10000 · Gerät Wärmepumpe | - | an / aus | Ausstattungs-Flag: Die Anlage hat Heizen. Wählt die Ausstattung im Einrichtungsdialog vor. Nicht in python-luxtronik, nur durch Beobachtung belegt. *(OBS)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Ausstattung: Warmwasser | `cap_hot_water`<br>binary_sensor · discrete input 10001 · Gerät Wärmepumpe | - | an / aus | Ausstattungs-Flag: Die Anlage hat Warmwasser. Wählt die Ausstattung im Einrichtungsdialog vor. Nicht in python-luxtronik, nur durch Beobachtung belegt. *(OBS)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Ausstattung: Kühlen | `cap_cooling`<br>binary_sensor · discrete input 10002 · Gerät Wärmepumpe | - | an / aus | Ausstattungs-Flag: Die Anlage hat Kühlen. Wählt die Ausstattung im Einrichtungsdialog vor. Nicht in python-luxtronik, nur durch Beobachtung belegt. *(OBS)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Ausstattung: Pool | `cap_pool`<br>binary_sensor · discrete input 10003 · Gerät Wärmepumpe | - | an / aus | Ausstattungs-Flag: Die Anlage hat Pool. Wählt die Ausstattung im Einrichtungsdialog vor. Nicht in python-luxtronik, nur durch Beobachtung belegt. *(OBS)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Ausstattung: Raumregler | `cap_room_controller`<br>binary_sensor · discrete input 10005 · Gerät Wärmepumpe | - | an / aus | Ausstattungs-Flag: Die Anlage hat ein Raumregler. Wählt die Ausstattung im Einrichtungsdialog vor. Nicht in python-luxtronik, nur durch Beobachtung belegt. *(OBS)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Ausstattung: Mischkreis 1 Heizen | `cap_mk1_heating`<br>binary_sensor · discrete input 10006 · Gerät Wärmepumpe | - | an / aus | Ausstattungs-Flag: Die Anlage hat Heizen von Mischkreis 1. Wählt die Ausstattung im Einrichtungsdialog vor. Nicht in python-luxtronik, nur durch Beobachtung belegt. *(OBS)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Ausstattung: Mischkreis 1 Kühlen | `cap_mk1_cooling`<br>binary_sensor · discrete input 10007 · Gerät Wärmepumpe | - | an / aus | Ausstattungs-Flag: Die Anlage hat Kühlen von Mischkreis 1. Wählt die Ausstattung im Einrichtungsdialog vor. Nicht in python-luxtronik, nur durch Beobachtung belegt. *(OBS)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Ausstattung: Mischkreis 2 Heizen | `cap_mk2_heating`<br>binary_sensor · discrete input 10008 · Gerät Wärmepumpe | - | an / aus | Ausstattungs-Flag: Die Anlage hat Heizen von Mischkreis 2. Wählt die Ausstattung im Einrichtungsdialog vor. Nicht in python-luxtronik, nur durch Beobachtung belegt. *(OBS)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Ausstattung: Mischkreis 2 Kühlen | `cap_mk2_cooling`<br>binary_sensor · discrete input 10009 · Gerät Wärmepumpe | - | an / aus | Ausstattungs-Flag: Die Anlage hat Kühlen von Mischkreis 2. Wählt die Ausstattung im Einrichtungsdialog vor. Nicht in python-luxtronik, nur durch Beobachtung belegt. *(OBS)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Ausstattung: Mischkreis 3 Heizen | `cap_mk3_heating`<br>binary_sensor · discrete input 10010 · Gerät Wärmepumpe | - | an / aus | Ausstattungs-Flag: Die Anlage hat Heizen von Mischkreis 3. Wählt die Ausstattung im Einrichtungsdialog vor. Nicht in python-luxtronik, nur durch Beobachtung belegt. *(OBS)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |
| Ausstattung: Mischkreis 3 Kühlen | `cap_mk3_cooling`<br>binary_sensor · discrete input 10011 · Gerät Wärmepumpe | - | an / aus | Ausstattungs-Flag: Die Anlage hat Kühlen von Mischkreis 3. Wählt die Ausstattung im Einrichtungsdialog vor. Nicht in python-luxtronik, nur durch Beobachtung belegt. *(OBS)*<br>*Kategorie Diagnose; gelesen alle 10 Abfragen* |

## 15. Rohwerte

**Hintergrund.** Register, deren Bedeutung niemand geklärt hat, gibt es als Diagnose-Sensoren `raw_<Adresse>`: **standardmäßig deaktiviert**, nur lesend (nie geschrieben), selten abgefragt, als einfache 16-Bit-Zahl. Sie dienen der Analyse und dem Reverse Engineering. Baue keine Automationen darauf. Quellen: PL, FW.

| Name | Schlüssel | Einheit | Bereich / Werte | Erklärung |
|---|---|---|---|---|
| Rohwert: 10113 | `raw_10113`<br>sensor · input 10113 · Gerät Wärmepumpe | - | - | Unbekanntes Eingangsregister, Funktion nicht analysiert. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 4 Abfragen* |
| Rohwert: 10350 | `raw_10350`<br>sensor · input 10350 · Gerät Wärmepumpe | - | - | Undokumentiertes Eingangsregister (python-luxtronik: Funktion unbekannt). Keine Herstellerquelle für die Bedeutung; eine Registerquelle darunter ist, falls vorhanden, eine abgeleitete Beobachtung, keine Spezifikation. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 4 Abfragen* |
| Rohwert: 10351 | `raw_10351`<br>sensor · input 10351 · Gerät Wärmepumpe | - | - | Undokumentiertes Eingangsregister (python-luxtronik: Funktion unbekannt). Keine Herstellerquelle für die Bedeutung; eine Registerquelle darunter ist, falls vorhanden, eine abgeleitete Beobachtung, keine Spezifikation. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 4 Abfragen* |
| Rohwert: 10354 | `raw_10354`<br>sensor · input 10354 · Gerät Wärmepumpe | - | - | Undokumentiertes Eingangsregister (python-luxtronik: Funktion unbekannt). Keine Herstellerquelle für die Bedeutung; eine Registerquelle darunter ist, falls vorhanden, eine abgeleitete Beobachtung, keine Spezifikation. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 4 Abfragen* |
| Rohwert: 10355 | `raw_10355`<br>sensor · input 10355 · Gerät Wärmepumpe | - | - | Undokumentiertes Eingangsregister (python-luxtronik: Funktion unbekannt). Keine Herstellerquelle für die Bedeutung; eine Registerquelle darunter ist, falls vorhanden, eine abgeleitete Beobachtung, keine Spezifikation. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 4 Abfragen* |
| Rohwert: 10356 | `raw_10356`<br>sensor · input 10356 · Gerät Wärmepumpe | - | - | Undokumentiertes Eingangsregister (python-luxtronik: Funktion unbekannt). Keine Herstellerquelle für die Bedeutung; eine Registerquelle darunter ist, falls vorhanden, eine abgeleitete Beobachtung, keine Spezifikation. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 4 Abfragen* |
| Rohwert: 10360 | `raw_10360`<br>sensor · input 10360 · Gerät Wärmepumpe | - | - | Undokumentiertes Eingangsregister (python-luxtronik: Funktion unbekannt). Keine Herstellerquelle für die Bedeutung; eine Registerquelle darunter ist, falls vorhanden, eine abgeleitete Beobachtung, keine Spezifikation. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 4 Abfragen* |
| Rohwert: 10361 | `raw_10361`<br>sensor · input 10361 · Gerät Wärmepumpe | - | - | Undokumentiertes Eingangsregister (python-luxtronik: Funktion unbekannt). Keine Herstellerquelle für die Bedeutung; eine Registerquelle darunter ist, falls vorhanden, eine abgeleitete Beobachtung, keine Spezifikation. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 4 Abfragen* |
| Rohwert: 10352 | `raw_10352`<br>sensor · input 10352 · Gerät Wärmepumpe | - | - | Unbekanntes Eingangsregister, Funktion nicht analysiert. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Rohwert: 10353 | `raw_10353`<br>sensor · input 10353 · Gerät Wärmepumpe | - | - | Unbekanntes Eingangsregister, Funktion nicht analysiert. *(PL)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Rohwert: 10410 | `raw_10410`<br>sensor · input 10410 · Gerät Wärmepumpe | - | - | Oberes Wort eines 32-Bit-Zählers mit dem Teiler 3600 (ein Stundenzähler). Zusammen mit 10411. Bedeutung ungeklärt. *(FW)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Rohwert: 10411 | `raw_10411`<br>sensor · input 10411 · Gerät Wärmepumpe | - | - | Unteres Wort des 32-Bit-Zählers, der bei 10410 beginnt. Bedeutung ungeklärt. *(FW)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Rohwert: 10412 | `raw_10412`<br>sensor · input 10412 · Gerät Wärmepumpe | - | - | Oberes Wort eines 32-Bit-Zählers mit dem ungewöhnlichen Teiler 7200; die Einheit ist unklar (ungeklärt). Zusammen mit 10413. *(FW)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Rohwert: 10413 | `raw_10413`<br>sensor · input 10413 · Gerät Wärmepumpe | - | - | Unteres Wort des 32-Bit-Zählers, der bei 10412 beginnt. Bedeutung ungeklärt. *(FW)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Rohwert: 10416 | `raw_10416`<br>sensor · input 10416 · Gerät Wärmepumpe | - | - | Oberes Wort eines 32-Bit-Zählers mit dem Teiler 3600 (ein Stundenzähler). Zusammen mit 10417. Bedeutung ungeklärt. *(FW)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Rohwert: 10417 | `raw_10417`<br>sensor · input 10417 · Gerät Wärmepumpe | - | - | Unteres Wort des 32-Bit-Zählers, der bei 10416 beginnt. Bedeutung ungeklärt. *(FW)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Rohwert: 10500 | `raw_10500`<br>sensor · input 10500 · Gerät Wärmepumpe | - | - | Zeitwert, Bedeutung ungeklärt. *(FW)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Rohwert: 10501 | `raw_10501`<br>sensor · input 10501 · Gerät Wärmepumpe | - | - | Zeitwert; die Firmware teilt Sekunden durch 60, der Wert auf dem Bus ist also in Minuten. Bedeutung ungeklärt. *(FW)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 30 Abfragen* |
| Rohwert: 10502 | `raw_10502`<br>sensor · input 10502 · Gerät Wärmepumpe | - | - | Zeitwert; die Firmware teilt Sekunden durch 60, der Wert auf dem Bus ist also in Minuten. Bedeutung ungeklärt. *(FW)*<br>*standardmäßig deaktiviert; Kategorie Diagnose; gelesen alle 30 Abfragen* |

## Fallstricke und Wissenswertes

1. **Über die SHI gesetzte Werte sind flüchtig.** Die Regelung verwirft jeden über Modbus gesetzten Wert, wenn sie neu startet und wenn 600 s (10 Minuten) lang niemand auf die SHI zugegriffen hat; jeder Modbus-Zugriff setzt diesen Zeitgeber zurück, auch ein reines Lesen. Solange die Integration abfragt, läuft der Watchdog nicht ab; das größte Aktualisierungsintervall ist deshalb 300 s. Nach einem Reset lesen **Betriebsarten, Stufen und Sperren 0**, **Sollwerte ihren gespeicherten oder Standardwert** (nicht 0), und Anhebungen lesen vermutlich 0 (nicht belegt). Eine Auszeit von Home Assistant über 10 Minuten wirkt genauso. Sperren, die 0 lesen, heißt *nicht gesperrt*: Die Wärmepumpe fällt auf ihre eigene Regelung zurück (FW).
2. **Wiederherstellung nach einem Geräte-Reset** ist eine Option, standardmäßig aus. Ist sie an, schreibt die Integration die selbst gesetzten Werte zurück, aber nur nach einem Verbindungsausfall und nur, wenn jeder davon seinen Reset-Wert liest; eine Änderung bei durchgehender Abfrage gilt als fremd. Wiederhergestellte Schlüssel: `cfg_dhw_level`, `cfg_dhw_mode`, `cfg_dhw_offset`, `cfg_dhw_setpoint`, `cfg_heating_level`, `cfg_heating_mode`, `cfg_heating_offset`, `cfg_heating_setpoint`, `cfg_mk1_cool_mode`, `cfg_mk1_cool_offset`, `cfg_mk1_cool_setpoint`, `cfg_mk1_level`, `cfg_mk1_mode`, `cfg_mk1_offset`, `cfg_mk1_setpoint`, `cfg_mk2_cool_mode`, `cfg_mk2_cool_offset`, `cfg_mk2_cool_setpoint`, `cfg_mk2_level`, `cfg_mk2_mode`, `cfg_mk2_offset`, `cfg_mk2_setpoint`, `cfg_mk3_cool_mode`, `cfg_mk3_cool_offset`, `cfg_mk3_cool_setpoint`, `cfg_mk3_level`, `cfg_mk3_mode`, `cfg_mk3_offset`, `cfg_mk3_setpoint`, `cfg_room_setpoint`. Sperren, Zirkulationspumpe, Extra-Warmwasser, die Leistungsbegrenzung und die Gesamt-Gruppe sind bewusst ausgenommen. Lass die Option aus, wenn ein anderes System diese Register ebenfalls schreibt.
3. **Ein Sollwert zählt nur in seiner Betriebsart `setpoint`.** In `off`, `offset` und `level` ignoriert ihn die Regelung. Die Sollwert-Zahlen schreiben trotzdem in jeder Betriebsart; Climate und Water Heater lehnen ab. Prüfe `setpoint_active` und `effective_target`.
4. **Die Betriebsart `off` heißt „keine Vorgabe“, nicht aus.** Zum Stoppen des Heizens nimm die Heizungs-Sperre, für das Warmwasser die Warmwasser-Sperre.
5. **Warmwasser-Schreibzugriffe werden spät übernommen** (etwa 10 s) und nicht, solange die Warmwasser-Sperre an ist, siehe [Warmwasser-Steuerung](#9-warmwasser-steuerung).
6. **Zwei Schreiber überschreiben sich.** Heat Pump Optimizer, OpenEMS, die native Luxtronik-Integration (Port 8889), das Bedienteil und diese Integration schreiben dieselben Einstellungen; der letzte Schreibzugriff gewinnt. Eine Änderung, die nicht von Home Assistant kam, erzeugt den Reparaturhinweis *Wert außerhalb von Home Assistant geändert*; zurückgeschrieben wird nichts.
7. **Nicht verfügbar.** Ein Register, das die Regelung als nicht verfügbar meldet, liest die Rohzahl 32767 (0x7FFF), zum Beispiel 3276,7 an einem Temperatursensor. Die Integration übersetzt diesen Wert nicht; behandle ihn als unbekannt. Ein Register, das gar nicht existiert, macht die Entität *unbekannt*.
8. **Die Ausstattung bestimmt, welche Entitäten es gibt.** Abgewählte Teile werden nicht abgefragt und bekommen keine Entitäten; ihre Entity-IDs bleiben reserviert. Wähle keinen Teil ab, den ein Optimierer liest oder schreibt (zum Beispiel Mischkreis 1).
9. **Schreibbereiche** stammen aus python-luxtronik. Die Regelung wendet zusätzlich eigene Grenzen an; das Zurücklesen nach jedem Schreiben zeigt, was sie wirklich übernommen hat.
10. **Langsame Werte** (Zähler, Stunden, Einstellungen, Firmware) werden nur jede N-te Abfrage gelesen und können deshalb mehrere Aktualisierungsintervalle hinterherhinken.

## Umbenannte Schlüssel

Diese Schlüssel wurden umbenannt. Der alte Schlüssel bleibt im Entitäten-Vertrag, die Integration verschiebt den Registry-Eintrag, und die Entity-ID bleibt.

| Alter Schlüssel | Neuer Schlüssel |
|---|---|
| `raw_10109` | `outside_temp_average` |
| `raw_10110` | `heat_source_input` |
| `raw_10112` | `max_flow_temp` |

## Index aller Schlüssel

| Schlüssel | Plattform | Thema |
|---|---|---|
| `aux_heater_1` | binary_sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `aux_heater_2` | binary_sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `buffer_type` | sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `cap_cooling` | binary_sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `cap_heating` | binary_sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `cap_hot_water` | binary_sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `cap_mk1_cooling` | binary_sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `cap_mk1_heating` | binary_sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `cap_mk2_cooling` | binary_sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `cap_mk2_heating` | binary_sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `cap_mk3_cooling` | binary_sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `cap_mk3_heating` | binary_sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `cap_pool` | binary_sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `cap_room_controller` | binary_sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `cfg_dhw_level` | select | [9. Warmwasser-Steuerung](#9-warmwasser-steuerung) |
| `cfg_dhw_mode` | select | [9. Warmwasser-Steuerung](#9-warmwasser-steuerung) |
| `cfg_dhw_offset` | number | [9. Warmwasser-Steuerung](#9-warmwasser-steuerung) |
| `cfg_dhw_setpoint` | number | [9. Warmwasser-Steuerung](#9-warmwasser-steuerung) |
| `cfg_heating_level` | select | [8. Heizkreis-Steuerung](#8-heizkreis-steuerung) |
| `cfg_heating_mode` | select | [8. Heizkreis-Steuerung](#8-heizkreis-steuerung) |
| `cfg_heating_offset` | number | [8. Heizkreis-Steuerung](#8-heizkreis-steuerung) |
| `cfg_heating_setpoint` | number | [8. Heizkreis-Steuerung](#8-heizkreis-steuerung) |
| `cfg_mk1_cool_mode` | select | [11. Kühlen und Pool](#11-kühlen-und-pool) |
| `cfg_mk1_cool_offset` | number | [11. Kühlen und Pool](#11-kühlen-und-pool) |
| `cfg_mk1_cool_setpoint` | number | [11. Kühlen und Pool](#11-kühlen-und-pool) |
| `cfg_mk1_level` | select | [10. Mischkreis-Steuerung (Heizen)](#10-mischkreis-steuerung-heizen) |
| `cfg_mk1_mode` | select | [10. Mischkreis-Steuerung (Heizen)](#10-mischkreis-steuerung-heizen) |
| `cfg_mk1_offset` | number | [10. Mischkreis-Steuerung (Heizen)](#10-mischkreis-steuerung-heizen) |
| `cfg_mk1_setpoint` | number | [10. Mischkreis-Steuerung (Heizen)](#10-mischkreis-steuerung-heizen) |
| `cfg_mk2_cool_mode` | select | [11. Kühlen und Pool](#11-kühlen-und-pool) |
| `cfg_mk2_cool_offset` | number | [11. Kühlen und Pool](#11-kühlen-und-pool) |
| `cfg_mk2_cool_setpoint` | number | [11. Kühlen und Pool](#11-kühlen-und-pool) |
| `cfg_mk2_level` | select | [10. Mischkreis-Steuerung (Heizen)](#10-mischkreis-steuerung-heizen) |
| `cfg_mk2_mode` | select | [10. Mischkreis-Steuerung (Heizen)](#10-mischkreis-steuerung-heizen) |
| `cfg_mk2_offset` | number | [10. Mischkreis-Steuerung (Heizen)](#10-mischkreis-steuerung-heizen) |
| `cfg_mk2_setpoint` | number | [10. Mischkreis-Steuerung (Heizen)](#10-mischkreis-steuerung-heizen) |
| `cfg_mk3_cool_mode` | select | [11. Kühlen und Pool](#11-kühlen-und-pool) |
| `cfg_mk3_cool_offset` | number | [11. Kühlen und Pool](#11-kühlen-und-pool) |
| `cfg_mk3_cool_setpoint` | number | [11. Kühlen und Pool](#11-kühlen-und-pool) |
| `cfg_mk3_level` | select | [10. Mischkreis-Steuerung (Heizen)](#10-mischkreis-steuerung-heizen) |
| `cfg_mk3_mode` | select | [10. Mischkreis-Steuerung (Heizen)](#10-mischkreis-steuerung-heizen) |
| `cfg_mk3_offset` | number | [10. Mischkreis-Steuerung (Heizen)](#10-mischkreis-steuerung-heizen) |
| `cfg_mk3_setpoint` | number | [10. Mischkreis-Steuerung (Heizen)](#10-mischkreis-steuerung-heizen) |
| `cfg_overall_level` | select | [13. Gesamt-Heizen](#13-gesamt-heizen) |
| `cfg_overall_mode` | select | [13. Gesamt-Heizen](#13-gesamt-heizen) |
| `cfg_overall_offset` | number | [13. Gesamt-Heizen](#13-gesamt-heizen) |
| `cfg_power_limit` | number | [12. Leistungsbegrenzung](#12-leistungsbegrenzung) |
| `cfg_power_limit_mode` | select | [12. Leistungsbegrenzung](#12-leistungsbegrenzung) |
| `cfg_room_setpoint` | number | [8. Heizkreis-Steuerung](#8-heizkreis-steuerung) |
| `circulation` | switch | [9. Warmwasser-Steuerung](#9-warmwasser-steuerung) |
| `climate_heating` | climate | [8. Heizkreis-Steuerung](#8-heizkreis-steuerung) |
| `compressor_1` | binary_sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `compressor_2` | binary_sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `compressor_thermal_power` | sensor | [4. Leistung und berechnete Leistungszahl](#4-leistung-und-berechnete-leistungszahl) |
| `cooling_block` | switch | [7. Sperren (Schalter)](#7-sperren-schalter) |
| `cooling_configured` | binary_sensor | [11. Kühlen und Pool](#11-kühlen-und-pool) |
| `cooling_release` | binary_sensor | [11. Kühlen und Pool](#11-kühlen-und-pool) |
| `cooling_status` | sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `cop` | sensor | [4. Leistung und berechnete Leistungszahl](#4-leistung-und-berechnete-leistungszahl) |
| `cop_dhw` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `cop_heating` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `dhw` | sensor | [2. Warmwassertemperaturen](#2-warmwassertemperaturen) |
| `dhw_block` | switch | [7. Sperren (Schalter)](#7-sperren-schalter) |
| `dhw_limit` | sensor | [2. Warmwassertemperaturen](#2-warmwassertemperaturen) |
| `dhw_max` | sensor | [2. Warmwassertemperaturen](#2-warmwassertemperaturen) |
| `dhw_min` | sensor | [2. Warmwassertemperaturen](#2-warmwassertemperaturen) |
| `dhw_target` | sensor | [2. Warmwassertemperaturen](#2-warmwassertemperaturen) |
| `electric_power` | sensor | [4. Leistung und berechnete Leistungszahl](#4-leistung-und-berechnete-leistungszahl) |
| `electric_power_min` | sensor | [4. Leistung und berechnete Leistungszahl](#4-leistung-und-berechnete-leistungszahl) |
| `energy_el_cooling` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `energy_el_dhw` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `energy_el_heating` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `energy_el_pool` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `energy_el_total` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `energy_th_cooling` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `energy_th_dhw` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `energy_th_heating` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `energy_th_pool` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `energy_th_total` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `error_number` | sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `extra_dhw` | switch | [9. Warmwasser-Steuerung](#9-warmwasser-steuerung) |
| `flow` | sensor | [1. Temperaturen des Heizkreises](#1-temperaturen-des-heizkreises) |
| `fw_major` | sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `fw_minor` | sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `fw_platform` | sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `heat_generator_state` | sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `heat_source_input` | sensor | [1. Temperaturen des Heizkreises](#1-temperaturen-des-heizkreises) |
| `heat_source_out` | sensor | [1. Temperaturen des Heizkreises](#1-temperaturen-des-heizkreises) |
| `heating_block` | switch | [7. Sperren (Schalter)](#7-sperren-schalter) |
| `heating_limit` | sensor | [1. Temperaturen des Heizkreises](#1-temperaturen-des-heizkreises) |
| `heating_status` | sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `heatpump_vd2_status` | binary_sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `heatpump_zwe2_status` | binary_sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `heatpump_zwe3_status` | binary_sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `hot_water_status` | sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `hours_dhw` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `hours_heating` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `hours_hp` | sensor | [5. Energiezähler, Betriebsstunden und Gesamt-Leistungszahl](#5-energiezähler-betriebsstunden-und-gesamt-leistungszahl) |
| `max_flow_temp` | sensor | [1. Temperaturen des Heizkreises](#1-temperaturen-des-heizkreises) |
| `min_runtime_minutes` | sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `mk1_flow` | sensor | [3. Temperaturen der Mischkreise](#3-temperaturen-der-mischkreise) |
| `mk1_flow_max` | sensor | [3. Temperaturen der Mischkreise](#3-temperaturen-der-mischkreise) |
| `mk1_flow_min` | sensor | [3. Temperaturen der Mischkreise](#3-temperaturen-der-mischkreise) |
| `mk1_flow_target` | sensor | [3. Temperaturen der Mischkreise](#3-temperaturen-der-mischkreise) |
| `mk2_flow` | sensor | [3. Temperaturen der Mischkreise](#3-temperaturen-der-mischkreise) |
| `mk2_flow_max` | sensor | [3. Temperaturen der Mischkreise](#3-temperaturen-der-mischkreise) |
| `mk2_flow_min` | sensor | [3. Temperaturen der Mischkreise](#3-temperaturen-der-mischkreise) |
| `mk2_flow_target` | sensor | [3. Temperaturen der Mischkreise](#3-temperaturen-der-mischkreise) |
| `mk3_flow` | sensor | [3. Temperaturen der Mischkreise](#3-temperaturen-der-mischkreise) |
| `mk3_flow_max` | sensor | [3. Temperaturen der Mischkreise](#3-temperaturen-der-mischkreise) |
| `mk3_flow_min` | sensor | [3. Temperaturen der Mischkreise](#3-temperaturen-der-mischkreise) |
| `mk3_flow_target` | sensor | [3. Temperaturen der Mischkreise](#3-temperaturen-der-mischkreise) |
| `online` | binary_sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `operating_mode` | sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `outside` | sensor | [1. Temperaturen des Heizkreises](#1-temperaturen-des-heizkreises) |
| `outside_temp_average` | sensor | [1. Temperaturen des Heizkreises](#1-temperaturen-des-heizkreises) |
| `pool_block` | switch | [7. Sperren (Schalter)](#7-sperren-schalter) |
| `pool_configured` | binary_sensor | [11. Kühlen und Pool](#11-kühlen-und-pool) |
| `pool_status` | sensor | [6. Status und Betriebszustand](#6-status-und-betriebszustand) |
| `raw_10113` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10350` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10351` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10352` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10353` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10354` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10355` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10356` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10360` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10361` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10410` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10411` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10412` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10413` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10416` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10417` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10500` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10501` | sensor | [15. Rohwerte](#15-rohwerte) |
| `raw_10502` | sensor | [15. Rohwerte](#15-rohwerte) |
| `return` | sensor | [1. Temperaturen des Heizkreises](#1-temperaturen-des-heizkreises) |
| `return_external` | sensor | [1. Temperaturen des Heizkreises](#1-temperaturen-des-heizkreises) |
| `return_limit` | sensor | [1. Temperaturen des Heizkreises](#1-temperaturen-des-heizkreises) |
| `return_min_target` | sensor | [1. Temperaturen des Heizkreises](#1-temperaturen-des-heizkreises) |
| `return_target` | sensor | [1. Temperaturen des Heizkreises](#1-temperaturen-des-heizkreises) |
| `room` | sensor | [1. Temperaturen des Heizkreises](#1-temperaturen-des-heizkreises) |
| `switching_lock_minutes` | sensor | [14. Anlage, Firmware und Ausstattung](#14-anlage-firmware-und-ausstattung) |
| `water_heater_dhw` | water_heater | [9. Warmwasser-Steuerung](#9-warmwasser-steuerung) |

## Quellen

* python-luxtronik: [Bouni/python-luxtronik](https://github.com/Bouni/python-luxtronik), `luxtronik/definitions/inputs.py`, `holdings.py`, `datatypes.py` (MIT).
* [firmware-3.92.3-shi-analysis.md](firmware-3.92.3-shi-analysis.md), [registers.md](registers.md).
* Heizkurve: [Wikipedia: Heizkurve](https://de.wikipedia.org/wiki/Heizkurve)
* Wärmepumpe: [Wikipedia: Wärmepumpe](https://de.wikipedia.org/wiki/Wärmepumpe)
* Leistungszahl: [Wikipedia: Leistungszahl](https://de.wikipedia.org/wiki/Leistungszahl)
* Zweipunktregler: [Wikipedia: Zweipunktregler](https://de.wikipedia.org/wiki/Zweipunktregler)
* Arbeitszahl: [energiesparhaus.at: Arbeitszahl (Jahresarbeitszahl, JAZ)](https://www.energiesparhaus.at/fachbegriffe/arbeitszahl.htm)
* UBA factsheet: [Umweltbundesamt: Factsheet Trinkwarmwasserkonzepte](https://www.umweltbundesamt.de/sites/default/files/medien/11850/publikationen/factsheet_trinkwarmwasserkonzepte.pdf)
* Reihenpuffer und Trennpuffer: [elektronik-zeit.de: Reihenpuffer vs. Trennpuffer](https://elektronik-zeit.de/waermepumpe/reihenpuffer-trennpuffer-vergleich/)
* EVU-Sperre: [baunetzwissen.de: EVU-Sperre](https://www.baunetzwissen.de/glossar/e/evu-sperre-9514499)
* §14a EnWG: [42watt.de: § 14a EnWG](https://42watt.de/magazin/paragraph-14a-enwg)
