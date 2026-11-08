# Register meanings: firmware analysis and measurement (FW 3.92.3)

Sources: (1) independent decompilation of `bin/Controller` of Luxtronik V3.92.3, done for interoperability of this
independent program; only facts and function addresses are recorded, no code is reproduced; (2) read-only
measurements on the reference installation (alpha innotec LWDV 91-1/3): the disabled `raw_<address>` sensors
(polled every 2 minutes) compared with the pump and compressor outputs of the native Luxtronik integration
(port 8889), 2026-11-06 19:40 to 2026-11-07 17:20, about 25 transitions per register. Nothing was written.
Grades: **proven** = read directly from the firmware, **inferred** = reasoned (reasoning given), **unknown**.

> **Update 2026-11-08:** the [full analysis of V3.92.3](firmware-3.92.3-shi-full-analysis.md) (German:
> [firmware-3.92.3-shi-full-analysis.de.md](firmware-3.92.3-shi-full-analysis.de.md); register table as
> [CSV](firmware-3.92.3-registers.csv)) names every SHI register. It uses the grades proven / likely / open. Where it
> refines a statement of this note, an *Update* line says so; no statement was removed.

## How the firmware names a SHI input (proven)

Each SHI input is bound to an item `t<table>/0x<id>` of the controller's datapoint table (see
`firmware-3.92.3-shi-analysis.md`). Two registration functions list the items together with the name of the
controller variable that feeds them: `0x0008bef8` (outputs), `0x0009833c` (inputs) and `0x0008a058` (counters).
The variable names are exported symbols of the binary and match the `ID_WEB_*` names of python-luxtronik
(`HUPout` is `ID_WEB_HUPout`). So the name of the variable behind an item is a firmware fact.

## Results

| Register | Item | Firmware variable | Meaning | Unit / scale | Grade |
|----------|------|-------------------|---------|--------------|-------|
| 10113 | t0/0x67 | `Sollwert_TRL_HZ` + `MovingAverage::spread` (assignment at `0x0019ac68`; the item is tagged `supplyTemp` in the myUplink binding `0x000ff110`) | calculated heating flow target = return target + moving average of the flow-minus-return spread | 0.1 degC, int16, divisor 1 | proven (formula); unit inferred (return target 10101 is 0.1 degC, live 200 = 20.0); measured: raw 253 with return target 20.0 and an average spread of 5.3 K |
| 10350 | t0/0x45 | `VBOout` | digital output VBO (0/1) | none | proven; measurement: coincides with the compressor runs |
| 10351 | t0/0x6d | `FP1out` | digital output FP1 (0/1) | none | proven; measurement: follows the heating circulation pump |
| 10352 | t0/0x4c | `FP2out` | digital output FP2 (0/1) | none | proven; not measured (no second circuit) |
| 10353 | t0/0x4d | `FP3out` | digital output FP3 (0/1) | none | proven; not measured (no third circuit) |
| 10354 | t0/0x20 | `HUPout` | heating circulation pump (0/1) | none | proven; measured (identical to 10351 on this plant) |
| 10355 | t0/0x44 | `BUPout` | DHW pump BUP (0/1) | none | proven; measured |
| 10356 | t0/0x48 | `ZIPout` | circulation pump ZIP (0/1) | none | proven; measured (2-minute pulses) |
| 10360 | t0/0x2a | `EVUin` | digital input EVU (utility lock) (0/1) | none | proven name; measured: constant 1 while the native `evu_unlocked` is on, so 1 = released (inferred from that single state) |
| 10361 | t0/0x2b | `EVU2in` | digital input EVU 2 (0/1) | none | proven name; measured: constant 0, native `evu2` off |

*Update 2026-11-08 (10113):* the full analysis reads the firmware text of item t0/0x67 as "TVL calc max" (calculated
maximum flow) and says the earlier reading "flow target heating (calculated)" is to be replaced by that text. It names
the same function `0x0019ac68` as the formula above and its live values (25.7 degC with return target 20.0) fit as
well. No measurement decides between "setpoint" and "upper limit", so both readings are kept here.

*Update 2026-11-08 (VBO):* the firmware text of 10350 reads "Ventil.-BOSUP / VBO"; the long form of FP is still not
stated.

The long forms of the abbreviations VBO and FP are not given by the firmware; only HUP, BUP, ZIP (heating,
DHW and circulation pump by the Luxtronik naming convention) are expanded in the display names, inferred.
The correction against the first version of this note: 10350 is `VBOout`, not the additional circulation pump
`ZUPout` (that is t0/0x21, which the SHI does not expose).

### Counters and other raw values that are not on the reference installation's entity list (proven names)

| Register | Item | Firmware variable | Meaning | Divisor | Grade |
|----------|------|-------------------|---------|---------|-------|
| 10404 (u32) | t1/0x29c | `Zaehler_BetrZeitWP` | operating hours heat pump | 3600 s | proven |
| 10406 (u32) | t1/0x2d8 | `Zaehler_BetrZeitHz` | operating hours heating | 3600 s | proven |
| 10408 (u32) | t1/0x2d9 | `Zaehler_BetrZeitBW` | operating hours DHW | 3600 s | proven |
| 10410 (u32) | t1/0x2da | `Zaehler_BetrZeitKue` | operating hours cooling | 3600 s | proven |
| 10412 (u32) | t1/0x35b | `Zaehler_BetrZeitSW` | operating hours counter "SW" (the name suggests the pool) | 7200 s | name proven; meaning of "SW" and of the divisor 7200 inferred |
| 10416 (u32) | t1/0x372 | `BSTD_Solar` | operating hours solar | 3600 s | proven |
| 10502 | t0/0x3a | `ExtraDHW::timer` | timer of the extra hot water function | 60 (seconds to minutes) | proven |

*Update 2026-11-08 (10412):* "SW" is the pool (firmware text "Schwimmbad", visibility `ID_Visi_Bst_BStdSW`). The full
analysis reads the divisor 7200 as a deviation of the SHI code (the firmware display uses 3600), so the wire value is
likely hours/2; not measurable without a pool. The "possibly 2-hour units" guess is superseded by this.

These are not promoted in `registers.py`: `raw_10411`, `raw_10413` and `raw_10417` exist as separate 16 bit
entities (the low words of the 32 bit counters), the keys must not change, and no measurement of them exists.

### 0x7FFF

The SHI dispatcher `0x000d9298` answers `0x7FFF` exactly when the register's `avail()` is 0 (proven). `avail()`
depends on the configuration of the controller (equipment that is not installed). On the reference installation
no enabled raw value reads 0x7FFF; they all return values. Which equipment makes each individual register
unavailable is not decoded (unknown). For FP2out/FP3out (10352/10353) "no second/third circuit" is the likely
reason (inferred); no data exists to check it.

## Buffer tank type (input 10202)

python-luxtronik (`inputs.py` index 202, `BufferType`): 0 series, 1 separation, 2 multi-function buffer. The
integration used the tuple `("unknown", "series", "separation", "multi")` with the raw value as index, so every
value was shifted by one: the reference installation (configured as a separation buffer, raw 1) showed "series".
The tuple is now `("series", "separation", "multi")`. Grade: proven (library definition plus the owner's
configuration matching raw 1).

## Open

* 10404 to 10417 and 10500 to 10502 are not renamed (see above).
* 10351 against 10354: the firmware separates them (FP1out against HUPout); on this plant they switch together.
* What `VBO` and `FP` stand for is not stated by the firmware.
