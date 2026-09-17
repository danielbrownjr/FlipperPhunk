# Hardware — Inline RS232 Level-Shifter / Relay Board

This board sits **inline** in an RS232 link between two devices (A and B). It
breaks both signal paths and hands them to the Flipper Zero as two
independent, level-shifted, full-duplex 3.3V TTL UARTs. The Flipper app is
what actually reconnects A and B (see `firmware/flipperphunk/`) — the board
itself does no relaying, only voltage translation.

This is a schematic-level design (BOM + wiring tables), meant to be laid out
on perfboard or a simple 2-layer PCB. No KiCad project is included yet; ask
if you want one generated from this design.

## Concept

Each RS232 side needs one driver (TTL→RS232, for the Flipper's TX into that
device's RX) and one receiver (RS232→TTL, for that device's TX into the
Flipper's RX). Two sides = 2 drivers + 2 receivers, which is exactly one
**MAX3232** (or MAX3232E for extra ESD margin) — it has 2 drivers/2 receivers
and only needs 4 external 0.1µF caps for its internal charge pump, running
off 3.3V.

```
                         MAX3232
                     ┌───────────────┐
 DE-9 A pin 3 (TXD)──►R1IN     R1OUT ├──► Flipper pin 14 (USART RX)
 DE-9 A pin 2 (RXD)◄──T1OUT     T1IN │◄── Flipper pin 13 (USART TX)
 DE-9 A pin 5 (GND)──────────────GND │
                     │               │
 DE-9 B pin 3 (TXD)──►R2IN     R2OUT ├──► Flipper pin 16 (LPUART RX)
 DE-9 B pin 2 (RXD)◄──T2OUT     T2IN │◄── Flipper pin 15 (LPUART TX)
 DE-9 B pin 5 (GND)──────────────GND │
                     │  C1+ C1- C2+ C2-  VCC  GND
                     └───┬───┬───┬───┬────┬────┬──┘
                        0.1uF pairs to   3.3V  Flipper GND
                        the 4 cap pins  (Flipper (pin 8/11/18)
                        per datasheet    pin 9)
```

Notes:
- DE-9 pinout above assumes each device is wired as **DTE** (the common case
  for PCs, PLCs, most embedded gear) — TXD is pin 3, RXD is pin 2, GND is
  pin 5 on a standard DE-9. If a device is actually DCE (e.g. a modem), its
  TXD/RXD are swapped relative to this table — check the target device's
  pinout before wiring, since getting it backwards just means no data flows
  (not damage), because the MAX3232 receiver inputs tolerate the full
  ±30V RS232 swing.
- Add a **TVS diode array** (e.g. SM712 or similar RS232-rated array) on the
  four RS232-side lines (both DE-9 connectors' pins 2/3) for ESD/surge
  protection — you're plugging this into unknown field equipment during
  engagements, so don't skip this.
- Tie unused RS232 handshake lines (RTS/CTS/DTR/DSR/DCD) straight through
  with a wire loopback at each DE-9 (e.g. jumper RTS→CTS, DTR→DSR+DCD) if the
  target devices expect hardware flow control / handshake to be present, since
  this board only relays TXD/RXD. If your target link doesn't use hardware
  flow control (most simple point-to-point serial links don't), you can
  leave them unconnected.

## Bill of materials

| Ref | Part | Notes |
|---|---|---|
| U1 | MAX3232E (SOIC-16 or use a breakout module) | 3.3V RS232 transceiver, 2 TX/2 RX |
| C1–C4 | 0.1µF ceramic, 16V+ | MAX3232 charge-pump caps |
| C5 | 0.1µF ceramic | VCC decoupling, close to U1 |
| J1, J2 | DE-9 female connector | One per RS232 side (A, B) |
| D1–D4 | TVS diode array (e.g. SM712) or 4x individual TVS | ESD/surge protection on TXD/RXD lines, optional but recommended |
| J3 | 2.54mm pin header, 6-pin | Connects to Flipper GPIO: 3V3, GND, pins 13/14/15/16 |
| — | Perfboard or 2-layer PCB, wire, standoffs, enclosure | Mechanical |

A ready-made "MAX3232 RS232 to TTL" breakout module (widely available, ~$1-2,
often sold in Arduino accessory kits) can replace U1+C1-C5+J1 if you only
need one side — you'd need **two** such modules (one per RS232 side) wired
into the Flipper's two UART channels, which is a faster path to a working
prototype than building a custom board first.

## Wiring table: board → Flipper GPIO header

Flipper Zero's GPIO header pinout (relevant pins only):

| Flipper pin | Function | Connect to |
|---|---|---|
| 1 | +5V (must be enabled in GPIO settings) | not used |
| 8 | GND | board GND |
| 9 | +3.3V (max 1.2A) | board VCC |
| 11 | GND | board GND (2nd tie point if needed) |
| 13 | USART1 TX | MAX3232 T1IN (drives Side A's RXD) |
| 14 | USART1 RX | MAX3232 R1OUT (receives Side A's TXD) |
| 15 | LPUART TX | MAX3232 T2IN (drives Side B's RXD) |
| 16 | LPUART RX | MAX3232 R2OUT (receives Side B's TXD) |
| 18 | GND | board GND |

The firmware (`firmware/flipperphunk/`) is written for exactly this pin
assignment — Side A = USART (13/14), Side B = LPUART (15/16). If you rewire
differently, update `SIDE_A_ID`/`SIDE_B_ID` in `flipperphunk_app.c` to match.

## Safety

- Never connect the RS232-side (J1/J2) pins directly to the Flipper's GPIO —
  RS232's ±12V swing will destroy the Flipper's 3.3V-tolerant I/O instantly.
  The MAX3232 is not optional.
- Power the board from the Flipper's 3.3V rail, not a separate supply, unless
  you tie grounds together — floating/mismatched grounds between the board
  and the Flipper will corrupt or destroy the logic-level signaling.
- Verify with a multimeter (RS232 side floating, board unpowered) that DE-9
  pin 2/3 are not shorted to pin 5 (GND) or to each other before first power-up.
