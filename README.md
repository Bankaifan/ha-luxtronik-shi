<p align="center">
  <img src="assets/banner.png" alt="Luxtronik SHI – alpha innotec / Luxtronik heat pumps in Home Assistant" width="100%">
</p>

<p align="center">
  <a href="https://github.com/Bankaifan/ha-luxtronik-shi/releases"><img src="https://img.shields.io/github/v/release/Bankaifan/ha-luxtronik-shi?sort=semver&label=release" alt="Latest release"></a>
  <a href="https://github.com/Bankaifan/ha-luxtronik-shi/actions/workflows/validate.yml"><img src="https://img.shields.io/github/actions/workflow/status/Bankaifan/ha-luxtronik-shi/validate.yml?branch=main&label=validate" alt="Validate"></a>
  <a href="https://hacs.xyz"><img src="https://img.shields.io/badge/HACS-custom-41BDF5" alt="HACS custom repository"></a>
  <img src="https://img.shields.io/badge/Home%20Assistant-2025.8%2B-18BCF2?logo=homeassistant&logoColor=white" alt="Home Assistant 2025.8 or newer">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/Bankaifan/ha-luxtronik-shi" alt="License"></a>
</p>

<p align="center">🇩🇪 <a href="README.de.md">Deutsche Version</a></p>

Home Assistant integration for **alpha innotec / Luxtronik heat pumps** via the **Modbus/TCP interface
"Smart Home Interface" (SHI)**. Set up entirely in the UI, no YAML.

Developed and used daily on an **alpha innotec LWDV 91-1/3** (Luxtronik 2.x with SHI, firmware 3.92.3).
Other Luxtronik controllers with SHI should work but are untested. If yours works, please tell us with a
[model report](https://github.com/Bankaifan/ha-luxtronik-shi/issues/new/choose).

## Highlights

* 🔍 **Automatic discovery** (DHCP) and a setup wizard that asks for the installed equipment.
* 🗂️ **Organised like the controller:** separate devices for heat pump, heating, hot water, cooling and pool.
* 🌡️ **Climate and water heater entities** for heating and hot water, plus numbers, selects and switches for
  setpoints, modes, blocks and the circulation pump.
* ⚡ **Power, energy and COP** – electric and thermal values per area, with a calculated COP.
* ✅ **Safe writes:** every write is checked against a value range and read back from the heat pump.
* 🪶 **Easy on the heat pump:** block reads and tiered polling instead of one request per value.
* 🛠️ **Repair issues and diagnostics** for outdated firmware, lost connections and values that changed during an
  outage, plus a diagnostics download for bug reports.
* 🇬🇧 🇩🇪 English and German.

**Contents:** [Installation](#installation) · [Features](#features) · [Structure](#structure-in-home-assistant) ·
[Equipment](#installation-equipment) · [Repair issues](#repair-issues) · [Diagnostics](#diagnostics) ·
[Beta versions](#beta-versions) · [Notes and limitations](#notes-and-limitations) · [Development](#development)

## Installation

The integration is not in the HACS default catalog yet (the request is pending), so it is added by link.

**Home Assistant 2026.11 or newer (Marketplace):**

1. **Settings → Marketplace → Add from link** → `https://github.com/Bankaifan/ha-luxtronik-shi`. Adding a repository by
   link needs a GitHub connection (device sign-in, read-only access to public data).
2. Install "Luxtronik SHI (Modbus)", restart Home Assistant.

**Older Home Assistant (HACS):**

1. HACS → ⋮ → **Custom repositories** → `https://github.com/Bankaifan/ha-luxtronik-shi`, category **Integration**.
2. Install "Luxtronik SHI (Modbus)", restart Home Assistant.

**Then, in both cases:**

1. **Settings → Devices & services → Add integration → "Luxtronik SHI (Modbus)"**.
2. Enter name, IP address of the heat pump, port (502) and unit ID (1).
3. Confirm the installation equipment (see [below](#installation-equipment)).

Requirement: Modbus/TCP (Smart Home Interface) is enabled in the controller and the heat pump is reachable on the network.

**Automatic discovery:** Home Assistant can find the heat pump by DHCP if both are in the same network segment (DHCP
traffic is not routed between VLANs) and the heat pump renews its lease. It then appears under *Settings → Devices &
services → Discovered*. Discovery only offers devices whose Smart Home Interface answers on Modbus/TCP port 502; if
your heat pump uses another port or unit ID, add it by hand. Discovery also follows IP address changes of a heat pump
that is already set up.

> **Do not delete and re-add the integration** if other automations or a planner depend on its entity IDs.
> Re-adding creates new entities with default IDs. Use *Reconfigure* to change host, port or unit ID instead.

## Features

| Area | Entities |
|---|---|
| Temperatures | flow, return, heat source inlet/outlet, outside average, return target/limit/minimum, return external, outside, room (room unit only), heating/hot water limit temperatures, hot water (actual, target, min, max), mixing circuits 1–3 (flow, target, min, max; disabled by default for circuits 2 and 3) |
| Power & energy | electric and thermal power, minimum electric power, electric/thermal energy counters (total, heating, hot water, cooling, pool), operating hours |
| Calculated COP | **COP (10 min)** (energy ratio of the last 10 minutes from thermal and electric power, main device; unknown while less than 60 Wh of electric energy are in the window, i.e. when the compressor is stopped or just started) and **COP overall** for heating and hot water (thermal / electric energy counters, in the *Heating* / *Hot water* device); unknown instead of a number when values are missing, negative or implausible, or a counter was reset |
| Status | operating mode as text (heating, hot water, pool / solar, utility lockout, defrost, no request, heating from external source, cooling), **compressor 1/2 running**, **auxiliary heater (ZWE) 1/2 active** (additional status bits for VD2, ZWE2 and ZWE3 exist, disabled by default), error number, heating/hot water/cooling/pool status as text (disabled, no request, requested, running; other values as *Unknown (n)*), connection |
| **Climate / water heater** | heating circuit (auto / heat, setpoint 15–75 °C) and hot water (no influence / setpoint / offset / level, setpoint 30–75 °C), see below |
| **Write: numbers** | **heating curve offset** (−20 … +20 K), heating setpoint, hot water setpoint and offset, mixing circuits 1–3 setpoint and offset (heating and cooling), overall heating offset, power limit value (0–30 kW) |
| **Write: selects** | mode (no influence / setpoint / offset / level) for heating, hot water, mixing circuits 1–3 (heating and cooling), overall heating; level (normal / increased / increased step 2 / decreased); power limit mode (none / soft / hard) |
| **Write: switches** | *block heating*, *block hot water*, *block cooling*, *block pool* (only with a pool selected), **circulation pump**, *extra hot water* |
| Diagnostic | buffer tank type, switching lock, minimum runtime, limit/min/max values, equipment flags, firmware, undocumented raw values (disabled by default) |

Mixing circuits 2 and 3 have the same writable entities as circuit 1 (mode, setpoint, offset, level, and the cooling mode,
setpoint and offset), and all write ranges follow python-luxtronik holdings.py: heating setpoint 20–65 °C and
offset −5 … +5 K, cooling setpoint 5–25 °C and offset −5 … +5 K. Circuit 1 has the same ranges. They only
exist when the circuit is selected in the [equipment](#installation-equipment) (the cooling entities also need cooling).

Settings (numbers and selects) are in the *Configuration* section of the device page. Writes use the same registers as
the Smart Home Interface itself; the heat pump enforces its own limits. Every write is read back, so the UI always shows
the real device state. Negative values (heating curve offset) are written correctly as 16-bit two's complement.

### Climate and water heater

A **climate entity** for the heating circuit and a **water heater entity** in the *Hot water* device are views on the
mode select and the setpoint number of their circuit. They write the same registers.

**Modes say what they do** (python-luxtronik `ControlMode`). Raw 0 of every mode select is **No influence**: the heat
pump works with its own values. It does not switch anything off. The selects show:

| Raw | Option key | Shown as |
|---|---|---|
| 0 | `off` | No influence |
| 1 | `setpoint` | Setpoint (replaces the controller's target) |
| 2 | `offset` | Offset (controller's target plus offset) |
| 3 | `level` | Level (controller's target corrected by the level) |

The option keys stay the same for automations; only the shown text changed.

* **Climate:** HVAC mode `auto` is control mode 0 (*the heat pump controls itself*), `heat` is setpoint, offset or
  level. There is **no `off`**: blocking heating is the *block heating* switch, which an optimizer owns. Choosing
  `heat` (or `climate.turn_on`) from `auto` writes `setpoint`; an offset or level mode stays as it is. The current
  temperature is the **return temperature**, because the heating setpoint is a return temperature setpoint (tRL).
  `hvac_action` is `heating` while the heat pump heats, `idle` otherwise and `off` while heating is blocked.
* **Water heater:** the operation modes are `no_influence` (raw 0), `setpoint`, `offset` and `level`.
* **A target only applies in mode `setpoint`.** Climate and water heater refuse a target in any other mode with an
  error that names the mode select; nothing is written. Set the mode select to *Setpoint* first. The heating and hot
  water setpoint **numbers** still write in every mode, because optimizers write them and set the mode themselves.
* Climate, water heater and the two setpoint numbers have the attributes `setpoint_active` (the mode is `setpoint`) and
  `effective_target` (the controller's target: return target 10101 for heating, hot water target 10121). After a
  setpoint write the effective target is read once more, so it follows without waiting for the next poll.

Both are enabled by default on new installations. For entries created before they existed they are disabled by default
(enable them in the entity settings).

> Planners such as the Heat Pump Optimizer write the same registers. Do not use these entities and such a planner for
> the same circuit at the same time, or they overwrite each other; the last write wins. Writes through Home Assistant
> show in the logbook with who made them (user, automation, script). Changes made outside Home Assistant are reported,
> see [repair issues](#repair-issues). The Heat Pump Optimizer does not control hot water through the water heater
> entity.

Coming from 0.9 or earlier: use `hvac_mode: auto` instead of `off` (or the *block heating* switch to stop heating),
and `no_influence` instead of the water heater operation `off`.

**Overall heating** (mode, offset and level, 10065–10067) is disabled by default: its effect is not proven, and it
overrides the per-circuit settings.

### Structure in Home Assistant

Like the menus of the Luxtronik controller, the entities are split into devices:

| Device | Content |
|---|---|
| **<name>** (heat pump) | temperatures (flow, return, outside, heat source), status and operating mode, compressor/auxiliary heater, power, COP, total energy and compressor hours, power limit, system values, firmware version (one text sensor, e.g. 3.92.3), equipment flags, raw values |
| **<name> Heating** | climate entity, mode, setpoint, heating curve offset, level, overall heating, block, mixing circuits 1–3, heating energy, hours and COP |
| **<name> Hot water** | water heater entity, temperatures, mode, setpoint, offset, level, block, circulation pump, extra hot water, hot water energy, hours and COP |
| **<name> Cooling** / **<name> Pool** | only when cooling or a pool is selected in the equipment; Cooling holds the cooling entities of the mixing circuits, Pool the pool block, status and energy |

The sub-devices are linked to the heat pump device. Within a sub-device the names are short (*Setpoint*,
*Block*, *Mixing circuit 1: setpoint*); Home Assistant shows them together with the device name, e.g.
"Heat pump Heating Setpoint". Moving entities between devices never changes their entity IDs. On each device page
Home Assistant also separates *Controls*, *Sensors*, *Configuration* and *Diagnostic*.

### Installation equipment

During setup the integration asks which optional parts are present: **mixing circuits 1–3, cooling, pool,
room unit**. The heat pump's equipment flags pre-select the answer. Deselected parts are not polled and get no
entities. Change it under *Settings → Devices & services → Luxtronik SHI → Configure*. Entity IDs of deselected
parts stay reserved; switching a part on again brings back the same entities.
Entries created before 0.3.0 keep all entities until the equipment is saved there once.

> If a planner such as the Heat Pump Optimizer reads or writes entities of a part (e.g. mixing circuit 1),
> do not deselect that part.

### Polling

* **Block reads** instead of one request per value. If the device rejects a block read (e.g. because a register in
  the gap does not exist), the integration falls back to single reads automatically.
* **Tiered polling**: measurements every cycle (default 30 s), counters and settings less often, firmware rarely.
* **At most every 5 minutes** (10–300 s): the SHI drops every value set over it after 10 minutes without any Modbus
  access ([SHI watchdog](docs/firmware-3.92.3-shi-analysis.md#shi-watchdog)). An existing entry with a longer
  interval polls every 300 s and logs a warning; saving the options once stores the new value.

## Repair issues

The integration raises these issues under *Settings → System → Repairs*:

| Issue | Severity | Raised when |
|---|---|---|
| Heat pump firmware is outdated | warning | Firmware is older than 3.92.0: circulation pump and extra hot water have no values. |
| Smart Home Interface not reachable | error | Every poll failed for 10 minutes in a row. |
| Values changed after connection outage | warning | After an outage, the heating block, hot water block, heating mode or hot water mode differs from the last value read before the outage. |
| Value changed outside Home Assistant | warning | A writable setting (mode, level, setpoint, offset, block, circulation, power limit) changed between two polls without a write through Home Assistant. |

The first two disappear by themselves when their condition ends.

**Value changed outside Home Assistant:** another Modbus client, the native Luxtronik protocol (port 8889), OpenEMS or
the controller panel changed a setting. The issue lists the setting, old and new value and the time; further changes
are added while it is open, and each change also gets a logbook entry. Dismiss it once you have checked the values;
the next change raises it again. It is a notice only, nothing is written back. Not reported: the first poll after
setup, everything after an outage (failed polls, a reconnect or a gap beyond the SHI watchdog, the same signal as the
restore) until every setting was read again, values the integration itself tried to write within the last 10 minutes,
and *extra hot water*, which the controller ends by itself. Without an outage the device cannot revert values, so a
change is always reported. Writes through Home Assistant are never reported; they show in the logbook with
who made them. Works with and without the restore option.

**Values changed after an outage:** if the controller was unreachable (e.g. restart or power cut, the SHI holding
registers are volatile) and comes back with different values, a warning lists the old and new values. **This is a
notice only: the integration never writes anything back**, unless you turn on
[restore after a device reset](#restore-after-a-device-reset-option). The comparison uses the normal poll, no extra Modbus reads.
The issue disappears when the values match the pre-outage values again or when you dismiss it. The values from before
the outage are kept in memory only, so an outage that spans a Home Assistant restart is not noticed.

## Restore after a device reset (option)

The SHI forgets every value set over Modbus when the controller restarts, and when its watchdog expires after 10
minutes without any Modbus access (every read re-arms it, so this only happens while nothing polls; see
[SHI watchdog](docs/firmware-3.92.3-shi-analysis.md#shi-watchdog)). The holding registers
then read their reset value. Measured on the reference installation (LWDV 91-1/3, firmware 3.92.3): after two
controller reboots the heating mode read `off` (raw 0) instead of `setpoint`, and once the heating level read raw 0
instead of 2.

Under *Options*, **Restore values after a device reset** (off by default) makes the integration write such values back:

* **Its own values, plus a one-time snapshot at switch-on, and only settings.** It remembers a value after it was
  written through one of its own
  entities (number, select, climate, water heater) and read back unchanged. Only the **mode, level, offset and setpoint**
  of each circuit (heating, hot water, mixing circuits 1–3 heating and cooling) and the room setpoint are
  remembered (`RESTORE_KEYS` in `const.py`). The overall group (`cfg_overall_*`, 10065–10067) is left out: its
  meaning is unproven (on the reference installation 10065 fell back to `off` about 2 s after a write, and
  python-luxtronik gives the overall mode no setpoint). Blocks (heating, hot water, cooling, pool), circulation, extra
  hot water and the power limit are **never** restored: an optimizer such as the Heat Pump Optimizer owns them live, and
  re-applying a block after a long downtime would undo the watchdog's fail-safe (everything released). The modes and
  setpoints in the list (for example `cfg_heating_mode`, `cfg_heating_setpoint`, `cfg_mk1_setpoint`) are restored
  even if an optimizer writes them; its next write wins. A failed write or a different read-back forgets the
  key. The values are stored per entry in Home Assistant's storage (`.storage/luxtronik_shi.restore.<entry_id>`), so a
  restore also works after a Home Assistant restart. Setting a value back to its neutral value (e.g. mode `off`,
  offset 0) is remembered like any other write, so there is nothing left to restore for it.
  Apart from the one-time adoption below, values written by others are not remembered: another Modbus client's values are out of scope, and values another
  integration writes over the native port 8889 are controller parameters, not values set over the SHI, so a reset
  does not revert them.
* **Adopting the current values once.** When the option is switched on (in the options, or on the first setup with
  it on), the first full read cycle is taken as a snapshot and remembered as if written by the integration: every
  mode, level and offset of the allow-list that reads non-zero (never `0x7FFF`), and a setpoint only if its circuit's
  mode reads `setpoint`. The adopted keys are logged. This happens once; a restart or reload with the option still on
  does not adopt again. Adopted values may have been set by another client; they are restored like your own. Who set
  a value cannot be read over Modbus, so the mode filter only makes it likely that a setpoint was meant: an adopted
  setpoint can also be a boot default or a controller parameter. After a reset in which that parameter changed, the
  adopted value is written back over the change, and from then on the SHI owns it.
* **Only after an outage.** The controller reverts the SHI values for exactly two reasons: a reboot, which drops the
  connection, and 10 minutes without any Modbus access
  ([SHI watchdog](docs/firmware-3.92.3-shi-analysis.md#shi-watchdog)). So a reset is only considered after
  * failed polls,
  * a re-established connection (a reboot shorter than the poll interval can drop the connection without a failed
    poll; the integration counts reconnects of its Modbus connection, no extra requests). This rests on an
    **assumption that is not measured yet**: the SHI keeps the TCP connection open between polls, so a reconnect
    means the controller dropped it. If reconnects happen on 3 of the last 5 polls, the assumption does not hold for
    the setup: a warning is logged once and reconnects no longer count in that session,
  * more than 10 minutes since the previous successful poll while Home Assistant runs, measured with a monotonic
    clock so that a change of the system clock does not count (a suspended host, for example a paused virtual
    machine, is not seen this way: the restore then simply does not happen, which errs on the safe side), or
  * a gap of more than 11 minutes since the last successful poll, for example a long Home Assistant downtime (10
    minutes watchdog plus 1 minute, because the time of the last poll is stored at most once a minute).

  **Any change seen while polling continuously is someone else's**: it is forgotten (logged at info level) and never
  restored.
* **All or nothing.** On a revert the controller resets every value set over the SHI at once: modes and levels to 0,
  setpoints to their persisted or default value (never 0). After an outage, once every remembered register was read
  (one or two polls, no extra reads), it is a reset only if **every** remembered value reads its reset value:
  0 for modes, levels and offsets (for offsets this is an assumption: if a non-zero offset does not revert to 0, the
  reset is not recognised and nothing is overwritten), any non-zero value for setpoints (or exactly the learned value, see below). Then
  all differing values are restored, values first and modes last. If only some reverted, the changed ones were
  external changes: they are forgotten and nothing is restored. A single remembered mode reading 0 after an outage is
  enough. Example: hot water mode `setpoint` at 54 °C and heating mode `offset` with offset 0 – after a reboot both
  modes and the 54 °C come back; a mode that was `off` stays `off`.
* **Learned setpoint reset values.** After a confirmed reset the integration stores the value each setpoint reverted
  to. From then on a setpoint only counts as reverted if it reads exactly that value; another value means someone
  changed it. These values are learned on your device, not taken from a firmware table. If a setpoint blocks a reset
  only because it differs from its learned value, a warning names it. After a reboot with failed polls in which every
  remembered mode and level reads 0, the reset is accepted anyway and the learned value is replaced; an information notice (not a repair issue) then lists the changed base values and the restored values, no action needed. `0x7FFF`
  ("not available") is never a reset value and never learned. A remembered register that becomes unavailable is
  forgotten.
* **Groups.** Mode, setpoint, offset and level of one circuit form a group: once any of them was changed by someone
  else, that circuit's mode is forgotten as well and is only restored again after it was written through Home
  Assistant again, so no combination is created that nobody set.
* **No write loops.** Each key is restored once per detected reset, with read-back. A mode is not restored if another
  value of its circuit failed to restore. A restore whose write fails or reads back a different value forgets that
  key and is not retried. A reset detected again within 15 minutes of a restore is not restored. Remembered values
  older than 24 hours (since the last successful poll) are dropped when the integration starts. Restored keys are
  logged at warning level.

The [outage notice](#repair-issues) keeps working as before; with the option on it usually disappears with the next
poll, because the values match again. *Download diagnostics* lists the remembered and learned values, the number of
reconnects and the time of the last one, and whether reconnects still count as an outage signal.

**Limits:**

* **Hot water settings are taken with a delay.** The controller commits writes to the hot water mode, setpoint,
  offset and level about 10 s later (firmware analysis; measured for the mode), and writing the current value cancels
  such a pending write. The integration therefore checks a differing read-back once more after 15 s instead of
  treating it as a failure, and writes nothing to that register meanwhile. The entity shows the new value from the
  next poll on. A restore of these values waits while the hot water block is on (owner measurement: the hot water
  mode can only be set while the block is not active; the reason is unknown) and is retried on later polls, at most 5
  times within 10 minutes, before it is given up with a warning. A write through Home Assistant cancels it.

* A wrong or stale learned value (for example learned while another client changed the setpoint during a reset) can
  block restores until a reboot with failed polls in which every remembered mode and level reads 0. Turning the option
  off and on again clears all learned values.

* If another Modbus client changes values around an outage **so that every remembered value happens to read its reset
  value** (for example it switches off the only remembered mode), that looks exactly like a reset and is restored over
  that change. **Leave the option off if another system also writes these registers.**
* Before a setpoint's reset value was learned, any non-zero value counts as reverted, so a setpoint changed by someone
  else during an outage can be restored over that change if everything else reverted too.
* A restore writes to the heat pump without a user action. Writes through Home Assistant and a restore never run at
  the same time; a write that arrives during a restore waits for it and then applies.

## Diagnostics

Under *Settings → Devices & services → Luxtronik SHI*, the ⋮ menu of the entry offers **Download diagnostics**. It
creates a file with the integration and Home Assistant
version, the selected equipment and equipment flags, the firmware and the last polled register values (raw and
decoded) and, with the [restore option](#restore-after-a-device-reset-option) on, the remembered values. Host address, MAC address and the entry's unique ID and title are redacted. The file is built from the last
poll, without extra Modbus reads. Please attach it to bug reports.

## Beta versions

Pre-release versions (`X.Y.Z-beta.N`) are published as GitHub pre-releases. To test one in HACS, open the integration,
choose **Redownload** and enable **Show beta versions**. Beta versions may change between releases and are meant for
testing. Users who do not enable this option are not affected and only get stable versions.

## Running alongside the native Luxtronik integration (port 8889)

Both integrations can run side by side but should be clearly separated:

* **luxtronik_shi (this integration):** the only path that **writes** (blocks, setpoints, modes, circulation pump)
  and the values a planner like the Heat Pump Optimizer needs.
* **Native Luxtronik integration (entities `luxtronik_<serial>_*`):** **diagnostics only** (additional measurements,
  parameters, error log). Disable its write entities (select, climate, switch, number) so two integrations do not
  write to the same controller. Enable diagnostic entities individually as needed.
* Settings only the native protocol offers (e.g. thermal disinfection / legionella protection) are not changed by
  this integration. That stays a deliberate decision of the operator.

<details>
<summary><b>Migrating from a YAML <code>modbus:</code> configuration</b></summary>

The integration fully replaces a YAML configuration (`modbus:` hub plus template entities). The internal keys
deliberately match the former entity IDs (`lwdv_shi_<key>`). This is how the migration went on the reference
installation (LWDV 91-1/3, Heat Pump Optimizer in "control" mode) without changing the consumers:

1. **Remove the YAML hub first** (`modbus:` block and the related template entities in `configuration.yaml`, restart).
   Some SHI firmwares allow only a few concurrent TCP connections, and only one path should write.
2. Add the integration (see above).
3. **Delete orphaned registry entries of the old YAML entities** (state "restored/unavailable"), otherwise the old
   entity ID is taken and renaming fails.
4. Rename the new entities (`warmepumpe_*`) to the old IDs (Settings → Entities), e.g. `sensor.lwdv_shi_flow`,
   `sensor.lwdv_shi_return`, `switch.lwdv_shi_heating_block`, `switch.lwdv_shi_dhw_block`. The heating curve offset
   is now writable (`number.<name>_heizkurven_anhebung`, previously read-only as
   `sensor.einstellung_heizen_anhebung_heating_offset`).
5. **Check consumers:** renaming does not update references in dashboards, automations and templates. Check them
   (e.g. with the entity search) and adjust references to removed sensors.
6. **Operating mode is now text** (`off`, `heating`, `dhw`, `defrost`, …). The old YAML entity was numeric
   (Luxtronik: 1 = hot water, 5 = no demand). Templates that compare numbers must be changed to text.
7. Long-term statistics are kept if the new entity gets the same entity ID and the same unit. Statistics of removed
   entities (e.g. `einstellung_*`, `diagnose_rohwert_*`) remain orphaned in the database.

**`tools/gen_yaml.py`** generates the equivalent YAML configuration from the register map. It is a **legacy tool** for
those who deliberately stay on YAML, no longer used in production and not tested against register map changes.

</details>

## Sources of the register map

* [Bouni/python-luxtronik](https://github.com/Bouni/python-luxtronik), module `luxtronik/shi` and
  `luxtronik/definitions/{inputs,holdings}.py` (MIT): addresses, data types, ranges, firmware version.
  According to this source the SHI holding registers are **volatile** and are reset when the controller restarts –
  unlike the controller's persistent settings.
* Measurements on the reference installation (LWDV 91-1/3, firmware 3.92.3), see below.
* DHCP discovery matchers (MAC prefixes, hostname `wp-novelan`) are taken from
  [BenPru/luxtronik](https://github.com/BenPru/luxtronik) (MIT).
* Not contained in python-luxtronik and therefore only backed by observation: the equipment registers (discrete
  inputs 10000–10011), firmware major/minor version (10401/10402, matches the version shown on the controller) and
  the interpretation of 10404/10406/10408 as operating hours.
* Complete table of all registers (type, address, data type, scale, unit, range): [docs/registers.md](docs/registers.md).

## Notes and limitations

* **Values can fall back after a controller restart.** The SHI holding registers are volatile. After a power cut or
  a controller restart, values written through this integration (for example the heating or hot water block) can
  return to the controller default, e.g. `off`. By default the integration does **not** write them back; see
  [restore after a device reset](#restore-after-a-device-reset-option) for the option that does. If Home Assistant was
  running during the outage, a [repair issue](#repair-issues) shows what changed. Check the block and mode entities
  after a power outage, or have your automation or planner write them again.
* **Return / return target:** the published register list names 10100 "return target" and 10101 "return actual".
  Measured on a real installation it is the other way round (10100 follows the water temperature, 10101 jumps to the
  target while heating). The entities follow the measurement; python-luxtronik agrees.
* **Heating setpoint (reg. 10001):** measured, the value acts as return target, not as flow target (`return target`
  followed the written value). It only applies with heating mode `setpoint` (reg. 10000 = 1).
* **Block heating:** `switch.<name>_heating_block` only blocks heating; hot water keeps running. A planner (e.g. Heat
  Pump Optimizer) can block at a planned 0 W and release again if the planner fails or the room gets too cold.
* The *level* options (normal / increased / increased step 2 / decreased) follow python-luxtronik `LevelMode`, which
  marks the effect of the non-normal levels as not yet analysed. Circulation pump and extra hot water require firmware 3.92.0.
* **Status bits VD2, ZWE2, ZWE3:** the binary sensors `heatpump_vd2_status`, `heatpump_zwe2_status` and
  `heatpump_zwe3_status` come from python-luxtronik (bits 1, 3 and 4 of register 10000) and are disabled by default.
  VD2 and ZWE2 show the same bits as *compressor 2* and *auxiliary heater 2*; ZWE3 needs firmware 3.90.1 or later
  (per python-luxtronik).
* **Renamed raw values (10109, 10110, 10112):** `raw_10109` is now `outside_temp_average` (outside average, °C),
  `raw_10110` is now `heat_source_input` (heat source inlet, °C) and `raw_10112` is
  `max_flow_temp` (flow maximum, °C, disabled by default). The integration moves the existing entities over when it
  starts, so their entity IDs, history and settings stay. Only the unique ID suffix and the name change; adjust
  anything that matches on the old `raw_*` unique ID. Long-term statistics of 10112 start now (it had no unit before).
* **Undocumented raw values:** registers that python-luxtronik lists with unknown function (inputs 10352, 10353, 10410–10413,
  10416, 10417, 10500–10502 and holding 10060) are available as disabled `raw_<address>` diagnostic sensors. They are
  read only (never written) and polled rarely.
* **Pool block and power limit:** the pool block switch (register 10053) only exists with a pool selected. The power
  limit consists of a mode select (none / soft / hard, register 10040) and a value number (0–30 kW, register 10041).
* **Mixing circuit valve:** the SHI only provides temperatures and mode/setpoints of the mixing circuits, no valve
  position and no "valve always open" switch. That is configured on the controller (installer level).
* **Heating circulation pumps** (HUP) cannot be controlled via the SHI, only the hot water circulation pump. The native
  Luxtronik protocol (port 8889, e.g. the integration by BenPru) offers many more parameters.
* In every hot water mode other than *Setpoint* (raw 0 is *No influence*) the heat pump ignores the setpoint; the actual target is in the *hot water target*
  sensor.
* Writes act directly on the heat pump. Automate blocks and offsets with care.

## Development

```bash
python -m venv venv && . venv/bin/activate
pip install -r requirements_test.txt pytest-timeout ruff
ruff check . && pytest --timeout=60
```

Tests run against a small simulated Modbus/TCP server (`tests/fake_shi.py`) that, like the real SHI, only answers
existing registers. Translations are generated from the register map: `python tools/gen_translations.py`.
Entity keys are a contract (`tests/test_contract.py`). See [CONTRIBUTING.md](CONTRIBUTING.md) for contributions,
[CLAUDE.md](CLAUDE.md) for the working rules and [CHANGELOG.md](CHANGELOG.md) for versioning.

Releases are created automatically: when a version bump reaches `main` and the *Validate* workflow (hassfest, HACS
action, tests) has passed, a GitHub Actions workflow tags that commit and publishes the release with the CHANGELOG
section as notes.

Long-term goal: move the protocol code into a library on PyPI and submit the integration to Home Assistant Core.

## Disclaimer

Unofficial, not affiliated with alpha innotec or Luxtronik. Product names are used only to describe compatibility.
Use at your own risk.
