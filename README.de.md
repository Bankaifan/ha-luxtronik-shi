<p align="center">
  <img src="assets/banner.png" alt="Luxtronik SHI – alpha innotec / Luxtronik Wärmepumpen in Home Assistant" width="100%">
</p>

<p align="center">
  <a href="https://github.com/Bankaifan/ha-luxtronik-shi/releases"><img src="https://img.shields.io/github/v/release/Bankaifan/ha-luxtronik-shi?sort=semver&label=release" alt="Aktuelles Release"></a>
  <a href="https://github.com/Bankaifan/ha-luxtronik-shi/actions/workflows/validate.yml"><img src="https://img.shields.io/github/actions/workflow/status/Bankaifan/ha-luxtronik-shi/validate.yml?branch=main&label=validate" alt="Validate"></a>
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-custom-41BDF5" alt="HACS Custom Repository"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2025.8%2B-18BCF2?logo=homeassistant&logoColor=white" alt="Home Assistant 2025.8 oder neuer">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/Bankaifan/ha-luxtronik-shi" alt="Lizenz"></a>
</p>

<p align="center">🇬🇧 <a href="README.md">English version</a></p>

Home-Assistant-Integration für **alpha innotec / Luxtronik Wärmepumpen** über die **Modbus/TCP-Schnittstelle
„Smart Home Interface" (SHI)**. Komplett über die Oberfläche einrichtbar, ohne YAML.

Entwickelt und im Alltag genutzt an einer **alpha innotec LWDV 91-1/3** (Luxtronik 2.x mit SHI, Firmware 3.92.3).
Andere Luxtronik-Anlagen mit SHI sollten funktionieren, sind aber nicht getestet. Wenn deine läuft, freuen wir uns
über einen [Modellbericht](https://github.com/Bankaifan/ha-luxtronik-shi/issues/new/choose).

## Auf einen Blick

* 🔍 **Automatische Erkennung** (DHCP) und ein Einrichtungsassistent, der die vorhandene Ausstattung abfragt.
* 🗂️ **Gegliedert wie die Regelung:** eigene Geräte für Wärmepumpe, Heizung, Warmwasser, Kühlung und Pool.
* 🌡️ **Climate- und Water-Heater-Entität** für Heizung und Warmwasser, dazu Zahlen, Auswahlen und Schalter für
  Sollwerte, Betriebsarten, Sperren und die Zirkulationspumpe.
* ⚡ **Leistung, Energie und COP** – elektrische und thermische Werte je Bereich, mit berechnetem COP.
* ✅ **Sicheres Schreiben:** Jeder Schreibzugriff wird gegen einen Wertebereich geprüft und von der Wärmepumpe
  zurückgelesen.
* 🪶 **Schont die Wärmepumpe:** gebündelte Abfragen und abgestufte Intervalle statt eines Requests pro Wert.
* 🛠️ **Reparaturhinweise und Diagnose** bei veralteter Firmware, Verbindungsverlust und Werten, die sich während
  eines Ausfalls geändert haben, dazu ein Diagnose-Download für Fehlermeldungen.
* 🇩🇪 🇬🇧 Deutsch und Englisch.

**Inhalt:** [Installation](#installation) · [Funktionen](#was-die-integration-kann) ·
[Gliederung](#gliederung-in-home-assistant) · [Ausstattung](#ausstattung-der-anlage) ·
[Reparaturhinweise](#reparaturhinweise) · [Diagnose](#diagnose) · [Beta-Versionen](#beta-versionen) ·
[Hinweise und Grenzen](#hinweise-und-grenzen) · [Entwicklung](#entwicklung)

## Installation

Die Integration ist noch nicht im HACS-Standardkatalog (der Antrag läuft) und wird deshalb per Link hinzugefügt.

**Home Assistant 2026.11 oder neuer (Marketplace):**

1. **Einstellungen → Marketplace →** per Link hinzufügen (*Add from link*) → `https://github.com/Bankaifan/ha-luxtronik-shi`.
   Dafür ist eine GitHub-Verbindung nötig (Anmeldung per Gerätecode, nur Lesezugriff auf öffentliche Daten).
2. „Luxtronik SHI (Modbus)" installieren, Home Assistant neu starten.

**Ältere Home-Assistant-Versionen (HACS):**

1. HACS → ⋮ → **Benutzerdefinierte Repositories** → `https://github.com/Bankaifan/ha-luxtronik-shi`, Kategorie **Integration**.
2. „Luxtronik SHI (Modbus)" installieren, Home Assistant neu starten.

**Danach in beiden Fällen:**

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → „Luxtronik SHI (Modbus)"**.
2. Name, IP-Adresse der Wärmepumpe, Port (502) und Geräte-ID (1) eintragen.
3. Ausstattung bestätigen (siehe [unten](#ausstattung-der-anlage)).

Voraussetzung: In der Regelung ist Modbus/TCP aktiviert (Smart-Home-Schnittstelle) und die Wärmepumpe ist im Netz erreichbar.

**Automatische Erkennung:** Home Assistant findet die Wärmepumpe per DHCP, wenn beide im selben Netzsegment liegen
(DHCP-Verkehr wird nicht zwischen VLANs geroutet) und die Wärmepumpe ihre Adresse erneuert. Sie erscheint dann unter
*Einstellungen → Geräte & Dienste → Entdeckt*. Angeboten werden nur Geräte, deren Smart-Home-Schnittstelle auf
Modbus/TCP-Port 502 antwortet; bei anderem Port oder anderer Geräte-ID die Wärmepumpe von Hand hinzufügen. Ändert sich
die IP-Adresse einer bereits eingerichteten Wärmepumpe, übernimmt die Erkennung die neue Adresse.

> **Integration nicht löschen und neu hinzufügen**, wenn Automationen oder ein Planer an ihren Entity-IDs hängen.
> Beim Neuanlegen entstehen neue Entitäten mit Standard-IDs. Host, Port oder Geräte-ID stattdessen über
> *Neu konfigurieren* ändern.

## Was die Integration kann

| Bereich | Entitäten |
|---|---|
| Temperaturen | Vorlauf, Rücklauf, Wärmequelle Ein-/Austritt, Außen-Mittelwert, Rücklauf-Soll/-Begrenzung/-Minimum, Rücklauf extern, Außen, Raum (nur mit Raumeinheit), Grenztemperaturen Heizen/Warmwasser, Warmwasser (Ist, Soll, Min, Max), Mischkreise 1–3 (Vorlauf, Soll, Min, Max; bei Mischkreis 2 und 3 standardmäßig deaktiviert) |
| Leistung & Energie | elektrische und thermische Leistung, minimale Stromaufnahme, Zähler Strom/Wärme (gesamt, Heizen, Warmwasser, Kühlen, Pool), Betriebsstunden |
| Berechneter COP | **COP** (thermische / elektrische Leistung, Gerät der Wärmepumpe) und **COP gesamt** für Heizen und Warmwasser (thermische / elektrische Energiezähler, im Gerät *Heizung* / *Warmwasser*); unbekannt statt einer Zahl bei elektrischer Leistung unter 200 W, Nullwerten, negativen oder unplausiblen Werten oder nach einem Zählerreset |
| Status | Betriebsart als Klartext (Heizen, Warmwasser, Pool, EVU-Sperre, Abtauen, Aus, externe Quelle, Kühlen), **Verdichter 1/2 läuft**, **Zusatzheizung (ZWE) 1/2 aktiv** (zusätzliche Statusbits für VD2, ZWE2 und ZWE3 sind standardmäßig deaktiviert), Fehlernummer, Status Heizen/Warmwasser/Kühlung/Pool, Verbindung |
| **Climate / Water Heater** | Heizkreis (Aus / Heizen, Sollwert 15–75 °C) und Warmwasser (Aus / Sollwert / Anhebung / Stufe, Sollwert 30–75 °C), siehe unten |
| **Schreiben: Zahlen** | **Heizkurven-Anhebung** (−20 … +20 K), Heizen Sollwert, Warmwasser Sollwert und Anhebung, Mischkreise 1–3 Sollwert und Anhebung (Heizen und Kühlen), Gesamt-Heizung Anhebung, Wert der Leistungsbegrenzung (0–30 kW) |
| **Schreiben: Auswahl** | Betriebsart (Aus / Sollwert / Anhebung / Stufe) für Heizen, Warmwasser, Mischkreise 1–3 (Heizen und Kühlen), Gesamt-Heizung; Stufe (EVU-Sperre / Absenkung / Normal / Boost); Modus der Leistungsbegrenzung (keine / weich / hart) |
| **Schreiben: Schalter** | *Heizung sperren*, *Warmwasser sperren*, *Kühlung sperren*, *Pool sperren* (nur mit gewähltem Pool), **Zirkulationspumpe**, *Extra-Warmwasser* |
| Diagnose | Puffertyp, Schaltspielsperre, Mindestlaufzeit, Grenz-/Min-/Max-Werte, Ausstattungsmerkmale, Firmware, undokumentierte Rohwerte (standardmäßig deaktiviert) |

Mischkreis 2 und 3 haben dieselben schreibbaren Entitäten wie Mischkreis 1 (Betriebsart, Sollwert, Anhebung, Stufe sowie
Betriebsart, Sollwert und Anhebung für Kühlen). Alle Schreibbereiche folgen python-luxtronik (holdings.py): Heizen
Sollwert 20–65 °C und Anhebung −5 … +5 K, Kühlen Sollwert 5–25 °C und Anhebung −5 … +5 K. Mischkreis 1 hat dieselben Bereiche. Sie existieren nur, wenn der Mischkreis in der [Ausstattung](#ausstattung-der-anlage) gewählt ist (die
Kühl-Entitäten brauchen zusätzlich Kühlung).

Die Einstellungen (Zahlen und Auswahl) liegen in der Kategorie *Konfiguration* der Geräteseite. Schreibzugriffe verwenden
dieselben Register wie die Smart-Home-Schnittstelle selbst; die Wärmepumpe erzwingt dabei ihre eigenen Grenzen. Nach jedem
Schreibzugriff wird der Wert zurückgelesen, die Oberfläche zeigt also immer den echten Gerätezustand. Negative Werte
(Heizkurven-Anhebung) werden korrekt als 16-bit-Zweierkomplement geschrieben.

### Climate und Water Heater

Eine **Climate-Entität** für den Heizkreis fasst die Betriebsart (Aus / Heizen) und den Heizungs-Sollwert (15–75 °C)
zusammen und zeigt die Vorlauftemperatur als Istwert. Eine **Water-Heater-Entität** im Gerät *Warmwasser* fasst die
Warmwasser-Betriebsart (Aus / Sollwert / Anhebung / Stufe) und den Warmwasser-Sollwert (30–75 °C) zusammen und zeigt die
Warmwassertemperatur als Istwert. Beide schreiben dieselben Register wie die passende Auswahl „Betriebsart" und die Zahl
„Sollwert".

Bei neuen Installationen sind beide standardmäßig aktiviert. Bei Einträgen, die vor ihrer Einführung angelegt wurden, sind
sie standardmäßig deaktiviert (in den Entitäts-Einstellungen aktivierbar).

> Planer wie der Heat Pump Optimizer schreiben dieselben Register. Diese Entitäten und einen solchen Planer nicht
> gleichzeitig für denselben Kreis verwenden, sonst überschreiben sie sich gegenseitig. Der Heat Pump Optimizer steuert
> das Warmwasser nicht über die Water-Heater-Entität.

### Gliederung in Home Assistant

Wie in den Menüs der Luxtronik-Regelung sind die Entitäten auf Geräte verteilt:

| Gerät | Inhalt |
|---|---|
| **<Name>** (Wärmepumpe) | Temperaturen (Vorlauf, Rücklauf, Außen, Wärmequelle), Status und Betriebsart, Verdichter/Zusatzheizung, Leistung, COP, Gesamtenergie und Verdichterstunden, Leistungsbegrenzung, Anlagenwerte, Firmware, Ausstattung, Rohwerte |
| **<Name> Heizung** | Climate-Entität, Betriebsart, Sollwert, Heizkurven-Anhebung, Stufe, Gesamt-Heizung, Sperre, Mischkreise 1–3, Energie, Stunden und COP Heizen |
| **<Name> Warmwasser** | Water-Heater-Entität, Temperaturen, Betriebsart, Sollwert, Anhebung, Stufe, Sperre, Zirkulationspumpe, Extra-Warmwasser, Energie, Stunden und COP Warmwasser |
| **<Name> Kühlung** / **<Name> Pool** | nur wenn Kühlung bzw. Pool in der Ausstattung gewählt ist; Kühlung enthält die Kühl-Entitäten der Mischkreise, Pool die Pool-Sperre, Status und Energie |

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

### Abfragen

* **Gebündelte Abfragen** statt eines Requests pro Wert. Lehnt das Gerät eine Blockabfrage ab (z. B. weil ein Register
  in der Lücke fehlt), liest die Integration automatisch einzeln weiter.
* **Abgestufte Abfrageintervalle**: Messwerte jeden Zyklus (Standard 30 s), Zähler und Einstellungen seltener, Firmware
  fast nie.

## Reparaturhinweise

Die Integration meldet diese Hinweise unter *Einstellungen → System → Reparaturen*:

| Hinweis | Schweregrad | Wird ausgelöst, wenn |
|---|---|---|
| Firmware der Wärmepumpe ist veraltet | Warnung | Firmware älter als 3.92.0: Zirkulationspumpe und Extra-Warmwasser haben keine Werte. |
| Smart-Home-Schnittstelle nicht erreichbar | Fehler | Alle Abfragen sind 10 Minuten in Folge fehlgeschlagen. |
| Werte nach Verbindungsausfall geändert | Warnung | Nach einem Ausfall weichen Heizungssperre, Warmwassersperre, Heizungs-Betriebsart oder Warmwasser-Betriebsart vom zuletzt vor dem Ausfall gelesenen Wert ab. |

Die ersten beiden verschwinden von selbst, sobald ihre Ursache weg ist.

**Werte nach einem Ausfall geändert:** War die Regelung nicht erreichbar (z. B. Neustart oder Stromausfall, die
SHI-Holding-Register sind flüchtig) und meldet sich mit anderen Werten zurück, zeigt eine Warnung die alten und neuen
Werte. **Das ist nur ein Hinweis: Die Integration schreibt nie etwas zurück**, außer du schaltest
[Werte nach einem Geräte-Reset wiederherstellen](#werte-nach-einem-geräte-reset-wiederherstellen-option) ein. Verglichen wird mit der normalen Abfrage,
ohne zusätzliche Modbus-Lesezugriffe. Der Hinweis verschwindet, wenn die Werte wieder denen vor dem Ausfall entsprechen,
oder wenn du ihn schließt. Die Werte vor dem Ausfall liegen nur im Arbeitsspeicher; ein Ausfall, der einen Neustart von
Home Assistant überdauert, wird deshalb nicht bemerkt.

## Werte nach einem Geräte-Reset wiederherstellen (Option)

Die SHI vergisst alle über Modbus gesetzten Werte, wenn die Regelung neu startet, und wenn ihr Watchdog nach 10
Minuten ohne jeden Modbus-Zugriff abläuft (jeder Lesezugriff zieht ihn neu auf, das passiert also nur, solange niemand
abfragt; siehe [SHI-Watchdog](docs/firmware-3.92.3-shi-analysis.md#shi-watchdog), englisch). Die
Holding-Register lesen dann ihren Reset-Wert. Gemessen an der Referenzanlage (LWDV 91-1/3, Firmware 3.92.3): Nach zwei
Neustarts der Regelung stand die Heizungs-Betriebsart auf `aus` (Rohwert 0) statt `Sollwert`, einmal auch die
Heizungs-Stufe auf Rohwert 0 statt 2.

Unter *Optionen* sorgt **Werte nach einem Geräte-Reset wiederherstellen** (standardmäßig aus) dafür, dass die
Integration solche Werte zurückschreibt:

* **Nur eigene Werte, und nur Einstellungen.** Gemerkt wird ein Wert erst, wenn er über eine Entität dieser
  Integration (Number, Select, Climate, Water Heater) geschrieben und unverändert zurückgelesen wurde. Gemerkt werden
  nur **Betriebsart, Stufe, Offset und Sollwert** jedes Kreises (Heizung, Warmwasser, Mischkreise 1–3 Heizen und
  Kühlen, gesamt) und der Raum-Sollwert (`RESTORE_KEYS` in `const.py`). Sperren (Heizung, Warmwasser, Kühlung, Pool),
  Zirkulation, Warmwasser-Extra und die Leistungsbegrenzung werden **nie** wiederhergestellt: Die gehören live einem
  Optimierer wie dem Heat Pump Optimizer, und eine Sperre nach langem Stillstand wieder zu setzen, würde die
  Rückfallebene des Watchdogs (alles freigegeben) aushebeln. Die Betriebsarten und Sollwerte der Liste (etwa
  `cfg_heating_mode`, `cfg_heating_setpoint`, `cfg_mk1_setpoint`) werden auch dann wiederhergestellt, wenn ein
  Optimierer sie schreibt; dessen nächster Schreibzugriff gewinnt. Ein fehlgeschlagenes Schreiben oder
  ein abweichender Rücklesewert löscht den Schlüssel. Die Werte liegen je Eintrag im Speicher von Home Assistant
  (`.storage/luxtronik_shi.restore.<entry_id>`), die Wiederherstellung klappt also auch nach einem Neustart von Home
  Assistant. Wer einen Wert auf seinen neutralen Wert zurücksetzt (z. B. Betriebsart `aus`, Offset 0), dem wird das
  wie jedes andere Schreiben gemerkt – danach gibt es für diesen Wert nichts mehr wiederherzustellen.
  Abgesehen von der einmaligen Übernahme unten werden von anderen geschriebene Werte nicht gemerkt: Werte eines anderen Modbus-Clients sind nicht Sache dieser
  Integration, und was eine andere Integration über den nativen Port 8889 schreibt, sind Parameter der Regelung, keine
  über die SHI gesetzten Werte – ein Reset setzt sie nicht zurück.
* **Einmalige Übernahme der aktuellen Werte.** Wird die Option eingeschaltet (in den Optionen oder bei der ersten
  Einrichtung mit eingeschalteter Option), dient der erste vollständige Lesezyklus als Momentaufnahme und wird gemerkt,
  als hätte die Integration ihn geschrieben: jede Betriebsart, Stufe und jeder Offset der Liste, die nicht 0 lesen,
  und ein Sollwert nur, wenn die Betriebsart seines Kreises `Sollwert` liest (ein nie gesetzter Sollwert liest seinen
  Startwert, und ihn wiederherzustellen würde ihn der SHI unterstellen). Die übernommenen Schlüssel stehen im Log. Das
  passiert einmal; ein Neustart oder Neuladen bei weiter eingeschalteter Option übernimmt nichts erneut.
* **Erfordert ein Aktualisierungsintervall von höchstens 540 Sekunden.** Darüber lehnen die Optionen die
  Wiederherstellung ab, deutlich unter dem 600-Sekunden-Watchdog; ein Eintrag, der beides trotzdem hat, läuft mit
  ausgeschalteter Option (Warnung im Log).
* **Nur nach einem Ausfall.** Die Regelung setzt die SHI-Werte aus genau zwei Gründen zurück: bei einem Neustart, der
  die Verbindung trennt, und nach 10 Minuten ganz ohne Modbus-Zugriff
  ([SHI-Watchdog](docs/firmware-3.92.3-shi-analysis.md#shi-watchdog), englisch). Ein Reset kommt deshalb nur in Frage
  nach
  * fehlgeschlagenen Abfragen,
  * einer neu aufgebauten Verbindung (ein Neustart, der kürzer ist als das Abfrageintervall, kann die Verbindung
    trennen, ohne dass eine Abfrage fehlschlägt; die Integration zählt die Wiederverbindungen ihrer Modbus-Verbindung,
    ohne zusätzliche Anfragen). Das beruht auf einer **noch nicht gemessenen Annahme**: Die SHI hält die
    TCP-Verbindung zwischen den Abfragen offen, eine Wiederverbindung heißt also, dass die Regelung sie getrennt hat.
    Gibt es bei 3 der letzten 5 Abfragen eine Wiederverbindung, gilt die Annahme für diese Anlage nicht: Es wird
    einmal gewarnt, und Wiederverbindungen zählen in dieser Sitzung nicht mehr,
  * mehr als 10 Minuten seit der vorigen erfolgreichen Abfrage, während Home Assistant läuft, gemessen mit einer
    monotonen Uhr, damit ein Verstellen der Systemuhr nicht zählt, oder
  * einer Lücke von mehr als 11 Minuten seit der letzten erfolgreichen Abfrage, etwa einem langen Stillstand von Home
    Assistant (10 Minuten Watchdog plus 1 Minute, weil die Zeit der letzten Abfrage höchstens einmal pro Minute
    gespeichert wird).

  **Jede Änderung, die bei durchgehender Abfrage auftaucht, stammt von jemand anderem**: Sie wird vergessen
  (Log-Level info) und nie wiederhergestellt.
* **Alles oder nichts.** Bei einem Rücksetzen stellt die Regelung alle über die SHI gesetzten Werte auf einmal zurück:
  Betriebsarten und Stufen auf 0, Sollwerte auf ihren gespeicherten oder festen Standardwert (nie 0). Nach einem
  Ausfall, sobald jedes gemerkte Register gelesen wurde (ein bis zwei Abfragen, keine zusätzlichen Lesezugriffe), ist
  es nur dann ein Reset, wenn **jeder** gemerkte Wert seinen Reset-Wert liest: 0 bei Betriebsarten, Stufen und
  Offsets (bei Offsets ist das eine Annahme: fällt ein Offset ungleich 0 nicht auf 0 zurück, wird der Reset nicht
  erkannt und nichts überschrieben), ein beliebiger Wert ungleich 0 bei Sollwerten (oder genau der gelernte Wert, siehe unten). Dann werden alle
  abweichenden Werte wiederhergestellt, erst die Werte, die Betriebsarten zuletzt. Ist nur ein Teil zurückgesetzt,
  waren die geänderten Werte fremde Änderungen: Sie werden vergessen, und nichts wird wiederhergestellt. Eine einzige
  gemerkte Betriebsart, die nach einem Ausfall 0 liest, genügt. Beispiel: Warmwasser-Betriebsart `Sollwert` mit 54 °C
  und Heizungs-Betriebsart `Offset` mit Offset 0 – nach einem Neustart kommen beide Betriebsarten und die 54 °C zurück;
  eine Betriebsart, die `aus` war, bleibt `aus`.
* **Gelernte Reset-Werte der Sollwerte.** Nach einem bestätigten Reset speichert die Integration, auf welchen Wert
  jeder Sollwert zurückgefallen ist. Danach gilt ein Sollwert nur noch als zurückgesetzt, wenn er genau diesen Wert
  liest; ein anderer Wert heißt, dass ihn jemand geändert hat. Diese Werte sind an deiner Anlage gelernt, nicht aus
  einer Firmware-Tabelle übernommen. Verhindert ein Sollwert einen Reset nur, weil er vom gelernten Wert abweicht,
  nennt ihn eine Warnung. Nach einem Neustart mit fehlgeschlagenen Abfragen, bei dem jede gemerkte Betriebsart und
  Stufe 0 liest, wird der Reset trotzdem angenommen und der gelernte Wert ersetzt (mit Log-Eintrag). `0x7FFF`
  („nicht verfügbar“) ist nie ein Reset-Wert und wird nie gelernt. Ein gemerktes Register, das nicht mehr verfügbar
  ist, wird vergessen.
* **Gruppen.** Betriebsart, Sollwert, Offset und Stufe eines Kreises bilden eine Gruppe: Sobald einer davon fremd
  geändert wurde, wird auch die Betriebsart dieses Kreises vergessen und erst wieder wiederhergestellt, nachdem sie
  erneut über Home Assistant geschrieben wurde – so entsteht keine Kombination, die niemand eingestellt hat.
* **Keine Schreibschleifen.** Jeder Schlüssel wird pro erkanntem Reset einmal wiederhergestellt, mit Rücklesen. Eine
  Betriebsart wird nicht wiederhergestellt, wenn ein anderer Wert ihres Kreises nicht wiederhergestellt werden konnte.
  Schlägt das Schreiben fehl oder liest es einen anderen Wert zurück, wird der Schlüssel vergessen und nicht erneut
  versucht. Ein Reset, der innerhalb von 15 Minuten nach einer Wiederherstellung erneut erkannt wird, wird nicht
  wiederhergestellt. Gemerkte Werte, die älter als 24 Stunden sind (seit der letzten erfolgreichen Abfrage), werden
  beim Start der Integration verworfen. Wiederhergestellte Schlüssel stehen mit Log-Level warning im Log.

Der [Hinweis nach einem Ausfall](#reparaturhinweise) funktioniert wie bisher; mit eingeschalteter Option verschwindet er
meist mit der nächsten Abfrage, weil die Werte wieder stimmen. *Diagnose herunterladen* listet die gemerkten und
gelernten Werte, die Zahl der Wiederverbindungen und die Zeit der letzten sowie, ob Wiederverbindungen noch als
Ausfall zählen.

**Grenzen:**

* Ein falscher oder veralteter gelernter Wert (etwa gelernt, während ein anderer Client den Sollwert während eines
  Resets geändert hat) kann Wiederherstellungen blockieren, bis zu einem Neustart mit fehlgeschlagenen Abfragen, bei
  dem jede gemerkte Betriebsart und Stufe 0 liest. Option aus- und wieder einschalten löscht alle gelernten Werte.

* Ändert ein anderer Modbus-Client rund um einen Ausfall Werte so, **dass zufällig jeder gemerkte Wert seinen
  Reset-Wert liest** (etwa indem er die einzige gemerkte Betriebsart ausschaltet), sieht das genau wie ein Reset aus und
  wird über diese Änderung hinweg wiederhergestellt. **Lass die Option aus, wenn ein anderes System diese Register
  ebenfalls schreibt.**
* Solange der Reset-Wert eines Sollwerts noch nicht gelernt ist, gilt jeder Wert ungleich 0 als zurückgesetzt. Ein
  Sollwert, den jemand anderes während eines Ausfalls ändert, kann dann über diese Änderung hinweg wiederhergestellt
  werden, wenn alles andere ebenfalls zurückgesetzt ist.
* Eine Wiederherstellung schreibt ohne Zutun auf die Wärmepumpe. Schreibzugriffe aus Home Assistant und eine
  Wiederherstellung laufen nie gleichzeitig; ein Schreibzugriff während einer Wiederherstellung wartet und wird danach
  ausgeführt.

## Diagnose

Unter *Einstellungen → Geräte & Dienste → Luxtronik SHI* bietet das ⋮-Menü des Eintrags **Diagnose herunterladen**.
Die Datei enthält die Version von Integration und Home Assistant, die gewählte Ausstattung und die
Ausstattungsmerkmale, die Firmware, die zuletzt abgefragten Registerwerte (roh und umgerechnet) und bei eingeschalteter
[Wiederherstellung](#werte-nach-einem-geräte-reset-wiederherstellen-option) die gemerkten Werte. Host-Adresse,
MAC-Adresse sowie Unique-ID und Titel des Eintrags werden unkenntlich gemacht. Die Datei entsteht aus der letzten
Abfrage, ohne zusätzliche Modbus-Lesezugriffe. Bitte an Fehlermeldungen anhängen.

## Beta-Versionen

Vorabversionen (`X.Y.Z-beta.N`) werden als GitHub-Pre-Releases veröffentlicht. Zum Testen in HACS die Integration
öffnen, **Erneut herunterladen** (*Redownload*) wählen und **Beta-Versionen anzeigen** (*Show beta versions*)
aktivieren. Beta-Versionen können sich zwischen den Releases ändern und sind zum Testen gedacht. Wer die Option nicht
aktiviert, ist nicht betroffen und erhält nur stabile Versionen.

## Zusammenspiel mit der nativen Luxtronik-Integration (Port 8889)

Beide Integrationen können nebeneinander laufen, sollten aber klar getrennt werden:

* **luxtronik_shi (diese Integration):** der einzige Weg, der **schreibt** (Sperren, Sollwerte, Betriebsarten, Zirkulationspumpe)
  und die Werte, die ein Planer wie der Heat Pump Optimizer braucht.
* **Native Luxtronik-Integration (Entitäten `luxtronik_<seriennummer>_*`):** nur **Diagnose** (zusätzliche Messwerte,
  Parameter, Fehlerspeicher). Ihre Schreib-Entitäten (select, climate, switch, number) werden deaktiviert, damit nicht zwei
  Integrationen dieselbe Regelung beschreiben. Diagnose-Entitäten werden einzeln bei Bedarf aktiviert.
* Einstellungen, die nur das native Protokoll bietet (z. B. die Thermische Desinfektion/Legionellenschutz), werden nicht von
  dieser Integration geändert. Das bleibt eine bewusste Entscheidung des Betreibers.

<details>
<summary><b>Umstieg von einer bestehenden YAML-<code>modbus:</code>-Konfiguration</b></summary>

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

**`tools/gen_yaml.py`** erzeugt aus der Registerliste die gleichwertige YAML-Konfiguration. Es ist ein
**Legacy-Werkzeug** für alle, die bewusst bei YAML bleiben, wird nicht mehr produktiv eingesetzt und nicht gegen
Änderungen der Registerliste getestet.

</details>

## Quellen der Registerkarte

* [Bouni/python-luxtronik](https://github.com/Bouni/python-luxtronik), Modul `luxtronik/shi` und
  `luxtronik/definitions/{inputs,holdings}.py` (MIT): Adressen, Datentypen, Wertebereiche, Firmware-Stand.
  Laut dieser Quelle sind die SHI-Holding-Register **flüchtig** und werden beim Neustart der Regelung
  zurückgesetzt – anders als die dauerhaften Einstellungen der Regelung.
* Messungen an der Referenzanlage (LWDV 91-1/3, Firmware 3.92.3), siehe unten.
* Die DHCP-Erkennungsmerkmale (MAC-Präfixe, Hostname `wp-novelan`) stammen aus
  [BenPru/luxtronik](https://github.com/BenPru/luxtronik) (MIT).
* Nicht in python-luxtronik enthalten und daher nur durch Beobachtung belegt: die Ausstattungs-Register
  (Discrete Inputs 10000–10011), Firmware-Haupt-/Nebenversion (10401/10402, stimmt mit der Anzeige der Regelung
  überein) und die Deutung von 10404/10406/10408 als Betriebsstunden.
* Vollständige Tabelle aller Register (Typ, Adresse, Datentyp, Skalierung, Einheit, Bereich): [docs/registers.md](docs/registers.md).

## Hinweise und Grenzen

* **Werte können nach einem Neustart der Regelung zurückfallen.** Die SHI-Holding-Register sind flüchtig. Nach
  Stromausfall oder Neustart der Regelung können über diese Integration geschriebene Werte, etwa die Heizungs- oder
  Warmwassersperre, auf den Standardwert der Regelung zurückfallen, z. B. `aus`. Standardmäßig schreibt die
  Integration sie **nicht** zurück; die Option dafür steht unter
  [Werte nach einem Geräte-Reset wiederherstellen](#werte-nach-einem-geräte-reset-wiederherstellen-option). Lief Home Assistant während des Ausfalls, zeigt ein [Reparaturhinweis](#reparaturhinweise), was sich geändert
  hat. Nach einem Stromausfall Sperren und Betriebsart prüfen oder Automatisierung bzw. Planer die Werte erneut
  schreiben lassen.
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
* **Statusbits VD2, ZWE2, ZWE3:** Die Binärsensoren `heatpump_vd2_status`, `heatpump_zwe2_status` und
  `heatpump_zwe3_status` stammen aus python-luxtronik (Bit 1, 3 und 4 von Register 10000) und sind standardmäßig
  deaktiviert. VD2 und ZWE2 zeigen dieselben Bits wie *Verdichter 2* und *Zusatzheizung 2*; ZWE3 gibt es laut
  python-luxtronik ab Firmware 3.90.1.
* **Umbenannte Rohwerte (10109, 10110, 10112):** `raw_10109` heißt jetzt `outside_temp_average` (Außen Mittelwert, °C),
  `raw_10110` heißt jetzt `heat_source_input` (Wärmequelle Eintritt, °C) und
  `raw_10112` heißt `max_flow_temp` (Vorlauf Maximum, °C, standardmäßig deaktiviert). Die Integration überträgt die
  vorhandenen Entitäten beim Start, Entity-IDs, Verlauf und Einstellungen bleiben erhalten. Es ändern sich nur das Ende
  der Unique-ID und der Name; Verweise auf die alte `raw_*`-Unique-ID müssen angepasst werden. Langzeitstatistik gibt es
  für 10112 erst ab jetzt (vorher ohne Einheit).
* **Undokumentierte Rohwerte:** Register, die python-luxtronik mit unbekannter Funktion führt (Inputs 10352, 10353,
  10410–10413, 10416, 10417, 10500–10502 und Holding 10060), gibt es als deaktivierte Diagnose-Sensoren `raw_<Adresse>`.
  Sie werden nur gelesen (nie geschrieben) und selten abgefragt.
* **Pool-Sperre und Leistungsbegrenzung:** Der Schalter für die Pool-Sperre (Register 10053) existiert nur mit gewähltem
  Pool. Die Leistungsbegrenzung besteht aus einer Auswahl für den Modus (keine / weich / hart, Register 10040) und einer
  Zahl für den Wert (0–30 kW, Register 10041).
* **Mischkreis-Ventil:** Das SHI liefert nur Temperaturen und Betriebsart/Sollwerte der Mischkreise, keine Ventilstellung und
  keine Umschaltung „Ventil immer offen". Das wird in der Regelung am Gerät (Installateur-Ebene) eingestellt.
* **Heizungsumwälzpumpen** (HUP/Heizkreispumpe) sind über das SHI nicht steuerbar, nur die Zirkulationspumpe des Warmwassers.
  Darüber hinaus bietet das native Luxtronik-Protokoll (Port 8889, z. B. die Integration von BenPru) deutlich mehr Parameter.
* Bei Warmwasser-Betriebsart 0 („Aus") ignoriert die Wärmepumpe den Sollwert; das tatsächliche Ziel steht im Sensor *Warmwasser Soll*.
* Schreibzugriffe wirken direkt auf die Wärmepumpe. Wer Heizungs-/Warmwassersperre oder Offset automatisiert, sollte
  das mit Bedacht tun.

## Entwicklung

```bash
python -m venv venv && . venv/bin/activate
pip install -r requirements_test.txt pytest-timeout ruff
ruff check . && pytest --timeout=60
```

Die Tests laufen gegen einen kleinen simulierten Modbus/TCP-Server (`tests/fake_shi.py`), der wie die echte SHI nur
vorhandene Register beantwortet. Die Übersetzungen werden aus der Registerliste erzeugt:
`python tools/gen_translations.py`. Die Entity-Schlüssel sind ein Vertrag (`tests/test_contract.py`). Hinweise für
Beiträge stehen in [CONTRIBUTING.md](CONTRIBUTING.md), die Arbeitsregeln in [CLAUDE.md](CLAUDE.md), die Versionierung
in [CHANGELOG.md](CHANGELOG.md).

Releases entstehen automatisch: Landet eine Versionserhöhung auf `main` und ist der Workflow *Validate* (hassfest,
HACS-Action, Tests) grün, setzt ein GitHub-Actions-Workflow den Tag auf genau diesen Commit und veröffentlicht das
Release mit dem passenden CHANGELOG-Abschnitt als Text.

Langfristiges Ziel: eine Bibliothek auf PyPI auslagern und die Integration im Home-Assistant-Core einreichen.

## Haftung

Inoffiziell, keine Verbindung zu alpha innotec oder Luxtronik. Produktnamen dienen nur zur Beschreibung der
Kompatibilität. Nutzung auf eigene Verantwortung.
