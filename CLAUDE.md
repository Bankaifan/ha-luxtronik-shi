# Arbeitsregeln für dieses Repo

Home-Assistant-Integration `luxtronik_shi` für alpha innotec / Luxtronik Wärmepumpen über das
Smart Home Interface (SHI, Modbus/TCP). Die Integration **schreibt auf eine produktive Heizung** und wird
vom Heat Pump Optimizer (HPO) gesteuert. Stabilität geht vor Funktionsumfang.

## Harte Regeln

1. **Entity-Vertrag.** Unique-IDs sind `<entry_id>_<key>`. Keys in `registers.py`, die Keys der Statusbits in
   `binary_sensor.py` und `online` dürfen nie umbenannt, entfernt oder auf eine andere Plattform verschoben
   werden. `tests/test_contract.py` erzwingt das. Neue Keys mit `python tools/gen_contract.py` eintragen.
   Das Unique-ID-Schema nicht ändern ohne Registry-Migration (`async_migrate_entries`), Test und
   Owner-Freigabe.
   Keys, an denen der HPO der Referenzanlage hängt (Auswahl): `flow`, `return`, `outside`, `dhw`,
   `compressor_thermal_power`, `energy_el_heating`, `aux_heater_1`, `cfg_heating_setpoint`, `cfg_mk1_setpoint`,
   `heating_block`, `dhw_block`, `circulation`.
2. **Anzeigenamen sind frei**, Keys nicht. Namen (`name_de`/`name_en`) dürfen sich ändern; bestehende
   Entity-IDs bleiben in der Registry erhalten. Übersetzungen nur mit `python tools/gen_translations.py`
   erzeugen, nie die JSON-Dateien von Hand ändern.
3. **Keine erfundenen Registerfakten.** Adresse, Datentyp, Skalierung, Wertebereich und Wirkung nur mit Quelle:
   - `python-luxtronik` (Bouni/python-luxtronik, `luxtronik/definitions/{inputs,holdings}.py`, MIT),
   - Messung an der Referenzanlage (LWDV 91-1/3, FW 3.92.3) mit Beschreibung,
   - sonst als **offen** markieren und als Rohwert (`raw_<adresse>`, standardmäßig deaktiviert) führen.
4. **Schreibende Register** nur mit Test gegen `tests/fake_shi.py`, inklusive Rücklesen. Keine neuen
   Schreibzugriffe ohne Wertebereich.
5. **Nie gegen echte Geräte oder ein echtes Home Assistant testen.** Nur die Simulation.
6. **Keine Polling-Last erhöhen** ohne Grund: Blockabfragen, `every` für selten benötigte Werte.

## Versionierung

* `0.x.y` Beta, `1.0.0` erste fertige Version. `x.Y.0` neue Funktion, `x.y.Z` Fix/Doku/Tests.
* Jede Änderung trägt sich unter `## [Unreleased]` bzw. der kommenden Version in `CHANGELOG.md` ein.
* Version steht in `custom_components/luxtronik_shi/manifest.json`; `tools/check_version.py` prüft
  Manifest, CHANGELOG und Tag. Releases erstellt der Owner (Tag `vX.Y.Z`).

## Ablauf

* Arbeit über Branch + Pull Request, nie direkt auf `main`. Der Owner prüft und merged.
* Vor dem PR: `ruff check .` und `pytest --timeout=60` grün.
* Breaking Changes nur nach Rücksprache, fett im CHANGELOG, mit Migrationshinweis in der README.

## Befehle

```bash
pip install -r requirements_test.txt pytest-timeout ruff
ruff check . && pytest --timeout=60
python tools/gen_translations.py   # nach Namensänderungen
python tools/gen_contract.py       # nach neuen Keys
python tools/check_version.py      # Version/CHANGELOG
```
