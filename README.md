# FlipperPhunk — RS-232 Bridge/Logger/MitM for Flipper Zero

An inline RS232 interception rig for authorized security testing: a small
level-shifter board sits between two serial devices, and a Flipper Zero app
relays, logs, and can inject on the wire in real time.

> **Authorized use only.** This is a dual-use security tool intended for
> engagements you are authorized to test (pentests, red-team work, your own
> lab equipment) or CTF/research use. Intercepting communications you do not
> own or have written authorization to test is illegal in most jurisdictions
> (e.g. wiretapping statutes, CFAA-adjacent laws). Keep engagement paperwork
> on hand when using this in the field.

## How it works

Rev C.1 uses one Adafruit 5987 RS232 Pal module as the dual-channel voltage
boundary. J2 is the female HOST/PC connector and uses Flipper USART on GPIO
pins 13/14. J3 is the male INSTRUMENT/DCE connector and uses LPUART on GPIO
pins 15/16. See [`hardware/README.md`](hardware/README.md) for the audited
pin-level mapping.

The board is **inline**, not a passive tap: Device A's TX line is broken and
terminates at the Flipper (via level shifting), and the Flipper's own TX line
feeds Device B's RX — and vice versa. That means the Flipper app is the thing
actually relaying bytes between A and B, so it sees, logs, and can hold or
inject on every byte in both directions. If the Flipper app isn't running or
the relay is paused, the link between A and B is down — there is no
passive fallback path.

Rev C.1 also has no selectable DTE/DCE/null-modem matrix, galvanic isolation,
or implemented fail-safe bypass. Its handshake lines pass straight through
and are not captured by the Flipper.

## Project authority

- **Mem** — current project truth, revision state, and design decisions live
  in a private project-knowledge note (not linked here since this repo is
  public; ask the project owner for access).
- **GitHub** — source code and repository history.
- **Google Drive** — audited schematics, netlists/BOMs, datasheets, and other
  binary/design artifacts live in a private artifact vault (access-controlled
  separately from this repo; ask the project owner for access).

## Repo layout

- `hardware/` — level-shifter board design: schematic description, BOM,
  wiring table from RS232 through to the Flipper GPIO header.
- `firmware/` — the Flipper Zero application (FAP) source.
- `tools/sprite_assets/` — reproducible source-to-Flipper conversion
  pipeline for the firmware's splash-screen mascot animation. See
  `tools/sprite_assets/README.md`.

## Quick start

1. Build the hardware from `hardware/README.md`.
2. Build and deploy the app — see `firmware/README.md`.
3. Connect the host/PC to J2 and the DCE instrument to J3, plug the
   board's ribbon/header into the Flipper's GPIO pins per the wiring table,
   power the board from the Flipper's 3V3 rail (pin 9), launch the app,
   select the baud rate/framing to match the link under test, and start the
   relay.

## Status / limitations

- Firmware targets the stock Flipper Zero firmware `furi_hal_serial` API
  (USART + LPUART channels). It has not yet been flashed to real hardware —
  see `firmware/README.md` for what's been validated (compiles
  under `ufbt`) versus what still needs a bench test.
- Injection is currently a minimal hook (a fixed byte sequence bound to a
  button) rather than a full text-entry UI — documented in the firmware
  README as the natural next extension.
- Both sides currently must run the same baud rate/framing (no rate
  conversion between A and B).
- Hardware behavior remains bench-unverified; do not treat a successful
  firmware build as validation of the complete Rev C.1 assembly.
