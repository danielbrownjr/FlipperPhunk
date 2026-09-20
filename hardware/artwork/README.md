# PCB artwork sources and derivatives

`FlipperPhunk_PCB_Silkscreen_Mascot_Concept.png` is the unchanged source asset
from Google Drive file `10mS8YFlCxH06XEhFGrP6FUxIgZma-iS4`. It is concept art,
not fabrication-ready PCB geometry.

`FlipperPhunk_PCB_Silkscreen_Mascot_Simplified.svg` is the manufacturing-oriented
monochrome derivative used by Rev C.1. `vectorize_mascot.py` regenerates the SVG
and the project-local KiCad footprint at
`../kicad/FlipperPhunk.pretty/FlipperPhunk_Mascot_BSilkscreen.kicad_mod`.

The Rev C.1 printed geometry is approximately 24.26 x 22.03 mm on `B.SilkS`,
inside a 26.00 x 22.67 mm SVG canvas. Vectorization uses the PNG alpha channel,
a 0.25 mm morphological feature filter, a 0.06 mm2 isolated-area filter, and
0.05 mm contour simplification. The source pose and overall silhouette are
preserved; anti-aliasing and details too small for dependable silkscreen
reproduction are intentionally removed.
