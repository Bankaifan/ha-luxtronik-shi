# Changelog

All notable changes to this project. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
versioning follows [Semantic Versioning](https://semver.org/):

* **0.x.y** – beta. **1.0.0** is the first version considered complete.
* **x.Y.0** – new features (new registers, new options).
* **x.y.Z** – bug fixes, documentation, tests.
* Changes that could alter an entity ID (key renamed/removed, platform changed, unique ID scheme changed) are
  **breaking changes**. They are marked in bold here and need a migration path.

## [Unreleased]

### Action required
- **Write ranges of nine settings now follow the python-luxtronik source (`holdings.py`), with the owner's approval.**
  The Home Assistant number, climate and water heater entities (and so the limits an optimizer reads from them)
  change as follows. Check automations and optimizers that rely on the old limits.

  | Key | Address | Old range | New range |
  |---|---|---|---|
  | `cfg_heating_setpoint` (also the climate entity) | 10001 | 10–70 °C | 15–75 °C |
  | `cfg_heating_offset` | 10002 | −5 … +5 K | −20 … +20 K |
  | `cfg_dhw_setpoint` (also the water heater entity) | 10006 | 10–65 °C | 30–75 °C |
  | `cfg_dhw_offset` | 10007 | −10 … +10 K | −20 … +20 K |
  | `cfg_mk1_setpoint` | 10011 | 10–70 °C | 20–65 °C |
  | `cfg_mk1_offset` | 10012 | −10 … +10 K | −5 … +5 K |
  | `cfg_mk1_cool_setpoint` | 10016 | 5–40 °C | 5–25 °C |
  | `cfg_mk1_cool_offset` | 10017 | −10 … +10 K | −5 … +5 K |
  | `cfg_overall_offset` | 10066 | −10 … +10 K | −20 … +20 K |

  Ranges got wider for the heating and hot water settings and the overall offset, and narrower for mixing circuit 1
  (setpoint, offset, cooling setpoint and offset). Values outside the new range are rejected before anything is
  written. Keys and unique IDs are unchanged.
- **Three keys of already released entities were renamed (with the owner's approval): `raw_10109` is now
  `outside_temp_average`, `raw_10110` is now `heat_source_input` and `raw_10112` is now `max_flow_temp`.** Your entities are kept: on start the integration moves
  the registry entries to the new unique IDs, so entity IDs, history, customised names, areas and the enabled/disabled
  state stay as they are. Only the name is new for 10110 and 10112 (*Temperature: heat source inlet*, *Temperature:
  flow maximum*; 10109 keeps *Temperature: outside average*) and the unique ID ends with the new key. Check
  automations, templates or tools that look entities up by the old unique ID `<entry_id>_raw_10109` /
  `<entry_id>_raw_10110` / `<entry_id>_raw_10112`; entity IDs are unaffected.
- `max_flow_temp` (10112) is now a temperature in °C (0.1 °C resolution, uint16, from python-luxtronik) instead of a
  unitless raw number. If you had enabled it, the value changes from e.g. `600` to `60.0`, and Home Assistant starts
  long-term statistics for it.
- **The options of the five level selects now follow the python-luxtronik `LevelMode` source.** `cfg_heating_level`
  (10003), `cfg_dhw_level` (10008), `cfg_mk1_level` (10013), the mixing-circuit-2/3 levels and `cfg_overall_level`
  (10067) previously offered `evu_lock`/`reduced`/`normal`/`boost` (raw 0/1/2/3); they now offer
  `normal`/`increased`/`increased2`/`decreased` (raw 0/1/2/3). So the value written for a given selection changes
  (e.g. `normal` wrote 2 before and writes 0 now). Keys and unique IDs are unchanged. Check automations or optimizers
  that set or read a level option.

### Added
- Binary sensors for the status bits of heat generator state (10000): `heatpump_vd2_status`, `heatpump_zwe2_status`
  and `heatpump_zwe3_status`, from python-luxtronik (bit 1, bit 3 and bit 4). All three are disabled by default.
  `heatpump_vd2_status` and `heatpump_zwe2_status` show the same bits as `compressor_2` and `aux_heater_2`.
- Undocumented raw values, all disabled by default and polled every 30th cycle: inputs 10352, 10353, 10410–10413, 10416,
  10417 and 10500–10502 (`unknown_input_*` in python-luxtronik), as `raw_<address>`. Their meaning is unknown, so they
  stay raw values. Entries created before 0.3.0 (no equipment option) do not get them, so their polling load stays the same.
- `cfg_room_setpoint` (holding 10060): writable room-temperature setpoint of the room control unit (number,
  20–40 °C, 0.5 °C step; only with the *room unit* equipment option). Firmware V3.92.3 exposes this address as the
  writable `RBE_RoomTemperatureSetpointRegister` (target `RBE_RT_Soll`); see
  `docs/firmware-3.92.3-shi-analysis.md`. 10060 was never released as a raw value, so there is no migration.

### Changed
- **`raw_10109` renamed to `outside_temp_average`, `raw_10110` to `heat_source_input` and `raw_10112` to
  `max_flow_temp`** (python-luxtronik `outside_temp_average`, `heat_source_input` and `max_flow_temp`). Registry migration at start-up keeps the entity IDs, see *Action required*. The old keys stay
  in the entity contract fixture; `RENAMED_KEYS` in `registers.py` tells the contract test that they were renamed on
  purpose.

### Tests
- `tests/test_migration.py`: the renamed entities keep their entity ID, state, unit and disabled flag after the
  migration (also for entries without equipment option and when the new unique ID already exists); the added raw
  values are read, disabled and not polled by entries without equipment option. The contract test accepts a missing
  key only if `RENAMED_KEYS` maps it to a key on the same platform.
- Write and read-back test for the pool lock switch (`pool_block`, 10053) and the range limits of the power limit
  (`cfg_power_limit_mode` 10040, `cfg_power_limit` 10041). The registers were already exposed; ranges match
  python-luxtronik (`lock_swimming_pool` 0..1, `lpc_mode` 0..2, `pc_limit` 0..300 kW/10).
- Write and read-back test for all writable holdings of mixing circuits 2 and 3 (`cfg_mk2_*`, `cfg_mk3_*`: mode,
  setpoint, offset, level, and the cooling mode, setpoint and offset), including the range limits. The registers were
  already exposed; ranges match python-luxtronik (`mc{2,3}_heat_setpoint` 20..65 °C, `mc{2,3}_heat_offset` and
  `mc{2,3}_cool_offset` -5..5 K, `mc{2,3}_cool_setpoint` 5..25 °C, modes 0..3).
- Write and read-back test with range limits for `cfg_room_setpoint` (10060, 20..40 °C), and a check that the level
  selects expose the python-luxtronik order (`normal`/`increased`/`increased2`/`decreased`).

### Documentation
- README (English and German) reworked: banner and badges, a highlights section and table of contents, installation
  first, climate and water heater in one section, a new *Diagnostics* section, the YAML migration collapsed, and
  the notes on volatile holding registers and on the release workflow brought up to date. New `assets/banner.svg`
  (own design) rendered to `assets/banner.png`.
- README (English and German): features and notes describe the writable entities of mixing circuits 2 and 3 with
  their ranges, the pool block, the power limit and the disabled status bits `heatpump_vd2_status`,
  `heatpump_zwe2_status` and `heatpump_zwe3_status`.
- README (English and German): notes on the renamed keys and on the added raw values.

## [0.8.2] – 2026-11-06

### Changed
- Releases are now created only after the *Validate* workflow (hassfest, HACS action, tests) succeeded for the
  pushed commit on `main`, and the release targets exactly that commit. Before, the release workflow ran in parallel
  with the validation. No change to the integration itself.

## [0.8.1] – 2026-11-06

### Fixed
- Deprecation warnings on newer Home Assistant releases: the climate and water heater entities now use
  `_attr_native_temperature_unit`, `native_current_temperature` and `native_target_temperature` when the Home Assistant
  base class provides them, and the previous attribute names on older releases (minimum 2025.8). Units, values and
  setpoint writes are unchanged. No entity, key or ID changes.

## [0.8.0] – 2026-11-06

### Added
- Repair issue *Heat pump firmware is outdated* (warning, issue #24): raised when the firmware read from
  10401/10402 is below 3.92.0, because the circulation pump and extra hot water entities need 3.92.0 or later and
  have no values on older firmware. Removed when the firmware is 3.92.0 or later and when the entry is unloaded.
  The issue ID contains the config entry ID. No new registers, no extra Modbus reads, no entity changes. Texts are
  generated by `tools/gen_translations.py`.
- Repair issue *Values changed after connection outage* (warning): when the SHI was unreachable and comes back with
  a different heating block, hot water block, heating mode or hot water mode (`heating_block`, `dhw_block`,
  `cfg_heating_mode`, `cfg_dhw_mode`), the issue lists the old and new values. Notice only, nothing is written back.
  It is removed when the values match the pre-outage values again or when dismissed. The pre-outage values are kept
  in memory only and are lost on a Home Assistant restart. No new registers, no extra Modbus reads, no entity
  changes. Texts are generated by `tools/gen_translations.py`.
- Beta release channel: versions of the form `X.Y.Z-beta.N` are published as GitHub pre-releases, which HACS offers
  only to users who enable "Show beta versions". Stable releases are unchanged.

### Documentation
- Notes: values written through the integration can fall back to the controller default after a controller restart
  or power cut (volatile SHI holding registers). The integration does not detect or correct this (issue #9).

## [0.7.0] – 2026-11-05

### Added
- Repair issue (issue #24), shown under Settings > System > Repairs and deleted automatically when the condition ends
  (also when the entry is unloaded): *SHI not reachable* (error), raised when all polls failed for 10 minutes in a row.
  The issue ID contains the config entry ID, so several heat pumps do not clash. No new registers, no extra Modbus
  reads, no entity changes. Texts are generated by `tools/gen_translations.py`.
- Calculated COP sensors (issue #23), no new registers and no extra Modbus reads: `cop` (thermal power 10300 / electric
  power 10301, in the main heat pump device) and `cop_heating` / `cop_dhw` (thermal / electric energy counters of
  heating and hot water, 10322/10312 and 10324/10314, in the *Heating* / *Hot water* device). A sensor is unknown
  (never a number) when an input is missing, the electric value is zero or below the minimum (200 W / 1 kWh), the
  thermal value is zero or negative (e.g. defrost), the result is above 12, or an energy counter went backwards since
  the previous reading. These limits are a design choice, not register facts.
- Water heater entity for domestic hot water (issue #20), in the *Hot water* device. Target temperature writes the
  existing hot water setpoint register (10006, 10 ... 65 °C in 0.5 K steps, out-of-range values are rejected before
  anything is written); the operation modes are the options of the existing hot water mode register (10005: `off` /
  `setpoint` / `offset` / `level`). The current temperature is the hot water temperature (10120). Every write is read
  back, like for the number and select entities. New key `water_heater_dhw`; no new registers. Enabled by default on
  new installations, disabled by default for entries that already had entities before this change (enable it in the
  entity settings). The Heat Pump Optimizer does not control hot water through this entity; do not let a planner and
  this entity write the same registers at the same time.
- Climate entity for the heating circuit (issue #19), in the *Heating* device. Target temperature writes the existing
  heating setpoint register (10001, 10 ... 70 °C in 0.5 K steps, out-of-range values are rejected before anything is
  written); *Off* / *Heat* write the existing heating mode register (10000: `off` / `setpoint`). The current
  temperature is the flow temperature. Every write is read back, like for the number and select entities. Other
  controller modes (offset, level) show as *Heat* and are listed in the `controller_mode` attribute. New key
  `climate_heating`; no new registers. Enabled by default on new installations, disabled by default for entries that
  already had entities before this change (enable it in the entity settings). Planners such as the Heat Pump Optimizer
  write the same registers: do not use both at once.
- Diagnostics download (issue #21) for bug reports: integration and Home Assistant version, selected equipment,
  capability flags, firmware and the last polled register values (raw and decoded) grouped by block. Host, MAC
  address and unique ID are redacted. It uses the data of the last poll, no extra Modbus reads.
- GitHub issue forms for bug reports and supported model reports (English), under `.github/ISSUE_TEMPLATE/`.
  Blank issues are disabled.
- Register reference `docs/registers.md` (issues #27, #3): a table of all registers with address, type, data type,
  scale, unit, range and status. Generated from the register map by `tools/gen_register_docs.py`; a test fails when the
  file is out of date. The status column reads from the register map and shows `open` until the map records sources.

### Changed
- CI runs the tests against the minimum Home Assistant version declared in `hacs.json` (2025.8.0) in addition to the
  newest ones. The minimum passes, so it stays at 2025.8.0.

## [0.6.0] – 2026-11-05

### Added
- **Automatic discovery via DHCP.** Heat pumps with a Luxtronik MAC prefix or the hostname `wp-novelan` are offered
  under *Discovered* – but only if the Smart Home Interface answers on Modbus/TCP (port 502, unit ID 1); other
  devices are ignored silently. Setup then asks for a name and the equipment. Matchers taken from
  BenPru/luxtronik (MIT).
- Discovery keeps existing entries up to date: a known heat pump (matched by MAC) with a new IP address gets the new
  address and is reloaded; an entry created by hand learns its MAC address the first time it is discovered.

## [0.5.0] – 2026-11-05

### Action required
- Entities move from the single heat pump device to sub-devices (*Heating*, *Hot water*, *Cooling*, *Pool*).
  **Entity IDs do not change**, automations, scripts and templates that use entity IDs keep working.
  Check automations that use *device* triggers, conditions or actions on the heat pump device for heating or
  hot water entities, and re-select the new sub-device there.
- Display names inside the sub-devices are shorter (e.g. *Sollwert* on device *Heizung*). Dashboards that show
  the default name change accordingly.

### Added
- Sub-devices like the Luxtronik controller menus: heat pump (main), heating, hot water, and cooling/pool when
  selected in the equipment (#8). Created through the device registry and linked to the main device.
- CI job `tests-latest-ha` runs the tests against the newest Home Assistant test harness (Python 3.14).
- CI: `validate.yml` restricts the `GITHUB_TOKEN` to read access (CodeQL finding); only the HACS job may comment on PRs.

### Changed
- Firmware version is written to the device registry instead of mutating the shared `DeviceInfo`.

## [0.4.0] – 2026-11-05

### Action required
- Only if you had enabled the raw values 10109 or 10110: they are now temperatures in °C. Home Assistant may
  report a unit change for their long-term statistics; accept it in *Settings → Repairs*.

### Added
- Mixing circuits 2 and 3: mode, setpoint, offset and level for heating, mode/setpoint/offset for cooling
  (holdings 10020–10037, ranges from python-luxtronik). Available when the mixing circuit (and for cooling also
  *cooling*) is selected in the equipment options.
- Heat source outlet temperature (10111).
- Energy counters for cooling and pool (10316, 10318, 10326, 10328), with the matching equipment part.

### Changed
- 10109 and 10110 are no longer anonymous raw values: *Temperature: outside average* and *Temperature: heat
  source inlet* (signed, °C, enabled by default for new installs). 10112 is named *flow maximum* but stays a
  raw value, because python-luxtronik documents no unit or scale. Keys stay `raw_10109` etc. (entity contract).
- Entries without an equipment option (created before 0.3.0) do not get the registers added in 0.4.0, so their
  polling load stays the same. Save the equipment in the options to use them.

## [0.3.2] – 2026-11-05

### Added
- Integration icon in `custom_components/luxtronik_shi/brand/` (`icon.png`, `icon@2x.png`), shown by Home Assistant
  2026.3+ and the Marketplace. Source drawing in `assets/icon.svg`. No manufacturer logos are used.
- Manifest `categories`: `climate.heat_pumps_air_conditioning` (Marketplace/HACS catalog category).

### Changed
- `hacs.json`: removed `render_readme` (no longer a documented key).
- CI: the HACS action no longer skips the `brands` check.
- README: installation via the Home Assistant Marketplace (2026.11+) alongside HACS.

## [0.3.1] – 2026-11-05

### Added
- Automatic releases: when a version bump reaches `main`, the workflow `release.yml` creates the tag `vX.Y.Z`
  and a GitHub release with the matching CHANGELOG section as notes.
- Pull requests that bump the version are checked for a dated CHANGELOG section.

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

## [0.2.1] – not released separately (included in 0.3.0)

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

[Unreleased]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/v0.8.2...HEAD
[0.8.2]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Bankaifan/ha-luxtronik-shi/compare/2f54427...v0.2.0
[0.1.0]: https://github.com/Bankaifan/ha-luxtronik-shi/commit/2f54427
