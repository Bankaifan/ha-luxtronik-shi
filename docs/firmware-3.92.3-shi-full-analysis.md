# Luxtronik 2.1 – Smart Home Interface (SHI, Modbus/TCP) – full analysis of firmware V3.92.3

Device: alpha innotec LWDV 91-1/3, Luxtronik 2.1, firmware `wp2reg-V3.92.3_260513_3a381baa`, binary `bin/Controller`
(ARM 32-bit LE, EABI5, C++, stripped, 2646 dynamic symbols). The analysis was made to achieve interoperability of the
independent integration `Bankaifan/ha-luxtronik-shi` (§ 69e UrhG). Only facts are recorded (addresses, types, limits,
texts, function addresses as evidence); no decompiled code.

Grades: **proven** = read directly from code/data · **likely** = concluded from code, evidence incomplete · **open** = not determined.
Addresses are virtual addresses in the binary (`FUN_…`). File offset = VA − 0x8000 (.text/.rodata) or VA − 0x10000 (.data).

Status 2026-11-08. Companion file: [`firmware-3.92.3-registers.csv`](firmware-3.92.3-registers.csv) (all 131 registers/bits with evidence and grade; German version: [`firmware-3.92.3-registers.de.csv`](firmware-3.92.3-registers.de.csv)). The analysis scripts (Ghidra/Capstone) and the working log are not part of this repository.

> German version: [firmware-3.92.3-shi-full-analysis.de.md](firmware-3.92.3-shi-full-analysis.de.md). Register table as CSV: [firmware-3.92.3-registers.csv](firmware-3.92.3-registers.csv) (English) and [firmware-3.92.3-registers.de.csv](firmware-3.92.3-registers.de.csv) (German). This file is the English translation of the analysis; the section below and the note on code fragments are not part of the analysis itself but place it in the repository's documentation.

### Relation to the existing documentation

This document extends [firmware-3.92.3-shi-analysis.md](firmware-3.92.3-shi-analysis.md) (mechanics, watchdog, deferred writes, error 816) and [firmware-3.92.3-register-meanings.md](firmware-3.92.3-register-meanings.md) (register meanings, measurements). Both stay valid unless stated otherwise below. Where an earlier statement is superseded or refined by this analysis, a note was added there; nothing was deleted.

* **10113:** `register-meanings` reads the register as a calculated heating flow target (return target plus moving average of the spread, assignment at `0x0019ac68`). This analysis reads the firmware text of t0/0x67 as "TVL calc max" (calculated maximum flow) and says the earlier interpretation "flow target heating (calculated)" is to be replaced by that text. Both statements name the same function `0x0019ac68`; the measured values (raw 253 with return target 20.0 and an average spread of 5.3 K; 25.7 °C with return target 20.0) contradict neither. No measurement decides whether the register is a setpoint or an upper limit. Both statements are kept.
* **10412:** "SW" stands for Schwimmbad (pool): firmware text "Schwimmbad", visibility `ID_Visi_Bst_BStdSW`. The earlier guess "2-hour units or an average" is superseded by the assumption that the divisor 7200 is a deviation in the SHI code (hours/2 on the wire; likely, not measurable without a pool).
* **10350 (VBO):** the firmware text reads "Ventil.-BOSUP / VBO". The long form of FP is still not stated by the firmware.
* **Watchdog, open item "default of each setpoint register":** answered by §3.4 and §4. t2 setpoints revert to a fixed default (350/400/200/300), the t1 parameter 10060 to its persisted value.
* **Levels (`_LEVELS`):** levels 1 and 2 use the same parameter ("increase"), level 3 the "decrease" parameter; python-luxtronik's "Increased2" is not a separate value in the firmware (§3.1, §5 item 3).
* **10060:** the value range is still open (§3.3, §6); new is the availability condition (RBE present, connected, influence factor greater than 0).
* **New compared with both documents:** revert on an out-of-range write (§1.4, §4), the value ranges of all holdings (§2.1, §5 item 4), overall mode 10065–10067, the parameter "Enable SHI", discrete inputs (§2.3), word order of the 32-bit counters, visibility IDs.

On wording: the analysis records function addresses (`FUN_…`, `0x…`) as evidence but no decompiled code. A few calls and assignments of the working version are rendered in words here.

---

## 1. Overview: how the SHI works

### 1.1 Object structure (proven)

* Constructor `ModBus_TCP::SmartHomeInterface` = `FUN_000dc298`: base offset **10000** for both tables (set through `FUN_000d5b00`); builds two pointer arrays:
  `FUN_000d8014` → holdings (object offset +8, 0x49 = 73 slots) and `FUN_000d95d4` → inputs (offset +0x12c, 0x1f7 = 503 slots). Slot = address − 10000; an empty slot → Modbus exception 2.
* Dispatcher `FUN_000d9298` (parameters: start address, count, buffer, read/write flag, array base, array length): calls `FUN_000de744` **first** (watchdog re-arm, §4), then `avail()` (vtable+8) for each register.
  Not available → read value **0x7FFF**, a write is silently skipped. Available → `get()` (vtable+0xc), or a write through `FUN_000dc76c` → `set()` (vtable+0x14).
* **Discrete inputs (FC 2)** exist as well: handler `FUN_000db9b0` (vtable slot 4 of the SHI), addresses 10000–10011 (table §2.3). From address 10012 → exception 2. Coils (FC 1/5) are not implemented (no handler in the vtable 0x9c3510).
* **Sign** (`FUN_000dc76c`): object field +4 = 0 → INT16, 1 → UINT16. Register constructor `FUN_000dd2e8` (parameters: GDI item from ID and table, sign, divisor).
* **Divisor** (getter `FUN_000dfbb4`): wire = round(internal / divisor) for divisor ≥ 2, otherwise internal. The wire value is already the engineering value (0.1 °C; h; 0.1 kWh …).
* **Availability** `avail()` = `FUN_000dfc98`: fetches the *visibility ID* of the bound GDI item (`FUN_00425c10`) and checks the visibility table `FUN_003d9e0c` (byte array `DAT_00a19464`; ID −1 = always, −2 or 0x191 = never).
  **New:** firmware visibility ID + 2 = python-luxtronik visibility index (`visibilities.py`): firmware 0 = `ID_Visi_Heizung` (index 2), 5 = `ID_Visi_MK1` (7), 0xd1 = `ID_Visi_MK3` (211), 0xf8 = `ID_Visi_Solar` (250), 0x12a = `ID_Visi_RBE` (300) … consistent on more than 40 items → **proven**. So for every register it is known which equipment makes it visible (column "Visibility").
* Classes (vtables): `Register` 0x9c3678; `Register::Bound` 0x9c36c8 (all normal registers); `Register::Fixed` 0x9c3698 (constant, constructor `FUN_000dc81c` takes the value, always available);
  `Register::MultiByte` 0x9c3640 (32 bit over two registers, high word first; `FUN_000d94b4` creates two partial registers of 0x14 bytes each); `RBE_RoomTemperatureSetpointRegister` 0x9c3780 (10060 only).

### 1.2 GDI – the internal data points (proven)

Every register is bound to a GDI item `t<table>/<ID>` (resolver `FUN_0042bf8c`). Three tables:

* **t0** (handle constructor `FUN_0042c6ec`): runtime/measured values. Registration with **variable address, text ID, visibility ID, format** in `FUN_0009ab8c` (temperatures), `FUN_0008bef8` (outputs), `FUN_0009833c` (inputs), `FUN_0008b908` (energy counters), `FUN_00096648` (status), `FUN_0008d0a8` (SHI's own items) and others.
  The variables are exported symbols (`Temperatur_TVL`, `HUPout`, `Zaehler_BetrZeitWP` …) and correspond to the `ID_WEB_*` names of python-luxtronik.
* **t1** (`FUN_0042c76c`): persisted **parameters**. The t1 ID **is** the python-luxtronik parameter index (`parameters.py`): t1/87 = `ID_Einst_TRBegr_akt`, t1/979 = `ID_Einst_Minimale_Ruecklaufsolltemperatur`, t1/973 = `ID_Einst_BW_max`, t1/1072–1077 = `ID_Einst_MinVLMK1..3/MaxVLMK1..3`, t1/1148 = `HEATING_TARGET_TEMP_ROOM_THERMOSTAT` = `RBE_Raumtemperatur_Soll`, t1/668/728/729/730/859/882 = operating-hour counters, t1/1146/1147 = `ExtraDHW::temperatureSetpoint/durationSetpoint` (still `Unknown_Parameter_1146/1147` in python-luxtronik).
* **t2** (`FUN_0042c7ec`): the **volatile SHI write values**, 0x29 = 41 items, created in `FUN_0008d0a8` (IDs 2–0x28) and `FUN_0009bab4` (IDs 0, 1). This is where the **limits** are (`GDI::Boundaries::Range`, created through `FUN_004220b4` with minimum, maximum and step; check `FUN_00421f2c`: the value lies between minimum and maximum and its distance from the minimum is an integer multiple of the step; source `Modules/GDI/Boundaries/Range.cpp`) and the **enum lists** ("Setpoint/Offset/Level", "No limit/Soft limit/Hard limit").
  Boot defaults of all t2 items: `FUN_00087e9c` (table in §3.4), set in `FUN_0009da20`.

### 1.3 Text table (new, proven)

`.data`, file offset 0x9ce58c (VA 0x9de58c): 24 pointers per text ID (languages; 0 = German, 1 = English), row 0 = language names, row n+1 = text ID n. `scripts/texts.py` → 1372 texts. This resolves the display names of all GDI items (column "Firmware text").

### 1.4 Write path (proven)

`Register::Bound::set()` (`FUN_000dfa6c`) creates a lambda (`FUN_000defd4`; client ID = CRC32 over the peer address) and runs it in the application thread (`FUN_000df0bc`):

1. `smart_home_interface::write_log::update` (`FUN_00187314`, called with the data point, source 6 = SHI and the client ID): writer log per data point; more than 2 writers within 3600 s → error index 0x6F (816), the write is discarded (return 0, **no** Modbus exception).
2. Range check `FUN_0042486c` → `Range::isValid` (`FUN_00421f2c`). **Invalid value → revert `FUN_000881e0`: the item is reset to its default/persisted value**, not to the previous value; return 0, no Modbus exception. Example: 10001 = 900 (90 °C) resets 10001 to 350; 10000 = 5 resets 10000 to 0.
3. Valid → `GDI::Item::set` (`FUN_004270bc`, called with the value, source 6 and not deferred); for t2 5/6/7/0x27 (DHW group) through the pending map (§3.2). Writing the value that is already stored is a no-op (and deletes a pending map entry).

---

## 2. Complete register table

The columns "Min/Max" and "Default" are internal values = wire values (divisor 1). "GDI" = table/ID, "Symbol" = exported firmware variable, "Visibility" = firmware visibility ID with python-luxtronik name (index +2). All entries come from the builders `FUN_000d8014`/`FUN_000d95d4` (parser `scripts/parse_builder.py`), limits from `FUN_0008d0a8`. Complete evidence columns are in the CSV; there, `fn_<address>.c` in the evidence column means the function at that address. Free-text columns of the tables are translated; the "Firmware text (de/en)" column is the firmware's own German/English text pair and stays as is.

### 2.1 Holding registers (FC 3/6/16, all writable, 1 word, divisor 1)

| Address | Type | Min | Max | Default | GDI | Symbol | Firmware text (de/en) | Visibility | Meaning | Grade |
|---|---|---|---|---|---|---|---|---|---|---|
| 10000 | UINT16 |  |  | 0 | t2/0x2 (2) |  |  | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Heating: SHI mode | proven |
| 10001 | UINT16 | 150 | 750 | 350 | t2/0x3 (3) |  |  | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Heating: return setpoint | proven |
| 10002 | INT16 | -200 | 200 | 0 | t2/0x4 (4) |  |  | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Heating: return offset | proven |
| 10003 | UINT16 | 0 | 3 | 0 | t2/0x23 (35) |  |  | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Heating: level | proven |
| 10005 | UINT16 |  |  | 0 | t2/0x5 (5) |  |  | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | DHW: SHI mode | proven |
| 10006 | UINT16 | 300 | 750 | 400 | t2/0x6 (6) |  |  | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | DHW: setpoint | proven |
| 10007 | INT16 | -200 | 200 | 0 | t2/0x7 (7) |  |  | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | DHW: offset | proven |
| 10008 | UINT16 | 0 | 3 | 0 | t2/0x27 (39) |  |  | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | DHW: level | proven |
| 10010 | UINT16 |  |  | 0 | t2/0x8 (8) |  |  | 5 (python-luxtronik Visi 7: ID_Visi_MK1) | MC1 heating: SHI mode | proven |
| 10011 | UINT16 | 200 | 650 | 350 | t2/0x9 (9) |  |  | 5 (python-luxtronik Visi 7: ID_Visi_MK1) | MC1 heating: flow setpoint | proven |
| 10012 | INT16 | -50 | 50 | 0 | t2/0xa (10) |  |  | 5 (python-luxtronik Visi 7: ID_Visi_MK1) | MC1 heating: offset | proven |
| 10013 | UINT16 | 0 | 3 | 0 | t2/0x24 (36) |  |  | 5 (python-luxtronik Visi 7: ID_Visi_MK1) | MC1 heating: level | proven |
| 10015 | UINT16 |  |  | 0 | t2/0xb (11) |  |  | 398 (python-luxtronik Visi 400: unknown) | MC1 cooling: SHI mode | likely |
| 10016 | UINT16 | 50 | 250 | 200 | t2/0xc (12) |  |  | 398 (python-luxtronik Visi 400: unknown) | MC1 cooling: setpoint | likely |
| 10017 | INT16 | -50 | 50 | 0 | t2/0xd (13) |  |  | 398 (python-luxtronik Visi 400: unknown) | MC1 cooling: offset | likely |
| 10020 | UINT16 |  |  | 0 | t2/0xe (14) |  |  | 6 (python-luxtronik Visi 8: ID_Visi_MK2) | MC2 heating: SHI mode | proven |
| 10021 | UINT16 | 200 | 650 | 350 | t2/0xf (15) |  |  | 6 (python-luxtronik Visi 8: ID_Visi_MK2) | MC2 heating: flow setpoint | proven |
| 10022 | INT16 | -50 | 50 | 0 | t2/0x10 (16) |  |  | 6 (python-luxtronik Visi 8: ID_Visi_MK2) | MC2 heating: offset | proven |
| 10023 | UINT16 | 0 | 3 | 0 | t2/0x25 (37) |  |  | 6 (python-luxtronik Visi 8: ID_Visi_MK2) | MC2 heating: level | proven |
| 10025 | UINT16 |  |  | 0 | t2/0x11 (17) |  |  | 399 (python-luxtronik Visi 401: unknown) | MC2 cooling: SHI mode | likely |
| 10026 | UINT16 | 50 | 250 | 200 | t2/0x12 (18) |  |  | 399 (python-luxtronik Visi 401: unknown) | MC2 cooling: setpoint | likely |
| 10027 | INT16 | -50 | 50 | 0 | t2/0x13 (19) |  |  | 399 (python-luxtronik Visi 401: unknown) | MC2 cooling: offset | likely |
| 10030 | UINT16 |  |  | 0 | t2/0x14 (20) |  |  | 209 (python-luxtronik Visi 211: ID_Visi_MK3) | MC3 heating: SHI mode | proven |
| 10031 | UINT16 | 200 | 650 | 350 | t2/0x15 (21) |  |  | 209 (python-luxtronik Visi 211: ID_Visi_MK3) | MC3 heating: flow setpoint | proven |
| 10032 | INT16 | -50 | 50 | 0 | t2/0x16 (22) |  |  | 209 (python-luxtronik Visi 211: ID_Visi_MK3) | MC3 heating: offset | proven |
| 10033 | UINT16 | 0 | 3 | 0 | t2/0x26 (38) |  |  | 209 (python-luxtronik Visi 211: ID_Visi_MK3) | MC3 heating: level | proven |
| 10035 | UINT16 |  |  | 0 | t2/0x17 (23) |  |  | 400 (python-luxtronik Visi 402: unknown) | MC3 cooling: SHI mode | likely |
| 10036 | UINT16 | 50 | 250 | 200 | t2/0x18 (24) |  |  | 400 (python-luxtronik Visi 402: unknown) | MC3 cooling: setpoint | likely |
| 10037 | INT16 | -50 | 50 | 0 | t2/0x19 (25) |  |  | 400 (python-luxtronik Visi 402: unknown) | MC3 cooling: offset | likely |
| 10040 | UINT16 |  |  | 0 | t2/0x1a (26) |  | LPC Modus / LPC mode | always (−1) | Power limitation: mode (LPC) | proven |
| 10041 | UINT16 | 0 | 300 | 300 | t2/0x1b (27) |  | PC Limit / PC limit | always (−1) | Power limitation: limit value | proven |
| 10050 | UINT16 |  |  | 0 | t2/0x1e (30) |  | Sperre Heizung / Heating blocked | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Heating block | proven |
| 10051 | UINT16 |  |  | 0 | t2/0x1f (31) |  | Sperre Warmwasser / DHW blocked | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | DHW block | proven |
| 10052 | UINT16 |  |  | 0 | t2/0x1c (28) |  | Sperre Kühlung / Cooling blocked | always (−1) | Cooling block | proven |
| 10053 | UINT16 |  |  | 0 | t2/0x1d (29) |  | Sperre Schwimmbad / Pool blocked | always (−1) | Pool block | proven |
| 10060 | UINT16 |  |  |  | t1/0x47c (1148) | RBE_Raumtemperatur_Soll | Raumtemperatur Soll / desired room temp. | 374 (python-luxtronik Visi 376: Unknown_Visibility_376) | Room temperature setpoint (RBE) | proven |
| 10065 | UINT16 |  |  | 0 | t2/0x20 (32) |  |  | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Overall: SHI mode | proven |
| 10066 | INT16 | -50 | 50 | 0 | t2/0x21 (33) |  |  | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Overall: offset | proven |
| 10067 | UINT16 | 0 | 3 | 0 | t2/0x22 (34) |  |  | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Overall: level | proven |
| 10070 | UINT16 |  |  | 0 | t2/0x28 (40) |  | Zirkulation / secondary return | 8 (python-luxtronik Visi 10: ID_Visi_Zirkulation) | Circulation pump | proven |
| 10071 | UINT16 |  |  | 0 | t2/0x1 (1) |  | Extra Warmwasser / Extra DHW | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Extra DHW | proven |

Mode enum (all `*_mode`, visibility-dependent): 0 = no influence, 1 = setpoint, 2 = offset, 3 = level (texts `FUN_0008d0a8`: "Setpoint", "Offset", "Level"; the limits of the mode items are enum lists without a Range object).
Level (`*_level`, Range 0..3): 0 = normal, 1 and 2 = **increase** (both use the same parameter "Erhöhung %1"), 3 = **decrease** (parameter "Absenkung %1"); see §3.1.
Blocks (10050–10053) and switches (10070/10071): enum 0/1 (texts of the 0x4fe group: "Sperre Heizung/Warmwasser/Kühlung/Schwimmbad", "Zirkulation", "Extra Warmwasser"); no Range object, every value other than 0 acts as 1 (`FUN_00064588` is checked for "not equal to 0" or "equal to 1" depending on the consumer, see CSV).

### 2.2 Input registers (FC 4, read only)

| Address | Class | Type | Divisor | Fixed | GDI | Symbol | Firmware text (de/en) | Visibility | Meaning | Grade |
|---|---|---|---|---|---|---|---|---|---|---|
| 10000 | Register | UINT16 | 1 |  | t0/0x55 (85) |  | Heat generator status | always (−1) | Heat generator status (bit mask) | likely |
| 10002 | Register | UINT16 | 1 |  | t0/0x11 (17) |  | Betriebszustand / operation mode | always (−1) | Operating state | proven |
| 10003 | Register | UINT16 | 1 |  | t0/0x2d (45) |  | Status Heizung / Status Heating | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Heating status | proven |
| 10004 | Register | UINT16 | 1 |  | t0/0x2e (46) |  | Status Warmwasser / Status DHW | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | DHW status | proven |
| 10006 | Register | UINT16 | 1 |  | t0/0x2f (47) |  | Status Kühlung / Status Cooling | 3 (python-luxtronik Visi 5: ID_Visi_Kuhlung) | Cooling status | proven |
| 10007 | Register | UINT16 | 1 |  | t0/0x30 (48) |  | Status Schwimmbad / Status Pool | 228 (python-luxtronik Visi 230: ID_Visi_Bst_BStdSW) | Pool status | proven |
| 10100 | Register | UINT16 | 1 |  | t0/0x1 (1) | Temperatur_TRL | Rücklauf / return | 22 (python-luxtronik Visi 24: ID_Visi_Temp_Rucklauf) | Return actual (Temperatur_TRL) | proven |
| 10101 | Register | UINT16 | 1 |  | t0/0x2 (2) | Sollwert_TRL_HZ | Rückl.-Soll / return target | 23 (python-luxtronik Visi 25: ID_Visi_Temp_RL_Soll) | Return target (Sollwert_TRL_HZ) | proven |
| 10102 | Register | UINT16 | 1 |  | t0/0x3 (3) | Temperatur_TRL_ext | Rückl.-Extern / return external | 24 (python-luxtronik Visi 26: ID_Visi_Temp_Ruecklext) | Return external | proven |
| 10103 | Register | INT16 | 1 |  | t1/0x57 (87) |  | Rückl.-Begr. / return temp. limit. | 92 (python-luxtronik Visi 94: ID_Visi_EinstTemp_RucklBegr) | Return limit (Einst_TRBegr) | proven |
| 10104 | Register | INT16 | 1 |  | t1/0x3d3 (979) |  | Min. Rückl.Solltemp. / min return targ.temp | 295 (python-luxtronik Visi 297: ID_Visi_Einst_Minimale_Ruecklaufsolltemperatur) | Minimum return target temperature | proven |
| 10105 | Register | UINT16 | 1 |  | t0/0x0 (0) | Temperatur_TVL | Vorlauf / flow | 21 (python-luxtronik Visi 23: ID_Visi_Temp_Vorlauf) | Flow actual (Temperatur_TVL) | proven |
| 10106 | Register | INT16 | 1 |  | t0/0x29 (41) | RBE_Raumtemperatur_Ist | Raumtemperatur Ist / current room temp. | 298 (python-luxtronik Visi 300: ID_Visi_RBE) | Room temperature actual (RBE) | proven |
| 10107 | Register | INT16 | 1 |  | t0/0x57 (87) |  | Heating demand border | always (−1) | Heating demand border ("Heating demand border") | proven |
| 10108 | Register | INT16 | 1 |  | t0/0x5 (5) | Temperatur_TA | Außentemperatur / outdoor temp. | 26 (python-luxtronik Visi 28: ID_Visi_Temp_Aussent) | Outside temperature | proven |
| 10109 | Register | INT16 | 1 |  | t0/0x27 (39) | Mitteltemperatur | Mitteltemperatur / outdoor temp. ø | 182 (python-luxtronik Visi 184: ID_Visi_Mitteltemperatur) | Outside temperature average | proven |
| 10110 | Register | INT16 | 1 |  | t0/0x8 (8) | Temperatur_TWE | Wärmequelle-Ein / heat source inlet | 29 (python-luxtronik Visi 31: ID_Visi_Temp_WQ_Ein) | Heat source inlet | proven |
| 10111 | Register | INT16 | 1 |  | t0/0x9 (9) | Temperatur_TWA | Wärmequelle-Aus / heat source outlet | 30 (python-luxtronik Visi 32: ID_Visi_Temp_Kaltekreis) | Heat source outlet | proven |
| 10112 | Register | INT16 | 1 |  | t0/0x66 (102) |  | Vorlauf max. / max. flow temp. | always (−1) | Flow max. | proven |
| 10113 | Register | INT16 | 1 |  | t0/0x67 (103) |  | TVL calc max | 357 (python-luxtronik Visi 359: Unknown_Visibility_359) | TVL calc max (calculated max. flow) | proven |
| 10120 | Register | INT16 | 1 |  | t0/0x6 (6) | Temperatur_TBW | Warmwasser-Ist / DHW | 27 (python-luxtronik Visi 29: ID_Visi_Temp_BW_Ist) | DHW actual | proven |
| 10121 | Register | UINT16 | 1 |  | t0/0x7 (7) |  | Warmwasser-Soll / DHW target | 28 (python-luxtronik Visi 30: ID_Visi_Temp_BW_Soll) | DHW target | proven |
| 10122 | Fixed | UINT16 |  | 300 |  |  |  |  | DHW minimum (constant) | proven |
| 10123 | Register | INT16 | 1 |  | t1/0x3cd (973) |  | Max.Warmwassertemp. / DHW temp. max. | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | DHW maximum (Einst_BW_max) | proven |
| 10124 | Register | INT16 | 1 |  | t0/0x58 (88) |  | DHW Demand border | always (−1) | DHW demand border | proven |
| 10140 | Register | INT16 | 1 |  | t0/0x17 (23) | Temperatur_TFB1 | Mischkreis1-Vorlauf / mix circ1 flow | 31 (python-luxtronik Visi 33: ID_Visi_Temp_MK1_Vorlauf) | MC1 flow actual | proven |
| 10141 | Register | INT16 | 1 |  | t0/0x16 (22) |  | Mischkreis1 VL-Soll / mix circ1 target | 32 (python-luxtronik Visi 34: ID_Visi_Temp_MK1VL_Soll) | MC1 flow target | proven |
| 10142 | Register | INT16 | 1 |  | t1/0x430 (1072) |  |  |  | MC1 flow minimum | proven |
| 10143 | Register | INT16 | 1 |  | t1/0x433 (1075) |  |  |  | MC1 flow maximum | proven |
| 10150 | Register | INT16 | 1 |  | t0/0x19 (25) | Temperatur_TFB2 | Mischkreis2-Vorlauf / MC2 flow | 34 (python-luxtronik Visi 36: ID_Visi_Temp_MK2_Vorlauf) | MC2 flow actual | proven |
| 10151 | Register | INT16 | 1 |  | t0/0x18 (24) |  | Mischkreis2 VL-Soll / MC2 flow target | 35 (python-luxtronik Visi 37: ID_Visi_Temp_MK2VL_Soll) | MC2 flow target | proven |
| 10152 | Register | INT16 | 1 |  | t1/0x431 (1073) |  |  |  | MC2 flow minimum | proven |
| 10153 | Register | INT16 | 1 |  | t1/0x434 (1076) |  |  |  | MC2 flow maximum | proven |
| 10160 | Register | INT16 | 1 |  | t0/0x1b (27) | Temperatur_TFB3 | Mischkreis3-Vorlauf / MC3 flow | 210 (python-luxtronik Visi 212: ID_Visi_Temp_MK3_Vorlauf) | MC3 flow actual | proven |
| 10161 | Register | INT16 | 1 |  | t0/0x1a (26) |  | Mischkreis3 VL-Soll / MC3 flow target | 211 (python-luxtronik Visi 213: ID_Visi_Temp_MK3VL_Soll) | MC3 flow target | proven |
| 10162 | Register | INT16 | 1 |  | t1/0x432 (1074) |  |  |  | MC3 flow minimum | proven |
| 10163 | Register | INT16 | 1 |  | t1/0x435 (1077) |  |  |  | MC3 flow maximum | proven |
| 10201 | Register | UINT16 | 1 |  | t0/0x54 (84) |  | Fehlernummer / error number | always (−1) | Error number | proven |
| 10202 | Register | UINT16 | 1 |  | t0/0x53 (83) |  | Einbindung / integration | always (−1) | Integration / buffer type | proven (name); values from python-luxtronik |
| 10203 | Fixed | UINT16 |  | 20 |  |  |  |  | Switching cycle lock (constant) | proven |
| 10204 | Fixed | UINT16 |  | 20 |  |  |  |  | Minimum run time (constant) | proven |
| 10205 | Register | UINT16 | 1 |  | t0/0x59 (89) |  | Cooling enabled | always (−1) | Cooling configured | proven |
| 10206 | Register | UINT16 | 1 |  | t0/0x5a (90) |  | Pool enabled | always (−1) | Pool configured | proven |
| 10207 | Register | UINT16 | 1 |  | t0/0x32 (50) | Signal_CoolingClearance | Freigabe Kühlung / release cooling | 3 (python-luxtronik Visi 5: ID_Visi_Kuhlung) | Cooling release | proven |
| 10300 | Register | INT16 | 100 |  | t0/0x15 (21) | Waermeleistung | Heizleistung Ist / Heating capacity | 342 (python-luxtronik Visi 344: Unknown_Visibility_344) | Heating capacity actual (Waermeleistung) | proven |
| 10301 | Register | UINT16 | 100 |  | t0/0x5b (91) |  | Leistungsaufnahme / Power Consumption | always (−1) | Power consumption (electricPowerConsumption) | proven |
| 10302 | Register | UINT16 | 1 |  | t0/0x5c (92) |  | Power consumption min | always (−1) | Power consumption minimum (forecast) | proven |
| 10310 | MultiByte(Register) | UINT32 | 10 |  | t0/0x62 (98) |  | Gesamt / total | always (−1) | Electrical energy total | proven |
| 10312 | MultiByte(Register) | UINT32 | 10 |  | t0/0x5d (93) |  | Heizung / heating | always (−1) | Electrical energy heating | proven |
| 10314 | MultiByte(Register) | UINT32 | 10 |  | t0/0x5e (94) |  | Warmwasser / domestic hot water | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Electrical energy DHW | proven |
| 10316 | MultiByte(Register) | UINT32 | 10 |  | t0/0x60 (96) |  | Kühlung / cooling | 3 (python-luxtronik Visi 5: ID_Visi_Kuhlung) | Electrical energy cooling | proven |
| 10318 | MultiByte(Register) | UINT32 | 10 |  | t0/0x5f (95) |  | Schwimmbad / swimming pool | 228 (python-luxtronik Visi 230: ID_Visi_Bst_BStdSW) | Electrical energy pool | proven |
| 10320 | MultiByte(Register) | INT32 | 10 |  | t0/0x68 (104) |  | Wärmemenge WQ gesamt / total heat quant. HS | always (−1) | Heat quantity total | proven |
| 10322 | MultiByte(Register) | INT32 | 10 |  | t0/0x69 (105) |  | Heizen / heating | 0 (python-luxtronik Visi 2: ID_Visi_Heizung) | Heat quantity heating | proven |
| 10324 | MultiByte(Register) | INT32 | 10 |  | t0/0x6a (106) |  | Warmwasser / domestic hot water | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Heat quantity DHW | proven |
| 10326 | MultiByte(Register) | INT32 | 10 |  | t0/0x6b (107) |  | Kühlung / cooling | 3 (python-luxtronik Visi 5: ID_Visi_Kuhlung) | Heat quantity cooling | proven |
| 10328 | MultiByte(Register) | INT32 | 10 |  | t0/0x6c (108) |  | Schwimmbad / swimming pool | 2 (python-luxtronik Visi 4: ID_Visi_Schwimmbad) | Heat quantity pool | proven |
| 10350 | Register | UINT16 | 1 |  | t0/0x45 (69) | VBOout | Ventil.-BOSUP / VBO | 54 (python-luxtronik Visi 56: ID_Visi_OUT_Ventil_BOSUP) | Output VBO | proven |
| 10351 | Register | UINT16 | 1 |  | t0/0x6d (109) | FP1out |  | 49 (python-luxtronik Visi 51: ID_Visi_OUT_FUP1) | Output FP1 | proven |
| 10352 | Register | UINT16 | 1 |  | t0/0x4c (76) | FP2out | FP2 / FP2 | 62 (python-luxtronik Visi 64: ID_Visi_OUT_FUP2) | Output FP2 | proven |
| 10353 | Register | UINT16 | 1 |  | t0/0x4d (77) | FP3out | FP3 / FP3 | 225 (python-luxtronik Visi 227: ID_Visi_OUT_FUP3) | Output FP3 | proven |
| 10354 | Register | UINT16 | 1 |  | t0/0x20 (32) | HUPout | HUP / HUP | 50 (python-luxtronik Visi 52: ID_Visi_OUT_HUP) | Output HUP | proven |
| 10355 | Register | UINT16 | 1 |  | t0/0x44 (68) | BUPout | BUP / BUP - DHW pump | 48 (python-luxtronik Visi 50: ID_Visi_OUT_BUP) | Output BUP | proven |
| 10356 | Register | UINT16 | 1 |  | t0/0x48 (72) | ZIPout | ZIP / ZIP | 57 (python-luxtronik Visi 59: ID_Visi_OUT_ZIP) | Output ZIP | proven |
| 10360 | Register | UINT16 | 1 |  | t0/0x2a (42) | EVUin | EVU / EVU | 41 (python-luxtronik Visi 43: ID_Visi_IN_EVU) | Input EVU | proven |
| 10361 | Register | UINT16 | 1 |  | t0/0x2b (43) | EVU2in | EVU 2 / EVU 2 | 306 (python-luxtronik Visi 308: ID_Visi_HZIO) | Input EVU 2 | proven |
| 10400 | Fixed | UINT16 |  | 3 |  |  |  |  | Firmware major | proven |
| 10401 | Fixed | UINT16 |  | 92 |  |  |  |  | Firmware minor | proven |
| 10402 | Fixed | UINT16 |  | 3 |  |  |  |  | Firmware patch | proven |
| 10404 | MultiByte(Register) | UINT32 | 3600 |  | t1/0x29c (668) | Zaehler_BetrZeitWP | Betriebstunden WP / operating hours HP | 87 (python-luxtronik Visi 89: ID_Visi_Bst_BStdWP) | Operating hours heat pump | proven |
| 10406 | MultiByte(Register) | UINT32 | 3600 |  | t1/0x2d8 (728) | Zaehler_BetrZeitHz | Betriebstunden Heiz. / operat. hours heat. | 195 (python-luxtronik Visi 197: ID_Visi_Bst_BStdHz) | Operating hours heating | proven |
| 10408 | MultiByte(Register) | UINT32 | 3600 |  | t1/0x2d9 (729) | Zaehler_BetrZeitBW | Betriebstunden WW / operating hours DHW | 196 (python-luxtronik Visi 198: ID_Visi_Bst_BStdBW) | Operating hours DHW | proven |
| 10410 | MultiByte(Register) | UINT32 | 3600 |  | t1/0x2da (730) | Zaehler_BetrZeitKue | Betriebstunden Kuehl / operat. hours cool. | 197 (python-luxtronik Visi 199: ID_Visi_Bst_BStdKue) | Operating hours cooling | proven |
| 10412 | MultiByte(Register) | UINT32 | 7200 |  | t1/0x35b (859) | Zaehler_BetrZeitSW | Schwimmbad / swimming pool | 228 (python-luxtronik Visi 230: ID_Visi_Bst_BStdSW) | Operating hours pool (SW) | proven (counter), purpose of the divisor open |
| 10416 | MultiByte(Register) | UINT32 | 3600 |  | t1/0x372 (882) | BSTD_Solar | Betriebstunden Solar / operating hours solar | 248 (python-luxtronik Visi 250: ID_Visi_Solar) | Operating hours solar | proven |
| 10500 | Register | INT16 | 1 |  | t1/0x47a (1146) | ExtraDHW::temperatureSetpoint | Sollwert / targ.value | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Extra DHW target temperature | proven |
| 10501 | Register | INT16 | 60 |  | t1/0x47b (1147) | ExtraDHW::durationSetpoint | Dauer Extra Warmwasser / duration extra DHW | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Extra DHW duration | proven |
| 10502 | Register | INT16 | 60 |  | t0/0x3a (58) | ExtraDHW::timer | Laufzeit / running time | 1 (python-luxtronik Visi 3: ID_Visi_Brauwasser) | Extra DHW remaining run time | proven |

Specifics:
* 10107 is **not** the parameter "Heizgrenze" (heating limit) but the SHI's own item t0/0x57 "Heating demand border": the effective demand threshold of the heating (= effective return setpoint − hysteresis `Einst_HRHyst_akt`, with mode-dependent tracking in `FUN_00206268`; written in `FUN_00205d68`). Likewise 10124 = t0/0x58 "DHW Demand border" (`FUN_002071a8`). The names "heating_limit"/"dhw_limit" in python-luxtronik are correct in meaning ("limit temperature, demand when it is undershot").
* 10100/10101: the firmware binds 10100 to `Temperatur_TRL` (actual) and 10101 to `Sollwert_TRL_HZ` (target) – i.e. as measured in `registers.py`; the naming in the published lists was swapped.
* 10112 = t0/0x66 "Vorlauf max." (source `FUN_0027043c` → `DAT_00a177c8`), 10113 = t0/0x67 "TVL calc max" (calculated maximum flow; visibility 0x165 = python-luxtronik Visi 359). The previous interpretation "flow setpoint heating (calculated)" is to be replaced by the firmware text.
* 10300/10301: internally watts (float `Waermeleistung` or `electricPowerConsumption`, display format "%.02f kW" with factor 0.001); divisor 100 → wire = W/100 → `registers.py` scale 100 is correct. 10302 = forecast of the minimum power consumption (`FUN_002f96cc` → `DAT_00a19118`, `FUN_002f9640` writes divided by 100).
* Energy counters 10310–10328: t0/0x5d–0x6c, group "Leistungsaufnahme" (power consumption; `FUN_0008b908`, format "%.01f kWh" factor 0.01 → internal 10 Wh, divisor 10 → wire 0.1 kWh). Order heating (0x5d), DHW (0x5e), pool (0x5f), cooling (0x60), total (0x62); heat quantity 0x68 total, 0x69 heating, 0x6a DHW, 0x6b cooling, 0x6c pool. Electrical UINT32, thermal INT32 (builder sign).
* 10412 divisor **7200**: counter `Zaehler_BetrZeitSW` (operating hours pool; firmware text "Schwimmbad", visibility 0xe4 = `ID_Visi_Bst_BStdSW`). The firmware display itself uses the same factor 1/3600 for this counter as for all others (format "%.0fh", constant 0x3f323456…). The SHI divisor 7200 is therefore a deviation of the SHI code (probably a typo, 0x1c20 instead of 0xe10); wire value = hours/2 → multiply by 2 to show hours (**likely**; cannot be conclusively checked without a live measurement, as the reference installation has no pool).
* 10500/10501/10502 = extra DHW: target temperature (parameter 1146, 0.1 °C), duration (parameter 1147, internal s, wire min) and remaining timer (`ExtraDHW::timer`, internal s, wire min; decremented per tick in `FUN_0025662c`).

### 2.3 Discrete inputs (FC 2) – newly documented

| Address | Meaning | Condition | Grade |
|---|---|---|---|
| 10000 | Equipment heating | device_config bit 1 && Ba_Hz_akt != 4 (heating operating mode not "off") | proven |
| 10001 | Equipment DHW | device_config bit 2 && Ba_Bw_akt != 4 | proven |
| 10002 | Equipment cooling | t0/0x59 "Cooling enabled" != 0 | proven |
| 10003 | Equipment pool | t0/0x5a "Pool enabled" != 0 | proven |
| 10004 | Equipment solar | Firmware visibility 0xf8 (248) = python-luxtronik Visi 250 ID_Visi_Solar (firmware ID + 2 = python-luxtronik index, proven on 40+ items) | proven |
| 10005 | Room controller (RBE) | Einst_RFVEinb_akt == 4 | proven |
| 10006 | MC1 heating | Firmware visibility 5 = python-luxtronik Visi 7 ID_Visi_MK1 | proven |
| 10007 | MC1 cooling | Firmware visibility 0x18e (398) = python-luxtronik Visi 400 (unnamed there) – cooling visibility MK1 | proven |
| 10008 | MC2 heating | Firmware visibility 6 = Visi 8 ID_Visi_MK2 | proven |
| 10009 | MC2 cooling | Firmware visibility 399 = Visi 401 (unnamed) | proven |
| 10010 | MC3 heating | Firmware visibility 0xd1 (209) = Visi 211 ID_Visi_MK3 | proven |
| 10011 | MC3 cooling | Firmware visibility 400 = Visi 402 (unnamed) | proven |

Proven in `FUN_000db9b0` (vtable slot 4 of the SmartHomeInterface). `device_config::config` (bit mask `FUN_00063f98`): bit 1 heating, 2 DHW, 4 (cooling bit, used in `FUN_000e4990`). 10000/10001 are **0 when the operating mode of the function is "off" (Ba_*_akt == 4)** – so they report equipment AND not "off". Corresponds to `registers.py` `CAPABILITIES` (where 10004 has no assignment → **solar**).

---

## 3. Semantics of the write registers

### 3.1 Heating (10000–10003), mixing circuits (10010–10037), overall (10065–10067) – proven

Return setpoint of the heating circuit: `FUN_00205d68` (writes `Sollwert_TRL_HZ`). Order of the checks:
1. Cooling operation/cooling release → setpoint = 50 (5.0 °C) or cooling logic.
2. Parallel-operation slave, forced heating (`Signal_zheiz` → 750), heat-up programme → fixed values; SHI has no effect.
3. **Heating "off"** (`Ba_Hz_akt == 4`), heating limit active **or block 10050 (t2/0x1e) other than 0** → setpoint = minimum (parameter 979 "Min. Rückl.Solltemp."), SHI setpoint/offset are not evaluated.
4. Otherwise `FUN_00205b60` supplies the heating-curve value; then the SHI selection `FUN_002056d8`:
   * only if parameter **t1/0x489 "Enable SHI" ≠ 0** (menu setting; python-luxtronik does not know index 1161);
   * **overall mode 10065 (t2/0x20) takes precedence**: if it is other than 0, the single mode 10000 is ignored. Overall 2 → offset 10066; overall 3 → level 10067 with the parameters "Hz. allg." (decrease t1/0x4a3, increase t1/0x4a4). Overall mode 1 (setpoint) is **not** implemented and acts like 0.
   * Overall = 0 → single mode 10000: 1 → setpoint = 10001 directly (heating curve replaced); 2 → setpoint = heating curve + 10002; 3 → setpoint = heating curve + parameter (level 1 or 2: "Erhöhung Heizen" t1/0x4a6; level 3: "Absenkung Heizen" t1/0x4a5; level 0: offset 0).
   * PV/multi-buffer special case (`FUN_00205140`): during PV surplus operation the offset/level path is replaced by `FUN_0020524c` (PV target temperature); the setpoint mode (1) stays effective.
5. Limitation by `FUN_00453a8c` to the minimum (parameter 979) and the maximum (`Einst_TRBegr_akt`). The SHI can therefore **not** exceed the return limit.
6. "Heating demand border" (t0/0x57 → 10107) = `FUN_00205374`: mode 1 → min(previous border, SHI setpoint) is tracked; mode 2/3 → a negative offset is remembered; minus `Einst_HRHyst_akt` when the compressor is not in heating operation.

Level parameters (table `DAT_007e3ef0`, registered in `FUN_0008a990`, range −200..+200 in 0.1 K, step 5, format "%+.01f K"; menu "Offsets" `FUN_00314f30`): Hz. allg. 0x4a3/0x4a4, heating 0x4a5/0x4a6, MC1 0x4a7/0x4a8, MC2 0x4a9/0x4aa, MC3 0x4ab/0x4ac, DHW 0x4ad/0x4ae (each decrease/increase). The user sets these parameters on the device; the level only chooses between them. The values are not yet named in python-luxtronik `parameters.py` (indices 1187–1198).

Mixing circuits: `FUN_002084d0` (MC flow setpoint) → `FUN_00207eb4`, identical logic with the t2 IDs from the MC object (+0x48 mode, +0x50 setpoint, +0x4c offset, +0x60 level, +0x64/+0x68 level parameters). The overall mode applies here as well. The result is limited to MC min/max (parameters 1072–1077), finally + `Einst_WK_akt`. Cooling registers 10015–10017 etc.: limits 50..250 (5–25 °C) and −50..50 proven; consumer not followed individually (**likely** analogous).

### 3.2 DHW (10005–10008, 10051, 10071) – proven

* `FUN_00206d2c` selects analogously (only with "Enable SHI"; **no** overall influence): mode 1 → setpoint = 10006; 2 → setpoint = normal DHW setpoint + 10007; 3 → + parameter 0x4ae (level 1/2, increase) or 0x4ad (level 3, decrease).
* `FUN_00206f7c` supplies `dhw::desiredSetpoint` (= `FUN_0020702c`: `DHW_DesiredTemperature` = thermostat/time-programme value, if applicable SmartWW/EBV, + parameter 0x462 in operating state 3/4) **replaced by the SHI setpoint** (mode 1) or **plus offset** (2/3).
* `FUN_00203668` (DHW control): `RBE_Warmwasser_Soll_extra` (extra DHW/RBE), thermal disinfection (`Signal_TDI`), `Signal_BWS` and reheating take precedence. Otherwise `controlSetpoint = desiredSetpoint`, if applicable limited to `DHW_CoverageOfHeatPump` (coverage limit of the heat pump) and always to `Einst_BW_max` (10123). The SHI setpoint is therefore an upper limit **below** `Einst_BW_max`, not above it.
* **Block 10051 (t2/0x1f)**: `FUN_002f9c0c` reports "DHW blocked" if 10051 ≠ 0 or Ba_Bw == 4 or holiday (SuBw_akt == 1) → demand block; the operating mode (Ba_Bw_akt, parameter 4) is not changed. `FUN_0010e45c` additionally binds 10051 into the demand object of the DHW preparation.
* **Pending map** (`FUN_00087700`): writes to exactly t2 5, 6, 7, 0x27 (10005–10008) are stored with a counter of 10 (`FUN_0008747c`, `'\n'` = 10) and committed by the 1 Hz tick `FUN_0008798c` after 10 ticks through `set` with the deferred flag (1) → about 10 s delay until read-back. Writing the currently stored value deletes the pending entry (`FUN_0008747c`, the branch in which the new and the stored value are equal).
* **Extra DHW 10071 (t2/1)**: write callback `FUN_00089328`: ≠ 0 → the timer `ExtraDHW::timer` is set to parameter 1147 (duration, s); 0 → timer 0. `FUN_00081c1c` (tick): while the timer runs, `RBE_Warmwasser_Soll_extra` has the larger of the old RBE setpoint and parameter 1146, limited to [`DHW_DesiredTemperature`, `Einst_BW_max`]; **when it has expired the firmware sets t2/1 to 0 itself** (through `FUN_004270bc`). 10502 shows the remaining time (min).

### 3.3 Other write registers – proven

* **10040/10041 LPC** (`limitation_power_consumption`): `FUN_002fa0b0` supplies the mode only if "Enable SHI" ≠ 0; 2 = hard limit; 1 = soft limit only if the additional condition `FUN_002fa1ec` (state object `DAT_00a19128`) is met, otherwise 0. The limit value `FUN_002fa044` multiplies 10041 by 100 → W (wire 0.1 kW, range 0..300, default 300 = 30 kW). Display "Max Power Consumption Limit - SHI" (text 0x7e3254) in the service menu.
* **10052 cooling block** (t2/0x1c): `FUN_001a3a84`, `FUN_001ed6f8` (== 1 → cooling passive/active blocked). **10053 pool block** (t2/0x1d): `FUN_001ef980`.
* **10050 heating block**: see 3.1 point 3; additionally `FUN_002f9c0c` (heating blocked or cooling release) into the LPC state object.
* **10070 circulation** (t2/0x28, visibility 8 = `ID_Visi_Zirkulation`): `FUN_00275f94` starts the ZIP logic (`DAT_00a17c7c`), run times from `Einst_Zirk_Ein/Aus_akt` × 60; if the bit is set but no run is active any more, **the firmware sets 10070 to 0** (through `FUN_00427538`). Blocked when Ba_Bw ∈ {3,4}.
* **10060 room setpoint** (`RBE_RoomTemperatureSetpointRegister`, `FUN_000dd478`): binds **t1/0x47c = parameter 1148 `RBE_Raumtemperatur_Soll` directly** (UINT16, 0.1 °C). Writing sets the parameter with source SHI; `avail()` (`FUN_000dfce4`) = visibility (0x176) ∧ `FUN_000e3c34`: RBE present, connected **and `RBE_Einflussfaktor_RT_akt` > 0**. Limits: no Range object in the SHI register itself, but the parameter carries its own bounds (registration path `FUN_000889e4` in `FUN_00099a78`, format "%.01f°C"); concrete min/max are not visible as numbers in the dump → **open**. As it is a t1 parameter, it is reset to the **persisted value** when the watchdog expires (type 1 in `FUN_000881e0`).
* **t2/0 "Schnellladung"** (quick charge; text 4, `FUN_0009bab4`): internal SHI item set by `FUN_00216a3c`/`FUN_0031f6f0`/`FUN_0031fb78` (DHW quick charge from the control unit); **no SHI register binds t2/0** → not reachable over Modbus.

### 3.4 Boot defaults and reset values (proven, `FUN_00087e9c`)

| t2 ID | Register | Default |
|---|---|---|
| 3 | 10001 | 350 (35.0 °C) |
| 6 | 10006 | 400 (40.0 °C) |
| 9, 0xf, 0x15 | 10011, 10021, 10031 | 350 |
| 0xc, 0x12, 0x18 | 10016, 10026, 10036 | 200 (20.0 °C) |
| 0x1b | 10041 | 300 (30.0 kW) |
| all others | modes, offsets, levels, blocks, switches | 0 |

---

## 4. Watchdog, restart, error cases

* `SmartHomeInterface::Monitor` (object at SHI+0x908, constructor `FUN_000dfd50`), tick `FUN_000dff50` (1 Hz, tick list `0x00a2128c`): counter 0…600; on reaching **600 s** → `FUN_00186170`: event-log entry (type 0x10, flag 1) and `FUN_00186120` → `GDI::reloadIfSetBy(source SHI)`.
* Re-arm `FUN_000de744` at the start of **every** dispatcher call (read and write, FC 2/3/4/6/16): counter = 0; if the counter was ≥ 600 (expired), an event-log entry "SHI back" (type 0x10, flag 0) is written. A polling client therefore keeps the watchdog armed permanently.
* `GDI::reloadIfSetBy` (`FUN_000882f0`) iterates **t1 0..0x4af and t2 0..0x28** and calls `FUN_000881e0` for every item whose last source is SHI (6): type 1 (t1 parameter, e.g. 10060) → persisted value from `FUN_00244298`; type 2 (t2) → default from `FUN_00087e9c` (§3.4); new source 0xFFFFFFFF ("---" in the display).
* Restart: `FUN_0009da20` sets all t2 items 0..0x28 to their defaults (source 0). Same effect as a watchdog expiry.
* Read-back after expiry: modes/levels/blocks/switches = 0, setpoints = default (350/400/200/300), LPC limit = 300; never 0x7FFF (that appears only when the visibility is missing).
* Error 816 "Mehrere SHI Schreibquellen" (multiple SHI write sources; texts 0x8766d4/0x8766f0, index 0x6F): more than 2 distinct (source, client ID) pairs within 3600 s; myUplink counts as its own source. While active: all SHI writes have no effect, no exception. (Mechanism confirmed from earlier work, not examined further here.)
* Write outside the range → **revert to default** instead of acceptance (§1.4). For the integration this means: an out-of-range write is not just "lost", it erases the previous SHI value.

---

## 5. New findings compared with python-luxtronik and registers.py

1. **All GDI IDs are now assigned names** (variable, firmware text, visibility) – see CSV. python-luxtronik `inputs.py` is fully confirmed in addresses, types and signs; additions:
   * `unknown_input_113` = "TVL calc max" (calculated max. flow, 0.1 °C, INT16).
   * `unknown_input_350..356/360/361` = `VBOout, FP1out, FP2out, FP3out, HUPout, BUPout, ZIPout, EVUin, EVU2in` (confirmed).
   * `unknown_input_404..417` = operating hours heat pump/heating/DHW/**cooling**/**pool (divisor 7200!)**/**solar**, UINT32.
   * `unknown_input_500/501/502` = extra DHW target (0.1 °C), duration (min), remaining time (min).
   * `unknown_holding_60` = **writable** RBE room setpoint (parameter 1148), 0.1 °C, available only with RBE + influence factor > 0.
   * `heating_limit`(10107)/`dhw_limit`(10124) are the dynamic demand borders (setpoint − hysteresis), not parameters.
   * `max_flow_temp`(10112) = "Vorlauf max." – confirmed.
2. **Overall mode 10065–10067** (previously without evidence, entities disabled): proven – overrides the heating-circuit **and** mixing-circuit modes, mode 1 (setpoint) has no effect there; offset −50..+50 (not −200..200 as with 10002!), level through the parameters "Hz. allg." 0x4a3/0x4a4.
3. **Level semantics** (`_LEVELS`): 0 normal, 1 increase, 2 increase (identical to 1), 3 decrease. The amounts are the device parameters 1187–1198 (menu "Offsets", ±20 K in 0.5 K steps). python-luxtronik's `LevelMode` ("Increased2") is not a separate value in the firmware.
4. **Limits from the firmware** (Range objects): 10001 150..750; 10002 −200..200; 10006 300..750; 10007 −200..200; 10011/21/31 200..650; 10012/22/32 −50..50; 10016/26/36 50..250; 10017/27/37 −50..50; 10041 0..300; 10066 −50..50; levels 0..3. Step is 1 everywhere (= 0.1 °C) – `registers.py` step 0.5 is a UI simplification, 0.1 steps would be permitted. **Deviation:** `registers.py` allows ±20 K for 10066, the firmware only ±5 K → values above that are reverted.
5. **Out-of-range write ⇒ revert to default** (not ignored). Read-after-write in the integration covers this, but the expectation "the old value stays" is wrong.
6. **Enable SHI** (parameter t1/0x489 = 1161, menu text "Enable SHI", options "ModBus TCP / myUplink / Both" at 0x7e3d8c): if it is 0, heating, DHW, MC and LPC ignore the SHI values – the registers stay readable/writable, though. Blocks (10050–10053), circulation and extra DHW do **not** check this parameter.
7. **Discrete inputs (FC 2)** 10000–10011 completely determined, including 10004 = solar; 10000/10001 = equipment ∧ operating mode ≠ off.
8. **Watchdog events** are logged in the device (event log type 0x10): expiry and return can be followed on the control unit.
9. **Circulation/extra DHW** are triggers: the firmware sets the bits to 0 itself after the end – a read-back of 0 is not an error.
10. **Not** reachable in the SHI although present as a t2 item: t2/0 "Schnellladung" (DHW quick charge of the control unit). No other hidden holdings: all 41 holding slots correspond to t2 1..0x28 plus 10060; no unused slots with content.
11. All 10 energy counters are MultiByte with sign: electrical UINT32, thermal INT32 (builder). Word order: **high word at the lower address** (`FUN_000d94b4` creates the first partial register with word index 1; getter `FUN_000dca24` shifts by index × 16 → word 1 = bits 31..16). A MultiByte partial register is also implemented as writable (`FUN_000dc904`, read-modify-write of the 32-bit value), but the inputs are only reachable through FC 4.

---

## 6. Open points

* 10412 divisor 7200: intention unclear (the firmware display computes 1/3600). Not measurable without a pool on the reference installation → **likely** a factor 2 is needed, stays a raw value.
* 10060 min/max: not visible as numbers in the dump (Range object of parameter 1148 not located) → **open**; measured plausible values 20–40 °C remain an owner decision.
* LPC "soft limit" condition `FUN_002fa1ec` not examined in depth (state object `DAT_00a19128`).
* Cooling registers 10015–10017 (and MC2/3): consumer not decompiled individually; limits/visibility proven, effect analogous to heating **likely**.
* Bit assignment of input 10000 from python-luxtronik, function `heating_control::getHeatGeneratorStatus` not decompiled → **likely**.
* Live cross-check through Home Assistant: the raw values 10410/10412/10416/10500–10502 are not enabled as entities on the reference installation (only `sensor.warmepumpe_diagnose_rohwert_10109…10361` exist), so no comparison was possible. The enabled values (10113 = 25.7 °C with return setpoint 20.0; 10351/10354 = 1, 10355 = 0, 10360 = 1) fit the interpretations.
* Error 816 (reset condition) and the behaviour "DHW mode cannot be set while the block is active" were not part of this analysis.

---

## 7. Method (reproducible)

1. Unpack the firmware: `scripts/extract_fw.py` (gzip from offset 4039, zlib `decompressobj(31)`, outer tar, inner tar `home.wp2reg-V3.92.3_…`; `bin/Controller` complete, 10 498 803 bytes).
2. Ghidra 11.4.2 headless, `-processor ARM:LE:32:v7 -max-cpu 1`, MAXMEM 4G: import + analysis 382 s. Project "SHI/Controller".
3. `scripts/parse_builder.py` (Capstone, symbolic mini-emulation of the −O0 builders `FUN_000d8014`/`FUN_000d95d4`): delivers class, {t,id}, sign, divisor, fixed value, slot/address per register.
4. `scripts/DumpDecomp.java` (Ghidra post-script): decompiles function lists into `dec/fn_<addr>.c`, xrefs `x:<addr>` → `dec/xref_<addr>.txt`. Lists used in `ref/list*.txt`.
5. `scripts/gdi_map.py`: parses all decompilations of the callers of the handle constructors (137 functions) → `ref/gdi_map.tsv` (t/ID → symbol, visibility, text ID, format, limits).
6. `scripts/texts.py`: text table (.data 0x9ce58c, 24 languages) → `ref/texts.tsv`.
7. `scripts/build_csv.py` + `scripts/build_report.py`: CSV and this report.
8. Cross-reference with python-luxtronik (Bouni/python-luxtronik, `definitions/{inputs,holdings,parameters,visibilities}.py`, parsed as text with `scripts/pl_table.py`) and `registers.py` of the integration.

Note on section 7: the script names (`scripts/…`, `ref/…`, `dec/…`) refer to the local working area of the analysis and are not part of this repository.
