# Luxtronik SHI (Modbus) für Home Assistant

Home-Assistant-Integration für **alpha innotec / Luxtronik Wärmepumpen** über die **Modbus/TCP-Schnittstelle
„Smart Home Interface" (SHI)** – komplett über die Oberfläche einrichtbar (Config Flow), ohne YAML.

Entwickelt und im Alltag getestet an einer **alpha innotec LWDV 91-1/3** (Luxtronik 2.x mit SHI).
Andere Luxtronik-Anlagen mit SHI sollten funktionieren, sind aber nicht getestet.

## Was die Integration kann

| Bereich | Entitäten |
|---|---|
| Temperaturen | Vorlauf, Rücklauf, Rücklauf-Soll/-Begrenzung/-Minimum, Rücklauf extern, Außen, Raum (nur mit Raumeinheit), Grenztemperaturen Heizen/Warmwasser, Warmwasser (Ist, Soll, Min, Max), Mischkreise 1–3 (Vorlauf, Soll, Min, Max) |
| Leistung & Energie | elektrische und thermische Leistung, minimale Stromaufnahme, Zähler Strom/Wärme (gesamt, Heizen, Warmwasser), Betriebsstunden |
| Status | Betriebsart als Klartext (Heizen, Warmwasser, Pool, EVU-Sperre, Abtauen, Aus, externe Quelle, Kühlen), **Verdichter 1/2 läuft**, **Zusatzheizung (ZWE) 1/2 aktiv**, Fehlernummer, Status Heizen/Warmwasser/Kühlung/Pool, Verbindung |
| **Schreiben: Zahlen** | **Heizkurven-Anhebung** (−5 … +5 K), Heizen Sollwert, Warmwasser Sollwert und Anhebung, Mischkreis 1 Sollwert und Anhebung (Heizen und Kühlen), Gesamt-Heizung Anhebung, Leistungsbegrenzung (0–30 kW) |
| **Schreiben: Auswahl** | Betriebsart (Aus / Sollwert / Anhebung / Stufe) für Heizen, Warmwasser, Mischkreis 1, Gesamt-Heizung; Stufe (EVU-Sperre / Absenkung / Normal / Boost); Leistungsbegrenzung (keine / weich / hart) |
| **Schreiben: Schalter** | *Heizung sperren*, *Warmwasser sperren*, *Kühlung sperren*, *Pool sperren*, **Zirkulationspumpe**, *Extra-Warmwasser* |
| Diagnose | Puffertyp, Schaltspielsperre, Mindestlaufzeit, Ausstattungsmerkmale, Firmware, undokumentierte Rohwerte (standardmäßig deaktiviert) |

Die Einstellungen (Zahlen und Auswahl) liegen in der Kategorie *Konfiguration* der Geräteseite. Schreibzugriffe verwenden
dieselben Register wie die Smart-Home-Schnittstelle selbst; die Wärmepumpe erzwingt dabei ihre eigenen Grenzen.

Wichtige Eigenschaften:

* **Gebündelte Abfragen** statt eines Requests pro Wert – schont die Wärmepumpe. Lehnt das Gerät eine Blockabfrage ab
  (z. B. weil ein Register in der Lücke fehlt), liest die Integration automatisch einzeln weiter.
* **Abgestufte Abfrageintervalle**: Messwerte jeden Zyklus (Standard 30 s), Zähler/Einstellungen seltener, Firmware fast nie.
* **Nach jedem Schreibzugriff wird der Wert zurückgelesen**, die Oberfläche zeigt also immer den echten Gerätezustand.
* Negative Werte (Heizkurven-Anhebung) werden korrekt als 16-bit-Zweierkomplement geschrieben.
* Deutsch und Englisch.

## Installation (HACS)

1. HACS → ⋮ → **Benutzerdefinierte Repositories** → `https://github.com/Bankaifan/ha-luxtronik-shi`, Kategorie **Integration**.
2. „Luxtronik SHI (Modbus)" installieren, Home Assistant neu starten.
3. **Einstellungen → Geräte & Dienste → Integration hinzufügen → „Luxtronik SHI (Modbus)"**.
4. Name, IP-Adresse der Wärmepumpe, Port (502) und Geräte-ID (1) eintragen.

Voraussetzung: In der Regelung ist Modbus/TCP aktiviert (Smart-Home-Schnittstelle) und die Wärmepumpe ist im Netz erreichbar.

## Umstieg von einer bestehenden YAML-`modbus:`-Konfiguration

Die Registerliste dieser Integration entspricht einer typischen Eigenkonfiguration; die internen Schlüssel sind absichtlich
so benannt wie die früheren Entity-IDs (`lwdv_shi_<schluessel>`).

1. **YAML-Hub erst deaktivieren** (`modbus:`-Block auskommentieren, Konfiguration neu laden/Neustart). Manche SHI-Firmwares
   erlauben nur wenige gleichzeitige TCP-Verbindungen.
2. Integration hinzufügen (siehe oben).
3. Entity-IDs auf die alten Namen umbenennen (Einstellungen → Entitäten), damit Automationen, Dashboards und
   Energie-Dashboard weiterlaufen. Die alten Namen sind z. B. `sensor.lwdv_shi_flow`, `switch.lwdv_shi_dhw_block`.
   Der Heizkurven-Offset heißt jetzt `number.<name>_heizkurven_anhebung` (vorher nur lesbar als `sensor.lwdv_shi_cfg_heating_offset`).
4. Langzeitstatistiken der Zähler bleiben erhalten, wenn die neue Entität dieselbe Entity-ID bekommt.

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

## Entwicklung

```bash
python -m venv venv && . venv/bin/activate
pip install -r requirements_test.txt pytest-timeout
pytest --timeout=60
```

Die Tests laufen gegen einen kleinen simulierten Modbus/TCP-Server (`tests/fake_shi.py`), der wie die echte SHI nur
vorhandene Register beantwortet. Die Übersetzungen werden aus der Registerliste erzeugt:
`python tools/gen_translations.py`.

Langfristiges Ziel: eine Bibliothek auf PyPI auslagern und die Integration im Home-Assistant-Core einreichen.

## Haftung

Inoffiziell, keine Verbindung zu alpha innotec oder Luxtronik. Nutzung auf eigene Verantwortung.
