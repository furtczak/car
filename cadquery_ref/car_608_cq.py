"""
Referencyjna wersja modelu (CadQuery) - ta sama geometria co skrypt Fusion 360.
Sluzy do weryfikacji geometrii i eksportu STEP/STL bez Fusion.

Uklad: X = dlugosc (0 = przod, +X = do tylu), Y = szerokosc (0 = os symetrii),
Z = wysokosc (0 = podloze). Jednostki: mm.
"""
import math
import os
import cadquery as cq
from cadquery import Vector as V

# ---------------------------------------------------------------- parametry --
L = 72.0          # dlugosc nadwozia
W = 38.0          # szerokosc nadwozia
HOOD_Z = 13.0     # wysokosc maski

# 608: 8 x 22 x 7
BRG_D, BRG_d, BRG_W = 22.0, 8.0, 7.0
BRG_FIT_D = 22.15      # srednica gniazda (wcisk/luz - dopasuj do drukarki)
BRG_DEPTH = 3.0        # glebokosc gniazda od powierzchni maski
BRG_RELIEF_D = 17.0    # podciecie pod pierscien wewnetrzny
BRG_RELIEF_H = 1.0
BRG_CHAMFER = 0.5
BRG_X = 15.7           # srodek lozyska (nad przednia osia)

WHEEL_R, WHEEL_W = 6.0, 3.4
WHEEL_X = (15.7, 60.0)
WHEEL_PROUD = 0.3      # o ile kolo wystaje poza bok nadwozia
ARCH_R, ARCH_DEPTH = 6.5, 2.8

# profil boczny (x, z)
SIDE = [(0, 1.2), (1.0, 0), (71.0, 0), (72, 1.2), (72, 13.0), (71.0, 14.8),
        (63.5, 14.8), (62.0, 16.3), (52.5, 24.8), (36.2, 24.8), (27.3, HOOD_Z),
        (3.0, HOOD_Z), (1.2, 12.2), (0, 10.2)]
# profil z gory - polowa (x, y)
TOP_HALF = [(0, 15.5), (4.0, 19.0), (70.0, 19.0), (72.0, 17.8)]
# przekroj poprzeczny - polowa (y, z)
FRONT_HALF = [(0, 0), (18.2, 0), (19.0, 0.8), (19.0, 12.4), (17.0, 14.9),
              (13.0, 24.0), (11.0, 26.0), (0, 26.0)]


# ------------------------------------------------------------------ pomoc ---
def prism(pts3d, vec):
    wire = cq.Wire.makePolygon([V(*p) for p in pts3d], close=True)
    return cq.Solid.extrudeLinear(cq.Face.makeFromWires(wire), V(*vec))


def cyl(r, p0, p1):
    p0, p1 = V(*p0), V(*p1)
    return cq.Solid.makeCylinder(r, (p1 - p0).Length, p0, (p1 - p0).normalized())


def lerp(a, b, t):
    return a + (b - a) * t


def plane_cut(body, poly_uv, origin, u, v, n, depth):
    """Wglebienie: wielokat (u,v) na plaszczyznie (origin,u,v) o normalnej n
    (na zewnatrz), wyciety na glebokosc depth."""
    o, u, v, n = V(*origin), V(*u), V(*v), V(*n).normalized()
    pts = [o + u * a + v * b + n * 0.2 for a, b in poly_uv]
    tool = prism([p.toTuple() for p in pts], (n * -(depth + 0.2)).toTuple())
    return body.cut(tool)


def gh(z):
    """polowa szerokosci kabiny (plaszczyzna boku kabiny) na wysokosci z"""
    (y0, z0), (y1, z1) = (17.0, 14.9), (13.0, 24.0)
    return y0 + (z - z0) * (y1 - y0) / (z1 - z0)


# ------------------------------------------------------------- nadwozie ----
def build_body():
    side = prism([(x, W, z) for x, z in SIDE], (0, -2 * W, 0))
    top_pts = TOP_HALF + [(x, -y) for x, y in reversed(TOP_HALF)]
    top = prism([(x, y, -1) for x, y in top_pts], (0, 0, 40))
    fr_pts = FRONT_HALF[1:-1] + [(-y, z) for y, z in reversed(FRONT_HALF[1:-1])]
    front = prism([(-5, y, z) for y, z in fr_pts], (L + 10, 0, 0))
    body = side.intersect(top).intersect(front)

    # --- szyba przednia (plaszczyzna przez (27.3,13) - (36.2,24.8))
    a, b = V(27.3, 0, HOOD_Z), V(36.2, 0, 24.8)
    u = (b - a).normalized()
    n = V(-u.z, 0, u.x)  # normalna na zewnatrz (do przodu/gory)
    def ws(z, side_):
        t = (z - HOOD_Z) / (24.8 - HOOD_Z)
        return (b - a).Length * t, side_
    z0, z1 = 14.2, 23.8
    poly = [ws(z0, -15.6), ws(z0, 15.6), ws(z1, gh(z1) - 1.2), ws(z1, -(gh(z1) - 1.2))]
    body = plane_cut(body, poly, a.toTuple(), u.toTuple(), (0, 1, 0), n.toTuple(), 0.5)

    # --- szyba tylna: dwie tafle po bokach pasa
    a, b = V(62.0, 0, 16.3), V(52.5, 0, 24.8)
    u = (b - a).normalized()
    n = V(u.z, 0, -u.x)
    if n.z < 0:
        n = -n
    Lr = (b - a).Length
    def rw(z, y):
        return Lr * (z - 16.3) / (24.8 - 16.3), y
    z0, z1 = 17.3, 23.9
    for s in (1, -1):
        poly = [rw(z0, s * 5.2), rw(z0, s * (gh(z0) - 1.2)), rw(z1, s * (gh(z1) - 1.2)), rw(z1, s * 5.2)]
        body = plane_cut(body, poly, a.toTuple(), u.toTuple(), (0, 1, 0), n.toTuple(), 0.5)
    # zeberka pasa na tylnej szybie
    for i in range(5):
        t0 = 1.2 + i * 1.6
        body = plane_cut(body, [(t0, -4.5), (t0 + 0.6, -4.5), (t0 + 0.6, 4.5), (t0, 4.5)],
                         a.toTuple(), u.toTuple(), (0, 1, 0), n.toTuple(), 0.35)

    # --- szyby boczne (plaszczyzna boku kabiny)
    for s in (1, -1):
        p0 = V(0, s * 17.0, 14.9)
        p1 = V(0, s * 13.0, 24.0)
        vdir = (p1 - p0).normalized()
        n = V(0, s * 9.1, 4.0).normalized()  # normalna boku kabiny
        def sw(x, z):
            return x, (z - 14.9) / (24.0 - 14.9) * (p1 - p0).Length
        k = (36.2 - 27.3) / (24.8 - HOOD_Z)
        zb, zt = 15.3, 19.6
        poly = [sw(27.3 + (zb - HOOD_Z) * k + 2.2, zb), sw(47.5, zb), sw(47.5, zt),
                sw(27.3 + (zt - HOOD_Z) * k + 2.2, zt)]
        body = plane_cut(body, poly, p0.toTuple(), (1, 0, 0), vdir.toTuple(), n.toTuple(), 0.5)

    # --- pas dachowy z zeberkami
    for i in range(10):
        x0 = 37.5 + i * 1.5
        body = body.cut(cq.Solid.makeBox(0.6, 9.0, 1.0, V(x0, -4.5, 24.8 - 0.35)))

    # --- linie drzwi (rowki)
    for s in (1, -1):
        for x in (30.0, 48.0):
            y0 = s * 19.0
            body = body.cut(cq.Solid.makeBox(0.4, 0.6, 11.2, V(x - 0.2, y0 - 0.3, 1.0)))
        body = body.cut(cq.Solid.makeBox(66.0, 0.6, 0.4, V(3.0, s * 19.0 - 0.3, 1.8)))

    # --- przod: wlot powietrza
    body = body.cut(cq.Solid.makeBox(1.5, 24.0, 3.2, V(0 - 0.01, -12.0, 3.7)))
    body = body.cut(cq.Solid.makeBox(0.3, 30.0, 0.4, V(0 - 0.01, -15.0, 8.2)))

    # --- tyl: panel lamp, listwa swietlna, wydechy, dyfuzor
    body = body.cut(cq.Solid.makeBox(0.4, 30.0, 5.5, V(L - 0.4, -15.0, 6.1)))
    body = body.cut(cq.Solid.makeBox(1.5, 25.2, 2.8, V(L - 1.5, -12.6, 7.0)))
    for s in (1, -1):
        body = body.cut(cq.Solid.makeBox(0.5, 4.4, 2.0, V(L - 0.5, s * 9.8 - 2.2, 1.7)))
        body = body.cut(cq.Solid.makeBox(2.5, 3.4, 1.2, V(L - 2.5, s * 9.8 - 1.7, 2.1)))
    body = body.cut(cq.Solid.makeBox(0.6, 14.0, 2.2, V(L - 0.6, -7.0, 1.4)))

    # --- spoiler: profil boczny na szerokosc 26.4, wyciety srodek pod skrzydlem
    sp = prism([(62.2, -13.2, 14.0), (69.8, -13.2, 14.0), (69.8, -13.2, 21.5), (63.2, -13.2, 21.5)],
               (0, 26.4, 0))
    sp = sp.cut(cq.Solid.makeBox(10.0, 22.0, 6.9, V(61.0, -11.0, 13.0)))
    body = body.fuse(sp)

    # --- gniazdo lozyska 608
    top_z = HOOD_Z
    body = body.cut(cyl(BRG_FIT_D / 2, (BRG_X, 0, top_z - BRG_DEPTH), (BRG_X, 0, top_z + 5)))
    body = body.cut(cyl(BRG_RELIEF_D / 2, (BRG_X, 0, top_z - BRG_DEPTH - BRG_RELIEF_H),
                        (BRG_X, 0, top_z)))
    body = body.cut(cq.Solid.makeCone(BRG_FIT_D / 2, BRG_FIT_D / 2 + BRG_CHAMFER + 2, BRG_CHAMFER + 2,
                                      V(BRG_X, 0, top_z - BRG_CHAMFER), V(0, 0, 1)))

    # --- nadkola
    for x in WHEEL_X:
        for s in (1, -1):
            yin = s * (W / 2 - ARCH_DEPTH)
            body = body.cut(cyl(ARCH_R, (x, yin, WHEEL_R), (x, s * (W / 2 + 2), WHEEL_R)))
    return body


def build_wheel(x, s):
    """kolo po stronie s (+1/-1); tarcza z 6 ramionami na zewnetrznej stronie"""
    y_out = s * (W / 2 + WHEEL_PROUD)
    y_in = y_out - s * WHEEL_W
    w = cyl(WHEEL_R, (x, y_in, WHEEL_R), (x, y_out, WHEEL_R))
    r_in, r_out, depth, n = 1.3, 4.9, 0.8, 6
    half_ang = math.radians(8)
    for i in range(n):
        a0 = 2 * math.pi * i / n + half_ang
        a1 = 2 * math.pi * (i + 1) / n - half_ang
        pts = []
        steps = 8
        for k in range(steps + 1):
            a = lerp(a0, a1, k / steps)
            pts.append((x + r_out * math.cos(a), r_out * math.sin(a) + WHEEL_R))
        for k in range(steps, -1, -1):
            a = lerp(a0, a1, k / steps)
            pts.append((x + r_in * math.cos(a), r_in * math.sin(a) + WHEEL_R))
        tool = prism([(px, y_out + s * 0.1, pz) for px, pz in pts], (0, -s * (depth + 0.1), 0))
        w = w.cut(tool)
    w = w.cut(cyl(0.6, (x, y_out - s * 1.0, WHEEL_R), (x, y_out + s * 0.1, WHEEL_R)))
    return w


def build_bearing():
    z0 = HOOD_Z - BRG_DEPTH
    b = cyl(BRG_D / 2, (BRG_X, 0, z0), (BRG_X, 0, z0 + BRG_W))
    b = b.cut(cyl(BRG_d / 2, (BRG_X, 0, z0 - 1), (BRG_X, 0, z0 + BRG_W + 1)))
    for zz in (z0 - 1, z0 + BRG_W - 0.3):
        b = b.cut(cyl(9.5, (BRG_X, 0, zz), (BRG_X, 0, zz + 1.3)).cut(
            cyl(6.0, (BRG_X, 0, zz - 1), (BRG_X, 0, zz + 3))))
    return b


def build_cap():
    zb = HOOD_Z - BRG_DEPTH + BRG_W  # gorna powierzchnia lozyska
    stem = cyl(7.95 / 2, (BRG_X, 0, zb - BRG_W + 0.5), (BRG_X, 0, zb))
    boss = cyl(5.5, (BRG_X, 0, zb), (BRG_X, 0, zb + 0.5))
    disk = cyl(9.6, (BRG_X, 0, zb + 0.5), (BRG_X, 0, zb + 4.0))
    c = stem.fuse(boss).fuse(disk)
    zt = zb + 4.0
    n, r_in, r_out = 5, 2.5, 8.0
    ha = math.radians(9)
    for i in range(n):
        a0 = 2 * math.pi * i / n + ha
        a1 = 2 * math.pi * (i + 1) / n - ha
        pts = [(BRG_X + r_out * math.cos(lerp(a0, a1, k / 10)), r_out * math.sin(lerp(a0, a1, k / 10)))
               for k in range(11)]
        pts += [(BRG_X + r_in * math.cos(lerp(a0, a1, k / 10)), r_in * math.sin(lerp(a0, a1, k / 10)))
                for k in range(10, -1, -1)]
        c = c.cut(prism([(px, py, zt + 0.1) for px, py in pts], (0, 0, -1.3)))
    c = c.cut(cyl(1.0, (BRG_X, 0, zt - 1.5), (BRG_X, 0, zt + 0.1)))
    return c


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "export")
    os.makedirs(out, exist_ok=True)
    body = build_body()
    for x in WHEEL_X:
        for s in (1, -1):
            body = body.fuse(build_wheel(x, s))
    body = body.clean()
    bearing = build_bearing()
    cap = build_cap()
    print("body valid:", body.isValid(), "solids:", len(body.Solids()), "vol:", round(body.Volume(), 1))
    bb = body.BoundingBox()
    print("bbox:", round(bb.xlen, 2), round(bb.ylen, 2), round(bb.zlen, 2))
    print("cap valid:", cap.isValid(), "bearing valid:", bearing.isValid())
    print("bearing/body overlap vol:", round(body.intersect(bearing).Volume(), 4))
    print("cap/body overlap vol:", round(body.intersect(cap).Volume(), 4))
    cq.exporters.export(cq.Workplane().add(body), os.path.join(out, "auto_608_karoseria.stl"), tolerance=0.02, angularTolerance=0.1)
    cq.exporters.export(cq.Workplane().add(cap), os.path.join(out, "auto_608_nakretka.stl"), tolerance=0.02, angularTolerance=0.1)
    asm = cq.Assembly(name="auto_608")
    asm.add(body, name="Karoseria", color=cq.Color(0.45, 0.15, 0.75))
    asm.add(cap, name="Nakretka_spinnera", color=cq.Color(0.08, 0.08, 0.08))
    asm.add(bearing, name="Lozysko_608_ref", color=cq.Color(0.75, 0.75, 0.78))
    asm.save(os.path.join(out, "auto_608.step"))
    cq.exporters.export(cq.Workplane().add(bearing), os.path.join(out, "_lozysko_608_ref.stl"))
    print("export ok ->", os.path.abspath(out))
