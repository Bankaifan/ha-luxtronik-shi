# Register meanings measured on the reference installation (FW 3.92.3)

Method: the raw values of the reference installation (alpha innotec LWDV 91-1/3, firmware 3.92.3) were read
through Home Assistant (history of the disabled-by-default `raw_<address>` sensors, polled every 2 minutes) and
compared with the outputs the native Luxtronik integration (port 8889) reports for the same plant (binary
sensors for pumps, compressor, defrost valve). Read-only; nothing was written. Window: 2026-11-06 19:40 to
2026-11-07 17:20, about 25 transitions per register. Grade: *derived* = the transitions coincide within one poll
interval, but no vendor source confirms the meaning. Nothing here is a vendor fact, so no register is promoted
from `raw_<address>` (rule 3); the findings are shown as `derived:` in `docs/registers.md`.

| Register | Observation | Meaning | Grade |
|----------|-------------|---------|-------|
| 10351 | 0/1. Rises and falls with `circulation_pump_heating` on 2026-11-07 at 00:56, 01:26/01:31, 02:01/02:06, 02:36/02:41, 03:11 and 09:01/09:06 (lag at most one poll). | heating circulation pump output | derived |
| 10354 | Identical to 10351 in every observed transition. | same signal as 10351 (the two cannot be told apart) | derived |
| 10350 | 0/1. 1 during `additional_circulation_pump` runs of 09:26-10:15, 10:47-11:27, 13:19-14:45, 16:30-16:36 and 16:42-17:00. The compressor runs almost exactly in the same windows. | additional circulation pump, or compressor running; not separable | derived (ambiguous) |
| 10355 | 0 all night, 1 only while `dhw_recirculation_pump` is on (16:30-16:32, 16:41-16:43, 16:45-17:00, 17:15-). | DHW recirculation pump output | derived |
| 10356 | 1 in 2-minute pulses that coincide with `dhw_charging_pump` (11:35-11:37, 13:50-13:52, 15:13-15:15, 16:27-16:29, also at night 01:11-01:13). | DHW charging pump output | derived |
| 10113 | int16, 248 to 418 (no unit known). 250-266 with the compressor off, mostly 320-350 while it runs, short dips to 248/250 during a run. No match with flow, return, mixing circuit flow, external return, hot gas, high pressure, overheating, compressor frequency or heat output. | unknown | open |
| 10360 / 10361 | Constant 1 and 0 over the whole window. | unknown (not asked) | open |

Firmware side (`docs/firmware-3.92.3-shi-analysis.md`): these registers are `Bound` to controller datapoints
`t0/0x67` (10113), `t0/0x45` (10350), `t0/0x6d` (10351), `t0/0x20` (10354), `t0/0x44` (10355) and `t0/0x48`
(10356), unsigned 16 bit, divisor 1. The datapoint names are not in the static image, so the firmware gives no
name for them.

## Buffer tank type (input 10202)

python-luxtronik (`inputs.py` index 202, `BufferType`): 0 series buffer, 1 separation buffer, 2 multi-function
buffer. The integration used the tuple `("unknown", "series", "separation", "multi")` with the raw value as index,
so every value was shifted by one: the reference installation (configured as a separation buffer, raw 1) showed
"series". The tuple is now `("series", "separation", "multi")`; other raw values have no state. Grade: *proven*
(vendor-independent library definition plus the owner's configuration matching raw 1).

## Open

* 10113: needs a longer capture with a second reading (for example the native integration's parameter list or a
  menu screenshot at known values).
* 10350: a moment with the compressor off and the additional circulation pump on, sampled in the same poll, would
  separate the two readings (the pump ran alone for about a minute at 13:06 and 16:20, shorter than the poll).
* 10351 against 10354: a state where the two differ.
