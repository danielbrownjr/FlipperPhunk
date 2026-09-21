# FlipperPhunk host-side serial test harness

A host-side Python tool that stress-tests the FlipperPhunk firmware's two
UART paths **directly at 3.3V TTL logic level**, using two USB-UART
adapters wired straight into the Flipper's GPIO header. It is a bench tool
for validating the firmware's relay/logger behavior before the Rev C.1 PCB
(RS-232 level shifting, DE-9 connectors) is available or attached.

**This is not part of the FlipperPhunk firmware or hardware design.** It
does not redesign hardware, does not add new firmware features, and does
not produce fabrication files. See the top-level project README and
`hardware/README.md` for the actual product.

## ⚠️ Safety: this is 3.3V TTL, not RS-232

The wiring in this document connects two USB-UART adapters **directly** to
the Flipper's 3.3V CMOS GPIO pins, bypassing the MAX3232-class level
shifter entirely. That is intentional for this test -- it isolates firmware
behavior from the level-shifter/PCB -- but it means:

- Only use USB-UART adapters that are **3.3V-logic capable** (many common
  adapters are 5V logic and will over-drive the Flipper's GPIO). Confirm
  your adapter's logic-level jumper/setting before connecting anything.
- **Never** connect a real RS-232 (bipolar, up to ±15V) signal to these
  pins. RS-232 voltage levels will damage the Flipper.
- **Never** wire the Flipper's own two UARTs directly into each other
  (e.g. looping USART TX into LPUART RX and vice versa) while the
  FlipperPhunk relay app is also running. The app already relays A→B and
  B→A itself; an external physical loop on top of that creates an
  uncontrolled recirculating-traffic loop (every byte gets re-relayed
  forever) with no rate limit. Always terminate each side in a real host
  process (this harness) that only sends deliberate, bounded test traffic.
- Tie the grounds of both USB-UART adapters to the Flipper's ground. Do not
  power the Flipper from both its own USB port and a USB-UART adapter's
  5V rail at the same time.

## Bench wiring

Two known-good 3.3V USB-UART adapters connect directly to the Flipper's
GPIO header (no level shifter, no DE-9, no Rev C.1 PCB in this test path):

| Side                    | USB-UART adapter | Flipper GPIO pin | Signal              |
| ------------------------ | ----------------- | ----------------- | -------------------- |
| A / HOST (`firmware`'s Side A, USART) | Adapter A TX | GPIO14 | USART RX (Flipper receives) |
| A / HOST | Adapter A RX | GPIO13 | USART TX (Flipper transmits) |
| B / INSTRUMENT (`firmware`'s Side B, LPUART) | Adapter B TX | GPIO16 | LPUART RX (Flipper receives) |
| B / INSTRUMENT | Adapter B RX | GPIO15 | LPUART TX (Flipper transmits) |
| both | adapter GND | GPIO8 or GPIO11 | common ground |

This matches the firmware's own side mapping in `firmware/flipperphunk.c`
(`SIDE_A_ID = FuriHalSerialIdUsart`, `SIDE_B_ID = FuriHalSerialIdLpuart`)
and the Rev C.1 net list in `hardware/README.md` (J1 pins 13-16), minus the
RS-232 level shifter and DE-9 connectors.

On the Flipper: launch the FlipperPhunk app, use Up/Down on the setup
screen to pick a baud rate, press OK to start the relay. The app's baud
rate is selected **on-device** -- this harness cannot set it remotely, so
the harness's `--baud` (or a `sweep` step) must match whatever the Flipper
is currently running.

## Requirements

- Python 3.9+
- [`pyserial`](https://pypi.org/project/pyserial/) >= 3.5

## Install

```
cd tools/serial_test
pip install -r requirements.txt
```

Or as an editable package (adds a `serial-test` command on your PATH):

```
cd tools/serial_test
pip install -e .
```

Everywhere below, `python -m serial_test.cli ...` and `serial-test ...` are
interchangeable; the examples use the module form since it needs no install
step.

## Quick start (no hardware required)

Validate the harness itself against an in-process simulated bridge:

```
cd tools/serial_test
python -m serial_test.cli self-test
```

This exercises pattern generation, comparison/framing logic, a bridge test,
a sustained transfer, and a latency measurement, all against a mock relay
-- **not** real serial hardware. See "Validation performed" below.

## Usage

List serial ports:

```
python -m serial_test.cli list-ports
```

Basic bidirectional payload verification (requirement: exact byte
equality, ordering, no duplication, no missing bytes) at the baud rate
currently selected on the Flipper:

```
python -m serial_test.cli bridge --port-a COM5 --port-b COM6 --baud 9600 \
    --patterns ascii zeros ones alt55aa incrementing random \
    --length 1024 --seed 1234 \
    --out-json results/bridge_9600.json --out-csv results/bridge_9600.csv
```

Baud-rate sweep across every firmware-supported rate. Because the Flipper's
baud is only settable on-device, this pauses between steps against real
hardware and asks you to change it and restart the relay (mock mode skips
the prompts):

```
python -m serial_test.cli sweep --port-a COM5 --port-b COM6 \
    --patterns ascii incrementing random --length 512 \
    --out-json results/sweep.json
```

Sustained one-way transfer, either by total size or by duration (exactly
one of `--size` / `--duration` is required):

```
# 1 MB, Side A -> Side B
python -m serial_test.cli sustained --port-a COM5 --port-b COM6 --baud 9600 \
    --direction a2b --pattern random --size 1000000 --out-json results/sustained_a2b.json

# 30-second soak, Side B -> Side A
python -m serial_test.cli sustained --port-a COM5 --port-b COM6 --baud 9600 \
    --direction b2a --pattern incrementing --duration 30 --out-json results/sustained_b2a.json
```

Simultaneous bidirectional sustained transfer:

```
python -m serial_test.cli sustained --port-a COM5 --port-b COM6 --baud 9600 \
    --direction bidirectional --pattern random --duration 20
```

Soak-test guardrail: durations over 300s or sizes over 50MB require
`--allow-long-soak` explicitly, e.g.:

```
python -m serial_test.cli sustained --port-a COM5 --port-b COM6 --baud 9600 \
    --direction bidirectional --pattern random --duration 1800 --allow-long-soak
```

Approximate forwarding-latency characterization (see "Latency measurement
limitations" below):

```
python -m serial_test.cli latency --port-a COM5 --port-b COM6 --baud 9600 \
    --direction A->B --samples 100 --out-json results/latency.json
```

Failure/recovery helpers:

```
# Guided: stream a heartbeat and log arrival gaps while you perform a
# failure action at the bench (app restart, bridge stop/restart, cable
# disconnect/reconnect, on-device pause). Correlate the reported gap
# windows with when you performed the action.
python -m serial_test.cli recover watch --port-a COM5 --port-b COM6 --baud 9600 \
    --direction A->B --duration 60 --out-json results/recover_watch.json

# Automated: host-side serial port close/reopen, verified end to end.
python -m serial_test.cli recover port-cycle --port-a COM5 --port-b COM6 --baud 9600
```

## Test patterns

| Name           | Description                              |
| -------------- | ----------------------------------------- |
| `ascii`        | Printable ASCII test string, tiled        |
| `zeros`        | Repeated `0x00` block                     |
| `ones`         | Repeated `0xFF` block                     |
| `alt55aa`      | Alternating `0x55`/`0xAA`                 |
| `incrementing` | Incrementing `0x00..0xFF` blocks          |
| `random`       | Seeded pseudorandom binary data           |

All patterns are pure functions of `(name, length, seed)` -- the same
arguments always produce byte-identical output, including when streamed in
arbitrary chunk sizes for sustained tests (see `tests/test_patterns.py`).

## Supported baud rates

`1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200` -- taken directly from
`kBaudRates[]` in `firmware/flipperphunk.c`, the firmware's own setup-screen
list. As of this firmware baseline the list matches this task's required
sweep exactly; if a future firmware revision changes `kBaudRates[]`,
`serial_test/baud.py` should be updated to match and any difference from
the original request documented here.

## Expected firmware behavior (for interpreting recovery-test results)

From `firmware/flipperphunk.c` and the project's Mem knowledge note:

- The relay is an **active bridge**, not a passive tap: firmware must
  receive on one UART and retransmit on the other. There is **no fail-safe
  bypass** -- if the app isn't running, or the relay is paused, or the
  Flipper loses power/crashes, A and B stop talking to each other entirely
  (fails closed, not open).
- Pause/resume is exposed only via the on-device OK button while the relay
  is running (`app->relay_paused`) -- there is no host-side / over-the-wire
  way to trigger it. `recover watch` can only *observe* the resulting gap,
  not trigger the pause itself.
- Baud rate is chosen on the setup screen before starting the relay and is
  fixed for that relay session; both sides always run the same baud/framing
  (8N1, no independent per-side rate).
- The firmware logs every relayed chunk to `apps_data/flipperphunk/*.log`
  on the SD card; it does not resend or buffer bytes across a stop/restart.

## Limitations

- **Latency measurement method**: one marker byte per sample, host
  timestamps taken immediately around `write()` and the matching `read(1)`,
  with the receiver's buffer drained before each sample so there's no
  ambiguity about which byte arrived. This is a coarse, host-side,
  single-flight measurement -- it bundles Python/OS scheduling jitter, the
  USB-UART adapter's own buffering, and USB polling interval together with
  whatever time the Flipper firmware actually takes to relay the byte. Do
  not read precision finer than roughly 1ms out of it, and do not treat it
  as a firmware-only or lab-grade number.
- **Byte-level diff classification** (`serial_test/compare.py`) labels
  `difflib` "insert" regions as `duplicated_or_extra_bytes`. On a pure
  relay that's almost always retransmission/duplication, but the tool
  cannot prove that from content alone -- treat it as "extra bytes that
  don't correspond to anything we sent at that point," not a certainty
  about *why* they're there.
- **Detailed diffs are skipped above ~256KB** per comparison (see
  `DETAILED_DIFF_MAX_BYTES` in `compare.py`) -- large sustained/soak tests
  still report exact pass/fail and simple sent/received/dropped counts,
  just without a byte-by-byte classification.
- **Sustained tests hold the full transferred payload in memory** for
  verification. That's fine for the sizes/durations this tool's guardrails
  allow by default; very large `--allow-long-soak` runs should be sized
  with available RAM in mind.
- **Failure/recovery testing is only partly automatable.** App restart,
  bridge stop/restart, physical cable disconnect/reconnect, and the
  on-device pause toggle all require a human at the bench -- `recover
  watch` observes and logs the resulting gaps but cannot trigger those
  actions itself. Only the host-side serial port close/reopen
  (`recover port-cycle`) is fully automated.
- **Mock/self-test mode does not model real UART timing or baud-rate
  throttling.** `--mock` (and `self-test`) validate the harness's own logic
  (pattern generation, comparison, threading, gap detection, CLI plumbing)
  against an in-process simulated relay, which forwards bytes as fast as
  Python can move them regardless of the configured baud. Do not read
  mock-mode throughput/latency numbers as representative of anything about
  the real firmware or hardware.

## Validation performed

- `python -m py_compile` over every module (syntax/import check).
- `pytest` unit tests (`tests/`) covering: deterministic/reproducible
  pattern generation including chunked streaming, byte-comparison/framing
  classification (exact match, dropped/duplicated/corrupted detection,
  large-payload fallback), JSON/CSV result serialization, and the mock
  serial/bridge simulator (forwarding, pause/resume, stop, timeout
  behavior).
- End-to-end runs of every CLI subcommand (`bridge`, `sweep`, `sustained`
  one-way/bidirectional/by-duration, `latency`, `recover watch`,
  `recover port-cycle`, `self-test`) against the in-process mock bridge.
- **No real USB-UART hardware or physical Flipper bridge test was
  performed as part of producing this tool.** Only one USB-UART adapter
  was present in the environment this tool was built in (no second
  adapter, and no Flipper wired up per the bench setup above), so the
  two-port hardware path described in this README has not been exercised
  end to end. Run the commands under "Usage" against real hardware before
  relying on their results.

## Recommended first physical test

1. Wire the bench setup above; connect Adapter A and Adapter B to the host,
   confirm both enumerate (`list-ports`).
2. Flash/launch FlipperPhunk on the Flipper, select 9600 baud on the setup
   screen, press OK to start the relay.
3. `python -m serial_test.cli bridge --port-a <A> --port-b <B> --baud 9600
   --patterns ascii incrementing --length 256` -- confirms basic
   bidirectional relay correctness before anything longer.
4. If that passes, run `sweep`, a short `sustained --duration 30`, and
   `latency --samples 50` to build out a baseline before soak testing.
