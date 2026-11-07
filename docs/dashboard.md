# Dashboards and blueprints

Ready-made Lovelace dashboards, three blueprints and a generator for your own entity IDs. Everything is built from
the entities of this integration and uses **built-in cards only**; the one exception is an optional, separate view
that needs the HACS card [apexcharts-card](https://github.com/RomRider/apexcharts-card).

## Who it is for

| View | For | Content |
|---|---|---|
| Overview | Everyone who leaves control to a planner such as the Heat Pump Optimizer | Connection, operating mode, status, pumps (HUP, BUP, ZIP), temperatures, power, COP, alerts for utility lockout and blocks. Read-only: tapping a lock does not switch it. |
| Energy | Energy management (HEMS) users | Electric and thermal energy today, this week and this month (long-term statistics, no helpers needed), energy per day per area, COP |
| Locks and grid | HEMS users | Heating, hot water, cooling and pool blocks, power limit, circulation, extra hot water, utility lockout, EVU input level (only if enabled; the level is shown, not "locked", its polarity is inferred), notes on PV surplus |
| Control | People who control the heat pump themselves | Thermostat, water heater, mode, setpoint (with the controller's effective target), offset and level per circuit |
| Diagnostics | Support and troubleshooting | Firmware, buffer type, error number, generator bits, equipment flags, status history, troubleshooting steps |
| Automation | People who write automations | Table of every entity (key and entity ID), blueprint import links, example automations |

## Install

1. Pick the file: `dashboards/luxtronik_shi.<profile>.<language>.yaml`.
   * **basic**: no optional parts. **full**: mixing circuits 1 to 3, cooling, pool and room unit as well.
   * Entities that do not exist show an error card, so use *basic* unless you have the parts, or generate your own (below).
2. Create a dashboard (Settings > Dashboards > Add dashboard), open it, then three dots > Edit > three dots >
   *Raw configuration editor*, and paste the file.
3. The entity IDs in the committed files are **predicted** for a device named `Wärmepumpe` (the default name) in
   the language of the file. If your device has another name or you renamed entities, generate your own.

For a YAML-mode dashboard put the file where `configuration.yaml` points to it
(`lovelace: dashboards: <name>: mode: yaml, filename: ...`).

## Your own entity IDs

Home Assistant builds an entity ID from the device name and the entity name in the language that was active when the
entity was created. The generator solves this by looking the IDs up in your entity registry:

```bash
pip install pyyaml
python tools/gen_dashboard.py --registry /config/.storage/core.entity_registry --lang en > my_dashboard.yaml
```

* Disabled and missing entities are left out, optional parts are detected from the entities that exist, renamed
  entities are found by their unique ID (`<entry_id>_<key>`).
* Several heat pumps: add `--entry-id <config entry id>`.
* Without a registry file: `--name "My heat pump" --lang de --profile full` predicts the IDs.
* `--hacs` writes the optional view with apexcharts-card.
* The committed files are generated; `tests/test_dashboard.py` fails when they are out of date and checks the
  prediction against the entity IDs Home Assistant really creates (English and German).

Not verified: how the dashboards look in a browser. The structure, the entity IDs and the blueprints are tested
against the simulated heat pump; visual rendering was not checked.

## Blueprints

| Blueprint | Does |
|---|---|
| Block heating or hot water while a signal is on | Turns the block switches on while a signal (price, utility signal, schedule) is on and releases them afterwards, optionally after a maximum time |
| Trigger with hysteresis | Runs your actions when a value (PV surplus, price, power) stays above an upper or below a lower threshold for some minutes; writes nothing itself |
| Notify about problems | Runs your notification when the connection is lost, the error number changes or the utility lockout lasts long; writes nothing |

Import them from the links in the *Automation* view or with the buttons below.

[![Block while a signal is on](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/Bankaifan/ha-luxtronik-shi/blob/main/blueprints/automation/luxtronik_shi/block_while_signal.yaml)
[![Trigger with hysteresis](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/Bankaifan/ha-luxtronik-shi/blob/main/blueprints/automation/luxtronik_shi/surplus_trigger.yaml)
[![Notify about problems](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https://github.com/Bankaifan/ha-luxtronik-shi/blob/main/blueprints/automation/luxtronik_shi/notify_problems.yaml)

The blueprints select entities of this integration with a filter, so entity IDs never have to be typed.
Blocks act directly on the heat pump: do not use them together with a planner for the same circuit (the last
write wins), and remember that the controller drops values set through the interface after 10 minutes without
access or after a restart.

## Limits

* The effect of the power limit modes (soft, hard) on the controller is not verified by this project.
* The error number has no text: the interface provides none.
* The overview shows the controller's own values; it does not decide anything.
