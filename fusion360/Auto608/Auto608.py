# -*- coding: utf-8 -*-
"""
Auto608 - skrypt Autodesk Fusion 360

Buduje model autka-spinnera (wg zdjec rzutow) z gniazdem na lozysko 608
(8 x 22 x 7 mm) na masce, nakretke spinnera oraz bryle referencyjna lozyska.

Uklad wspolrzednych modelu:
    X = dlugosc  (0 = przedni zderzak, +X w strone tylu)
    Y = szerokosc (0 = os symetrii)
    Z = wysokosc  (0 = podloze / spod auta)
Wszystkie wymiary w mm (API Fusion pracuje w cm - przeliczane w mm()).

Nadwozie:
  * dolna czesc  - loft przez przekroje poprzeczne (poszerzone blotniki nad
                   kolami, wezsze drzwi, zwezajacy sie przod i tyl),
  * kabina       - loft przez przekroje poziome (zaokraglony dach, fastback),
  * szyby        - plytkie wglebienia w "skorce" kabiny (kabina - kabina wewn.),
  * kola         - wystajace, w glebokich nadkolach, felgi 5 x podwojne ramie.

Uruchomienie: Utilities -> ADD-INS -> Scripts and Add-Ins -> zakladka Scripts
-> "+" (My Scripts) -> wskaz folder Auto608 -> Run.
"""

import math
import traceback

import adsk.core
import adsk.fusion

# =============================================================================
#  PARAMETRY (mm)
# =============================================================================
L = 72.0            # dlugosc nadwozia
HOOD_Z = 13.0       # wysokosc maski w miejscu lozyska

# --- lozysko 608 i gniazdo (gniazdo sterowane parametrami uzytkownika Fusion)
BRG_D, BRG_d, BRG_W = 22.0, 8.0, 7.0
BRG_X = 15.7            # srodek lozyska (nad przednia osia)
BRG_FIT_D = 22.15       # srednica gniazda  -> parametr "lozysko_gniazdo_D"
BRG_DEPTH = 3.0         # glebokosc gniazda -> parametr "lozysko_glebokosc"
BRG_RELIEF_D = 17.0     # podciecie pod pierscien wewn. -> "lozysko_podciecie_D"
BRG_RELIEF_H = 1.0      # glebokosc podciecia         -> "lozysko_podciecie_h"
BRG_CHAMFER = 0.5       # fazka wejsciowa gniazda

# --- kola
WHEEL_R = 5.8
WHEEL_X = (15.7, 60.0)
WHEEL_Y_OUT = 20.0      # zewnetrzna powierzchnia kola (|y|)
WHEEL_Y_IN = 15.0       # wewnetrzna powierzchnia kola (|y|) - wchodzi w nadwozie
ARCH_R = 6.7            # promien nadkola
ARCH_Y = 15.2           # dno nadkola (|y|)

JOIN_WHEELS = True      # True = kola polaczone z nadwoziem (druk w 1 kawalku)
MAKE_CAP = True         # nakretka spinnera (drukowana osobno)
MAKE_BEARING_REF = True # bryla lozyska 608 do podgladu

# --- dolna czesc nadwozia: przekroje poprzeczne
# (x, w = pol-szerokosc boku, wb = pol-szerokosc spodu, h = wysokosc gory,
#  c = wysokosc fazy barku, rise = przetloczenie blotnika ponad maske)
LOWER_KEYS = [
    (0.0,  16.0, 13.6,  9.8, 2.4, 0.0),
    (1.8,  17.6, 15.0, 11.8, 2.8, 0.4),
    (6.0,  18.7, 16.0, 13.0, 3.0, 1.1),
    (15.7, 19.1, 16.4, 13.0, 3.0, 1.3),
    (24.0, 18.8, 16.2, 13.0, 3.0, 1.3),
    (30.0, 18.0, 16.0, 14.0, 2.6, 0.2),
    (38.0, 17.8, 15.9, 14.2, 2.4, 0.1),
    (48.0, 17.9, 16.0, 14.3, 2.4, 0.1),
    (53.5, 18.8, 16.4, 14.5, 2.5, 0.1),
    (60.0, 19.3, 16.7, 14.7, 2.6, 0.1),
    (66.5, 19.1, 16.6, 14.8, 2.6, 0.1),
    (70.6, 18.8, 16.3, 14.5, 2.4, 0.0),
    (72.0, 18.0, 15.6, 13.6, 2.2, 0.0),
]

# --- kabina: przekroje poziome (z, x_przod, x_tyl, pol-szerokosc, faza_przod, faza_tyl)
CABIN_KEYS = [
    (12.6, 27.2, 65.0, 16.8, 3.0, 4.0),
    (14.6, 27.6, 63.9, 16.6, 3.0, 4.0),
    (17.0, 29.7, 61.8, 16.2, 3.0, 4.0),
    (20.0, 32.3, 58.9, 15.6, 3.0, 4.0),
    (22.8, 35.0, 55.6, 14.8, 3.0, 3.6),
    (24.0, 37.0, 53.4, 14.0, 2.8, 3.0),
    (24.7, 39.0, 51.0, 13.0, 2.6, 2.6),
    (25.0, 41.0, 48.5, 11.8, 2.2, 2.2),
]
SKIN = 0.5              # glebokosc szyb / zeberek (grubosc "skorki" kabiny)

# --- spoiler "kaczy ogon": skrzydlo + dwie plytki boczne (profil boczny x,z)
SPOILER_WING = [(63.6, 17.6), (70.4, 17.6), (70.4, 19.0), (64.8, 19.0)]
SPOILER_WING_HALF_W = 13.2
SPOILER_PLATE = [(63.0, 14.0), (70.4, 14.0), (70.4, 20.0), (65.6, 20.0)]
SPOILER_PLATE_Y = (10.0, 13.2)          # plytki boczne: zakres |y|


# =============================================================================
#  GEOMETRIA (czysty Python - wspolna dla Fusion i wersji CadQuery)
# =============================================================================
def lerp(a, b, t):
    return a + (b - a) * t


def lower_section(key):
    """zamkniety wielokat (y, z) przekroju poprzecznego dolnej czesci"""
    x, w, wb, h, c, rise = key
    half = [(wb, 0.0), (w, 2.2), (w, h - c), (w - 0.8 * c, h + rise), (w - 0.8 * c - 2.0, h)]
    return half + [(-y, z) for y, z in reversed(half)]


def cabin_section(key, shrink=0.0):
    """zamkniety osmiokat (x, y) przekroju poziomego kabiny"""
    z, xf, xr, hw, kf, kr = key
    xf, xr, hw = xf + shrink, xr - shrink, hw - shrink
    return [(xf, -(hw - kf)), (xf, hw - kf), (xf + kf, hw), (xr - kr, hw),
            (xr, hw - kr), (xr, -(hw - kr)), (xr - kr, -hw), (xf + kf, -hw)]


def cabin_keys(shrink=0.0):
    """przekroje kabiny; dla shrink > 0 - kabina wewnetrzna (gorne przekroje obnizone)"""
    if not shrink:
        return list(CABIN_KEYS)
    return [(z - shrink if z > 23.0 else z,) + tuple(k[1:]) for k in CABIN_KEYS for z in (k[0],)]


def _interp(keys, idx_in, idx_out, v):
    for a, b in zip(keys, keys[1:]):
        if a[idx_in] <= v <= b[idx_in]:
            t = (v - a[idx_in]) / (b[idx_in] - a[idx_in])
            return lerp(a[idx_out], b[idx_out], t)
    return keys[0][idx_out] if v < keys[0][idx_in] else keys[-1][idx_out]


def cabin_xf(z):
    return _interp(CABIN_KEYS, 0, 1, z)


def cabin_xr(z):
    return _interp(CABIN_KEYS, 0, 2, z)


def cabin_hw(z):
    return _interp(CABIN_KEYS, 0, 3, z)


def side_windows():
    """szyby boczne: wielokaty (x, z) - rzut z boku"""
    zb, zt = 14.9, 20.2
    return [
        [(cabin_xf(zb) + 2.6, zb), (47.4, zb), (47.4, zt), (cabin_xf(zt) + 2.6, zt)],
    ]


def windshield():
    """szyba przednia: wielokat (y, z) - rzut z przodu"""
    z0, z1 = 15.2, 23.4
    b0, b1 = cabin_hw(z0) - 1.7, cabin_hw(z1) - 1.9
    return [(-b0, z0), (b0, z0), (b1, z1), (-b1, z1)]


def rear_windows():
    """szyba tylna (dwie tafle obok pasa): wielokaty (y, z) - rzut z tylu"""
    z0, z1 = 17.0, 23.6
    out = []
    for s in (1, -1):
        out.append([(s * 5.0, z0), (s * (cabin_hw(z0) - 1.8), z0),
                    (s * (cabin_hw(z1) - 1.8), z1), (s * 5.0, z1)])
    return out


def stripe_ribs():
    """zeberka pasa na dachu i tylnej szybie: przedzialy x"""
    return [(37.6 + i * 1.5, 38.2 + i * 1.5) for i in range(16)]


STRIPE_HALF_W = 4.5

# szczegoly przodu / tylu: prostokaty (y0, y1, z0, z1, glebokosc)
FRONT_RECESSES = [
    (-11.0, 11.0, 3.2, 6.3, 1.5),       # wlot powietrza
]
REAR_RECESSES = [
    (-14.5, 14.5, 5.9, 11.0, 0.4),      # panel lamp
    (-12.4, 12.4, 6.7, 9.5, 1.5),       # listwa swietlna
    (7.6, 12.0, 1.5, 3.5, 0.5),         # wydech P - oslona
    (-12.0, -7.6, 1.5, 3.5, 0.5),       # wydech L - oslona
    (8.1, 11.5, 1.9, 3.1, 2.5),         # wydech P - koncowka
    (-11.5, -8.1, 1.9, 3.1, 2.5),       # wydech L - koncowka
    (-7.0, 7.0, 0.9, 3.4, 0.6),         # dyfuzor
]
DOOR_LINES_X = (30.0, 48.0)
DOOR_LINE_W, DOOR_LINE_DEPTH = 0.4, 0.35
DOOR_LINE_Z = (2.4, 13.6)


def wheel_sectors():
    """wglebienia felgi: (r_wew, r_zew, kat0, kat1) - 5 podwojnych ramion"""
    out = []
    for k in range(5):
        t = math.radians(72 * k + 90)
        out.append((1.7, 4.4, t + math.radians(8.5), t + math.radians(72 - 8.5)))
        out.append((2.6, 4.4, t - math.radians(3.2), t + math.radians(3.2)))
    return out


WHEEL_RIM_GROOVE = (4.75, 5.05, 0.3)    # rowek opona/felga (r0, r1, glebokosc)
WHEEL_DISH_DEPTH = 0.9
WHEEL_HUB_HOLE = (0.6, 1.0)             # (promien, glebokosc)
WHEEL_TIRE_CHAMFER = 0.6                # zaokraglenie/faza opony


def cap_sectors():
    """wglebienia nakretki spinnera (felga 5 ramion)"""
    out = []
    for k in range(5):
        t = math.radians(72 * k + 90)
        out.append((2.5, 8.0, t + math.radians(9), t + math.radians(72 - 9)))
    return out


# =============================================================================
#  FUSION 360
# =============================================================================
def mm(v):
    return v / 10.0


def P(x, y, z):
    return adsk.core.Point3D.create(mm(x), mm(y), mm(z))


def vi(v_mm):
    return adsk.core.ValueInput.createByReal(mm(v_mm))


def V3(x, y, z):
    return adsk.core.Vector3D.create(float(x), float(y), float(z))


BODY_NAME = 'Karoseria'


class Builder(object):
    def __init__(self, app, design):
        self.app = app
        self.design = design
        self.root = design.rootComponent
        self.feats = self.root.features
        self.ext = self.feats.extrudeFeatures
        self.warnings = []
        self._planes = {}
        self.NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
        self.JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation
        self.CUT = adsk.fusion.FeatureOperations.CutFeatureOperation
        self.INTERSECT = adsk.fusion.FeatureOperations.IntersectFeatureOperation

    # ------------------------------------------------------------ ogolne ---
    @property
    def body(self):
        return self.root.bRepBodies.itemByName(BODY_NAME)

    def safe(self, label, fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Exception:
            self.warnings.append('%s: %s' % (label, traceback.format_exc().strip().splitlines()[-1]))
            return None

    def param(self, name, value_mm, comment):
        ups = self.design.userParameters
        if ups.itemByName(name) is None:
            ups.add(name, adsk.core.ValueInput.createByString('%g mm' % value_mm), 'mm', comment)
        return name

    # -------------------------------------------------------- plaszczyzny ---
    def _offset_plane(self, base, axis, value):
        """plaszczyzna rownolegla do bazowej przez axis=value (mm); znak odsuniecia
        sprawdzany na geometrii (niezaleznie od kierunku normalnej plaszczyzny)"""
        k = (axis, round(value, 4))
        if k in self._planes:
            return self._planes[k]
        if abs(value) < 1e-9:
            self._planes[k] = base
            return base
        planes = self.root.constructionPlanes
        for sign in (1, -1):
            inp = planes.createInput()
            inp.setByOffset(base, vi(sign * value))
            cp = planes.add(inp)
            o = cp.geometry.origin
            got = {'x': o.x, 'y': o.y, 'z': o.z}[axis]
            if abs(got - mm(value)) < 1e-6:
                cp.isLightBulbOn = False
                self._planes[k] = cp
                return cp
            cp.deleteMe()
        raise RuntimeError('nie udalo sie utworzyc plaszczyzny %s=%g' % (axis, value))

    def plane_x(self, x):
        return self._offset_plane(self.root.yZConstructionPlane, 'x', x)

    def plane_y(self, y):
        return self._offset_plane(self.root.xZConstructionPlane, 'y', y)

    def plane_z(self, z):
        return self._offset_plane(self.root.xYConstructionPlane, 'z', z)

    # -------------------------------------------------------------- szkice ---
    def sketch(self, plane, name):
        sk = self.root.sketches.add(plane)
        sk.name = name
        return sk

    @staticmethod
    def to_sk(sk, p):
        return sk.modelToSketchSpace(p)

    def poly(self, sk, pts):
        """zamkniety wielokat; pts = lista (x, y, z) w mm, wsp. modelu"""
        lines = sk.sketchCurves.sketchLines
        sp = [self.to_sk(sk, P(*p)) for p in pts]
        first = prev = None
        for i in range(len(sp)):
            if prev is None:
                prev = first = lines.addByTwoPoints(sp[0], sp[1])
            elif i == len(sp) - 1:
                lines.addByTwoPoints(prev.endSketchPoint, first.startSketchPoint)
            else:
                prev = lines.addByTwoPoints(prev.endSketchPoint, sp[i + 1])

    def circle(self, sk, c, r):
        return sk.sketchCurves.sketchCircles.addByCenterRadius(self.to_sk(sk, P(*c)), mm(r))

    def sector(self, sk, cf, r_in, r_out, a0, a1):
        """wycinek pierscienia; cf(r, kat) -> (x, y, z) mm"""
        arcs = sk.sketchCurves.sketchArcs
        am = 0.5 * (a0 + a1)
        q = lambda r, a: self.to_sk(sk, P(*cf(r, a)))
        o = arcs.addByThreePoints(q(r_out, a0), q(r_out, am), q(r_out, a1))
        i = arcs.addByThreePoints(q(r_in, a0), q(r_in, am), q(r_in, a1))

        def near(arc, p):
            s, e = arc.startSketchPoint, arc.endSketchPoint
            return s if s.geometry.distanceTo(p) < e.geometry.distanceTo(p) else e
        for a in (a0, a1):
            sk.sketchCurves.sketchLines.addByTwoPoints(near(o, q(r_out, a)), near(i, q(r_in, a)))

    @staticmethod
    def normal_of(sk):
        a = sk.sketchToModelSpace(adsk.core.Point3D.create(0, 0, 0))
        b = sk.sketchToModelSpace(adsk.core.Point3D.create(0, 0, 1))
        return a.vectorTo(b)

    @staticmethod
    def all_profiles(sk):
        col = adsk.core.ObjectCollection.create()
        for pr in sk.profiles:
            col.add(pr)
        return col

    # ------------------------------------------------------ operacje -------
    def ext_sym(self, prof, total_mm, op, bodies=None):
        inp = self.ext.createInput(prof, op)
        inp.setSymmetricExtent(vi(total_mm), True)
        if bodies:
            inp.participantBodies = bodies
        return self.ext.add(inp)

    def ext_dir(self, prof, sk, dist, want, op, bodies=None):
        """wyciagniecie o dist (mm lub wyrazenie str) w kierunku wektora want (model)"""
        n = self.normal_of(sk)
        d = adsk.fusion.ExtentDirections.PositiveExtentDirection if n.dotProduct(want) > 0 \
            else adsk.fusion.ExtentDirections.NegativeExtentDirection
        val = adsk.core.ValueInput.createByString(dist) if isinstance(dist, str) else vi(dist)
        inp = self.ext.createInput(prof, op)
        inp.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(val), d)
        if bodies:
            inp.participantBodies = bodies
        return self.ext.add(inp)

    def loft(self, profiles, name):
        lofts = self.feats.loftFeatures
        li = lofts.createInput(self.NEW)
        for pr in profiles:
            li.loftSections.add(pr)
        li.isSolid = True
        f = lofts.add(li)
        b = f.bodies.item(0)
        b.name = name
        return b

    def combine(self, target, tools, op, keep=False):
        col = adsk.core.ObjectCollection.create()
        for t in tools:
            col.add(t)
        ci = self.feats.combineFeatures.createInput(target, col)
        ci.operation = op
        ci.isKeepToolBodies = keep
        return self.feats.combineFeatures.add(ci)

    def remove(self, body):
        try:
            self.feats.removeFeatures.add(body)
        except Exception:
            body.isLightBulbOn = False

    def chamfer_circle(self, body, radius, axis, value, dist):
        """fazka na krawedzi-okregu o promieniu radius, lezacej w plaszczyznie axis=value"""
        edges = adsk.core.ObjectCollection.create()
        for e in body.edges:
            g = e.geometry
            if g.curveType != adsk.core.Curve3DTypes.Circle3DCurveType:
                continue
            c = {'x': g.center.x, 'y': g.center.y, 'z': g.center.z}[axis]
            if abs(g.radius - mm(radius)) < 1e-4 and abs(c - mm(value)) < 1e-4:
                edges.add(e)
        if edges.count == 0:
            raise RuntimeError('brak krawedzi do fazowania')
        ch = self.feats.chamferFeatures
        try:
            inp = ch.createInput2()
            inp.chamferEdgeSets.addEqualDistanceChamferEdgeSet(edges, vi(dist), False)
        except Exception:
            inp = ch.createInput(edges, False)
            inp.setToEqualDistance(vi(dist))
        return ch.add(inp)

    # =========================================================== MODEL ===
    def lower_body(self):
        profs = []
        for k in LOWER_KEYS:
            sk = self.sketch(self.plane_x(k[0]), 'Przekroj x=%g' % k[0])
            self.poly(sk, [(k[0], y, z) for y, z in lower_section(k)])
            profs.append(sk.profiles.item(0))
        self.loft(profs, BODY_NAME)

    def cabin(self):
        profs = []
        for k in cabin_keys():
            sk = self.sketch(self.plane_z(k[0]), 'Kabina z=%g' % k[0])
            self.poly(sk, [(x, y, k[0]) for x, y in cabin_section(k)])
            profs.append(sk.profiles.item(0))
        cab = self.loft(profs, 'Kabina')
        skin = self.loft(profs, 'Kabina - skorka')
        inner = []
        for k in cabin_keys(SKIN):
            sk = self.sketch(self.plane_z(k[0]), 'Kabina wewn. z=%g' % k[0])
            self.poly(sk, [(x, y, k[0]) for x, y in cabin_section(k, SKIN)])
            inner.append(sk.profiles.item(0))
        inn = self.loft(inner, 'Kabina - wewn')
        self.combine(skin, [inn], self.CUT)
        self.combine(self.body, [cab], self.JOIN)
        return skin

    def glass(self, skin):
        """szyby i zeberka pasa = (graniastoslupy z rzutow) x skorka kabiny"""
        tools = []
        for s in (1, -1):
            sk = self.sketch(self.plane_y(s * 6.0), 'Szyby boczne ' + ('P' if s > 0 else 'L'))
            for pts in side_windows():
                self.poly(sk, [(x, s * 6.0, z) for x, z in pts])
            tools.append(self.ext_dir(self.all_profiles(sk), sk, 20, V3(0, s, 0), self.NEW).bodies.item(0))
        sk = self.sketch(self.plane_x(20.0), 'Szyba przednia')
        self.poly(sk, [(20.0, y, z) for y, z in windshield()])
        tools.append(self.ext_dir(sk.profiles.item(0), sk, 22, V3(1, 0, 0), self.NEW).bodies.item(0))
        sk = self.sketch(self.plane_x(47.0), 'Szyba tylna')
        for pts in rear_windows():
            self.poly(sk, [(47.0, y, z) for y, z in pts])
        tools.append(self.ext_dir(self.all_profiles(sk), sk, 24, V3(1, 0, 0), self.NEW).bodies.item(0))
        sk = self.sketch(self.plane_z(19.0), 'Pas - zeberka')
        for x0, x1 in stripe_ribs():
            self.poly(sk, [(x0, -STRIPE_HALF_W, 19), (x1, -STRIPE_HALF_W, 19),
                           (x1, STRIPE_HALF_W, 19), (x0, STRIPE_HALF_W, 19)])
        tools.append(self.ext_dir(self.all_profiles(sk), sk, 11, V3(0, 0, 1), self.NEW).bodies.item(0))

        tool = tools[0]
        tool.name = 'Szyby - narzedzie'
        self.combine(tool, tools[1:], self.JOIN)
        self.combine(tool, [skin], self.INTERSECT, keep=True)
        self.combine(self.body, [tool], self.CUT)

    def front_rear(self):
        for i, (y0, y1, z0, z1, d) in enumerate(FRONT_RECESSES):
            sk = self.sketch(self.plane_x(0.0), 'Przod %d' % (i + 1))
            self.poly(sk, [(0, y0, z0), (0, y1, z0), (0, y1, z1), (0, y0, z1)])
            self.safe('Przod %d' % (i + 1), self.ext_dir, sk.profiles.item(0), sk, d, V3(1, 0, 0),
                      self.CUT, [self.body])
        for i, (y0, y1, z0, z1, d) in enumerate(REAR_RECESSES):
            sk = self.sketch(self.plane_x(L), 'Tyl %d' % (i + 1))
            self.poly(sk, [(L, y0, z0), (L, y1, z0), (L, y1, z1), (L, y0, z1)])
            self.safe('Tyl %d' % (i + 1), self.ext_dir, sk.profiles.item(0), sk, d, V3(-1, 0, 0),
                      self.CUT, [self.body])

    def door_lines(self):
        z0, z1 = DOOR_LINE_Z
        for s in (1, -1):
            for x in DOOR_LINES_X:
                w = [k for k in LOWER_KEYS if k[0] == x][0][1]
                y = s * (w - DOOR_LINE_DEPTH)
                sk = self.sketch(self.plane_y(y), 'Linia drzwi x=%g %s' % (x, 'P' if s > 0 else 'L'))
                x0, x1 = x - DOOR_LINE_W / 2, x + DOOR_LINE_W / 2
                self.poly(sk, [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)])
                self.safe('Linia drzwi', self.ext_dir, sk.profiles.item(0), sk, 6, V3(0, s, 0),
                          self.CUT, [self.body])

    def spoiler(self):
        y0, y1 = SPOILER_PLATE_Y
        for s in (1, -1):
            sk = self.sketch(self.plane_y(s * y0), 'Spoiler plytka ' + ('P' if s > 0 else 'L'))
            self.poly(sk, [(x, s * y0, z) for x, z in SPOILER_PLATE])
            self.ext_dir(sk.profiles.item(0), sk, y1 - y0, V3(0, s, 0), self.JOIN, [self.body])
        sk = self.sketch(self.root.xZConstructionPlane, 'Spoiler skrzydlo')
        self.poly(sk, [(x, 0, z) for x, z in SPOILER_WING])
        self.ext_sym(sk.profiles.item(0), 2 * SPOILER_WING_HALF_W, self.JOIN, [self.body])

    def bearing_seat(self):
        pD = self.param('lozysko_gniazdo_D', BRG_FIT_D, 'Srednica gniazda lozyska 608 (22 mm + pasowanie)')
        pH = self.param('lozysko_glebokosc', BRG_DEPTH, 'Glebokosc gniazda od powierzchni maski')
        pR = self.param('lozysko_podciecie_D', BRG_RELIEF_D, 'Podciecie pod pierscien wewnetrzny')
        pRh = self.param('lozysko_podciecie_h', BRG_RELIEF_H, 'Glebokosc podciecia')

        sk = self.sketch(self.plane_z(HOOD_Z), 'Gniazdo 608')
        c_out = self.circle(sk, (BRG_X, 0, HOOD_Z), BRG_FIT_D / 2)
        c_in = self.circle(sk, (BRG_X, 0, HOOD_Z), BRG_RELIEF_D / 2)
        for c, pn, off in ((c_out, pD, 14.0), (c_in, pR, 10.0)):
            try:
                c.centerSketchPoint.isFixed = True
                d = sk.sketchDimensions.addDiameterDimension(c, self.to_sk(sk, P(BRG_X + off, off, HOOD_Z)))
                d.parameter.expression = pn
            except Exception:
                self.warnings.append('Wymiar %s nie zostal powiazany z parametrem' % pn)
        disk = [pr for pr in sk.profiles if pr.profileLoops.count == 1][0]
        both = self.all_profiles(sk)
        self.ext_dir(both, sk, pH, V3(0, 0, -1), self.CUT, [self.body]).name = 'Gniazdo 608'
        self.ext_dir(disk, sk, '%s + %s' % (pH, pRh), V3(0, 0, -1), self.CUT, [self.body]).name = 'Podciecie 608'
        # wyrownanie powierzchni wokol lozyska (wszystko ponad maska w obrysie gniazda)
        self.safe('Splaszczenie gniazda', self.ext_dir, both, sk, 8, V3(0, 0, 1), self.CUT, [self.body])

        def chamfer():
            r, c = BRG_FIT_D / 2, BRG_CHAMFER
            sk2 = self.sketch(self.root.xZConstructionPlane, 'Fazka gniazda')
            axis = sk2.sketchCurves.sketchLines.addByTwoPoints(
                self.to_sk(sk2, P(BRG_X, 0, 0)), self.to_sk(sk2, P(BRG_X, 0, 20)))
            axis.isConstruction = True
            self.poly(sk2, [(BRG_X + r, 0, HOOD_Z - c), (BRG_X + r + c + 3, 0, HOOD_Z + 3),
                            (BRG_X + r, 0, HOOD_Z + 3)])
            rv = self.feats.revolveFeatures
            inp = rv.createInput(sk2.profiles.item(0), axis, self.CUT)
            inp.setAngleExtent(False, adsk.core.ValueInput.createByString('360 deg'))
            inp.participantBodies = [self.body]
            rv.add(inp)
        self.safe('Fazka gniazda', chamfer)

    def arches(self):
        for s in (1, -1):
            sk = self.sketch(self.plane_y(s * ARCH_Y), 'Nadkola ' + ('P' if s > 0 else 'L'))
            for x in WHEEL_X:
                self.circle(sk, (x, s * ARCH_Y, WHEEL_R), ARCH_R)
            self.ext_dir(self.all_profiles(sk), sk, 10, V3(0, s, 0), self.CUT, [self.body])

    def wheel(self, x, s):
        name = 'Kolo %s %s' % ('przod' if x < L / 2 else 'tyl', 'P' if s > 0 else 'L')
        y_in, y_out = s * WHEEL_Y_IN, s * WHEEL_Y_OUT
        sk = self.sketch(self.plane_y(y_in), name)
        self.circle(sk, (x, y_in, WHEEL_R), WHEEL_R)
        wb = self.ext_dir(sk.profiles.item(0), sk, WHEEL_Y_OUT - WHEEL_Y_IN, V3(0, s, 0), self.NEW).bodies.item(0)
        wb.name = name
        inward = V3(0, -s, 0)
        cf = lambda r, a: (x + r * math.cos(a), y_out, WHEEL_R + r * math.sin(a))

        def dish():
            sk2 = self.sketch(self.plane_y(y_out), name + ' - felga')
            for r_in, r_out, a0, a1 in wheel_sectors():
                self.sector(sk2, cf, r_in, r_out, a0, a1)
            self.ext_dir(self.all_profiles(sk2), sk2, WHEEL_DISH_DEPTH, inward, self.CUT, [wb])

        def groove():
            r0, r1, d = WHEEL_RIM_GROOVE
            sk3 = self.sketch(self.plane_y(y_out), name + ' - rant')
            self.circle(sk3, (x, y_out, WHEEL_R), r1)
            self.circle(sk3, (x, y_out, WHEEL_R), r0)
            ring = [pr for pr in sk3.profiles if pr.profileLoops.count == 2][0]
            self.ext_dir(ring, sk3, d, inward, self.CUT, [wb])

        def hub():
            hr, hd = WHEEL_HUB_HOLE
            sk4 = self.sketch(self.plane_y(y_out), name + ' - piasta')
            self.circle(sk4, (x, y_out, WHEEL_R), hr)
            self.ext_dir(sk4.profiles.item(0), sk4, hd, inward, self.CUT, [wb])

        self.safe(name + ' felga', dish)
        self.safe(name + ' rant', groove)
        self.safe(name + ' piasta', hub)
        self.safe(name + ' opona', self.chamfer_circle, wb, WHEEL_R, 'y', y_out, WHEEL_TIRE_CHAMFER)
        return wb

    def wheels(self):
        made = [self.wheel(x, s) for s in (1, -1) for x in WHEEL_X]
        if JOIN_WHEELS:
            self.combine(self.body, made, self.JOIN)

    def bearing_ref(self):
        z0 = HOOD_Z - BRG_DEPTH
        sk = self.sketch(self.plane_z(z0), 'Lozysko 608 (ref)')
        self.circle(sk, (BRG_X, 0, z0), BRG_D / 2)
        self.circle(sk, (BRG_X, 0, z0), BRG_d / 2)
        ring = [pr for pr in sk.profiles if pr.profileLoops.count == 2][0]
        b = self.ext_dir(ring, sk, BRG_W, V3(0, 0, 1), self.NEW).bodies.item(0)
        b.name = 'Lozysko 608 (ref)'
        for zz, direction in ((z0, V3(0, 0, 1)), (z0 + BRG_W, V3(0, 0, -1))):
            sk = self.sketch(self.plane_z(zz), 'Lozysko - uszczelka')
            self.circle(sk, (BRG_X, 0, zz), 9.5)
            self.circle(sk, (BRG_X, 0, zz), 6.0)
            r = [pr for pr in sk.profiles if pr.profileLoops.count == 2][0]
            self.ext_dir(r, sk, 0.3, direction, self.CUT, [b])
        return b

    def cap(self):
        zb = HOOD_Z - BRG_DEPTH + BRG_W       # gorna powierzchnia lozyska
        up = V3(0, 0, 1)
        sk = self.sketch(self.plane_z(zb - BRG_W + 0.5), 'Nakretka - trzpien')
        self.circle(sk, (BRG_X, 0, zb - BRG_W + 0.5), 7.95 / 2)
        c = self.ext_dir(sk.profiles.item(0), sk, BRG_W - 0.5, up, self.NEW).bodies.item(0)
        c.name = 'Nakretka spinnera'
        sk = self.sketch(self.plane_z(zb), 'Nakretka - dystans')
        self.circle(sk, (BRG_X, 0, zb), 5.5)
        self.ext_dir(sk.profiles.item(0), sk, 0.5, up, self.JOIN, [c])
        sk = self.sketch(self.plane_z(zb + 0.5), 'Nakretka - tarcza')
        self.circle(sk, (BRG_X, 0, zb + 0.5), 9.6)
        self.ext_dir(sk.profiles.item(0), sk, 3.5, up, self.JOIN, [c])
        zt = zb + 4.0

        def top():
            sk = self.sketch(self.plane_z(zt), 'Nakretka - ramiona')
            cf = lambda r, a: (BRG_X + r * math.cos(a), r * math.sin(a), zt)
            for r_in, r_out, a0, a1 in cap_sectors():
                self.sector(sk, cf, r_in, r_out, a0, a1)
            self.ext_dir(self.all_profiles(sk), sk, 1.2, V3(0, 0, -1), self.CUT, [c])
            sk = self.sketch(self.plane_z(zt), 'Nakretka - piasta')
            self.circle(sk, (BRG_X, 0, zt), 1.0)
            self.ext_dir(sk.profiles.item(0), sk, 1.5, V3(0, 0, -1), self.CUT, [c])
        self.safe('Nakretka - wzor', top)
        return c

    def colors(self, items):
        libs = self.app.materialLibraries
        lib = None
        try:
            lib = libs.itemById('BA5EE55E-9982-449B-9D66-9F036540E140')
        except Exception:
            pass
        for nm in ('Fusion Appearance Library', 'Fusion 360 Appearance Library'):
            if lib is None:
                lib = libs.itemByName(nm)
        if lib is None:
            return
        base = None
        for nm in ('Paint - Enamel Glossy (Yellow)', 'Plastic - Glossy (White)'):
            base = base or lib.appearances.itemByName(nm)
        if base is None:
            return
        for body, name, rgb in items:
            if body is None:
                continue
            a = self.design.appearances.itemByName(name)
            if a is None:
                a = self.design.appearances.addByCopy(base, name)
                for pid in ('opaque_albedo', 'generic_diffuse'):
                    prop = a.appearanceProperties.itemById(pid)
                    if prop:
                        adsk.core.ColorProperty.cast(prop).value = adsk.core.Color.create(rgb[0], rgb[1], rgb[2], 255)
                        break
            body.appearance = a

    def run(self):
        self.lower_body()
        skin = self.cabin()
        self.safe('Szyby', self.glass, skin)
        self.safe('Skorka kabiny', self.remove, skin)
        self.front_rear()
        self.door_lines()
        self.safe('Spoiler', self.spoiler)
        self.bearing_seat()
        self.safe('Nadkola', self.arches)
        self.safe('Kola', self.wheels)
        brg = self.safe('Lozysko ref', self.bearing_ref) if MAKE_BEARING_REF else None
        cap = self.safe('Nakretka', self.cap) if MAKE_CAP else None
        self.safe('Kolory', self.colors, [
            (self.body, 'Auto608 - lakier', (120, 40, 200)),
            (cap, 'Auto608 - czarny', (25, 25, 28)),
            (brg, 'Auto608 - stal', (190, 190, 195)),
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

        b = Builder(app, design)
        b.run()
        try:
            app.activeViewport.fit()
        except Exception:
            pass
        msg = ('Auto608 gotowe.\n\nGniazdo 608 sterowane parametrami (Modify -> Change Parameters):\n'
               '  lozysko_gniazdo_D, lozysko_glebokosc, lozysko_podciecie_D, lozysko_podciecie_h')
        if b.warnings:
            msg += '\n\nOstrzezenia (pominiete detale):\n- ' + '\n- '.join(b.warnings)
        ui.messageBox(msg, 'Auto608')
    except Exception:
        if ui:
            ui.messageBox('Blad:\n{}'.format(traceback.format_exc()), 'Auto608')
