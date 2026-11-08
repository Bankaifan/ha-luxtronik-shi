# Firmware analysis — Luxtronik SHI, V3.92.3 (independent verification)

This document records an **independent decompilation** of the Luxtronik controller firmware
**V3.92.3** (`wp2reg-V3.92.3_260513_3a381baa`, binary `bin/Controller`, ARM 32-bit, stripped) of the
reference installation (alpha innotec **LWDV 91-1/3**). It serves as a **source** in the sense of the
"no invented register facts" rule: it confirms the register map in `custom_components/luxtronik_shi/registers.py`
against the firmware itself and lists the points that are still open.

Only facts are recorded here (addresses, data types, scaling, effect, code locations). No firmware code is
reproduced. The analysis was done for interoperability of this independent program (§ 69e UrhG). Code
locations are given as function addresses (`0x…`) in the binary so the findings are reproducible.

> **Update 2026-11-08:** the [full analysis of V3.92.3](firmware-3.92.3-shi-full-analysis.md) (German:
> [firmware-3.92.3-shi-full-analysis.de.md](firmware-3.92.3-shi-full-analysis.de.md); register table as
> [CSV](firmware-3.92.3-registers.csv)) extends this note: all holding and input registers, value ranges, boot
> defaults, discrete inputs and the write path. Statements below stay valid; where the full analysis refines or
> answers one, a short *Update* line says so.

## How the SHI works (verified)

The `SmartHomeInterface` constructor `0x000dc298` sets the Modbus base offset **10000**
(`FUN_000d5b00(this, 10000, 10000)`) and builds two pointer arrays of register objects:

- **Holdings** (writable, FC 3/6/16): builder `0x000d8014`, array at object offset **+8**, array index = `address − 10000`.
- **Inputs** (read-only, FC 4): builder `0x000d95d4`, array at object offset **+300**, read handler `0x000d9450` (length 503).

The generic dispatch `0x000d9298(start, count, buf, isRead, arrayBase, arrayLen)` resolves
`register = arrayBase[address − 10000]`. A `NULL` slot is an illegal address. Otherwise it calls the
register's *availability* method; if the register is not available it returns **`0x7FFF`** instead of a value
(so `0x7FFF` on a read means "not available", not a real measurement — worth handling as unknown).

The register constructor `0x000dd2e8(this, {datapoint-id, table}, arg4, arg5)`:

- binds the register to an internal controller datapoint (GDI) via one of three runtime tables
  (resolver `0x0042bf8c`); the plaintext names of those datapoints are **not** in the static image (the tables
  are populated at runtime), so a target is referenced here as a GDI handle `t<table>/0x<id>`.
- **`arg4` = sign** of the value — `0` → `int16`, `1` → `uint16` (write wrapper `0x000dc76c`).
- **`arg5` = scale divisor applied on read** — the value placed on the wire is `round(raw / arg5)` if
  `arg5 ≥ 2`, else the raw value (getter `0x000dfbb4`).

Consequence for this integration: **the Modbus wire value is already the engineering value**. The firmware
divisor turns the internal unit into the value the client reads, so the integration's own `scale` (e.g. `0.1`
for temperatures, `1.0` for the hour counters) is applied on top of an already-normalised wire value. This
matches the current `registers.py`.

Special register classes:

- **`Fixed`** (`0x000dc81c`): returns a **constant**, not a live value.
- **`RBE_RoomTemperatureSetpointRegister`** (`0x000dd478`): room-temperature setpoint register, target
  `RBE_RT_Soll`, **writable** — see open questions.
- **`MultiByte`** (`0x000d94b4`): a 32-bit value spread over **two consecutive registers** (energy and hour
  counters).

## Confirmed against `registers.py`

Verified directly from the constructor arguments, no deviation from the current map:

- **Signs / data types** of all `Bound` registers match (`int16`/`uint16` per `arg4`).
- **Writability**: all holdings are writable, all inputs are read-only (one exception, 10060, below).
- **Scaling model** as above — the temperature `×0.1`, the `uint32` energy counters (10310–10328, two
  registers each) and the operating-hour counters (`hours_hp` 10404, `hours_heating` 10406, `hours_dhw` 10408,
  `uint32`, already in hours on the wire) are consistent.
- **Operating mode** (`operating_mode`, input 10002): the eight values of `_OPERATING_MODES` match the standard
  Luxtronik operating-mode set.
- **Fixed constants** (informational — the firmware returns a constant, not a measurement):
  `10122` = `300` (30.0 °C, DHW minimum; confirmed live: `30.0`), `10203`/`10204` = `20` (minutes),
  firmware version registers `10400`/`10401`/`10402` = `3`/`92`/`3` → **V3.92.3**.

## SHI watchdog

Recorded from the reverse engineering of 2026-11-07 (function addresses only, no code):

- `SmartHomeInterface::Monitor` is a `Tick_t` task that runs **once per second**. Evidence: the hwclock counter
  86400 in `FUN_0047e7d4`.
- Its counter counts to **600**, i.e. **10 minutes** (tick at `0x000dff50`).
- The re-arm at `0x000de744` is called at the start of the SHI dispatcher `FUN_000d9298`, so **every Modbus access
  resets the counter, a pure read included**. While an integration polls, the watchdog does not expire.
- On expiry, `0x00186120` calls `GDI::reloadIfSetBy` (`0x000882f0`) for the SHI source, which **discards every value
  last set over the SHI**; the holding registers then read their reset value.
- **Reboots have the same effect.** The Home Assistant history of the reference installation shows the reset on
  2026-11-05 19:15 and 2026-11-06 13:16. At those times the separate port-8889 integration dropped as well, so these
  were controller reboots, not watchdog expiries. Measured after them: heating mode (10000) read raw 0 instead of 1,
  and on 2026-11-05 heating level (10003) read raw 0 instead of 2.
- **What the revert restores** (`reloadIfSetBy` walks the items of t1 and t2 and calls the revert function
  `0x000881e0` for each item last set by the SHI source): either the **persisted parameter value** (type 1,
  `0x00244298`) or the **fixed default** (type 2, `FUN_00087e9c`), written back with source `0xFFFFFFFF`, so the web
  UI shows "---" again. Result: **modes, levels and blocks read 0; setpoints read their persisted value or their
  default, not 0.**
- **Boot defaults.** At boot, `FUN_0009da20` sets every t2 item (0..0x28) to its default from `FUN_00087e9c` with
  source 0. Setpoints have real defaults (examples seen: 350, 400, 300, 200); levels (ids 0x22–0x27), modes and blocks
  default to 0.
- **A holding that was never set reads its boot default, not `0x7FFF`.** The dispatcher `0x000d9298` returns
  `0x7FFF` only when the register's availability check (`0x000dfc98` → `0x003d9e0c`) fails, which depends on the
  configuration (for example absent equipment), not on who set the value. 10003 reads 0 when never set, matching the
  device.
- **Open:** the exact default of each individual setpoint register, and whether a given setpoint reverts to a
  persisted parameter (type 1) or a fixed default (type 2).
  *Update 2026-11-08:* answered by the full analysis (§3.4 and §4): every t2 setpoint reverts to a fixed default
  (10001 = 350, 10006 = 400, 10011/10021/10031 = 350, 10016/10026/10036 = 200, 10041 = 300; modes, offsets, levels,
  blocks and switches = 0), the t1 parameter 10060 to its persisted value.

The integration uses these facts for the optional *restore after a device reset*: `SHI_WATCHDOG_TIMEOUT` in
`const.py` is the 600 s above.

## Deferred writes of the hot water group

From the analysis of 2026-11-07 (function addresses only, no code):

- SHI writes to the hot water group, the t2 items behind **10005/10006/10007/10008** (mode, setpoint, offset,
  level), do not take effect at once. They go into a **pending map** (`0x00087700` → `0x00087608` → `0x0008747c`;
  ticker `DAT_00a0c6a8`, tick `0x0008798c`) and are committed after about **10 ticks** of the 1 Hz SHI tick list.
  The delay is *inferred* from the shared tick list `0x00a2128c`: about **10 s**. Heating mode and offset do not go
  through this path.
- **A write of the value currently stored cancels a pending write for that item.**
- **Live data (reference installation, 2026-11-07, after a controller reboot at about 16:37):** a write of hot water
  mode = setpoint at about 16:38:57 read back `off` (0) at once and showed `setpoint` with the next poll at 16:39:14,
  which agrees for **10005**. A write of hot water setpoint 54 at 16:38:37 read back 54 at once: for **10006 the
  firmware claim and the measurement disagree**; nothing is built on it.
- **Owner measurement, mechanism unknown:** the hot water mode can only be set while the hot water block (10051) is
  not active. On that day the restore after the reboot reported that it could not restore the hot water mode and
  setpoint, and the hot water mode later read `off` again after the block was switched on and off.

- **The blocks are not deferred (inferred, not measured live).** The pending-map entry `0x00087700` builds a list of
  exactly four items, the t2 ids of 10005, 10006, 10007 and 10008, and routes a write into the pending map only for
  those. 10050 and 10051 are t2 ids 0x1e and 0x1f and are not in that list, so their read-back is expected at
  once. This comes from the decompilation; the table field of the item handle was not verified separately, and no
  live measurement of a lag on the blocks exists. The block select and switch therefore read back at once and raise
  an error if the value differs.

The integration checks a differing read-back of these four registers again after 15 s (`DEFERRED_RECHECK`), writes
nothing to the register meanwhile, and lets restores of this group wait while the hot water block reads on.

## Error 816 "Multiple SHI write sources"

From the analysis of 2026-11-07 (bin/Controller V3.92.3; grades as in the source notes: *proven* = read from code or
data, *inferred* = reasoned).

- The error table has an entry with number 816 (internal index 0x6F, entry at `0x009dbff0`, priority 1) with the
  texts "Mehrere SHI Schreibquellen" (German) and "Multiple SHI write sources" (English). The number and the texts
  are each *proven*; that these texts belong to 816 is *inferred* (strong).
- Trigger (*proven*): on every SHI write, `write_log::update` (`0x00187314`) updates a per-datapoint log of
  writers; with more than 2 entries (at least 3 distinct writers) it raises error index 0x6F. A writer is a distinct
  pair (source, client-id). Each Modbus client IP counts separately (the client-id is a CRC32 over the peer address,
  the port is not part of it); myUplink counts as one writer. Entries older than 3600 s are pruned.
- Effect (*proven*): while the error is active, `update` returns 0 and the Modbus write task stores nothing. The
  write is **not reported as an error**: the value simply does not change. The integration's read-back check is how
  such a dropped write becomes visible.
- Input 10201 shows the number of the active top-priority error (mechanism *proven*); that 816 is the number shown
  is *inferred*.
- Clearing: no caller of the clear function (`0x001e8c64`) was found; the error is probably held until it is reset
  (*inferred / unknown*).

## Open questions / proposed follow-ups

1. **Level option order (`_LEVELS`)** – *resolved in 0.9.0 (#44).* The firmware proves the level feature has one
   *increase* and one *decrease* direction (strings `Increase`, `Decrease`, `Absenkung`), but the exact value→meaning
   table is not in the static image. `_LEVELS` now follows `python-luxtronik` `LevelMode`
   (`0 Normal, 1 Increased, 2 Increased2, 3 Decreased`); the effect of the non-normal levels is still open there
   and here.
   *Update 2026-11-08:* the full analysis (§3.1, §5 item 3) reads the effect from the code: levels 1 and 2 use the same
   *increase* parameter, level 3 the *decrease* parameter, level 0 adds nothing; "Increased2" is not a separate value
   in the firmware.
2. **10060 is a writable room-temperature setpoint**, not an unknown read-only value. The firmware instantiates
   it as `RBE_RoomTemperatureSetpointRegister` (`0x000dd478`, target `RBE_RT_Soll`), `uint16`, °C/10, in the
   *holdings* (writable) array. It is currently exposed as `raw_10060` (read-only). Promoting it to a real
   writable setpoint needs a value range (not derivable from the static image → a measurement on the device)
   and a contract migration — owner decision.
   *Update 2026-11-08:* the full analysis (§3.3, §6) adds the availability condition (RBE present, connected, influence
   factor greater than 0); the value range stays open.
3. **Raw hour/time counters.** `10410`/`10416` are further `uint32` operating-hour counters (divisor 3600),
   `10500`/`10501`/`10502` are time values (`10501`/`10502` divisor 60, seconds→minutes). These are currently
   `raw_*`; they could become named sensors once their exact meaning is confirmed.
4. **10412 has an unusual divisor 7200** (not 3600) — a `uint32` counter whose unit is unclear (possibly
   2-hour units or an average). Keep as raw until confirmed.
   *Update 2026-11-08:* the full analysis (§2.2, §6) identifies the counter as the pool operating hours and reads
   the divisor 7200 as a deviation of the SHI code (the firmware display uses 3600), so the wire value is likely
   hours/2; not measurable without a pool.

## Reproduction

Ghidra 11.4.2 headless analysis of `bin/Controller`; the register map was parsed from the two builder
functions and cross-checked against `python-luxtronik` (`inputs.py`/`holdings.py`) and a read-only live sample
on the reference installation via Home Assistant.
