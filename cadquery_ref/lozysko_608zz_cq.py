"""
Wersja referencyjna (CadQuery) lozyska 608ZZ.

Wszystkie wymiary i przekroje sa brane ze skryptu Fusion 360
(fusion360/Lozysko608ZZ/Lozysko608ZZ.py), wiec obie wersje maja identyczna
geometrie. Skrypt sluzy do weryfikacji i eksportu STEP/STL bez Fusion.

    pip install cadquery
    python3 cadquery_ref/lozysko_608zz_cq.py
"""
import importlib.util
import os
import sys
import types
from unittest import mock

import cadquery as cq
from cadquery import Vector as V

HERE = os.path.dirname(os.path.abspath(__file__))
FUSION_SCRIPT = os.path.join(HERE, "..", "fusion360", "Lozysko608ZZ", "Lozysko608ZZ.py")

# --- wczytanie danych geometrii ze skryptu Fusion (adsk zastapione atrapa)
_adsk = types.ModuleType("adsk")
_adsk.core, _adsk.fusion = mock.MagicMock(), mock.MagicMock()
sys.modules.setdefault("adsk", _adsk)
sys.modules.setdefault("adsk.core", _adsk.core)
sys.modules.setdefault("adsk.fusion", _adsk.fusion)
_spec = importlib.util.spec_from_file_location("lozysko608zz", FUSION_SCRIPT)
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)

STEEL_DENSITY = 7.81e-3     # g/mm3 (stal lozyskowa 100Cr6)


def revolve_loop(loop):
    """bryla obrotowa wokol Z z konturu (r, z) -> (r, 0, z)"""
    pts = [V(p[0], 0, p[1]) for p, _ in loop]
    edges = []
    for i, (_, mid) in enumerate(loop):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        if mid is None:
            edges.append(cq.Edge.makeLine(a, b))
        else:
            edges.append(cq.Edge.makeThreePointArc(a, V(mid[0], 0, mid[1]), b))
    face = cq.Face.makeFromWires(cq.Wire.assembleEdges(edges))
    return cq.Solid.revolve(face, 360, V(0, 0, 0), V(0, 0, 1))


def build_inner_ring():
    return revolve_loop(G.inner_ring_loop())


def build_outer_ring():
    return revolve_loop(G.outer_ring_loop())


def sphere(r, c):
    """kula z biegunami na kierunku promieniowym (jak w skrypcie Fusion)"""
    return cq.Solid.makeSphere(r, V(*c), V(c[0], c[1], 0).normalized(),
                               angleDegrees1=-90, angleDegrees2=90)


def build_balls():
    return [sphere(G.R_BALL, c) for c in G.ball_centers()]


def build_cage():
    cage = revolve_loop(G.cage_web_loop())
    for c in G.ball_centers():
        cage = cage.fuse(sphere(G.CAGE_POCKET + G.CAGE_SHEET, c))
    cage = cage.intersect(revolve_loop(G.cage_band_loop()))
    for c in G.ball_centers():
        cage = cage.cut(sphere(G.CAGE_POCKET, c))
    for s in (1, -1):
        for x, y in G.rivet_centers():
            z0 = s * G.CAGE_SHEET
            cage = cage.fuse(cq.Solid.makeCylinder(G.RIVET_R, G.RIVET_H, V(x, y, z0), V(0, 0, s)))
    return cage.clean()


def build_shields():
    return [revolve_loop(G.shield_loop(s)) for s in (1, -1)]


def build_all():
    """czesci zlozenia: (nazwa komponentu, lista bryl, kolor RGB 0..1)"""
    return [
        ("Pierscien wewnetrzny", [build_inner_ring()], (0.70, 0.71, 0.74)),
        ("Pierscien zewnetrzny", [build_outer_ring()], (0.70, 0.71, 0.74)),
        ("Kulka 3,969 (5-32 in)", build_balls(), (0.90, 0.91, 0.93)),
        ("Koszyk", [build_cage()], (0.55, 0.52, 0.48)),
        ("Oslona ZZ", build_shields(), (0.62, 0.63, 0.66)),
    ]


if __name__ == "__main__":
    out = os.path.join(HERE, "..", "export")
    os.makedirs(out, exist_ok=True)
    parts = build_all()
    asm = cq.Assembly(name="lozysko_608zz")
    everything = []
    for name, solids, rgb in parts:
        col = cq.Color(*rgb)
        for i, s in enumerate(solids):
            nm = name if len(solids) == 1 else "%s %d" % (name, i + 1)
            asm.add(s, name=nm.replace(",", ".").replace(" ", "_"), color=col)
            everything.append(s)
        vol = sum(s.Volume() for s in solids)
        print("%-24s %d szt.  %8.2f mm3  %6.2f g" % (name, len(solids), vol, vol * STEEL_DENSITY))
    asm.export(os.path.join(out, "lozysko_608zz.step"))
    opts = dict(tolerance=0.01, angularTolerance=0.25)
    cq.exporters.export(cq.Workplane().add(cq.Compound.makeCompound(everything)),
                        os.path.join(out, "lozysko_608zz.stl"), **opts)
    total = sum(s.Volume() for s in everything)
    print("razem: %.2f g (SKF 608-2Z: 12 g)" % (total * STEEL_DENSITY))
    print("export ok ->", os.path.abspath(out))
