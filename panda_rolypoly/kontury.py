"""Wyciaga kontury detali twarzy pandy ze zdjecia referencyjnego (widok z przodu).

Wynik: ref/kontury_mm.json z konturami w mm (X w prawo, Z w gore, podloze Z = 0).
Skala: 0.0978 mm/px, wzieta z szerokosci kuli (63,2 mm, jak dol Mikolaja).
"""
import json, os
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from skimage import measure

HERE = os.path.dirname(os.path.abspath(__file__))
S, XC, YF = 0.0978, 541.5, 1245.0          # mm/px, os symetrii [px], podloze [px]

a = np.asarray(Image.open(os.path.join(HERE, 'ref', 'panda_zdjecie.webp')).convert('RGB')).astype(float)
br = a.mean(2)


def to_mm(c):
    return np.c_[(c[:, 1] - XC) * S, (YF - c[:, 0]) * S]


def comp_at(mask, pt):
    lab, _ = ndi.label(mask)
    return lab == lab[pt[1], pt[0]]


def contour(mask, sigma=1.0):
    m = ndi.gaussian_filter(mask.astype(float), sigma)
    return to_mm(max(measure.find_contours(m, 0.5), key=len))


def mirror(mask):
    """Odbicie maski wzgledem osi symetrii XC (kolumna x -> 2*XC - x)."""
    xs = np.arange(mask.shape[1])
    src = np.clip(np.round(2 * XC - xs).astype(int), 0, mask.shape[1] - 1)
    return mask[:, src]


def sym_mask_contour(mask, sigma=2.5):
    """Kontur z maski usrednionej z jej odbiciem (symetryczny, bez prazkow druku)."""
    m = (mask.astype(float) + mirror(mask).astype(float)) / 2
    return contour(m, sigma)


def smooth_star(poly, keep=8, n=720):
    """Kontur gwiazdzisty wygladzony do `keep` harmonicznych promienia (usuwa prazki druku)."""
    c = poly.mean(0)
    t = np.linspace(-np.pi, np.pi, n, endpoint=False)
    ang = np.arctan2(poly[:, 1] - c[1], poly[:, 0] - c[0])
    r = np.hypot(poly[:, 0] - c[0], poly[:, 1] - c[1])
    o = np.argsort(ang)
    r = np.interp(t, np.r_[ang[o] - 2 * np.pi, ang[o], ang[o] + 2 * np.pi], np.r_[r[o], r[o], r[o]])
    F = np.fft.rfft(r)
    F[keep + 1:] = 0
    r = np.fft.irfft(F, n)
    return np.c_[c[0] + r * np.cos(t), c[1] + r * np.sin(t)]


reg = np.zeros(br.shape, bool)
reg[300:650, 280:800] = True
dark = ndi.binary_opening((br < 95) & reg, iterations=1)
pink = (a[:, :, 0] - a[:, :, 1] > 45) & reg

# domkniecie morfologiczne zalewa przerwy miedzy prazkami druku na brzegu laty
disk = np.hypot(*np.mgrid[-7:8, -7:8]) <= 7
patch_l = ndi.binary_fill_holes(ndi.binary_closing(comp_at(dark, (360, 450)), disk))
patch_r = ndi.binary_fill_holes(ndi.binary_closing(comp_at(dark, (720, 450)), disk))
# lewa lata: srednia z lewej i odbitej prawej
lm = (patch_l.astype(float) + mirror(patch_r).astype(float)) / 2
out = {
    'lata': smooth_star(contour(lm, 3.0)),
    'nos': sym_mask_contour(comp_at(dark, (540, 480))),
    'buzia': sym_mask_contour(ndi.binary_fill_holes(comp_at(dark, (470, 540)) | pink), 2.0),
    'jezyk': sym_mask_contour(ndi.binary_opening(pink, iterations=1)),
}
json.dump({k: np.round(v, 4).tolist() for k, v in out.items()},
          open(os.path.join(HERE, 'ref', 'kontury_mm.json'), 'w'))
for k, v in out.items():
    print(k, len(v), v.min(0).round(2), v.max(0).round(2))
