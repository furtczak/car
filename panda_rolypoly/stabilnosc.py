"""Szacunek srodka ciezkosci zlozonej pandy (czy wstaje po przechyleniu).

Model masy PLA (1,24 g/cm3): czesci '100pct' pelne; pozostale = 2 obrysy (0,84 mm)
+ wypelnienie 15% liczone jako `INFILL_EFF` objetosci wnetrza. Male czesci (< 2 cm3) pelne.
"""
import glob, os, sys
import numpy as np, trimesh
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import panda_rolypoly as P

RHO, WALL = 1.24, 0.84


def mass_props(m, name, infill_eff):
    if '100pct' in name or m.volume < 2000:
        return m.volume * RHO / 1000, m.center_mass
    tri = m.triangles
    a = m.area_faces
    cs = tri.mean(1)
    shell_v = a.sum() * WALL
    shell_c = (cs * a[:, None]).sum(0) / a.sum()
    inner_v = max(m.volume - shell_v, 0)
    mass = (shell_v + inner_v * infill_eff) * RHO / 1000
    c = (shell_c * shell_v + m.center_mass * inner_v * infill_eff) / (shell_v + inner_v * infill_eff)
    return mass, c


BAND_Z = P.BODY_ZEQ + 1.0    # powyzej tej wysokosci dol ma modyfikator 15% (w 3MF)


def bottom_props(infill_eff, h=0.4):
    """Dol liczony z SDF: 100% ponizej BAND_Z, wyzej obrys + wypelnienie."""
    xs = np.arange(-32, 32, h)
    zs = np.arange(0, P.Z_JOINT + h, h)
    X, Y, Z = np.meshgrid(xs, xs, zs, indexing='ij')
    d = P.part_bottom(X, Y, Z)
    ins = d < 0
    w = np.where((Z < BAND_Z) | (d > -WALL), 1.0, infill_eff) * ins
    m = w.sum() * h ** 3 * RHO / 1000
    c = np.array([(X * w).sum(), (Y * w).sum(), (Z * w).sum()]) / w.sum()
    return m, c


def ballast_props(mass, bulk, h=0.3):
    """Obciaznik wsypany od dna komory (gestosc nasypowa `bulk` g/cm3)."""
    xs = np.arange(-26, 26, h)
    zs = np.arange(0, P.Z_JOINT, h)
    X, Y, Z = np.meshgrid(xs, xs, zs, indexing='ij')
    ins = P.sd_ballast(X, Y, Z) < 0
    vol_per_z = ins.sum((0, 1)) * h ** 3
    cum = np.cumsum(vol_per_z)
    need = mass / bulk * 1000
    k = min(np.searchsorted(cum, need), len(zs) - 1)
    w = ins & (Z <= zs[k])
    got = w.sum() * h ** 3 * bulk / 1000
    return got, np.array([X[w].mean(), Y[w].mean(), Z[w].mean()]), zs[k], cum[-1] / 1000


def report(infill_eff=0.15, extra=None, verbose=True):
    tot, mom = 0.0, np.zeros(3)
    for name, f, col, bb, h in P.parts_table():
        fn = os.path.join(HERE, 'export', name.replace(' ', '_') + '.stl')
        m = trimesh.load(fn)
        if 'bottom' in name:
            ms, c = bottom_props(infill_eff)
        else:
            ms, c = mass_props(m, name, infill_eff)
        tot += ms; mom += ms * c
        if verbose:
            print(f'{name:22s} {ms:6.1f} g   z_sr = {c[2]:5.1f} mm')
    if extra:
        for nm, ms, c in extra:
            tot += ms; mom += ms * np.asarray(c)
            print(f'{nm:22s} {ms:6.1f} g   z_sr = {c[2]:5.1f} mm')
    com = mom / tot
    R = P.BODY_A ** 2 / P.BODY_CLO
    if com[2] < R:
        tilt = f'pochylenie w spoczynku {np.degrees(np.arctan2(com[1], R - com[2])):+.1f} st.'
    else:
        tilt = 'NIESTABILNA: przewraca sie'
    print(f'RAZEM {tot:.0f} g, srodek ciezkosci z = {com[2]:.1f} mm (y = {com[1]:+.2f}), '
          f'promien toczenia = {R:.1f} mm, zapas = {R - com[2]:.1f} mm, {tilt}')
    return tot, com


if __name__ == '__main__':
    print('--- bez obciaznika, wypelnienie 15%')
    report(0.15)
    for nm, bulk in (('srut/kulki stalowe', 4.6), ('srut olowiany', 6.8)):
        for g in (60, 80, 100, 120):
            got, c, zt, vmax = ballast_props(g, bulk)
            if got < g * 0.97:
                continue
            print(f'--- {nm} {g} g (nasyp do z = {zt:.1f} mm, komora {vmax:.1f} cm3)')
            for e in (0.15, 0.08):
                report(e, extra=[(nm, got, c)], verbose=False)
