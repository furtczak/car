"""Uklada czesci w orientacji do druku i sklada projekt Bambu Studio (P1S) jak u Mikolaja.

Plyty wg kolorow (bez zmian filamentu w trakcie wydruku):
  1 BIALY  - dol 100% (z modyfikatorem 15% w pasie), lacznik 100%, glowa, brzuch, bialka oczu, poduszki
  2 CZARNY - korpus z rekami, uszy, stopy, laty, zrenice, nos, buzia
  3 ROZOWY - jezyk
Ustawienia drukarki/filamentow wziete z projektu Mikolaja (ref/bambu_project_settings.config).
"""
import json, os, sys, uuid, zipfile
import numpy as np, trimesh
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import panda_rolypoly as P

EXPORT = P.EXPORT
PLATE, PLATE_STEP = 256.0, 307.2
COLOURS = ['#FFFFFF', '#161616', '#EE7C86', '#161616']
MODIFIER_Z = P.BODY_ZEQ + 1.0      # powyzej tej wysokosci (w ukladzie pandy) dol ma 15%

# ustawienia obiektow (klucze jak w model_settings.config Mikolaja)
SOLID = {'sparse_infill_density': '100%', 'sparse_infill_pattern': 'zig-zag',
         'skeleton_infill_density': '100%', 'skin_infill_density': '100%', 'enable_support': '0'}
LIGHT = {'enable_support': '1', 'support_type': 'tree(auto)', 'support_on_build_plate_only': '1',
         'sparse_infill_pattern': 'lightning', 'sparse_infill_density': '15%'}
SMALL = {'enable_support': '0'}


def rot_a_to_b(a, b):
    a, b = np.asarray(a, float) / np.linalg.norm(a), np.asarray(b, float) / np.linalg.norm(b)
    v, c = np.cross(a, b), a @ b
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3) if c > 0 else np.diag([1, -1, -1])
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * (1 / (1 + c))


def print_orientation(name, face):
    """Macierz obrotu 3x3: uklad pandy -> uklad druku (Z w gore od stolu)."""
    z = np.array([0, 0, 1.0])
    if 'bottom' in name:
        return np.diag([1.0, -1.0, -1.0])                  # plaska strona na stol, kopula do gory
    if name.startswith('Ear'):
        return rot_a_to_b([0, 1, 0], -z)                   # splaszczony tyl na stol
    if name.startswith('Foot'):
        s = -1 if 'left' in name else 1
        return rot_a_to_b(P.foot_frame(s)[3], -z)          # podeszwa na stol
    if name.startswith('Paw'):
        s = -1 if 'left' in name else 1
        return rot_a_to_b(P.foot_frame(s)[3], z)           # plaskie dno poduszek na stol
    if name.startswith(('Eye', 'Pupil')):
        s = -1 if 'left' in name else 1
        return rot_a_to_b(face.eyes[s]['grp'].n, z)        # wspolne plaskie dno wkladek
    if name == 'Nose':
        return rot_a_to_b(face.gn.n, z)
    if name in ('Mouth', 'Tongue'):
        return rot_a_to_b(face.gm.n, z)
    return np.eye(3)                                        # korpus, glowa, brzuch, lacznik: jak stoja


def settings_for(name):
    if '100pct' in name:
        return SOLID
    if name in ('Panda head', 'Panda body'):
        return LIGHT
    if name == 'Belly':
        return {'enable_support': '0', 'sparse_infill_pattern': 'lightning', 'sparse_infill_density': '15%'}
    return SMALL


def model_xml(meshes):
    """meshes: lista (object_id, trimesh) -> tresc pliku 3D/Objects/*.model"""
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
           'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
           'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">',
           ' <metadata name="BambuStudio:3mfVersion">1</metadata>', ' <resources>']
    for oid, m in meshes:
        out.append(f'  <object id="{oid}" p:UUID="{uuid.uuid4()}" type="model">\n   <mesh>\n    <vertices>')
        out.append('\n'.join(f'     <vertex x="{v[0]:.5f}" y="{v[1]:.5f}" z="{v[2]:.5f}"/>' for v in m.vertices))
        out.append('    </vertices>\n    <triangles>')
        out.append('\n'.join(f'     <triangle v1="{f[0]}" v2="{f[1]}" v3="{f[2]}"/>' for f in m.faces))
        out.append('    </triangles>\n   </mesh>\n  </object>')
    out.append(' </resources>\n <build/>\n</model>\n')
    return '\n'.join(out)


def layout(items):
    """Proste ukladanie w rzedach na stole 256 x 256 (odstep 6 mm). items: lista (name, mesh)."""
    pos, x, y, row_h, gap = {}, 8.0, 8.0, 0.0, 6.0
    for name, m in sorted(items, key=lambda it: -it[1].extents[1]):
        w, d = m.extents[0], m.extents[1]
        if x + w > PLATE - 8:
            x, y, row_h = 8.0, y + row_h + gap, 0.0
        pos[name] = (x + w / 2, y + d / 2)
        x += w + gap
        row_h = max(row_h, d)
    if y + row_h > PLATE - 8:
        raise RuntimeError('czesci nie mieszcza sie na plycie')
    # wysrodkuj grupe na stole (z dala od strefy wykluczonej P1S w rogu 0..18 x 0..28 mm)
    lo = np.min([[pos[n][0] - m.extents[0] / 2, pos[n][1] - m.extents[1] / 2] for n, m in items], 0)
    hi = np.max([[pos[n][0] + m.extents[0] / 2, pos[n][1] + m.extents[1] / 2] for n, m in items], 0)
    sh = PLATE / 2 - (lo + hi) / 2
    return {n: (p[0] + sh[0], p[1] + sh[1]) for n, p in pos.items()}


def build_3mf(path=None, face=None):
    path = path or os.path.join(EXPORT, 'Panda_RolyPoly_P1S.3mf')
    face = face or P.Face()
    plates = {P.WHITE: [], P.BLACK: [], P.PINK: []}
    oriented = {}
    for name, f, col, bb, h in P.parts_table():
        m = trimesh.load(os.path.join(EXPORT, name.replace(' ', '_') + '.stl'))
        R = print_orientation(name, face)
        T = np.eye(4); T[:3, :3] = R
        m = m.copy(); m.apply_transform(T)
        c = m.bounds.mean(0)
        m.apply_translation([-c[0], -c[1], -m.bounds[0, 2]])
        oriented[name] = (m, col, R)
        plates[col].append((name, m))
    order = [P.WHITE, P.BLACK, P.PINK]
    plate_name = {P.WHITE: 'BIALY', P.BLACK: 'CZARNY', P.PINK: 'ROZOWY'}
    files, rels, res_xml, build_xml, cfg = {}, [], [], [], []
    oid = 1
    for pi, col in enumerate(order):
        pos = layout(plates[col])
        ox, oy = (pi % 2) * PLATE_STEP, -(pi // 2) * PLATE_STEP
        inst = []
        for name, m in plates[col]:
            fn = f'/3D/Objects/object_{len(files) + 1}.model'
            comps = [(oid, m)]
            mod = None
            if 'bottom' in name:
                # modyfikator: pas powyzej MODIFIER_Z (w druku to dolne warstwy, bo dol jest odwrocony)
                hz = P.Z_JOINT - MODIFIER_Z
                mod = trimesh.creation.box([m.extents[0] + 4, m.extents[1] + 4, hz])
                mod.apply_translation([0, 0, hz / 2])
                comps.append((oid + 1, mod))
            files[fn] = model_xml(comps)
            rels.append(fn)
            top = oid + len(comps)
            comp_xml = ''.join(f'\n    <component p:path="{fn}" objectid="{i}" p:UUID="{uuid.uuid4()}" '
                               f'transform="1 0 0 0 1 0 0 0 1 0 0 0"/>' for i, _ in comps)
            res_xml.append(f'  <object id="{top}" p:UUID="{uuid.uuid4()}" type="model">\n   <components>'
                           f'{comp_xml}\n   </components>\n  </object>')
            x, y = pos[name]
            build_xml.append(f'  <item objectid="{top}" p:UUID="{uuid.uuid4()}" '
                             f'transform="1 0 0 0 1 0 0 0 1 {x + ox:.4f} {y + oy:.4f} 0" printable="1"/>')
            st = settings_for(name)
            o = [f'  <object id="{top}">', f'    <metadata key="name" value="{name}"/>',
                 f'    <metadata key="extruder" value="{col}"/>']
            o += [f'    <metadata key="{k}" value="{v}"/>' for k, v in st.items()]
            o += ['    <metadata key="wall_generator" value="arachne"/>', f'    <metadata face_count="{len(m.faces)}"/>']
            for i, mm in comps:
                is_mod = mm is mod
                o += [f'    <part id="{i}" subtype="{"modifier_part" if is_mod else "normal_part"}">',
                      f'      <metadata key="name" value="{name + " - pas 15%" if is_mod else name}"/>',
                      '      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>',
                      f'      <metadata key="source_file" value="{name.replace(" ", "_")}.stl"/>',
                      '      <metadata key="source_object_id" value="0"/>',
                      f'      <metadata key="source_volume_id" value="{1 if is_mod else 0}"/>']
                if is_mod:
                    o += ['      <metadata key="sparse_infill_density" value="15%"/>',
                          '      <metadata key="sparse_infill_pattern" value="grid"/>']
                o += [f'      <mesh_stat face_count="{len(mm.faces)}" edges_fixed="0" degenerate_facets="0" '
                      'facets_removed="0" facets_reversed="0" backwards_edges="0"/>', '    </part>']
            o.append('  </object>')
            cfg.append('\n'.join(o))
            inst.append(top)
            oid = top + 1
        names = ', '.join(sorted(n for n, _ in plates[col]))
        pl = [f'  <plate>', f'    <metadata key="plater_id" value="{pi + 1}"/>',
              f'    <metadata key="plater_name" value="{plate_name[col]} - {names}"/>',
              '    <metadata key="locked" value="false"/>']
        for k, t in enumerate(inst):
            pl += ['    <model_instance>', f'      <metadata key="object_id" value="{t}"/>',
                   '      <metadata key="instance_id" value="0"/>',
                   f'      <metadata key="identify_id" value="{100 + t}"/>', '    </model_instance>']
        pl.append('  </plate>')
        cfg.append('\n'.join(pl))

    main = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
            'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021" '
            'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" requiredextensions="p">',
            ' <metadata name="Application">BambuStudio-02.07.01.62</metadata>',
            ' <metadata name="BambuStudio:3mfVersion">1</metadata>',
            ' <metadata name="Title">Panda Roly-Poly</metadata>',
            ' <resources>', *res_xml, ' </resources>', ' <build>', *build_xml, ' </build>', '</model>', '']
    ps = json.load(open(os.path.join(HERE, 'ref', 'bambu_project_settings.config')))
    ps['filament_colour'] = COLOURS
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n <Default Extension="png" ContentType="image/png"/>\n <Default Extension="gcode" ContentType="text/x.gcode"/>\n</Types>')
        z.writestr('_rels/.rels', '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n</Relationships>')
        z.writestr('3D/3dmodel.model', '\n'.join(main))
        z.writestr('3D/_rels/3dmodel.model.rels', '<?xml version="1.0" encoding="UTF-8"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
                   + '\n'.join(f' <Relationship Target="{fn}" Id="rel-{i + 1}" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>' for i, fn in enumerate(rels))
                   + '\n</Relationships>')
        for fn, xml in files.items():
            z.writestr(fn.lstrip('/'), xml)
        z.writestr('Metadata/model_settings.config', '<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + '\n'.join(cfg) + '\n</config>\n')
        z.writestr('Metadata/project_settings.config', json.dumps(ps, indent=4))
    return path, oriented


if __name__ == '__main__':
    p, oriented = build_3mf()
    for name, (m, col, R) in oriented.items():
        print(f'{name:22s} druk {np.round(m.extents, 1)}')
    print('zapisano', p, os.path.getsize(p) // 1024, 'kB')
