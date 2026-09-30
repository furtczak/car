"""
Wersja referencyjna (CadQuery) lozyska 608 do druku 3D (print-in-place).

Przekroje sa brane ze skryptu Fusion 360
(fusion360/Lozysko608Druk/Lozysko608Druk.py), wiec obie wersje maja identyczna
geometrie. Eksportuje STL dla luzow 0,15 / 0,20 / 0,25 mm i STEP (luz 0,15).

    pip install cadquery
    python3 cadquery_ref/lozysko_608_druk_cq.py
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
FUSION_SCRIPT = os.path.join(HERE, "..", "fusion360", "Lozysko608Druk", "Lozysko608Druk.py")

_adsk = types.ModuleType("adsk")
_adsk.core, _adsk.fusion = mock.MagicMock(), mock.MagicMock()
sys.modules.setdefault("adsk", _adsk)
sys.modules.setdefault("adsk.core", _adsk.core)
sys.modules.setdefault("adsk.fusion", _adsk.fusion)
_spec = importlib.util.spec_from_file_location("lozysko608druk", FUSION_SCRIPT)
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)

CLEARANCES = (0.15, 0.20, 0.25)


def revolve_loop(loop, x0=0.0):
    """bryla obrotowa z konturu (r, z) wokol osi pionowej x = x0"""
    pts = [V(x0 + p[0], 0, p[1]) for p, _ in loop]
    edges = []
    for i, (_, mid) in enumerate(loop):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        edges.append(cq.Edge.makeLine(a, b) if mid is None
                     else cq.Edge.makeThreePointArc(a, V(x0 + mid[0], 0, mid[1]), b))
    face = cq.Face.makeFromWires(cq.Wire.assembleEdges(edges))
    return cq.Solid.revolve(face, 360, V(x0, 0, 0), V(x0, 0, 1))


def build_all(c=G.CLEARANCE):
    """(nazwa komponentu, lista bryl, kolor RGB 0..1)"""
    roller = revolve_loop(G.roller_loop(), G.R_PITCH)
    rollers = [roller.rotate(V(0, 0, 0), V(0, 0, 1), math.degrees(G.roller_angle(i)))
               for i in range(G.N_ROLLERS)]
    return [
        ("Pierscien wewnetrzny", [revolve_loop(G.inner_ring_loop(c))], (0.93, 0.93, 0.90)),
        ("Pierscien zewnetrzny", [revolve_loop(G.outer_ring_loop(c))], (0.93, 0.93, 0.90)),
        ("Walek", rollers, (0.15, 0.15, 0.17)),
    ]


if __name__ == "__main__":
    out = os.path.join(HERE, "..", "export")
    os.makedirs(out, exist_ok=True)
    opts = dict(tolerance=0.01, angularTolerance=0.3)
    for c in CLEARANCES:
        parts = build_all(c)
        allsolids = [s for _, ss, _ in parts for s in ss]
        fn = "lozysko_608_druk_luz%03d.stl" % round(c * 100)
        cq.exporters.export(cq.Workplane().add(cq.Compound.makeCompound(allsolids)),
                            os.path.join(out, fn), **opts)
        print("%s  (%d bryl, %.1f mm3)" % (fn, len(allsolids), sum(s.Volume() for s in allsolids)))
    asm = cq.Assembly(name="lozysko_608_druk")
    for name, solids, rgb in build_all(0.15):
        for i, s in enumerate(solids):
            nm = name if len(solids) == 1 else "%s %d" % (name, i + 1)
            asm.add(s, name=nm.replace(" ", "_"), color=cq.Color(*rgb))
    asm.export(os.path.join(out, "lozysko_608_druk_luz015.step"))
    print("export ok ->", os.path.abspath(out))
