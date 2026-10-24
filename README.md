# Luxtronik SHI (Modbus) für Home Assistant

Home-Assistant-Integration für **alpha innotec / Luxtronik Wärmepumpen** über die **Modbus/TCP-Schnittstelle
„Smart Home Interface" (SHI)** – komplett über die Oberfläche einrichtbar (Config Flow), ohne YAML.

Entwickelt und im Alltag getestet an einer **alpha innotec LWDV 91-1/3** (Luxtronik 2.x mit SHI).
Andere Luxtronik-Anlagen mit SHI sollten funktionieren, sind aber nicht getestet.

## Was die Integration kann

| Bereich | Entitäten |
|---|---|
| Temperaturen | Vorlauf, Rücklauf, Rücklauf-Soll, Außen, Warmwasser (Ist, Soll, Min, Max) |
| Leistung & Energie | elektrische und thermische Leistung, Zähler Strom/Wärme (gesamt, Heizen, Warmwasser), Betriebsstunden |
| Status | Fehlernummer, Zustand Wärmeerzeuger, Betriebsart, Status Heizen/Warmwasser, Verbindung |
| **Schreiben** | **Heizkurven-Anhebung** (Number, −5 … +5 K, Schritt 0,5 K), Schalter *Heizung sperren*, *Warmwasser sperren*, *Kühlung sperren*, *Pool sperren*, *Extra-Warmwasser* |
| Diagnose | aktuelle Einstellungen (Betriebsarten, Sollwerte, Stufen, Leistungsbegrenzung), Ausstattungsmerkmale, Firmware, undokumentierte Rohwerte (standardmäßig deaktiviert) |

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

* Die Zahlenwerte für **Betriebsart, Zustand, Status** werden roh angezeigt; eine verlässliche Zuordnung der Werte zu
  Klartext ist nicht dokumentiert und wird daher nicht geraten. Beiträge willkommen.
* Der **Warmwasser-Sollwert** (Register 10006) wird nur gelesen. Bei „Automatik" (Warmwasser-Betriebsart 0) ignoriert die
  Wärmepumpe ihn; das tatsächliche Ziel steht im Sensor *Warmwasser Soll*.
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
