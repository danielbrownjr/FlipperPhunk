# Sprite asset tooling

A reproducible source-to-Flipper conversion pipeline that generates the
splash-screen mascot animation shown in the FlipperPhunk app
(`firmware/flipperphunk.c`, `AppStateSplash`).

**This is not part of the firmware build.** It's a one-time (and
re-runnable) offline step: point `extract_sprites.py` at the source art
and it regenerates the committed 1-bit animation frames under
`firmware/images/`. The FAP build itself only ever consumes those
generated PNGs + `frame_rate` file, via the normal
[Flipper FAP asset pipeline](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/documentation/AppManifests.md)
(`fap_icon_assets="images"` in `firmware/application.fam`).

## Source image

- **File:** `FlipperPhunk_SideApp_SpriteSheet_Source.png`
- **Canonical location:** Google Drive, `05_Firmware/Assets/` (Drive file
  ID `1DwmPWJTRGDj4tQb82OAxmPe5T1BSI7FZ`) — see the FlipperPhunk project
  Mem note for the authoritative pointer.
- **Properties:** 2048x2048 RGBA PNG, multi-pose sprite sheet, full-color
  reference art. **Not** itself a Flipper-ready asset.
- **Not committed to this repo.** Google Drive is the binary/reference
  artifact vault for this project; GitHub holds the derived, reproducible
  pipeline and its output. Download a local copy and pass its path via
  `--source` when running the script.

## Selected pose sequence

The source sheet is a 10-column x 5-row grid of populated cells (last row
partial, 45 cells total), auto-detected from alpha coverage rather than
hardcoded pixel coordinates (see `build_cellmap()` — it bands rows/columns
of nonzero alpha and takes each cell's tight bounding box). That detection
is deterministic given the same source file.

From that grid, four `(row, col)` cells were selected as a short "bop"
loop (see `SELECTED_FRAMES` in `extract_sprites.py`):

| Frame | Grid cell | Pose |
| ----- | --------- | ---- |
| 0 | `(2, 7)` | Extended "down beat" — arm/mic swung out |
| 1 | `(3, 3)` | Bent-arm "up beat" accent, mic pulled to chest |
| 2 | `(3, 7)` | Transition back down |
| 3 | `(4, 2)` | Settled hold (loops back into frame 0) |

The sheet also contains a much longer walk/run cycle and a separate
desaturated "glitch" palette variant; this animation deliberately uses
only enough frames from the plain-color idle poses to make the bop
motion obvious, per the design brief (low frame count, not a literal
reproduction of every sprite in the sheet).

## Pipeline

1. **Grid detection** — alpha-band the source into rows/cols, get each
   selected cell's tight bounding box.
2. **Monochrome classification** (`classify_frame`) — per pixel: opaque
   and not a "highlight" color -> black; everything else (background,
   skin, near-white fabric) -> white. This is a silhouette-plus-highlight
   reduction, not a literal grayscale threshold of the full-color art —
   see "Monochrome conversion" below for why.
3. **Highlight cleanup** (`clean_highlight_mask`) — binary closing (11x11
   kernel, 2 iterations) + hole fill + opening, then drop connected
   components under 1% of frame area. This bridges the internal linework
   (eyes, nose, knuckle creases) that would otherwise fragment the face
   into a speckled dither cloud, and removes stray noise, so the result
   is one or two clean light patches instead of noise.
4. **Registration** (`core_centroid_x`, feet baseline) — a single uniform
   scale factor is computed from one reference frame's height and applied
   to every frame (so prop/arm variance can't jitter the character's
   size); each frame is then positioned so its own feet baseline (bottom
   alpha row) and lower-body alpha centroid (legs/hips — stable across
   poses since only the arm swings) land on the same canvas anchor point
   every frame. This is what keeps the character from jittering frame to
   frame despite the source poses having different bounding boxes.
5. **Scaling method** — two different resizes, deliberately:
   - Shape reduction from source resolution down to a 4x-supersampled
     working canvas (160x160 for a 40x40 target) uses **Lanczos**
     resampling. A literal nearest-neighbor subsample straight from a
     ~200px-tall source crop down to a ~36px character would alias into
     noise and destroy the outline — Lanczos is what actually preserves
     the shape here.
   - That Lanczos step reintroduces antialiased gray edges, so the
     supersampled canvas is immediately **re-thresholded at 128** back to
     pure black/white before the final step.
   - The final reduction from the clean supersampled binary image down to
     the shipped 40x40 size uses **nearest-neighbor**, which is safe here
     specifically because the source for that step is already a clean,
     antialiasing-free binary shape (not detailed color art) — it keeps
     hard pixel-art edges instead of reintroducing gray fringe pixels.
6. **Output** — each frame saved as a 1-bit (`mode="1"`) PNG,
   `frame_0.png .. frame_3.png`, plus a `frame_rate` file containing `4`
   (within the requested 3-6 FPS "deliberately choppy" range), written to
   `firmware/images/Mascot_bop_40x40/`.

## Monochrome conversion method (why silhouette + highlight, not threshold+dither)

An early version of this pipeline did a straightforward grayscale
luminance threshold with light Bayer ordered dithering in the midtone
band. At the target size that produced a noisy speckled blob with no
recognizable structure — exactly the "noisy cloud of dithering that
destroys the shape" the design brief warns against, because at ~40px the
sprite sheet's mid-value fill colors (cap red, hair blue, shorts blue)
all collapse into a similar dithered gray. It was replaced with the
silhouette + highlight classifier described above: everything opaque
renders black by default (preserving the heavy source outlines first, as
required), and only skin tone and near-white fabric are carved out as
light patches, cleaned into solid blobs rather than speckle. This favors
recognizability over a literal color-to-luminance conversion, per the
brief's explicit priority.

Color heuristics (see constants at the top of `extract_sprites.py`):

- **Skin:** `R > 170`, `110 < G < 215`, `90 < B < 190`, `R > G`,
  `G >= B - 10`, `R - B > 25` (tuned against this source sheet's skin
  tone by sampling; see `skin_mask`).
- **White/near-white fabric:** `max(R,G,B) > 210` and saturation
  (`max - min`) `< 40`.

No dithering is used in the final image at all — every pixel is a clean
binary decision (silhouette/highlight classification, then a hard
128-threshold after the Lanczos resize).

## Target dimensions

40x40 px, chosen from the requested "roughly 32-48 px character height"
range and the app's `NAME_VARIANT_SIZE` Flipper asset-naming convention
(`Mascot_bop_40x40` -> compiled symbol `A_Mascot_bop_40x40`).

## Output location

- `firmware/images/Mascot_bop_40x40/frame_0.png` .. `frame_3.png` — the
  four animation frames, all 40x40, 1-bit.
- `firmware/images/Mascot_bop_40x40/frame_rate` — contains `4`.

The Flipper FAP asset compiler detects the `frame_rate` file in this
subdirectory and generates `const Icon A_Mascot_bop_40x40` in the app's
auto-generated `..._icons.c`/`.h` (confirmed by inspecting the actual
`ufbt` build output — see the PR/Mem note for the exact generated
symbol). `firmware/flipperphunk.c` references it directly via
`icon_animation_alloc(&A_Mascot_bop_40x40)`.

## Running it

```sh
cd tools/sprite_assets
pip install -r requirements.txt
python extract_sprites.py --source /path/to/FlipperPhunk_SideApp_SpriteSheet_Source.png
```

Regenerates `firmware/images/Mascot_bop_40x40/` in place and runs
`validate()` (frame count, identical 40x40 dimensions, binary pixel
values, positive-integer `frame_rate`) before exiting. Re-run after any
change to `SELECTED_FRAMES`, the target size, or the classification
heuristics; the tool is deterministic given the same source file.

## Known limitations

- The skin/fabric heuristics were tuned against this one source sheet's
  specific palette; a different character or art style would need new
  color thresholds.
- Registration assumes the character's feet stay near the bottom of each
  frame's bounding box and legs stay roughly still across poses (used as
  the horizontal anchor). That holds for this bop sequence but wouldn't
  suit e.g. a jump animation without adjustment.
