"""Create the simplified Rev C.1 bottom-silkscreen mascot assets.

Run with KiCad 10's bundled Python after installing opencv-python-headless.
The source PNG is preserved unchanged; this script thresholds its alpha channel,
applies a 0.25 mm morphological minimum feature, removes sub-feature specks, and
writes both an editable SVG and a KiCad compound-polygon footprint.
"""

from pathlib import Path
import xml.etree.ElementTree as ET

import cv2
import numpy as np
import pcbnew
from PIL import Image


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "FlipperPhunk_PCB_Silkscreen_Mascot_Concept.png"
SVG_OUT = HERE / "FlipperPhunk_PCB_Silkscreen_Mascot_Simplified.svg"
FOOTPRINT_OUT = (
    HERE.parent
    / "kicad"
    / "FlipperPhunk.pretty"
    / "FlipperPhunk_Mascot_BSilkscreen.kicad_mod"
)

ART_WIDTH_MM = 26.0
MIN_FEATURE_MM = 0.25
ALPHA_THRESHOLD = 64
SIMPLIFY_MM = 0.05
MIN_COMPONENT_AREA_MM2 = 0.06


def hierarchy_depth(hierarchy, index):
    depth = 0
    parent = hierarchy[index][3]
    while parent != -1:
        depth += 1
        parent = hierarchy[parent][3]
    return depth


def processed_mask():
    rgba = np.array(Image.open(SOURCE).convert("RGBA"))
    alpha = rgba[:, :, 3]
    px_per_mm = rgba.shape[1] / ART_WIDTH_MM
    mask = np.where(alpha >= ALPHA_THRESHOLD, 255, 0).astype(np.uint8)

    kernel_px = max(3, int(round(MIN_FEATURE_MM * px_per_mm)))
    if kernel_px % 2 == 0:
        kernel_px += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_px, kernel_px))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    min_area_px = MIN_COMPONENT_AREA_MM2 * px_per_mm * px_per_mm
    clean = np.zeros_like(mask)
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] >= min_area_px:
            clean[labels == label] = 255
    return clean, px_per_mm


def vector_contours(mask, px_per_mm):
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        raise RuntimeError("No mascot contours found")
    hierarchy = hierarchy[0]
    epsilon = SIMPLIFY_MM * px_per_mm
    result = []
    for index, contour in enumerate(contours):
        contour = cv2.approxPolyDP(contour, epsilon, True)
        if len(contour) < 3:
            continue
        points = [(float(p[0][0]) / px_per_mm, float(p[0][1]) / px_per_mm) for p in contour]
        result.append((index, hierarchy_depth(hierarchy, index), hierarchy[index][3], points))
    return result


def centered(contours, height_mm):
    return [
        (index, depth, parent, [(x - ART_WIDTH_MM / 2, y - height_mm / 2) for x, y in points])
        for index, depth, parent, points in contours
    ]


def write_svg(contours, height_mm):
    svg = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": f"{ART_WIDTH_MM:.3f}mm",
            "height": f"{height_mm:.3f}mm",
            "viewBox": f"0 0 {ART_WIDTH_MM:.6f} {height_mm:.6f}",
        },
    )
    ET.SubElement(
        svg,
        "metadata",
    ).text = (
        "FlipperPhunk Rev C.1 bottom-silkscreen derivative; alpha threshold 64, "
        "0.25 mm close/open minimum feature, 0.05 mm contour simplification."
    )
    path_data = []
    for _, _, _, points in contours:
        shifted = [(x + ART_WIDTH_MM / 2, y + height_mm / 2) for x, y in points]
        path_data.append("M " + " L ".join(f"{x:.6f},{y:.6f}" for x, y in shifted) + " Z")
    ET.SubElement(svg, "path", {"d": " ".join(path_data), "fill": "#000000", "fill-rule": "evenodd"})
    ET.indent(svg, space="  ")
    ET.ElementTree(svg).write(SVG_OUT, encoding="utf-8", xml_declaration=True)


def polygon(contour_points, holes):
    poly = pcbnew.SHAPE_POLY_SET()
    outline_index = poly.NewOutline()
    for x, y in contour_points:
        poly.Append(
            pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)),
            outline_index,
        )
    for hole in holes:
        hole_index = poly.NewHole(outline_index)
        for x, y in hole:
            poly.Append(
                pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)),
                outline_index,
                hole_index,
            )
    return poly


def write_footprint(contours):
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID("FlipperPhunk", "FlipperPhunk_Mascot_BSilkscreen"))
    fp.SetReference("LOGO?")
    fp.SetValue("FlipperPhunk mascot - simplified bottom silkscreen")
    fp.SetAttributes(pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)

    by_index = {index: (depth, parent, points) for index, depth, parent, points in contours}
    for index, (depth, _, points) in by_index.items():
        if depth % 2:
            continue
        holes = [
            child_points
            for _, (child_depth, child_parent, child_points) in by_index.items()
            if child_parent == index and child_depth == depth + 1
        ]
        shape = pcbnew.PCB_SHAPE(fp)
        shape.SetShape(pcbnew.SHAPE_T_POLY)
        shape.SetPolyShape(polygon(points, holes))
        shape.SetFilled(True)
        shape.SetWidth(0)
        shape.SetLayer(pcbnew.B_SilkS)
        fp.Add(shape)

    FOOTPRINT_OUT.parent.mkdir(parents=True, exist_ok=True)
    pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(str(FOOTPRINT_OUT.parent), fp)
    generated = FOOTPRINT_OUT.parent / f"{fp.GetFPID().GetLibItemName()}.kicad_mod"
    if generated != FOOTPRINT_OUT and generated.exists():
        generated.replace(FOOTPRINT_OUT)


def main():
    mask, px_per_mm = processed_mask()
    height_mm = mask.shape[0] / px_per_mm
    contours = centered(vector_contours(mask, px_per_mm), height_mm)
    write_svg(contours, height_mm)
    write_footprint(contours)
    print(f"Mascot: {ART_WIDTH_MM:.2f} x {height_mm:.2f} mm; {len(contours)} contours")
    print(f"SVG: {SVG_OUT}")
    print(f"Footprint: {FOOTPRINT_OUT}")


if __name__ == "__main__":
    main()
