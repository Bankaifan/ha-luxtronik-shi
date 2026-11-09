# Contributing

Thanks for helping with this integration. It writes to real heating systems, so a few rules matter more here than in
a typical project.

## Before you start

* Open an issue first for anything larger than a fix, so we can agree on the approach.
* Use the issue forms (bug report, model report, feature request). Please include the controller model and firmware.
* Never test against a real heat pump or a production Home Assistant in a pull request. Use the simulator in
  `tests/fake_shi.py`.

## Rules for changes

* **Entity keys are a contract.** `tests/test_contract.py` detects every change to a key, platform or option set. A
  wrongly modelled entity may be fixed, but then the change needs an *Action required* CHANGELOG section, migration notes
  in both READMEs, orphan cleanup and an updated `tests/fixtures/entity_contract.json` (see [AGENTS.md](AGENTS.md)).
  New keys are added with `python tools/gen_contract.py`.
* **Display names may change** freely. Translations are generated with `python tools/gen_translations.py`;
  do not edit the JSON files by hand.
* **No invented register facts.** Address, data type, scale, range and effect need a source: python-luxtronik, a
  measurement on a real installation (with a description), or the register is marked *open* and exposed as a raw value.
* **Writes need a test.** Every writable register needs a test against `tests/fake_shi.py`, including the read-back and
  a value range.
* **Do not increase polling load** without a reason. Use block reads and `every` for rarely needed values.

## Pull requests

1. Branch from the current `main`. Keep one topic per pull request.
2. Run the checks:

   ```bash
   pip install -r requirements_test.txt pytest-timeout ruff
   ruff check . && pytest --timeout=60
   python tools/check_version.py
   ```

3. Add an entry under `## [Unreleased]` in `CHANGELOG.md`. Put a `### Action required` section first if users must
   do something after updating.
4. Write user-facing text in English. Documentation changes go into **both** `README.md` (English) and `README.de.md`
   (German).
5. Describe the change and whether it should be released (feature, fix, or documentation) in the pull request.

Releases are automatic: a version bump in `manifest.json` that reaches `main` creates the tag and the GitHub release
from the CHANGELOG section.

## Scope

This integration covers the Smart Home Interface (SHI, Modbus/TCP) of alpha innotec / Luxtronik controllers. Features
that need the native Luxtronik protocol (port 8889) belong in a different project.

## Publishing a beta

To publish a beta, bump `version` in `custom_components/luxtronik_shi/manifest.json` to `X.Y.Z-beta.N`
(for example `0.8.0-beta.1`), add a `## [X.Y.Z-beta.N] – YYYY-MM-DD` section to `CHANGELOG.md` and open a PR.
On merge, the release workflow tags `vX.Y.Z-beta.N` and publishes a GitHub pre-release. The final release later
uses the plain `X.Y.Z` version and its own CHANGELOG section.
