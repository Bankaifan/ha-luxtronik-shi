# Working rules

Home Assistant integration `luxtronik_shi` for alpha innotec / Luxtronik heat pumps via the Smart Home Interface
(SHI, Modbus/TCP). It **writes to a heating system in production** and is driven by the Heat Pump Optimizer (HPO).
Current state: HANDOVER.md. Decisions: docs/decisions/. Roles: .agents/roles/. Contributors: CONTRIBUTING.md.

## Limits (not negotiable)
1. No secrets in code, logs, issues or PRs. Credentials only from environment variables / GitHub Secrets.
2. Nothing irreversible without Daniel's explicit OK: deleting repos or branches holding other people's work,
   releases by hand, payments, permission changes.
3. Never push to `main`, no tags by hand. Always branch + PR. Rebase and force-push are allowed on your own agent
   branches, never on `main`.
4. Read-only checks against the real installation and the real Home Assistant are allowed. Anything that writes to
   the real heat pump or to Home Assistant needs Daniel's OK. Tests use the simulator.
5. Changes to CI protection, permissions, workflows or this file go through the security reviewer. Changes to the
   CODEOWNERS paths (CODEOWNERS, rulesets, trust logic, release workflow) need Daniel's OK.
   Scout app token: contents, pull-requests, vulnerability-alerts, security-events read; issues write.

## Domain rules
1. **Correctness before continuity.** The project is in testing and Daniel is its only user. An entity that models a
   register wrongly (wrong platform, an option the firmware does not implement, a unit, state or name that gives a
   wrong idea of what the register does) is **fixed**, not preserved: remove, rename or move it to another platform.
   Reviewers recognise misleading models themselves and say so. Every such breaking change needs, in the same PR:
   - a `### Action required` subsection **first** in the CHANGELOG section of the version, naming every removed,
     renamed or moved entity and what the user must do, plus a migration note in both READMEs;
   - orphan cleanup: a renamed key moves its registry entry (`RENAMED_KEYS`, `async_migrate_renamed_keys`), a removed
     or moved entity deletes the old entry at setup (`REMOVED_KEYS`, `REMOVED_ENTITIES`,
     `async_remove_obsolete_entities`);
   - the hand-edited fixture `tests/fixtures/entity_contract.json` (unique IDs are `<entry_id>_<key>`).
     `tests/test_contract.py` is a change detector, not a ban: new keys via `python tools/gen_contract.py`,
     removals, renames and platform moves by hand, never silenced.

   Keys the HPO depends on: `flow`, `return`, `outside`, `dhw`, `compressor_thermal_power`, `energy_el_heating`,
   `aux_heater_1`, `cfg_heating_setpoint`, `cfg_mk1_setpoint`, `heating_block`, `dhw_block`, `circulation` (a button
   since 0.17.0), the option keys of the mode selects. If one changes (key, platform, option set), the PR says so under
   *Action required* so the HPO configuration is updated. They never depend on an optional equipment part other than
   their own (`cfg_mk1_setpoint` -> `mk1`).
2. **Display names may change freely** (`name_de`/`name_en`, no migration). Translations only via
   `python tools/gen_translations.py`, never by hand.
3. **No invented register facts.** Address, data type, scale, range and effect only with a source:
   `python-luxtronik` (Bouni/python-luxtronik, `luxtronik/definitions/{inputs,holdings}.py`), the firmware analysis
   `docs/firmware-3.92.3-shi-full-analysis.md` (graded *proven*), or a described measurement on the reference
   installation (LWDV 91-1/3, FW 3.92.3). Otherwise it is **open** and exposed as a raw value (`raw_<address>`,
   disabled by default).
4. **Writable registers** only with a test against `tests/fake_shi.py` including read-back, and with a value range.
   No untested change of any kind.
5. **Do not increase polling load** without reason: block reads, `every` for rarely needed values.
6. **Everything a user sees exists in English and German:** entity, option, state and attribute names, errors
   (`translation_key`), repair issues, logbook, flow and option texts, both READMEs. No user-facing literal in code.

## Versioning and release
- `0.x.y` beta, `1.0.0` first complete version. `x.Y.0` feature, `x.y.Z` fix/docs/tests.
- Every change gets a CHANGELOG entry under `## [Unreleased]` (or the upcoming version). The version lives in
  `custom_components/luxtronik_shi/manifest.json`; `tools/check_version.py` checks manifest, CHANGELOG and tag.
- **Releases are automatic.** To release, bump the manifest and rename `## [Unreleased]` to
  `## [X.Y.Z] – YYYY-MM-DD` (keep an empty `## [Unreleased]` above, update the compare links). After the merge and a
  green *validate* run on `main`, `release.yml` tags and publishes from that section. Never tag by hand.
- The section is the release note shown in Home Assistant: anything users must do goes first under
  `### Action required`.
- The PR body states the proposed version and why (feature/fix/breaking), or "no release".

## How to work
- Small PRs branched from current `main`, rebase-merged: no stacked PRs, no `git merge main` into a branch. If a
  branch falls behind, rebase it (own branch) or cherry-pick onto a fresh one.
- Before review squash the branch into ONE commit on current `origin/main`; force-push to your own branch is allowed.
- Before the PR: `make check` (ruff, pytest, version, PR form, generator drift, actionlint, zizmor) is green. CI
  (*validate*) is the truth. Generators: `gen_translations`, `gen_contract`, `gen_entity_docs`, `gen_register_docs`, `gen_icons`,
  `gen_dashboard`; a generator diff in CI means you forgot to run it.
- Setup: `pip install -r requirements_test.txt pytest-timeout ruff` (CI: `bash tools/ci/install_tools.sh`).
- Claim only what you measured (command + output). Unsure: ask in the issue, mark facts "open", never guess.
- Size caps for this file and `.agents/roles/*.md` live in `docs/budgets.json` (checked by `make check`): shrink
  freely, raise a cap only by a deliberate edit there.
- Read only the files the task names. HANDOVER.md (max 60 lines) is rewritten by the orchestrator only; developer and
  fix runs put notes in the PR body.
- Everything on GitHub in English (files, commits, PR titles and bodies, issues, CHANGELOG, README, code comments);
  German only in `README.de.md` and the German translations. Talking to Daniel: German.
- README changes go into both `README.md` and `README.de.md`.

## Commits and PRs
- Author: `git config user.name "Daniel"` and `user.email "476059+Bankaifan@users.noreply.github.com"`.
  No `Co-authored-by` trailer.
- No tool or AI attribution of any kind in commits, PR bodies, issues or comments: no "Generated with ...", no
  claude.ai/code session link, no `Co-Authored-By` or `Claude-Session` trailer. Enforced by CI.
- PR title: English, ASCII only, meaningful. Body: what and why in a few lines, link the issue, proposed version.
  The form is enforced by CI (`tools/check/check_pr_form.py`).

## Review rounds and merging
Developer -> CI -> reviewer (only on green CI) -> at most 2 fix rounds (started automatically on `CHANGES_REQUESTED`
or on a red CI). Then the task restarts once on its own: the issue gets `restart:1` and a new slip, `agent:dev` is set
again and the old PR is closed as superseded. If the issue already has `restart:1`, the PR gets `needs-human` plus a
review request to Daniel (a label alone is not in his inbox) and waits for the orchestrator or Daniel. Do not start a
third round. A newer agent PR for the same issue closes the older one.
Merges are rebase merges done by auto-merge after the approver app's approval and green CI. Only security-relevant
files need Daniel as code owner (`.github/CODEOWNERS`, the release workflow, rulesets, the trust and guard tools, the
risk gate); every other security diff is gated by the AI security reviewer (status `security-review`). Only trusted input drives agents: issues by Daniel or labelled `approved`/`auto-ok` by Daniel; the reviewer
never runs PR code.
Also trusted: an issue the liveness guard wrote (`Overdue scheduled run`): author app plus a valid HMAC signature
(`tools/guard_mark.py`, secret `GUARD_KEY`, script steps only). No key, no trust. Unblocker and idea issues are never signed.
Big work (architectural, breaking, release-relevant, multi-PR) starts with a design study in `docs/design/` (see its
README); only its *Owner decisions* go to Daniel.

## Waiting for Daniel
Daniel approves only what needs him: PRs that change his CODEOWNERS paths (check `risk`, see `tools/ci/risk.py`),
`needs-human`, design owner decisions, dependabot majors, product decisions. Whoever parks
something with him leaves, as the LAST comment, a short plain-German note: what changes, the worst case, what the
reviewers recommend, one exact yes/no question that names what "ja" and what "nein" do; technical terms explained in
a few words. The same comment carries one hidden decision marker line,
`<!-- decision: yes=<action> no=<action> -->` (grammar and action ids: `tools/decision.py`). PRs get a review request to
Bankaifan; only issues that wait for him mention `@Bankaifan` once in that note. No other comment mentions him. Every
infra/security PR also needs the security reviewer (`.agents/roles/security-reviewer.md`, status `security-review`)
besides the normal review, agent-smoke and zizmor.

## Template sync
This repo follows `Bankaifan/agent-template` (`.agents/template.json`). `template-sync.yml` opens a weekly
`Template sync <sha>` issue; port `clean` files as they are, `overridden` files by hand keeping their intent, set
`synced_sha`, one PR with `Closes #<issue>`.

## Models (subscription quota is scarce)
Routine work haiku; core, security and architecture sonnet; opus only with Daniel's OK.
Agent jobs at once: repo variable MAX_DEV (default 4); open PRs: MAX_PRS (default 5). PRs waiting only for Daniel's approval do not count (max 5 of them, see orchestrator.md). Script first, then haiku, then sonnet. Short reports, never repeat the diff.
