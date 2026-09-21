#!/usr/bin/env python3
"""
Reproducible source-to-Flipper sprite extraction for FlipperPhunk's splash
mascot animation.

This tool is NOT part of the firmware build. It is a one-time (and
re-runnable) conversion step: point it at the canonical 2048x2048 RGBA
source sprite sheet (see README.md in this directory for where that file
lives) and it regenerates the 1-bit animation frames under
firmware/images/<ANIM_NAME>/ plus the `frame_rate` file the Flipper FAP
asset compiler expects.

Pipeline (see README.md "Pipeline" section for the full rationale):
  1. Detect the sprite sheet's grid (rows/cols of populated cells) from
     alpha data alone -- no hardcoded pixel grid.
  2. Select a coherent pose sequence by (row, col) grid coordinate.
  3. Classify each frame's pixels into "silhouette" (black) vs. "skin /
     light fabric highlight" (white) using color heuristics, then clean
     the highlight mask with morphology so it reads as solid patches
     instead of a dithered speckle cloud.
  4. Register every frame to a shared scale/anchor (uniform scale from a
     reference frame's height; horizontal anchor = alpha-weighted
     centroid of the lower-body region; vertical anchor = feet baseline)
     so the character doesn't jitter frame to frame.
  5. Composite onto a supersampled canvas, re-threshold to remove
     LANCZOS antialiasing fringe, then reduce to the shipped size with a
     nearest-neighbor resize to keep hard pixel-art edges.
  6. Write frames + frame_rate into firmware/images/<ANIM_NAME>/.

Usage:
    python extract_sprites.py --source /path/to/SpriteSheet_Source.png
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

# ---- output identity -------------------------------------------------

# Flipper FAP asset naming convention: NAME_VARIANT_SIZE. The generated
# animation directory name becomes the compiled symbol `A_<dir name>`.
ANIM_NAME = "Mascot_bop_40x40"
TARGET_SIZE = 40           # shipped frame width/height, px
FRAME_RATE_FPS = 4         # within the requested 3-6 FPS "choppy" range

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / "firmware" / "images" / ANIM_NAME

# ---- pose selection ----------------------------------------------------

# (row, col) grid coordinates into the source sheet's auto-detected grid,
# in playback order. Chosen from FlipperPhunk_SideApp_SpriteSheet_Source.png
# (2048x2048 RGBA, 10 cols x 5 rows of populated cells, last row partial):
# an extended "down beat" pose, a bent-arm "up beat" accent, a transition
# back down, and a settled hold -- a short, obviously-moving bop loop
# rather than the sheet's full walk-cycle run.
SELECTED_FRAMES = [(2, 7), (3, 3), (3, 7), (4, 2)]

# ---- registration / supersampling constants ----------------------------

SUPER = TARGET_SIZE * 4          # supersample canvas: clean AA, then re-threshold
TARGET_CHAR_HEIGHT = SUPER - 16  # character height at supersample scale, with margin
BOTTOM_MARGIN = 6                # supersample px between feet baseline and canvas edge

# skin/highlight color heuristics (see README.md "Monochrome conversion")
SKIN_R_MIN, SKIN_G_MIN, SKIN_G_MAX = 170, 110, 215
SKIN_B_MIN, SKIN_B_MAX = 90, 190
SKIN_RB_MIN_DIFF = 25
WHITE_FABRIC_MIN = 210
WHITE_FABRIC_MAX_SAT = 40

MORPH_CLOSE_KERNEL = 11
MORPH_CLOSE_ITER = 2
MORPH_OPEN_KERNEL = 3
MIN_HIGHLIGHT_AREA_FRAC = 0.01  # drop connected highlight specks smaller than this


# ---- grid detection (reproducible from the source alone) ---------------

def _bands(idxs, gap):
    """Group sorted indices into contiguous runs, tolerating small gaps."""
    idxs = sorted(idxs)
    out = []
    start = prev = idxs[0]
    for i in idxs[1:]:
        if i - prev > gap:
            out.append((start, prev))
            start = i
        prev = i
    out.append((start, prev))
    return out


def build_cellmap(alpha):
    """Detect the sheet's row/col grid from alpha coverage and return
    {(row, col): (x0, y0, x1, y1)} tight bounding boxes per cell."""
    row_idx = np.where(alpha.sum(axis=1) > 0)[0]
    row_bands = _bands(row_idx, gap=2)
    cellmap = {}
    for ri, (y0, y1) in enumerate(row_bands):
        sub = alpha[y0:y1 + 1, :]
        col_idx = np.where(sub.sum(axis=0) > 0)[0]
        col_bands = _bands(col_idx, gap=3)
        for ci, (x0, x1) in enumerate(col_bands):
            region = alpha[y0:y1 + 1, x0:x1 + 1]
            ys, xs = np.where(region > 0)
            ty0, ty1 = int(ys.min() + y0), int(ys.max() + y0)
            tx0, tx1 = int(xs.min() + x0), int(xs.max() + x0)
            cellmap[(ri, ci)] = (tx0, ty0, tx1, ty1)
    return cellmap


# ---- monochrome classification -----------------------------------------

def skin_mask(rgba):
    """Pixels that should render as a light highlight: skin tone, plus
    near-white low-saturation fabric (shirt/shoe trim)."""
    a = rgba.astype(np.int16)
    r, g, b, al = a[:, :, 0], a[:, :, 1], a[:, :, 2], a[:, :, 3]
    skin = (
        (al > 10) & (r > SKIN_R_MIN) & (g > SKIN_G_MIN) & (g < SKIN_G_MAX) &
        (b > SKIN_B_MIN) & (b < SKIN_B_MAX) & (r > g) & (g >= b - 10) &
        (r - b > SKIN_RB_MIN_DIFF)
    )
    mx = a[:, :, :3].max(axis=2)
    mn = a[:, :, :3].min(axis=2)
    sat = mx - mn
    white_fabric = (al > 10) & (mx > WHITE_FABRIC_MIN) & (sat < WHITE_FABRIC_MAX_SAT)
    return skin | white_fabric


def clean_highlight_mask(mask):
    """Morphologically close the raw highlight mask into solid blobs
    (bridging linework gaps like eyes/nose/knuckles) and drop specks
    below the area threshold, so the shipped asset shows clean light
    patches instead of a noisy dither cloud."""
    closed = ndimage.binary_closing(
        mask, structure=np.ones((MORPH_CLOSE_KERNEL, MORPH_CLOSE_KERNEL)),
        iterations=MORPH_CLOSE_ITER)
    closed = ndimage.binary_fill_holes(closed)
    closed = ndimage.binary_opening(
        closed, structure=np.ones((MORPH_OPEN_KERNEL, MORPH_OPEN_KERNEL)))
    labeled, n = ndimage.label(closed)
    if n == 0:
        return closed
    min_area = mask.size * MIN_HIGHLIGHT_AREA_FRAC
    keep = np.zeros_like(closed)
    for i in range(1, n + 1):
        comp = labeled == i
        if comp.sum() >= min_area:
            keep |= comp
    return keep


def classify_frame(rgba):
    """Reduce one cropped RGBA frame to an L-mode 0/255 image: opaque
    non-highlight pixels -> 0 (black silhouette); everything else
    (background + highlight) -> 255 (white)."""
    alpha = rgba[:, :, 3]
    highlight = clean_highlight_mask(skin_mask(rgba))
    black = (alpha > 10) & (~highlight)
    return np.where(black, 0, 255).astype(np.uint8)


# ---- registration --------------------------------------------------------

def core_centroid_x(alpha, x0, y0, x1, y1):
    """Alpha-weighted horizontal centroid of the lower-body region (legs
    / hips), used as the horizontal registration anchor because it stays
    stable across poses where only the mic arm swings."""
    h = y1 - y0 + 1
    lower_y0 = y0 + int(h * 0.45)
    region = alpha[lower_y0:y1 + 1, x0:x1 + 1].astype(np.float64)
    xs = np.arange(x0, x1 + 1)
    weights = region.sum(axis=0)
    if weights.sum() == 0:
        return (x0 + x1) / 2.0
    return float((xs * weights).sum() / weights.sum())


# ---- main pipeline --------------------------------------------------------

def extract(source_path: Path, out_dir: Path, frames=SELECTED_FRAMES,
            target_size=TARGET_SIZE, verbose=True):
    im = Image.open(source_path).convert("RGBA")
    full = np.array(im)
    alpha = full[:, :, 3]
    cellmap = build_cellmap(alpha)

    for key in frames:
        if key not in cellmap:
            raise ValueError(
                f"Selected frame {key} not found in detected grid "
                f"({len(cellmap)} cells: {sorted(cellmap)}). Source sheet "
                f"layout may have changed.")

    ref_bbox = cellmap[frames[0]]
    ref_h = ref_bbox[3] - ref_bbox[1] + 1
    scale = TARGET_CHAR_HEIGHT / ref_h

    canvas_anchor_x = SUPER / 2
    canvas_anchor_y = SUPER - BOTTOM_MARGIN

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for idx, key in enumerate(frames):
        x0, y0, x1, y1 = cellmap[key]
        crop_rgba = full[y0:y1 + 1, x0:x1 + 1]
        class_img = classify_frame(crop_rgba)
        class_pil = Image.fromarray(class_img, mode="L")

        w = max(1, round(class_pil.width * scale))
        h = max(1, round(class_pil.height * scale))
        class_scaled = class_pil.resize((w, h), Image.LANCZOS)

        anchor_x_src = core_centroid_x(alpha, x0, y0, x1, y1)
        anchor_y_src = y1  # feet baseline
        local_x = (anchor_x_src - x0) * scale
        local_y = (anchor_y_src - y0) * scale

        super_canvas = Image.new("L", (SUPER, SUPER), 255)
        px = round(canvas_anchor_x - local_x)
        py = round(canvas_anchor_y - local_y)
        super_canvas.paste(class_scaled, (px, py))

        # Re-threshold post-LANCZOS to strip antialiased gray fringe
        # before the final pixel-preserving reduction.
        bin_arr = np.where(np.array(super_canvas) < 128, 0, 255).astype(np.uint8)
        super_bin = Image.fromarray(bin_arr, mode="L")

        final = super_bin.resize((target_size, target_size), Image.NEAREST)
        final_1bit = final.convert("1", dither=Image.NONE)

        frame_path = out_dir / f"frame_{idx}.png"
        final_1bit.save(frame_path)
        written.append(frame_path)
        if verbose:
            black_px = int((np.array(final_1bit) == 0).sum())
            print(f"  frame_{idx}.png <- grid cell {key} "
                  f"({black_px}/{target_size * target_size} px black)")

    frame_rate_path = out_dir / "frame_rate"
    frame_rate_path.write_text(str(FRAME_RATE_FPS), newline="\n")
    written.append(frame_rate_path)

    if verbose:
        print(f"frame_rate = {FRAME_RATE_FPS}")
        print(f"wrote {len(frames)} frames + frame_rate to {out_dir}")
    return written


def validate(out_dir: Path, frames=SELECTED_FRAMES, target_size=TARGET_SIZE):
    """Sanity-check the generated asset directory before it's committed."""
    errors = []
    dims = set()
    for idx in range(len(frames)):
        p = out_dir / f"frame_{idx}.png"
        if not p.exists():
            errors.append(f"missing {p}")
            continue
        with Image.open(p) as im:
            dims.add(im.size)
            if im.mode not in ("1", "L"):
                errors.append(f"{p} is mode {im.mode}, expected 1-bit")
            elif im.mode == "L":
                vals = set(np.array(im).flatten().tolist())
                if not vals.issubset({0, 255}):
                    errors.append(f"{p} has non-binary pixel values: {sorted(vals)[:5]}...")
    if len(dims) > 1:
        errors.append(f"frame dimensions are not identical: {dims}")
    elif dims and next(iter(dims)) != (target_size, target_size):
        errors.append(f"frame dimensions {dims} != expected {(target_size, target_size)}")

    fr_path = out_dir / "frame_rate"
    if not fr_path.exists():
        errors.append("missing frame_rate file")
    else:
        text = fr_path.read_text().strip()
        if not (text.isdigit() and int(text) > 0):
            errors.append(f"frame_rate contents {text!r} is not a positive integer")

    if errors:
        raise AssertionError("Validation failed:\n  " + "\n  ".join(errors))
    print(f"Validation OK: {len(frames)} frames, all {target_size}x{target_size}, "
          f"1-bit, frame_rate={fr_path.read_text().strip()}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", required=True, type=Path,
        help="Path to the local copy of "
             "FlipperPhunk_SideApp_SpriteSheet_Source.png "
             "(2048x2048 RGBA; canonical copy lives in Drive, see README.md)")
    parser.add_argument(
        "--out", type=Path, default=DEFAULT_OUT_DIR,
        help=f"Output animation directory (default: {DEFAULT_OUT_DIR})")
    args = parser.parse_args()

    if not args.source.exists():
        raise SystemExit(f"Source sprite sheet not found: {args.source}")

    extract(args.source, args.out)
    validate(args.out)


if __name__ == "__main__":
    main()
