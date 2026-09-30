# -*- coding: utf-8 -*-
"""
Lozysko608ZZ - skrypt Autodesk Fusion 360

Buduje zlozenie lozyska kulkowego zwyklego 608ZZ (8 x 22 x 7 mm) z osobnych
komponentow, tak jak wyglada prawdziwe lozysko po rozcieciu:

  * Pierscien wewnetrzny  - bieznia (promien rowka 0,52 Dw), fazki r 0,3,
                            podciecia pod labirynt oslon,
  * Pierscien zewnetrzny  - bieznia (0,53 Dw), gniazda oslon z podcieciem
                            (zawalcowanie oslony), zaokraglenia r 0,3,
  * Kulka 3,969 (5/32")   - 1 komponent, 7 wystapien na srednicy podzialowej 15 mm,
  * Koszyk                - koszyk wstazkowy z blachy (dwie polowki), 7 kieszeni
                            kulistych, 7 nitow,
  * Oslona ZZ             - blaszana oslona 0,3 mm, 1 komponent, 2 wystapienia.

Uklad: os lozyska = Z, srodek lozyska w (0, 0, 0), czola w Z = +-3,5 mm.
Wszystkie wymiary w mm (API Fusion pracuje w cm - przeliczane w mm()).

Wymiary wg ISO 15 / katalogu SKF (608-2Z): d = 8, D = 22, B = 7, r_s min = 0,3,
d1 = 12,1 (odsadzenie pierscienia wewn.), D2 = 19,2 (gniazdo oslony),
kulki 7 x 3,969 mm. Luz promieniowy ~10 um (klasa CN).

Uruchomienie: Utilities -> ADD-INS -> Scripts and Add-Ins -> zakladka Scripts
-> "+" (My Scripts) -> wskaz folder Lozysko608ZZ -> Run.
"""

import math
import traceback

import adsk.core
import adsk.fusion

# =============================================================================
#  PARAMETRY (mm)
# =============================================================================
d, D, B = 8.0, 22.0, 7.0        # otwor, srednica zewn., szerokosc
RS = 0.3                        # promien naroza (r_s min)

DW = 3.969                      # srednica kulki (5/32")
N_BALLS = 7
DPW = 15.0                      # srednica podzialowa
CLEAR = 0.010                   # luz promieniowy (calkowity)
F_IN, F_OUT = 0.52, 0.53        # wspolczynniki przylegania rowkow (r_rowka / Dw)

R_IL = 12.1 / 2                 # odsadzenie pierscienia wewn. (d1)
R_NOTCH = 5.85                  # podciecie labiryntu na pierscieniu wewn.
NOTCH_T = 0.55                  # glebokosc (osiowo) podciecia od czola
IN_CH = 0.15                    # fazka krawedzi podciecia

R_OL = 17.6 / 2                 # bieznia zewn. - czop (otwor pierscienia zewn.)
R_REC = 19.2 / 2                # gniazdo oslony (D2)
R_UC = 9.75                     # podciecie pod zawalcowany brzeg oslony
T_UC = 0.40                     # glebokosc do podciecia od czola
T_REC = 0.70                    # glebokosc gniazda oslony od czola
OUT_CH = 0.10                   # fazka wejsciowa gniazda oslony

# oslona ZZ: przekroj (r, t) - t = odleglosc od czola lozyska
SHIELD_SECTION = [
    (6.00, 0.15), (8.45, 0.15), (8.75, T_UC), (R_UC, T_UC),
    (R_UC, T_REC), (8.65, T_REC), (8.35, 0.45), (6.00, 0.45),
]

# koszyk wstazkowy
CAGE_RI, CAGE_RO = 6.80, 8.20   # zakres promieniowy tasmy koszyka
CAGE_POCKET = DW / 2 + 0.08     # promien kieszeni (luz 0,08)
CAGE_SHEET = 0.30               # grubosc blachy
RIVET_R, RIVET_H = 0.65, 0.20   # lby nitow

# =============================================================================
#  GEOMETRIA (czysty Python - wspolna dla Fusion i wersji CadQuery)
#  Kontur = lista (punkt, srodek_luku): odcinek od punktu do nastepnego jest
#  lukiem przez srodek_luku albo prosta (None). Punkty (r, z) w mm.
# =============================================================================
H = B / 2
R_BALL = DW / 2
R_PITCH = DPW / 2
R_IN_BOTTOM = R_PITCH - R_BALL - CLEAR / 2      # dno biezni wewn.
R_OUT_BOTTOM = R_PITCH + R_BALL + CLEAR / 2     # dno biezni zewn.


def groove_dz(r_bottom, radius, r_land, outward):
    """polowa szerokosci rowka na czopie r_land (rowek o promieniu radius, dno r_bottom)"""
    rc = r_bottom + radius if outward else r_bottom - radius
    return math.sqrt(radius ** 2 - (rc - r_land) ** 2)


def fillet_mid(corner, sr, sz, r=RS):
    """srodek luku zaokraglenia naroza corner; sr, sz = kierunki do wnetrza (+-1)"""
    c = 1.0 - math.sqrt(0.5)
    return (corner[0] + sr * r * c, corner[1] + sz * r * c)


def sym_loop(half, bridge_mid, close_mid=None):
    """zamkniety kontur symetryczny wzgledem z = 0 z polowki z > 0.
    bridge_mid - srodek odcinka od ostatniego punktu do jego odbicia,
    close_mid  - srodek odcinka od odbicia pierwszego punktu do pierwszego"""
    mir = lambda q: None if q is None else (q[0], -q[1])
    loop = list(half[:-1]) + [(half[-1][0], bridge_mid)]
    for i in range(len(half) - 1, 0, -1):
        loop.append((mir(half[i][0]), mir(half[i - 1][1])))
    loop.append((mir(half[0][0]), close_mid))
    return loop


def inner_ring_loop():
    rb = d / 2
    dz = groove_dz(R_IN_BOTTOM, F_IN * DW, R_IL, True)
    half = [
        ((rb, H - RS), fillet_mid((rb, H), 1, -1)),
        ((rb + RS, H), None),
        ((R_NOTCH - IN_CH, H), None),
        ((R_NOTCH, H - IN_CH), None),
        ((R_NOTCH, H - NOTCH_T), None),
        ((R_IL, H - NOTCH_T), None),
        ((R_IL, dz), None),
    ]
    return sym_loop(half, (R_IN_BOTTOM, 0.0))


def outer_ring_loop():
    ro = D / 2
    dz = groove_dz(R_OUT_BOTTOM, F_OUT * DW, R_OL, False)
    half = [
        ((ro, H - RS), fillet_mid((ro, H), -1, -1)),
        ((ro - RS, H), None),
        ((R_REC + OUT_CH, H), None),
        ((R_REC, H - OUT_CH), None),
        ((R_REC, H - T_UC), None),
        ((R_UC, H - T_UC), None),
        ((R_UC, H - T_REC), None),
        ((R_OL, H - T_REC), None),
        ((R_OL, dz), None),
    ]
    return sym_loop(half, (R_OUT_BOTTOM, 0.0))


def shield_loop(side=1):
    """oslona przy czole z = side * H"""
    return [((r, side * (H - t)), None) for r, t in SHIELD_SECTION]


def cage_web_loop():
    """plaska czesc koszyka (dwie blachy) - przekroj (r, z)"""
    return [((CAGE_RI, -CAGE_SHEET), None), ((CAGE_RO, -CAGE_SHEET), None),
            ((CAGE_RO, CAGE_SHEET), None), ((CAGE_RI, CAGE_SHEET), None)]


def cage_band_loop():
    """pierscien ograniczajacy koszyk promieniowo"""
    zz = CAGE_POCKET + CAGE_SHEET + 0.5
    return [((CAGE_RI, -zz), None), ((CAGE_RO, -zz), None),
            ((CAGE_RO, zz), None), ((CAGE_RI, zz), None)]


def ball_angle(k):
    return 2 * math.pi * k / N_BALLS


def ball_centers():
    return [(R_PITCH * math.cos(ball_angle(k)), R_PITCH * math.sin(ball_angle(k)), 0.0)
            for k in range(N_BALLS)]


def rivet_centers():
    a = [ball_angle(k) + math.pi / N_BALLS for k in range(N_BALLS)]
    return [(R_PITCH * math.cos(t), R_PITCH * math.sin(t)) for t in a]


# =============================================================================
#  FUSION 360
# =============================================================================
def mm(v):
    return v / 10.0


def P(x, y, z):
    return adsk.core.Point3D.create(mm(x), mm(y), mm(z))


def vi(v_mm):
    return adsk.core.ValueInput.createByReal(mm(v_mm))


class Builder(object):
    def __init__(self, app, design):
        self.app = app
        self.design = design
        self.root = design.rootComponent
        self.warnings = []
        self._planes = {}
        self.NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        self.JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation
        self.CUT = adsk.fusion.FeatureOperations.CutFeatureOperation
        self.INTERSECT = adsk.fusion.FeatureOperations.IntersectFeatureOperation
        self.parts = {}

    # ------------------------------------------------------------ ogolne ---
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

    def plane_z(self, comp, z):
        """plaszczyzna z = const w komponencie (znak odsuniecia sprawdzany na geometrii)"""
        if abs(z) < 1e-9:
            return comp.xYConstructionPlane
        k = (id(comp), round(z, 4))
        if k in self._planes:
            return self._planes[k]
        planes = comp.constructionPlanes
        for sign in (1, -1):
            inp = planes.createInput()
            inp.setByOffset(comp.xYConstructionPlane, vi(sign * z))
            cp = planes.add(inp)
            if abs(cp.geometry.origin.z - mm(z)) < 1e-6:
                cp.isLightBulbOn = False
                self._planes[k] = cp
                return cp
            cp.deleteMe()
        raise RuntimeError('nie udalo sie utworzyc plaszczyzny z=%g' % z)

    # -------------------------------------------------------------- szkice ---
    @staticmethod
    def _near(curve, p):
        s, e = curve.startSketchPoint, curve.endSketchPoint
        return s if s.geometry.distanceTo(p) < e.geometry.distanceTo(p) else e

    def draw_loop(self, sk, loop, to3d):
        """zamkniety kontur z odcinkow i lukow; to3d(u, v) -> (x, y, z) mm modelu.
        Kolejne krzywe sa laczone wspolnymi punktami szkicu. Zwraca liste krzywych."""
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

    def revolve(self, comp, prof, axis_line, op=None, name=None):
        rv = comp.features.revolveFeatures
        inp = rv.createInput(prof, axis_line, op or self.NEW)
        inp.setAngleExtent(False, adsk.core.ValueInput.createByString('360 deg'))
        f = rv.add(inp)
        b = f.bodies.item(0)
        if name:
            b.name = name
        return b

    def revolve_section(self, comp, loop, name, sk_name):
        """bryla obrotowa wokol osi Z z konturu (r, z)"""
        sk = comp.sketches.add(comp.xZConstructionPlane)
        sk.name = sk_name
        self.draw_loop(sk, loop, lambda r, z: (r, 0.0, z))
        ax = sk.sketchCurves.sketchLines.addByTwoPoints(sk.modelToSketchSpace(P(0, 0, -H - 1)),
                                                        sk.modelToSketchSpace(P(0, 0, H + 1)))
        ax.isConstruction = True
        return self.revolve(comp, sk.profiles.item(0), ax, name=name)

    def sphere(self, comp, c, r, name, sk_name):
        """kula: polkole w plaszczyznie z = c.z obrocone wokol swojej cieciwy.
        Cieciwa (os obrotu) lezy promieniowo, wiec bieguny kuli sa daleko od
        krawedzi koszyka i biezni (stabilne operacje logiczne)."""
        sk = comp.sketches.add(self.plane_z(comp, c[2]))
        sk.name = sk_name
        cx, cy, cz = c
        L = math.hypot(cx, cy)
        ux, uy = cx / L, cy / L
        loop = [((cx - r * ux, cy - r * uy), (cx - r * uy, cy + r * ux)),
                ((cx + r * ux, cy + r * uy), None)]
        axis = self.draw_loop(sk, loop, lambda x, y: (x, y, cz))[-1]
        return self.revolve(comp, sk.profiles.item(0), axis, name=name)

    def combine(self, comp, target, tools, op, keep=False):
        col = adsk.core.ObjectCollection.create()
        for t in tools:
            col.add(t)
        ci = comp.features.combineFeatures.createInput(target, col)
        ci.operation = op
        ci.isKeepToolBodies = keep
        return comp.features.combineFeatures.add(ci)

    # =========================================================== MODEL ===
    def inner_ring(self):
        occ = self.new_component('Pierscien wewnetrzny')
        self.revolve_section(occ.component, inner_ring_loop(), 'Pierscien wewnetrzny', 'Przekroj')
        return occ

    def outer_ring(self):
        occ = self.new_component('Pierscien zewnetrzny')
        self.revolve_section(occ.component, outer_ring_loop(), 'Pierscien zewnetrzny', 'Przekroj')
        return occ

    def balls(self):
        occ = self.new_component('Kulka 3,969 (5-32 in)')
        comp = occ.component
        self.sphere(comp, ball_centers()[0], R_BALL, 'Kulka', 'Kulka')
        occs = [occ]
        for k in range(1, N_BALLS):
            m = adsk.core.Matrix3D.create()
            m.setToRotation(ball_angle(k), adsk.core.Vector3D.create(0, 0, 1),
                            adsk.core.Point3D.create(0, 0, 0))
            occs.append(self.root.occurrences.addExistingComponent(comp, m))
        return occs

    def cage(self):
        occ = self.new_component('Koszyk')
        comp = occ.component
        web = self.revolve_section(comp, cage_web_loop(), 'Koszyk', 'Blacha')
        shells = [self.sphere(comp, c, CAGE_POCKET + CAGE_SHEET, 'kieszen', 'Kieszen %d' % (i + 1))
                  for i, c in enumerate(ball_centers())]
        self.combine(comp, web, shells, self.JOIN)
        band = self.revolve_section(comp, cage_band_loop(), 'tasma', 'Tasma')
        self.combine(comp, web, [band], self.INTERSECT)
        pockets = [self.sphere(comp, c, CAGE_POCKET, 'wnetrze', 'Wnetrze kieszeni %d' % (i + 1))
                   for i, c in enumerate(ball_centers())]
        self.combine(comp, web, pockets, self.CUT)

        def rivets():
            ext = comp.features.extrudeFeatures
            for s in (1, -1):
                sk = comp.sketches.add(self.plane_z(comp, s * CAGE_SHEET))
                sk.name = 'Nity %s' % ('gora' if s > 0 else 'dol')
                for x, y in rivet_centers():
                    sk.sketchCurves.sketchCircles.addByCenterRadius(
                        sk.modelToSketchSpace(P(x, y, s * CAGE_SHEET)), mm(RIVET_R))
                col = adsk.core.ObjectCollection.create()
                for pr in sk.profiles:
                    col.add(pr)
                n = sk.modelToSketchSpace(P(0, 0, s * CAGE_SHEET + s))
                o = sk.modelToSketchSpace(P(0, 0, s * CAGE_SHEET))
                dirn = adsk.fusion.ExtentDirections.PositiveExtentDirection if n.z - o.z > 0 \
                    else adsk.fusion.ExtentDirections.NegativeExtentDirection
                inp = ext.createInput(col, self.JOIN)
                inp.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(vi(RIVET_H)), dirn)
                inp.participantBodies = [web]
                ext.add(inp)
        self.safe('Nity koszyka', rivets)
        return occ

    def shields(self):
        occ = self.new_component('Oslona ZZ')
        self.revolve_section(occ.component, shield_loop(1), 'Oslona ZZ', 'Przekroj')
        m = adsk.core.Matrix3D.create()
        m.setToRotation(math.pi, adsk.core.Vector3D.create(1, 0, 0), adsk.core.Point3D.create(0, 0, 0))
        return [occ, self.root.occurrences.addExistingComponent(occ.component, m)]

    # ------------------------------------------------ material / wyglad ---
    def _lib(self, libs, names):
        for nm in names:
            try:
                lib = libs.itemByName(nm)
            except Exception:
                lib = None
            if lib:
                return lib
        return None

    def materials(self, items):
        libs = self.app.materialLibraries
        mlib = self._lib(libs, ('Fusion Material Library', 'Fusion 360 Material Library'))
        steel = None
        if mlib:
            for nm in ('Steel', 'Steel, Alloy', 'Steel AISI 52100'):
                steel = steel or mlib.materials.itemByName(nm)
        alib = self._lib(libs, ('Fusion Appearance Library', 'Fusion 360 Appearance Library'))
        for comp, looks in items:
            if comp is None:
                continue
            look = None
            if alib:
                for nm in looks:
                    look = look or alib.appearances.itemByName(nm)
            if look:
                da = self.design.appearances.itemByName(look.name)
                look = da or self.design.appearances.addByCopy(look, look.name)
            for body in comp.bRepBodies:
                if steel:
                    body.material = steel
                if look:
                    body.appearance = look

    def run(self):
        self.parts['wew'] = self.inner_ring()
        self.parts['zew'] = self.outer_ring()
        self.parts['kulki'] = self.balls()
        self.parts['koszyk'] = self.safe('Koszyk', self.cage)
        self.parts['oslony'] = self.safe('Oslony', self.shields)
        comp = lambda o: None if o is None else (o[0] if isinstance(o, list) else o).component
        self.safe('Materialy', self.materials, [
            (comp(self.parts['wew']), ('Steel - Satin', 'Steel - Polished')),
            (comp(self.parts['zew']), ('Steel - Satin', 'Steel - Polished')),
            (comp(self.parts['kulki']), ('Chrome - Polished', 'Steel - Polished', 'Steel - Mirror')),
            (comp(self.parts['koszyk']), ('Steel - Brushed Linear', 'Steel - Satin')),
            (comp(self.parts['oslony']), ('Steel - Brushed Circular', 'Steel - Satin')),
        ])


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        design.designType = adsk.fusion.DesignTypes.ParametricDesignType
        design.fusionUnitsManager.distanceDisplayUnits = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
        design.rootComponent.name = 'Lozysko 608ZZ'

        b = Builder(app, design)
        b.run()
        try:
            app.activeViewport.fit()
        except Exception:
            pass
        msg = 'Lozysko 608ZZ (8 x 22 x 7) gotowe.'
        try:
            msg += '\nMasa: %.1f g (SKF 608-2Z: 12 g)' % (design.rootComponent.physicalProperties.mass * 1000)
        except Exception:
            pass
        msg += ('\n\nPrzekroj: Inspect -> Section Analysis na plaszczyznie XZ.'
                '\nOslony mozna ukryc (oko przy "Oslona ZZ"), zeby zobaczyc kulki i koszyk.')
        if b.warnings:
            msg += '\n\nOstrzezenia (pominiete detale):\n- ' + '\n- '.join(b.warnings)
        ui.messageBox(msg, 'Lozysko 608ZZ')
    except Exception:
        if ui:
            ui.messageBox('Blad:\n{}'.format(traceback.format_exc()), 'Lozysko 608ZZ')
