# flipperphunk (Flipper Zero app)

Inline RS232 relay/sniffer/injector. Pairs with the level-shifter board in
`../hardware/`. See the top-level `README.md` for the overall system and
`../hardware/README.md` for wiring.

## What it does

- Acquires the Flipper's two hardware serial peripherals: **USART**
  (GPIO 13/14 — J2 HOST/PC side) and **LPUART** (GPIO 15/16 — J3
  INSTRUMENT/DCE side).
- Relays every byte received on one side out the other, in real time, so the
  two RS232 devices keep talking normally while the Flipper is inline.
- Logs every byte, timestamped and tagged by direction, to
  `/ext/apps_data/flipperphunk/captureN.log` on the SD card (plain text:
  `<tick_ms> <dir> <hex bytes...>`, where `dir` is `>` for A→B, `<` for B→A,
  and `i`/`I` for an injected chunk).
- Shows live byte counters and the last 8 bytes seen in each direction,
  labeled **Phunk In** (Side A traffic, relayed A→B) and **Phunk Out**
  (Side B traffic, relayed B→A).
- **Pause** (short-press OK while running): stops relaying without stopping
  logging — bytes from both sides are captured but no longer forwarded, so
  you can freeze the link mid-transaction. Short-press OK again to resume.
- **Inject** (long-press OK while running): sends a fixed byte sequence out
  whichever side is focused (Left/Right selects Side A/Side B, shown top
  right). The payload is `INJECT_PAYLOAD` in `flipperphunk.c` — edit it to
  whatever you need for a given engagement and rebuild. A proper on-device
  text-entry UI for arbitrary injection payloads is the natural next step;
  this is deliberately a minimal hook rather than that.

In the current UI/source naming, Side A means J2 HOST/PC and Side B means J3
INSTRUMENT/DCE. Rev C.1 is an active bridge: stopping this app, losing power,
or crashing interrupts both TX/RX data paths because no hardware bypass is
implemented.

Both sides run the same baud rate (selectable at the setup screen:
1200–115200) and framing (fixed at 8N1 — edit
`furi_hal_serial_configure_framing` calls in `relay_start()` if your target
link needs different framing).

## Build

Requires Python 3 and [ufbt](https://pypi.org/project/ufbt/) (installs the
Flipper SDK + ARM toolchain automatically, no full firmware checkout needed):

```sh
pip install ufbt
cd firmware
ufbt          # builds ./dist/flipperphunk.fap (or .ufbt/build/flipperphunk.fap)
```

This has been build-tested against SDK/firmware channel `release` (1.4.3 at
the time of writing) — it compiles clean with no warnings.

## Flash / run

With the Flipper connected over USB:

```sh
ufbt launch   # builds, uploads, and launches the app on the connected Flipper
```

Or copy the built `.fap` to `SD card:/apps/GPIO/` and launch it from the
Flipper's Apps menu.

## What's verified vs. not

- **Verified:** compiles cleanly against the real `furi_hal_serial` /
  `furi_hal_serial_control` / storage / GUI SDK headers and API, using
  `ufbt build`.
- **Not yet verified:** behavior on real hardware — the relay timing under
  load, whether the 2048-byte stream buffers and 64-byte relay chunks are
  sized right for your target baud rate/traffic pattern, and SD card write
  throughput at high baud rates (if logging can't keep up, bytes queue up in
  the stream buffer and, if it fills, are dropped — increase `RX_STREAM_SIZE`
  in `flipperphunk.c` if you see gaps in the log versus what you know the
  target sent). Bench-test against a known-good serial link before relying
  on this in the field.
- The app calls `expansion_disable()`/`expansion_enable()` around the serial
  handles so it doesn't fight with the Flipper's GPIO expansion-module
  service for the same UART pins — if you've got an expansion module
  physically attached, unplug it while using this app.
