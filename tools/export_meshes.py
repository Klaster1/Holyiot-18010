"""Export the Holyiot model as render meshes: one OBJ per material, pin labels grouped by colour.

Run inside FreeCAD with Holyiot.FCStd open, e.g. from the Python console:
`exec(open('/path/to/repo/tools/export_meshes.py').read())`.
Writes build/meshes/*.obj and build/meshes/manifest.json, which tools/render.py reads.
Coordinates stay in mm, as in the model.
"""

import json
import os

import FreeCAD as App
import MeshPart
import Part

doc = App.getDocument('Holyiot')
out = os.path.join(os.path.dirname(doc.FileName), 'build', 'meshes')
os.makedirs(out, exist_ok=True)

FINE = dict(LinearDeflection=0.002, AngularDeflection=0.05, Relative=False)

PARTS = {  # mesh name: (material key used by render.py, objects)
    'pcb': ('soldermask', ['PCB']),
    'castellations': ('enig', ['Castellations']),
    'inner_pads': ('enig', ['InnerPads']),
    'shield': ('nickel_silver', ['Shield']),
    'antenna': ('ceramic', ['Antenna']),
    'antenna_caps': ('silver', ['AntennaTerminations']),
    'silkscreen': ('silkscreen', [o.Name for o in doc.Markings.Group if o.Name.startswith('Silk') and o.TypeId == 'Part::Extrusion']),
    'laser_mark': ('laser_mark', [o.Name for o in doc.Markings.Group if o.Name.startswith('Mark') and o.TypeId == 'Part::Extrusion']),
}


def write(name, shape):
    mesh = MeshPart.meshFromShape(Shape=shape, **FINE)
    path = os.path.join(out, name + '.obj')
    mesh.write(path)
    return os.path.basename(path), mesh.CountFacets


manifest = {'units': 'mm', 'meshes': []}
for name, (material, names) in PARTS.items():
    shape = Part.makeCompound([doc.getObject(n).Shape for n in names])
    file, facets = write(name, shape)
    manifest['meshes'].append({'name': name, 'file': file, 'material': material, 'facets': facets})

# pin labels: one mesh per (view, colour), so render.py can give each an emissive colour
for group, view in (('LabelsTop', 'top'), ('LabelsBottom', 'bottom')):
    by_color = {}
    for o in doc.getObject(group).Group:
        if o.TypeId != 'Part::Part2DObjectPython':
            continue
        rgb = tuple(round(c, 3) for c in o.ViewObject.ShapeAppearance[0].DiffuseColor[:3])
        by_color.setdefault(rgb, []).append(o.Shape)
    for i, (rgb, shapes) in enumerate(sorted(by_color.items())):
        name = f'labels_{view}_{i}'
        file, facets = write(name, Part.makeCompound(shapes))
        manifest['meshes'].append({'name': name, 'file': file, 'material': 'label', 'color': rgb, 'view': view, 'facets': facets})

with open(os.path.join(out, 'manifest.json'), 'w') as f:
    json.dump(manifest, f, indent=1)
print('exported', len(manifest['meshes']), 'meshes,', sum(m['facets'] for m in manifest['meshes']), 'facets to', out)
