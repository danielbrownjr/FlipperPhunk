# Hardware — Rev C.1 active dual-UART RS-232 bridge/logger

Rev C.1 is a carrier for the Flipper Zero and an **Adafruit 5987 RS232 Pal**
module. It sits inline between a normal host/PC (DTE) and an instrument (DCE),
level-shifts both data directions, and presents them to the Flipper's two native
hardware UARTs. The Flipper app receives and retransmits the traffic; the
carrier itself does not bridge the two data paths.

This repository contains the source/history documentation. See the top-level
[`README.md`](../README.md#project-authority) for where canonical project
state, audited schematics, and other design artifacts are actually
maintained.

## What Rev C.1 is (and is not)

- It is an **active dual-UART inline bridge/logger**, not a passive tap.
- If the Flipper loses power, the app crashes, or forwarding stops, TX/RX
  communication stops. **No fail-safe bypass is implemented.**
- The six handshake signals pass straight through and are not observed by the
  Flipper.
- Selectable DTE/DCE/null-modem routing and galvanic isolation are not
  implemented.
- HV-side TVS/series protection and DE-9 shell grounding remain open design
  decisions. Do not infer either feature from this document.

## Reference designators

| Ref | Part | Role |
| --- | --- | --- |
| A1 | Adafruit 5987 RS232 Pal | Dual-channel MAX3232E RS-232/3.3 V translator; charge-pump capacitors are already on the module |
| J1 | Flipper Zero GPIO header | 2x8, 2.54 mm female receptacle; only pins 8, 9, 11, and 13–16 are used |
| J2 | DE-9 female | HOST/PC side; mates with a normal DTE male port |
| J3 | DE-9 male | INSTRUMENT side; mates with a normal DCE female port |

Do **not** add external MAX3232E charge-pump capacitors to the carrier. A1
contains the transceiver and its support circuitry. A1 `V+` and `V-` are
charge-pump outputs, not power inputs; leave them unconnected unless they are
deliberately exposed as clearly labelled test points.

## Canonical Rev C.1 data paths

| Direction | Path |
| --- | --- |
| Host/PC to Flipper | J2 pin 3 (DTE TX) -> A1 `R1_HV` -> A1 `R1_LV` -> J1 pin 14 (USART RX) |
| Flipper to host/PC | J1 pin 13 (USART TX) -> A1 `T1_LV` -> A1 `T1_HV` -> J2 pin 2 (DTE RX) |
| Instrument to Flipper | J3 pin 2 (DCE TX) -> A1 `R2_HV` -> A1 `R2_LV` -> J1 pin 16 (LPUART RX) |
| Flipper to instrument | J1 pin 15 (LPUART TX) -> A1 `T2_LV` -> A1 `T2_HV` -> J3 pin 3 (DCE RX) |

The J3 mapping is intentionally the opposite pin role from a DTE connector:
for a normal DCE instrument, pin 2 is its TX output and pin 3 is its RX input.
Verify pin numbering from the mating face and against the selected connector
footprint before fabrication.

The `Rx_HV`/`Rx_LV`/`Tx_HV`/`Tx_LV` labels above are descriptive names for A1's
physical pins, which are silkscreened per the [A1 carrier
geometry](#a1-carrier-geometry) below using the module's own names:
`R1_HV`=`R1IN`, `R1_LV`=`R1OUT`, `T1_LV`=`T1IN`, `T1_HV`=`T1OUT`,
`R2_HV`=`R2IN`, `R2_LV`=`R2OUT`, `T2_LV`=`T2IN`, `T2_HV`=`T2OUT`.

## Power, ground, and handshake nets

| Net | Connections / implementation |
| --- | --- |
| `+3V3` | J1.9 -> A1.VIN |
| `GND` | J1.8, J1.11, J2.5, J3.5, A1.GND |
| `DCD_PASS` | J2.1 <-> J3.1 |
| `DTR_PASS` | J2.4 <-> J3.4 |
| `DSR_PASS` | J2.6 <-> J3.6 |
| `RTS_PASS` | J2.7 <-> J3.7 |
| `CTS_PASS` | J2.8 <-> J3.8 |
| `RI_PASS` | J2.9 <-> J3.9 |

Handshake lines may be plain copper or optional 0 ohm links/solder bridges.
They are straight-through nets; do not loop them locally at either connector.
This treatment is valid for the intended DTE-to-DCE installation. A DTE
instrument requires an external null-modem adapter until selectable routing is
implemented in a future revision.

## A1 carrier geometry

The following dimensions were verified from Adafruit's official Eagle board
source at commit `653d1bb7c6cf2d9efe381b85ff275bf0feefdb17`:

- board outline: 17.78 x 20.32 mm, 2.54 mm corner radius;
- two 1x6 plated-through-hole rows at 2.54 mm pitch;
- 12.70 mm row-to-row spacing;
- header holes: 1.00 mm drill, 1.778 mm pad diameter;
- two mounting holes: 2.50 mm drill, 3.20 mm pad diameter, 15.24 mm pitch;
- LV row, bottom-to-top: `T1IN`, `R1OUT`, `T2IN`, `R2OUT`, `GND`, `VIN`;
- HV row, bottom-to-top: `T1OUT`, `R1IN`, `T2OUT`, `R2IN`, `V-`, `V+`.

Use the [official Adafruit RS232 Pal PCB repository](https://github.com/adafruit/Adafruit-RS232-Pal-PCB)
as the source authority for module geometry. The Drive artifact
`07_Reference/FlipperPhunk_Adafruit_5987_Carrier_Footprint_Reference.md`
contains the full coordinate and keepout handoff.

## Canonical artifacts

- `01_Schematics/Rev_C1/FlipperPhunk_RS232_RevC1_AUDITED.svg`
- `01_Schematics/Rev_C1/FlipperPhunk_RS232_RevC1_AUDITED.png`
- `02_Netlists_BOM/FlipperPhunk_RevC1_Netlist_BOM_AUDITED.xlsx`
- `07_Reference/FlipperPhunk_Adafruit_5987_Carrier_Footprint_Reference.md`
- `03_Datasheets/MAX3232E/max3232e.pdf`

Use the audited workbook when transcribing the design into KiCad or another
EDA package. No PCB layout or fabrication package is currently committed to
this repository.

## Pre-fabrication checks

- Confirm the physical A1 module, socket/header stack, mounting-hole fit, and
  component-side clearance.
- Confirm J2/J3 footprint pin numbering from the mating face.
- Decide on RS-232-side TVS/series protection — Rev C.1 as documented has
  **none**. You are plugging this into unknown field equipment during
  engagements; do not use it there until this is resolved.
- Decide whether each DE-9 shell floats or bonds to signal/chassis ground.
- Run schematic ERC and PCB DRC after EDA capture.
- Before first power-up, with the RS-232 side floating and the board
  unpowered, verify with a multimeter that no J2/J3 pin 2/3 is shorted to
  pin 5 (GND) or to any other pin.
- Bench-test forwarding and logging on a known-good DTE/DCE serial link before
  using the device on field equipment.

Never connect RS-232 voltage levels directly to Flipper GPIO. A1 is the
required voltage-domain boundary.
