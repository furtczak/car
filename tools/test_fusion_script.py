"""
Uruchamia skrypt Fusion 360 (fusion360/Auto608/Auto608.py) na atrapie API
(tools/fake_adsk.py) i porownuje wynik z wersja referencyjna CadQuery.

    python3 tools/test_fusion_script.py
"""
import importlib.util
import os
import sys
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fake_adsk  # noqa: E402

fake_adsk.install()

spec = importlib.util.spec_from_file_location(
    "Auto608", os.path.join(HERE, "..", "fusion360", "Auto608", "Auto608.py"))
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)

design = fake_adsk.Design()
b = A.Builder(mock.MagicMock(), design)
b.run()
print("ostrzezenia:", b.warnings or "brak")
bodies = {x.name: x for x in design.rootComponent.bRepBodies._list}
print("ciala:", list(bodies))

sys.path.insert(0, os.path.join(HERE, "..", "cadquery_ref"))
import car_608_cq as R  # noqa: E402

ref = R.build_body()
for wx in R.G.WHEEL_X:
    for s in (1, -1):
        ref = ref.fuse(R.build_wheel(wx, s))
ok = True
for name, ref_solid in (("Karoseria", ref), ("Nakretka spinnera", R.build_cap()),
                        ("Lozysko 608 (ref)", R.build_bearing())):
    got = bodies[name].solid.scale(10.0)       # cm -> mm
    diff = got.cut(ref_solid).Volume() + ref_solid.cut(got).Volume()
    print("%-20s Fusion-script: %9.1f mm3  CadQuery: %9.1f mm3  roznica: %.3f mm3  bryly: %d"
          % (name, got.Volume(), ref_solid.Volume(), diff, len(got.Solids())))
    ok &= diff < 1.0
print("WYNIK:", "OK - identyczna geometria" if ok else "ROZNICE!")
sys.exit(0 if ok and not b.warnings else 1)
