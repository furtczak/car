"""
Uruchamia skrypt Fusion 360 (fusion360/Lozysko608Druk/Lozysko608Druk.py) na
atrapie API (tools/fake_adsk.py) dla kilku luzow, porownuje wynik z wersja
CadQuery i sprawdza: brak kolizji, luz walek-pierscien rowny zadanemu,
wymiary 608 (8 x 22 x 7), odstep miedzy walkami.

    python3 tools/test_lozysko_608_druk.py
"""
import importlib.util
import itertools
import os
import sys
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fake_adsk  # noqa: E402

fake_adsk.install()
spec = importlib.util.spec_from_file_location(
    "Lozysko608Druk", os.path.join(HERE, "..", "fusion360", "Lozysko608Druk", "Lozysko608Druk.py"))
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)

sys.path.insert(0, os.path.join(HERE, "..", "cadquery_ref"))
import lozysko_608_druk_cq as R  # noqa: E402
from OCP.BRepGProp import BRepGProp  # noqa: E402
from OCP.GProp import GProp_GProps  # noqa: E402

cq = R.cq


def vol(shape):
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, p, 1e-9)
    return p.Mass()


def sym_diff(a, b):
    return vol(a) + vol(b) - 2 * vol(a.intersect(b))


ok = True
for c in (0.15, 0.25):
    print("=== luz %.2f mm" % c)
    design = fake_adsk.Design()
    b = A.Builder(mock.MagicMock(), design, c)
    b.run()
    ok &= not b.warnings
    print("ostrzezenia:", b.warnings or "brak")
    got = {}
    for occ in design.rootComponent.occurrences:
        for _, solid in occ.bodies():
            got.setdefault(occ.component.name, []).append(solid.scale(10.0))
    parts = R.build_all(c)
    for name, ref, _ in parts:
        g = got.get(name, [])
        diff = sym_diff(cq.Compound.makeCompound(g), cq.Compound.makeCompound(ref)) if g else 1e9
        print("  %-22s %2d bryl  %8.2f mm3  roznica z CadQuery: %.4f mm3"
              % (name, len(g), sum(vol(s) for s in g), abs(diff)))
        ok &= abs(diff) < 1e-3 and len(g) == len(ref)

    inner, outer = parts[0][1][0], parts[1][1][0]
    rollers = parts[2][1]
    bb = cq.Compound.makeCompound([inner, outer] + rollers).BoundingBox()
    bore = 2 * min(v.toTuple()[0] for v in inner.Vertices() if abs(v.toTuple()[1]) < 1e-9)
    for nm, v, want in (("D", bb.xlen, 22.0), ("B", bb.zlen, 7.0), ("d", bore, 8.0)):
        good = abs(v - want) < 1e-3
        ok &= good
        print("  %-3s %7.3f %s" % (nm, v, "ok" if good else "BLAD"))
    g_in = min(r.distance(inner) for r in rollers)
    g_out = min(r.distance(outer) for r in rollers)
    g_rr = min(a.distance(b) for a, b in itertools.combinations(rollers, 2))
    coll = max(vol(a.intersect(b)) for a, b in itertools.combinations([inner, outer] + rollers, 2))
    for nm, v in (("walek-pierscien wewn.", g_in), ("walek-pierscien zewn.", g_out)):
        good = abs(v - c) < 1e-3
        ok &= good
        print("  luz %-22s %.4f mm %s" % (nm, v, "ok" if good else "BLAD"))
    print("  odstep walek-walek       %.4f mm" % g_rr)
    print("  kolizje: %s" % ("brak" if coll < 1e-9 else "SA (%.4f mm3)" % coll))
    ok &= coll < 1e-9 and g_rr > 0.1

print("WYNIK:", "OK" if ok else "BLEDY!")
sys.exit(0 if ok else 1)
