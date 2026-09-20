# FlipperPhunk Rev C.1 KiCad project

This directory contains the initial manufacturable-layout capture of Rev C.1.
The design is an active dual-UART bridge/logger; it has no fail-safe bypass,
role switching, isolation, handshake monitoring, or speculative protection
circuitry.

## Open the project

Open `FlipperPhunk_RevC1.kicad_pro` with KiCad 10.0 or later. The project uses
only the project-local `FlipperPhunk.kicad_sym` and `FlipperPhunk.pretty`
libraries.

The generated board is 110.00 x 60.00 mm, two-layer, with four 3.2 mm M3
mounting holes. J2 is on the left edge, J3 is on the right edge, J1 is along
the top edge, and A1 is centered. The reserved `Dwgs.User` rectangles near the
DE-9 connectors intentionally leave space for a possible protection revision.

## Decorative bottom silkscreen

`LOGO1` is a board-only `FlipperPhunk:FlipperPhunk_Mascot_BSilkscreen`
footprint on `B.SilkS`, centered at board coordinate (53.0, 52.5) mm. Its
printed geometry is approximately 24.26 x 22.03 mm inside a 26.00 x 22.67 mm
SVG canvas. It sits in the open region between J2 and A1 and does not overlap
pads, holes, soldermask openings, connector labels, reference designators, or
pin-1/orientation markings.

The exact source is
`../artwork/FlipperPhunk_PCB_Silkscreen_Mascot_Concept.png`, retrieved from
Google Drive file `10mS8YFlCxH06XEhFGrP6FUxIgZma-iS4` (SHA-256
`339200fbbcba0f4e5484f77f06e7da99637f57516e74fdee5ba13d2bedb0f569`). The
source PNG remains unchanged and is not treated as fabrication geometry. The
committed `FlipperPhunk_PCB_Silkscreen_Mascot_Simplified.svg` and KiCad
footprint are monochrome derivatives. Conversion thresholds the source alpha,
uses a 0.25 mm morphological close/open operation, removes isolated regions
below 0.06 mm2, and simplifies vector contours to 0.05 mm. This retains the
recognizable silhouette and pose while removing anti-aliasing, hairlines, and
sub-process details.

The 0.25 mm artwork feature target is deliberately more conservative than
PCBWay's published 0.15 mm minimum legend width. KiCad DRC is clean with the
artwork in place. A fabrication preview should still be reviewed because final
silkscreen clipping and rendering are controlled by the selected board house's
CAM process.

## Exact footprints

- J2: `FlipperPhunk:Wurth_618009231121`, female, right-angle, with hex screws.
- J3: `FlipperPhunk:Wurth_618009231221`, male, right-angle, with hex screws.
- J1: `FlipperPhunk:Samtec_SSW-108-01-F-D`, 2x8, 2.54 mm pitch.
- A1: `FlipperPhunk:Adafruit_5987_Socketed`, implemented by two Samtec
  `SSW-106-01-G-S` 1x6 sockets.

The two Würth footprints reproduce the signal-pad, hex-screw/shell-pad, body,
and courtyard coordinates in Würth's official `KiCad_WR-DSUB (rev26b)` library
and current part drawings. The board placement follows the footprint's PCB-edge
indicator. Pin 1 is square and separately marked. J2 and J3 are deliberately
oriented so the board-side pad numbering agrees with their manufacturer
footprints; the schematic uses the corrected DCE mapping (`J3.2` instrument TX,
`J3.3` instrument RX). Do not infer pin numbering by looking only at the rear of
an unmated connector: verify continuity from each mating-face pin on the first
assembled board.

The Würth `S1` and `S2` hex-screw/shell pads are plated mechanical pads because
the actual parts require them. Both are explicit no-connects in the schematic
and have no PCB net, so the DE-9 shells remain electrically floating.

The A1 footprint uses the verified 17.78 x 20.32 mm rounded module outline,
12.70 mm row spacing, 2.54 mm pin pitch, 1.00 mm socket holes, and a 0.50 mm
assembly courtyard. Its two 2.70 mm carrier holes align with the module's
2.50 mm mounting holes for optional M2.5 standoffs. `V+` and `V-` are explicit
no-connects. The module outline/courtyard is the keep-clear region for tall
parts and exposed carrier pads.

## Routing and electrical decisions

All six handshake signals (pins 1, 4, 6, 7, 8, and 9) are routed as plain
copper from J2 to the same-numbered J3 pin. There are no 0-ohm links. The board
uses a solid B.Cu GND pour and 0.30 mm signal routing. All sixteen canonical
nets are fully connected. There is no TVS/ESD network in Rev C.1.

## Validation

Generated and checked with KiCad 10.0.6:

```powershell
kicad-cli sch erc FlipperPhunk_RevC1.kicad_sch --output erc.rpt
kicad-cli pcb drc FlipperPhunk_RevC1.kicad_pcb --output drc.rpt
```

Current result: ERC 0 errors / 0 warnings; DRC 0 violations / 0 unconnected
items / 0 footprint errors. The board generator requires KiCad's bundled Python
plus `kiutils` 1.4.8 and deterministically rebuilds the electrical footprints,
placement, routing, ground zone, schematic, and placement of the committed
mascot footprint. Rebuilding the mascot derivatives themselves additionally
requires Pillow, NumPy, and `opencv-python-headless`; run
`../artwork/vectorize_mascot.py` first if the source art changes.

## Mechanical assumptions to resolve before fabrication

No fabrication files are supplied or authorized by this revision. Before any
future order, physically measure or fit-check:

- the exact J2/J3 PCB-edge overhang, mating-face pin numbering, hex-screw
  hardware, and enclosure/panel clearance;
- J1 pin-1 orientation against the actual Flipper GPIO header, plus Flipper
  body/bumper clearance and the `SSW-108-01-F-D` mating height;
- both `SSW-106-01-G-S` socket tail fit, A1 insertion depth, total stack height,
  component-side clearance, and optional M2.5 standoff length;
- the actual Adafruit 5987 mounting-hole diameter/tolerance and whether the
  2.70 mm carrier holes provide the desired fit;
- cable strain and access to all four carrier mounting holes in the intended
  enclosure.

Also perform continuity checks from the DE-9 mating faces to the named nets,
confirm both floating shells, and bench-test on a known-good DTE/DCE link before
considering a fabrication release.
