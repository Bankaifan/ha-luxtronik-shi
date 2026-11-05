# Luxtronik SHI (Modbus) für Home Assistant

🇬🇧 [English version](README.md)

Home-Assistant-Integration für **alpha innotec / Luxtronik Wärmepumpen** über die **Modbus/TCP-Schnittstelle
„Smart Home Interface" (SHI)** – komplett über die Oberfläche einrichtbar (Config Flow), ohne YAML.

Entwickelt und im Alltag getestet an einer **alpha innotec LWDV 91-1/3** (Luxtronik 2.x mit SHI).
Andere Luxtronik-Anlagen mit SHI sollten funktionieren, sind aber nicht getestet.

## Was die Integration kann

| Bereich | Entitäten |
|---|---|
| Temperaturen | Vorlauf, Rücklauf, Wärmequelle Ein-/Austritt, Außen-Mittelwert, Rücklauf-Soll/-Begrenzung/-Minimum, Rücklauf extern, Außen, Raum (nur mit Raumeinheit), Grenztemperaturen Heizen/Warmwasser, Warmwasser (Ist, Soll, Min, Max), Mischkreise 1–3 (Vorlauf, Soll, Min, Max) |
| Leistung & Energie | elektrische und thermische Leistung, minimale Stromaufnahme, Zähler Strom/Wärme (gesamt, Heizen, Warmwasser, Kühlen, Pool), Betriebsstunden |
| Status | Betriebsart als Klartext (Heizen, Warmwasser, Pool, EVU-Sperre, Abtauen, Aus, externe Quelle, Kühlen), **Verdichter 1/2 läuft**, **Zusatzheizung (ZWE) 1/2 aktiv**, Fehlernummer, Status Heizen/Warmwasser/Kühlung/Pool, Verbindung |
| Berechneter COP | **COP** (thermische / elektrische Leistung, Gerät der Wärmepumpe) und **COP gesamt** für Heizen und Warmwasser (thermische / elektrische Energiezähler, im Gerät *Heizung* / *Warmwasser*); unbekannt statt einer Zahl bei elektrischer Leistung unter 200 W, Nullwerten, negativen oder unplausiblen Werten oder nach einem Zählerreset |
| **Schreiben: Zahlen** | **Heizkurven-Anhebung** (−5 … +5 K), Heizen Sollwert, Warmwasser Sollwert und Anhebung, Mischkreise 1–3 Sollwert und Anhebung (Heizen und Kühlen), Gesamt-Heizung Anhebung, Leistungsbegrenzung (0–30 kW) |
| **Schreiben: Auswahl** | Betriebsart (Aus / Sollwert / Anhebung / Stufe) für Heizen, Warmwasser, Mischkreise 1–3, Gesamt-Heizung; Stufe (EVU-Sperre / Absenkung / Normal / Boost); Leistungsbegrenzung (keine / weich / hart) |
| **Schreiben: Schalter** | *Heizung sperren*, *Warmwasser sperren*, *Kühlung sperren*, *Pool sperren*, **Zirkulationspumpe**, *Extra-Warmwasser* |
| Diagnose | Puffertyp, Schaltspielsperre, Mindestlaufzeit, Grenz-/Min-/Max-Werte, Ausstattungsmerkmale, Firmware, undokumentierte Rohwerte (standardmäßig deaktiviert) |

### Gliederung in Home Assistant

Wie in den Menüs der Luxtronik-Regelung sind die Entitäten auf Geräte verteilt:

| Gerät | Inhalt |
|---|---|
| **<Name>** (Wärmepumpe) | Temperaturen (Vorlauf, Rücklauf, Außen, Wärmequelle), Status und Betriebsart, Verdichter/Zusatzheizung, Leistung, Gesamtenergie und Verdichterstunden, Leistungsbegrenzung, Anlagenwerte, Firmware, Ausstattung, Rohwerte |
| **<Name> Heizung** | Betriebsart, Sollwert, Heizkurven-Anhebung, Stufe, Gesamt-Heizung, Sperre, Mischkreise 1–3, Energie und Stunden Heizen |
| **<Name> Warmwasser** | Temperaturen, Betriebsart, Sollwert, Anhebung, Stufe, Sperre, Zirkulationspumpe, Extra-Warmwasser, Energie und Stunden Warmwasser |
| **<Name> Kühlung** / **<Name> Pool** | nur wenn Kühlung bzw. Pool in der Ausstattung gewählt ist |

Die Unter-Geräte hängen am Gerät der Wärmepumpe. Innerhalb eines Unter-Geräts sind die Namen kurz (*Sollwert*,
*Sperren*, *Mischkreis 1: Sollwert*); Home Assistant zeigt sie zusammen mit dem Gerätenamen an, z. B.
„Wärmepumpe Heizung Sollwert“. Das Verschieben zwischen Geräten ändert keine Entity-ID. Auf jeder Geräteseite
trennt Home Assistant zusätzlich nach *Steuerelemente*, *Sensoren*, *Konfiguration* und *Diagnose*.

### Ausstattung der Anlage

Beim Einrichten fragt die Integration, welche optionalen Teile vorhanden sind: **Mischkreis 1–3, Kühlung,
Pool, Raumeinheit**. Vorausgewählt ist, was die Wärmepumpe über ihre Ausstattungs-Register meldet.
Abgewählte Teile werden nicht abgefragt und erscheinen nicht als Entitäten. Änderbar unter
*Einstellungen → Geräte & Dienste → Luxtronik SHI → Konfigurieren*. Die Entity-IDs abgewählter Teile bleiben
reserviert; schaltet man den Teil wieder ein, kommen dieselben Entitäten zurück.
Einträge aus Versionen vor 0.3.0 behalten alle Entitäten, bis die Ausstattung dort einmal gespeichert wird.

> Wer einen Planer wie den Heat Pump Optimizer nutzt: Teile, deren Entitäten der Planer liest oder
> schreibt (z. B. Mischkreis 1), nicht abwählen.

Eine **Climate-Entität** für den Heizkreis fasst die vorhandene Betriebsart (Aus / Heizen) und den Heizungs-Sollwert
(10–70 °C) zusammen und zeigt die Vorlauftemperatur als Istwert. Sie schreibt dieselben Register wie die Auswahl
„Betriebsart" und die Zahl „Sollwert" der Heizung. Bei neuen Installationen ist sie standardmäßig aktiviert; bei Einträgen,
die vor ihrer Einführung angelegt wurden, ist sie standardmäßig deaktiviert (in den Entitäts-Einstellungen aktivierbar).

> Planer wie der Heat Pump Optimizer schreiben dieselben Register (Betriebsart und Sollwert der Heizung). Climate-Entität
> und ein solcher Planer nicht gleichzeitig verwenden, sonst überschreiben sie sich gegenseitig.

Eine **Water-Heater-Entität** im Gerät *Warmwasser* fasst die vorhandene Betriebsart (Aus / Sollwert / Anhebung / Stufe,
wie in der Auswahl) und den Warmwasser-Sollwert (10–65 °C) zusammen und zeigt die Warmwassertemperatur als Istwert. Sie
schreibt dieselben Register wie die Auswahl „Betriebsart" und die Zahl „Sollwert" des Warmwassers. Wie die Climate-Entität
ist sie bei neuen Installationen standardmäßig aktiviert und bei Einträgen, die vor ihrer Einführung angelegt wurden,
standardmäßig deaktiviert.

> Der Heat Pump Optimizer steuert das Warmwasser nicht über diese Entität. Ein Planer sollte nicht gleichzeitig dieselben
> Register (Betriebsart und Sollwert des Warmwassers) schreiben, sonst überschreiben sie sich gegenseitig.

Die Einstellungen (Zahlen und Auswahl) liegen in der Kategorie *Konfiguration* der Geräteseite. Schreibzugriffe verwenden
dieselben Register wie die Smart-Home-Schnittstelle selbst; die Wärmepumpe erzwingt dabei ihre eigenen Grenzen.

Wichtige Eigenschaften:

* **Gebündelte Abfragen** statt eines Requests pro Wert – schont die Wärmepumpe. Lehnt das Gerät eine Blockabfrage ab
  (z. B. weil ein Register in der Lücke fehlt), liest die Integration automatisch einzeln weiter.
* **Abgestufte Abfrageintervalle**: Messwerte jeden Zyklus (Standard 30 s), Zähler/Einstellungen seltener, Firmware fast nie.
* **Nach jedem Schreibzugriff wird der Wert zurückgelesen**, die Oberfläche zeigt also immer den echten Gerätezustand.
* Negative Werte (Heizkurven-Anhebung) werden korrekt als 16-bit-Zweierkomplement geschrieben.
* Deutsch und Englisch.

## Installation

Die Integration ist (noch) nicht im Standard-Katalog und wird deshalb per Link hinzugefügt.

**Home Assistant 2026.11 oder neuer (Marketplace):**

1. **Einstellungen → Marketplace →** per Link hinzufügen (*Add from link*) → `https://github.com/Bankaifan/ha-luxtronik-shi`.
   Dafür ist eine GitHub-Verbindung nötig (Anmeldung per Gerätecode, nur Lesezugriff auf öffentliche Daten).
2. „Luxtronik SHI (Modbus)" installieren, Home Assistant neu starten.

**Ältere Home-Assistant-Versionen (HACS):**

1. HACS → ⋮ → **Benutzerdefinierte Repositories** → `https://github.com/Bankaifan/ha-luxtronik-shi`, Kategorie **Integration**.
2. „Luxtronik SHI (Modbus)" installieren, Home Assistant neu starten.

**Danach in beiden Fällen:**

Home Assistant kann **die Wärmepumpe automatisch finden** (DHCP), wenn beide im selben Netzsegment liegen
(DHCP-Verkehr wird nicht zwischen VLANs geroutet) und die Wärmepumpe ihre Adresse erneuert. Sie erscheint dann unter *Einstellungen → Geräte &
Dienste → Entdeckt*. Angeboten werden nur Geräte, deren Smart-Home-Schnittstelle auf Modbus/TCP-Port 502 antwortet;
bei anderem Port oder anderer Geräte-ID die Wärmepumpe von Hand hinzufügen. Ändert sich die IP-Adresse einer
bereits eingerichteten Wärmepumpe, übernimmt die Erkennung die neue Adresse.

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → „Luxtronik SHI (Modbus)"**.
2. Name, IP-Adresse der Wärmepumpe, Port (502) und Geräte-ID (1) eintragen.
3. Ausstattung bestätigen (siehe oben).

Voraussetzung: In der Regelung ist Modbus/TCP aktiviert (Smart-Home-Schnittstelle) und die Wärmepumpe ist im Netz erreichbar.

> **Integration nicht löschen und neu hinzufügen**, wenn Automationen oder ein Planer an ihren Entity-IDs hängen.
> Beim Neuanlegen entstehen neue Entitäten mit Standard-IDs. Host, Port oder Geräte-ID stattdessen über
> *Neu konfigurieren* ändern.

## Beta-Versionen

Vorabversionen (`X.Y.Z-beta.N`) werden als GitHub-Pre-Releases veröffentlicht. Zum Testen in HACS die Integration
öffnen, **Erneut herunterladen** (*Redownload*) wählen und **Beta-Versionen anzeigen** (*Show beta versions*)
aktivieren. Beta-Versionen können sich zwischen den Releases ändern und sind zum Testen gedacht. Wer die Option nicht
aktiviert, ist nicht betroffen und erhält nur stabile Versionen.

## Umstieg von einer bestehenden YAML-`modbus:`-Konfiguration

Die Integration ersetzt die YAML-Konfiguration (`modbus:`-Hub plus Template-Entitäten) vollständig. Die internen Schlüssel sind
absichtlich so benannt wie die früheren Entity-IDs (`lwdv_shi_<schluessel>`). So lief der Umstieg an der Referenzanlage
(LWDV 91-1/3, Heat Pump Optimizer im Modus „control") ohne Umbau der Konsumenten:

1. **YAML-Hub zuerst entfernen** (`modbus:`-Block und die zugehörigen Template-Entitäten aus der `configuration.yaml`, Neustart).
   Manche SHI-Firmwares erlauben nur wenige gleichzeitige TCP-Verbindungen, außerdem soll nur ein Zugriffsweg schreiben.
2. Integration hinzufügen (siehe oben).
3. **Verwaiste Registry-Einträge der alten YAML-Entitäten löschen** (Status „wiederhergestellt/nicht verfügbar"), sonst ist die
   alte Entity-ID belegt und das Umbenennen schlägt fehl.
4. Die neuen Entitäten (`warmepumpe_*`) auf die alten IDs umbenennen (Einstellungen → Entitäten), z. B. `sensor.lwdv_shi_flow`,
   `sensor.lwdv_shi_return`, `switch.lwdv_shi_heating_block`, `switch.lwdv_shi_dhw_block`. Die Heizkurven-Anhebung ist jetzt
   schreibbar (`number.<name>_heizkurven_anhebung`, vorher nur lesbar als `sensor.einstellung_heizen_anhebung_heating_offset`).
5. **Konsumenten prüfen:** Das Umbenennen aktualisiert keine Referenzen in Dashboards, Automationen und Templates. Prüfen
   (z. B. mit der Entitätssuche) und Verweise auf entfallene Sensoren anpassen.
6. **Betriebsart ist jetzt Text** (`off`, `heating`, `dhw`, `defrost`, …). Die alte YAML-Entität war numerisch (Luxtronik: 1 = Warmwasser,
   5 = keine Anforderung). Templates, die auf Zahlen prüfen, müssen auf Text umgestellt werden.
7. Langzeitstatistiken bleiben erhalten, wenn die neue Entität dieselbe Entity-ID und dieselbe Einheit bekommt.
   Statistiken entfallener Entitäten (z. B. `einstellung_*`, `diagnose_rohwert_*`) bleiben verwaist in der Datenbank.

### Zusammenspiel mit der nativen Luxtronik-Integration (Port 8889)

Beide Integrationen können nebeneinander laufen, sollten aber klar getrennt werden:

* **luxtronik_shi (diese Integration):** der einzige Weg, der **schreibt** (Sperren, Sollwerte, Betriebsarten, Zirkulationspumpe)
  und die Werte, die ein Planer wie der Heat Pump Optimizer braucht.
* **Native Luxtronik-Integration (Entitäten `luxtronik_<seriennummer>_*`):** nur **Diagnose** (zusätzliche Messwerte,
  Parameter, Fehlerspeicher). Ihre Schreib-Entitäten (select, climate, switch, number) werden deaktiviert, damit nicht zwei
  Integrationen dieselbe Regelung beschreiben. Diagnose-Entitäten werden einzeln bei Bedarf aktiviert.
* Einstellungen, die nur das native Protokoll bietet (z. B. die Thermische Desinfektion/Legionellenschutz), werden nicht von
  dieser Integration geändert. Das bleibt eine bewusste Entscheidung des Betreibers.

### `tools/gen_yaml.py`

Das Skript erzeugt aus der Registerliste die gleichwertige YAML-Konfiguration (`modbus:`-Hub plus Templates). Es ist ein
**Legacy-Werkzeug** für alle, die bewusst bei YAML bleiben wollen. Es wird nicht mehr produktiv eingesetzt und nicht gegen
neue Registerlisten-Änderungen getestet. Der empfohlene Weg ist die Integration.

## Quellen der Registerkarte

* [Bouni/python-luxtronik](https://github.com/Bouni/python-luxtronik), Modul `luxtronik/shi` und
  `luxtronik/definitions/{inputs,holdings}.py` (MIT): Adressen, Datentypen, Wertebereiche, Firmware-Stand.
  Laut dieser Quelle sind die SHI-Holding-Register **flüchtig** und werden beim Neustart der Regelung
  zurückgesetzt – anders als die dauerhaften Einstellungen der Regelung.
* Messungen an der Referenzanlage (LWDV 91-1/3, Firmware 3.92.3), siehe unten.
* Die DHCP-Erkennungsmerkmale (MAC-Präfixe, Hostname `wp-novelan`) stammen aus
  [BenPru/luxtronik](https://github.com/BenPru/luxtronik) (MIT).
* Nicht in python-luxtronik enthalten und daher nur durch Beobachtung belegt: die Ausstattungs-Register
  (Discrete Inputs 10000–10011), Firmware-Haupt-/Nebenversion (10401/10402) und die Deutung von
  10404/10406/10408 als Betriebsstunden.
* Vollständige Tabelle aller Register (Typ, Adresse, Datentyp, Skalierung, Einheit, Bereich): [docs/registers.md](docs/registers.md).

## Reparaturhinweise

Die Integration meldet diesen Hinweis unter *Einstellungen > System > Reparaturen*. Er verschwindet von selbst,
sobald seine Ursache weg ist.

| Hinweis | Schweregrad | Wird ausgelöst, wenn |
|---|---|---|
| Smart-Home-Schnittstelle nicht erreichbar | Fehler | Alle Abfragen sind 10 Minuten in Folge fehlgeschlagen. |
| Werte nach Verbindungsausfall geändert | Warnung | Nach einem Ausfall weichen Heizungssperre, Warmwassersperre, Heizungs-Betriebsart oder Warmwasser-Betriebsart vom zuletzt vor dem Ausfall gelesenen Wert ab. |

### Werte nach einem Ausfall geändert

War die Regelung nicht erreichbar (z. B. Neustart oder Stromausfall, die SHI-Holding-Register sind flüchtig) und
meldet sich mit anderen Werten für Heizungssperre, Warmwassersperre, Heizungs- oder Warmwasser-Betriebsart zurück,
zeigt eine Warnung die alten und neuen Werte. **Das ist nur ein Hinweis: Die Integration schreibt nie etwas
zurück.** Verglichen wird mit der normalen Abfrage, es gibt keine zusätzlichen Modbus-Lesezugriffe. Der Hinweis
verschwindet, wenn die Werte wieder denen vor dem Ausfall entsprechen, oder wenn du ihn schließt; sonst bleibt er.

Einschränkung: Die Werte vor dem Ausfall liegen nur im Arbeitsspeicher. Nach einem Neustart von Home Assistant sind
sie weg; eine Änderung während eines Ausfalls, der einen Neustart überdauert, wird nicht bemerkt.

## Hinweise und Grenzen

* **Rücklauf / Rücklauf-Soll:** Die veröffentlichte Registerliste nennt 10100 „RL-Soll" und 10101 „RL-Ist". Gemessen an einer
  echten Anlage ist es umgekehrt (10100 folgt der Wassertemperatur, 10101 springt beim Heizen auf den Sollwert). Die
  Entitäten folgen der Messung.
* **Heizen Sollwert (Reg. 10001):** Gemessen wirkt der Wert als Rücklauf-Soll, nicht als Vorlauf-Soll (`Rücklauf Soll` folgte dem
  geschriebenen Wert). Er greift nur bei Heizen-Betriebsart `setpoint` (Reg. 10000 = 1).
* **Heizung sperren:** `switch.<name>_heating_block` sperrt nur das Heizen; Warmwasser läuft weiter. Wer die Heizung von einem
  Planer (z. B. Heat Pump Optimizer) steuern lässt, kann bei geplanten 0 W sperren und bei Ausfall des Planers oder zu kaltem
  Raum wieder freigeben.
* Die *Stufe*-Werte (EVU-Sperre / Absenkung / Normal / Boost) sind aus der Community-Dokumentation übernommen (vermutlich
  SG-Ready) und nicht an jeder Firmware bestätigt. Zirkulationspumpe und Extra-Warmwasser gibt es erst ab Firmware 3.92.0.
* **Mischkreis-Ventil:** Das SHI liefert nur Temperaturen und Betriebsart/Sollwerte der Mischkreise, keine Ventilstellung und
  keine Umschaltung „Ventil immer offen". Das wird in der Regelung am Gerät (Installateur-Ebene) eingestellt.
* **Heizungsumwälzpumpen** (HUP/Heizkreispumpe) sind über das SHI nicht steuerbar, nur die Zirkulationspumpe des Warmwassers.
  Darüber hinaus bietet das native Luxtronik-Protokoll (Port 8889, z. B. die Integration von BenPru) deutlich mehr Parameter.
* Bei Warmwasser-Betriebsart 0 („Aus") ignoriert die Wärmepumpe den Sollwert; das tatsächliche Ziel steht im Sensor *Warmwasser Soll*.
* Schreibzugriffe wirken direkt auf die Wärmepumpe. Wer Heizungs-/Warmwassersperre oder Offset automatisiert, sollte
  das mit Bedacht tun.
* **Werte können nach einem Neustart der Steuerung zurückfallen.** Die SHI-Holdingregister sind flüchtig (siehe
  *Quellen*). Nach Stromausfall oder Neustart der Steuerung können über diese Integration geschriebene Werte, etwa die
  Heizungs- oder Warmwassersperre, auf den Standardwert der Steuerung zurückfallen, z. B. `aus`. Die Integration
  erkennt das **nicht** und korrigiert es auch nicht: Die Entität zeigt den Wert der Steuerung, und er wird nicht
  automatisch neu geschrieben. Dasselbe passiert, wenn ein anderer Schreiber (Planer oder jemand an der Steuerung) einen
  Wert ändert. Nach einem Stromausfall Sperren und Betriebsart prüfen oder Automatisierung bzw. Planer die Werte erneut
  schreiben lassen.

## Entwicklung

```bash
python -m venv venv && . venv/bin/activate
pip install -r requirements_test.txt pytest-timeout
pytest --timeout=60
```

Die Tests laufen gegen einen kleinen simulierten Modbus/TCP-Server (`tests/fake_shi.py`), der wie die echte SHI nur
vorhandene Register beantwortet. Die Übersetzungen werden aus der Registerliste erzeugt:
`python tools/gen_translations.py`.

Releases entstehen automatisch: Landet eine Versionserhöhung auf `main`, setzt ein GitHub-Actions-Workflow den Tag
und veröffentlicht das Release mit dem passenden CHANGELOG-Abschnitt als Text.

Langfristiges Ziel: eine Bibliothek auf PyPI auslagern und die Integration im Home-Assistant-Core einreichen.

## Haftung

Inoffiziell, keine Verbindung zu alpha innotec oder Luxtronik. Nutzung auf eigene Verantwortung.
