# Luxtronik 2.1 – Smart Home Interface (SHI, Modbus/TCP) – Vollanalyse Firmware V3.92.3

Gerät: alpha innotec LWDV 91-1/3, Luxtronik 2.1, Firmware `wp2reg-V3.92.3_260513_3a381baa`, Binary `bin/Controller`
(ARM 32-bit LE, EABI5, C++, stripped, 2646 dynamische Symbole). Analyse zur Herstellung der Interoperabilität der
eigenen Integration `Bankaifan/ha-luxtronik-shi` (§ 69e UrhG). Festgehalten werden ausschließlich Fakten
(Adressen, Typen, Grenzen, Texte, Funktionsadressen als Beleg); kein dekompilierter Code.

Bewertung: **belegt** = direkt aus Code/Daten gelesen · **wahrscheinlich** = aus Code geschlossen, Beleg lückenhaft · **offen** = nicht bestimmt.
Adressen sind virtuelle Adressen im Binary (`FUN_…`). Datei-Offset = VA − 0x8000 (.text/.rodata) bzw. VA − 0x10000 (.data).

Stand 2026-11-08. Begleitdatei: [`firmware-3.92.3-registers.de.csv`](firmware-3.92.3-registers.de.csv) (alle 131 Register/Bits mit Beleg und Grad; englische Fassung: [`firmware-3.92.3-registers.csv`](firmware-3.92.3-registers.csv)). Die Analyseskripte (Ghidra/Capstone) und das Arbeitsprotokoll gehören nicht zu diesem Repository.



> Englische Fassung: [firmware-3.92.3-shi-full-analysis.md](firmware-3.92.3-shi-full-analysis.md). Registertabelle als CSV: [firmware-3.92.3-registers.de.csv](firmware-3.92.3-registers.de.csv) (deutsch) und [firmware-3.92.3-registers.csv](firmware-3.92.3-registers.csv) (englisch). Diese Datei ist die deutsche Fassung der Analyse; der folgende Abschnitt und die Hinweise zu Code-Fragmenten stammen nicht aus der Analyse selbst, sondern ordnen sie in die Dokumentation des Repositorys ein.

### Einordnung in die bestehende Dokumentation

Dieses Dokument erweitert [firmware-3.92.3-shi-analysis.md](firmware-3.92.3-shi-analysis.md) (Mechanik, Watchdog, verzögerte Schreibzugriffe, Fehler 816) und [firmware-3.92.3-register-meanings.md](firmware-3.92.3-register-meanings.md) (Registerbedeutungen, Messungen); beide sind englisch und bleiben unverändert gültig, soweit unten nichts anderes steht. Wo eine frühere Aussage durch diese Analyse überholt oder präzisiert wird, steht dort ein Hinweis; gelöscht wurde nichts.

* **10113:** `register-meanings` deutet das Register als berechneten Heizungs-Vorlaufsollwert (Rücklaufsoll plus gleitender Mittelwert der Spreizung, Zuweisung in `0x0019ac68`). Diese Analyse liest den Firmware-Text von t0/0x67 als „TVL calc max“ (berechneter maximaler Vorlauf) und ersetzt die frühere Deutung „Vorlauf-Soll Heizen (berechnet)“ durch diesen Text. Beide Aussagen nennen dieselbe Funktion `0x0019ac68`; die gemessenen Werte (Rohwert 253 bei Rücklaufsoll 20,0 und mittlerer Spreizung 5,3 K; 25,7 °C bei Rücklaufsoll 20,0) widersprechen keiner von beiden. Ob das Register ein Sollwert oder eine Obergrenze ist, entscheidet keine Messung. Beide Aussagen bleiben stehen.
* **10412:** „SW“ steht für Schwimmbad (Firmware-Text „Schwimmbad“, Sichtbarkeit `ID_Visi_Bst_BStdSW`). Die frühere Vermutung „2-Stunden-Einheiten oder ein Mittelwert“ ist durch die Annahme ersetzt, dass der Divisor 7200 eine Abweichung im SHI-Code ist (Stunden/2 auf dem Draht; wahrscheinlich, ohne Pool nicht messbar).
* **10350 (VBO):** Der Firmware-Text lautet „Ventil.-BOSUP / VBO“. Die Langform von FP steht weiterhin nicht in der Firmware.
* **Watchdog, offener Punkt „Default je Sollwert-Register“:** beantwortet durch §3.4 und §4. t2-Sollwerte kehren auf einen festen Default zurück (350/400/200/300), der t1-Parameter 10060 auf seinen persistierten Wert.
* **Stufen (`_LEVELS`):** Stufe 1 und 2 nutzen denselben Parameter („Erhöhung“), Stufe 3 den Parameter „Absenkung“; „Increased2“ aus python-luxtronik ist in der Firmware kein eigener Wert (§3.1, §5 Punkt 3).
* **10060:** Wertebereich weiterhin offen (§3.3, §6); neu ist die Verfügbarkeitsbedingung (RBE vorhanden, verbunden, Einflussfaktor größer 0).
* **Neu gegenüber beiden Dokumenten:** Revert bei Schreiben außerhalb des Wertebereichs (§1.4, §4), Wertebereiche aller Holdings (§2.1, §5 Punkt 4), Gesamt-Modus 10065–10067, Parameter „Enable SHI“, Discrete Inputs (§2.3), Wortreihenfolge der 32-Bit-Zähler, Sichtbarkeits-IDs.

Zur Schreibweise: Die Analyse hält Funktionsadressen (`FUN_…`, `0x…`) als Beleg fest, aber keinen dekompilierten Code. Einzelne Aufrufe und Zuweisungen aus der Arbeitsfassung sind hier in Worten wiedergegeben.

---

## 1. Überblick: Mechanik des SHI

### 1.1 Objektaufbau (belegt)

* Konstruktor `ModBus_TCP::SmartHomeInterface` = `FUN_000dc298`: Basisoffset **10000** für beide Tabellen (gesetzt über `FUN_000d5b00`); baut zwei Zeiger-Arrays:
  `FUN_000d8014` → Holdings (Objekt-Offset +8, 0x49 = 73 Slots) und `FUN_000d95d4` → Inputs (Offset +0x12c, 0x1f7 = 503 Slots). Slot = Adresse − 10000; leerer Slot → Modbus-Exception 2.
* Dispatcher `FUN_000d9298` (Parameter: Startadresse, Anzahl, Puffer, Lese-/Schreibkennung, Array-Basis, Array-Länge): ruft **zuerst** `FUN_000de744` (Wächter-Re-arm, §4), dann je Register `avail()` (vtable+8).
  Nicht verfügbar → Lesewert **0x7FFF**, Schreiben wird still übersprungen. Verfügbar → `get()` (vtable+0xc) bzw. Schreiben via `FUN_000dc76c` → `set()` (vtable+0x14).
* **Discrete Inputs (FC 2)** gibt es ebenfalls: Handler `FUN_000db9b0` (vtable-Slot 4 der SHI), Adressen 10000–10011 (Tabelle §2.3). Ab Adresse 10012 → Exception 2. Coils (FC 1/5) sind nicht implementiert (kein Handler in der vtable 0x9c3510).
* **Vorzeichen** (`FUN_000dc76c`): Objektfeld +4 = 0 → INT16, 1 → UINT16. Register-Konstruktor `FUN_000dd2e8` (Parameter: GDI-Item aus ID und Tabelle, Vorzeichen, Divisor).
* **Divisor** (Getter `FUN_000dfbb4`): Wire = round(intern / divisor) für divisor ≥ 2, sonst intern. Der Wire-Wert ist bereits der Ingenieurswert (0,1 °C; h; 0,1 kWh …).
* **Verfügbarkeit** `avail()` = `FUN_000dfc98`: holt die *Visibility-ID* des gebundenen GDI-Items (`FUN_00425c10`) und prüft die Sichtbarkeitstabelle `FUN_003d9e0c` (Byte-Array `DAT_00a19464`; ID −1 = immer, −2 oder 0x191 = nie).
  **Neu:** Firmware-Visibility-ID + 2 = python-luxtronik-Visibility-Index (`visibilities.py`): Firmware 0 = `ID_Visi_Heizung` (Index 2), 5 = `ID_Visi_MK1` (7), 0xd1 = `ID_Visi_MK3` (211), 0xf8 = `ID_Visi_Solar` (250), 0x12a = `ID_Visi_RBE` (300) … an über 40 Items konsistent → **belegt**. Damit ist für jedes Register bekannt, welche Ausstattung es sichtbar macht (Spalte „Sichtbarkeit“).
* Klassen (vtables): `Register` 0x9c3678; `Register::Bound` 0x9c36c8 (alle normalen Register); `Register::Fixed` 0x9c3698 (Konstante, Konstruktor `FUN_000dc81c` nimmt den Wert, immer verfügbar);
  `Register::MultiByte` 0x9c3640 (32 Bit über zwei Register, High-Word zuerst; `FUN_000d94b4` erzeugt zwei Teilregister à 0x14 Bytes); `RBE_RoomTemperatureSetpointRegister` 0x9c3780 (nur 10060).

### 1.2 GDI – die internen Datenpunkte (belegt)

Jedes Register ist an ein GDI-Item `t<Tabelle>/<ID>` gebunden (Resolver `FUN_0042bf8c`). Drei Tabellen:

* **t0** (Handle-Ctor `FUN_0042c6ec`): Laufzeit-/Messwerte. Registrierung mit **Variablenadresse, Text-ID, Visibility-ID, Format** in `FUN_0009ab8c` (Temperaturen), `FUN_0008bef8` (Ausgänge), `FUN_0009833c` (Eingänge), `FUN_0008b908` (Energiezähler), `FUN_00096648` (Status), `FUN_0008d0a8` (SHI-eigene Items) u. a.
  Die Variablen sind exportierte Symbole (`Temperatur_TVL`, `HUPout`, `Zaehler_BetrZeitWP` …) und entsprechen den `ID_WEB_*`-Namen von python-luxtronik.
* **t1** (`FUN_0042c76c`): persistierte **Parameter**. Die t1-ID **ist** der python-luxtronik-Parameterindex (`parameters.py`): t1/87 = `ID_Einst_TRBegr_akt`, t1/979 = `ID_Einst_Minimale_Ruecklaufsolltemperatur`, t1/973 = `ID_Einst_BW_max`, t1/1072–1077 = `ID_Einst_MinVLMK1..3/MaxVLMK1..3`, t1/1148 = `HEATING_TARGET_TEMP_ROOM_THERMOSTAT` = `RBE_Raumtemperatur_Soll`, t1/668/728/729/730/859/882 = Betriebsstundenzähler, t1/1146/1147 = `ExtraDHW::temperatureSetpoint/durationSetpoint` (in python-luxtronik noch `Unknown_Parameter_1146/1147`).
* **t2** (`FUN_0042c7ec`): die **flüchtigen SHI-Schreibwerte**, 0x29 = 41 Items, angelegt in `FUN_0008d0a8` (IDs 2–0x28) und `FUN_0009bab4` (IDs 0, 1). Dort stehen **Grenzen** (`GDI::Boundaries::Range`, angelegt über `FUN_004220b4` mit Minimum, Maximum und Schrittweite; Prüfung `FUN_00421f2c`: der Wert liegt zwischen Minimum und Maximum und sein Abstand zum Minimum ist ein ganzzahliges Vielfaches der Schrittweite; Quelle `Modules/GDI/Boundaries/Range.cpp`) und **Enum-Listen** („Setpoint/Offset/Level“, „No limit/Soft limit/Hard limit“).
  Boot-Defaults aller t2-Items: `FUN_00087e9c` (Tabelle in §3.4), gesetzt in `FUN_0009da20`.

### 1.3 Texttabelle (neu, belegt)

`.data`, Datei-Offset 0x9ce58c (VA 0x9de58c): pro Text-ID 24 Zeiger (Sprachen; 0 = Deutsch, 1 = Englisch), Zeile 0 = Sprachnamen, Zeile n+1 = Text-ID n. `scripts/texts.py` → 1372 Texte. Damit sind die Anzeigenamen aller GDI-Items auflösbar (Spalte „Firmware-Text“).

### 1.4 Schreibpfad (belegt)

`Register::Bound::set()` (`FUN_000dfa6c`) erzeugt ein Lambda (`FUN_000defd4`; Client-ID = CRC32 über die Peer-Adresse) und führt es im Applikationsthread aus (`FUN_000df0bc`):

1. `smart_home_interface::write_log::update` (`FUN_00187314`, aufgerufen mit Datenpunkt, Quelle 6 = SHI und Client-ID): Schreibquellen-Log pro Datenpunkt; > 2 Schreiber in 3600 s → Fehlerindex 0x6F (816), Schreibvorgang wird verworfen (Rückgabe 0, **keine** Modbus-Exception).
2. Bereichsprüfung `FUN_0042486c` → `Range::isValid` (`FUN_00421f2c`). **Ungültiger Wert → Revert `FUN_000881e0`: das Item wird auf Default/persistierten Wert zurückgesetzt**, nicht auf den vorherigen Wert; Rückgabe 0, keine Modbus-Exception. Beispiel: 10001 = 900 (90 °C) setzt 10001 auf 350 zurück; 10000 = 5 setzt 10000 auf 0.
3. Gültig → `GDI::Item::set(value, source 6, deferred 0)` (`FUN_004270bc`); für t2 5/6/7/0x27 (WW-Gruppe) über die Pending-Map (§3.2). Schreiben des bereits gespeicherten Werts ist ein No-op (und löscht einen anstehenden Pending-Eintrag).

---

## 2. Vollständige Registertabelle

Spalten „Min/Max“ und „Default“ sind interne Werte = Wire-Werte (Divisor 1). „GDI“ = Tabelle/ID, „Symbol“ = exportierte Firmware-Variable, „Sichtbarkeit“ = Firmware-Visibility-ID mit python-luxtronik-Name (Index +2). Alle Einträge aus den Buildern `FUN_000d8014`/`FUN_000d95d4` (Parser `scripts/parse_builder.py`), Grenzen aus `FUN_0008d0a8`. Vollständige Belegspalten in der CSV; dort bedeutet `fn_<Adresse>.c` in der Belegspalte die Funktion an dieser Adresse.

### 2.1 Holding-Register (FC 3/6/16, alle schreibbar, 1 Wort, Divisor 1)


| Adresse | Typ | Min | Max | Default | GDI | Symbol | Firmware-Text (de/en) | Sichtbarkeit | Bedeutung | Grad |
|---|---|---|---|---|---|---|---|---|---|---|
| 10000 | UINT16 |  |  | 0 | t2/0x2 (2) |  |  | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Heizung: SHI-Modus | belegt |
| 10001 | UINT16 | 150 | 750 | 350 | t2/0x3 (3) |  |  | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Heizung: Rücklauf-Sollwert | belegt |
| 10002 | INT16 | -200 | 200 | 0 | t2/0x4 (4) |  |  | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Heizung: Rücklauf-Offset | belegt |
| 10003 | UINT16 | 0 | 3 | 0 | t2/0x23 (35) |  |  | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Heizung: Stufe | belegt |
| 10005 | UINT16 |  |  | 0 | t2/0x5 (5) |  |  | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Warmwasser: SHI-Modus | belegt |
| 10006 | UINT16 | 300 | 750 | 400 | t2/0x6 (6) |  |  | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Warmwasser: Sollwert | belegt |
| 10007 | INT16 | -200 | 200 | 0 | t2/0x7 (7) |  |  | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Warmwasser: Offset | belegt |
| 10008 | UINT16 | 0 | 3 | 0 | t2/0x27 (39) |  |  | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Warmwasser: Stufe | belegt |
| 10010 | UINT16 |  |  | 0 | t2/0x8 (8) |  |  | 5 (python-luxtronik Visi 7: ID_Visi_MK1) | MK1 Heizen: SHI-Modus | belegt |
| 10011 | UINT16 | 200 | 650 | 350 | t2/0x9 (9) |  |  | 5 (python-luxtronik Visi 7: ID_Visi_MK1) | MK1 Heizen: Vorlauf-Sollwert | belegt |
| 10012 | INT16 | -50 | 50 | 0 | t2/0xa (10) |  |  | 5 (python-luxtronik Visi 7: ID_Visi_MK1) | MK1 Heizen: Offset | belegt |
| 10013 | UINT16 | 0 | 3 | 0 | t2/0x24 (36) |  |  | 5 (python-luxtronik Visi 7: ID_Visi_MK1) | MK1 Heizen: Stufe | belegt |
| 10015 | UINT16 |  |  | 0 | t2/0xb (11) |  |  | 398 (python-luxtronik Visi 400: unbekannt) | MK1 Kühlen: SHI-Modus | wahrscheinlich |
| 10016 | UINT16 | 50 | 250 | 200 | t2/0xc (12) |  |  | 398 (python-luxtronik Visi 400: unbekannt) | MK1 Kühlen: Sollwert | wahrscheinlich |
| 10017 | INT16 | -50 | 50 | 0 | t2/0xd (13) |  |  | 398 (python-luxtronik Visi 400: unbekannt) | MK1 Kühlen: Offset | wahrscheinlich |
| 10020 | UINT16 |  |  | 0 | t2/0xe (14) |  |  | 6 (python-luxtronik Visi 8: ID_Visi_MK2) | MK2 Heizen: SHI-Modus | belegt |
| 10021 | UINT16 | 200 | 650 | 350 | t2/0xf (15) |  |  | 6 (python-luxtronik Visi 8: ID_Visi_MK2) | MK2 Heizen: Vorlauf-Sollwert | belegt |
| 10022 | INT16 | -50 | 50 | 0 | t2/0x10 (16) |  |  | 6 (python-luxtronik Visi 8: ID_Visi_MK2) | MK2 Heizen: Offset | belegt |
| 10023 | UINT16 | 0 | 3 | 0 | t2/0x25 (37) |  |  | 6 (python-luxtronik Visi 8: ID_Visi_MK2) | MK2 Heizen: Stufe | belegt |
| 10025 | UINT16 |  |  | 0 | t2/0x11 (17) |  |  | 399 (python-luxtronik Visi 401: unbekannt) | MK2 Kühlen: SHI-Modus | wahrscheinlich |
| 10026 | UINT16 | 50 | 250 | 200 | t2/0x12 (18) |  |  | 399 (python-luxtronik Visi 401: unbekannt) | MK2 Kühlen: Sollwert | wahrscheinlich |
| 10027 | INT16 | -50 | 50 | 0 | t2/0x13 (19) |  |  | 399 (python-luxtronik Visi 401: unbekannt) | MK2 Kühlen: Offset | wahrscheinlich |
| 10030 | UINT16 |  |  | 0 | t2/0x14 (20) |  |  | 209 (python-luxtronik Visi 211: ID_Visi_MK3) | MK3 Heizen: SHI-Modus | belegt |
| 10031 | UINT16 | 200 | 650 | 350 | t2/0x15 (21) |  |  | 209 (python-luxtronik Visi 211: ID_Visi_MK3) | MK3 Heizen: Vorlauf-Sollwert | belegt |
| 10032 | INT16 | -50 | 50 | 0 | t2/0x16 (22) |  |  | 209 (python-luxtronik Visi 211: ID_Visi_MK3) | MK3 Heizen: Offset | belegt |
| 10033 | UINT16 | 0 | 3 | 0 | t2/0x26 (38) |  |  | 209 (python-luxtronik Visi 211: ID_Visi_MK3) | MK3 Heizen: Stufe | belegt |
| 10035 | UINT16 |  |  | 0 | t2/0x17 (23) |  |  | 400 (python-luxtronik Visi 402: unbekannt) | MK3 Kühlen: SHI-Modus | wahrscheinlich |
| 10036 | UINT16 | 50 | 250 | 200 | t2/0x18 (24) |  |  | 400 (python-luxtronik Visi 402: unbekannt) | MK3 Kühlen: Sollwert | wahrscheinlich |
| 10037 | INT16 | -50 | 50 | 0 | t2/0x19 (25) |  |  | 400 (python-luxtronik Visi 402: unbekannt) | MK3 Kühlen: Offset | wahrscheinlich |
| 10040 | UINT16 |  |  | 0 | t2/0x1a (26) |  | LPC Modus / LPC mode | immer (−1) | Leistungsbegrenzung: Modus (LPC) | belegt |
| 10041 | UINT16 | 0 | 300 | 300 | t2/0x1b (27) |  | PC Limit / PC limit | immer (−1) | Leistungsbegrenzung: Grenzwert | belegt |
| 10050 | UINT16 |  |  | 0 | t2/0x1e (30) |  | Sperre Heizung / Heating blocked | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Sperre Heizung | belegt |
| 10051 | UINT16 |  |  | 0 | t2/0x1f (31) |  | Sperre Warmwasser / DHW blocked | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Sperre Warmwasser | belegt |
| 10052 | UINT16 |  |  | 0 | t2/0x1c (28) |  | Sperre Kühlung / Cooling blocked | immer (−1) | Sperre Kühlung | belegt |
| 10053 | UINT16 |  |  | 0 | t2/0x1d (29) |  | Sperre Schwimmbad / Pool blocked | immer (−1) | Sperre Schwimmbad | belegt |
| 10060 | UINT16 |  |  |  | t1/0x47c (1148) | RBE_Raumtemperatur_Soll | Raumtemperatur Soll / desired room temp. | 374 (python-luxtronik Visi 376: Unknown_Visibility_376) | Raumtemperatur-Sollwert (RBE) | belegt |
| 10065 | UINT16 |  |  | 0 | t2/0x20 (32) |  |  | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Gesamt (Overall): SHI-Modus | belegt |
| 10066 | INT16 | -50 | 50 | 0 | t2/0x21 (33) |  |  | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Gesamt: Offset | belegt |
| 10067 | UINT16 | 0 | 3 | 0 | t2/0x22 (34) |  |  | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Gesamt: Stufe | belegt |
| 10070 | UINT16 |  |  | 0 | t2/0x28 (40) |  | Zirkulation / secondary return | 8 (python-luxtronik Visi 10: ID_Visi_Zirkulation) | Zirkulationspumpe | belegt |
| 10071 | UINT16 |  |  | 0 | t2/0x1 (1) |  | Extra Warmwasser / Extra DHW | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Extra Warmwasser | belegt |

Modus-Enum (alle `*_mode`, Visibility-abhängig): 0 = kein Einfluss, 1 = Sollwert, 2 = Offset, 3 = Stufe (Texte `FUN_0008d0a8`: "Setpoint", "Offset", "Level"; Grenzen für die Modus-Items sind Enum-Listen ohne Range-Objekt).
Stufe (`*_level`, Range 0..3): 0 = Normal, 1 und 2 = **Erhöhung** (beide nutzen denselben Parameter „Erhöhung %1“), 3 = **Absenkung** (Parameter „Absenkung %1“); s. §3.1.
Sperren (10050–10053) und Schalter (10070/10071): Enum 0/1 (Texte 0x4fe-Gruppe: „Sperre Heizung/Warmwasser/Kühlung/Schwimmbad“, „Zirkulation“, „Extra Warmwasser“); kein Range-Objekt, jeder Wert ≠ 0 wirkt als 1 (`FUN_00064588` wird je Konsument auf „ungleich 0“ bzw. „gleich 1“ geprüft, s. CSV).

### 2.2 Input-Register (FC 4, nur lesen)


| Adresse | Klasse | Typ | Divisor | Fix | GDI | Symbol | Firmware-Text (de/en) | Sichtbarkeit | Bedeutung | Grad |
|---|---|---|---|---|---|---|---|---|---|---|
| 10000 | Register | UINT16 | 1 |  | t0/0x55 (85) |  | Heat generator status | immer (−1) | Status Wärmeerzeuger (Bitmaske) | wahrscheinlich |
| 10002 | Register | UINT16 | 1 |  | t0/0x11 (17) |  | Betriebszustand / operation mode | immer (−1) | Betriebszustand | belegt |
| 10003 | Register | UINT16 | 1 |  | t0/0x2d (45) |  | Status Heizung / Status Heating | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Status Heizung | belegt |
| 10004 | Register | UINT16 | 1 |  | t0/0x2e (46) |  | Status Warmwasser / Status DHW | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Status Warmwasser | belegt |
| 10006 | Register | UINT16 | 1 |  | t0/0x2f (47) |  | Status Kühlung / Status Cooling | 3 (python-luxtronik Visi 5: ID_Visi_Kuhlung) | Status Kühlung | belegt |
| 10007 | Register | UINT16 | 1 |  | t0/0x30 (48) |  | Status Schwimmbad / Status Pool | 228 (python-luxtronik Visi 230: ID_Visi_Bst_BStdSW) | Status Schwimmbad | belegt |
| 10100 | Register | UINT16 | 1 |  | t0/0x1 (1) | Temperatur_TRL | Rücklauf / return | 22 (python-luxtronik Visi 24: ID_Visi_Temp_Rucklauf) | Rücklauf-Ist (Temperatur_TRL) | belegt |
| 10101 | Register | UINT16 | 1 |  | t0/0x2 (2) | Sollwert_TRL_HZ | Rückl.-Soll / return target | 23 (python-luxtronik Visi 25: ID_Visi_Temp_RL_Soll) | Rücklauf-Soll (Sollwert_TRL_HZ) | belegt |
| 10102 | Register | UINT16 | 1 |  | t0/0x3 (3) | Temperatur_TRL_ext | Rückl.-Extern / return external | 24 (python-luxtronik Visi 26: ID_Visi_Temp_Ruecklext) | Rücklauf extern | belegt |
| 10103 | Register | INT16 | 1 |  | t1/0x57 (87) |  | Rückl.-Begr. / return temp. limit. | 92 (python-luxtronik Visi 94: ID_Visi_EinstTemp_RucklBegr) | Rücklauf-Begrenzung (Einst_TRBegr) | belegt |
| 10104 | Register | INT16 | 1 |  | t1/0x3d3 (979) |  | Min. Rückl.Solltemp. / min return targ.temp | 295 (python-luxtronik Visi 297: ID_Visi_Einst_Minimale_Ruecklaufsolltemperatur) | Min. Rücklauf-Solltemperatur | belegt |
| 10105 | Register | UINT16 | 1 |  | t0/0x0 (0) | Temperatur_TVL | Vorlauf / flow | 21 (python-luxtronik Visi 23: ID_Visi_Temp_Vorlauf) | Vorlauf-Ist (Temperatur_TVL) | belegt |
| 10106 | Register | INT16 | 1 |  | t0/0x29 (41) | RBE_Raumtemperatur_Ist | Raumtemperatur Ist / current room temp. | 298 (python-luxtronik Visi 300: ID_Visi_RBE) | Raumtemperatur Ist (RBE) | belegt |
| 10107 | Register | INT16 | 1 |  | t0/0x57 (87) |  | Heating demand border | immer (−1) | Heizung Anforderungsgrenze ("Heating demand border") | belegt |
| 10108 | Register | INT16 | 1 |  | t0/0x5 (5) | Temperatur_TA | Außentemperatur / outdoor temp. | 26 (python-luxtronik Visi 28: ID_Visi_Temp_Aussent) | Außentemperatur | belegt |
| 10109 | Register | INT16 | 1 |  | t0/0x27 (39) | Mitteltemperatur | Mitteltemperatur / outdoor temp. ø | 182 (python-luxtronik Visi 184: ID_Visi_Mitteltemperatur) | Außentemperatur Mittelwert | belegt |
| 10110 | Register | INT16 | 1 |  | t0/0x8 (8) | Temperatur_TWE | Wärmequelle-Ein / heat source inlet | 29 (python-luxtronik Visi 31: ID_Visi_Temp_WQ_Ein) | Wärmequelle Eintritt | belegt |
| 10111 | Register | INT16 | 1 |  | t0/0x9 (9) | Temperatur_TWA | Wärmequelle-Aus / heat source outlet | 30 (python-luxtronik Visi 32: ID_Visi_Temp_Kaltekreis) | Wärmequelle Austritt | belegt |
| 10112 | Register | INT16 | 1 |  | t0/0x66 (102) |  | Vorlauf max. / max. flow temp. | immer (−1) | Vorlauf max. | belegt |
| 10113 | Register | INT16 | 1 |  | t0/0x67 (103) |  | TVL calc max | 357 (python-luxtronik Visi 359: Unknown_Visibility_359) | TVL calc max (berechneter max. Vorlauf) | belegt |
| 10120 | Register | INT16 | 1 |  | t0/0x6 (6) | Temperatur_TBW | Warmwasser-Ist / DHW | 27 (python-luxtronik Visi 29: ID_Visi_Temp_BW_Ist) | Warmwasser-Ist | belegt |
| 10121 | Register | UINT16 | 1 |  | t0/0x7 (7) |  | Warmwasser-Soll / DHW target | 28 (python-luxtronik Visi 30: ID_Visi_Temp_BW_Soll) | Warmwasser-Soll | belegt |
| 10122 | Fixed | UINT16 |  | 300 |  |  |  |  | Warmwasser Minimum (Konstante) | belegt |
| 10123 | Register | INT16 | 1 |  | t1/0x3cd (973) |  | Max.Warmwassertemp. / DHW temp. max. | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Warmwasser Maximum (Einst_BW_max) | belegt |
| 10124 | Register | INT16 | 1 |  | t0/0x58 (88) |  | DHW Demand border | immer (−1) | Warmwasser Anforderungsgrenze | belegt |
| 10140 | Register | INT16 | 1 |  | t0/0x17 (23) | Temperatur_TFB1 | Mischkreis1-Vorlauf / mix circ1 flow | 31 (python-luxtronik Visi 33: ID_Visi_Temp_MK1_Vorlauf) | MK1 Vorlauf-Ist | belegt |
| 10141 | Register | INT16 | 1 |  | t0/0x16 (22) |  | Mischkreis1 VL-Soll / mix circ1 target | 32 (python-luxtronik Visi 34: ID_Visi_Temp_MK1VL_Soll) | MK1 Vorlauf-Soll | belegt |
| 10142 | Register | INT16 | 1 |  | t1/0x430 (1072) |  |  |  | MK1 Vorlauf Minimum | belegt |
| 10143 | Register | INT16 | 1 |  | t1/0x433 (1075) |  |  |  | MK1 Vorlauf Maximum | belegt |
| 10150 | Register | INT16 | 1 |  | t0/0x19 (25) | Temperatur_TFB2 | Mischkreis2-Vorlauf / MC2 flow | 34 (python-luxtronik Visi 36: ID_Visi_Temp_MK2_Vorlauf) | MK2 Vorlauf-Ist | belegt |
| 10151 | Register | INT16 | 1 |  | t0/0x18 (24) |  | Mischkreis2 VL-Soll / MC2 flow target | 35 (python-luxtronik Visi 37: ID_Visi_Temp_MK2VL_Soll) | MK2 Vorlauf-Soll | belegt |
| 10152 | Register | INT16 | 1 |  | t1/0x431 (1073) |  |  |  | MK2 Vorlauf Minimum | belegt |
| 10153 | Register | INT16 | 1 |  | t1/0x434 (1076) |  |  |  | MK2 Vorlauf Maximum | belegt |
| 10160 | Register | INT16 | 1 |  | t0/0x1b (27) | Temperatur_TFB3 | Mischkreis3-Vorlauf / MC3 flow | 210 (python-luxtronik Visi 212: ID_Visi_Temp_MK3_Vorlauf) | MK3 Vorlauf-Ist | belegt |
| 10161 | Register | INT16 | 1 |  | t0/0x1a (26) |  | Mischkreis3 VL-Soll / MC3 flow target | 211 (python-luxtronik Visi 213: ID_Visi_Temp_MK3VL_Soll) | MK3 Vorlauf-Soll | belegt |
| 10162 | Register | INT16 | 1 |  | t1/0x432 (1074) |  |  |  | MK3 Vorlauf Minimum | belegt |
| 10163 | Register | INT16 | 1 |  | t1/0x435 (1077) |  |  |  | MK3 Vorlauf Maximum | belegt |
| 10201 | Register | UINT16 | 1 |  | t0/0x54 (84) |  | Fehlernummer / error number | immer (−1) | Fehlernummer | belegt |
| 10202 | Register | UINT16 | 1 |  | t0/0x53 (83) |  | Einbindung / integration | immer (−1) | Einbindung / Puffertyp | belegt (Name); Werte aus python-luxtronik |
| 10203 | Fixed | UINT16 |  | 20 |  |  |  |  | Schaltspielsperre (Konstante) | belegt |
| 10204 | Fixed | UINT16 |  | 20 |  |  |  |  | Mindestlaufzeit (Konstante) | belegt |
| 10205 | Register | UINT16 | 1 |  | t0/0x59 (89) |  | Cooling enabled | immer (−1) | Kühlung konfiguriert | belegt |
| 10206 | Register | UINT16 | 1 |  | t0/0x5a (90) |  | Pool enabled | immer (−1) | Pool konfiguriert | belegt |
| 10207 | Register | UINT16 | 1 |  | t0/0x32 (50) | Signal_CoolingClearance | Freigabe Kühlung / release cooling | 3 (python-luxtronik Visi 5: ID_Visi_Kuhlung) | Freigabe Kühlung | belegt |
| 10300 | Register | INT16 | 100 |  | t0/0x15 (21) | Waermeleistung | Heizleistung Ist / Heating capacity | 342 (python-luxtronik Visi 344: Unknown_Visibility_344) | Heizleistung Ist (Waermeleistung) | belegt |
| 10301 | Register | UINT16 | 100 |  | t0/0x5b (91) |  | Leistungsaufnahme / Power Consumption | immer (−1) | Leistungsaufnahme (electricPowerConsumption) | belegt |
| 10302 | Register | UINT16 | 1 |  | t0/0x5c (92) |  | Power consumption min | immer (−1) | Leistungsaufnahme Minimum (Prognose) | belegt |
| 10310 | MultiByte(Register) | UINT32 | 10 |  | t0/0x62 (98) |  | Gesamt / total | immer (−1) | Energie elektrisch gesamt | belegt |
| 10312 | MultiByte(Register) | UINT32 | 10 |  | t0/0x5d (93) |  | Heizung / heating | immer (−1) | Energie elektrisch Heizung | belegt |
| 10314 | MultiByte(Register) | UINT32 | 10 |  | t0/0x5e (94) |  | Warmwasser / domestic hot water | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Energie elektrisch Warmwasser | belegt |
| 10316 | MultiByte(Register) | UINT32 | 10 |  | t0/0x60 (96) |  | Kühlung / cooling | 3 (python-luxtronik Visi 5: ID_Visi_Kuhlung) | Energie elektrisch Kühlung | belegt |
| 10318 | MultiByte(Register) | UINT32 | 10 |  | t0/0x5f (95) |  | Schwimmbad / swimming pool | 228 (python-luxtronik Visi 230: ID_Visi_Bst_BStdSW) | Energie elektrisch Schwimmbad | belegt |
| 10320 | MultiByte(Register) | INT32 | 10 |  | t0/0x68 (104) |  | Wärmemenge WQ gesamt / total heat quant. HS | immer (−1) | Wärmemenge gesamt | belegt |
| 10322 | MultiByte(Register) | INT32 | 10 |  | t0/0x69 (105) |  | Heizen / heating | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Wärmemenge Heizung | belegt |
| 10324 | MultiByte(Register) | INT32 | 10 |  | t0/0x6a (106) |  | Warmwasser / domestic hot water | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Wärmemenge Warmwasser | belegt |
| 10326 | MultiByte(Register) | INT32 | 10 |  | t0/0x6b (107) |  | Kühlung / cooling | 3 (python-luxtronik Visi 5: ID_Visi_Kuhlung) | Wärmemenge Kühlung | belegt |
| 10328 | MultiByte(Register) | INT32 | 10 |  | t0/0x6c (108) |  | Schwimmbad / swimming pool | 2 (python-luxtronik Visi 4: ID_Visi_Schwimmbad) | Wärmemenge Schwimmbad | belegt |
| 10350 | Register | UINT16 | 1 |  | t0/0x45 (69) | VBOout | Ventil.-BOSUP / VBO | 54 (python-luxtronik Visi 56: ID_Visi_OUT_Ventil_BOSUP) | Ausgang VBO | belegt |
| 10351 | Register | UINT16 | 1 |  | t0/0x6d (109) | FP1out |  | 49 (python-luxtronik Visi 51: ID_Visi_OUT_FUP1) | Ausgang FP1 | belegt |
| 10352 | Register | UINT16 | 1 |  | t0/0x4c (76) | FP2out | FP2 / FP2 | 62 (python-luxtronik Visi 64: ID_Visi_OUT_FUP2) | Ausgang FP2 | belegt |
| 10353 | Register | UINT16 | 1 |  | t0/0x4d (77) | FP3out | FP3 / FP3 | 225 (python-luxtronik Visi 227: ID_Visi_OUT_FUP3) | Ausgang FP3 | belegt |
| 10354 | Register | UINT16 | 1 |  | t0/0x20 (32) | HUPout | HUP / HUP | 50 (python-luxtronik Visi 52: ID_Visi_OUT_HUP) | Ausgang HUP | belegt |
| 10355 | Register | UINT16 | 1 |  | t0/0x44 (68) | BUPout | BUP / BUP - DHW pump | 48 (python-luxtronik Visi 50: ID_Visi_OUT_BUP) | Ausgang BUP | belegt |
| 10356 | Register | UINT16 | 1 |  | t0/0x48 (72) | ZIPout | ZIP / ZIP | 57 (python-luxtronik Visi 59: ID_Visi_OUT_ZIP) | Ausgang ZIP | belegt |
| 10360 | Register | UINT16 | 1 |  | t0/0x2a (42) | EVUin | EVU / EVU | 41 (python-luxtronik Visi 43: ID_Visi_IN_EVU) | Eingang EVU | belegt |
| 10361 | Register | UINT16 | 1 |  | t0/0x2b (43) | EVU2in | EVU 2 / EVU 2 | 306 (python-luxtronik Visi 308: ID_Visi_HZIO) | Eingang EVU 2 | belegt |
| 10400 | Fixed | UINT16 |  | 3 |  |  |  |  | Firmware Major | belegt |
| 10401 | Fixed | UINT16 |  | 92 |  |  |  |  | Firmware Minor | belegt |
| 10402 | Fixed | UINT16 |  | 3 |  |  |  |  | Firmware Patch | belegt |
| 10404 | MultiByte(Register) | UINT32 | 3600 |  | t1/0x29c (668) | Zaehler_BetrZeitWP | Betriebstunden WP / operating hours HP | 87 (python-luxtronik Visi 89: ID_Visi_Bst_BStdWP) | Betriebsstunden WP | belegt |
| 10406 | MultiByte(Register) | UINT32 | 3600 |  | t1/0x2d8 (728) | Zaehler_BetrZeitHz | Betriebstunden Heiz. / operat. hours heat. | 195 (python-luxtronik Visi 197: ID_Visi_Bst_BStdHz) | Betriebsstunden Heizung | belegt |
| 10408 | MultiByte(Register) | UINT32 | 3600 |  | t1/0x2d9 (729) | Zaehler_BetrZeitBW | Betriebstunden WW / operating hours DHW | 196 (python-luxtronik Visi 198: ID_Visi_Bst_BStdBW) | Betriebsstunden Warmwasser | belegt |
| 10410 | MultiByte(Register) | UINT32 | 3600 |  | t1/0x2da (730) | Zaehler_BetrZeitKue | Betriebstunden Kuehl / operat. hours cool. | 197 (python-luxtronik Visi 199: ID_Visi_Bst_BStdKue) | Betriebsstunden Kühlung | belegt |
| 10412 | MultiByte(Register) | UINT32 | 7200 |  | t1/0x35b (859) | Zaehler_BetrZeitSW | Schwimmbad / swimming pool | 228 (python-luxtronik Visi 230: ID_Visi_Bst_BStdSW) | Betriebsstunden Schwimmbad (SW) | belegt (Zähler), Divisor-Absicht offen |
| 10416 | MultiByte(Register) | UINT32 | 3600 |  | t1/0x372 (882) | BSTD_Solar | Betriebstunden Solar / operating hours solar | 248 (python-luxtronik Visi 250: ID_Visi_Solar) | Betriebsstunden Solar | belegt |
| 10500 | Register | INT16 | 1 |  | t1/0x47a (1146) | ExtraDHW::temperatureSetpoint | Sollwert / targ.value | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Extra-Warmwasser Soll-Temperatur | belegt |
| 10501 | Register | INT16 | 60 |  | t1/0x47b (1147) | ExtraDHW::durationSetpoint | Dauer Extra Warmwasser / duration extra DHW | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Extra-Warmwasser Dauer | belegt |
| 10502 | Register | INT16 | 60 |  | t0/0x3a (58) | ExtraDHW::timer | Laufzeit / running time | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Extra-Warmwasser Restlaufzeit | belegt |

Besonderheiten:
* 10107 ist **nicht** der Parameter „Heizgrenze“, sondern das SHI-eigene Item t0/0x57 „Heating demand border“: die effektive Anforderungsschwelle der Heizung (= wirksamer Rücklaufsollwert − Hysterese `Einst_HRHyst_akt`, mit Modus-abhängigem Tracking in `FUN_00206268`; geschrieben in `FUN_00205d68`). Analog 10124 = t0/0x58 „DHW Demand border“ (`FUN_002071a8`). Die Namen „heating_limit“/„dhw_limit“ in python-luxtronik sind sinngemäß richtig („Grenztemperatur, bei Unterschreiten Anforderung“).
* 10100/10101: Firmware bindet 10100 an `Temperatur_TRL` (Ist) und 10101 an `Sollwert_TRL_HZ` (Soll) – also wie in `registers.py` gemessen; die Benennung in den veröffentlichten Listen war vertauscht.
* 10112 = t0/0x66 „Vorlauf max.“ (Quelle `FUN_0027043c` → `DAT_00a177c8`), 10113 = t0/0x67 „TVL calc max“ (berechneter maximaler Vorlauf; Visibility 0x165 = python-luxtronik Visi 359). Die bisherige Deutung „Vorlauf-Soll Heizen (berechnet)“ ist durch den Firmware-Text zu ersetzen.
* 10300/10301: intern Watt (float `Waermeleistung` bzw. `electricPowerConsumption`, Anzeigeformat „%.02f kW“ mit Faktor 0,001); Divisor 100 → Wire = W/100 → `registers.py` scale 100 ist korrekt. 10302 = Prognose der minimalen Leistungsaufnahme (`FUN_002f96cc` → `DAT_00a19118`, `FUN_002f9640` schreibt /100).
* Energiezähler 10310–10328: t0/0x5d–0x6c, Gruppe „Leistungsaufnahme“ (`FUN_0008b908`, Format „%.01f kWh“ Faktor 0,01 → intern 10 Wh, Divisor 10 → Wire 0,1 kWh). Reihenfolge Heizung (0x5d), Warmwasser (0x5e), Schwimmbad (0x5f), Kühlung (0x60), Gesamt (0x62); Wärmemenge 0x68 Gesamt, 0x69 Heizen, 0x6a WW, 0x6b Kühlung, 0x6c Schwimmbad. Elektrisch UINT32, thermisch INT32 (Builder-Vorzeichen).
* 10412 Divisor **7200**: Zähler `Zaehler_BetrZeitSW` (Betriebsstunden Schwimmbad; Firmware-Text „Schwimmbad“, Visibility 0xe4 = `ID_Visi_Bst_BStdSW`). Die Firmware-Anzeige selbst nutzt für diesen Zähler denselben Faktor 1/3600 wie für alle anderen (Format „%.0fh“, Konstante 0x3f323456…). Der SHI-Divisor 7200 ist also eine Abweichung des SHI-Codes (wahrscheinlich ein Tippfehler 0x1c20 statt 0xe10); Wire-Wert = Stunden/2 → zur Darstellung in Stunden ×2 (**wahrscheinlich**; ohne Live-Messung nicht abschließend prüfbar, da auf der Referenzanlage kein Pool).
* 10500/10501/10502 = Extra-Warmwasser: Soll-Temperatur (Param 1146, 0,1 °C), Dauer (Param 1147, intern s, Wire min) und Rest-Timer (`ExtraDHW::timer`, intern s, Wire min; dekrementiert pro Tick in `FUN_0025662c`).

### 2.3 Discrete Inputs (FC 2) – neu dokumentiert


| Adresse | Bedeutung | Bedingung | Grad |
|---|---|---|---|
| 10000 | Ausstattung Heizen | device_config bit 1 && Ba_Hz_akt != 4 (Betriebsart Heizung nicht "Aus") | belegt |
| 10001 | Ausstattung Warmwasser | device_config bit 2 && Ba_Bw_akt != 4 | belegt |
| 10002 | Ausstattung Kühlen | t0/0x59 "Cooling enabled" != 0 | belegt |
| 10003 | Ausstattung Pool | t0/0x5a "Pool enabled" != 0 | belegt |
| 10004 | Ausstattung Solar | Firmware-Visibility 0xf8 (248) = python-luxtronik Visi 250 ID_Visi_Solar (Firmware-ID + 2 = python-luxtronik-Index, belegt an 40+ Items) | belegt |
| 10005 | Raumregler (RBE) | Einst_RFVEinb_akt == 4 | belegt |
| 10006 | MK1 Heizen | Firmware-Visibility 5 = python-luxtronik Visi 7 ID_Visi_MK1 | belegt |
| 10007 | MK1 Kühlen | Firmware-Visibility 0x18e (398) = python-luxtronik Visi 400 (dort unbenannt) – Kühl-Sichtbarkeit MK1 | belegt |
| 10008 | MK2 Heizen | Firmware-Visibility 6 = Visi 8 ID_Visi_MK2 | belegt |
| 10009 | MK2 Kühlen | Firmware-Visibility 399 = Visi 401 (unbenannt) | belegt |
| 10010 | MK3 Heizen | Firmware-Visibility 0xd1 (209) = Visi 211 ID_Visi_MK3 | belegt |
| 10011 | MK3 Kühlen | Firmware-Visibility 400 = Visi 402 (unbenannt) | belegt |

Belegt in `FUN_000db9b0` (vtable-Slot 4 der SmartHomeInterface). `device_config::config` (Bitmaske `FUN_00063f98`): Bit 1 Heizung, 2 Warmwasser, 4 (Kühlung-Bit, in `FUN_000e4990` genutzt). 10000/10001 sind **0, wenn die Betriebsart der Funktion auf „Aus“ (Ba_*_akt == 4)** steht – sie melden also nicht nur Ausstattung, sondern Ausstattung ∧ nicht „Aus“. Entspricht `registers.py` `CAPABILITIES` (dort 10004 ohne Zuordnung → **Solar**).

---

## 3. Semantik der Schreibregister

### 3.1 Heizung (10000–10003), Mischkreise (10010–10037), Gesamt (10065–10067) – belegt

Rücklaufsollwert des Heizkreises: `FUN_00205d68` (schreibt `Sollwert_TRL_HZ`). Reihenfolge der Prüfungen:
1. Kühlbetrieb/Kühlfreigabe → Soll = 50 (5,0 °C) bzw. Kühllogik.
2. Parallelbetrieb-Slave, Zwangsheizung (`Signal_zheiz` → 750), Ausheizprogramm → feste Werte; SHI wirkungslos.
3. **Heizung „Aus“** (`Ba_Hz_akt == 4`), Heizgrenze aktiv **oder Sperre 10050 (t2/0x1e) ≠ 0** → Soll = Minimum (Param 979 „Min. Rückl.Solltemp.“), SHI-Soll/Offset werden nicht ausgewertet.
4. Sonst liefert `FUN_00205b60` den Heizkurvenwert; dann SHI-Auswahl `FUN_002056d8`:
   * nur wenn Parameter **t1/0x489 „Enable SHI“ ≠ 0** (Menü-Einstellung; python-luxtronik kennt Index 1161 nicht);
   * **Gesamt-Modus 10065 (t2/0x20) hat Vorrang**: ist er ≠ 0, wird der Einzelmodus 10000 ignoriert. Gesamt 2 → Offset 10066; Gesamt 3 → Stufe 10067 mit Parametern „Hz. allg.“ (Absenkung t1/0x4a3, Erhöhung t1/0x4a4). Gesamt-Modus 1 (Sollwert) ist **nicht** implementiert und wirkt wie 0.
   * Gesamt = 0 → Einzelmodus 10000: 1 → Soll = 10001 direkt (Heizkurve ersetzt); 2 → Soll = Heizkurve + 10002; 3 → Soll = Heizkurve + Parameter (Stufe 1 oder 2: „Erhöhung Heizen“ t1/0x4a6; Stufe 3: „Absenkung Heizen“ t1/0x4a5; Stufe 0: Offset 0).
   * PV-/Multispeicher-Sonderfall (`FUN_00205140`): bei PV-Überschussbetrieb wird der Offset-/Stufenpfad durch `FUN_0020524c` (PV-Zieltemperatur) ersetzt; der Sollwert-Modus (1) bleibt wirksam.
5. Begrenzung durch `FUN_00453a8c` auf Minimum (Parameter 979) und Maximum (`Einst_TRBegr_akt`). Das SHI kann also die Rücklaufbegrenzung **nicht** überschreiten.
6. „Heating demand border“ (t0/0x57 → 10107) = `FUN_00205374`: Mode 1 → min(bisheriger Border, SHI-Soll) wird nachgeführt; Mode 2/3 → negativer Offset wird gemerkt; abzüglich `Einst_HRHyst_akt`, wenn Verdichter nicht im Heizbetrieb.

Stufen-Parameter (Tabelle `DAT_007e3ef0`, registriert in `FUN_0008a990`, Range −200..+200 in 0,1 K, Schritt 5, Format „%+.01f K“; Menü „Offsets“ `FUN_00314f30`): Hz. allg. 0x4a3/0x4a4, Heizen 0x4a5/0x4a6, MK1 0x4a7/0x4a8, MK2 0x4a9/0x4aa, MK3 0x4ab/0x4ac, Warmwasser 0x4ad/0x4ae (jeweils Absenkung/Erhöhung). Diese Parameter stellt der Nutzer am Gerät ein; die Stufe wählt nur zwischen ihnen. Die Werte sind in python-luxtronik `parameters.py` noch nicht benannt (Indizes 1187–1198).

Mischkreise: `FUN_002084d0` (MK-Vorlaufsoll) → `FUN_00207eb4`, identische Logik mit den t2-IDs aus dem MK-Objekt (+0x48 Modus, +0x50 Sollwert, +0x4c Offset, +0x60 Stufe, +0x64/+0x68 Stufen-Parameter). Gesamt-Modus gilt auch hier. Ergebnis wird auf MK-Min/Max (Params 1072–1077) begrenzt, zuletzt + `Einst_WK_akt`. Kühl-Register 10015–10017 etc.: Grenzen 50..250 (5–25 °C) und −50..50 belegt; Konsument nicht einzeln verfolgt (**wahrscheinlich** analog).

#### Heizkurve (belegt)

Die Funktion `0x0020752c` berechnet die Heizkurve aus dem Endpunkt *E* und dem Parameter *Parallelverschiebung* *F*;
*F* wird auf 5,0–35,0 °C begrenzt. Mit der Außentemperatur *T*<sub>außen</sub>:

Soll = F + (E − 20) · (F − T<sub>außen</sub>) / (20 − (T<sub>außen</sub> − F) / 2)

Das Ergebnis wird unten auf 15,0 °C begrenzt und danach vom Aufrufer auf Minimum und Maximum des Kreises (Mischkreise:
`FUN_002084d0`, Parameter 1072–1077, danach + `Einst_WK_akt`). Ist E = 20,0, ist das Soll die Konstante *F*.

Folgen: *F* ist der Punkt, an dem Außentemperatur und Soll gleich sind, und eine Änderung von *F* ändert die Steigung
der Kurve; trotz des Namens ist es keine Parallelverschiebung. *E* ist das Soll bei −20 °C außen nur, wenn F = 20.

An der Referenzanlage nachgerechnet: Heizkreis E/F 30/22 bei etwa 6 °C außen → 27,7 °C (Regelung 27,7); MK1 45/30 bei
6,1 °C → 48,8 °C, auf das Maximum 45 begrenzt (Regelung 45,0); MK1 45/20 bei 5,8 °C → 33,1 °C (Regelung 33,0).

### 3.2 Warmwasser (10005–10008, 10051, 10071) – belegt

* `FUN_00206d2c` wählt analog (nur mit „Enable SHI“; **kein** Gesamt-Einfluss): Modus 1 → Soll = 10006; 2 → Soll = normaler WW-Soll + 10007; 3 → + Parameter 0x4ae (Stufe 1/2, Erhöhung) bzw. 0x4ad (Stufe 3, Absenkung).
* `FUN_00206f7c` liefert `dhw::desiredSetpoint` (= `FUN_0020702c`: `DHW_DesiredTemperature` = Thermostat-/Zeitprogrammwert, ggf. SmartWW/EBV, + Param 0x462 bei Betriebszustand 3/4) **ersetzt durch SHI-Soll** (Modus 1) oder **plus Offset** (2/3).
* `FUN_00203668` (WW-Regelung): Vorrang haben `RBE_Warmwasser_Soll_extra` (Extra-WW/RBE), thermische Desinfektion (`Signal_TDI`), `Signal_BWS`, Nachheizung. Sonst `controlSetpoint = desiredSetpoint`, ggf. begrenzt auf `DHW_CoverageOfHeatPump` (Deckungs-Grenze der WP) und immer auf `Einst_BW_max` (10123). Der SHI-Sollwert ist also eine Obergrenze **unter** `Einst_BW_max`, nicht darüber.
* **Sperre 10051 (t2/0x1f)**: `FUN_002f9c0c` meldet „WW gesperrt“ wenn 10051 ≠ 0 oder Ba_Bw == 4 oder Urlaub (SuBw_akt == 1) → Anforderungsblock; die Betriebsart (Ba_Bw_akt, Param 4) wird nicht verändert. `FUN_0010e45c` bindet 10051 zusätzlich in das Anforderungsobjekt der WW-Bereitung ein.
* **Pending-Map** (`FUN_00087700`): Schreibzugriffe auf genau t2 5, 6, 7, 0x27 (10005–10008) werden mit Zähler 10 abgelegt (`FUN_0008747c`, `'\n'` = 10) und vom 1-Hz-Tick `FUN_0008798c` nach 10 Ticks mit gesetztem Deferred-Flag (1) über `set` committed → ~10 s Verzögerung bis zum Rücklesen. Ein Schreiben des aktuell gespeicherten Werts löscht den Pending-Eintrag (`FUN_0008747c`, Zweig, in dem neuer und gespeicherter Wert gleich sind).
* **Extra-WW 10071 (t2/1)**: Schreib-Callback `FUN_00089328`: ≠ 0 → der Timer `ExtraDHW::timer` wird auf Parameter 1147 (Dauer, s) gesetzt; 0 → Timer 0. `FUN_00081c1c` (Tick): solange Timer läuft, hat `RBE_Warmwasser_Soll_extra` den größeren Wert aus altem RBE-Sollwert und Parameter 1146, begrenzt auf [`DHW_DesiredTemperature`, `Einst_BW_max`]; **nach Ablauf setzt die Firmware t2/1 selbst auf 0** (über `FUN_004270bc`). 10502 zeigt die Restzeit (min).

### 3.3 Übrige Schreibregister – belegt

* **10040/10041 LPC** (`limitation_power_consumption`): `FUN_002fa0b0` liefert Modus nur wenn „Enable SHI“ ≠ 0; 2 = Hard limit; 1 = Soft limit nur wenn Zusatzbedingung `FUN_002fa1ec` (Zustandsobjekt `DAT_00a19128`) erfüllt, sonst 0. Grenzwert `FUN_002fa044` multipliziert 10041 mit 100 → W (Wire 0,1 kW, Range 0..300, Default 300 = 30 kW). Anzeige „Max Power Consumption Limit - SHI“ (Text 0x7e3254) im Service-Menü.
* **10052 Sperre Kühlung** (t2/0x1c): `FUN_001a3a84`, `FUN_001ed6f8` (== 1 → Kühlung passiv/aktiv blockiert). **10053 Sperre Pool** (t2/0x1d): `FUN_001ef980`.
* **10050 Sperre Heizung**: s. 3.1 Punkt 3; zusätzlich `FUN_002f9c0c` (Heizung gesperrt oder Kühlfreigabe) in das LPC-Zustandsobjekt.
* **10070 Zirkulation** (t2/0x28, Visibility 8 = `ID_Visi_Zirkulation`): `FUN_00275f94` startet die ZIP-Logik (`DAT_00a17c7c`), Laufzeiten aus `Einst_Zirk_Ein/Aus_akt` × 60; wenn das Bit gesetzt ist, aber kein Lauf mehr aktiv, **setzt die Firmware 10070 auf 0** (über `FUN_00427538`). Gesperrt wenn Ba_Bw ∈ {3,4}.
* **Beenden eines Laufs durch Schreiben von 0 in 10070** (belegt): `FUN_00275f94` bildet die Zirkulationsanforderung in jedem 1-s-Zyklus als *(10070 ≠ 0) ODER die Anforderung des eigenen Zirkulations-Zeitprogramms der Regelung* (`FUN_00252f54`) und übergibt sie an die ZIP-Zustandsmaschine (Objekt bei `DAT_00a17c7c`): Der Setter `FUN_00276488` speichert das Anforderungs-Flag, und `FUN_0028a5d4` meldet „läuft“ nur, wenn die Maschine freigegeben **und** `FUN_0028a4a0` wahr ist. `FUN_0028a4a0` liefert sofort falsch, solange das Anforderungs-Flag 0 ist; der Pumpenausgang (ZIP, Input 10356) stoppt also sofort. Der Laufzähler wird nicht zurückgesetzt, sondern eingefroren: Der nächste Start setzt die restliche Laufzeit fort statt einer vollen. Schreiben von 0 während eines Laufs beendet ihn also, außer das Zeitprogramm fordert gleichzeitig Zirkulation an. Die Integration bietet das als Taster `circulation_stop` an; ob die Pumpe läuft, zeigt der Binärsensor `pump_circulation` (10356), der auch Läufe des Zeitprogramms abdeckt.
* **10060 Raumsollwert** (`RBE_RoomTemperatureSetpointRegister`, `FUN_000dd478`): bindet **direkt t1/0x47c = Parameter 1148 `RBE_Raumtemperatur_Soll`** (UINT16, 0,1 °C). Schreiben setzt den Parameter mit Quelle SHI; `avail()` (`FUN_000dfce4`) = Visibility(0x176) ∧ `FUN_000e3c34`: RBE vorhanden, verbunden **und `RBE_Einflussfaktor_RT_akt` > 0**. Grenzen: kein Range-Objekt im SHI-Register selbst, aber der Parameter trägt seine eigenen Bounds (Registrierung `FUN_000889e4`-Pfad in `FUN_00099a78`, Format „%.01f°C“); konkrete Min/Max im Dump nicht als Zahlen sichtbar → **offen**. Da es ein t1-Parameter ist, wird er beim Wächterablauf auf den **persistierten Wert** zurückgesetzt (typ 1 in `FUN_000881e0`).
* **t2/0 „Schnellladung“** (Text 4, `FUN_0009bab4`): internes SHI-Item, das von `FUN_00216a3c`/`FUN_0031f6f0`/`FUN_0031fb78` (WW-Schnellladung über Bedienteil) gesetzt wird; **kein SHI-Register bindet t2/0** → über Modbus nicht erreichbar.

### 3.4 Boot-Defaults und Rücksetzwerte (belegt, `FUN_00087e9c`)

| t2-ID | Register | Default |
|---|---|---|
| 3 | 10001 | 350 (35,0 °C) |
| 6 | 10006 | 400 (40,0 °C) |
| 9, 0xf, 0x15 | 10011, 10021, 10031 | 350 |
| 0xc, 0x12, 0x18 | 10016, 10026, 10036 | 200 (20,0 °C) |
| 0x1b | 10041 | 300 (30,0 kW) |
| alle übrigen | Modi, Offsets, Stufen, Sperren, Schalter | 0 |

---

## 4. Wächter, Neustart, Fehlerfälle

* `SmartHomeInterface::Monitor` (Objekt an SHI+0x908, Konstruktor `FUN_000dfd50`), Tick `FUN_000dff50` (1 Hz, Tick-Liste `0x00a2128c`): Zähler 0…600; bei Erreichen von **600 s** → `FUN_00186170`: Eventlog-Eintrag (Typ 0x10, Flag 1) und `FUN_00186120` → `GDI::reloadIfSetBy(Source SHI)`.
* Re-arm `FUN_000de744` am Anfang **jedes** Dispatcher-Aufrufs (Lesen und Schreiben, FC 2/3/4/6/16): Zähler = 0; war der Zähler ≥ 600 (abgelaufen), wird ein Eventlog-Eintrag „SHI wieder da“ (Typ 0x10, Flag 0) geschrieben. Ein pollender Client hält den Wächter also dauerhaft scharf.
* `GDI::reloadIfSetBy` (`FUN_000882f0`) iteriert **t1 0..0x4af und t2 0..0x28** und ruft für jedes Item, dessen letzte Quelle SHI (6) ist, `FUN_000881e0`: typ 1 (t1-Parameter, z. B. 10060) → persistierter Wert aus `FUN_00244298`; typ 2 (t2) → Default aus `FUN_00087e9c` (§3.4); neue Quelle 0xFFFFFFFF („---“ in der Anzeige).
* Neustart: `FUN_0009da20` setzt alle t2-Items 0..0x28 auf ihre Defaults (Quelle 0). Wirkung identisch zum Wächterablauf.
* Rücklesen nach Ablauf: Modi/Stufen/Sperren/Schalter = 0, Sollwerte = Default (350/400/200/300), LPC-Limit = 300; nie 0x7FFF (das erscheint nur bei fehlender Sichtbarkeit).
* Fehler 816 „Mehrere SHI Schreibquellen“ (Texte 0x8766d4/0x8766f0, Index 0x6F): > 2 verschiedene (Quelle, Client-ID)-Paare in 3600 s; myUplink zählt als eigene Quelle. Während aktiv: alle SHI-Schreibvorgänge wirkungslos, keine Exception. (Mechanik aus Vorarbeit bestätigt, hier nicht weiter vertieft.)
* Schreiben außerhalb Range → **Revert auf Default** statt Übernahme (§1.4). Für die Integration bedeutet das: ein Out-of-range-Write ist nicht nur „verloren“, sondern löscht den vorherigen SHI-Wert.

---

## 5. Neue Erkenntnisse gegenüber python-luxtronik und registers.py

1. **Alle GDI-IDs sind jetzt Namen zugeordnet** (Variable, Firmware-Text, Visibility) – siehe CSV. python-luxtronik `inputs.py` ist in Adressen, Typen und Vorzeichen vollständig bestätigt; Ergänzungen:
   * `unknown_input_113` = „TVL calc max“ (berechneter max. Vorlauf, 0,1 °C, INT16).
   * `unknown_input_350..356/360/361` = `VBOout, FP1out, FP2out, FP3out, HUPout, BUPout, ZIPout, EVUin, EVU2in` (bestätigt).
   * `unknown_input_404..417` = Betriebsstunden WP/Heizung/WW/**Kühlung**/**Schwimmbad (Divisor 7200!)**/**Solar**, UINT32.
   * `unknown_input_500/501/502` = Extra-WW Soll (0,1 °C), Dauer (min), Restzeit (min).
   * `unknown_holding_60` = **schreibbarer** RBE-Raumsollwert (Parameter 1148), 0,1 °C, nur mit RBE + Einflussfaktor > 0 verfügbar.
   * `heating_limit`(10107)/`dhw_limit`(10124) sind die dynamischen Anforderungsgrenzen (Soll − Hysterese), keine Parameter; seit 0.18.0 heißen die Schlüssel `heating_demand_border`/`dhw_demand_border`.
   * `max_flow_temp`(10112) = „Vorlauf max.“ – bestätigt.
2. **Gesamt-Modus 10065–10067** (bisher ohne Beleg, Entities deaktiviert): belegt – überschreibt die Heizkreis- **und** Mischkreis-Modi, Modus 1 (Sollwert) ist dort wirkungslos; Offset −50..+50 (nicht −200..200 wie bei 10002!), Stufe über Parameter „Hz. allg.“ 0x4a3/0x4a4.
3. **Stufen-Semantik** (`_LEVELS`): 0 Normal, 1 Erhöhung, 2 Erhöhung (identisch zu 1), 3 Absenkung. Die Beträge sind die Geräte-Parameter 1187–1198 (Menü „Offsets“, ±20 K in 0,5-K-Schritten). python-luxtroniks `LevelMode` („Increased2“) ist in der Firmware kein eigener Wert.
4. **Grenzen aus der Firmware** (Range-Objekte): 10001 150..750; 10002 −200..200; 10006 300..750; 10007 −200..200; 10011/21/31 200..650; 10012/22/32 −50..50; 10016/26/36 50..250; 10017/27/37 −50..50; 10041 0..300; 10066 −50..50; Stufen 0..3. Schritt überall 1 (= 0,1 °C) – `registers.py` step 0.5 ist eine Oberflächen-Vereinfachung, 0,1-Schritte wären zulässig. **Abweichung:** `registers.py` erlaubt für 10066 ±20 K, die Firmware nur ±5 K → Werte darüber werden revertiert.
5. **Out-of-range-Write ⇒ Revert auf Default** (nicht Ignorieren). Lesen-nach-Schreiben in der Integration deckt das ab, aber die Erwartung „alter Wert bleibt“ stimmt nicht.
6. **Enable SHI** (Parameter t1/0x489 = 1161, Menütext „Enable SHI“, Optionen „ModBus TCP / myUplink / Both“ bei 0x7e3d8c): ist er 0, ignorieren Heizung, WW, MK und LPC die SHI-Werte – die Register bleiben aber lesbar/schreibbar. Sperren (10050–10053), Zirkulation und Extra-WW prüfen diesen Parameter **nicht**.
7. **Discrete Inputs (FC 2)** 10000–10011 vollständig bestimmt, inkl. 10004 = Solar; 10000/10001 = Ausstattung ∧ Betriebsart ≠ Aus.
8. **Watchdog-Ereignisse** werden im Gerät protokolliert (Eventlog Typ 0x10): Ablauf und Wiederkehr lassen sich am Bedienteil nachvollziehen.
9. **Zirkulation/Extra-WW** sind Trigger: die Firmware setzt die Bits nach Ende selbst auf 0 – ein Rücklesen 0 ist kein Fehler.
10. Im SHI **nicht** erreichbar, obwohl als t2-Item vorhanden: t2/0 „Schnellladung“ (WW-Schnellladung des Bedienteils). Keine weiteren versteckten Holdings: alle 41 Holding-Slots entsprechen t2 1..0x28 plus 10060; keine unbenutzten Slots mit Inhalt.
11. Alle 10 Energiezähler sind MultiByte mit Vorzeichen: elektrisch UINT32, thermisch INT32 (Builder). Reihenfolge der Worte: **High-Word an der niedrigeren Adresse** (`FUN_000d94b4` legt das erste Teilregister mit Wort-Index 1 an; Getter `FUN_000dca24` schiebt um Index×16 → Wort 1 = Bits 31..16). Ein MultiByte-Teilregister ist auch schreibbar implementiert (`FUN_000dc904`, Read-Modify-Write des 32-bit-Werts), die Inputs sind aber nur über FC 4 erreichbar.

---

## 6. Offene Punkte

* 10412 Divisor 7200: Absicht unklar (Firmware-Anzeige rechnet 1/3600). Ohne Pool auf der Referenzanlage nicht messbar → **wahrscheinlich** Faktor 2 nötig, bleibt als Rohwert.
* 10060 Min/Max: nicht als Zahlen im Dump sichtbar (Range-Objekt des Parameters 1148 nicht lokalisiert) → **offen**; gemessene plausible Werte 20–40 °C bleiben Owner-Entscheidung.
* LPC „Soft limit“-Bedingung `FUN_002fa1ec` nicht vertieft (Zustandsobjekt `DAT_00a19128`).
* Kühl-Register 10015–10017 (und MK2/3): Konsument nicht einzeln dekompiliert; Grenzen/Visibility belegt, Wirkung analog zu Heizen **wahrscheinlich**.
* Bit-Belegung 10000 (Input) aus python-luxtronik, Funktion `heating_control::getHeatGeneratorStatus` nicht dekompiliert → **wahrscheinlich**.
* Live-Cross-Check über Home Assistant: die Rohwerte 10410/10412/10416/10500–10502 sind auf der Referenzanlage nicht als Entities aktiviert (nur `sensor.warmepumpe_diagnose_rohwert_10109…10361` vorhanden), daher kein Abgleich möglich. Die aktivierten Werte (10113 = 25,7 °C bei Rücklaufsoll 20,0; 10351/10354 = 1, 10355 = 0, 10360 = 1) passen zu den Deutungen.
* Fehler 816 (Rücksetzbedingung) und das Verhalten „WW-Modus nicht setzbar bei aktiver Sperre“ waren nicht Gegenstand dieser Analyse.

---

## 7. Methode (reproduzierbar)

1. Firmware entpacken: `scripts/extract_fw.py` (gzip ab Offset 4039, zlib `decompressobj(31)`, äußeres Tar, inneres Tar `home.wp2reg-V3.92.3_…`; `bin/Controller` vollständig, 10 498 803 Bytes).
2. Ghidra 11.4.2 headless, `-processor ARM:LE:32:v7 -max-cpu 1`, MAXMEM 4G: Import+Analyse 382 s. Projekt „SHI/Controller“.
3. `scripts/parse_builder.py` (Capstone, symbolische Mini-Emulation der −O0-Builder `FUN_000d8014`/`FUN_000d95d4`): liefert pro Register Klasse, {t,id}, Vorzeichen, Divisor, Fixed-Wert, Slot/Adresse.
4. `scripts/DumpDecomp.java` (Ghidra-Postscript): dekompiliert Funktionslisten in `dec/fn_<addr>.c`, Xrefs `x:<addr>` → `dec/xref_<addr>.txt`. Verwendete Listen in `ref/list*.txt`.
5. `scripts/gdi_map.py`: parst alle Dekompilate der Handle-Konstruktor-Aufrufer (137 Funktionen) → `ref/gdi_map.tsv` (t/ID → Symbol, Visibility, Text-ID, Format, Grenzen).
6. `scripts/texts.py`: Texttabelle (.data 0x9ce58c, 24 Sprachen) → `ref/texts.tsv`.
7. `scripts/build_csv.py` + `scripts/build_report.py`: CSV und dieser Bericht.
8. Querbezug python-luxtronik (Bouni/python-luxtronik, `definitions/{inputs,holdings,parameters,visibilities}.py`, textuell geparst mit `scripts/pl_table.py`) und `registers.py` der Integration.

Hinweis zu Abschnitt 7: Die genannten Skriptnamen (`scripts/…`, `ref/…`, `dec/…`) bezeichnen den lokalen Arbeitsbereich der Analyse und sind nicht Teil dieses Repositorys.
