"""Generate the FlipperPhunk Rev C.1 KiCad board and legacy capture source.

Run with the Python bundled with KiCad 10.0, then upgrade the generated legacy
schematic with kicad-cli.  The committed modern KiCad files are the deliverable;
this script documents the placement, net assignment, and source dimensions.
"""

from pathlib import Path
from copy import deepcopy
import math
import pcbnew
import uuid
import heapq


ROOT = Path(__file__).resolve().parent
PROJECT = "FlipperPhunk_RevC1"
MM = pcbnew.FromMM


NETS = {
    "GND": [("J1", "8"), ("J1", "11"), ("J2", "5"), ("J3", "5"), ("A1", "5")],
    "+3V3": [("J1", "9"), ("A1", "6")],
    "HOST_RXD": [("J2", "2"), ("A1", "7")],
    "HOST_TXD": [("J2", "3"), ("A1", "8")],
    "INST_TXD_TO_DCE": [("J3", "3"), ("A1", "9")],
    "INST_RXD_FROM_DCE": [("J3", "2"), ("A1", "10")],
    "USART_TX": [("J1", "13"), ("A1", "1")],
    "USART_RX": [("J1", "14"), ("A1", "2")],
    "LPUART_TX": [("J1", "15"), ("A1", "3")],
    "LPUART_RX": [("J1", "16"), ("A1", "4")],
    "DCD_PASS": [("J2", "1"), ("J3", "1")],
    "DTR_PASS": [("J2", "4"), ("J3", "4")],
    "DSR_PASS": [("J2", "6"), ("J3", "6")],
    "RTS_PASS": [("J2", "7"), ("J3", "7")],
    "CTS_PASS": [("J2", "8"), ("J3", "8")],
    "RI_PASS": [("J2", "9"), ("J3", "9")],
}


# Canonical schematic-symbol pin offsets in legacy KiCad mils. Both the
# generated legacy library/schematic and the modern schematic path derive their
# pin positions from this table so their geometry cannot drift independently.
SCHEMATIC_PIN_OFFSETS = {
    "FLIPPER_HEADER": {
        **{str(i): (-500, 700 - (i - 1) * 200) for i in range(1, 9)},
        **{str(i): (500, 700 - (i - 9) * 200) for i in range(9, 17)},
    },
    "ADAFRUIT_5987": {
        **{str(i): (-600, 500 - (i - 1) * 200) for i in range(1, 7)},
        **{str(i): (600, 500 - (i - 7) * 200) for i in range(7, 13)},
    },
    "DSUB9_SHELL": {
        **{str(i): (-500, 800 - (i - 1) * 200) for i in range(1, 10)},
        "S1": (500, 200),
        "S2": (500, -200),
    },
}


PIN_NETS = {
    ref: {pin: net for net, endpoints in NETS.items() for endpoint_ref, pin in endpoints if endpoint_ref == ref}
    for ref in ("J1", "A1", "J2", "J3")
}


def v(x, y):
    return pcbnew.VECTOR2I(MM(x), MM(y))


def add_line(parent, start, end, layer, width=0.15):
    shape = pcbnew.PCB_SHAPE(parent)
    shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
    shape.SetStart(v(*start))
    shape.SetEnd(v(*end))
    shape.SetLayer(layer)
    shape.SetWidth(MM(width))
    parent.Add(shape)
    return shape


def add_rect(parent, p1, p2, layer, width=0.15):
    x1, y1 = p1
    x2, y2 = p2
    add_line(parent, (x1, y1), (x2, y1), layer, width)
    add_line(parent, (x2, y1), (x2, y2), layer, width)
    add_line(parent, (x2, y2), (x1, y2), layer, width)
    add_line(parent, (x1, y2), (x1, y1), layer, width)


def add_arc(parent, start, mid, end, layer, width=0.15):
    shape = pcbnew.PCB_SHAPE(parent)
    shape.SetShape(pcbnew.SHAPE_T_ARC)
    shape.SetArcGeometry(v(*start), v(*mid), v(*end))
    shape.SetLayer(layer)
    shape.SetWidth(MM(width))
    parent.Add(shape)
    return shape


def add_pad(fp, number, at, drill, size, square=False, npth=False):
    pad = pcbnew.PAD(fp)
    pad.SetNumber(str(number))
    pad.SetPosition(v(*at))
    pad.SetSize(v(size, size))
    pad.SetDrillSize(v(drill, drill))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH if npth else pcbnew.PAD_ATTRIB_PTH)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT if square else pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetLayerSet(pad.UnplatedHoleMask() if npth else pad.PTHMask())
    fp.Add(pad)
    return pad


def set_fp_text(fp, ref_at, value_at):
    fp.Reference().SetPosition(v(*ref_at))
    fp.Reference().SetLayer(pcbnew.F_SilkS)
    fp.Reference().SetTextSize(v(1.0, 1.0))
    fp.Reference().SetTextThickness(MM(0.15))
    fp.Value().SetPosition(v(*value_at))
    fp.Value().SetLayer(pcbnew.F_Fab)
    fp.Value().SetVisible(False)


def make_j1():
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID("FlipperPhunk", "Samtec_SSW-108-01-F-D"))
    fp.SetReference("REF**")
    fp.SetValue("Samtec SSW-108-01-F-D")
    fp.SetAttributes(pcbnew.FP_THROUGH_HOLE)
    set_fp_text(fp, (1.27, -2.4), (1.27, 20.2))
    for row in range(8):
        y = row * 2.54
        add_pad(fp, row * 2 + 1, (0, y), 1.02, 1.75, square=(row == 0))
        add_pad(fp, row * 2 + 2, (2.54, y), 1.02, 1.75)
    add_rect(fp, (-1.27, -1.27), (3.81, 19.05), pcbnew.F_SilkS, 0.20)
    add_rect(fp, (-1.52, -1.52), (4.06, 19.30), pcbnew.F_CrtYd, 0.05)
    add_rect(fp, (-1.27, -1.27), (3.81, 19.05), pcbnew.F_Fab, 0.10)
    add_line(fp, (-1.27, -1.27), (-0.20, -1.27), pcbnew.F_SilkS, 0.35)
    return fp


def make_a1():
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID("FlipperPhunk", "Adafruit_5987_Socketed"))
    fp.SetReference("REF**")
    fp.SetValue("Adafruit 5987 on 2x Samtec SSW-106-01-G-S")
    fp.SetAttributes(pcbnew.FP_THROUGH_HOLE)
    set_fp_text(fp, (0, -11.6), (0, 11.6))
    ys = [6.35, 3.81, 1.27, -1.27, -3.81, -6.35]
    for idx, y in enumerate(ys, 1):
        add_pad(fp, idx, (-6.35, y), 1.00, 1.78, square=(idx == 1))
        add_pad(fp, idx + 6, (6.35, y), 1.00, 1.78, square=(idx == 1))
    # Matching carrier holes for optional M2.5 standoffs through the module.
    add_pad(fp, "", (0, -7.62), 2.70, 2.70, npth=True)
    add_pad(fp, "", (0, 7.62), 2.70, 2.70, npth=True)
    # Verified 17.78 x 20.32 mm rounded module outline, R2.54.
    x, y, r = 8.89, 10.16, 2.54
    for layer, width in ((pcbnew.F_Fab, 0.10), (pcbnew.F_SilkS, 0.20)):
        add_line(fp, (-x + r, -y), (x - r, -y), layer, width)
        add_line(fp, (x, -y + r), (x, y - r), layer, width)
        add_line(fp, (x - r, y), (-x + r, y), layer, width)
        add_line(fp, (-x, y - r), (-x, -y + r), layer, width)
        add_arc(fp, (-x + r, -y), (-x + 0.744, -y + 0.744), (-x, -y + r), layer, width)
        add_arc(fp, (x, -y + r), (x - 0.744, -y + 0.744), (x - r, -y), layer, width)
        add_arc(fp, (x - r, y), (x - 0.744, y - 0.744), (x, y - r), layer, width)
        add_arc(fp, (-x, y - r), (-x + 0.744, y - 0.744), (-x + r, y), layer, width)
    add_rect(fp, (-9.39, -10.66), (9.39, 10.66), pcbnew.F_CrtYd, 0.05)
    # Visible pin-one/orientation cue at T1IN.
    add_line(fp, (-8.5, 6.9), (-7.5, 6.9), pcbnew.F_SilkS, 0.35)
    add_line(fp, (-8.5, 6.9), (-8.5, 5.9), pcbnew.F_SilkS, 0.35)
    return fp


def make_dsub(part, female):
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID("FlipperPhunk", f"Wurth_{part}"))
    fp.SetReference("REF**")
    fp.SetValue(f"Wurth {part}")
    fp.SetAttributes(pcbnew.FP_THROUGH_HOLE)
    if female:
        set_fp_text(fp, (7.72, -11.0), (7.72, 22.5))
        for n in range(1, 6):
            add_pad(fp, n, (0, (n - 1) * 2.77), 1.09, 1.65, square=(n == 1))
        for n in range(6, 10):
            add_pad(fp, n, (2.84, 1.385 + (n - 6) * 2.77), 1.09, 1.65)
        add_pad(fp, "S1", (1.42, 18.04), 3.20, 4.80)
        add_pad(fp, "S2", (1.42, -6.96), 3.20, 4.80)
        # The full body crosses the board edge by design; keep it on Fab so DRC
        # does not treat the intentional connector overhang as clipped silk.
        add_rect(fp, (-1.59, -9.97), (10.95, 21.05), pcbnew.F_Fab, 0.12)
        add_rect(fp, (-1.98, -10.36), (17.42, 21.44), pcbnew.F_CrtYd, 0.05)
        add_rect(fp, (-1.48, -9.86), (10.84, 20.94), pcbnew.F_Fab, 0.10)
        add_rect(fp, (10.84, -9.86), (16.92, 20.94), pcbnew.F_Fab, 0.10)
        add_line(fp, (-2.065, -0.825), (-2.065, 0.825), pcbnew.F_SilkS, 0.20)
    else:
        set_fp_text(fp, (5.54, -2.78), (5.54, 18.5))
        for n in range(1, 6):
            add_pad(fp, n, ((n - 1) * 2.77, 0), 1.04, 1.55, square=(n == 1))
        for n in range(6, 10):
            add_pad(fp, n, (1.385 + (n - 6) * 2.77, 2.84), 1.04, 1.55)
        add_pad(fp, "S1", (-6.96, 1.42), 3.20, 4.80)
        add_pad(fp, "S2", (18.04, 1.42), 3.20, 4.80)
        add_rect(fp, (-9.97, -1.59), (21.05, 10.95), pcbnew.F_Fab, 0.12)
        add_rect(fp, (-10.36, -1.98), (21.44, 17.42), pcbnew.F_CrtYd, 0.05)
        add_rect(fp, (-9.86, -1.48), (20.94, 10.84), pcbnew.F_Fab, 0.10)
        add_rect(fp, (-9.86, 10.84), (20.94, 16.92), pcbnew.F_Fab, 0.10)
        add_line(fp, (-0.775, -2.065), (0.775, -2.065), pcbnew.F_SilkS, 0.20)
    return fp


def make_mounting_hole():
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID("FlipperPhunk", "MountingHole_3.2mm_M3"))
    fp.SetReference("H?")
    fp.SetValue("M3 mounting hole")
    fp.SetAttributes(pcbnew.FP_BOARD_ONLY | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)
    add_pad(fp, "", (0, 0), 3.20, 3.20, npth=True)
    circle = pcbnew.PCB_SHAPE(fp)
    circle.SetShape(pcbnew.SHAPE_T_CIRCLE)
    circle.SetCenter(v(0, 0))
    circle.SetEnd(v(2.8, 0))
    circle.SetLayer(pcbnew.F_CrtYd)
    circle.SetWidth(MM(0.05))
    fp.Add(circle)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)
    return fp


def save_footprints():
    lib = ROOT / "FlipperPhunk.pretty"
    lib.mkdir(parents=True, exist_ok=True)
    fps = [
        (make_j1(), "Samtec_SSW-108-01-F-D"),
        (make_a1(), "Adafruit_5987_Socketed"),
        (make_dsub("618009231121", True), "Wurth_618009231121"),
        (make_dsub("618009231221", False), "Wurth_618009231221"),
        (make_mounting_hole(), "MountingHole_3.2mm_M3"),
    ]
    plugin = pcbnew.PCB_IO_KICAD_SEXPR()
    for fp, name in fps:
        plugin.FootprintSave(str(lib), fp)
        generated = lib / f"{fp.GetFPID().GetLibItemName()}.kicad_mod"
        target = lib / f"{name}.kicad_mod"
        if generated != target and generated.exists():
            generated.replace(target)
    return lib


def clone_for_board(lib, name, ref, pos, rotation=0):
    fp = pcbnew.FootprintLoad(str(lib), name)
    fp.SetReference(ref)
    fp.SetPosition(v(*pos))
    fp.SetOrientationDegrees(rotation)
    fp.Reference().SetVisible(True)
    return fp


def board_text(board, text, pos, size=1.2, layer=pcbnew.F_SilkS, justify=None):
    item = pcbnew.PCB_TEXT(board)
    item.SetText(text)
    item.SetPosition(v(*pos))
    item.SetLayer(layer)
    item.SetTextSize(v(size, size))
    item.SetTextThickness(MM(max(0.15, size * 0.14)))
    if justify is not None:
        item.SetHorizJustify(justify)
    board.Add(item)
    return item


def add_track(board, net, start, end, layer=pcbnew.F_Cu, width=0.35):
    if start == end:
        return
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(v(*start))
    track.SetEnd(v(*end))
    track.SetWidth(MM(width))
    track.SetLayer(layer)
    track.SetNet(net)
    board.Add(track)


def add_via(board, net, at, diameter=0.90, drill=0.45):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(v(*at))
    via.SetWidth(MM(diameter))
    via.SetDrill(MM(drill))
    via.SetNet(net)
    board.Add(via)


def route_polyline(board, net, points, layer=pcbnew.F_Cu, width=0.35):
    for a, b in zip(points, points[1:]):
        add_track(board, net, a, b, layer, width)


def pmm(pad):
    p = pad.GetPosition()
    return (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))


def autoroute(board, footprints, netobjs):
    """Route the small two-layer board with a deterministic orthogonal A* router."""
    step = 0.25
    min_x, max_x, min_y, max_y = 21.5, 128.5, 21.5, 78.5
    width = 0.30
    clearance = 0.22
    via_diameter = 0.90
    via_drill = 0.45
    layers = (pcbnew.F_Cu, pcbnew.B_Cu)
    pads = [pad for fp in footprints.values() for pad in fp.Pads()]

    def cell(point):
        return (round((point[0] - min_x) / step), round((point[1] - min_y) / step))

    def point(c):
        return (min_x + c[0] * step, min_y + c[1] * step)

    nx = round((max_x - min_x) / step)
    ny = round((max_y - min_y) / step)
    pad_blocks = []
    pad_geometry = []
    for pad in pads:
        pos = pmm(pad)
        size = pad.GetSize()
        sx, sy = pcbnew.ToMM(size.x), pcbnew.ToMM(size.y)
        copper_radius = math.hypot(sx / 2, sy / 2) if pad.GetShape() == pcbnew.PAD_SHAPE_RECT else max(sx, sy) / 2
        radius = copper_radius + width / 2 + clearance
        if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            radius += 0.03
        pad_geometry.append((pad.GetNetname(), pos, copper_radius))
        blocked = set()
        cx, cy = cell(pos)
        reach = math.ceil(radius / step)
        for ix in range(max(0, cx - reach), min(nx, cx + reach) + 1):
            for iy in range(max(0, cy - reach), min(ny, cy + reach) + 1):
                px, py = point((ix, iy))
                if math.hypot(px - pos[0], py - pos[1]) < radius:
                    blocked.add((ix, iy))
        pad_blocks.append((pad.GetNetname(), blocked))

    occupied = {0: {}, 1: {}}
    via_occupied = {}

    def add_occ(mapping, key, net_name):
        mapping.setdefault(key, set()).add(net_name)

    def raster_segment(a, b, layer_idx, net_name):
        ax, ay = a
        bx, by = b
        ca, cb = cell(a), cell(b)
        radius = width + clearance
        reach = math.ceil(radius / step)
        length = max(abs(cb[0] - ca[0]), abs(cb[1] - ca[1]), 1)
        for n in range(length + 1):
            t = n / length
            ix = round(ca[0] + (cb[0] - ca[0]) * t)
            iy = round(ca[1] + (cb[1] - ca[1]) * t)
            for dx in range(-reach, reach + 1):
                for dy in range(-reach, reach + 1):
                    if math.hypot(dx * step, dy * step) <= radius:
                        add_occ(occupied[layer_idx], (ix + dx, iy + dy), net_name)

    def raster_via(at, net_name):
        c = cell(at)
        radius = via_diameter / 2 + width / 2 + clearance
        reach = math.ceil(radius / step)
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                if math.hypot(dx * step, dy * step) <= radius:
                    add_occ(via_occupied, (c[0] + dx, c[1] + dy), net_name)

    def blocked(c, layer_idx, net_name):
        ix, iy = c
        if ix < 0 or iy < 0 or ix > nx or iy > ny:
            return True
        for pad_net, block in pad_blocks:
            if pad_net != net_name and c in block:
                return True
        if any(owner != net_name for owner in occupied[layer_idx].get(c, ())):
            return True
        if any(owner != net_name for owner in via_occupied.get(c, ())):
            return True
        return False

    def can_via(c, net_name):
        px, py = point(c)
        via_radius = via_diameter / 2
        for pad_net, pos, pad_radius in pad_geometry:
            if pad_net != net_name and math.hypot(px - pos[0], py - pos[1]) < pad_radius + via_radius + clearance:
                return False
        reach = math.ceil((via_radius + width / 2 + clearance) / step)
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                if math.hypot(dx * step, dy * step) > via_radius + width / 2 + clearance:
                    continue
                cc = (c[0] + dx, c[1] + dy)
                for li in (0, 1):
                    if any(owner != net_name for owner in occupied[li].get(cc, ())):
                        return False
                if any(owner != net_name for owner in via_occupied.get(cc, ())):
                    return False
        return True

    def find_path(start, goal, net_name):
        starts = [(cell(start)[0], cell(start)[1], li) for li in (0, 1)]
        goals = {(cell(goal)[0], cell(goal)[1], li) for li in (0, 1)}
        heap = []
        cost = {}
        parent = {}
        gx, gy = cell(goal)
        for s in starts:
            if not blocked((s[0], s[1]), s[2], net_name):
                cost[s] = 0
                parent[s] = None
                heapq.heappush(heap, (abs(s[0] - gx) + abs(s[1] - gy), 0, s))
        end = None
        while heap:
            _, g, state = heapq.heappop(heap)
            if g != cost.get(state):
                continue
            if state in goals:
                end = state
                break
            ix, iy, li = state
            neighbors = [(ix + 1, iy, li, 1), (ix - 1, iy, li, 1), (ix, iy + 1, li, 1), (ix, iy - 1, li, 1)]
            other = 1 - li
            # Vias are expensive enough that the router stays on one layer when practical.
            if not blocked((ix, iy), other, net_name) and can_via((ix, iy), net_name):
                neighbors.append((ix, iy, other, 12))
            for nx1, ny1, nl, delta in neighbors:
                if blocked((nx1, ny1), nl, net_name):
                    continue
                ns = (nx1, ny1, nl)
                ng = g + delta
                if ng < cost.get(ns, 10**12):
                    cost[ns] = ng
                    parent[ns] = state
                    h = abs(nx1 - gx) + abs(ny1 - gy) + (0 if nl in (0, 1) else 1)
                    heapq.heappush(heap, (ng + h, ng, ns))
        if end is None:
            raise RuntimeError(f"Autorouter failed for {net_name}: {start} -> {goal}")
        path = []
        while end is not None:
            path.append(end)
            end = parent[end]
        return list(reversed(path))

    route_order = [
        "GND",
        "+3V3",
        "USART_RX", "USART_TX", "LPUART_RX", "LPUART_TX",
        "HOST_RXD", "HOST_TXD", "INST_TXD_TO_DCE", "INST_RXD_FROM_DCE",
        "DCD_PASS", "DTR_PASS", "DSR_PASS", "RTS_PASS", "CTS_PASS", "RI_PASS",
    ]
    pad_lookup = {(ref, pad.GetNumber()): pad for ref, fp in footprints.items() for pad in fp.Pads()}
    for net_name in route_order:
        endpoints = [pmm(pad_lookup[key]) for key in NETS[net_name]]
        for start, goal in zip(endpoints[1:], [endpoints[0]] * (len(endpoints) - 1)):
            path = find_path(start, goal, net_name)
            net = netobjs[net_name]
            # Connect exact pad centres to the grid path.
            first = point((path[0][0], path[0][1]))
            add_track(board, net, start, first, layers[path[0][2]], width)
            raster_segment(start, first, path[0][2], net_name)
            segment_start = path[0]
            previous = path[0]
            direction = None
            for current in path[1:]:
                if current[2] != previous[2]:
                    a = point((segment_start[0], segment_start[1]))
                    b = point((previous[0], previous[1]))
                    add_track(board, net, a, b, layers[previous[2]], width)
                    raster_segment(a, b, previous[2], net_name)
                    at = point((current[0], current[1]))
                    add_via(board, net, at, via_diameter, via_drill)
                    raster_via(at, net_name)
                    segment_start = current
                    direction = None
                else:
                    new_direction = (current[0] - previous[0], current[1] - previous[1])
                    if direction is not None and new_direction != direction:
                        a = point((segment_start[0], segment_start[1]))
                        b = point((previous[0], previous[1]))
                        add_track(board, net, a, b, layers[previous[2]], width)
                        raster_segment(a, b, previous[2], net_name)
                        segment_start = previous
                    direction = new_direction
                previous = current
            a = point((segment_start[0], segment_start[1]))
            b = point((previous[0], previous[1]))
            add_track(board, net, a, b, layers[previous[2]], width)
            raster_segment(a, b, previous[2], net_name)
            add_track(board, net, b, goal, layers[previous[2]], width)
            raster_segment(b, goal, previous[2], net_name)


def add_ground_zone(board, net):
    zone = pcbnew.ZONE(board)
    zone.SetLayer(pcbnew.B_Cu)
    zone.SetNet(net)
    zone.SetLocalClearance(MM(0.25))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    outline = zone.Outline()
    outline.NewOutline()
    for x, y in ((21.0, 21.0), (129.0, 21.0), (129.0, 79.0), (21.0, 79.0)):
        outline.Append(MM(x), MM(y))
    board.Add(zone)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def build_board(lib):
    board = pcbnew.BOARD()
    board.GetDesignSettings().SetCopperLayerCount(2)
    # 110 x 60 mm carrier.
    for a, b in [((20, 20), (130, 20)), ((130, 20), (130, 80)), ((130, 80), (20, 80)), ((20, 80), (20, 20))]:
        add_line(board, a, b, pcbnew.Edge_Cuts, 0.10)

    placements = {
        "J2": ("Wurth_618009231121", (30.84, 55.54), 180),
        "J3": ("Wurth_618009231221", (119.16, 55.54), 270),
        "J1": ("Samtec_SSW-108-01-F-D", (84.0, 25.0), 90),
        "A1": ("Adafruit_5987_Socketed", (75.0, 53.0), 0),
    }
    footprints = {}
    for ref, (name, pos, rotation) in placements.items():
        fp = clone_for_board(lib, name, ref, pos, rotation)
        board.Add(fp)
        footprints[ref] = fp
    # Decorative artwork is a board-only B.SilkS footprint.  It has no pads or
    # copper and is deliberately kept out of the electrical footprint map.
    mascot = clone_for_board(lib, "FlipperPhunk_Mascot_BSilkscreen", "LOGO1", (53.0, 52.5))
    mascot.Reference().SetVisible(False)
    mascot.Value().SetVisible(False)
    board.Add(mascot)
    for ref, pos in (("H1", (24, 24)), ("H2", (126, 24)), ("H3", (24, 76)), ("H4", (126, 76))):
        fp = clone_for_board(lib, "MountingHole_3.2mm_M3", ref, pos)
        fp.Reference().SetVisible(False)
        board.Add(fp)

    netobjs = {}
    for name in NETS:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
        netobjs[name] = net
    for name, endpoints in NETS.items():
        for ref, num in endpoints:
            pad = footprints[ref].FindPadByNumber(num)
            if pad is None:
                raise RuntimeError(f"Missing {ref}.{num}")
            pad.SetNet(netobjs[name])

    # Route each two-terminal signal through a dedicated channel.  The six
    # handshake lines remain plain copper: there are no 0-ohm links.
    pads = {(ref, pad.GetNumber()): pmm(pad) for ref, fp in footprints.items() for pad in fp.Pads()}
    handshake_lanes = {
        "DCD_PASS": 31.0,
        "DTR_PASS": 34.0,
        "DSR_PASS": 69.0,
        "RTS_PASS": 72.0,
        "CTS_PASS": 75.0,
        "RI_PASS": 78.0,
    }
    for idx, (name, lane) in enumerate(handshake_lanes.items()):
        a_ref, a_num = NETS[name][0]
        b_ref, b_num = NETS[name][1]
        a, b = pads[(a_ref, a_num)], pads[(b_ref, b_num)]
        # Alternate layers and use connector-side fanout X channels.
        layer = pcbnew.B_Cu if idx % 2 == 0 else pcbnew.F_Cu
        x1 = 42.0 + idx * 1.4
        x2 = 108.0 - idx * 1.4
        route_polyline(board, netobjs[name], [a, (x1, a[1]), (x1, lane), (x2, lane), (x2, b[1]), b], layer, 0.32)

    # RS-232 data paths from the edge connectors to A1.
    data_routes = {
        "HOST_RXD": [("J2", "2"), (48.0, 43.0), ("A1", "7")],
        "HOST_TXD": [("J2", "3"), (51.0, 47.0), ("A1", "8")],
        "INST_TXD_TO_DCE": [("J3", "3"), (101.0, 54.0), ("A1", "9")],
        "INST_RXD_FROM_DCE": [("J3", "2"), (104.0, 58.0), ("A1", "10")],
    }
    for idx, (name, spec) in enumerate(data_routes.items()):
        start = pads[spec[0]]
        end = pads[spec[2]]
        mid = spec[1]
        layer = pcbnew.F_Cu if idx % 2 == 0 else pcbnew.B_Cu
        route_polyline(board, netobjs[name], [start, (mid[0], start[1]), mid, (mid[0], end[1]), end], layer, 0.38)

    # TTL-side UARTs from J1 to the LV row of A1.
    uart_specs = {
        "USART_TX": ("13", "1", 57.0),
        "USART_RX": ("14", "2", 60.0),
        "LPUART_TX": ("15", "3", 63.0),
        "LPUART_RX": ("16", "4", 66.0),
    }
    for idx, (name, (jpin, apin, lane_x)) in enumerate(uart_specs.items()):
        a = pads[("J1", jpin)]
        b = pads[("A1", apin)]
        layer = pcbnew.F_Cu if idx < 2 else pcbnew.B_Cu
        route_polyline(board, netobjs[name], [a, (a[0], 38.0 + idx * 2), (lane_x, 38.0 + idx * 2), (lane_x, b[1]), b], layer, 0.32)

    # Power and a branched ground trunk.
    a = pads[("J1", "9")]
    b = pads[("A1", "6")]
    route_polyline(board, netobjs["+3V3"], [a, (80.0, a[1]), (80.0, b[1]), b], pcbnew.F_Cu, 0.60)
    gnd = netobjs["GND"]
    trunk_y = 64.5
    add_track(board, gnd, (45.0, trunk_y), (106.0, trunk_y), pcbnew.B_Cu, 0.80)
    for ref, pin, x in (("J2", "5", 45.0), ("J3", "5", 106.0), ("A1", "5", 68.65), ("J1", "8", 77.0), ("J1", "11", 80.0)):
        p = pads[(ref, pin)]
        route_polyline(board, gnd, [p, (x, p[1]), (x, trunk_y)], pcbnew.B_Cu, 0.65)

    # Replace the exploratory hand routes above with the deterministic router.
    for item in list(board.GetTracks()):
        board.Remove(item)
    autoroute(board, footprints, netobjs)
    add_ground_zone(board, netobjs["GND"])

    # Human-facing silkscreen and mechanical reservation notes.
    board_text(board, "FLIPPERPHUNK REV C.1", (75, 75.5), 1.4)
    board_text(board, "HOST / PC", (28.0, 70.0), 1.1)
    board_text(board, "INSTRUMENT", (113.0, 70.0), 1.1)
    board_text(board, "J1 FLIPPER", (92.0, 32.0), 1.0)
    board_text(board, "A1 ADAFRUIT 5987", (75.0, 39.5), 1.0)
    board_text(board, "PIN 1", (63.0, 62.5), 0.8)
    board_text(board, "SHELLS FLOAT", (75.0, 77.2), 0.9)
    board_text(board, "FUTURE PROTECTION", (45.0, 23.8), 0.8, pcbnew.Dwgs_User)
    board_text(board, "FUTURE PROTECTION", (108.0, 23.8), 0.8, pcbnew.Dwgs_User)
    add_rect(board, (34, 25.5), (55, 38.0), pcbnew.Dwgs_User, 0.15)
    add_rect(board, (98, 25.5), (119, 38.0), pcbnew.Dwgs_User, 0.15)
    board_text(board, "A1 MODULE / SOCKET CLEARANCE", (75, 42.8), 0.65, pcbnew.Dwgs_User)

    pcbnew.SaveBoard(str(ROOT / f"{PROJECT}.kicad_pcb"), board)
    return board


def legacy_lib_text():
    def pin(name, num, x, y, orient):
        return f"X {name} {num} {x} {y} 200 {orient} 45 45 1 1 P"

    out = ["EESchema-LIBRARY Version 2.4", "#encoding utf-8"]
    out += ["#", "# FLIPPER_HEADER", "#", "DEF FLIPPER_HEADER J 0 40 Y Y 1 F N", "F0 \"J\" 0 950 50 H V C CNN", "F1 \"FLIPPER_HEADER\" 0 -950 50 H V C CNN", "DRAW", "S -300 800 300 -800 0 1 10 f"]
    for number, (x, y) in SCHEMATIC_PIN_OFFSETS["FLIPPER_HEADER"].items():
        out.append(pin(number, number, x, y, "R" if x < 0 else "L"))
    out += ["ENDDRAW", "ENDDEF"]

    out += ["#", "# ADAFRUIT_5987", "#", "DEF ADAFRUIT_5987 A 0 40 Y Y 1 F N", "F0 \"A\" 0 850 50 H V C CNN", "F1 \"ADAFRUIT_5987\" 0 -850 50 H V C CNN", "DRAW", "S -400 650 400 -650 0 1 10 f"]
    left = ["T1IN", "R1OUT", "T2IN", "R2OUT", "GND", "VIN"]
    right = ["T1OUT", "R1IN", "T2OUT", "R2IN", "V-", "V+"]
    a1_names = {str(i): name for i, name in enumerate(left, 1)}
    a1_names.update({str(i): name for i, name in enumerate(right, 7)})
    for number, (x, y) in SCHEMATIC_PIN_OFFSETS["ADAFRUIT_5987"].items():
        out.append(pin(a1_names[number], number, x, y, "R" if x < 0 else "L"))
    out += ["ENDDRAW", "ENDDEF"]

    out += ["#", "# DSUB9_SHELL", "#", "DEF DSUB9_SHELL J 0 40 Y Y 1 F N", "F0 \"J\" 0 1100 50 H V C CNN", "F1 \"DSUB9_SHELL\" 0 -1200 50 H V C CNN", "DRAW", "S -300 950 300 -1050 0 1 10 f"]
    dsub_names = {**{str(i): str(i) for i in range(1, 10)}, "S1": "SHELL_A", "S2": "SHELL_B"}
    for number, (x, y) in SCHEMATIC_PIN_OFFSETS["DSUB9_SHELL"].items():
        out.append(pin(dsub_names[number], number, x, y, "R" if x < 0 else "L"))
    out += ["ENDDRAW", "ENDDEF", "#", "#End Library", ""]
    return "\n".join(out)


def component(lib, ref, value, footprint, x, y, uid):
    return f"""$Comp
L {lib} {ref}
U 1 1 {uid}
P {x} {y}
F 0 \"{ref}\" H {x} {y-1200} 50  0000 C CNN
F 1 \"{value}\" H {x} {y+1200} 50  0000 C CNN
F 2 \"{footprint}\" H {x} {y} 50  0001 C CNN
F 3 \"\" H {x} {y} 50  0001 C CNN
\t1    {x} {y}
\t1    0    0    -1
$EndComp"""


def build_legacy_schematic():
    (ROOT / f"{PROJECT}-cache.lib").write_text(legacy_lib_text(), encoding="utf-8")
    comps = [
        component(f"{PROJECT}-cache:FLIPPER_HEADER", "J1", "Samtec SSW-108-01-F-D", "FlipperPhunk:Samtec_SSW-108-01-F-D", 2100, 3900, "70000001"),
        component(f"{PROJECT}-cache:ADAFRUIT_5987", "A1", "Adafruit 5987 RS232 Pal", "FlipperPhunk:Adafruit_5987_Socketed", 5200, 3900, "70000002"),
        component(f"{PROJECT}-cache:DSUB9_SHELL", "J2", "HOST/PC FEMALE 618009231121", "FlipperPhunk:Wurth_618009231121", 8300, 2700, "70000003"),
        component(f"{PROJECT}-cache:DSUB9_SHELL", "J3", "INSTRUMENT MALE 618009231221", "FlipperPhunk:Wurth_618009231221", 8300, 5600, "70000004"),
    ]
    lines = [
        "EESchema Schematic File Version 4",
        f"LIBS:{PROJECT}-cache",
        "EELAYER 29 0",
        "EELAYER END",
        "$Descr A4 11693 8268",
        "encoding utf-8",
        "Sheet 1 1",
        'Title "FlipperPhunk Rev C.1 active dual-UART RS-232 bridge/logger"',
        'Date "2026-09-20"',
        'Rev "C.1"',
        'Comp "FlipperPhunk"',
        'Comment1 "Shell pads float; no ESD/TVS; no bypass; handshakes plain copper"',
        'Comment2 "Corrected J3 DCE mapping: pin 2 TX from instrument, pin 3 RX to instrument"',
        "$EndDescr",
        *comps,
    ]

    # Symbol pin coordinates and local net labels. Pin endpoints and label
    # direction come from the same geometry used to emit the symbol library.
    connections = []
    no_connects = []
    legacy_parts = {
        "J1": ("FLIPPER_HEADER", (2100, 3900)),
        "A1": ("ADAFRUIT_5987", (5200, 3900)),
        "J2": ("DSUB9_SHELL", (8300, 2700)),
        "J3": ("DSUB9_SHELL", (8300, 5600)),
    }
    for ref, (symbol_name, (cx, cy)) in legacy_parts.items():
        for pin_number, (dx, dy) in SCHEMATIC_PIN_OFFSETS[symbol_name].items():
            point = (cx + dx, cy + dy)
            net_name = PIN_NETS[ref].get(pin_number)
            if net_name is None:
                no_connects.append((point, None))
            else:
                connections.append((point, net_name, dx))

    for (x, y), name, pin_dx in connections:
        x2 = x - 250 if pin_dx < 0 else x + 250
        # Regression guard: every wire/label must extend away from its symbol.
        assert (x2 - x) * pin_dx > 0, f"Label for {name} points into its symbol"
        lines += [f"Wire Wire Line", f"\t{x} {y} {x2} {y}", f"Text Label {x2} {y} 0    45   ~ 0", name]
    for (x, y), _ in no_connects:
        lines.append(f"NoConn ~ {x} {y}")

    lines += [
        'Text Notes 1200 1200 0    90   ~ 18',
        'REV C.1 ACTIVE BRIDGE / LOGGER',
        'Text Notes 1200 1450 0    50   ~ 0',
        'J2 female faces HOST/PC (DTE); J3 male faces INSTRUMENT (DCE).',
        'Text Notes 1200 1600 0    50   ~ 0',
        'Handshake pins 1/4/6/7/8/9 are straight-through copper. Shell pads S1/S2 are NC/floating.',
        'Text Notes 1200 1750 0    50   ~ 0',
        'A1 V+ and V- are charge-pump nodes and are intentionally NC.',
        "$EndSCHEMATC",
        "",
    ]
    (ROOT / f"{PROJECT}.sch").write_text("\n".join(lines), encoding="utf-8")


def build_modern_schematic():
    """Build a native KiCad schematic using the converted custom symbol library."""
    from kiutils.schematic import Schematic
    from kiutils.symbol import SymbolLib
    from kiutils.items.common import Effects, Font, Position, Property, TitleBlock
    from kiutils.items.schitems import (
        Connection,
        LocalLabel,
        NoConnect,
        SchematicSymbol,
        SymbolProjectInstance,
        SymbolProjectPath,
        Text,
    )

    def uid():
        return str(uuid.uuid4())

    def effects(hidden=False, size=1.27):
        obj = Effects(font=Font(height=size, width=size))
        obj.hide = hidden
        return obj

    sym_path = ROOT / "FlipperPhunk.kicad_sym"
    if not sym_path.exists():
        raise RuntimeError(
            "Run kicad-cli sym upgrade on FlipperPhunk_RevC1-cache.lib first"
        )
    library = SymbolLib.from_file(str(sym_path), encoding="utf-8")
    by_name = {item.entryName: item for item in library.symbols}

    sch = Schematic.create_new()
    sch.uuid = uid()
    sch.titleBlock = TitleBlock(
        title="FlipperPhunk Rev C.1 active dual-UART RS-232 bridge/logger",
        date="2026-09-20",
        revision="C.1",
        company="FlipperPhunk",
        comments={
            1: "Corrected J3 DCE mapping: pin 2 TX from instrument, pin 3 RX to instrument",
            2: "Shell pads float; no ESD/TVS; no bypass; handshakes plain copper",
        },
    )

    for source in library.symbols:
        embedded = deepcopy(source)
        embedded.libraryNickname = "FlipperPhunk"
        sch.libSymbols.append(embedded)

    # Symbol positions in millimetres on an A4 landscape page.
    parts = {
        "J1": ("FLIPPER_HEADER", "Samtec SSW-108-01-F-D", "FlipperPhunk:Samtec_SSW-108-01-F-D", (60.96, 99.06)),
        "A1": ("ADAFRUIT_5987", "Adafruit 5987 RS232 Pal", "FlipperPhunk:Adafruit_5987_Socketed", (129.54, 99.06)),
        "J2": ("DSUB9_SHELL", "HOST/PC FEMALE 618009231121", "FlipperPhunk:Wurth_618009231121", (220.98, 60.96)),
        "J3": ("DSUB9_SHELL", "INSTRUMENT MALE 618009231221", "FlipperPhunk:Wurth_618009231221", (220.98, 144.78)),
    }

    # Derive modern millimetre offsets from the canonical legacy geometry.
    pin_offsets = {
        symbol_name: {
            number: (round(x * 0.0254, 3), round(y * 0.0254, 3))
            for number, (x, y) in offsets.items()
        }
        for symbol_name, offsets in SCHEMATIC_PIN_OFFSETS.items()
    }

    for ref, (lib_name, value, footprint, (x, y)) in parts.items():
        source = by_name[lib_name]
        symbol_uuid = uid()
        pin_numbers = list(pin_offsets[lib_name])
        symbol = SchematicSymbol(
            libraryNickname="FlipperPhunk",
            entryName=lib_name,
            position=Position(x, y, 0),
            unit=1,
            inBom=True,
            onBoard=True,
            uuid=symbol_uuid,
            pins={num: uid() for num in pin_numbers},
            properties=[
                Property(key="Reference", value=ref, position=Position(x, y - 23.0, 0), effects=effects()),
                Property(key="Value", value=value, position=Position(x, y + 23.0, 0), effects=effects()),
                Property(key="Footprint", value=footprint, position=Position(x, y, 0), effects=effects(hidden=True)),
                Property(key="Datasheet", value="", position=Position(x, y, 0), effects=effects(hidden=True)),
                Property(key="Description", value="", position=Position(x, y, 0), effects=effects(hidden=True)),
            ],
            instances=[
                SymbolProjectInstance(
                    name=PROJECT,
                    paths=[SymbolProjectPath(sheetInstancePath=f"/{symbol_uuid}", reference=ref, unit=1)],
                )
            ],
        )
        sch.schematicSymbols.append(symbol)
        for number, (dx, dy) in pin_offsets[lib_name].items():
            pos = Position(round(x + dx, 3), round(y - dy, 3), 0)
            net_name = PIN_NETS[ref].get(number)
            if net_name is None:
                sch.noConnects.append(NoConnect(position=pos, uuid=uid()))
            else:
                direction = -1 if dx < 0 else 1
                label_pos = Position(round(pos.X + direction * 10.16, 3), pos.Y, 0)
                sch.graphicalItems.append(Connection(points=[pos, label_pos], uuid=uid()))
                sch.labels.append(LocalLabel(text=net_name, position=label_pos, effects=effects(size=1.0), uuid=uid()))

    note_effects = effects(size=1.27)
    sch.texts.extend([
        Text(text="REV C.1 ACTIVE BRIDGE / LOGGER", position=Position(140, 25, 0), effects=effects(size=2.0), uuid=uid()),
        Text(text="J2 female faces HOST/PC (DTE); J3 male faces INSTRUMENT (DCE).", position=Position(140, 31, 0), effects=note_effects, uuid=uid()),
        Text(text="Handshake pins 1/4/6/7/8/9 are straight-through copper. Shell pads S1/S2 are NC/floating.", position=Position(140, 35, 0), effects=note_effects, uuid=uid()),
        Text(text="A1 V+ and V- are charge-pump nodes and are intentionally NC.", position=Position(140, 39, 0), effects=note_effects, uuid=uid()),
    ])
    sch.to_file(str(ROOT / f"{PROJECT}.kicad_sch"), encoding="utf-8")


def write_tables_and_project():
    (ROOT / "fp-lib-table").write_text('(fp_lib_table\n  (version 7)\n  (lib (name "FlipperPhunk")(type "KiCad")(uri "${KIPRJMOD}/FlipperPhunk.pretty")(options "")(descr "FlipperPhunk Rev C.1 footprints"))\n)\n', encoding="utf-8")
    (ROOT / "sym-lib-table").write_text('(sym_lib_table\n  (version 7)\n  (lib (name "FlipperPhunk")(type "KiCad")(uri "${KIPRJMOD}/FlipperPhunk.kicad_sym")(options "")(descr "FlipperPhunk Rev C.1 custom symbols"))\n)\n', encoding="utf-8")
    (ROOT / f"{PROJECT}.kicad_pro").write_text('{"board": {}, "cvpcb": {}, "erc": {}, "libraries": {}, "meta": {"filename": "FlipperPhunk_RevC1.kicad_pro", "version": 1}, "net_settings": {}, "pcbnew": {}, "schematic": {}, "text_variables": {}}\n', encoding="utf-8")


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    lib = save_footprints()
    build_board(lib)
    build_legacy_schematic()
    write_tables_and_project()
    build_modern_schematic()
    print(f"Generated {PROJECT} in {ROOT}")


if __name__ == "__main__":
    main()
