# Changelog

All notable changes to this project. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/):

* **0.x.y** – beta. **1.0.0** is the first version considered complete.
* **x.Y.0** – new features (new registers, new options).
* **x.y.Z** – bug fixes, documentation, tests.
* Changes that could alter an entity ID (key renamed/removed, platform changed, unique ID scheme changed) are
  **breaking changes**. They are marked in bold here and need a migration path.

## [2026-11-05]

### Changed
- README in English; German version moved to `README.de.md`. CHANGELOG and `CLAUDE.md` in English.
- README: warning not to delete and re-add the integration (entity IDs would be lost), see #7.

## [0.3.0] – 2026-11-05

### Added
- **Installation equipment** in the setup dialog and in the options: mixing circuits 1–3, cooling, pool,
  room unit. Pre-filled from the equipment registers (discrete inputs 10002–10011) during setup.
  Deselected parts are not polled and get no entities; their registry entries and entity IDs are kept and
  come back when the part is switched on again.
- Tests for pre-fill, deselect/reselect and for entries without the equipment option.

### Changed
- **Display names grouped by area** ("Heizen: Sollwert", "Warmwasser: Temperatur", "Mischkreis 1: Vorlauf",
  "Status: Betriebsart", "Energie: Strom Heizen" …) so the device page is sorted. Keys, unique IDs and existing
  entity IDs do **not** change; only display names of entities without a custom name change visibly.
- Limit, minimum and maximum values (return limit, hot water min/max/limit, mixing circuit min/max, return
  external) are now in the *Diagnostic* section.
- Entries created before 0.3.0 keep all entities until the equipment is changed in the options.

## [0.2.1] – unreleased

### Added
- Entity contract: `tests/fixtures/entity_contract.json` and `tests/test_contract.py` fail CI when a key is
  removed, renamed or moved to another platform.
- Test for the unique ID scheme `<entry_id>_<key>`.
- `tools/gen_contract.py` adds new keys to the contract (never removes anything).
- Version check in CI (`tools/check_version.py`): the manifest version must appear in the CHANGELOG, a git tag
  `vX.Y.Z` must match the manifest version.
- `CLAUDE.md` with the working rules for the repository.

## [0.2.0] – 2026-10-25

Documented retroactively (there were no tags so far).

### Added
- Full coverage of the SHI registers of the reference installation: numbers, selects, mixing circuits,
  circulation pump, status bits (compressor, auxiliary heater).
- `tools/gen_yaml.py` (legacy) generates an equivalent YAML `modbus:` configuration.
- README: migration from YAML, separation from the native Luxtronik integration, measured deviations.

## [0.1.0] – 2026-10-24

### Added
- First version of the integration with config flow, options flow and reconfigure flow.

[Unreleased]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/2f54427...v0.2.0
[0.1.0]: https://github.com/Bankaifan/ha-luxtronik-shi/commit/2f54427
