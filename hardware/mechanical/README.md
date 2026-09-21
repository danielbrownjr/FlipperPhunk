# FlipperPhunk Rev C.1 mechanical fit-check

## Purpose

`FlipperPhunk_RevC1_FitCheck.stl` and `FlipperPhunk_RevC1_FitCheck.step`
are 1:1 physical dummy-board models for checking the current Rev C.1 connector
placement, component lead/socket fit, cable clearance, mounting-hole access, and
Flipper mating geometry before PCB fabrication.

**This is only a mechanical fit-check. It is not electrically functional and
must not be used as electrical, PCB-layout, routing, manufacturing, or
fabrication authority.** The canonical electrical/mechanical source remains
`hardware/kicad/FlipperPhunk_RevC1.kicad_pcb`.

The known awkward J1 placement is intentionally reproduced without redesign.
Moving J1 to the bottom/bottom-edge arrangement remains a later-revision item.

## Dimensions and derived geometry

- Finished model size: **110.00 x 60.00 x 1.60 mm**.
- The 110 x 60 mm outline is the exact rectangle on `Edge.Cuts`, from KiCad
  coordinates `(20.00, 20.00)` to `(130.00, 80.00)` mm.
- Thickness is the PCB's declared **1.60 mm** value.
- The model origin is the outline corner at KiCad coordinate `(20.00, 20.00)`.
  KiCad's MCAD export keeps +X and converts its screen-down +Y convention to
  MCAD -Y, so the models span `X = 0..110` and `Y = -60..0` mm. The CSV records
  both original PCB coordinates and these exact local model coordinates.
- Exactly **56 through-holes** are reproduced:
  - four PCB mounting holes (`H1`-`H4`);
  - J2 Würth 618009231121 pins 1-9 and shell/mechanical holes S1/S2;
  - J3 Würth 618009231221 pins 1-9 and shell/mechanical holes S1/S2;
  - J1 Samtec SSW-108-01-F-D pins 1-16;
  - A1's two 1x6 Samtec SSW-106-01-G-S socket rows and two module
    mounting/clearance holes.

The exact hole centers and diameters are listed in
`FlipperPhunk_RevC1_FitCheck_holes.csv`. Hole centers are transformed directly
from the footprint/pad placements in the canonical PCB; no center was moved.

Copper, soldermask, silkscreen, traces, zones, component bodies, connector
shells, and raised labels are intentionally omitted. Their addition would make
the print less useful as a component lead/socket fit gauge or could interfere
with installing real parts.

## FDM hole compensation

Every included through-hole receives exactly **+0.30 mm on diameter** (that is,
`+0.15 mm` radial clearance). This is within the requested +0.2 to +0.4 mm FDM
allowance.

| Geometry | KiCad drill | Fit-check hole |
| --- | ---: | ---: |
| PCB mounting holes H1-H4 | 3.20 mm | 3.50 mm |
| J1 signal/socket holes | 1.02 mm | 1.32 mm |
| J2 signal pins | 1.09 mm | 1.39 mm |
| J2 shell/mechanical holes | 3.20 mm | 3.50 mm |
| J3 signal pins | 1.04 mm | 1.34 mm |
| J3 shell/mechanical holes | 3.20 mm | 3.50 mm |
| A1 socket-row holes | 1.00 mm | 1.30 mm |
| A1 mounting/clearance holes | 2.70 mm | 3.00 mm |

Printer calibration, elephant foot, filament shrinkage, and slicer horizontal
expansion can still change the printed result. Treat the 0.30 mm allowance as a
documented starting point, not a substitute for printer calibration.

## Rebuild

Requirements:

- Python 3.11 or newer;
- KiCad CLI 10.x (the script auto-detects the standard Windows KiCad 10 path);
- optional `trimesh` for STL topology/dimension validation.

From the repository root:

```powershell
python hardware/mechanical/generate_fit_check.py
```

If KiCad CLI is elsewhere:

```powershell
python hardware/mechanical/generate_fit_check.py --kicad-cli "C:\path\to\kicad-cli.exe"
```

The script does not edit the electrical PCB. It creates a temporary board copy,
adds the documented drill compensation, and invokes KiCad's board-only STL and
STEP exporters. KiCad's board-only exporter removes 0.09 mm assigned to the
default copper/soldermask stack from the declared finished thickness; the
temporary export copy compensates for that exporter behavior so the printable
solid is exactly 1.60 mm thick. The canonical PCB remains 1.60 mm and unchanged.

## Suggested FDM settings

- Print flat, with either broad face on the build plate.
- Use a 0.4 mm nozzle, 0.20 mm layers, at least three perimeters, and 15-25%
  infill. No supports should be required.
- Use a well-calibrated dimensional profile. Disable or minimize slicer-level
  horizontal-hole expansion unless deliberately replacing the model's built-in
  +0.30 mm diameter allowance.
- Elephant-foot compensation is recommended. A brim may help if the 110 x 60 mm
  plate tends to lift, but keep brim material out of the holes.
- Let the print cool before test-fitting; insert component pins gently and do
  not force plated connector leads into undersized or stringy holes.

## Validation

Generation performs these checks before reporting success:

- source `Edge.Cuts` bounds equal **110.00 x 60.00 mm**;
- source thickness equals **1.60 mm**;
- all **56** requested hole centers are identical before and after compensation;
- every included diameter increases by exactly **0.30 mm**;
- generated STL extents equal **110.00 x 60.00 x 1.60 mm** within 0.02 mm;
- generated STL is a single watertight solid with topology corresponding to 56
  through-holes.

KiCad 10.0.6 successfully exported both STL and STEP. All required planar board
and through-hole geometry was reproduced faithfully. The models intentionally
do not reproduce connector bodies, socket bodies, board copper, or silkscreen;
real components are meant to be inserted into the printed hole pattern for the
fit check.
