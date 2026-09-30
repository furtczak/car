# -*- coding: utf-8 -*-
"""
Lozysko608Druk - skrypt Autodesk Fusion 360

Lozysko 608 (8 x 22 x 7 mm) do druku 3D w jednym kawalku (print-in-place).
Zamiast kulek ma 10 walkow w ksztalcie szpulki: waska talia i stozki 45 st.
obejmuja grzbiety w ksztalcie litery V na obu pierscieniach. Walki trzymaja
sie wiec pierscieni osiowo i nie potrzebuja koszyka. Wszystkie powierzchnie
sa pod katem 45 st. albo pionowe, wiec drukuje sie bez podpor (os pionowo).

Przekroj (r = promien, z = wysokosc, srodek lozyska w z = 0):

   pierscien wewn.  |  walek (szpulka)  |  pierscien zewn.
        ____          ______________          ____
       |    \  luz   |              |  luz   /    |
       |     >------ |>  talia    <|------ <     |
       |____/        |______________|        \____|

Luz (odstep mierzony prostopadle do kazdej powierzchni) podajesz przy
uruchomieniu: 0,15 mm dla dobrze skalibrowanej drukarki, 0,20-0,25 mm dla
luzniejszej. Otwor i srednica zewnetrzna sa lekko rozchylone przy czolach
(0,2 mm), zeby "stopa slonia" pierwszej warstwy nie zmniejszala wymiarow.

Uklad: os lozyska = Z, srodek w (0, 0, 0), czola w Z = +-3,5 mm.
Uruchomienie: Utilities -> ADD-INS -> Scripts and Add-Ins -> zakladka Scripts
-> "+" (My Scripts) -> wskaz folder Lozysko608Druk -> Run.
"""

import math
import traceback

import adsk.core
import adsk.fusion

# =============================================================================
#  PARAMETRY (mm)
# =============================================================================
d, D, B = 8.0, 22.0, 7.0        # otwor, srednica zewn., wysokosc
CLEARANCE = 0.15                # luz domyslny (pytanie przy uruchomieniu)

N_ROLLERS = 10
R_PITCH = 7.5                   # promien podzialowy walkow
R_END = 2.25                    # promien walka na koncach (Ø4,5)
R_WAIST = 1.35                  # promien talii walka (Ø2,7)
Z_CONE = 2.112                  # wysokosc srodka stozka 45 st. na walku
FILLET = 1.0                    # zaokraglenia przejsc talia/stozek/koniec
EF_DEPTH = 0.20                 # rozchylenie otworu i srednicy zewn. przy czole
EF_HEIGHT = 0.872               # wysokosc strefy rozchylenia

H = B / 2
SQ2 = math.sqrt(2.0)


# =============================================================================
#  GEOMETRIA (czysty Python - wspolna dla Fusion i wersji CadQuery)
#  Kontur = lista (punkt, srodek_luku): odcinek od punktu do nastepnego jest
#  lukiem przez srodek_luku albo prosta (None). Punkty (r, z) w mm.
# =============================================================================
def rounded(poly):
    """poly = [(punkt, promien_zaokraglenia, srodek_luku_do_nastepnego)].
    Zaokragla naroza (promien > 0) miedzy dwoma odcinkami prostymi."""
    n = len(poly)
    out = []
    for i, (v, rad, mid) in enumerate(poly):
        if not rad:
            out.append((v, mid))
            continue
        p, q = poly[i - 1][0], poly[(i + 1) % n][0]
        a = (p[0] - v[0], p[1] - v[1])
        b = (q[0] - v[0], q[1] - v[1])
        la, lb = math.hypot(*a), math.hypot(*b)
        a, b = (a[0] / la, a[1] / la), (b[0] / lb, b[1] / lb)
        half = 0.5 * math.acos(max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1])))
        t = rad / math.tan(half)
        u = (a[0] + b[0], a[1] + b[1])
        lu = math.hypot(*u)
        u = (u[0] / lu, u[1] / lu)
        c = rad / math.sin(half)
        arc_mid = (v[0] + u[0] * (c - rad), v[1] + u[1] * (c - rad))
        out.append(((v[0] + a[0] * t, v[1] + a[1] * t), arc_mid))
        out.append(((v[0] + b[0] * t, v[1] + b[1] * t), mid))
    return out


def flare_mid(r_wall, sign_r, sign_z):
    """srodek luku rozchylenia: styczny do scianki r = r_wall w z = +-(H - EF_HEIGHT),
    konczy sie na czole w r_wall + sign_r * EF_DEPTH"""
    rad = (EF_HEIGHT ** 2 + EF_DEPTH ** 2) / (2 * EF_DEPTH)
    cr, cz = r_wall + sign_r * rad, sign_z * (H - EF_HEIGHT)
    a0 = math.pi if sign_r > 0 else 0.0            # kierunek od srodka do punktu stycznosci
    am = a0 - sign_r * sign_z * 0.5 * math.asin(EF_HEIGHT / rad)
    return (cr + rad * math.cos(am), cz + rad * math.sin(am))


def cone_k():
    """stozek walka: r = |z| - k"""
    return Z_CONE - 0.5 * (R_WAIST + R_END)


def inner_ring_loop(c=CLEARANCE):
    k = cone_k()
    kin = R_PITCH + k - c * SQ2           # powierzchnia grzbietu: r = kin - |z|
    rf, rm = R_PITCH - R_END - c, R_PITCH - R_WAIST - c
    rb, zt = d / 2, H - EF_HEIGHT
    return rounded([
        ((rb, -zt), 0, None),
        ((rb, zt), 0, flare_mid(rb, 1, 1)),
        ((rb + EF_DEPTH, H), 0, None),
        ((rf, H), 0, None),
        ((rf, kin - rf), FILLET, None),
        ((rm, kin - rm), FILLET, None),
        ((rm, -(kin - rm)), FILLET, None),
        ((rf, -(kin - rf)), FILLET, None),
        ((rf, -H), 0, None),
        ((rb + EF_DEPTH, -H), 0, flare_mid(rb, 1, -1)),
    ])


def outer_ring_loop(c=CLEARANCE):
    k = cone_k()
    kout = R_PITCH - k + c * SQ2          # r = kout + |z|
    rf, rm = R_PITCH + R_END + c, R_PITCH + R_WAIST + c
    ro, zt = D / 2, H - EF_HEIGHT
    return rounded([
        ((ro, zt), 0, None),
        ((ro, -zt), 0, flare_mid(ro, -1, -1)),
        ((ro - EF_DEPTH, -H), 0, None),
        ((rf, -H), 0, None),
        ((rf, -(rf - kout)), FILLET, None),
        ((rm, -(rm - kout)), FILLET, None),
        ((rm, rm - kout), FILLET, None),
        ((rf, rf - kout), FILLET, None),
        ((rf, H), 0, None),
        ((ro - EF_DEPTH, H), 0, flare_mid(ro, -1, 1)),
    ])


def roller_loop():
    """pol-przekroj walka (r_lokalny >= 0, z); pierwszy odcinek lezy na osi walka"""
    k = cone_k()
    return rounded([
        ((0.0, H), 0, None),
        ((0.0, -H), 0, None),
        ((R_END, -H), 0, None),
        ((R_END, -(R_END + k)), FILLET, None),
        ((R_WAIST, -(R_WAIST + k)), FILLET, None),
        ((R_WAIST, R_WAIST + k), FILLET, None),
        ((R_END, R_END + k), FILLET, None),
        ((R_END, H), 0, None),
    ])


def roller_angle(i):
    return 2 * math.pi * i / N_ROLLERS


# =============================================================================
#  FUSION 360
# =============================================================================
def mm(v):
    return v / 10.0


def P(x, y, z):
    return adsk.core.Point3D.create(mm(x), mm(y), mm(z))


class Builder(object):
    def __init__(self, app, design, clearance=CLEARANCE):
        self.app = app
        self.design = design
        self.root = design.rootComponent
        self.clearance = clearance
        self.warnings = []
        self.NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation

    def safe(self, label, fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Exception:
            self.warnings.append('%s: %s' % (label, traceback.format_exc().strip().splitlines()[-1]))
            return None

    def new_component(self, name):
        occ = self.root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
        occ.component.name = name
        return occ

    @staticmethod
    def _near(curve, p):
        s, e = curve.startSketchPoint, curve.endSketchPoint
        return s if s.geometry.distanceTo(p) < e.geometry.distanceTo(p) else e

    def draw_loop(self, sk, loop, to3d):
        """zamkniety kontur z odcinkow i lukow; kolejne krzywe maja wspolne punkty szkicu"""
        q = [sk.modelToSketchSpace(P(*to3d(*p))) for p, _ in loop]
        lines, arcs = sk.sketchCurves.sketchLines, sk.sketchCurves.sketchArcs
        curves, first, prev = [], None, None
        n = len(loop)
        for i in range(n):
            a = prev if prev is not None else q[i]
            b = first if i == n - 1 else q[i + 1]
            mid = loop[i][1]
            if mid is None:
                c = lines.addByTwoPoints(a, b)
            else:
                c = arcs.addByThreePoints(a, sk.modelToSketchSpace(P(*to3d(*mid))), b)
            curves.append(c)
            if first is None:
                first = self._near(c, q[0])
            prev = self._near(c, q[(i + 1) % n])
        return curves

    def revolve(self, comp, loop, name, x0=0.0, axis_curve=None):
        """bryla obrotowa z konturu (r, z) wokol osi pionowej x = x0 (plaszczyzna XZ).
        axis_curve = indeks krzywej konturu lezacej na osi (albo None)"""
        sk = comp.sketches.add(comp.xZConstructionPlane)
        sk.name = name
        curves = self.draw_loop(sk, loop, lambda r, z: (x0 + r, 0.0, z))
        if axis_curve is None:
            ax = sk.sketchCurves.sketchLines.addByTwoPoints(
                sk.modelToSketchSpace(P(x0, 0, -H - 1)), sk.modelToSketchSpace(P(x0, 0, H + 1)))
            ax.isConstruction = True
        else:
            ax = curves[axis_curve]
        rv = comp.features.revolveFeatures
        inp = rv.createInput(sk.profiles.item(0), ax, self.NEW)
        inp.setAngleExtent(False, adsk.core.ValueInput.createByString('360 deg'))
        body = rv.add(inp).bodies.item(0)
        body.name = name
        return body

    def run(self):
        c = self.clearance
        wew = self.new_component('Pierscien wewnetrzny')
        self.revolve(wew.component, inner_ring_loop(c), 'Pierscien wewnetrzny')
        zew = self.new_component('Pierscien zewnetrzny')
        self.revolve(zew.component, outer_ring_loop(c), 'Pierscien zewnetrzny')
        wal = self.new_component('Walek')
        self.revolve(wal.component, roller_loop(), 'Walek', x0=R_PITCH, axis_curve=0)
        for i in range(1, N_ROLLERS):
            m = adsk.core.Matrix3D.create()
            m.setToRotation(roller_angle(i), adsk.core.Vector3D.create(0, 0, 1),
                            adsk.core.Point3D.create(0, 0, 0))
            self.root.occurrences.addExistingComponent(wal.component, m)
        self.safe('Kolory', self.colors, [wew.component, zew.component], wal.component)

    def colors(self, rings, roller):
        libs = self.app.materialLibraries
        lib = None
        for nm in ('Fusion Appearance Library', 'Fusion 360 Appearance Library'):
            lib = lib or libs.itemByName(nm)
        if lib is None:
            return
        for comp, names in ((rings[0], ('Plastic - Matte (White)', 'Plastic - Glossy (White)')),
                            (rings[1], ('Plastic - Matte (White)', 'Plastic - Glossy (White)')),
                            (roller, ('Plastic - Matte (Black)', 'Plastic - Glossy (Black)'))):
            look = None
            for nm in names:
                look = look or lib.appearances.itemByName(nm)
            if look is None:
                continue
            look = self.design.appearances.itemByName(look.name) or \
                self.design.appearances.addByCopy(look, look.name)
            for body in comp.bRepBodies:
                body.appearance = look


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        res = ui.inputBox('Luz miedzy walkami a pierscieniami [mm]\n'
                          '0,15 - dobrze skalibrowana drukarka, 0,20-0,25 - luzniej',
                          'Lozysko 608 do druku', '%.2f' % CLEARANCE)
        if res[1]:
            return
        clearance = float(res[0].replace(',', '.'))
        if not 0.05 <= clearance <= 0.5:
            raise ValueError('luz poza zakresem 0,05-0,5 mm: %g' % clearance)

        app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        design.fusionUnitsManager.distanceDisplayUnits = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
        design.rootComponent.name = 'Lozysko 608 druk (luz %.2f)' % clearance

        b = Builder(app, design, clearance)
        b.run()
        try:
            app.activeViewport.fit()
        except Exception:
            pass
        msg = ('Lozysko 608 do druku gotowe (luz %.2f mm).\n\n'
               'Druk: os pionowo, bez podpor, PLA, warstwa 0,12 mm, 2 obrysy.\n'
               'Eksport: prawy klik na komponencie glownym -> Save As Mesh (3MF/STL).\n'
               'Po druku przekrec kazdy walek palcem, zeby go uwolnic.' % clearance)
        if b.warnings:
            msg += '\n\nOstrzezenia:\n- ' + '\n- '.join(b.warnings)
        ui.messageBox(msg, 'Lozysko 608 do druku')
    except Exception:
        if ui:
            ui.messageBox('Blad:\n{}'.format(traceback.format_exc()), 'Lozysko 608 do druku')
