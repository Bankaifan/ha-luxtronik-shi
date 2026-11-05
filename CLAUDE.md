# Working rules for this repository

Home Assistant integration `luxtronik_shi` for alpha innotec / Luxtronik heat pumps via the Smart Home
Interface (SHI, Modbus/TCP). The integration **writes to a heating system in production** and is driven by the
Heat Pump Optimizer (HPO). Stability comes before features.

## Hard rules

1. **Entity contract.** Unique IDs are `<entry_id>_<key>`. Keys in `registers.py`, the status bit keys in
   `binary_sensor.py` and `online` must never be renamed, removed or moved to another platform.
   `tests/test_contract.py` enforces this. Add new keys with `python tools/gen_contract.py`.
   Do not change the unique ID scheme without a registry migration (`async_migrate_entries`), a test and the
   owner's approval.
   Keys the HPO of the reference installation depends on (selection): `flow`, `return`, `outside`, `dhw`,
   `compressor_thermal_power`, `energy_el_heating`, `aux_heater_1`, `cfg_heating_setpoint`, `cfg_mk1_setpoint`,
   `heating_block`, `dhw_block`, `circulation`. Never make these depend on an optional equipment part other
   than the one they belong to (`cfg_mk1_setpoint` → `mk1`).
2. **Display names may change, keys may not.** Names (`name_de`/`name_en`) may change; existing entity IDs stay
   in the registry. Generate translations only with `python tools/gen_translations.py`, never edit the JSON
   files by hand.
3. **No invented register facts.** Address, data type, scale, range and effect only with a source:
   - `python-luxtronik` (Bouni/python-luxtronik, `luxtronik/definitions/{inputs,holdings}.py`, MIT),
   - a measurement on the reference installation (LWDV 91-1/3, FW 3.92.3) with a description,
   - otherwise mark it as **open** and expose it as a raw value (`raw_<address>`, disabled by default).
4. **Writable registers** only with a test against `tests/fake_shi.py`, including read-back. No new writes
   without a value range.
5. **Never test against real devices or a real Home Assistant.** Simulation only.
6. **Do not increase polling load** without reason: block reads, `every` for rarely needed values.

## Versioning

* `0.x.y` beta, `1.0.0` first complete version. `x.Y.0` new feature, `x.y.Z` fix/docs/tests.
* Every change gets an entry under `## [Unreleased]` or the upcoming version in `CHANGELOG.md`.
* The version lives in `custom_components/luxtronik_shi/manifest.json`; `tools/check_version.py` checks
  manifest, CHANGELOG and tag.
* **Releases are automatic.** Whoever prepares a PR decides whether it releases: to release, bump the manifest
  version per the rules above and rename `## [Unreleased]` to `## [X.Y.Z] – YYYY-MM-DD` (keep an empty
  `## [Unreleased]` above it, update the compare links). On merge, `.github/workflows/release.yml` creates tag
  `vX.Y.Z` and the GitHub release from that CHANGELOG section. Without a bump, entries just collect under
  `[Unreleased]`. Never create tags by hand.
* State the proposed version and the reason (feature/fix/breaking) in the PR description, so the owner can
  object during review.

## Workflow

* Work on a branch and open a pull request; never push to `main` (protected). No force push.
  The owner reviews and merges.
* `main` requires a **linear history**; PRs are merged with *Squash and merge*. Therefore:
  - branch every PR directly from the current `main`, **no stacked PRs**;
  - **no merge commits** in a branch (never `git merge main` into it);
  - if a branch falls behind and conflicts, do not rebase/force-push: create a fresh branch from `main`,
    re-apply the changes (e.g. `git cherry-pick`), open a new PR and close the old one with a link.
  - Squash uses the PR title as commit subject: keep PR titles meaningful and in English.
* Commit author: `git config user.name "Daniel"` and
  `git config user.email "476059+Bankaifan@users.noreply.github.com"`. Every commit message ends with the
  trailer `Co-authored-by: Claude <noreply@anthropic.com>`.
* **Everything on GitHub in English:** commit messages, PR titles and descriptions, issues, comments, labels,
  CHANGELOG, README and code comments. German only in `README.de.md` and the German translations.
* README changes go into both `README.md` (English) and `README.de.md` (German).
* Before opening a PR: `ruff check .` and `pytest --timeout=60` pass.
* Breaking changes only after consultation, in bold in the CHANGELOG, with migration notes in the README.

## Commands

```bash
pip install -r requirements_test.txt pytest-timeout ruff
ruff check . && pytest --timeout=60
python tools/gen_translations.py   # after name changes
python tools/gen_contract.py       # after adding keys
python tools/check_version.py      # version/CHANGELOG
```
