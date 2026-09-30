"""Panda wanka-wstanka (roly-poly) na Bambu Lab P1S.

Konstrukcja jak w Mikolaju (Santa_RolyPoly_P1S.3mf):
  * ciezki dol drukowany ze 100% wypelnienia (kopula toczna),
  * lacznik szesciokatny 25 x 12 mm (100%) miedzy dolem a korpusem,
  * korpus i glowa z lekkim wypelnieniem, glowa na szesciokatnym czopie,
  * kolorowe detale jako osobne jednokolorowe czesci wklejane w gniazda.

Uklad: X w prawo, Y do tylu (przod pandy patrzy w -Y), Z w gore, podloze Z = 0.
Wymiary z przodu wziete ze zdjecia (ref/panda_zdjecie.webp, skala 0.0978 mm/px).

Uruchom:  python3 panda_rolypoly.py      -> export/*.stl + export/Panda_RolyPoly_P1S.3mf
"""
import json, os, sys, time
import numpy as np
from matplotlib.path import Path as MPath
from scipy import ndimage as ndi
from skimage.measure import marching_cubes
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
EXPORT = os.path.join(HERE, 'export')

# --------------------------------------------------------------------------- wymiary
# Kula / korpus: bryla obrotowa, dwie polowki elipsoidy.
BODY_A = 31.6        # promien w pasie (szerokosc 63,2 mm jak dol Mikolaja)
BODY_ZEQ = 28.5      # wysokosc pasa
BODY_CLO = 28.5      # polos pionowa dolnej polowki -> promien krzywizny toczenia 35,0 mm
BODY_CUP = 44.0      # polos pionowa gornej polowki (schowana pod glowa)

Z_JOINT = 41.8       # plaszczyzna dol / korpus (= granica bialy / czarny na bokach i z tylu)
HEX_R, HEX_H = 12.5, 12.0          # lacznik jak u Mikolaja (25 mm po wierzcholkach, 12 mm)
HEX_CLR = 0.25                     # luz promieniowy gniazda
HEX_DEPTH_BOTTOM, HEX_DEPTH_CHEST = 6.0, 6.5

# Brzuch: luk z przodu (widok z przodu) z = g(x), wewnatrz dach 50 st. -> druk bez podpor.
BELLY_TOP, BELLY_HALF_W, BELLY_EXP = 54.1, 30.6, 0.7
BELLY_ROOF = 1.2     # nachylenie dachu klina (dz/dy)

# Glowa: superelipsoida (przekroje poziome to elipsy), dol splaszczony do druku.
HEAD_A, HEAD_B = 27.1, 22.8        # pol szerokosci, pol glebokosci
HEAD_ZC = 74.8                     # wysokosc najszerszego miejsca
HEAD_CU, HEAD_PU = 27.7, 1.9       # gorna polowka: polos, wykladnik
HEAD_CL, HEAD_PL = 18.4, 2.5       # dolna polowka
HEAD_Y = 0.0
Z_HEAD = 57.2                      # plaski spod glowy = dno misy w korpusie
HEAD_CLR = 0.2
NECK_HEX_R, NECK_HEX_H, NECK_HEX_DEPTH = 7.0, 4.0, 4.6   # czop w misie korpusu / gniazdo w glowie
MUZZLE_C, MUZZLE_R = (0.0, -21.7, 72.0), (8.0, 4.0, 6.0)

# Uszy (elipsoidy, splaszczony tyl pod druk).
EAR_C, EAR_R, EAR_BACK = (20.5, 2.0, 97.5), (8.6, 4.6, 8.6), 2.6
EAR_EMBED = 1.5

# Rece: lancuch stozkow zaokraglonych (koniuszek -> lokiec -> bark), wtopione w korpus.
ARM = [((37.0, -2.0, 67.4), 7.0), ((31.0, -1.0, 57.0), 7.2), ((21.0, 0.0, 48.0), 6.8)]
ARM_BLEND = 2.0

# Stopy: walce eliptyczne z zaokragleniem, podeszwa patrzy do przodu i na zewnatrz.
FOOT_SOLE = (26.6, -25.0, 25.8)    # srodek podeszwy (lewa stopa ma X ujemne)
FOOT_YAW, FOOT_PITCH = 18.0, 6.0   # obrot na zewnatrz / w gore [st.]
FOOT_RU, FOOT_RV, FOOT_L, FOOT_ROUND = 11.4, 12.9, 11.0, 3.0
FOOT_EMBED = 1.5
# Poduszki (widok z przodu, lewa stopa lustrzanie): (x, z, r)
PADS = [(27.16, 22.84, 5.65), (34.05, 28.62, 1.95), (30.54, 31.53, 2.1), (25.57, 31.54, 2.1)]
PAD_DEPTH, PAD_RAISE, PAD_ROUND = 1.2, 1.2, 0.8

# Oczy (lewe oko, prawe lustrzanie): elipsy ze zdjecia
EYE_C, EYE_R = (10.92, 80.33), (4.02, 4.78)
PUPIL_C, PUPIL_R = (9.88, 79.95), (2.89, 3.67)
GLINT_C, GLINT_R = (9.18, 81.60), 0.86

# Komora na obciaznik w dolnej kopule (pod lacznikiem): lejek 45 st. + walec + kanal.
# Dol drukowany do gory nogami, wiec lejek (w druku zwezajacy sie ku gorze) nie potrzebuje podpor.
BALLAST_Z0, BALLAST_R0 = 2.2, 5.0          # dno lejka
BALLAST_R, BALLAST_Z1 = 22.0, 26.5          # promien i gora komory
BALLAST_SHAFT_R = 9.5                       # kanal do wsypywania (mniejszy niz lacznik)
BALLAST_Y = 2.2                             # komora przesunieta do tylu: rownowazy twarz i stopy

CLR = 0.15           # luz wkladek w gniazdach (na strone)
DEC_MIN = 1.5        # minimalna glebokosc gniazda wkladki

# --------------------------------------------------------------------------- SDF
def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def sd_ellipsoid(x, y, z, c, r):
    px, py, pz = (x - c[0]) / r[0], (y - c[1]) / r[1], (z - c[2]) / r[2]
    k0 = np.sqrt(px * px + py * py + pz * pz)
    k1 = np.sqrt((px / r[0]) ** 2 + (py / r[1]) ** 2 + (pz / r[2]) ** 2)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def sd_body(x, y, z):
    c = np.where(z > BODY_ZEQ, BODY_CUP, BODY_CLO)
    px, py, pz = x / BODY_A, y / BODY_A, (z - BODY_ZEQ) / c
    k0 = np.sqrt(px * px + py * py + pz * pz)
    k1 = np.sqrt((px / BODY_A) ** 2 + (py / BODY_A) ** 2 + (pz / c) ** 2)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def body_radius(z):
    c = np.where(z > BODY_ZEQ, BODY_CUP, BODY_CLO)
    return BODY_A * np.sqrt(np.clip(1 - ((z - BODY_ZEQ) / c) ** 2, 0, 1))


def sd_head_raw(x, y, z):
    dz = z - HEAD_ZC
    up = dz > 0
    p = np.where(up, HEAD_PU, HEAD_PL)
    C = np.where(up, HEAD_CU, HEAD_CL)
    rho = np.sqrt((x / HEAD_A) ** 2 + ((y - HEAD_Y) / HEAD_B) ** 2) + 1e-9
    t = np.abs(dz) / C + 1e-12
    F = rho ** p + t ** p - 1.0
    gr = p * rho ** (p - 2)
    gx = gr * x / HEAD_A ** 2
    gy = gr * (y - HEAD_Y) / HEAD_B ** 2
    gz = p * t ** (p - 1) / C
    return F / np.sqrt(gx * gx + gy * gy + gz * gz + 1e-12)


def sd_head_base(x, y, z):
    """Glowa z pyszczkiem (bez gniazd), nieobcieta."""
    return smin(sd_head_raw(x, y, z), sd_ellipsoid(x, y, z, MUZZLE_C, MUZZLE_R), 2.0)


def sd_round_cone(x, y, z, a, b, ra, rb):
    """Stozek o zaokraglonych koncach (Inigo Quilez)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ba = b - a
    l2 = ba @ ba
    rr = ra - rb
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pax, pay, paz = x - a[0], y - a[1], z - a[2]
    yv = pax * ba[0] + pay * ba[1] + paz * ba[2]
    zv = yv - l2
    qx = pax * l2 - ba[0] * yv
    qy = pay * l2 - ba[1] * yv
    qz = paz * l2 - ba[2] * yv
    x2 = qx * qx + qy * qy + qz * qz
    y2 = yv * yv * l2
    z2 = zv * zv * l2
    k = np.sign(rr) * rr * rr * x2
    d1 = np.sqrt(x2 + z2) * il2 - rb
    d2 = np.sqrt(x2 + y2) * il2 - ra
    d3 = (np.sqrt(x2 * a2 * il2) + yv * rr) * il2 - ra
    return np.where(np.sign(zv) * a2 * z2 > k, d1, np.where(np.sign(yv) * a2 * y2 < k, d2, d3))


def sd_arm(x, y, z, side):
    d = None
    for (p0, r0), (p1, r1) in zip(ARM[:-1], ARM[1:]):
        a = (side * p0[0], p0[1], p0[2])
        b = (side * p1[0], p1[1], p1[2])
        s = sd_round_cone(x, y, z, a, b, r0, r1)
        d = s if d is None else smin(d, s, 1.0)
    return d


def sd_hex(x, y, z, r, z0, z1, cx=0.0, cy=0.0):
    """Graniastoslup szesciokatny (wierzcholki na osi X), promien opisany r."""
    h = r * np.sqrt(3) / 2
    kx, ky, kz = -0.8660254, 0.5, 0.57735027
    px, py = np.abs(x - cx), np.abs(y - cy)
    dt = np.minimum(kx * px + ky * py, 0.0)
    px, py = px - 2 * dt * kx, py - 2 * dt * ky
    # obrot o 90 st.: IQ ma boki plaskie na +-y dla osi zamienionych
    qx = px - np.clip(px, -kz * h, kz * h)
    qy = py - h
    d2 = np.sqrt(qx * qx + qy * qy) * np.sign(qy)
    dz = np.maximum(z0 - z, z - z1)
    return np.maximum(d2, dz)


def ear_sdf(x, y, z, side):
    c = (side * EAR_C[0], EAR_C[1], EAR_C[2])
    return np.maximum(sd_ellipsoid(x, y, z, c, EAR_R), y - (EAR_C[1] + EAR_BACK))


# ---- stopy (lokalny uklad: u w bok, v w gore, w wzdluz normalnej podeszwy)
def foot_frame(side):
    yaw, pitch = np.radians(FOOT_YAW), np.radians(FOOT_PITCH)
    n = np.array([side * np.sin(yaw) * np.cos(pitch), -np.cos(yaw) * np.cos(pitch), np.sin(pitch)])
    u = np.array([np.cos(yaw), side * np.sin(yaw), 0.0]) * side
    u = u - n * (u @ n)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    if v[2] < 0:
        v = -v
    c = np.array([side * FOOT_SOLE[0], FOOT_SOLE[1], FOOT_SOLE[2]])
    return c, u, v, n


def to_local(x, y, z, frame):
    c, u, v, n = frame
    px, py, pz = x - c[0], y - c[1], z - c[2]
    return (px * u[0] + py * u[1] + pz * u[2], px * v[0] + py * v[1] + pz * v[2],
            px * n[0] + py * n[1] + pz * n[2])


def sd_ellipse2(u, v, ru, rv):
    k0 = np.sqrt((u / ru) ** 2 + (v / rv) ** 2)
    k1 = np.sqrt((u / ru ** 2) ** 2 + (v / rv ** 2) ** 2)
    return k0 * (k0 - 1) / np.maximum(k1, 1e-9)


def foot_sdf(x, y, z, side):
    u, v, w = to_local(x, y, z, foot_frame(side))
    dr = sd_ellipse2(u, v, FOOT_RU, FOOT_RV) + FOOT_ROUND
    da = np.abs(w + FOOT_L / 2) - FOOT_L / 2 + FOOT_ROUND
    return np.sqrt(np.maximum(dr, 0) ** 2 + np.maximum(da, 0) ** 2) + np.minimum(np.maximum(dr, da), 0) - FOOT_ROUND


def pad_uv(side):
    """Srodki poduszek w ukladzie podeszwy: rzut ze zdjecia wzdluz Y na plaszczyzne podeszwy."""
    c, u, v, n = foot_frame(side)
    res = []
    for (px, pz, r) in PADS:
        X, Z = side * px, pz
        # punkt na plaszczyznie podeszwy o tym samym (X, Z)
        t = ((c - np.array([X, 0, Z])) @ n) / n[1]
        p = np.array([X, t, Z]) - c
        res.append((p @ u, p @ v, r))
    return res


def pads_sdf(x, y, z, side, grow=0.0, depth_extra=0.0, raised=True):
    u, v, w = to_local(x, y, z, foot_frame(side))
    d = None
    for (pu, pv, r) in pad_uv(side):
        dc = np.sqrt((u - pu) ** 2 + (v - pv) ** 2) - r - grow
        d = dc if d is None else np.minimum(d, dc)
    back = -(w + PAD_DEPTH + depth_extra)
    if raised:
        top = smax(d, w - PAD_RAISE, PAD_ROUND)
        return np.maximum(top, back)
    return np.maximum(d, back)


# ---- brzuch
def belly_g(x):
    u = np.clip(np.abs(x) / BELLY_HALF_W, 0, 1)
    g = Z_JOINT + (BELLY_TOP - Z_JOINT) * (1 - u * u) ** BELLY_EXP
    return np.where(np.abs(x) < BELLY_HALF_W, g, Z_JOINT - 1.0)


def belly_zint(x, y):
    g = belly_g(x)
    ysb = -np.sqrt(np.maximum(body_radius(g) ** 2 - x * x, 0))
    return np.where(y <= ysb, g, g - BELLY_ROOF * (y - ysb))


# ---- wkladki na twarzy: kontury 2D (x, z) -> SDF z rastra
class Poly2D:
    def __init__(self, pts, res=0.02, margin=4.0, smooth=0.0):
        pts = np.asarray(pts, float)
        self.pts = pts
        lo, hi = pts.min(0) - margin, pts.max(0) + margin
        nx, nz = int(np.ceil((hi[0] - lo[0]) / res)) + 1, int(np.ceil((hi[1] - lo[1]) / res)) + 1
        gx, gz = np.meshgrid(lo[0] + res * np.arange(nx), lo[1] + res * np.arange(nz), indexing='ij')
        inside = MPath(pts).contains_points(np.c_[gx.ravel(), gz.ravel()]).reshape(nx, nz)
        d = (ndi.distance_transform_edt(~inside) - ndi.distance_transform_edt(inside)) * res
        if smooth > 0:
            # rozmycie usuwa grzbiety pola odleglosci (os szkieletowa) -> gladka kopulka
            # (przy samym konturze zostaje dokladna odleglosc, zeby wkladka pasowala do gniazda)
            w = np.clip((-d - 0.3) / 1.0, 0, 1)
            d = (1 - w) * d + w * ndi.gaussian_filter(d, smooth / res)
        self.lo, self.res, self.d, self.margin = lo, res, d.astype(np.float32), margin

    def __call__(self, x, z):
        i = (x - self.lo[0]) / self.res
        k = (z - self.lo[1]) / self.res
        out = ndi.map_coordinates(self.d, [i.ravel(), k.ravel()], order=1, mode='nearest').reshape(np.shape(x))
        # poza rastrem: odleglosc do ramki + margines (wystarczy, bo daleko od konturu)
        ex = np.maximum(np.maximum(self.lo[0] - x, x - (self.lo[0] + self.res * (self.d.shape[0] - 1))), 0)
        ez = np.maximum(np.maximum(self.lo[1] - z, z - (self.lo[1] + self.res * (self.d.shape[1] - 1))), 0)
        return out + np.hypot(ex, ez)


def ellipse_pts(c, r, n=360):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[c[0] + r[0] * np.cos(t), c[1] + r[1] * np.sin(t)]


def head_surface_y(x, z):
    """Y przedniej powierzchni glowy (z pyszczkiem) dla punktow (x, z)."""
    lo = np.full(np.shape(x), -40.0)
    hi = np.full(np.shape(x), HEAD_Y)
    for _ in range(40):
        m = (lo + hi) / 2
        inside = sd_head_base(x, m, z) < 0
        hi = np.where(inside, m, hi)
        lo = np.where(inside, lo, m)
    return (lo + hi) / 2


def head_normal(x, y, z, e=0.02):
    g = np.stack([sd_head_base(x + e, y, z) - sd_head_base(x - e, y, z),
                  sd_head_base(x, y + e, z) - sd_head_base(x, y - e, z),
                  sd_head_base(x, y, z + e) - sd_head_base(x, y, z - e)], -1)
    return g / np.linalg.norm(g, axis=-1, keepdims=True)


class DecalGroup:
    """Wkladki z jednym wspolnym plaskim dnem (plaszczyzna pochylona wg sredniej normalnej)."""

    def __init__(self, outer_poly):
        self.outer = outer_poly
        pts = outer_poly.pts
        lo, hi = pts.min(0), pts.max(0)
        gx, gz = np.meshgrid(np.linspace(lo[0], hi[0], 60), np.linspace(lo[1], hi[1], 60))
        m = MPath(pts).contains_points(np.c_[gx.ravel(), gz.ravel()])
        sx, sz = gx.ravel()[m], gz.ravel()[m]
        sy = head_surface_y(sx, sz)
        n = head_normal(sx, sy, sz).mean(0)
        self.n = n / np.linalg.norm(n)
        self.lev_s = np.c_[sx, sy, sz] @ self.n          # poziom powierzchni nad kazdym punktem
        self.samples = (sx, sz)
        self.L0 = self.lev_s.min() - DEC_MIN

    def level(self, x, y, z):
        return x * self.n[0] + y * self.n[1] + z * self.n[2]

    def surf_level_max(self, poly):
        sx, sz = self.samples
        m = MPath(poly.pts).contains_points(np.c_[sx, sz])
        return self.lev_s[m].max()


def decal_solid(x, y, z, grp, poly, back, raise_, rnd):
    """Wkladka: kontur wyciagniety wzdluz Y, dno = plaszczyzna, wierzch = powierzchnia glowy + raise."""
    d2 = poly(x, z)
    top = sd_head_base(x, y, z) - raise_
    s = smax(d2, top, rnd) if rnd > 0 else np.maximum(d2, top)
    return np.maximum(s, back - grp.level(x, y, z))


def decal_cut(x, y, z, grp, poly, back, c=CLR):
    return np.maximum(poly(x, z) - c, (back - c) - grp.level(x, y, z))


# --------------------------------------------------------------------------- wkladki twarzy
KONT = json.load(open(os.path.join(HERE, 'ref', 'kontury_mm.json')))


class Face:
    def __init__(self):
        mir = lambda p: np.asarray(p) * [-1, 1]
        self.eyes = {}
        for side in (-1, 1):
            patch = np.asarray(KONT['lata']) if side < 0 else mir(KONT['lata'])[::-1]
            e = {}
            e['patch'] = Poly2D(patch)
            e['eye'] = Poly2D(ellipse_pts((side * EYE_C[0], EYE_C[1]), EYE_R))
            pup = Poly2D(ellipse_pts((side * PUPIL_C[0], PUPIL_C[1]), PUPIL_R))
            eye_in = Poly2D(ellipse_pts((side * EYE_C[0], EYE_C[1]), (EYE_R[0] - 0.55, EYE_R[1] - 0.55)))
            # zrenica przycieta do wnetrza bialka (min. 0,55 mm bialego pierscienia)
            e['pupil_raw'], e['eye_in'] = pup, eye_in
            e['glint'] = Poly2D(ellipse_pts((side * GLINT_C[0], GLINT_C[1]), (GLINT_R, GLINT_R)))
            g = DecalGroup(e['patch'])
            e['grp'] = g
            e['L_patch'] = g.L0
            e['L_pupil'] = g.surf_level_max(e['eye']) + 1.0 - 0.8
            self.eyes[side] = e
        self.nose = Poly2D(KONT['nos'], smooth=0.8)
        self.gn = DecalGroup(self.nose)
        self.mouth = Poly2D(KONT['buzia'])
        self.tongue = Poly2D(KONT['jezyk'])
        self.gm = DecalGroup(self.mouth)
        self.gm.L0 = self.gm.lev_s.min() - 3.0          # 1,2 wglebienia + 1,8 wkladki

    def pupil_d2(self, e, x, z):
        return np.maximum(e['pupil_raw'](x, z), e['eye_in'](x, z))

    # -- czesci
    def patch(self, x, y, z, side):
        e = self.eyes[side]
        s = decal_solid(x, y, z, e['grp'], e['patch'], e['L_patch'], 0.6, 0.5)
        return np.maximum(s, -decal_cut(x, y, z, e['grp'], e['eye'], e['L_patch']))

    def eye(self, x, y, z, side):
        e = self.eyes[side]
        g = e['grp']
        s = decal_solid(x, y, z, g, e['eye'], e['L_patch'], 1.0, 0.5)
        pup_cut = np.maximum(self.pupil_d2(e, x, z) - CLR, (e['L_pupil'] - CLR) - g.level(x, y, z))
        s = np.maximum(s, -pup_cut)
        post = decal_solid(x, y, z, g, e['glint'], e['L_patch'], 1.8, 0.3)
        return np.minimum(s, post)

    def pupil(self, x, y, z, side):
        e = self.eyes[side]
        g = e['grp']
        d2 = self.pupil_d2(e, x, z)
        top = sd_head_base(x, y, z) - 1.5
        s = np.maximum(smax(d2, top, 0.4), e['L_pupil'] - g.level(x, y, z))
        return np.maximum(s, -(e['glint'](x, z) - CLR))

    def nose_part(self, x, y, z):
        return decal_solid(x, y, z, self.gn, self.nose, self.gn.L0, 3.2, 2.6)

    def mouth_part(self, x, y, z):
        s = decal_solid(x, y, z, self.gm, self.mouth, self.gm.L0, -1.2, 0.0)
        return np.maximum(s, -(self.tongue(x, z) - CLR))

    def tongue_part(self, x, y, z):
        return decal_solid(x, y, z, self.gm, self.tongue, self.gm.L0, -0.4, 0.5)

    def pockets(self, x, y, z):
        d = None
        for side, e in self.eyes.items():
            c = decal_cut(x, y, z, e['grp'], e['patch'], e['L_patch'])
            d = c if d is None else np.minimum(d, c)
        d = np.minimum(d, decal_cut(x, y, z, self.gn, self.nose, self.gn.L0))
        d = np.minimum(d, decal_cut(x, y, z, self.gm, self.mouth, self.gm.L0))
        return d


def to_manifold(m):
    import manifold3d as mf
    return mf.Manifold(mf.Mesh(np.asarray(m.vertices, np.float32), np.asarray(m.faces, np.uint32)))


def from_manifold(M):
    mm = M.to_mesh()
    return trimesh.Trimesh(np.asarray(mm.vert_properties)[:, :3], np.asarray(mm.tri_verts), process=True)


def pocket_prism(poly, grp, back, c=CLR, y0=-45.0, y1=10.0):
    """Dokladne gniazdo: kontur (+luz) wyciagniety wzdluz Y, obciety plaszczyzna dna."""
    from shapely.geometry import Polygon
    pg = Polygon(poly.pts).buffer(c, join_style=1, quad_segs=16)
    m = trimesh.creation.extrude_polygon(pg, y1 - y0)
    M = np.array([[1, 0, 0, 0], [0, 0, 1, y0], [0, 1, 0, 0], [0, 0, 0, 1.0]])
    m.apply_transform(M)
    # trimesh sam odwraca scianki przy odbiciu osi, wiec objetosc zostaje dodatnia
    return to_manifold(m).trim_by_plane(list(grp.n), float(back - c))


def head_pockets(m, face):
    H = to_manifold(m)
    cuts = [pocket_prism(e['patch'], e['grp'], e['L_patch']) for e in face.eyes.values()]
    cuts += [pocket_prism(face.nose, face.gn, face.gn.L0), pocket_prism(face.mouth, face.gm, face.gm.L0)]
    for c in cuts:
        H = H - c
    return from_manifold(H)


# --------------------------------------------------------------------------- czesci
def sd_ballast(x, y, z):
    r = np.sqrt(x * x + (y - BALLAST_Y) * (y - BALLAST_Y))
    s2 = np.sqrt(0.5)
    funnel = (r - (BALLAST_R0 + (z - BALLAST_Z0))) * s2           # stozek 45 st.
    chamber = np.maximum.reduce([funnel, r - BALLAST_R, BALLAST_Z0 - z, z - BALLAST_Z1])
    r = np.sqrt(x * x + y * y)                                      # kanal w osi (pod lacznikiem)
    shaft = np.maximum.reduce([r - BALLAST_SHAFT_R, BALLAST_Z1 - 1 - z, z - (Z_JOINT - HEX_DEPTH_BOTTOM + 0.5)])
    return np.minimum(chamber, shaft)


def part_bottom(x, y, z, face=None):
    d = np.maximum(sd_body(x, y, z), z - Z_JOINT)
    d = np.maximum(d, -sd_hex(x, y, z, HEX_R + HEX_CLR, Z_JOINT - HEX_DEPTH_BOTTOM, Z_JOINT + 1))
    d = np.maximum(d, -sd_ballast(x, y, z))
    for s in (-1, 1):
        sock = np.maximum(foot_sdf(x, y, z, s) - CLR, -(sd_body(x, y, z) + FOOT_EMBED + CLR))
        d = np.maximum(d, -sock)
    return d


def part_hex(x, y, z, face=None):
    return sd_hex(x, y, z, HEX_R, Z_JOINT - HEX_DEPTH_BOTTOM, Z_JOINT - HEX_DEPTH_BOTTOM + HEX_H)


def hex_connector_mesh():
    """Dokladnie jak u Mikolaja: graniastoslup 25 mm po wierzcholkach, 12 mm wysokosci."""
    ang = np.radians(np.arange(6) * 60.0)
    poly = np.c_[HEX_R * np.cos(ang), HEX_R * np.sin(ang)]
    from shapely.geometry import Polygon
    m = trimesh.creation.extrude_polygon(Polygon(poly), HEX_H)
    m.apply_translation([0, 0, Z_JOINT - HEX_DEPTH_BOTTOM])
    return m


def part_belly(x, y, z, face=None):
    d = np.maximum(sd_body(x, y, z), Z_JOINT - z)
    return np.maximum(d, z - (belly_zint(x, y) - 0.05))


def part_chest(x, y, z, face=None):
    d = sd_body(x, y, z)
    for s in (-1, 1):
        d = smin(d, sd_arm(x, y, z, s), ARM_BLEND)
    d = np.maximum(d, Z_JOINT - z)
    d = np.maximum(d, (belly_zint(x, y) + 0.05) - z)
    return np.maximum(d, -sd_hex(x, y, z, HEX_R + HEX_CLR, Z_JOINT - 1, Z_JOINT + HEX_DEPTH_CHEST))
    # misa pod glowe i czop: dokladnie (manifold) w chest_cup()


def hex_prism_mesh(r, z0, z1):
    from shapely.geometry import Polygon
    ang = np.radians(np.arange(6) * 60.0)
    m = trimesh.creation.extrude_polygon(Polygon(np.c_[r * np.cos(ang), r * np.sin(ang)]), z1 - z0)
    m.apply_translation([0, 0, z0])
    return m


def chest_cup(m, face):
    cup = mesh_sdf(lambda x, y, z, f: np.maximum(sd_head_base(x, y, z) - HEAD_CLR, Z_HEAD - z), face,
                   (-29, -28, Z_HEAD - 0.5), (29, 25, 80), 0.15, 150000)
    C = to_manifold(m) - to_manifold(cup) + to_manifold(hex_prism_mesh(NECK_HEX_R, Z_HEAD - 1.0, Z_HEAD + NECK_HEX_H))
    return from_manifold(C)


def part_head(x, y, z, face):
    d = np.maximum(sd_head_base(x, y, z), Z_HEAD - z)
    d = np.maximum(d, -sd_hex(x, y, z, NECK_HEX_R + HEX_CLR, Z_HEAD - 1, Z_HEAD + NECK_HEX_DEPTH))
    for s in (-1, 1):
        sock = np.maximum(ear_sdf(x, y, z, s) - CLR, -(sd_head_base(x, y, z) + EAR_EMBED + CLR))
        d = np.maximum(d, -sock)
    return d          # gniazda wkladek wycinane dokladnie (manifold) w head_pockets()


def part_ear(side):
    return lambda x, y, z, face=None: np.maximum(ear_sdf(x, y, z, side), -(sd_head_base(x, y, z) + EAR_EMBED))


def part_foot(side):
    def f(x, y, z, face=None):
        d = np.maximum(foot_sdf(x, y, z, side), -(sd_body(x, y, z) + FOOT_EMBED))
        return np.maximum(d, -pads_sdf(x, y, z, side, grow=CLR, depth_extra=CLR, raised=False))
    return f


def part_pads(side):
    return lambda x, y, z, face=None: pads_sdf(x, y, z, side)


# nazwa, funkcja, kolor, bbox (lo, hi), krok siatki, (wypelnienie, podpory)
WHITE, BLACK, PINK = 1, 2, 3


def parts_table():
    P = []
    P.append(('Panda bottom 100pct', part_bottom, WHITE, ((-33, -33, -1), (33, 33, Z_JOINT + 1)), 0.2))
    P.append(('Hex connector 100pct', part_hex, WHITE, ((-13, -12, 34), (13, 12, 49)), 0.1))
    P.append(('Belly', part_belly, WHITE, ((-32, -33, Z_JOINT - 1), (32, 0, 56)), 0.15))
    P.append(('Panda body', part_chest, BLACK, ((-46, -33, Z_JOINT - 1), (46, 33, 76)), 0.2))
    P.append(('Panda head', part_head, WHITE, ((-29, -27, Z_HEAD - 1), (29, 25, 104)), 0.15))
    for s, nm in ((-1, 'left'), (1, 'right')):
        ex = EAR_C[0] * s
        P.append((f'Ear {nm}', part_ear(s), BLACK, ((ex - 10, -4, 87), (ex + 10, 6, 108)), 0.12))
        fc = foot_frame(s)[0]
        P.append((f'Foot {nm}', part_foot(s), BLACK, (tuple(fc - 17), tuple(fc + 17)), 0.12))
        P.append((f'Paw pads {nm}', part_pads(s), WHITE, (tuple(fc - 14), tuple(fc + 14)), 0.08))
    lata = np.asarray(KONT['lata'])
    for s, nm in ((-1, 'left'), (1, 'right')):
        xs = np.sort(lata[:, 0] if s < 0 else -lata[:, 0])
        P.append((f'Eye patch {nm}', lambda x, y, z, f, s=s: f.patch(x, y, z, s), BLACK,
                  ((xs[0] - 1, -26, 70), (xs[-1] + 1, -6, 91)), 0.07))
        ex = EYE_C[0] * s
        P.append((f'Eye {nm}', lambda x, y, z, f, s=s: f.eye(x, y, z, s), WHITE,
                  ((ex - 5, -26, 74.5), (ex + 5, -10, 86)), 0.05))
        P.append((f'Pupil {nm}', lambda x, y, z, f, s=s: f.pupil(x, y, z, s), BLACK,
                  ((ex - 5, -26, 74.5), (ex + 5, -10, 86)), 0.05))
    P.append(('Nose', lambda x, y, z, f: f.nose_part(x, y, z), BLACK, ((-5, -30, 70), (5, -15, 79)), 0.06))
    P.append(('Mouth', lambda x, y, z, f: f.mouth_part(x, y, z), BLACK, ((-9, -28, 59), (9, -12, 72)), 0.06))
    P.append(('Tongue', lambda x, y, z, f: f.tongue_part(x, y, z), PINK, ((-6, -28, 60), (6, -12, 68.5)), 0.05))
    return P


# --------------------------------------------------------------------------- siatki
def mesh_sdf(f, face, lo, hi, h, target_faces=None):
    # siatka przesunieta o ulamek kroku, zeby plaszczyzny nie trafialy w wezly
    lo, hi = np.asarray(lo, float) - h * 0.3137, np.asarray(hi, float)
    n = np.ceil((hi - lo) / h).astype(int) + 1
    xs, ys, zs = (lo[i] + h * np.arange(n[i]) for i in range(3))
    vol = np.empty(n, np.float32)
    X, Y = np.meshgrid(xs, ys, indexing='ij')
    step = max(1, int(4e6 // (n[0] * n[1])))
    for k0 in range(0, n[2], step):
        zz = zs[k0:k0 + step]
        XX = np.repeat(X[:, :, None], len(zz), 2)
        YY = np.repeat(Y[:, :, None], len(zz), 2)
        ZZ = np.broadcast_to(zz, XX.shape)
        vol[:, :, k0:k0 + step] = f(XX, YY, ZZ, face)
    vol[vol == 0] = 1e-6
    vol[[0, -1], :, :] = vol[:, [0, -1], :] = 1.0
    vol[:, :, [0, -1]] = 1.0
    v, fa, _, _ = marching_cubes(vol, 0.0, spacing=(h, h, h))
    m = trimesh.Trimesh(v + lo, fa, process=True)
    if m.volume < 0:
        m.invert()
    if target_faces and len(m.faces) > target_faces:
        import fast_simplification
        for k in (1.0, 0.97, 1.03, 0.94, 1.06, 0.91, 1.09, 0.88, 1.12, 0.85, 1.15, 0.8):
            red = min(0.98, 1 - k * target_faces / len(m.faces))
            v2, f2 = fast_simplification.simplify(m.vertices, m.faces, red, agg=3)   # agg=3: blad < 0,01 mm
            m2 = trimesh.Trimesh(v2, f2, process=True)
            m2.update_faces(m2.nondegenerate_faces())
            m2.update_faces(m2.unique_faces())
            m2.remove_unreferenced_vertices()
            m2.merge_vertices()
            if m2.is_watertight and m2.is_winding_consistent:
                if m2.volume < 0:
                    m2.invert()
                m = m2
                break
    # usun okruchy (bryly mniejsze niz 0,5 mm3), zostaw prawdziwe czesci (np. 4 poduszki)
    comps = m.split(only_watertight=False)
    if len(comps) > 1:
        m = trimesh.util.concatenate([c for c in comps if abs(c.volume) > 0.5])
    return m


def build(names=None, verbose=True):
    face = Face()
    out = {}
    for name, f, col, (lo, hi), h in parts_table():
        if names and name not in names:
            continue
        t = time.time()
        h *= float(os.environ.get('PANDA_RES', '1'))
        big = np.prod(np.subtract(hi, lo)) > 40000          # duze czesci: wiecej trojkatow
        m = hex_connector_mesh() if f is part_hex else mesh_sdf(f, face, lo, hi, h, 150000 if big else 35000)
        if f is part_head:
            m = head_pockets(m, face)
        if f is part_chest:
            m = chest_cup(m, face)
        out[name] = (m, col)
        if verbose:
            print(f'{name:22s} faces={len(m.faces):7d} vol={m.volume/1000:7.2f} cm3 wt={m.is_watertight} '
                  f'bb={np.round(m.bounds, 1).tolist()} {time.time()-t:.1f}s', flush=True)
    return out


if __name__ == '__main__':
    os.makedirs(EXPORT, exist_ok=True)
    parts = build(sys.argv[1:] or None)
    for name, (m, col) in parts.items():
        m.export(os.path.join(EXPORT, name.replace(' ', '_') + '.stl'))
