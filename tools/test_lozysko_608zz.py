"""
Uruchamia skrypt Fusion 360 (fusion360/Lozysko608ZZ/Lozysko608ZZ.py) na atrapie
API (tools/fake_adsk.py), porownuje wynik z wersja CadQuery i sprawdza
zlozenie: brak kolizji miedzy czesciami, wymiary katalogowe, luzy.

    python3 tools/test_lozysko_608zz.py
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
    "Lozysko608ZZ", os.path.join(HERE, "..", "fusion360", "Lozysko608ZZ", "Lozysko608ZZ.py"))
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)

design = fake_adsk.Design()
b = A.Builder(mock.MagicMock(), design)
b.run()
print("ostrzezenia:", b.warnings or "brak")

got = {}
for occ in design.rootComponent.occurrences:
    for _, solid in occ.bodies():
        got.setdefault(occ.component.name, []).append(solid.scale(10.0))    # cm -> mm

sys.path.insert(0, os.path.join(HERE, "..", "cadquery_ref"))
import lozysko_608zz_cq as R  # noqa: E402

from OCP.BRepGProp import BRepGProp  # noqa: E402
from OCP.GProp import GProp_GProps  # noqa: E402


def vol(shape):
    """dokladna objetosc (domyslna w CadQuery ma za mala dokladnosc dla kul)"""
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, p, 1e-9)
    return p.Mass()


def sym_diff(a, b):
    """objetosc roznicy symetrycznej przez czesc wspolna (cut na kulach bywa zawodny w OCC)"""
    return vol(a) + vol(b) - 2 * vol(a.intersect(b))


ok = True
ref_parts = R.build_all()
for name, ref_solids, _ in ref_parts:
    g = got.get(name, [])
    ref_c = R.cq.Compound.makeCompound(ref_solids)
    got_c = R.cq.Compound.makeCompound(g) if g else None
    diff = sym_diff(got_c, ref_c) if g else float("inf")
    n_solids = sum(len(s.Solids()) for s in g)
    print("%-24s Fusion-script: %8.2f mm3 (%d bryl)  CadQuery: %8.2f mm3  roznica: %.4f mm3"
          % (name, sum(vol(s) for s in g), n_solids, vol(ref_c), abs(diff)))
    ok &= diff < 1e-3 and n_solids == len(ref_solids)

# --- kolizje: kazda para czesci (rozne czesci) musi miec zerowa czesc wspolna
solids = [(n if len(s) == 1 else "%s %d" % (n, i + 1), x)
          for n, s, _ in ref_parts for i, x in enumerate(s)]
worst = 0.0
for (na, sa), (nb, sb) in itertools.combinations(solids, 2):
    v = vol(sa.intersect(sb))
    if v > 1e-6:
        print("KOLIZJA: %s / %s: %.5f mm3" % (na, nb, v))
        ok = False
    worst = max(worst, v)
print("kolizje: %s" % ("brak" if worst <= 1e-6 else "SA"))


# --- wymiary katalogowe i luzy
def bbox(s):
    return s.BoundingBox()


asm = R.cq.Compound.makeCompound([x for _, x in solids])
bb = bbox(asm)
inner = dict(solids)["Pierscien wewnetrzny"]
checks = [
    ("D (srednica zewn.)", bb.xlen, 22.0),
    ("B (szerokosc)", bb.zlen, 7.0),
    ("B pierscienia wewn.", bbox(inner).zlen, 7.0),
    ("d (otwor)", 2 * min(abs(v.toTuple()[0]) for v in inner.Vertices() if abs(v.toTuple()[1]) < 1e-9
                          and abs(abs(v.toTuple()[2]) - 3.2) < 1e-6), 8.0),
    ("liczba kulek", len(got.get("Kulka 3,969 (5-32 in)", [])), 7),
]
ball = dict(solids)["Kulka 3,969 (5-32 in) 1"]
outer = dict(solids)["Pierscien zewnetrzny"]
cage = dict(solids)["Koszyk"]
gaps = [
    ("kulka - pierscien wewn.", ball.distance(inner), A.CLEAR / 2),
    ("kulka - pierscien zewn.", ball.distance(outer), A.CLEAR / 2),
    ("kulka - koszyk", ball.distance(cage), A.CLEAR),
]
for nm, v, want in checks:
    good = abs(v - want) < 1e-3
    ok &= good
    print("%-24s %8.3f  (oczekiwane %g) %s" % (nm, v, want, "ok" if good else "BLAD"))
for nm, v, lo in gaps:
    good = v >= lo - 1e-4
    ok &= good
    print("luz %-20s %8.4f mm %s" % (nm, v, "ok" if good else "BLAD"))
mass = sum(vol(x) for _, x in solids) * R.STEEL_DENSITY
print("masa: %.2f g (SKF 608-2Z: 12 g)" % mass)
ok &= 10.5 < mass < 13.5

print("WYNIK:", "OK" if ok and not b.warnings else "BLEDY!")
sys.exit(0 if ok and not b.warnings else 1)
