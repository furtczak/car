# -*- coding: utf-8 -*-
"""
Auto608 - skrypt Autodesk Fusion 360

Buduje model autka-spinnera (wg zdjec rzutow) z gniazdem na lozysko 608
(8 x 22 x 7 mm) na masce, nakretke spinnera oraz bryle referencyjna lozyska.

Uklad wspolrzednych modelu:
    X = dlugosc  (0 = przedni zderzak, +X w strone tylu)
    Y = szerokosc (0 = os symetrii)
    Z = wysokosc  (0 = podloze / spod auta)
Wszystkie wymiary ponizej w mm (API Fusion pracuje w cm - przeliczane w mm()).

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
W = 38.0            # szerokosc nadwozia
HOOD_Z = 13.0       # wysokosc (plaska) maski

# lozysko 608 i gniazdo (gniazdo jest sterowane parametrami uzytkownika Fusion)
BRG_D, BRG_d, BRG_W = 22.0, 8.0, 7.0
BRG_X = 15.7            # polozenie srodka lozyska (nad przednia osia)
BRG_FIT_D = 22.15       # srednica gniazda  -> parametr "lozysko_gniazdo_D"
BRG_DEPTH = 3.0         # glebokosc gniazda -> parametr "lozysko_glebokosc"
BRG_RELIEF_D = 17.0     # podciecie pod pierscien wewn. -> "lozysko_podciecie_D"
BRG_RELIEF_H = 1.0      # glebokosc podciecia         -> "lozysko_podciecie_h"
BRG_CHAMFER = 0.5       # fazka wejsciowa gniazda

# kola
WHEEL_R = 6.0
WHEEL_W = 3.4
WHEEL_X = (15.7, 60.0)
WHEEL_PROUD = 0.3       # o ile kolo wystaje poza bok nadwozia
ARCH_R = 6.5            # promien nadkola
ARCH_DEPTH = 2.8        # glebokosc nadkola od boku

JOIN_WHEELS = True      # True = kola polaczone z nadwoziem (druk w 1 kawalku)
MAKE_CAP = True         # nakretka spinnera (drukowana osobno)
MAKE_BEARING_REF = True # bryla lozyska 608 do podgladu

# profil boczny (x, z) - zmierzony ze zdjec, skala z lozyska 608
SIDE = [(0, 1.2), (1.0, 0), (71.0, 0), (72, 1.2), (72, 13.0), (71.0, 14.8),
        (63.5, 14.8), (62.0, 16.3), (52.5, 24.8), (36.2, 24.8), (27.3, HOOD_Z),
        (3.0, HOOD_Z), (1.2, 12.2), (0, 10.2)]
# obrys z gory - polowa (x, y)
TOP_HALF = [(0, 15.5), (4.0, 19.0), (70.0, 19.0), (72.0, 17.8)]
# przekroj poprzeczny - polowa (y, z)
FRONT_HALF = [(18.2, 0), (19.0, 0.8), (19.0, 12.4), (17.0, 14.9),
              (13.0, 24.0), (11.0, 26.0)]

# linie pomocnicze karoserii (musza zgadzac sie z profilami powyzej)
WS_A, WS_B = (27.3, HOOD_Z), (36.2, 24.8)     # szyba przednia (x, z)
RW_A, RW_B = (62.0, 16.3), (52.5, 24.8)       # szyba tylna (x, z)
GH_A, GH_B = (17.0, 14.9), (13.0, 24.0)       # bok kabiny (y, z)
ROOF_Z = 24.8

BODY_NAME = 'Karoseria'


# =============================================================================
#  POMOCNICZE
# =============================================================================
def mm(v):
    return v / 10.0


def P(x, y, z):
    return adsk.core.Point3D.create(mm(x), mm(y), mm(z))


def vi(v_mm):
    return adsk.core.ValueInput.createByReal(mm(v_mm))


def V3(x, y, z):
    return adsk.core.Vector3D.create(float(x), float(y), float(z))


def lerp(a, b, t):
    return a + (b - a) * t


def gh(z):
    """polowa szerokosci kabiny na wysokosci z (plaszczyzna boku kabiny)"""
    (y0, z0), (y1, z1) = GH_A, GH_B
    return y0 + (z - z0) * (y1 - y0) / (z1 - z0)


def ws_x(z):
    """x szyby przedniej na wysokosci z"""
    (x0, z0), (x1, z1) = WS_A, WS_B
    return x0 + (z - z0) * (x1 - x0) / (z1 - z0)


NEW = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
JOIN = adsk.fusion.FeatureOperations.JoinFeatureOperation
CUT = adsk.fusion.FeatureOperations.CutFeatureOperation
INTERSECT = adsk.fusion.FeatureOperations.IntersectFeatureOperation
POS = adsk.fusion.ExtentDirections.PositiveExtentDirection
NEG = adsk.fusion.ExtentDirections.NegativeExtentDirection


class Builder(object):
    def __init__(self, app, design):
        self.app = app
        self.design = design
        self.root = design.rootComponent
        self.ext = self.root.features.extrudeFeatures
        self.warnings = []
        self._planes = {}

    # ------------------------------------------------------------ ogolne ---
    @property
    def body(self):
        return self.root.bRepBodies.itemByName(BODY_NAME)

    def warn(self, what):
        self.warnings.append(what)

    def safe(self, label, fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Exception:
            self.warn('%s: %s' % (label, traceback.format_exc().splitlines()[-1]))
            return None

    def param(self, name, value_mm, comment):
        ups = self.design.userParameters
        p = ups.itemByName(name)
        if p is None:
            ups.add(name, adsk.core.ValueInput.createByString('%g mm' % value_mm), 'mm', comment)
        return name

    # -------------------------------------------------------- plaszczyzny ---
    def _offset_plane(self, key, base, axis, value):
        """plaszczyzna rownolegla do bazowej, przechodzaca przez axis=value (mm).
        Znak odsuniecia weryfikowany na geometrii (niezaleznie od orientacji normalnej)."""
        k = (key, round(value, 4))
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
        return self._offset_plane('x', self.root.yZConstructionPlane, 'x', x)

    def plane_y(self, y):
        return self._offset_plane('y', self.root.xZConstructionPlane, 'y', y)

    def plane_z(self, z):
        return self._offset_plane('z', self.root.xYConstructionPlane, 'z', z)

    # -------------------------------------------------------------- szkice ---
    def sketch(self, planar, name=None):
        sk = None
        if isinstance(planar, adsk.fusion.BRepFace):
            try:
                sk = self.root.sketches.addWithoutEdges(planar)
            except Exception:
                sk = None
        if sk is None:
            sk = self.root.sketches.add(planar)
        if name:
            sk.name = name
        return sk

    @staticmethod
    def to_sk(sk, p):
        return sk.modelToSketchSpace(p)

    def poly(self, sk, pts):
        """zamkniety wielokat; pts = lista (x,y,z) w mm (wsp. modelu)"""
        lines = sk.sketchCurves.sketchLines
        sp = [self.to_sk(sk, P(*p)) for p in pts]
        first = prev = None
        for i in range(len(sp)):
            if i == len(sp) - 1:
                ln = lines.addByTwoPoints(prev.endSketchPoint, first.startSketchPoint)
            elif prev is None:
                ln = lines.addByTwoPoints(sp[0], sp[1])
                first = ln
            else:
                ln = lines.addByTwoPoints(prev.endSketchPoint, sp[i + 1])
            prev = ln
        return first

    def circle(self, sk, c, r):
        return sk.sketchCurves.sketchCircles.addByCenterRadius(self.to_sk(sk, P(*c)), mm(r))

    def sector(self, sk, center_fn, r_in, r_out, a0, a1):
        """wycinek pierscienia (ramiona felgi); center_fn(r, a) -> (x,y,z) mm"""
        arcs = sk.sketchCurves.sketchArcs
        lines = sk.sketchCurves.sketchLines
        am = 0.5 * (a0 + a1)
        o = arcs.addByThreePoints(self.to_sk(sk, P(*center_fn(r_out, a0))),
                                  self.to_sk(sk, P(*center_fn(r_out, am))),
                                  self.to_sk(sk, P(*center_fn(r_out, a1))))
        i = arcs.addByThreePoints(self.to_sk(sk, P(*center_fn(r_in, a0))),
                                  self.to_sk(sk, P(*center_fn(r_in, am))),
                                  self.to_sk(sk, P(*center_fn(r_in, a1))))

        def near(arc, p):
            p = self.to_sk(sk, P(*p))
            s, e = arc.startSketchPoint, arc.endSketchPoint
            return s if s.geometry.distanceTo(p) < e.geometry.distanceTo(p) else e

        for a in (a0, a1):
            lines.addByTwoPoints(near(o, center_fn(r_out, a)), near(i, center_fn(r_in, a)))

    @staticmethod
    def normal_of(sk):
        a = sk.sketchToModelSpace(adsk.core.Point3D.create(0, 0, 0))
        b = sk.sketchToModelSpace(adsk.core.Point3D.create(0, 0, 1))
        return a.vectorTo(b)

    @staticmethod
    def profiles(sk, max_area=None):
        col = adsk.core.ObjectCollection.create()
        for pr in sk.profiles:
            if max_area is not None and pr.areaProperties().area > max_area:
                continue
            col.add(pr)
        return col

    # ------------------------------------------------------------ wyciagn. ---
    def ext_sym(self, prof, total_mm, op, bodies=None):
        inp = self.ext.createInput(prof, op)
        inp.setSymmetricExtent(vi(total_mm), True)
        if bodies:
            inp.participantBodies = bodies
        return self.ext.add(inp)

    def ext_dir(self, prof, sk, dist, want, op, bodies=None):
        """wyciagniecie o dist w kierunku wektora want (Vector3D w ukladzie modelu).
        dist: mm (float) albo wyrazenie (str) np. 'lozysko_glebokosc'"""
        n = self.normal_of(sk)
        d = POS if n.dotProduct(want) > 0 else NEG
        val = adsk.core.ValueInput.createByString(dist) if isinstance(dist, str) else vi(dist)
        inp = self.ext.createInput(prof, op)
        inp.setOneSideExtent(adsk.fusion.DistanceExtentDefinition.create(val), d)
        if bodies:
            inp.participantBodies = bodies
        return self.ext.add(inp)

    def cut_into(self, prof, sk, depth, outward, body=None):
        """wglebienie od powierzchni do srodka bryly (przeciwnie do normalnej outward).
        Jesli nic nie zostalo usuniete - probuje w druga strone."""
        body = body or self.body
        v0 = body.volume
        inward = V3(-outward.x, -outward.y, -outward.z)
        try:
            f = self.ext_dir(prof, sk, depth, inward, CUT, [body])
            if body.volume < v0 - 1e-9:
                return f
            f.deleteMe()
        except Exception:
            pass
        return self.ext_dir(prof, sk, depth, outward, CUT, [body])

    # ------------------------------------------------------------ sciany ---
    def find_face(self, body, normal, point, tol_deg=1.0):
        """plaska sciana o normalnej (na zewnatrz) ~normal, lezaca w plaszczyznie przez point"""
        n = V3(*normal)
        n.normalize()
        p = P(*point)
        best = None
        for f in body.faces:
            if f.geometry.surfaceType != adsk.core.SurfaceTypes.PlaneSurfaceType:
                continue
            ok, fn = f.evaluator.getNormalAtPoint(f.pointOnFace)
            if not ok or fn.angleTo(n) > math.radians(tol_deg):
                continue
            pl = f.geometry
            dist = abs(pl.origin.vectorTo(p).dotProduct(pl.normal))
            if dist > 1e-4:
                continue
            if best is None or f.area > best.area:
                best = f
        if best is None:
            raise RuntimeError('nie znaleziono sciany n=%s p=%s' % (normal, point))
        return best

    def face_recess(self, label, normal, on_point, polys, depth, body=None):
        """wglebienia (lista wielokatow 3D lezacych na scianie)"""
        body = body or self.body
        face = self.find_face(body, normal, on_point)
        max_a = face.area * 0.9
        sk = self.sketch(face, label)
        for pts in polys:
            self.poly(sk, pts)
        prof = self.profiles(sk, max_a)
        n = V3(*normal)
        n.normalize()
        return self.cut_into(prof, sk, depth, n, body)

    # =========================================================== MODEL ===
    def build_body(self):
        # 1) profil boczny -> wyciagniecie symetryczne na cala szerokosc
        sk = self.sketch(self.root.xZConstructionPlane, 'Profil boczny')
        self.poly(sk, [(x, 0, z) for x, z in SIDE])
        f = self.ext_sym(sk.profiles.item(0), W + 4, NEW)
        body = f.bodies.item(0)
        body.name = BODY_NAME

        # 2) obrys z gory -> czesc wspolna
        sk = self.sketch(self.root.xYConstructionPlane, 'Obrys z gory')
        pts = TOP_HALF + [(x, -y) for x, y in reversed(TOP_HALF)]
        self.poly(sk, [(x, y, 0) for x, y in pts])
        self.ext_sym(sk.profiles.item(0), 80, INTERSECT, [body])

        # 3) przekroj poprzeczny -> czesc wspolna
        sk = self.sketch(self.root.yZConstructionPlane, 'Przekroj poprzeczny')
        pts = FRONT_HALF + [(-y, z) for y, z in reversed(FRONT_HALF)]
        self.poly(sk, [(0, y, z) for y, z in pts])
        self.ext_sym(sk.profiles.item(0), 2 * (L + 10), INTERSECT, [self.body])

    def glass(self):
        # --- szyba przednia
        ax, az = WS_A
        bx, bz = WS_B
        n = (-(bz - az), 0, (bx - ax))            # na zewnatrz: do przodu i w gore
        z0, z1 = 14.2, 23.8
        h1 = gh(z1) - 1.2
        poly = [(ws_x(z0), -15.6, z0), (ws_x(z0), 15.6, z0), (ws_x(z1), h1, z1), (ws_x(z1), -h1, z1)]
        self.safe('Szyba przednia', self.face_recess, 'Szyba przednia', n,
                  (ax, 0, az), [poly], 0.5)

        # --- szyba tylna (2 tafle) + zeberka pasa
        ax, az = RW_A
        bx, bz = RW_B
        n = ((bz - az), 0, -(bx - ax))            # na zewnatrz: do tylu i w gore

        def rw_x(z):
            return ax + (z - az) * (bx - ax) / (bz - az)

        z0, z1 = 17.3, 23.9
        polys = []
        for s in (1, -1):
            polys.append([(rw_x(z0), s * 5.2, z0), (rw_x(z0), s * (gh(z0) - 1.2), z0),
                          (rw_x(z1), s * (gh(z1) - 1.2), z1), (rw_x(z1), s * 5.2, z1)])
        self.safe('Szyba tylna', self.face_recess, 'Szyba tylna', n, (ax, 0, az), polys, 0.5)

        ln = math.hypot(bx - ax, bz - az)
        ux, uz = (bx - ax) / ln, (bz - az) / ln
        ribs = []
        for i in range(5):
            t0 = 1.2 + i * 1.6
            t1 = t0 + 0.6
            p0 = (ax + ux * t0, az + uz * t0)
            p1 = (ax + ux * t1, az + uz * t1)
            ribs.append([(p0[0], -4.5, p0[1]), (p1[0], -4.5, p1[1]),
                         (p1[0], 4.5, p1[1]), (p0[0], 4.5, p0[1])])
        self.safe('Pas - tylna szyba', self.face_recess, 'Pas na tylnej szybie', n,
                  (ax, 0, az), ribs, 0.35)

        # --- szyby boczne (na pochylonym boku kabiny)
        (ya, za), (yb, zb_) = GH_A, GH_B
        zb, zt = 15.3, 19.6
        for s in (1, -1):
            nn = (0, s * (zb_ - za), -(yb - ya))  # normalna boku kabiny na zewnatrz
            poly = [(ws_x(zb) + 2.2, s * gh(zb), zb), (47.5, s * gh(zb), zb),
                    (47.5, s * gh(zt), zt), (ws_x(zt) + 2.2, s * gh(zt), zt)]
            self.safe('Szyba boczna %+d' % s, self.face_recess,
                      'Szyba boczna ' + ('P' if s > 0 else 'L'), nn,
                      (40.0, s * ya, za), [poly], 0.5)

        # --- pas dachowy z zeberkami
        ribs = []
        for i in range(10):
            x0 = 37.5 + i * 1.5
            ribs.append([(x0, -4.5, ROOF_Z), (x0 + 0.6, -4.5, ROOF_Z),
                         (x0 + 0.6, 4.5, ROOF_Z), (x0, 4.5, ROOF_Z)])
        self.safe('Pas dachowy', self.face_recess, 'Pas dachowy', (0, 0, 1),
                  (44, 0, ROOF_Z), ribs, 0.35)

    def panel_lines(self):
        for s in (1, -1):
            y = s * W / 2
            rects = []
            for x in (30.0, 48.0):
                rects.append([(x - 0.2, y, 1.0), (x + 0.2, y, 1.0), (x + 0.2, y, 12.2), (x - 0.2, y, 12.2)])
            rects.append([(4.5, y, 1.8), (69.5, y, 1.8), (69.5, y, 2.2), (4.5, y, 2.2)])
            self.safe('Linie drzwi %+d' % s, self.face_recess,
                      'Linie drzwi ' + ('P' if s > 0 else 'L'), (0, s, 0), (40, y, 6), rects, 0.3)

    def front_rear(self):
        def rect_x(x, y0, y1, z0, z1):
            return [(x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)]

        # przod
        self.safe('Wlot', self.face_recess, 'Wlot powietrza', (-1, 0, 0), (0, 0, 5),
                  [rect_x(0, -12, 12, 3.7, 6.9)], 1.5)
        self.safe('Przetloczenie przod', self.face_recess, 'Przetloczenie przod', (-1, 0, 0),
                  (0, 0, 5), [rect_x(0, -15, 15, 8.2, 8.6)], 0.3)
        # tyl
        self.safe('Panel lamp', self.face_recess, 'Panel lamp', (1, 0, 0), (L, 0, 5),
                  [rect_x(L, -15, 15, 6.1, 11.6)], 0.4)
        self.safe('Listwa swietlna', self.face_recess, 'Listwa swietlna', (1, 0, 0), (L, 0, 3),
                  [rect_x(L, -12.6, 12.6, 7.0, 9.8)], 1.5)
        self.safe('Wydechy', self.face_recess, 'Wydechy - oslona', (1, 0, 0), (L, 0, 3),
                  [rect_x(L, s * 9.8 - 2.2, s * 9.8 + 2.2, 1.7, 3.7) for s in (1, -1)], 0.5)
        self.safe('Wydechy', self.face_recess, 'Wydechy - koncowki', (1, 0, 0), (L, 0, 3),
                  [rect_x(L, s * 9.8 - 1.7, s * 9.8 + 1.7, 2.1, 3.3) for s in (1, -1)], 2.5)
        self.safe('Dyfuzor', self.face_recess, 'Dyfuzor', (1, 0, 0), (L, 0, 3),
                  [rect_x(L, -7.0, 7.0, 1.4, 3.6)], 0.6)

    def spoiler(self):
        # plyty boczne + skrzydlo: profil z boku na pelna szerokosc spoilera,
        # potem wyciecie srodka pod skrzydlem, na koniec polaczenie z nadwoziem
        sk = self.sketch(self.root.xZConstructionPlane, 'Spoiler')
        self.poly(sk, [(62.2, 0, 14.0), (69.8, 0, 14.0), (69.8, 0, 21.5), (63.2, 0, 21.5)])
        f = self.ext_sym(sk.profiles.item(0), 26.4, NEW)
        sp = f.bodies.item(0)
        sp.name = 'Spoiler'
        sk = self.sketch(self.root.xZConstructionPlane, 'Spoiler - przeswit')
        self.poly(sk, [(61.0, 0, 13.0), (71.0, 0, 13.0), (71.0, 0, 19.9), (61.0, 0, 19.9)])
        self.ext_sym(sk.profiles.item(0), 22.0, CUT, [sp])
        col = adsk.core.ObjectCollection.create()
        col.add(sp)
        ci = self.root.features.combineFeatures.createInput(self.body, col)
        ci.operation = JOIN
        ci.isKeepToolBodies = False
        self.root.features.combineFeatures.add(ci)

    def bearing_seat(self):
        pD = self.param('lozysko_gniazdo_D', BRG_FIT_D, 'Srednica gniazda lozyska 608 (22 mm + luz/wcisk)')
        pH = self.param('lozysko_glebokosc', BRG_DEPTH, 'Glebokosc gniazda od powierzchni maski')
        pR = self.param('lozysko_podciecie_D', BRG_RELIEF_D, 'Podciecie pod pierscien wewnetrzny')
        pRh = self.param('lozysko_podciecie_h', BRG_RELIEF_H, 'Glebokosc podciecia')

        face = self.find_face(self.body, (0, 0, 1), (BRG_X, 0, HOOD_Z))
        sk = self.sketch(face, 'Gniazdo 608')
        c_out = self.circle(sk, (BRG_X, 0, HOOD_Z), BRG_FIT_D / 2)
        c_in = self.circle(sk, (BRG_X, 0, HOOD_Z), BRG_RELIEF_D / 2)
        for c, pn, off in ((c_out, pD, 14.0), (c_in, pR, 10.0)):
            try:
                c.centerSketchPoint.isFixed = True
                d = sk.sketchDimensions.addDiameterDimension(
                    c, self.to_sk(sk, P(BRG_X + off, off, HOOD_Z)))
                d.parameter.expression = pn
            except Exception:
                self.warn('Wymiar %s nie zostal powiazany z parametrem' % pn)

        disk = ring = None
        for pr in sk.profiles:
            if pr.profileLoops.count == 1:
                disk = pr
            else:
                ring = pr
        both = adsk.core.ObjectCollection.create()
        both.add(disk)
        both.add(ring)
        down = V3(0, 0, -1)
        self.ext_dir(both, sk, pH, down, CUT, [self.body]).name = 'Gniazdo 608'
        self.ext_dir(disk, sk, '%s + %s' % (pH, pRh), down, CUT, [self.body]).name = 'Podciecie 608'

        # fazka wejsciowa
        def chamfer():
            edges = adsk.core.ObjectCollection.create()
            for e in self.body.edges:
                g = e.geometry
                if g.curveType == adsk.core.Curve3DTypes.Circle3DCurveType and \
                        abs(g.radius - mm(BRG_FIT_D / 2)) < 1e-4 and abs(g.center.z - mm(HOOD_Z)) < 1e-4:
                    edges.add(e)
            if edges.count == 0:
                raise RuntimeError('brak krawedzi gniazda')
            ch = self.root.features.chamferFeatures
            try:
                inp = ch.createInput2()
                inp.chamferEdgeSets.addEqualDistanceChamferEdgeSet(edges, vi(BRG_CHAMFER), False)
            except Exception:
                inp = ch.createInput(edges, False)
                inp.setToEqualDistance(vi(BRG_CHAMFER))
            ch.add(inp)
        self.safe('Fazka gniazda', chamfer)

    def arches(self):
        for s in (1, -1):
            y_in = s * (W / 2 - ARCH_DEPTH)
            sk = self.sketch(self.plane_y(y_in), 'Nadkola ' + ('P' if s > 0 else 'L'))
            for x in WHEEL_X:
                self.circle(sk, (x, y_in, WHEEL_R), ARCH_R)
            self.ext_dir(self.profiles(sk), sk, ARCH_DEPTH + 3, V3(0, s, 0), CUT, [self.body])

    def wheels(self):
        made = []
        for s in (1, -1):
            y_out = s * (W / 2 + WHEEL_PROUD)
            for x in WHEEL_X:
                name = 'Kolo %s %s' % ('P' if x < L / 2 else 'T', 'P' if s > 0 else 'L')
                sk = self.sketch(self.plane_y(y_out), name)
                self.circle(sk, (x, y_out, WHEEL_R), WHEEL_R)
                f = self.ext_dir(sk.profiles.item(0), sk, WHEEL_W, V3(0, -s, 0), NEW)
                wb = f.bodies.item(0)
                wb.name = name

                def spokes(x=x, wb=wb, y_out=y_out, s=s, name=name):
                    sk2 = self.sketch(self.plane_y(y_out), name + ' - felga')
                    n_sp, r_in, r_out = 6, 1.3, 4.9
                    ha = math.radians(8)

                    def cf(r, a):
                        return (x + r * math.cos(a), y_out, WHEEL_R + r * math.sin(a))
                    for i in range(n_sp):
                        a0 = 2 * math.pi * i / n_sp + ha
                        a1 = 2 * math.pi * (i + 1) / n_sp - ha
                        self.sector(sk2, cf, r_in, r_out, a0, a1)
                    # tylko wycinki (bez ew. profili zewnetrznych)
                    col = adsk.core.ObjectCollection.create()
                    for pr in sk2.profiles:
                        if pr.areaProperties().area < mm(1) * mm(1) * 15:
                            col.add(pr)
                    self.ext_dir(col, sk2, 0.8, V3(0, -s, 0), CUT, [wb])
                    sk3 = self.sketch(self.plane_y(y_out), name + ' - piasta')
                    self.circle(sk3, (x, y_out, WHEEL_R), 0.6)
                    self.ext_dir(sk3.profiles.item(0), sk3, 1.0, V3(0, -s, 0), CUT, [wb])
                self.safe(name + ' felga', spokes)
                made.append(wb)
        if JOIN_WHEELS:
            col = adsk.core.ObjectCollection.create()
            for b in made:
                col.add(b)
            ci = self.root.features.combineFeatures.createInput(self.body, col)
            ci.operation = JOIN
            ci.isKeepToolBodies = False
            self.root.features.combineFeatures.add(ci)

    def bearing_ref(self):
        z0 = HOOD_Z - BRG_DEPTH
        sk = self.sketch(self.plane_z(z0), 'Lozysko 608 (ref)')
        self.circle(sk, (BRG_X, 0, z0), BRG_D / 2)
        self.circle(sk, (BRG_X, 0, z0), BRG_d / 2)
        ring = [pr for pr in sk.profiles if pr.profileLoops.count == 2][0]
        f = self.ext_dir(ring, sk, BRG_W, V3(0, 0, 1), NEW)
        b = f.bodies.item(0)
        b.name = 'Lozysko 608 (ref)'
        for zz, direction in ((z0, V3(0, 0, 1)), (z0 + BRG_W, V3(0, 0, -1))):
            sk = self.sketch(self.plane_z(zz), 'Lozysko - uszczelka')
            self.circle(sk, (BRG_X, 0, zz), 9.5)
            self.circle(sk, (BRG_X, 0, zz), 6.0)
            r = [pr for pr in sk.profiles if pr.profileLoops.count == 2][0]
            self.ext_dir(r, sk, 0.3, direction, CUT, [b])
        return b

    def cap(self):
        zb = HOOD_Z - BRG_DEPTH + BRG_W       # gorna powierzchnia lozyska
        up = V3(0, 0, 1)
        sk = self.sketch(self.plane_z(zb - BRG_W + 0.5), 'Nakretka - trzpien')
        self.circle(sk, (BRG_X, 0, zb - BRG_W + 0.5), 7.95 / 2)
        f = self.ext_dir(sk.profiles.item(0), sk, BRG_W - 0.5, up, NEW)
        c = f.bodies.item(0)
        c.name = 'Nakretka spinnera'
        sk = self.sketch(self.plane_z(zb), 'Nakretka - dystans')
        self.circle(sk, (BRG_X, 0, zb), 5.5)
        self.ext_dir(sk.profiles.item(0), sk, 0.5, up, JOIN, [c])
        sk = self.sketch(self.plane_z(zb + 0.5), 'Nakretka - tarcza')
        self.circle(sk, (BRG_X, 0, zb + 0.5), 9.6)
        self.ext_dir(sk.profiles.item(0), sk, 3.5, up, JOIN, [c])

        zt = zb + 4.0

        def top():
            sk = self.sketch(self.plane_z(zt), 'Nakretka - ramiona')
            n_sp, r_in, r_out = 5, 2.5, 8.0
            ha = math.radians(9)

            def cf(r, a):
                return (BRG_X + r * math.cos(a), r * math.sin(a), zt)
            for i in range(n_sp):
                self.sector(sk, cf, r_in, r_out, 2 * math.pi * i / n_sp + ha,
                            2 * math.pi * (i + 1) / n_sp - ha)
            self.ext_dir(self.profiles(sk), sk, 1.2, V3(0, 0, -1), CUT, [c])
            sk = self.sketch(self.plane_z(zt), 'Nakretka - piasta')
            self.circle(sk, (BRG_X, 0, zt), 1.0)
            self.ext_dir(sk.profiles.item(0), sk, 1.5, V3(0, 0, -1), CUT, [c])
        self.safe('Nakretka - wzor', top)
        return c

    def colors(self, bodies_rgb):
        lib = None
        libs = self.app.materialLibraries
        for key in ('BA5EE55E-9982-449B-9D66-9F036540E140',):
            try:
                lib = libs.itemById(key)
            except Exception:
                lib = None
        if lib is None:
            for nm in ('Fusion Appearance Library', 'Fusion 360 Appearance Library'):
                lib = libs.itemByName(nm)
                if lib:
                    break
        if lib is None:
            return
        base = None
        for nm in ('Paint - Enamel Glossy (Yellow)', 'Plastic - Glossy (White)', 'Paint - Enamel Glossy (Red)'):
            base = lib.appearances.itemByName(nm)
            if base:
                break
        if base is None:
            return
        for body, name, rgb in bodies_rgb:
            if body is None:
                continue
            a = self.design.appearances.itemByName(name)
            if a is None:
                a = self.design.appearances.addByCopy(base, name)
                prop = None
                for pid in ('opaque_albedo', 'generic_diffuse'):
                    prop = a.appearanceProperties.itemById(pid)
                    if prop:
                        break
                if prop:
                    adsk.core.ColorProperty.cast(prop).value = adsk.core.Color.create(rgb[0], rgb[1], rgb[2], 255)
            body.appearance = a

    def run(self):
        self.build_body()
        self.glass()
        self.panel_lines()
        self.front_rear()
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

        msg = 'Auto608 gotowe.\n\nGniazdo 608 sterowane parametrami (Modify -> Change Parameters):\n' \
              '  lozysko_gniazdo_D, lozysko_glebokosc, lozysko_podciecie_D, lozysko_podciecie_h'
        if b.warnings:
            msg += '\n\nOstrzezenia (pominiete detale):\n- ' + '\n- '.join(b.warnings)
        ui.messageBox(msg, 'Auto608')
    except Exception:
        if ui:
            ui.messageBox('Blad:\n{}'.format(traceback.format_exc()), 'Auto608')
