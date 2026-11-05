# Changelog

Alle nennenswerten Änderungen an diesem Projekt. Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/):

* **0.x.y** – Beta. **1.0.0** ist die erste als fertig betrachtete Version.
* **x.Y.0** – neue Funktionen (neue Register, neue Optionen).
* **x.y.Z** – Fehlerbehebungen, Doku, Tests.
* Änderungen, die eine Entity-ID ändern könnten (Key umbenannt/entfernt, Plattform gewechselt,
  Unique-ID-Schema geändert), sind **Breaking Changes**. Sie werden hier fett markiert und brauchen
  einen Migrationspfad.

## [Unreleased]

## [0.3.0] – 05.11.2026

### Hinzugefügt
- **Ausstattung der Anlage** im Einrichtungsdialog und in den Optionen: Mischkreis 1–3, Kühlung, Pool,
  Raumeinheit. Beim Einrichten aus den Ausstattungs-Registern (Discrete Inputs 10002–10011) vorbelegt.
  Abgewählte Teile werden nicht abgefragt und bekommen keine Entitäten; ihre Registry-Einträge und
  Entity-IDs bleiben erhalten und kommen beim Wiedereinschalten zurück.
- Tests für Vorbelegung, Ab- und Wiederanwahl und für Einträge ohne Ausstattungs-Option.

### Geändert
- **Anzeigenamen nach Bereichen gegliedert** („Heizen: Sollwert“, „Warmwasser: Temperatur“,
  „Mischkreis 1: Vorlauf“, „Status: Betriebsart“, „Energie: Strom Heizen“ …), damit die Geräteseite sortiert
  ist. Keys, Unique-IDs und bestehende Entity-IDs ändern sich **nicht**; sichtbar ändern sich nur Namen von
  Entitäten, denen kein eigener Name gegeben wurde.
- Grenz-, Minimum- und Maximumwerte (Rücklauf-Begrenzung, Warmwasser Min/Max/Grenze, Mischkreis Min/Max,
  Rücklauf extern) liegen jetzt unter *Diagnose*.
- Einträge, die vor 0.3.0 angelegt wurden, behalten alle Entitäten, bis die Ausstattung in den Optionen
  geändert wird.

## [0.2.1] – unveröffentlicht

### Hinzugefügt
- Entity-Vertrag: `tests/fixtures/entity_contract.json` und `tests/test_contract.py` lassen die CI scheitern,
  wenn ein Key entfernt, umbenannt oder auf eine andere Plattform verschoben wird.
- Test für das Unique-ID-Schema `<entry_id>_<key>`.
- `tools/gen_contract.py` trägt neue Keys in den Vertrag ein (entfernt nie etwas).
- Versionsprüfung in der CI (`tools/check_version.py`): Manifest-Version muss im CHANGELOG stehen,
  ein Git-Tag `vX.Y.Z` muss zur Manifest-Version passen.
- `CLAUDE.md` mit den Arbeitsregeln für das Repo.

## [0.2.0] – 2026-10-25

Nachträglich dokumentierter Stand (es gab bisher keine Tags).

### Hinzugefügt
- Vollständige Abdeckung der SHI-Register der Referenzanlage: Zahlen, Auswahlen, Mischkreise,
  Zirkulationspumpe, Statusbits (Verdichter, ZWE).
- `tools/gen_yaml.py` (Legacy) erzeugt eine gleichwertige YAML-`modbus:`-Konfiguration.
- README: Umstieg von YAML, Abgrenzung zur nativen Luxtronik-Integration, gemessene Abweichungen.

## [0.1.0] – 2026-10-24

### Hinzugefügt
- Erste Version der Integration mit Config Flow, Options- und Reconfigure-Flow.

[Unreleased]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/2f54427...v0.2.0
[0.1.0]: https://github.com/Bankaifan/ha-luxtronik-shi/commit/2f54427
