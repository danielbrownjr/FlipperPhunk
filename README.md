# FlipperPhunk — RS232 Inline MitM Tap for Flipper Zero

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

```
 Device A (DTE/DCE)                                   Device B (DTE/DCE)
   RS232 @ ±12V                                          RS232 @ ±12V
       │                                                      │
   ┌───┴────┐   MAX3232 (RS232 <-> 3.3V TTL)            ┌─────┴──┐
   │ DE-9 A │───────────────┐                ┌──────────│ DE-9 B │
   └────────┘               │                │          └────────┘
                       ┌─────▼────────────────▼─────┐
                       │   Level-shifter board       │
                       │   (see hardware/README.md)  │
                       └─────┬────────────────┬──────┘
                         TX/RX (3.3V TTL)  TX/RX (3.3V TTL)
                             │                │
                       ┌─────▼────────────────▼──────┐
                       │        Flipper Zero          │
                       │  USART (pins 13/14) = side A │
                       │  LPUART (pins 15/16) = side B│
                       │  FlipperPhunk app             │
                       └───────────────────────────────┘
```

The board is **inline**, not a passive tap: Device A's TX line is broken and
terminates at the Flipper (via level shifting), and the Flipper's own TX line
feeds Device B's RX — and vice versa. That means the Flipper app is the thing
actually relaying bytes between A and B, so it sees, logs, and can hold or
inject on every byte in both directions. If the Flipper app isn't running or
the relay is paused, the link between A and B is down — there is no
passive fallback path.

## Repo layout

- `hardware/` — level-shifter board design: schematic description, BOM,
  wiring table from RS232 through to the Flipper GPIO header.
- `firmware/flipperphunk/` — the Flipper Zero application (FAP) source.

## Quick start

1. Build the hardware from `hardware/README.md`.
2. Build and deploy the app — see `firmware/flipperphunk/README.md`.
3. Wire Device A and Device B into the two DE-9 ports on the board, plug the
   board's ribbon/header into the Flipper's GPIO pins per the wiring table,
   power the board from the Flipper's 3V3 rail (pin 9), launch the app,
   select the baud rate/framing to match the link under test, and start the
   relay.

## Status / limitations

- Firmware targets the stock Flipper Zero firmware `furi_hal_serial` API
  (USART + LPUART channels). It has not yet been flashed to real hardware —
  see `firmware/flipperphunk/README.md` for what's been validated (compiles
  under `ufbt`) versus what still needs a bench test.
- Injection is currently a minimal hook (a fixed byte sequence bound to a
  button) rather than a full text-entry UI — documented in the firmware
  README as the natural next extension.
- Both sides currently must run the same baud rate/framing (no rate
  conversion between A and B).
