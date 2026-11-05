# Luxtronik SHI (Modbus) for Home Assistant

🇩🇪 [Deutsche Version](README.de.md)

Home Assistant integration for **alpha innotec / Luxtronik heat pumps** via the **Modbus/TCP interface
"Smart Home Interface" (SHI)** – set up entirely in the UI (config flow), no YAML.

Developed and used daily on an **alpha innotec LWDV 91-1/3** (Luxtronik 2.x with SHI).
Other Luxtronik controllers with SHI should work but are untested.

## Features

| Area | Entities |
|---|---|
| Temperatures | flow, return, heat source inlet/outlet, outside average, return target/limit/minimum, return external, outside, room (room unit only), heating/hot water limit temperatures, hot water (actual, target, min, max), mixing circuits 1–3 (flow, target, min, max) |
| Power & energy | electric and thermal power, minimum electric power, electric/thermal energy counters (total, heating, hot water, cooling, pool), operating hours |
| Status | operating mode as text (heating, hot water, pool, utility lockout, defrost, off, external source, cooling), **compressor 1/2 running**, **auxiliary heater (ZWE) 1/2 active**, error number, heating/hot water/cooling/pool status, connection |
| **Write: numbers** | **heating curve offset** (−5 … +5 K), heating setpoint, hot water setpoint and offset, mixing circuits 1–3 setpoint and offset (heating and cooling), overall heating offset, power limit (0–30 kW) |
| **Write: selects** | mode (off / setpoint / offset / level) for heating, hot water, mixing circuits 1–3, overall heating; level (utility lockout / reduced / normal / boost); power limit (none / soft / hard) |
| **Write: switches** | *block heating*, *block hot water*, *block cooling*, *block pool*, **circulation pump**, *extra hot water* |
| Diagnostic | buffer tank type, switching lock, minimum runtime, limit/min/max values, equipment flags, firmware, undocumented raw values (disabled by default) |

A **climate entity** for the heating circuit combines the existing heating mode (off / heat) and heating setpoint
(10–70 °C) with the flow temperature as current value. It writes the same registers as the heating mode select and the
heating setpoint number. It is enabled by default on new installations; for entries created before it existed it is
disabled by default (enable it in the entity settings).

> Planners such as the Heat Pump Optimizer write the same registers (heating mode and setpoint). Do not use the climate
> entity and such a planner at the same time, or they overwrite each other.

Settings (numbers and selects) are in the *Configuration* section of the device page. Writes use the same registers as
the Smart Home Interface itself; the heat pump enforces its own limits.

### Structure in Home Assistant

Like the menus of the Luxtronik controller, the entities are split into devices:

| Device | Content |
|---|---|
| **<name>** (heat pump) | temperatures (flow, return, outside, heat source), status and operating mode, compressor/auxiliary heater, power, total energy and compressor hours, power limit, system values, firmware, equipment flags, raw values |
| **<name> Heating** | mode, setpoint, heating curve offset, level, overall heating, block, mixing circuits 1–3, heating energy and hours |
| **<name> Hot water** | temperatures, mode, setpoint, offset, level, block, circulation pump, extra hot water, hot water energy and hours |
| **<name> Cooling** / **<name> Pool** | only when cooling or a pool is selected in the equipment |

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

Key properties:

* **Block reads** instead of one request per value – easy on the heat pump. If the device rejects a block read
  (e.g. because a register in the gap does not exist), the integration falls back to single reads automatically.
* **Tiered polling**: measurements every cycle (default 30 s), counters/settings less often, firmware rarely.
* **Every write is read back**, so the UI always shows the real device state.
* Negative values (heating curve offset) are written correctly as 16-bit two's complement.
* German and English.

## Installation

The integration is not in the default catalog (yet), so it is added by link.

**Home Assistant 2026.11 or newer (Marketplace):**

1. **Settings → Marketplace → Add from link** → `https://github.com/Bankaifan/ha-luxtronik-shi`. Adding a repository by
   link needs a GitHub connection (device sign-in, read-only access to public data).
2. Install "Luxtronik SHI (Modbus)", restart Home Assistant.

**Older Home Assistant (HACS):**

1. HACS → ⋮ → **Custom repositories** → `https://github.com/Bankaifan/ha-luxtronik-shi`, category **Integration**.
2. Install "Luxtronik SHI (Modbus)", restart Home Assistant.

**Then, in both cases:**

Home Assistant can **discover the heat pump automatically** (DHCP) if both are in the same network segment
(DHCP traffic is not routed between VLANs) and the heat pump renews its lease: it then appears under *Settings → Devices &
services → Discovered*. Discovery only offers devices whose Smart Home Interface answers on Modbus/TCP port 502;
if your heat pump uses another port or unit ID, add it by hand. Discovery also follows IP address changes of a
heat pump that is already set up.

1. **Settings → Devices & services → Add integration → "Luxtronik SHI (Modbus)"**.
2. Enter name, IP address of the heat pump, port (502) and unit ID (1).
3. Confirm the installation equipment (see above).

Requirement: Modbus/TCP (Smart Home Interface) is enabled in the controller and the heat pump is reachable on the network.

> **Do not delete and re-add the integration** if other automations or a planner depend on its entity IDs.
> Re-adding creates new entities with default IDs. Use *Reconfigure* to change host, port or unit ID instead.

## Migrating from a YAML `modbus:` configuration

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

### Running alongside the native Luxtronik integration (port 8889)

Both integrations can run side by side but should be clearly separated:

* **luxtronik_shi (this integration):** the only path that **writes** (blocks, setpoints, modes, circulation pump)
  and the values a planner like the Heat Pump Optimizer needs.
* **Native Luxtronik integration (entities `luxtronik_<serial>_*`):** **diagnostics only** (additional measurements,
  parameters, error log). Disable its write entities (select, climate, switch, number) so two integrations do not
  write to the same controller. Enable diagnostic entities individually as needed.
* Settings only the native protocol offers (e.g. thermal disinfection / legionella protection) are not changed by
  this integration. That stays a deliberate decision of the operator.

### `tools/gen_yaml.py`

The script generates the equivalent YAML configuration (`modbus:` hub plus templates) from the register map. It is a
**legacy tool** for those who deliberately stay on YAML. It is no longer used in production and not tested against
register map changes. The recommended way is the integration.

## Sources of the register map

* [Bouni/python-luxtronik](https://github.com/Bouni/python-luxtronik), module `luxtronik/shi` and
  `luxtronik/definitions/{inputs,holdings}.py` (MIT): addresses, data types, ranges, firmware version.
  According to this source the SHI holding registers are **volatile** and are reset when the controller restarts –
  unlike the controller's persistent settings.
* Measurements on the reference installation (LWDV 91-1/3, firmware 3.92.3), see below.
* DHCP discovery matchers (MAC prefixes, hostname `wp-novelan`) are taken from
  [BenPru/luxtronik](https://github.com/BenPru/luxtronik) (MIT).
* Not contained in python-luxtronik and therefore only backed by observation: the equipment registers (discrete
  inputs 10000–10011), firmware major/minor version (10401/10402) and the interpretation of 10404/10406/10408 as
  operating hours.
* Complete table of all registers (type, address, data type, scale, unit, range): [docs/registers.md](docs/registers.md).

## Notes and limitations

* **Return / return target:** the published register list names 10100 "return target" and 10101 "return actual".
  Measured on a real installation it is the other way round (10100 follows the water temperature, 10101 jumps to the
  target while heating). The entities follow the measurement; python-luxtronik agrees.
* **Heating setpoint (reg. 10001):** measured, the value acts as return target, not as flow target (`return target`
  followed the written value). It only applies with heating mode `setpoint` (reg. 10000 = 1).
* **Block heating:** `switch.<name>_heating_block` only blocks heating; hot water keeps running. A planner (e.g. Heat
  Pump Optimizer) can block at a planned 0 W and release again if the planner fails or the room gets too cold.
* The *level* values (utility lockout / reduced / normal / boost) come from community documentation (probably
  SG-Ready) and are not confirmed on every firmware. Circulation pump and extra hot water require firmware 3.92.0.
* **Mixing circuit valve:** the SHI only provides temperatures and mode/setpoints of the mixing circuits, no valve
  position and no "valve always open" switch. That is configured on the controller (installer level).
* **Heating circulation pumps** (HUP) cannot be controlled via the SHI, only the hot water circulation pump. The native
  Luxtronik protocol (port 8889, e.g. the integration by BenPru) offers many more parameters.
* With hot water mode 0 ("off") the heat pump ignores the setpoint; the actual target is in the *hot water target*
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
Entity keys are a contract (`tests/test_contract.py`); see [CLAUDE.md](CLAUDE.md) for the working rules and
[CHANGELOG.md](CHANGELOG.md) for versioning.
Releases are created automatically: when a version bump reaches `main`, a GitHub Actions workflow tags it and
publishes the release with the CHANGELOG section as notes.

Long-term goal: move the protocol code into a library on PyPI and submit the integration to Home Assistant Core.

## Disclaimer

Unofficial, not affiliated with alpha innotec or Luxtronik. Use at your own risk.
