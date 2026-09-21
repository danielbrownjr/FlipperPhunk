#!/usr/bin/env python3
"""Generate the Rev C.1 FDM mechanical fit-check from the canonical KiCad PCB.

The script makes a temporary copy of the PCB, increases only the requested
through-hole drill diameters, and asks KiCad CLI to export board-only STL and
STEP models.  The electrical PCB source is never modified.
"""

from __future__ import annotations

import argparse
import csv
import math
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
SOURCE_PCB = REPO_ROOT / "hardware" / "kicad" / "FlipperPhunk_RevC1.kicad_pcb"
OUTPUT_STL = SCRIPT_DIR / "FlipperPhunk_RevC1_FitCheck.stl"
OUTPUT_STEP = SCRIPT_DIR / "FlipperPhunk_RevC1_FitCheck.step"
OUTPUT_CSV = SCRIPT_DIR / "FlipperPhunk_RevC1_FitCheck_holes.csv"

DIAMETER_COMPENSATION_MM = 0.30
EXPECTED_BOARD_WIDTH_MM = 110.0
EXPECTED_BOARD_HEIGHT_MM = 60.0
EXPECTED_BOARD_THICKNESS_MM = 1.6
EXPECTED_HOLE_COUNT = 56
# KiCad's board-only exporter subtracts the default two copper foils and two
# soldermask layers (0.09 mm total) from the declared finished-board thickness.
# The temporary export copy adds that amount back so the printable solid itself
# is the canonical 1.60 mm thick; the source PCB remains unchanged.
KICAD_BOARD_ONLY_STACKUP_ADJUSTMENT_MM = 0.09

TARGET_FOOTPRINTS = {
    "MountingHole_3.2mm_M3",
    "Samtec_SSW-108-01-F-D",
    "Wurth_618009231121",
    "Wurth_618009231221",
    "Adafruit_5987_Socketed",
}


@dataclass(frozen=True)
class Hole:
    reference: str
    pad: str
    footprint: str
    pcb_x_mm: float
    pcb_y_mm: float
    original_diameter_mm: float

    @property
    def fitcheck_diameter_mm(self) -> float:
        return self.original_diameter_mm + DIAMETER_COMPENSATION_MM


def parenthesis_delta(line: str) -> int:
    """Count parentheses outside quoted KiCad strings."""
    delta = 0
    quoted = False
    escaped = False
    for char in line:
        if escaped:
            escaped = False
        elif char == "\\" and quoted:
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif not quoted and char == "(":
            delta += 1
        elif not quoted and char == ")":
            delta -= 1
    return delta


def balanced_blocks(lines: list[str], prefix: str) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        if lines[index].lstrip().startswith(prefix):
            start = index
            depth = 0
            while index < len(lines):
                depth += parenthesis_delta(lines[index])
                if depth == 0:
                    blocks.append((start, index + 1))
                    break
                index += 1
        index += 1
    return blocks


def first_match(pattern: str, text: str, description: str) -> re.Match[str]:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not find {description}")
    return match


def parse_at(text: str, top_indent: str) -> tuple[float, float, float]:
    match = first_match(
        rf"^{re.escape(top_indent)}\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)",
        text,
        "placement",
    )
    return float(match.group(1)), float(match.group(2)), float(match.group(3) or 0.0)


def parse_holes(lines: list[str]) -> list[Hole]:
    holes: list[Hole] = []
    for start, end in balanced_blocks(lines, "(footprint "):
        block_lines = lines[start:end]
        block = "".join(block_lines)
        name_match = re.match(r'\s*\(footprint\s+"([^"]+)"', block_lines[0])
        if not name_match or name_match.group(1) not in TARGET_FOOTPRINTS:
            continue
        footprint = name_match.group(1)
        reference = first_match(
            r'^\s*\(property\s+"Reference"\s+"([^"]+)"', block, "footprint reference"
        ).group(1)
        fx, fy, rotation = parse_at(block, "\t\t")
        radians = math.radians(rotation)
        cosine, sine = math.cos(radians), math.sin(radians)

        for pad_start, pad_end in balanced_blocks(block_lines, "(pad "):
            pad_lines = block_lines[pad_start:pad_end]
            pad_block = "".join(pad_lines)
            drill_match = re.search(r"^\s*\(drill\s+([\d.]+)\)\s*$", pad_block, re.MULTILINE)
            if not drill_match:
                raise RuntimeError(f"Non-circular or missing drill in {reference}")
            pad_match = re.match(r'\s*\(pad\s+"([^"]*)"', pad_lines[0])
            if not pad_match:
                raise RuntimeError(f"Could not parse pad name in {reference}")
            px, py, _ = parse_at(pad_block, "\t\t\t")
            absolute_x = fx + px * cosine - py * sine
            absolute_y = fy + px * sine + py * cosine
            holes.append(
                Hole(
                    reference=reference,
                    pad=pad_match.group(1) or "NPTH",
                    footprint=footprint,
                    pcb_x_mm=round(absolute_x, 6),
                    pcb_y_mm=round(absolute_y, 6),
                    original_diameter_mm=float(drill_match.group(1)),
                )
            )
    return sorted(holes, key=lambda h: (h.reference, h.pad, h.pcb_x_mm, h.pcb_y_mm))


def parse_board_geometry(lines: list[str]) -> tuple[float, float, float, float, float]:
    text = "".join(lines)
    thickness = float(first_match(r"\(thickness\s+([\d.]+)\)", text, "board thickness").group(1))
    edge_points: list[tuple[float, float]] = []
    for start, end in balanced_blocks(lines, "(gr_line"):
        block = "".join(lines[start:end])
        if '(layer "Edge.Cuts")' not in block:
            continue
        for key in ("start", "end"):
            match = first_match(rf"\({key}\s+([-\d.]+)\s+([-\d.]+)\)", block, f"Edge.Cuts {key}")
            edge_points.append((float(match.group(1)), float(match.group(2))))
    if len(edge_points) != 8:
        raise RuntimeError(f"Expected four straight Edge.Cuts segments, found {len(edge_points) // 2}")
    xs, ys = zip(*edge_points)
    return min(xs), min(ys), max(xs), max(ys), thickness


def compensated_copy(lines: list[str]) -> list[str]:
    output = list(lines)
    thickness_replacements = 0
    for index, line in enumerate(output):
        match = re.match(r"(\t\t\(thickness\s+)([\d.]+)(\)\s*)$", line)
        if match:
            export_thickness = float(match.group(2)) + KICAD_BOARD_ONLY_STACKUP_ADJUSTMENT_MM
            output[index] = f"{match.group(1)}{export_thickness:.2f}{match.group(3)}\n"
            thickness_replacements += 1
    if thickness_replacements != 1:
        raise RuntimeError(f"Expected one board thickness field, found {thickness_replacements}")

    for start, end in balanced_blocks(lines, "(footprint "):
        name_match = re.match(r'\s*\(footprint\s+"([^"]+)"', lines[start])
        if not name_match or name_match.group(1) not in TARGET_FOOTPRINTS:
            continue
        for index in range(start, end):
            match = re.match(r"(\s*\(drill\s+)([\d.]+)(\)\s*)$", output[index])
            if match:
                compensated = float(match.group(2)) + DIAMETER_COMPENSATION_MM
                output[index] = f"{match.group(1)}{compensated:.2f}{match.group(3)}\n"
    return output


def find_kicad_cli(explicit: str | None) -> str:
    candidates = [
        explicit,
        shutil.which("kicad-cli"),
        r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    raise RuntimeError("KiCad CLI 10 was not found; pass --kicad-cli PATH")


def export_model(kicad_cli: str, kind: str, source: Path, destination: Path) -> None:
    command = [
        kicad_cli,
        "pcb",
        "export",
        kind,
        "--force",
        "--board-only",
        "--user-origin",
        "20x20mm",
        "--output",
        str(destination),
        str(source),
    ]
    subprocess.run(command, check=True)


def normalize_text_export(path: Path) -> None:
    """Remove exporter-only trailing blanks without changing model geometry."""
    content = path.read_text(encoding="utf-8")
    path.write_text("\n".join(line.rstrip() for line in content.splitlines()) + "\n", encoding="utf-8", newline="\n")


def write_manifest(holes: list[Hole], origin_x: float, origin_y: float) -> None:
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "reference",
                "pad",
                "footprint",
                "pcb_x_mm",
                "pcb_y_mm",
                "model_x_mm",
                "model_y_mm",
                "original_diameter_mm",
                "fitcheck_diameter_mm",
                "diameter_compensation_mm",
            ]
        )
        for hole in holes:
            writer.writerow(
                [
                    hole.reference,
                    hole.pad,
                    hole.footprint,
                    f"{hole.pcb_x_mm:.3f}",
                    f"{hole.pcb_y_mm:.3f}",
                    f"{hole.pcb_x_mm - origin_x:.3f}",
                    f"{-(hole.pcb_y_mm - origin_y):.3f}",
                    f"{hole.original_diameter_mm:.2f}",
                    f"{hole.fitcheck_diameter_mm:.2f}",
                    f"{DIAMETER_COMPENSATION_MM:.2f}",
                ]
            )


def validate_stl(path: Path) -> None:
    try:
        import trimesh
    except ImportError:
        print("trimesh unavailable; skipped mesh topology validation")
        return
    mesh = trimesh.load_mesh(path, process=True)
    extents = sorted(float(value) for value in mesh.extents)
    expected = sorted([EXPECTED_BOARD_WIDTH_MM, EXPECTED_BOARD_HEIGHT_MM, EXPECTED_BOARD_THICKNESS_MM])
    if any(abs(actual - wanted) > 0.02 for actual, wanted in zip(extents, expected)):
        raise RuntimeError(f"Unexpected STL extents {mesh.extents}; expected 110 x 60 x 1.6 mm")
    if not mesh.is_watertight:
        raise RuntimeError("STL is not watertight")
    expected_euler = 2 - 2 * EXPECTED_HOLE_COUNT
    if mesh.euler_number != expected_euler:
        raise RuntimeError(
            f"STL Euler number {mesh.euler_number}; expected {expected_euler} for {EXPECTED_HOLE_COUNT} holes"
        )
    print(f"STL validation: extents={mesh.extents}, watertight=yes, holes={EXPECTED_HOLE_COUNT}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kicad-cli", help="Path to KiCad 10 kicad-cli executable")
    arguments = parser.parse_args()

    source_lines = SOURCE_PCB.read_text(encoding="utf-8").splitlines(keepends=True)
    min_x, min_y, max_x, max_y, thickness = parse_board_geometry(source_lines)
    width, height = max_x - min_x, max_y - min_y
    assert math.isclose(width, EXPECTED_BOARD_WIDTH_MM, abs_tol=1e-9)
    assert math.isclose(height, EXPECTED_BOARD_HEIGHT_MM, abs_tol=1e-9)
    assert math.isclose(thickness, EXPECTED_BOARD_THICKNESS_MM, abs_tol=1e-9)

    source_holes = parse_holes(source_lines)
    if len(source_holes) != EXPECTED_HOLE_COUNT:
        raise RuntimeError(f"Expected {EXPECTED_HOLE_COUNT} fit-check holes, found {len(source_holes)}")

    modified_lines = compensated_copy(source_lines)
    modified_holes = parse_holes(modified_lines)
    for original, modified in zip(source_holes, modified_holes):
        if (original.reference, original.pad, original.pcb_x_mm, original.pcb_y_mm) != (
            modified.reference,
            modified.pad,
            modified.pcb_x_mm,
            modified.pcb_y_mm,
        ):
            raise RuntimeError("Hole-center regression detected")
        if not math.isclose(
            modified.original_diameter_mm,
            original.fitcheck_diameter_mm,
            abs_tol=1e-9,
        ):
            raise RuntimeError("Hole-diameter compensation regression detected")

    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    write_manifest(source_holes, min_x, min_y)
    kicad_cli = find_kicad_cli(arguments.kicad_cli)
    with tempfile.TemporaryDirectory(prefix="flipperphunk-fitcheck-") as temporary:
        temporary_pcb = Path(temporary) / "FlipperPhunk_RevC1_FitCheck.kicad_pcb"
        temporary_pcb.write_text("".join(modified_lines), encoding="utf-8")
        export_model(kicad_cli, "stl", temporary_pcb, OUTPUT_STL)
        export_model(kicad_cli, "step", temporary_pcb, OUTPUT_STEP)
        normalize_text_export(OUTPUT_STL)
        normalize_text_export(OUTPUT_STEP)

    validate_stl(OUTPUT_STL)
    print(f"Board validation: {width:.2f} x {height:.2f} x {thickness:.2f} mm")
    print(f"Hole validation: {len(source_holes)} centers unchanged; +{DIAMETER_COMPENSATION_MM:.2f} mm diameter")
    print(f"Generated {OUTPUT_STL.name}, {OUTPUT_STEP.name}, and {OUTPUT_CSV.name}")


if __name__ == "__main__":
    main()
