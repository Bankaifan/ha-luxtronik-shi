# 0002 Protocol library on PyPI

Status: proposed (design only, awaiting Daniel's approval; no code moves in this PR). Issue #26.

## Context
A Home Assistant Core submission requires that the device protocol lives in a PyPI library and the integration only
depends on it. Today the protocol code sits inside `custom_components/luxtronik_shi/`. This ADR is based on the
imports as they are now (measured with `grep` on the package); anything not verified is marked **open**.

## Scope: what moves, what stays
Moves (no Home Assistant import today):
- `registers.py` (1458 lines): `Register`, `RegKind`, `DType`, the register tuples, `decode`, `encode_int16`,
  `raw_in_range`, `usable`, `reports_not_available`, `active_registers`, `features_of`, `firmware_version`,
  `SETPOINT_GROUPS`, `CONTROL_MODES`, `CAPABILITIES`, `FIRMWARE_PARTS`, derived-value descriptions
  (`DerivedSensor`, `DifferenceSensor`, `DerivedFlag`, `TriggerAction`), `WindowedCop`/`overall_cop`, `area_of`.
  It imports only `dataclasses` and `typing`; its docstring-level contract is that tools load it standalone.
- `modbus_client.py` (99 lines): `LuxtronikModbusClient`, `ModbusCommError`, `ModbusIllegalAddress`. Depends on
  `pymodbus` and `registers.RegKind` only.
- Block planning: `plan_blocks`, `Block`, `MAX_BLOCK` currently live in `coordinator.py` (around lines 83-140),
  not in `poll_plan.py`. They are pure functions of `Register` and move after being split out of the coordinator.
- The pure part of `block_views.py` (`mode_for`, `power_for`, `writes_for_mode/off/on`, `Write`): **open**, it shares
  a module with coordinator access and must be split first.

Stays in the integration:
- `coordinator.py` (state, scheduling, restore, deferred writes, repairs; imports `homeassistant`), all platforms,
  `config_flow.py`, `entity.py`, `diagnostics.py`, `compat.py`, `const.py` (domain, option keys).
- `poll_plan.py`: it decides *which registers* from the entity registry (`er`, `HomeAssistant`) and uses `DOMAIN`.
  It stays and only consumes the library's register tuples.
- Presentation fields of `Register` (`name_de`, `name_en`, `device_class`, `state_class`, `platform`, `diagnostic`,
  `enabled_default`, `config`) are Home Assistant concepts, not protocol facts: **open**, see questions.
- Translations, icons, dashboard and README generators and `tests/contract.py` stay in this repo.

## Public API (proposal)
- `luxtronik_shi_protocol.registers`: `Register`, `REGISTERS`, `active_registers(features)`, `decode`, `encode_int16`
  (exists today), `RegKind`, `DType`. **New, not in the code today:** `encode` as a generic writer with a range check
  (today only `encode_int16` and `raw_in_range` exist). Its introduction is a behaviour addition with its own tests and
  is not part of the mechanical move in steps 2-3.
- `luxtronik_shi_protocol.planning`: `plan_blocks`, `Block`, `MAX_BLOCK` (today `plan_blocks` uses the fixed
  `MAX_BLOCK`). **Changed:** a `max_block` parameter (default `MAX_BLOCK` = 40, same behaviour) is a new signature and
  is added in its own slip; step 1 moves the function with its signature unchanged.
- `luxtronik_shi_protocol.client`: `LuxtronikModbusClient`, `ModbusCommError`, `ModbusIllegalAddress`.
- Everything else is private (underscore); the integration imports only from these three modules.
- Fully typed (`py.typed`), no Home Assistant dependency, runtime dependency `pymodbus` with the current range.

## Versioning
- Semver. `0.x` while the integration is beta, `1.0.0` together with the integration's `1.0.0`.
- Adding a register or field: minor. Changing key, address, dtype, scale or range of an existing register: major
  (before 1.0: minor with a CHANGELOG note), because HPO-relevant keys (AGENTS.md domain rule 1) must not change
  silently.
- The integration pins `luxtronik-shi-protocol==X.Y.Z` in `manifest.json` `requirements` (exact pin, Core style);
  Dependabot proposes bumps.

## Package name candidates
`luxtronik-shi` (import name would clash with the integration domain inside this repo), `luxtronik-shi-protocol`
(proposed), `pyluxtronik-shi`. **Open:** PyPI availability not checked.

## Keeping the register map in sync
- The library is the single source of the register map. `registers.py` is removed from the integration; there is
  no second copy and therefore nothing to drift. Register facts keep their `source` field (domain rule 3).
- Development stays in one repository first: the library lives in this repo (e.g. `protocol/`), is installed
  editable for `make check` and CI (dev only, never shipped with the integration; see the release rule under
  Migration steps), and is released from here. A separate repository is only needed if Core
  reviewers ask for it (**open**). This keeps register change, generator output and tests in one PR.
- Generators (`tools/gen_*.py`) import `registers` standalone today (`import registers`). They switch to the
  library; their output files must not change, the `make check` generator drift check proves it.
- `tests/fixtures/entity_contract.json` and `tests/test_contract.py` stay in the integration and keep running
  unchanged; they detect any key or platform change caused by a library bump.
- `tests/fake_shi.py` and the writable-register read-back tests stay (they test the integration end to end).
  The library gets its own unit tests (decode/encode round trips, `plan_blocks`, client against `fake_shi`),
  moved from `test_registers.py`, `test_client.py` and parts of `test_poll_plan.py`.
- Order for a register change once the pin is a published version: library PR and release first, then a PR that
  bumps the pin. **Open:** whether this two-step cost is acceptable for small register fixes; the alternative is a
  path requirement for development only.

## Publishing
- PyPI Trusted Publishing (OIDC) from a dedicated GitHub Actions workflow; no API token in the repo or in secrets.
  Needs a PyPI project with the publisher configured by Daniel.
- Workflow changes are code-owner paths (AGENTS.md limit 5): they need Daniel's OK and are a separate slip.
- Library releases are automatic from a CHANGELOG section like the integration's (`release.yml` pattern); no tags
  by hand.

## Domain rules during the migration
- No invented register facts: the move is mechanical; address, dtype, scale, range and `source` are copied
  unchanged and `entity_contract.json` must stay identical in every migration PR.
- Writable registers keep their `fake_shi` read-back tests and value ranges.
- No extra polling load: `plan_blocks` and `MAX_BLOCK` keep their behaviour; `tests/test_poll_plan.py` and the
  block tests pass unchanged.
- English and German texts: if the names stay in the library, translations still come only from
  `tools/gen_translations.py`.

## Migration steps (each a separate small slip, only after approval)
1. Split `plan_blocks`/`Block` out of `coordinator.py` and the pure part out of `block_views.py` (in place, no
   packaging yet). No release.
2. Create the package skeleton (`pyproject.toml`, `py.typed`, CI test job) and move `registers.py` unchanged;
   the integration imports from it; generators adapt.
3. Move `modbus_client.py` and `plan_blocks`; move the matching tests.
4. Trusted-publishing workflow and first PyPI release (needs Daniel: PyPI project, workflow change).
5. Switch `manifest.json` `requirements` to the published pin, drop the in-repo path install.
6. Docs: CONTRIBUTING, HANDOVER, README developer notes.

### Release rule for the steps (chosen)
- The integration is **not released** between step 2 and step 5. Steps 2, 3 and 4 carry `Proposed version: no release`
  in their PR bodies and do not bump `manifest.json`, so `release.yml` cuts no tag for them.
- Step 5 is the first point where a release of the integration may happen. It must not be cut before the published
  pin is in `manifest.json` `requirements`, because HACS and Home Assistant install only `custom_components/` plus the
  manifest requirements.
- The in-repo editable install (`protocol/` for `make check` and CI) is **development only**. It never reaches a
  released integration: the release artifact carries the pin, not the path.
- Step 4 (PyPI release of the library) comes before step 5, so the pin always resolves on PyPI when it is set.

## Open questions for Daniel
1. Package name (see candidates) and who owns the PyPI project.
2. Monorepo first (proposed) or a separate repository from the start?
3. Presentation fields in `Register` (`name_de/en`, `device_class`, `platform`, ...): keep in the library (simple,
   one map) or split into a protocol part and an integration part (cleaner for Core review, more work and a
   second table to keep in sync)?
4. `block_views` and the derived-value descriptions (`DerivedSensor`, `TriggerAction`): library or integration?
5. Is the two-step flow (library release, then pin bump) acceptable for register fixes?
6. Is the library version policy before 1.0 (see Versioning) ok?
7. Should the library work without `pymodbus` (a transport interface)? Proposed: no.
