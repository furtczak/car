"""
Wersja referencyjna (CadQuery) modelu Auto608.

Wszystkie wymiary i profile sa brane ze skryptu Fusion 360
(fusion360/Auto608/Auto608.py), wiec obie wersje maja identyczna geometrie.
Skrypt sluzy do weryfikacji geometrii i eksportu STEP/STL bez Fusion.

    pip install cadquery
    python3 cadquery_ref/car_608_cq.py
"""
import importlib.util
import math
import os
import sys
import types
from unittest import mock

import cadquery as cq
from cadquery import Vector as V

HERE = os.path.dirname(os.path.abspath(__file__))
FUSION_SCRIPT = os.path.join(HERE, "..", "fusion360", "Auto608", "Auto608.py")

# --- wczytanie danych geometrii ze skryptu Fusion (adsk zastapione atrapa)
_adsk = types.ModuleType("adsk")
_adsk.core, _adsk.fusion = mock.MagicMock(), mock.MagicMock()
sys.modules.setdefault("adsk", _adsk)
sys.modules.setdefault("adsk.core", _adsk.core)
sys.modules.setdefault("adsk.fusion", _adsk.fusion)
_spec = importlib.util.spec_from_file_location("auto608", FUSION_SCRIPT)
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)


# ------------------------------------------------------------------ pomoc ---
def poly_wire(pts3d):
    return cq.Wire.makePolygon([V(*p) for p in pts3d], close=True)


def prism(pts3d, vec):
    return cq.Solid.extrudeLinear(cq.Face.makeFromWires(poly_wire(pts3d)), V(*vec))


def cyl(r, p0, p1):
    p0, p1 = V(*p0), V(*p1)
    return cq.Solid.makeCylinder(r, (p1 - p0).Length, p0, (p1 - p0).normalized())


def box(x0, x1, y0, y1, z0, z1):
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, V(x0, y0, z0))


def sector_face(center_fn, r_in, r_out, a0, a1):
    am = 0.5 * (a0 + a1)
    p = lambda r, a: V(*center_fn(r, a))
    edges = [
        cq.Edge.makeThreePointArc(p(r_out, a0), p(r_out, am), p(r_out, a1)),
        cq.Edge.makeLine(p(r_out, a1), p(r_in, a1)),
        cq.Edge.makeThreePointArc(p(r_in, a1), p(r_in, am), p(r_in, a0)),
        cq.Edge.makeLine(p(r_in, a0), p(r_out, a0)),
    ]
    return cq.Face.makeFromWires(cq.Wire.assembleEdges(edges))


def loft(wires):
    return cq.Solid.makeLoft(wires, ruled=False)


# ------------------------------------------------------------- nadwozie ----
def lower_body():
    wires = [poly_wire([(k[0], y, z) for y, z in G.lower_section(k)]) for k in G.LOWER_KEYS]
    return loft(wires)


def cabin(shrink=0.0):
    wires = [poly_wire([(x, y, k[0]) for x, y in G.cabin_section(k, shrink)])
             for k in G.cabin_keys(shrink)]
    return loft(wires)


def glass_tool(skin):
    tools = []
    for pts in G.side_windows():
        tools.append(prism([(x, 6.0, z) for x, z in pts], (0, 20, 0)))
        tools.append(prism([(x, -6.0, z) for x, z in pts], (0, -20, 0)))
    tools.append(prism([(20.0, y, z) for y, z in G.windshield()], (22, 0, 0)))
    for pts in G.rear_windows():
        tools.append(prism([(47.0, y, z) for y, z in pts], (24, 0, 0)))
    for x0, x1 in G.stripe_ribs():
        tools.append(box(x0, x1, -G.STRIPE_HALF_W, G.STRIPE_HALF_W, 19.0, 30.0))
    t = tools[0]
    for o in tools[1:]:
        t = t.fuse(o)
    return t.intersect(skin)


def build_body():
    body = lower_body().fuse(cabin())
    skin = cabin().cut(cabin(G.SKIN))
    glass = glass_tool(skin)
    body = body.cut(glass)
    build_body.glass = glass

    # przod / tyl
    for y0, y1, z0, z1, d in G.FRONT_RECESSES:
        body = body.cut(box(-1.0, d, y0, y1, z0, z1))
    for y0, y1, z0, z1, d in G.REAR_RECESSES:
        body = body.cut(box(G.L - d, G.L + 1.0, y0, y1, z0, z1))

    # linie drzwi
    for s in (1, -1):
        for x in G.DOOR_LINES_X:
            w = [k for k in G.LOWER_KEYS if k[0] == x][0][1]
            yin = w - G.DOOR_LINE_DEPTH
            y0, y1 = (yin, 25.0) if s > 0 else (-25.0, -yin)
            body = body.cut(box(x - G.DOOR_LINE_W / 2, x + G.DOOR_LINE_W / 2, y0, y1, *G.DOOR_LINE_Z))

    # spoiler
    hw = G.SPOILER_WING_HALF_W
    body = body.fuse(prism([(x, -hw, z) for x, z in G.SPOILER_WING], (0, 2 * hw, 0)))
    y0, y1 = G.SPOILER_PLATE_Y
    for s in (1, -1):
        body = body.fuse(prism([(x, s * y0, z) for x, z in G.SPOILER_PLATE], (0, s * (y1 - y0), 0)))

    # gniazdo lozyska 608 (+ splaszczenie powyzej maski, podciecie, fazka)
    zc, x = G.HOOD_Z, G.BRG_X
    body = body.cut(cyl(G.BRG_FIT_D / 2, (x, 0, zc - G.BRG_DEPTH), (x, 0, zc + 8)))
    body = body.cut(cyl(G.BRG_RELIEF_D / 2, (x, 0, zc - G.BRG_DEPTH - G.BRG_RELIEF_H), (x, 0, zc)))
    c = G.BRG_CHAMFER
    body = body.cut(cq.Solid.makeCone(G.BRG_FIT_D / 2, G.BRG_FIT_D / 2 + c + 3, c + 3,
                                      V(x, 0, zc - c), V(0, 0, 1)))

    # nadkola
    for wx in G.WHEEL_X:
        for s in (1, -1):
            body = body.cut(cyl(G.ARCH_R, (wx, s * G.ARCH_Y, G.WHEEL_R), (wx, s * 25, G.WHEEL_R)))
    return body


def build_wheel(x, s):
    y_out, y_in = s * G.WHEEL_Y_OUT, s * G.WHEEL_Y_IN
    w = cyl(G.WHEEL_R, (x, y_in, G.WHEEL_R), (x, y_out, G.WHEEL_R))
    cf = lambda r, a: (x + r * math.cos(a), y_out + s * 0.05, G.WHEEL_R + r * math.sin(a))
    for r_in, r_out, a0, a1 in G.wheel_sectors():
        f = sector_face(cf, r_in, r_out, a0, a1)
        w = w.cut(cq.Solid.extrudeLinear(f, V(0, -s * (G.WHEEL_DISH_DEPTH + 0.05), 0)))
    r0, r1, d = G.WHEEL_RIM_GROOVE
    ring = cyl(r1, (x, y_out + s * 0.05, G.WHEEL_R), (x, y_out - s * d, G.WHEEL_R)).cut(
        cyl(r0, (x, y_out + s, G.WHEEL_R), (x, y_out - s * 2, G.WHEEL_R)))
    w = w.cut(ring)
    c = G.WHEEL_TIRE_CHAMFER
    cone = cq.Solid.makeCone(G.WHEEL_R - c, G.WHEEL_R + 3, c + 3, V(x, y_out, G.WHEEL_R), V(0, -s, 0))
    w = w.cut(cyl(G.WHEEL_R + 5, (x, y_out + s, G.WHEEL_R), (x, y_out - s * (c + 3), G.WHEEL_R)).cut(cone))
    hr, hd = G.WHEEL_HUB_HOLE
    w = w.cut(cyl(hr, (x, y_out + s * 0.05, G.WHEEL_R), (x, y_out - s * hd, G.WHEEL_R)))
    return w


def build_bearing():
    z0, x = G.HOOD_Z - G.BRG_DEPTH, G.BRG_X
    b = cyl(G.BRG_D / 2, (x, 0, z0), (x, 0, z0 + G.BRG_W))
    b = b.cut(cyl(G.BRG_d / 2, (x, 0, z0 - 1), (x, 0, z0 + G.BRG_W + 1)))
    for zz in (z0 - 1, z0 + G.BRG_W - 0.3):
        b = b.cut(cyl(9.5, (x, 0, zz), (x, 0, zz + 1.3)).cut(cyl(6.0, (x, 0, zz - 1), (x, 0, zz + 3))))
    return b


def build_cap():
    zb, x = G.HOOD_Z - G.BRG_DEPTH + G.BRG_W, G.BRG_X
    c = cyl(7.95 / 2, (x, 0, zb - G.BRG_W + 0.5), (x, 0, zb))
    c = c.fuse(cyl(5.5, (x, 0, zb), (x, 0, zb + 0.5))).fuse(cyl(9.6, (x, 0, zb + 0.5), (x, 0, zb + 4.0)))
    zt = zb + 4.0
    cf = lambda r, a: (x + r * math.cos(a), r * math.sin(a), zt + 0.05)
    for r_in, r_out, a0, a1 in G.cap_sectors():
        c = c.cut(cq.Solid.extrudeLinear(sector_face(cf, r_in, r_out, a0, a1), V(0, 0, -1.25)))
    c = c.cut(cyl(1.0, (x, 0, zt - 1.5), (x, 0, zt + 0.1)))
    return c


if __name__ == "__main__":
    out = os.path.join(HERE, "..", "export")
    os.makedirs(out, exist_ok=True)
    body = build_body()
    for wx in G.WHEEL_X:
        for s in (1, -1):
            body = body.fuse(build_wheel(wx, s))
    body = body.clean()
    bearing, cap = build_bearing(), build_cap()
    bb = body.BoundingBox()
    print("body valid:", body.isValid(), "solids:", len(body.Solids()), "vol:", round(body.Volume(), 1))
    print("bbox: %.2f x %.2f x %.2f" % (bb.xlen, bb.ylen, bb.zlen))
    print("cap valid:", cap.isValid(), "bearing valid:", bearing.isValid())
    print("bearing/body overlap:", round(body.intersect(bearing).Volume(), 4),
          " cap/body overlap:", round(body.intersect(cap).Volume(), 4))
    opts = dict(tolerance=0.01, angularTolerance=0.1)
    cq.exporters.export(cq.Workplane().add(body), os.path.join(out, "auto_608_karoseria.stl"), **opts)
    cq.exporters.export(cq.Workplane().add(cap), os.path.join(out, "auto_608_nakretka.stl"), **opts)
    cq.exporters.export(cq.Workplane().add(bearing), os.path.join(out, "_lozysko_608_ref.stl"), **opts)
    if "--podglad" in sys.argv:   # szyby jako osobna bryla - tylko do renderow
        cq.exporters.export(cq.Workplane().add(build_body.glass), os.path.join(out, "_szyby_podglad.stl"), **opts)
    asm = cq.Assembly(name="auto_608")
    asm.add(body, name="Karoseria", color=cq.Color(0.45, 0.15, 0.75))
    asm.add(cap, name="Nakretka_spinnera", color=cq.Color(0.08, 0.08, 0.08))
    asm.add(bearing, name="Lozysko_608_ref", color=cq.Color(0.75, 0.75, 0.78))
    asm.export(os.path.join(out, "auto_608.step"))
    print("export ok ->", os.path.abspath(out))
