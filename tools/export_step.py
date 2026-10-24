"""Export the module as a coloured STEP AP242 assembly: export/Holyiot-18010.step.

Run inside the FreeCAD GUI with Holyiot.FCStd open (colours come from the view providers).
The STEP tree mirrors the FreeCAD one: an assembly "Holyiot-18010 nRF52840" with one named,
coloured part per body. Geometry only: the pin labels and the markings (silkscreen, laser text)
stay out. The text alone would be over 80 % of the file and of the faces a STEP importer heals.
The user's STEP preferences, the group visibility and the document's modified flag are restored.
"""

import os

import FreeCAD as App
import FreeCADGui as Gui
import ImportGui

doc = App.getDocument('Holyiot')
out_dir = os.path.join(os.path.dirname(doc.FileName), 'export')
os.makedirs(out_dir, exist_ok=True)
path = os.path.join(out_dir, 'Holyiot-18010.step')

step = App.ParamGet('User parameter:BaseApp/Preferences/Mod/Part/STEP')
saved = {k: step.GetString(k) for k in ('Scheme', 'Company', 'Author', 'Product')}
excluded = [doc.getObject(n) for n in ('Markings', 'LabelsTop', 'InnerOverlay', 'LabelsBottom')]
visible = [g.ViewObject.Visibility for g in excluded]
modified = Gui.getDocument(doc.Name).Modified
try:
    step.SetString('Scheme', 'AP242DIS')
    step.SetString('Author', 'Klaster_1')
    step.SetString('Company', '')
    step.SetString('Product', 'Holyiot-18010 nRF52840 BLE module')
    for g in excluded:
        g.ViewObject.Visibility = False
    ImportGui.export([doc.getObject('Module')], path, {'exportHidden': False, 'keepPlacement': False, 'legacy': False})
finally:
    for g, v in zip(excluded, visible):
        g.ViewObject.Visibility = v
    for k, v in saved.items():
        step.SetString(k, v)
    Gui.getDocument(doc.Name).Modified = modified

# Right after FreeCAD opens the file, the exporter can silently write only some bodies.
with open(path, encoding='utf8', errors='replace') as f:
    step_text = f.read()
missing = [o.Label for o in doc.Module.Group if o.isDerivedFrom('PartDesign::Body') and f"PRODUCT('{o.Label}'" not in step_text]
if missing:
    raise RuntimeError(f'STEP export is missing {missing}; run the script again once the document has loaded')
print('wrote', path, round(os.path.getsize(path) / 1e6, 2), 'MB')
