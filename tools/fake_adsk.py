"""
Atrapa API Fusion 360 (adsk.core / adsk.fusion) zbudowana na CadQuery/OCC.

Pozwala wykonac skrypt fusion360/Auto608/Auto608.py poza Fusion i sprawdzic
logike budowy (kierunki wyciagniec, wybor profili, kolejnosc operacji).
Implementuje tylko to, czego uzywa skrypt. Jednostki wewnetrzne: cm (jak w Fusion).
Plaszczyzna XZ ma celowo normalna -Y, a szkice na niej odwrocona os - zeby
sprawdzic, ze skrypt nie zaklada konkretnej orientacji plaszczyzn.
"""
import math
import re
import sys
import types
from unittest import mock

import cadquery as cq
from cadquery import Vector as CV

core = types.ModuleType("adsk.core")
fusion = types.ModuleType("adsk.fusion")
adsk = types.ModuleType("adsk")
adsk.core, adsk.fusion = core, fusion


# ================================================================ core ======
class Vector3D(object):
    def __init__(self, x, y, z):
        self.x, self.y, self.z = float(x), float(y), float(z)

    @staticmethod
    def create(x=0.0, y=0.0, z=0.0):
        return Vector3D(x, y, z)

    def dotProduct(self, o):
        return self.x * o.x + self.y * o.y + self.z * o.z

    def cv(self):
        return CV(self.x, self.y, self.z)


class Point3D(Vector3D):
    @staticmethod
    def create(x=0.0, y=0.0, z=0.0):
        return Point3D(x, y, z)

    def distanceTo(self, o):
        return math.dist((self.x, self.y, self.z), (o.x, o.y, o.z))

    def vectorTo(self, o):
        return Vector3D(o.x - self.x, o.y - self.y, o.z - self.z)


class ValueInput(object):
    def __init__(self, real=None, expr=None):
        self.real, self.expr = real, expr

    @staticmethod
    def createByReal(v):
        return ValueInput(real=float(v))

    @staticmethod
    def createByString(s):
        return ValueInput(expr=s)

    def value(self, design):
        if self.expr is None:
            return self.real
        e = self.expr
        if 'deg' in e:
            return math.radians(float(e.replace('deg', '')))
        for p in design.userParameters._items.values():
            e = re.sub(r'\b%s\b' % p.name, '(%r)' % p.value, e)
        e = e.replace('mm', '*0.1')
        return float(eval(e))


class ObjectCollection(list):
    @staticmethod
    def create():
        return ObjectCollection()

    def add(self, o):
        self.append(o)

    @property
    def count(self):
        return len(self)

    def item(self, i):
        return self[i]


class _Enum(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)


core.Vector3D, core.Point3D, core.ValueInput, core.ObjectCollection = Vector3D, Point3D, ValueInput, ObjectCollection
core.Curve3DTypes = _Enum(Circle3DCurveType='circle', Line3DCurveType='line')
core.SurfaceTypes = _Enum(PlaneSurfaceType='plane')
core.DocumentTypes = _Enum(FusionDesignDocumentType=1)
core.Color = mock.MagicMock()
core.ColorProperty = mock.MagicMock()


# ============================================================== fusion =====
FeatureOperations = _Enum(NewBodyFeatureOperation='new', JoinFeatureOperation='join',
                          CutFeatureOperation='cut', IntersectFeatureOperation='intersect')
ExtentDirections = _Enum(PositiveExtentDirection=1, NegativeExtentDirection=-1)
fusion.FeatureOperations, fusion.ExtentDirections = FeatureOperations, ExtentDirections
fusion.DesignTypes = _Enum(ParametricDesignType=1)
fusion.DistanceUnits = _Enum(MillimeterDistanceUnits=1)


class Plane(object):
    def __init__(self, origin, normal):
        self.origin, self.normal = origin, normal


class ConstructionPlane(object):
    def __init__(self, origin, normal, xdir, comp):
        self.origin, self.n, self.xdir, self.comp = origin, normal, xdir, comp
        self.isLightBulbOn = True

    @property
    def geometry(self):
        return Plane(Point3D(*self.origin.toTuple()), Vector3D(*self.n.toTuple()))

    def deleteMe(self):
        self.comp.constructionPlanes._list.remove(self)


class ConstructionPlanes(object):
    def __init__(self, comp):
        self.comp, self._list = comp, []

    def createInput(self):
        return _PlaneInput()

    def add(self, inp):
        base, off = inp.base, inp.offset.value(self.comp.design)
        cp = ConstructionPlane(base.origin + base.n * off, base.n, base.xdir, self.comp)
        self._list.append(cp)
        return cp


class _PlaneInput(object):
    def setByOffset(self, base, off):
        self.base, self.offset = base, off


class SketchPoint(object):
    def __init__(self, p):
        self.geometry = p


class _Curve(object):
    isConstruction = False


class SketchLine(_Curve):
    def __init__(self, sk, a, b):
        self.sk = sk
        self.startSketchPoint = a if isinstance(a, SketchPoint) else SketchPoint(a)
        self.endSketchPoint = b if isinstance(b, SketchPoint) else SketchPoint(b)

    def edge(self):
        return cq.Edge.makeLine(self.sk.m(self.startSketchPoint.geometry), self.sk.m(self.endSketchPoint.geometry))


class SketchArc(_Curve):
    def __init__(self, sk, a, mid, b):
        self.sk, self.mid = sk, mid
        self.startSketchPoint, self.endSketchPoint = SketchPoint(a), SketchPoint(b)

    def edge(self):
        return cq.Edge.makeThreePointArc(self.sk.m(self.startSketchPoint.geometry), self.sk.m(self.mid),
                                         self.sk.m(self.endSketchPoint.geometry))


class SketchCircle(_Curve):
    def __init__(self, sk, c, r):
        self.sk, self.c, self.r = sk, c, r
        self.centerSketchPoint = SketchPoint(c)

    def edge(self):
        return cq.Edge.makeCircle(self.r, self.sk.m(self.c), self.sk.n)


class _CurveList(object):
    def __init__(self, sk, cls):
        self.sk, self.cls = sk, cls

    def addByTwoPoints(self, a, b):
        return self.sk._add(SketchLine(self.sk, a, b))

    def addByThreePoints(self, a, m, b):
        return self.sk._add(SketchArc(self.sk, a, m, b))

    def addByCenterRadius(self, c, r):
        return self.sk._add(SketchCircle(self.sk, c, r))


class Profile(object):
    def __init__(self, face, loops):
        self.face, self._loops = face, loops

    @property
    def profileLoops(self):
        return _Enum(count=self._loops)

    def areaProperties(self):
        return _Enum(area=self.face.Area())


class Sketch(object):
    def __init__(self, comp, plane):
        self.comp, self.plane = comp, plane
        self.o, self.n = plane.origin, plane.n.normalized()
        self.xd = plane.xdir.normalized()
        self.yd = self.n.cross(self.xd)
        self.curves = []
        self.name = ''
        lines = _CurveList(self, SketchLine)
        self.sketchCurves = _Enum(sketchLines=lines, sketchArcs=lines, sketchCircles=lines)
        self.sketchDimensions = _Dims(comp.design)

    def _add(self, c):
        self.curves.append(c)
        return c

    def m(self, p):
        return self.o + self.xd * p.x + self.yd * p.y + self.n * p.z

    def modelToSketchSpace(self, p):
        d = p.cv() - self.o
        return Point3D(d.dot(self.xd), d.dot(self.yd), d.dot(self.n))

    def sketchToModelSpace(self, p):
        return Point3D(*self.m(p).toTuple())

    @property
    def profiles(self):
        edges = [c.edge() for c in self.curves if not c.isConstruction]
        wires = cq.Wire.combine(edges, tol=1e-6)
        faces = [cq.Face.makeFromWires(w) for w in wires if w.IsClosed()]
        faces.sort(key=lambda f: -f.Area())
        profs = []
        for i, f in enumerate(faces):
            inner = [g for g in faces[i + 1:] if abs(f.intersect(g).Area() - g.Area()) < 1e-9]
            if inner:
                ff = f
                for g in inner:
                    ff = ff.cut(g)
                profs.append(Profile(ff.Faces()[0], 1 + len(inner)))
            else:
                profs.append(Profile(f, 1))
        return ObjectCollection(profs)


class _Dims(object):
    def __init__(self, design):
        self.design = design

    def addDiameterDimension(self, c, p):
        design = self.design

        class Par(object):
            @property
            def expression(self):
                return ''

            @expression.setter
            def expression(self, e):
                v = ValueInput.createByString(e).value(design)
                assert abs(v - 2 * c.r) < 1e-9, 'wymiar != parametr'
        return _Enum(parameter=Par())


class Sketches(object):
    def __init__(self, comp):
        self.comp = comp

    def add(self, plane):
        return Sketch(self.comp, plane)


class BRepEdge(object):
    def __init__(self, e):
        self.e = e

    @property
    def geometry(self):
        if self.e.geomType() == 'CIRCLE':
            return _Enum(curveType='circle', radius=self.e.radius(),
                         center=Point3D(*self.e.arcCenter().toTuple()))
        return _Enum(curveType='other')


class BRepBody(object):
    def __init__(self, comp, solid, name='Body'):
        self.comp, self.solid, self.name = comp, solid, name
        self.isLightBulbOn, self.appearance = True, None

    @property
    def volume(self):
        return self.solid.Volume()

    @property
    def edges(self):
        return [BRepEdge(e) for e in self.solid.Edges()]


class BRepBodies(object):
    def __init__(self, comp):
        self.comp, self._list = comp, []

    def itemByName(self, n):
        for b in self._list:
            if b.name == n:
                return b
        return None

    def new(self, solid):
        b = BRepBody(self.comp, solid, 'Body%d' % (len(self._list) + 1))
        self._list.append(b)
        return b


def _apply(comp, tool, op, bodies):
    """wynik operacji; zwraca liste cial wynikowych"""
    if op == 'new':
        return [comp.bRepBodies.new(tool)]
    targets = bodies or list(comp.bRepBodies._list)
    hit = False
    for b in targets:
        common = b.solid.intersect(tool)
        touches = common.Volume() > 1e-12
        if op == 'join':
            if touches or b.solid.distance(tool) < 1e-9:
                b.solid = b.solid.fuse(tool).clean()
                hit = True
        elif op == 'cut':
            if touches:
                b.solid = b.solid.cut(tool).clean()
                hit = True
        elif op == 'intersect':
            b.solid = common
            hit = True
    if not hit:
        raise RuntimeError('operacja %s nie trafila w zadne cialo' % op)
    return targets


class _ExtInput(object):
    def __init__(self, prof, op):
        self.prof, self.op, self.participantBodies = prof, op, None
        self.mode = None

    def setSymmetricExtent(self, d, full):
        self.mode, self.d, self.full = 'sym', d, full

    def setOneSideExtent(self, ext, direction):
        self.mode, self.d, self.dir = 'one', ext.d, direction


class DistanceExtentDefinition(object):
    @staticmethod
    def create(d):
        return _Enum(d=d)


fusion.DistanceExtentDefinition = DistanceExtentDefinition


class _Feature(object):
    def __init__(self, comp, bodies):
        self.comp, self._bodies, self.name = comp, bodies, ''

    @property
    def bodies(self):
        return ObjectCollection(self._bodies)

    def deleteMe(self):
        raise NotImplementedError


def _profiles_of(p):
    return list(p) if isinstance(p, list) else [p]


class ExtrudeFeatures(object):
    def __init__(self, comp):
        self.comp = comp

    def createInput(self, prof, op):
        return _ExtInput(prof, op)

    def add(self, inp):
        tools = []
        for pr in _profiles_of(inp.prof):
            sk = pr.sketch
            d = inp.d.value(self.comp.design)
            if inp.mode == 'sym':
                h = d / 2 if inp.full else d
                f = pr.face.translate(sk.n * -h)
                tools.append(cq.Solid.extrudeLinear(f, sk.n * (2 * h)))
            else:
                tools.append(cq.Solid.extrudeLinear(pr.face, sk.n * (d * inp.dir)))
        tool = tools[0]
        for t in tools[1:]:
            tool = tool.fuse(t)
        return _Feature(self.comp, _apply(self.comp, tool, inp.op, inp.participantBodies))


class LoftFeatures(object):
    def __init__(self, comp):
        self.comp = comp

    def createInput(self, op):
        return _Enum(op=op, loftSections=_Enum(add=None), isSolid=True, _p=[])

    def add(self, li):
        wires = [p.face.outerWire() for p in li._p]
        solid = cq.Solid.makeLoft(wires, ruled=False)
        return _Feature(self.comp, _apply(self.comp, solid, li.op, None))


class CombineFeatures(object):
    def __init__(self, comp):
        self.comp = comp

    def createInput(self, target, tools):
        return _Enum(target=target, tools=list(tools), operation=None, isKeepToolBodies=False)

    def add(self, ci):
        t = ci.target
        for b in ci.tools:
            if ci.operation == 'join':
                t.solid = t.solid.fuse(b.solid)
            elif ci.operation == 'cut':
                t.solid = t.solid.cut(b.solid)
            else:
                t.solid = t.solid.intersect(b.solid)
            if not ci.isKeepToolBodies:
                self.comp.bRepBodies._list.remove(b)
        t.solid = t.solid.clean()
        return _Feature(self.comp, [t])


class RevolveFeatures(object):
    def __init__(self, comp):
        self.comp = comp

    def createInput(self, prof, axis, op):
        return _Enum(prof=prof, axis=axis, op=op, participantBodies=None,
                     setAngleExtent=lambda sym, a: None)

    def add(self, inp):
        sk = inp.prof.sketch
        a0 = sk.m(inp.axis.startSketchPoint.geometry)
        a1 = sk.m(inp.axis.endSketchPoint.geometry)
        solid = cq.Solid.revolve(inp.prof.face, 360, a0, a1)
        return _Feature(self.comp, _apply(self.comp, solid, inp.op, inp.participantBodies))


class ChamferFeatures(object):
    def __init__(self, comp):
        self.comp = comp

    def createInput2(self):
        ci = _Enum(sets=[])
        ci.chamferEdgeSets = _Enum(addEqualDistanceChamferEdgeSet=lambda e, d, t: ci.sets.append((e, d)))
        return ci

    def add(self, ci):
        for edges, d in ci.sets:
            body = None
            for b in self.comp.bRepBodies._list:
                if any(e.e.isSame(x) for x in b.solid.Edges() for e in edges[:1]):
                    body = b
            dist = d.value(self.comp.design)
            body.solid = body.solid.chamfer(dist, None, [e.e for e in edges]).clean()
        return _Feature(self.comp, [])


class RemoveFeatures(object):
    def __init__(self, comp):
        self.comp = comp

    def add(self, body):
        self.comp.bRepBodies._list.remove(body)


class Component(object):
    def __init__(self, design):
        self.design = design
        X, Y, Z = CV(1, 0, 0), CV(0, 1, 0), CV(0, 0, 1)
        O = CV(0, 0, 0)
        self.xYConstructionPlane = ConstructionPlane(O, Z, X, self)
        self.xZConstructionPlane = ConstructionPlane(O, -Y, -X, self)   # celowo "odwrocona"
        self.yZConstructionPlane = ConstructionPlane(O, X, Y, self)
        self.constructionPlanes = ConstructionPlanes(self)
        self.bRepBodies = BRepBodies(self)
        self._sketches_all = []
        comp = self

        class _Sk(Sketches):
            def add(self, plane):
                sk = Sketch(comp, plane)
                comp._sketches_all.append(sk)
                orig = Sketch.profiles.fget

                def profs(s=sk):
                    ps = orig(s)
                    for p in ps:
                        p.sketch = s
                    s._last_profiles = ps
                    return ps
                sk.__class__ = type('SketchX', (Sketch,), {'profiles': property(lambda s: profs(s))})
                return sk
        self.sketches = _Sk(self)
        self.features = _Enum(extrudeFeatures=ExtrudeFeatures(self), loftFeatures=LoftFeatures(self),
                              combineFeatures=CombineFeatures(self), revolveFeatures=RevolveFeatures(self),
                              chamferFeatures=ChamferFeatures(self), removeFeatures=RemoveFeatures(self))


# loftSections.add musi dopisywac do listy wejscia
def _loft_create(self, op):
    li = _Enum(op=op, isSolid=True, _p=[])
    li.loftSections = _Enum(add=li._p.append)
    return li


LoftFeatures.createInput = _loft_create


class _UserParams(object):
    def __init__(self, design):
        self.design, self._items = design, {}

    def itemByName(self, n):
        return self._items.get(n)

    def add(self, name, vi, units, comment):
        p = _Enum(name=name, value=vi.value(self.design))
        self._items[name] = p
        return p


class Design(object):
    def __init__(self):
        self.userParameters = _UserParams(self)
        self.rootComponent = Component(self)
        self.appearances = mock.MagicMock()
        self.fusionUnitsManager = _Enum()
        self.designType = None


fusion.Design = _Enum(cast=lambda x: x)
fusion.BRepFace = type('BRepFace', (), {})


def install():
    sys.modules['adsk'] = adsk
    sys.modules['adsk.core'] = core
    sys.modules['adsk.fusion'] = fusion
