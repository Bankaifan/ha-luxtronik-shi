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

The integration is in the HACS default catalog.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Bankaifan&repository=ha-luxtronik-shi&category=integration)
[![Add integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=luxtronik_shi)

One click: the first button opens the integration in HACS of your Home Assistant, the second sets it up after the
installation and restart (both via My Home Assistant).

**Home Assistant 2026.11 or newer (Marketplace):** **Settings → Marketplace**, search for "Luxtronik SHI", install
"Luxtronik SHI (Modbus)", restart Home Assistant.

**Older Home Assistant (HACS):** open HACS, search for "Luxtronik SHI", install "Luxtronik SHI (Modbus)", restart
Home Assistant.

**Fallback (if the search does not find it yet):** add the repository by link (Marketplace → **Add from link**, needs a
GitHub connection) or in HACS → ⋮ → **Custom repositories**, category **Integration**:
`https://github.com/Bankaifan/ha-luxtronik-shi`.

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
| Power & energy | electric and thermal power, minimum electric power, electric/thermal energy counters (total, heating, hot water, cooling, pool), operating hours (compressor, heating, hot water; **cooling** and **solar** with the matching equipment) |
| Calculated COP | **COP (10 min)** (energy ratio of the last 10 minutes from thermal and electric power, main device; unknown while less than 60 Wh of electric energy are in the window, i.e. when the compressor is stopped or just started) and **COP overall** for heating, hot water and all modes together (thermal / electric energy counters, in the *Heating* / *Hot water* device and the main device; a long-term average, not the 10-minute value and not a seasonal performance factor); unknown instead of a number when values are missing, negative or implausible, or a counter was reset |
| Status | operating mode as text (heating, hot water, pool / solar, utility lockout, defrost, no request, heating from external source, cooling), **compressor 1/2 running**, **auxiliary heater (ZWE) 1/2 active** (additional status bits for VD2, ZWE2 and ZWE3 exist, disabled by default), error number, heating/hot water/cooling/pool status as text (disabled, no request, requested, running; other values as *Unknown (n)*), connection. Calculated from registers that are read anyway (no extra polling): **fault** (error number is not 0), **defrost active**, **heating running** / **hot water running** (status is *running*), **power limit: mode set** (the configured mode is soft or hard; this is not whether the limit currently reduces the power) and the **flow-return difference** in K (flow minus return, can be negative) |
| **Climate / water heater** | heating circuit (auto / heat, setpoint 15–75 °C) and hot water (no influence / setpoint / offset / level, setpoint 30–75 °C), see below |
| **Write: numbers** | **heating curve offset** (−20 … +20 K), heating setpoint, hot water setpoint and offset, mixing circuits 1–3 setpoint and offset (heating and cooling), overall heating offset (−5 … +5 K), power limit value (0–30 kW). All ranges are the firmware's, see [write ranges](#write-ranges-and-defaults-firmware) |
| **Write: selects** | mode (`no_influence` / `setpoint` / `offset` / `level`) for heating, hot water, mixing circuits 1–3 (heating and cooling), overall heating (`no_influence` / `offset` / `level`: the firmware has no setpoint there); level (`normal` / `increased` / `decreased`; raw 1 and 2 are both `increased`, the amounts are the controller's *Offsets* parameters); power limit mode (none / soft / hard) |
| **Write: switches** | *block heating*, *block hot water*, *block cooling*, *block pool* (only with a pool selected): a block stays as written until it is changed or the SHI watchdog releases it; plus the block views *operating mode (blocks)* (select) and *on/off (blocks)* (switch), see [below](#block-views-for-the-heat-pump-optimizer) |
| **Write: buttons** | **circulation: start run** and **extra: start** (the two trigger registers 10070/10071: a press writes 1, the firmware sets the register back to 0 when the run or the timer ends), **extra: end** (writes 0, ends extra hot water early). The running state is the binary sensors **circulation: run active** and **extra: running**, see [triggers](#triggers-circulation-run-and-extra-hot-water) |
| Extra hot water | **setpoint**, **duration** and **remaining time** of extra hot water (controller parameters 1146/1147 and the running timer; firmware 3.92.3 analysis), in the *Hot water* device |
| Pumps and I/O | **pump heating (HUP), hot water (BUP), circulation (ZIP)** running, outputs **VBO** and **FP1** (FP2 and FP3 disabled by default; not measured), inputs **EVU** and **EVU 2** as a level (disabled by default). Read from the same registers as the matching `raw_` sensors, which stay as they are. For EVU only the name is proven by the firmware analysis; that level 1 means *released* is inferred from one measured state, so the sensors show the level, not "locked". The operating mode *utility lockout* reports the lock itself |
| Diagnostic | buffer tank type, limit/min/max values, equipment flags, firmware, the calculated maximum flow (*TVL calc max*, 10113) and the raw values without a proven meaning (disabled by default). The switching lock, minimum runtime and minimum hot water temperature are fixed firmware constants and disabled by default for new installations |

**Every entity explained:** the [entity reference](docs/entities.md) (also in [German](docs/entities.de.md)) lists each
entity by topic with key, unit, value range, meaning and pitfalls, plus short background on how heat pumps work.

Mixing circuits 2 and 3 have the same writable entities as circuit 1 (mode, setpoint, offset, level, and the cooling mode,
setpoint and offset), with the firmware's ranges: heating setpoint 20–65 °C and offset −5 … +5 K, cooling setpoint
5–25 °C and offset −5 … +5 K. Circuit 1 has the same ranges. They only exist when the circuit is selected in the
[equipment](#installation-equipment) (the cooling entities also need cooling).

Settings (numbers and selects) are in the *Configuration* section of the device page. Writes use the same registers as
the Smart Home Interface itself; the heat pump enforces its own limits. Every write is read back, so the UI always shows
the real device state. Negative values (heating curve offset) are written correctly as 16-bit two's complement.

### Write ranges and defaults (firmware)

The full analysis of firmware V3.92.3 ([docs/firmware-3.92.3-shi-full-analysis.md](docs/firmware-3.92.3-shi-full-analysis.md),
German: [docs/firmware-3.92.3-shi-full-analysis.de.md](docs/firmware-3.92.3-shi-full-analysis.de.md)) proves the range
of every writable register and what the firmware does with a value outside it: it **acknowledges the write and resets
the register to its default** (heating and mixing circuit setpoints 35.0 °C, hot water setpoint 40.0 °C, cooling
setpoints 20.0 °C, power limit 30.0 kW, everything else 0). The previous value is lost, not kept. The integration
therefore never sends a value outside the range: the number entities carry the firmware limits, climate, water heater,
services and the restore refuse such values with an error. If a register reads its default right after a write, the
write fails with an error that names the likely causes (error 816 *multiple SHI write sources*, watchdog expiry). The
same defaults are the values every register falls back to after a controller restart or a watchdog expiry.

| Register | Range | Default |
|---|---|---|
| heating setpoint 10001 | 15.0 … 75.0 °C | 35.0 °C |
| heating offset 10002, hot water offset 10007 | −20.0 … +20.0 K | 0 |
| hot water setpoint 10006 | 30.0 … 75.0 °C | 40.0 °C |
| mixing circuit setpoints 10011/10021/10031 | 20.0 … 65.0 °C | 35.0 °C |
| mixing circuit offsets 10012/10022/10032, cooling offsets, **overall offset 10066** | −5.0 … +5.0 K | 0 |
| cooling setpoints 10016/10026/10036 | 5.0 … 25.0 °C | 20.0 °C |
| power limit 10041 | 0 … 30.0 kW | 30.0 kW |
| modes, levels (0 … 3), blocks, triggers | enumerations | 0 |
| room setpoint 10060 | open (controller parameter 1148; 20 … 40 °C is the owner's choice) | persisted value |

The controller limits the **effect** on top: the heating setpoint is clamped to [return target minimum, return limit]
(while heating is blocked the target is the minimum regardless), the hot water target to the maximum hot water
temperature, and extra hot water and thermal disinfection take precedence. Changed in 0.17.0: the overall offset
allowed −20 … +20 K before (python-luxtronik); the firmware resets anything beyond ±5 K to 0.

**Levels** (heating, hot water, mixing circuits, overall): 0 = normal; 1 and 2 both **raise** the target by the
controller parameter *Erhöhung* of that circuit (the same parameter, so step 2 equals step 1); 3 **lowers** it by
*Absenkung*. The amounts live in the controller menu *Offsets* (parameters 1187–1198, −20 … +20 K in 0.5 K steps) and
cannot be read or written over the SHI.

**Enable SHI.** The controller parameter *Enable SHI* (1161, options Modbus TCP / myUplink / both) cannot be read over
Modbus. While it is off, setpoints, offsets, levels and the power limit are accepted and read back correctly but have
no effect; the blocks, the circulation pump and extra hot water work regardless. The diagnostics download names it. If
written values have no effect, check this setting at the control panel.

### Climate and water heater

A **climate entity** for the heating circuit and a **water heater entity** in the *Hot water* device are views on the
mode select and the setpoint number of their circuit. They write the same registers.

**Modes say what they do** (firmware analysis, python-luxtronik `ControlMode`). Raw 0 of every mode select is
**No influence**: the heat pump works with its own values. It does not switch anything off. The selects show:

| Raw | Option key | Shown as |
|---|---|---|
| 0 | `no_influence` | No influence (controller uses its own values) |
| 1 | `setpoint` | Setpoint (replaces the controller's target) |
| 2 | `offset` | Offset (controller's target plus offset) |
| 3 | `level` | Level (controller's target corrected by the level) |

**Changed in 0.18.0:** the option key of raw 0 is `no_influence` (it was `off`, which it is not). Automations and
optimizer configurations that select or compare `off` on a mode select must use `no_influence`; the water heater
already used that key. The operating mode sensor likewise shows `no_request` for raw 5 instead of `off`.

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

**Overall heating** (mode, offset and level, 10065–10067) is disabled by default. The firmware analysis proves what it
does: while its mode is not *no influence*, the modes of the heating circuit **and** of all mixing circuits are ignored
and the overall offset or level applies to them (hot water is not affected). Raw 1 (*setpoint*) is **not implemented**
by the firmware for this group and acts like *no influence*, so the select offers only `no_influence`, `offset` and
`level`; a raw 1 another client wrote shows as *unknown* (the raw value is in the diagnostics download and in the
change notice). The level uses the controller parameters *Hz. allg.* (1187/1188). It stays disabled by default because
an active overall mode silently overrides what an optimizer writes per circuit.

**Levels** (`cfg_*_level`): the firmware uses the same controller parameter *Erhöhung* for raw 1 and raw 2, so both are
one option `increased` (written as raw 1; a raw 2 another client wrote shows as `increased` too). Raw 3 is `decreased`
(*Absenkung*). The option `increased2` of 0.17.x is gone.

### Triggers: circulation run and extra hot water

Registers 10070 (circulation) and 10071 (extra hot water) are **triggers**, proven by the firmware analysis: a write of
1 starts the action, and the firmware sets the register back to 0 itself when the action is over (circulation: once no
run with the controller's run and pause times is active any more; extra hot water: when its timer of
`extra_dhw_duration` minutes ends). A trigger is not a state the user holds, so since 0.18.0 each one is a start
**button** plus a stop **button**, in the *Hot water* device, with a binary sensor that shows whether it runs:

| Key | Platform | What it does |
|---|---|---|
| `circulation` | button | *Circulation: start run*: writes 1 to 10070 |
| `circulation_stop` | button | *Circulation: end*: writes 0 to 10070, the pump stops at once (unless the controller's own time program requests circulation at the same time) |
| `pump_circulation` | binary_sensor | *Pump: circulation (ZIP)*: the real pump output 10356; on for runs started here and for runs of the time program |
| `extra_dhw` | button | *Extra: start*: writes 1 to 10071, the hot water target is raised to `extra_dhw_setpoint` for `extra_dhw_duration` |
| `extra_dhw_stop` | button | *Extra: end*: writes 0 to 10071, which sets the timer to 0 |
| `extra_dhw_running` | binary_sensor | *Extra: running*: 10071 reads 1; `extra_dhw_remaining` shows the minutes left |

Up to 0.17.x both triggers were **switches** (`switch.<name>_circulation…`, `switch.<name>_extra…`). Those entities are
removed when 0.18.0 starts (the registry entries are deleted, they would otherwise stay as dead entities); the buttons
get new entity IDs. **Automations and the Heat Pump Optimizer must call `button.press` on the new button instead of
`switch.turn_on`** (and `circulation_stop` / `extra_dhw_stop` instead of `switch.turn_off`), and read the running
state from `pump_circulation` and `extra_dhw_running`. A read-back of 0 right after the press is the
normal end (or the controller did not accept the trigger) and is not an error. The circulation trigger is not accepted
while the controller's hot water operating mode is *holiday* or *off*: *off* also clears the equipment flag
`hot_water_available`, so the buttons are unavailable then; *holiday* cannot be read over the SHI. The *Enable SHI* parameter
does not apply to the triggers. Neither is restored after a reset or reported as a change outside Home Assistant.

### Block views for the Heat Pump Optimizer

A **select** (`block_mode`, *Operating mode (blocks)*) and a **switch** (`block_power`, *On/off (blocks)*) in the main
device are views on the two registers `heating_block` (10050) and `dhw_block` (10051). They read and write exactly
those, poll nothing extra, and write like every other entity (read-back, no notice about "changed outside Home
Assistant"). Like the blocks themselves they are **not restored** after a reset. They replace the template select and
template switch that some installations keep in `configuration.yaml` for the Heat Pump Optimizer; a coordinator
entity writes its state on every poll, which keeps the optimizer's freshness check (`last_reported`) honest, whereas
Home Assistant does not re-report an unchanged template state.

| Option key | Shown as | Heating block | Hot water block |
|---|---|---|---|
| `heating_dhw` | Heating and hot water | off | off |
| `heating` | Heating only | off | **on** |
| `dhw_hot_water` | Hot water only | **on** | off |

The option keys fold (letters and digits only) to `Heating + DHW`, `Heating` and `DHW (Hot Water)`, the labels the
optimizer recognises, so it maps them to full / heating only / hot water only.

* **"Hot water only" is also shown while both blocks are set.** Three options cannot show that state. The switch
  shows the real *off*: it is off exactly when both blocks are set.
* **Switch:** turning off sets both blocks (hot water first). Turning on releases the **hot water block only, and
  only if both blocks are set**; the heating block stays as the select left it. In any other state turning on does
  nothing.
* **Write order.** Two writes follow each other, and the SHI releases everything when its watchdog expires. A change
  therefore releases before it blocks, so an interruption between the two writes leaves fewer blocks, never more
  (heating only -> hot water only passes through "heating and hot water"). Both registers are written every time. After
  each write the value is read back; if the heat pump does not take it (for example while its error 816 *multiple SHI
  write sources* is active, which drops writes without an error code), the sequence stops with an error.
* Enabled by default on new installations; for entries created before they existed they are disabled (enable them in
  the entity settings).

**Using them with the optimizer:** in the optimizer's options, set the *heat pump mode* entity to the select and the
on/off entity to the switch (entity IDs depend on your device name and language, see the entity registry). Then remove
the old template select and switch from `configuration.yaml`, restart or reload template entities, and delete the
orphaned entities. Use only one writer of the blocks at a time.

### Structure in Home Assistant

Like the menus of the Luxtronik controller, the entities are split into devices:

| Device | Content |
|---|---|
| **<name>** (heat pump) | temperatures (flow, return, outside, heat source), status and operating mode, compressor/auxiliary heater, power, COP, total energy and compressor hours, power limit, system values, firmware version (one text sensor, e.g. 3.92.3), equipment flags, raw values |
| **<name> Heating** | climate entity, mode, setpoint, heating curve offset, level, overall heating, block, mixing circuits 1–3, heating energy, hours and COP |
| **<name> Hot water** | water heater entity, temperatures, mode, setpoint, offset, level, block, the circulation run and extra hot water triggers (buttons and running flags), hot water energy, hours and COP |
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
* **Only what is used:** registers of *disabled* entities are not read. Enabling an entity reads its register at
  once and includes it in the following polls. Whatever the integration needs itself stays in the poll even if the
  entity is disabled: firmware, the control values compared after an outage, everything the restore and the reset
  detection use, the equipment flags and the sources of the climate, water heater and status bit entities. The
  inputs of the calculated entities (COP, flow-return difference, fault, defrost, running, power limit) are read
  while the source entity or at least one calculated entity that uses it is enabled; a default installation
  reads the same registers as before.
* **At most every 5 minutes** (10–300 s): the SHI drops every value set over it after 10 minutes without any Modbus
  access ([SHI watchdog](docs/firmware-3.92.3-shi-analysis.md#shi-watchdog)). An existing entry with a longer
  interval polls every 300 s and logs a warning; saving the options once stores the new value.

## Energy dashboard

The counters **Energy: electric total** (`energy_el_total`) and **Energy: thermal total** (`energy_th_total`) are in
kWh with the state class `total_increasing`, so Home Assistant accepts them as they are: add the electric counter
under *Settings → Dashboards → Energy → Individual devices*. The counters for heating, hot
water, cooling and pool are built the same way. The counters have a resolution of 0.1 kWh.

## Repair issues

The integration raises these issues under *Settings → System → Repairs*:

| Issue | Severity | Raised when |
|---|---|---|
| Heat pump firmware is outdated | warning | Firmware is older than 3.92.0: the circulation run and extra hot water triggers have no values. |
| Smart Home Interface not reachable | error | Every poll failed for 10 minutes in a row. |
| Values changed after connection outage | warning | After an outage, the heating block, hot water block, heating mode or hot water mode differs from the last value read before the outage. |
| Value changed outside Home Assistant | warning | A writable setting (mode, level, setpoint, offset, block, power limit) changed between two polls without a write through Home Assistant. |

The first two disappear by themselves when their condition ends.

**Value changed outside Home Assistant:** another Modbus client, the native Luxtronik protocol (port 8889), OpenEMS or
the controller panel changed a setting. The issue lists the setting, old and new value and the time; further changes
are added while it is open, and each change also gets a logbook entry. Dismiss it once you have checked the values;
the next change raises it again. It is a notice only, nothing is written back. Not reported: the first poll after
setup, everything after an outage (failed polls, a reconnect or a gap beyond the SHI watchdog, the same signal as the
restore) until every setting was read again, values the integration itself tried to write within the last 10 minutes,
and the triggers *circulation* and *extra hot water*, which the controller ends by itself. Without an outage the device cannot revert values, so a
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
controller reboots the heating mode read `no_influence` (raw 0) instead of `setpoint`, and once the heating level read raw 0
instead of 2.

Under *Options*, **Restore values after a device reset** (off by default) makes the integration write such values back:

* **Its own values, plus a one-time snapshot at switch-on, and only settings.** It remembers a value after it was
  written through one of its own
  entities (number, select, climate, water heater) and read back unchanged. Only the **mode, level, offset and setpoint**
  of each circuit (heating, hot water, mixing circuits 1–3 heating and cooling) and the room setpoint are
  remembered (`RESTORE_KEYS` in `const.py`). The overall group (`cfg_overall_*`, 10065–10067) is left out: it is
  proven to override the heating and mixing circuit modes, so an automatic re-apply could silently override what an
  optimizer sets per circuit (on the reference installation 10065 once fell back to `no_influence` about 2 s after a write).
  Blocks (heating, hot water, cooling, pool), the triggers circulation and extra hot water (the firmware switches
  them off itself) and the power limit are **never** restored: an optimizer such as the Heat Pump Optimizer owns them
  live, and re-applying a block after a long downtime would undo the watchdog's fail-safe (everything released). A
  remembered value outside the firmware range is never written (it would reset the register to its default). The
  proven defaults (35.0 / 40.0 / 20.0 °C, 30.0 kW, 0) count as reset values. The modes and
  setpoints in the list (for example `cfg_heating_mode`, `cfg_heating_setpoint`, `cfg_mk1_setpoint`) are restored
  even if an optimizer writes them; its next write wins. A failed write or a different read-back forgets the
  key. The values are stored per entry in Home Assistant's storage (`.storage/luxtronik_shi.restore.<entry_id>`), so a
  restore also works after a Home Assistant restart. Setting a value back to its neutral value (e.g. mode `no_influence`,
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
  modes and the 54 °C come back; a mode that was `no_influence` stays `no_influence`.
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

See also [Dashboards and blueprints](docs/dashboard.md): ready-made dashboards (overview, energy, locks and grid, control, diagnostics), blueprints and a generator for your own entity IDs.

Under *Settings → Devices & services → Luxtronik SHI*, the ⋮ menu of the entry offers **Download diagnostics**. It
creates a file with the integration and Home Assistant
version, the selected equipment and equipment flags, the firmware and the last polled register values (raw and
decoded) and, with the [restore option](#restore-after-a-device-reset-option) on, the remembered values. A
*polling* section shows the poll interval, the duration of the last poll, the number of polls and failed polls,
the failures in a row, the time of the last success and failure and the registers that are not polled
(disabled entities). It comes from memory, not from the heat pump. Host address, MAC address and the entry's unique ID and title are redacted. The file is built from the last
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
6. **Operating mode is now text** (`no_request`, `heating`, `hot_water`, `defrost`, …). The old YAML entity was numeric
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
* Full analysis of firmware V3.92.3 (`bin/Controller`, § 69e UrhG interoperability):
  [docs/firmware-3.92.3-shi-full-analysis.md](docs/firmware-3.92.3-shi-full-analysis.md) (English) and
  [docs/firmware-3.92.3-shi-full-analysis.de.md](docs/firmware-3.92.3-shi-full-analysis.de.md) (German): every
  register with its firmware item, variable, text, visibility condition, range, default and evidence grade
  (proven / likely / open). It proves the equipment registers (discrete inputs 10000–10011, 10004 = solar; 10000/10001
  = equipped **and** the controller mode is not *off*), the firmware version registers, the operating hour counters
  10404–10416, the extra hot water registers 10500–10502, 10113 (*TVL calc max*) and the demand borders 10107/10124
  (setpoint minus hysteresis, not parameters). The only register that stays a raw value is the pool hour counter
  10412 (divisor 7200 instead of 3600, so the wire value is likely half the hours; not measured).
  The firmware reads 32-bit values with the **high word at the lower address**; the electric energy counters are
  unsigned, the heat quantity counters signed (the integration decodes them as such since 0.17.0). Discrete inputs
  exist (function code 2), coils do not.
* Every entity explained (generated from the code): [docs/entities.md](docs/entities.md).
* Complete table of all registers (type, address, data type, scale, unit, range): [docs/registers.md](docs/registers.md).
* Firmware 3.92.3 analysis (independent, for interoperability): [full analysis](docs/firmware-3.92.3-shi-full-analysis.md)
  ([German](docs/firmware-3.92.3-shi-full-analysis.de.md)) with the register table as
  [CSV](docs/firmware-3.92.3-registers.csv); earlier notes: [SHI mechanics](docs/firmware-3.92.3-shi-analysis.md) and
  [register meanings](docs/firmware-3.92.3-register-meanings.md) (English).

## Notes and limitations

* **Values can fall back after a controller restart.** The SHI holding registers are volatile. After a power cut or
  a controller restart, values written through this integration (for example the heating or hot water block) can
  return to the controller default, e.g. released. By default the integration does **not** write them back; see
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
* The *level* options are `normal` / `increased` / `decreased` (raw 0 / 1 and 2 / 3): the firmware proves that raw 1
  and 2 raise by the same controller parameter and 3 lowers (see
  [write ranges and defaults](#write-ranges-and-defaults-firmware)). Circulation run and extra hot water require
  firmware 3.92.0 and are **triggers** (buttons with a running binary sensor, see
  [triggers](#triggers-circulation-run-and-extra-hot-water)).
* **Status bits VD2, ZWE2, ZWE3:** the binary sensors `heatpump_vd2_status`, `heatpump_zwe2_status` and
  `heatpump_zwe3_status` come from python-luxtronik (bits 1, 3 and 4 of register 10000) and are disabled by default.
  VD2 and ZWE2 show the same bits as *compressor 2* and *auxiliary heater 2*; ZWE3 needs firmware 3.90.1 or later
  (per python-luxtronik).
* **Renamed raw values (10109, 10110, 10112, 10113):** `raw_10109` is now `outside_temp_average` (outside average,
  °C), `raw_10110` is now `heat_source_input` (heat source inlet, °C), `raw_10112` is `max_flow_temp` (flow maximum,
  °C, disabled by default) and, since 0.18.0, `raw_10113` is `flow_calc_max` (*TVL calc max*, the calculated maximum
  flow, °C, disabled by default). The integration moves the existing entities over when it starts, so their entity
  IDs, history and settings stay. Only the unique ID suffix changes; adjust anything that matches on the old `raw_*`
  unique ID.
* **Raw values:** the firmware analysis resolved most of the registers python-luxtronik lists with unknown function.
  The resolved ones have proper sensors: `hours_cooling` (10410, needs *cooling*), `hours_solar` (10416, needs the
  equipment option *solar*, pre-filled from the flag `cap_solar` = discrete input 10004), `extra_dhw_setpoint`,
  `extra_dhw_duration` and `extra_dhw_remaining` (10500–10502) and `flow_calc_max` (10113). **Since 0.18.0 the raw
  word sensors of those addresses (`raw_10410`, `raw_10411`, `raw_10416`, `raw_10417`, `raw_10500`, `raw_10501`,
  `raw_10502`) no longer exist**; their registry entries are deleted at start. Still raw (disabled diagnostics, read
  only, polled rarely): the pool operating hours 10412/10413 (the firmware divides them by 7200 instead of 3600, only
  likely a factor 2, not measured). **Since 0.18.0 the raw twins of the proven outputs and inputs (`raw_10350` …
  `raw_10356`, `raw_10360`, `raw_10361`) no longer exist** either; the binary sensors `output_vbo`, `output_fp1` …
  `output_fp3`, `pump_heating`, `pump_hot_water`, `pump_circulation`, `input_evu`, `input_evu2` read those registers
  (same poll interval), and the raw registry entries are deleted at start.
* **Demand borders renamed (0.18.0):** `heating_limit` is now `heating_demand_border` and `dhw_limit` is now
  `dhw_demand_border` (*demand border*: setpoint minus hysteresis, tracked by the firmware, not a parameter). The
  integration moves the registry entries over, so entity IDs, history and settings stay; only the unique ID suffix
  changes.
* **Availability flags renamed (0.18.0):** `cap_heating` is now `heating_available` and `cap_hot_water` is now
  `hot_water_available` (discrete inputs 10000/10001: on while the part is equipped **and** the controller's operating
  mode for it is not *off*; proven). The registry entries move over, so entity IDs, history and settings stay.
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
