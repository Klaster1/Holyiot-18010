"""Build the parametric Holyiot-18010 (nRF52840) module model in the open `Holyiot` document.

Run inside FreeCAD with Holyiot.FCStd open, e.g. from the Python console:
`exec(open('/path/to/repo/tools/build_model.py').read())`.

Document layout (all dimensions are expressions on `Params`, all pad positions live in `Pinout`):

    Params        App::VarSet         every dimension; Derived group is computed, read-only
    Pinout        Spreadsheet         pin table with aliases pinN_x / pinN_y / pinN_label
    Module        App::Part           "Holyiot-18010 nRF52840"
      PCB                  Body       board with castellation half-holes  (FR-4, black mask look)
      Castellations        Body       pins 1-37: pads on both faces + plated half-hole barrel (ENIG)
      InnerPads            Body       pins 38-55 on the bottom face (ENIG)
      Shield               Body       RF shield can (nickel silver)
      Antenna              Body       ceramic chip antenna
      AntennaTerminations  Body       its silver end caps
      Markings             Group      silkscreen on the PCB, laser marking on the shield
      LabelsTop            Group      edge pin labels readable in top view
      InnerOverlay         Group      inner pads 38-55 + labels drawn above the shield (top view)
      LabelsBottom         Group      pin labels readable in bottom view (hidden)

The script is re-runnable: it deletes every object it created (tagged `HolyiotGen`), rebuilds
them and saves. `Params` is created once and never overwritten, so hand-tuned values survive.

Coordinates: origin at the board centre, PCB bottom face at z = 0, +Y towards the antenna,
pin 1 top-left when looking down at the shield (datasheet "TOP-VIEW").
Sources (see docs/README.md): DS = Holyiot-18010 datasheet, PH = AliExpress product photos.
"""

import math
import os

import FreeCAD as App
import FreeCADGui as Gui
import Materials
import Part
import Sketcher
from draftobjects.clone import Clone
from draftobjects.shapestring import ShapeString
from draftviewproviders.view_clone import ViewProviderClone
from draftviewproviders.view_shapestring import ViewProviderShapeString

doc = App.getDocument('Holyiot')
TAG = 'HolyiotGen'
LICENSE = ('CC0 1.0 Universal', 'https://creativecommons.org/publicdomain/zero/1.0/')
P = 'Params.'  # expression prefix

# Fonts are bundled in <project>/fonts; a leading "." makes ShapeString resolve them relative to the .FCStd.
FONT_LABEL = './fonts/RobotoCondensed-Bold.ttf'
FONT_SILK = './fonts/RobotoCondensed-Regular.ttf'
FONT_MARK = './fonts/Roboto-Regular.ttf'
FONT_LOGO = './fonts/Quicksand-Light.ttf'

# --------------------------------------------------------------------------- parameters
# (name, type, group, value, tooltip). Derived parameters get an expression from DERIVED instead.
PARAMS = [
    ('BoardWidth', 'Length', 'Board', 13.5, 'PCB width along X. DS'),
    ('BoardHeight', 'Length', 'Board', 18.0, 'PCB length along Y. DS'),
    ('BoardThickness', 'Length', 'Board', 1.0, 'PCB thickness. ESTIMATE (vendor: 2.7 mm overall) - measure'),
    ('CopperThickness', 'Length', 'Board', 0.035, 'Pad height above the PCB faces (1 oz copper + ENIG)'),
    ('PlatingThickness', 'Length', 'Board', 0.025, 'Castellation barrel plating'),
    ('OuterPadCountSide', 'Integer', 'Castellations', 13, 'Pads per long side: pins 1-13 and 25-37. DS'),
    ('OuterPadCountBottom', 'Integer', 'Castellations', 11, 'Pads on the bottom edge: pins 14-24. DS'),
    ('OuterPadHeight', 'Length', 'Castellations', 0.7, 'Pad size along the board edge. PH'),
    ('OuterPadSpacing', 'Length', 'Castellations', 0.4, 'Gap between neighbouring pads (1.1 mm pitch). DS'),
    ('OuterPadWidth', 'Length', 'Castellations', 0.9, 'Bottom-face pad depth, board edge inwards. PH'),
    ('OuterPadTopWidth', 'Length', 'Castellations', 0.5, 'Top-face pad depth, board edge inwards. PH'),
    ('OuterPadRadius', 'Length', 'Castellations', 0.25, 'Finished (plated) half-hole radius. ESTIMATE from PH'),
    ('OuterPadOffsetBottom', 'Length', 'Castellations', 1.15, 'Board bottom edge to lower edge of pins 13/25 (centre 1.5). DS'),
    ('OuterPadOffsetSide', 'Length', 'Castellations', 0.9, 'Board side edge to outer edge of pins 14/24 (centre 1.25). DS'),
    ('InnerPadCount', 'Integer', 'InnerPads', 9, 'Pads per inner column: 38-46 and 47-55. DS'),
    ('InnerPadWidth', 'Length', 'InnerPads', 1.0, 'Inner pad size along X. DS'),
    ('InnerPadHeight', 'Length', 'InnerPads', 0.7, 'Inner pad size along Y. DS'),
    ('InnerPadSpacing', 'Length', 'InnerPads', 0.4, 'Gap between inner pads (1.1 mm pitch). DS'),
    ('OuterInnerPadGap', 'Length', 'InnerPads', 2.0, 'Board side edge to outer edge of an inner column (columns 8.5 apart). DS'),
    ('InnerPadOffsetBottom', 'Length', 'InnerPads', 3.35, 'Board bottom edge to lower edge of pins 46/55 (centre 3.7). DS'),
    ('ShieldOffsetSide', 'Length', 'Shield', 0.9, 'Board side edge to shield wall. PH'),
    ('ShieldOffsetBottom', 'Length', 'Shield', 0.7, 'Board bottom edge to shield wall. PH'),
    ('ShieldHeight', 'Length', 'Shield', 14.6, 'Shield length along Y. PH'),
    ('ShieldThickness', 'Length', 'Shield', 1.7, 'Shield height above the PCB. ESTIMATE (2.7 mm overall) - measure'),
    ('ShieldCornerRadius', 'Length', 'Shield', 0.4, 'Vertical corner radius'),
    ('AntennaWidth', 'Length', 'Antenna', 8.0, 'Chip antenna length along X. PH'),
    ('AntennaHeight', 'Length', 'Antenna', 1.0, 'Chip antenna size along Y. PH'),
    ('AntennaThickness', 'Length', 'Antenna', 1.0, 'Chip antenna height above the PCB. ESTIMATE'),
    ('AntennaOffsetTop', 'Length', 'Antenna', 0.3, 'Board top edge to antenna. PH'),
    ('AntennaTerminalWidth', 'Length', 'Antenna', 0.8, 'Silver end cap length'),
    ('MarkingThickness', 'Length', 'Markings', 0.01, 'Silkscreen and laser marking height'),
    ('SilkTitleSize', 'Length', 'Markings', 0.75, 'Cap height of the HOLYIOT-18010-NRF52840 silkscreen'),
    ('SilkTitleOffsetTop', 'Length', 'Markings', 2.45, 'Board top edge to silkscreen title baseline'),
    ('LabelSize', 'Length', 'Labels', 0.5, 'Pin label cap height'),
    ('LabelGap', 'Length', 'Labels', 0.3, 'Gap between a pad and its label'),
    ('ShieldWidth', 'Length', 'Derived', None, 'BoardWidth - 2 * ShieldOffsetSide'),
    ('OuterPadPitch', 'Length', 'Derived', None, 'OuterPadHeight + OuterPadSpacing'),
    ('InnerPadPitch', 'Length', 'Derived', None, 'InnerPadHeight + InnerPadSpacing'),
    ('SidePadFirstY', 'Length', 'Derived', None, 'Y of the centre of pins 13/25 (lowest side pads)'),
    ('BottomPadFirstX', 'Length', 'Derived', None, 'X of the centre of pin 14 (left-most bottom pad)'),
    ('InnerPadColumnX', 'Length', 'Derived', None, '|X| of the inner pad column centres'),
    ('InnerPadFirstY', 'Length', 'Derived', None, 'Y of the centre of pins 46/55 (lowest inner pads)'),
    ('ShieldBottomY', 'Length', 'Derived', None, 'Y of the lower shield wall'),
    ('ModuleHeight', 'Length', 'Derived', None, 'PCB bottom face to shield top'),
]
OBSOLETE_PARAMS = ['ShieldEdgeRadius']  # removed from older documents on rebuild
DERIVED = {
    'ShieldWidth': 'BoardWidth - 2 * ShieldOffsetSide',
    'OuterPadPitch': 'OuterPadHeight + OuterPadSpacing',
    'InnerPadPitch': 'InnerPadHeight + InnerPadSpacing',
    'SidePadFirstY': '-BoardHeight / 2 + OuterPadOffsetBottom + OuterPadHeight / 2',
    'BottomPadFirstX': '-BoardWidth / 2 + OuterPadOffsetSide + OuterPadHeight / 2',
    'InnerPadColumnX': 'BoardWidth / 2 - OuterInnerPadGap - InnerPadWidth / 2',
    'InnerPadFirstY': '-BoardHeight / 2 + InnerPadOffsetBottom + InnerPadHeight / 2',
    'ShieldBottomY': '-BoardHeight / 2 + ShieldOffsetBottom',
    'ModuleHeight': 'BoardThickness + ShieldThickness',
}

# --------------------------------------------------------------------------- pinout (DS section 3.2)
PINS = {
    1: 'GND', 2: 'P1.11', 3: 'P1.10', 4: 'P1.13', 5: 'P1.15', 6: 'P0.03', 7: 'P0.02', 8: 'P0.28', 9: 'P0.29',
    10: 'P0.30', 11: 'P0.31', 12: 'P0.04', 13: 'P0.05', 14: 'VDD_nRF', 15: 'P0.07', 16: 'P1.09', 17: 'P0.12',
    18: 'P0.23', 19: 'P0.21', 20: 'P0.19', 21: 'P0.18', 22: 'VBUS', 23: 'D-', 24: 'D+', 25: 'GND', 26: 'P0.22',
    27: 'P1.00', 28: 'P1.03', 29: 'P1.01', 30: 'P1.02', 31: 'SWDCLK', 32: 'SWDIO', 33: 'P1.04', 34: 'P1.06',
    35: 'P0.09', 36: 'P0.10', 37: 'GND', 38: 'P1.14', 39: 'P1.12', 40: 'P0.25', 41: 'P0.11', 42: 'P1.08',
    43: 'P0.27', 44: 'P0.08', 45: 'P0.06', 46: 'P0.26', 47: 'P1.07', 48: 'P1.05', 49: 'P0.24', 50: 'P0.20',
    51: 'P0.17', 52: 'P0.15', 53: 'P0.14', 54: 'P0.13', 55: 'P0.16',
}
FUNC = {  # nRF52840 alternate functions that matter for a programming / test jig
    'GND': 'Ground', 'VDD_nRF': 'Supply, 3.9 V max', 'VBUS': 'USB supply, 5.8 V max', 'D-': 'USB D-', 'D+': 'USB D+',
    'SWDCLK': 'SWD clock', 'SWDIO': 'SWD data', 'P0.18': 'GPIO / nRESET',
    'P0.09': 'GPIO / NFC1', 'P0.10': 'GPIO / NFC2', 'P0.07': 'GPIO / TRACECLK',
    'P1.00': 'GPIO / TRACEDATA0', 'P0.11': 'GPIO / TRACEDATA1', 'P0.12': 'GPIO / TRACEDATA2', 'P1.09': 'GPIO / TRACEDATA3',
}
for _pin, _ain in (('P0.02', 0), ('P0.03', 1), ('P0.04', 2), ('P0.05', 3), ('P0.28', 4), ('P0.29', 5), ('P0.30', 6), ('P0.31', 7)):
    FUNC[_pin] = f'GPIO / AIN{_ain}'

LABEL_COLORS = {
    'ground': (0.62, 0.62, 0.66), 'power': (1.00, 0.33, 0.28), 'swd': (1.00, 0.62, 0.10), 'reset': (1.00, 0.85, 0.20),
    'usb': (0.30, 0.72, 1.00), 'nfc': (0.78, 0.52, 1.00), 'analog': (0.45, 0.86, 0.45), 'gpio': (0.93, 0.93, 0.93),
}


def pin_kind(name):
    if name == 'GND': return 'ground'
    if name in ('VDD_nRF', 'VBUS'): return 'power'
    if name.startswith('SWD'): return 'swd'
    if name == 'P0.18': return 'reset'
    if name in ('D-', 'D+'): return 'usb'
    if name in ('P0.09', 'P0.10'): return 'nfc'
    if 'AIN' in FUNC.get(name, ''): return 'analog'
    return 'gpio'


def pin_location(k):
    if k <= 13: return 'left'
    if k <= 24: return 'bottom'
    if k <= 37: return 'right'
    if k <= 46: return 'inner-left'
    return 'inner-right'


# --------------------------------------------------------------------------- materials (<project>/materials)
MAT = {  # key: (file in materials/, UUID in that file)
    'fr4': ('FR4', 'dbf70b65-0510-5c45-8565-59429eea8ac7'),
    'mask': ('SolderMask-Black', '8751821c-8d9e-59d7-80dc-1af2aef63c75'),
    'enig': ('ENIG-Gold', '39b13bc2-893c-5158-992a-19ff4f98c76a'),
    'shield': ('NickelSilver-CuNi18Zn20', 'a974743e-8a0c-5cfd-a96c-ac684334375a'),
    'ceramic': ('Ceramic-Alumina', 'b7373114-ddd5-5f96-aa51-3cce7929e54f'),
    'silk': ('Silkscreen-White', 'b65b9509-1d91-5d2f-a106-79b160de3b1e'),
    'laser': ('LaserMark-Dark', '1df9f119-23fd-5cb7-ad72-4a9d15818618'),
    'silver': ('Silver-Termination', 'f56f90a5-009a-5c13-ada3-8d6e20aad4a5'),
}
MATERIALS_DIR = os.path.join(os.path.dirname(doc.FileName), 'materials')
_mm = Materials.MaterialManager()


def fcmat_appearance(key):
    """BasicRendering values read straight from materials/<file>.FCMat, so no material library is needed."""
    values = {}
    with open(os.path.join(MATERIALS_DIR, MAT[key][0] + '.FCMat'), encoding='utf8') as f:
        for line in f:
            name, _, value = line.strip().partition(': ')
            if name in ('DiffuseColor', 'AmbientColor', 'SpecularColor', 'Shininess'):
                values[name] = value.strip('"')
    return values


def library_material(key):
    """The material from FreeCAD's library, or None when materials/ isn't set up as a library."""
    try:
        return _mm.getMaterial(MAT[key][1])
    except LookupError:
        return None


def _rgb(s):
    return tuple(float(x) for x in s.strip('()').split(','))[:3]


def set_appearance(obj, key, transparency=0):
    """Viewport look from a material's BasicRendering model (stored in the .FCStd, so it is portable)."""
    look = fcmat_appearance(key)
    m = App.Material()
    m.DiffuseColor = _rgb(look['DiffuseColor'])
    m.AmbientColor = _rgb(look['AmbientColor'])
    m.SpecularColor = _rgb(look['SpecularColor'])
    m.EmissiveColor = (0.0, 0.0, 0.0)
    m.Shininess = float(look['Shininess'])
    m.Transparency = transparency / 100.0
    obj.ViewObject.ShapeAppearance = (m,)
    obj.ViewObject.LineColor = tuple(c * 0.5 for c in m.DiffuseColor)


def set_material(obj, key, look=None, transparency=0):
    mat = library_material(key)
    if mat is not None:
        obj.ShapeMaterial = mat
    set_appearance(obj, look or key, transparency)


def set_label_color(obj, rgb):
    m = App.Material()
    m.DiffuseColor = rgb
    m.AmbientColor = tuple(c * 0.3 for c in rgb)
    m.EmissiveColor = tuple(c * 0.55 for c in rgb)  # readable regardless of lighting
    m.SpecularColor = (0.0, 0.0, 0.0)
    m.Shininess = 0.0
    obj.ViewObject.ShapeAppearance = (m,)
    obj.ViewObject.LineColor = rgb


# --------------------------------------------------------------------------- helpers
def tag(obj):
    obj.addProperty('App::PropertyBool', TAG, 'Generator', 'Created by tools/build_model.py', 4)  # 4 = hidden
    setattr(obj, TAG, True)
    return obj


def add(type_id, name, label):
    obj = tag(doc.addObject(type_id, name))
    obj.Label = label
    return obj


def offset(obj, x=None, y=None, z=None, rot=None, prop='Placement'):
    if rot is not None:
        p = getattr(obj, prop)
        p.Rotation = rot
        setattr(obj, prop, p)
    for axis, e in (('x', x), ('y', y), ('z', z)):
        if e is not None:
            obj.setExpression(f'{prop}.Base.{axis}', e)


def origin(body, role):
    return next(o for o in body.Origin.OriginFeatures if o.Role == role)


def append(body, kind, name):
    """Add a feature after the body's Tip and make it the new Tip (body.newObject misplaces transforms)."""
    f = tag(doc.addObject(f'PartDesign::{kind}', name))
    body.addObject(f)
    body.Tip = f
    return f


def new_body(part, name, label, compound=False):
    body = add('PartDesign::Body', name, label)
    part.addObject(body)
    body.AllowCompound = compound
    return body


def feature(body, kind, name, label, dims, x, y, z):
    """PartDesign primitive on the body's XY plane, sized and placed by expressions."""
    f = append(body, kind, name)
    f.Label = label
    f.AttachmentSupport = [(origin(body, 'XY_Plane'), '')]
    f.MapMode = 'FlatFace'
    for prop, e in dims.items():
        f.setExpression(prop, e)
    offset(f, x, y, z, prop='AttachmentOffset')
    return f


def rounded_rect_sketch(body, name, label, width, height, radius, cx, cy, z):
    """Fully constrained rounded rectangle centred on the sketch origin; size and position are expressions."""
    sk = tag(doc.addObject('Sketcher::SketchObject', name))
    body.addObject(sk)
    sk.Label = label
    sk.AttachmentSupport = [(origin(body, 'XY_Plane'), '')]
    sk.MapMode = 'FlatFace'
    w, h, r = 10.0, 14.0, 0.5  # seed geometry, overridden by the expressions
    V = App.Vector
    lines = [((-w / 2 + r, -h / 2), (w / 2 - r, -h / 2)), ((w / 2, -h / 2 + r), (w / 2, h / 2 - r)),
             ((w / 2 - r, h / 2), (-w / 2 + r, h / 2)), ((-w / 2, h / 2 - r), (-w / 2, -h / 2 + r))]
    for a, b in lines:
        sk.addGeometry(Part.LineSegment(V(*a, 0), V(*b, 0)))
    centres = [(w / 2 - r, -h / 2 + r), (w / 2 - r, h / 2 - r), (-w / 2 + r, h / 2 - r), (-w / 2 + r, -h / 2 + r)]
    for i, c in enumerate(centres):
        a0 = math.radians(-90 + 90 * i)
        sk.addGeometry(Part.ArcOfCircle(Part.Circle(V(*c, 0), V(0, 0, 1), r), a0, a0 + math.pi / 2))
    C = Sketcher.Constraint
    # line i ends where arc i starts, arc i ends where line i+1 starts; arcs are 4..7
    for i in range(4):
        sk.addConstraint(C('Tangent', i, 2, 4 + i, 1))
        sk.addConstraint(C('Tangent', 4 + i, 2, (i + 1) % 4, 1))
    sk.addConstraint(C('Horizontal', 0)); sk.addConstraint(C('Horizontal', 2))
    sk.addConstraint(C('Vertical', 1)); sk.addConstraint(C('Vertical', 3))
    for i in (5, 6, 7):
        sk.addConstraint(C('Equal', 4, i))
    sk.renameConstraint(sk.addConstraint(C('Radius', 4, r)), 'Radius')
    sk.renameConstraint(sk.addConstraint(C('DistanceX', 3, 1, 1, 1, w)), 'Width')
    sk.renameConstraint(sk.addConstraint(C('DistanceY', 0, 1, 2, 1, h)), 'Height')
    sk.addConstraint(C('Symmetric', 7, 3, 5, 3, -1, 1))  # centred on the sketch origin
    sk.setExpression('.Constraints.Radius', radius)
    sk.setExpression('.Constraints.Width', width)
    sk.setExpression('.Constraints.Height', height)
    offset(sk, cx, cy, z, prop='AttachmentOffset')
    return sk


def pattern(body, name, label, originals, axis, count, spacing, axis2=None, count2=None, spacing2=None):
    lp = append(body, 'LinearPattern', name)
    lp.Label = label
    lp.Originals = originals
    lp.Direction = (origin(body, axis), [''])
    lp.Mode = 'Spacing'
    lp.setExpression('Occurrences', count)
    lp.setExpression('Offset', spacing)
    if axis2:
        lp.Direction2 = (origin(body, axis2), [''])
        lp.Mode2 = 'Spacing'
        lp.setExpression('Occurrences2', count2)
        lp.setExpression('Offset2', spacing2)
    return lp


def mirror_yz(body, name, label, originals=None):
    m = append(body, 'Mirrored', name)
    m.Label = label
    m.MirrorPlane = (origin(body, 'YZ_Plane'), [''])
    if originals:
        m.Originals = originals
    else:
        m.TransformMode = 'Whole shape'
    return m


def text(name, label, string, font, size, justification):
    """Draft ShapeString with a proper object name (Draft.make_shape_string always names it 'ShapeString')."""
    s = add('Part::Part2DObjectPython', name, label)
    ShapeString(s)
    ViewProviderShapeString(s.ViewObject)
    s.String, s.FontFile, s.Tracking = string, font, 0
    s.Justification = justification
    s.JustificationReference = 'Cap Height'
    s.setExpression('Size', size)
    s.ViewObject.PointSize = 1
    return s


def clone(name, label, source):
    """Draft Clone with a proper object name."""
    c = add('Part::FeaturePython', name, label)
    c.addExtension('Part::AttachExtensionPython')
    Clone(c)
    c.Objects = [source]
    ViewProviderClone(c.ViewObject)
    return c


def emboss(group, name, label, shape_string, look):
    e = add('Part::Extrusion', name, label)
    e.Base = shape_string
    shape_string.ViewObject.Visibility = False  # the flat text would z-fight with the surface it sits on
    group.addObject(shape_string)
    e.DirMode = 'Custom'
    e.Dir = App.Vector(0, 0, 1)
    e.Solid = True
    e.setExpression('LengthFwd', f'{P}MarkingThickness')
    group.addObject(e)
    set_material(e, look)
    return e


def group(parent, name, label):
    g = add('App::DocumentObjectGroup', name, label)
    parent.addObject(g)
    return g


# --------------------------------------------------------------------------- cleanup
def remove(objs):
    names = {o.Name for o in objs if o is not None}
    while True:
        names = {n for n in names if doc.getObject(n) is not None}  # bodies take their features with them
        if not names:
            return
        objs = [doc.getObject(n) for n in names]
        leaves = [o for o in objs if not any(p.Name in names for p in o.InList)] or objs
        for name in [o.Name for o in leaves]:
            o = doc.getObject(name)
            if o is None:
                continue
            if o.TypeId == 'PartDesign::Body':
                o.removeObjectsFromDocument()
            doc.removeObject(name)


def cleanup():
    generated = [o for o in doc.Objects if TAG in o.PropertiesList]
    # FreeCAD bug #33685: removing an object that still has expressions leaves stale entries in the
    # fine-grained recompute list of the objects it referenced. The next recompute then hits deleted
    # objects and silently aborts (Windows) or crashes (macOS). Drop every expression first.
    for o in generated:
        if o.TypeId == 'Spreadsheet::Sheet':
            o.clearAll()
        for path, _ in list(o.ExpressionEngine):
            o.setExpression(path, None)
    remove(generated)
    # one-off: the hand-drawn starting point (draft sketch + its VarSet) is superseded by Params
    remove([doc.getObject(n) for n in ('Body', 'Sketch', 'VarSet')])


# --------------------------------------------------------------------------- Params
def setup_params():
    vs = doc.getObject('Params')
    first = vs is None
    if first:
        vs = doc.addObject('App::VarSet', 'Params')  # not tagged: survives rebuilds
        vs.Label = 'Parameters'
    for name, kind, grp, value, tip in PARAMS:
        if name not in vs.PropertiesList:
            vs.addProperty(f'App::Property{kind}', name, grp, tip)
            if name not in DERIVED:
                setattr(vs, name, value)
        else:  # keep the value, refresh the metadata
            vs.setGroupOfProperty(name, grp)
            vs.setDocumentationOfProperty(name, tip)
        if name in DERIVED:
            vs.setExpression(name, DERIVED[name])
            vs.setEditorMode(name, 1)  # read-only
    for name in OBSOLETE_PARAMS:
        if name in vs.PropertiesList:
            vs.removeProperty(name)
    return vs


# --------------------------------------------------------------------------- Pinout
def setup_pinout():
    sh = add('Spreadsheet::Sheet', 'Pinout', 'Pinout')
    for col, head in zip('ABCDEFGH', ('Pin', 'Name', 'Function', 'Location', 'X', 'Y', 'Z', 'Label')):
        sh.set(f'{col}1', head)
    sh.setStyle('A1:H1', 'bold')
    for k in range(1, 56):
        r = k + 1
        name, loc = PINS[k], pin_location(k)
        if loc == 'left':
            x = f'=-{P}BoardWidth / 2 + {P}OuterPadWidth / 2'
            y = f'={P}SidePadFirstY + ({P}OuterPadCountSide - {k}) * {P}OuterPadPitch'
        elif loc == 'bottom':
            x = f'={P}BottomPadFirstX + {k - 14} * {P}OuterPadPitch'
            y = f'=-{P}BoardHeight / 2 + {P}OuterPadWidth / 2'
        elif loc == 'right':
            x = f'={P}BoardWidth / 2 - {P}OuterPadWidth / 2'
            y = f'={P}SidePadFirstY + {k - 25} * {P}OuterPadPitch'
        elif loc == 'inner-left':
            x = f'=-{P}InnerPadColumnX'
            y = f'={P}InnerPadFirstY + {46 - k} * {P}InnerPadPitch'
        else:
            x = f'={P}InnerPadColumnX'
            y = f'={P}InnerPadFirstY + {55 - k} * {P}InnerPadPitch'
        sh.set(f'A{r}', str(k))
        sh.set(f'B{r}', "'" + name)
        sh.set(f'C{r}', "'" + FUNC.get(name, 'GPIO'))
        sh.set(f'D{r}', "'" + loc)
        sh.set(f'E{r}', x)
        sh.set(f'F{r}', y)
        sh.set(f'G{r}', f'=-{P}CopperThickness')
        sh.set(f'H{r}', f"'{k} {name}")
        sh.setAlias(f'E{r}', f'pin{k}_x')
        sh.setAlias(f'F{r}', f'pin{k}_y')
        sh.setAlias(f'H{r}', f'pin{k}_label')
    notes = [
        'Origin: board centre, PCB bottom face at z = 0, +Y towards the antenna, pin 1 top-left in top view.',
        'X / Y: centre of the bottom-face copper pad (pogo pin target). Z: pad contact surface.',
        'Use the aliases in jig sketches, e.g. Pinout.pin31_x / Pinout.pin31_y for SWDCLK.',
        'Generated by tools/build_model.py: edit the script, not this sheet.',
    ]
    for i, n in enumerate(notes):
        sh.set(f'A{58 + i}', "'" + n)
    sh.setColumnWidth('C', 150)
    sh.setColumnWidth('D', 90)
    return sh


# --------------------------------------------------------------------------- geometry
def build():
    W, L, T, CU = f'{P}BoardWidth', f'{P}BoardHeight', f'{P}BoardThickness', f'{P}CopperThickness'
    R, PITCH = f'{P}OuterPadRadius', f'{P}OuterPadPitch'
    H, D, DT = f'{P}OuterPadHeight', f'{P}OuterPadWidth', f'{P}OuterPadTopWidth'

    part = add('App::Part', 'Module', 'Holyiot-18010 nRF52840')
    part.Type = 'BLE module'
    part.Id = 'HOLYIOT-18010-NRF52840'
    part.Meta = {'Datasheet': 'http://www.holyiot.com/tp/2019042516322180424.pdf', 'Chip': 'nRF52840-QIAA',
                 'Origin': 'board centre, PCB bottom face at z = 0, +Y towards the antenna'}
    part.License, part.LicenseURL = LICENSE

    # ---- PCB
    pcb = new_body(part, 'PCB', 'PCB')
    feature(pcb, 'AdditiveBox', 'Board', 'Board', {'Length': W, 'Width': L, 'Height': T}, f'-{W} / 2', f'-{L} / 2', '0 mm')
    # drilled before plating: the Castellations barrel fills R..R+plating, so no two faces coincide
    hole = dict(Radius=f'{R} + {P}PlatingThickness', Height=f'{T} + 1 mm')
    sh = feature(pcb, 'SubtractiveCylinder', 'SideHole', 'Side half-hole', hole, f'-{W} / 2', f'{P}SidePadFirstY', '-0.5 mm')
    pattern(pcb, 'SideHoles', 'Side half-holes', [sh], 'X_Axis', '2', W, 'Y_Axis', f'{P}OuterPadCountSide', PITCH)
    bh = feature(pcb, 'SubtractiveCylinder', 'BottomHole', 'Bottom half-hole', hole, f'{P}BottomPadFirstX', f'-{L} / 2', '-0.5 mm')
    pattern(pcb, 'BottomHoles', 'Bottom half-holes', [bh], 'X_Axis', f'{P}OuterPadCountBottom', PITCH)
    set_material(pcb, 'fr4', look='mask')  # FR-4 laminate, seen through black solder mask

    # ---- castellated pads 1-37: bottom pad + top pad + plated barrel, drilled and trimmed at the board edge
    cast = new_body(part, 'Castellations', 'Castellated pads 1-37', compound=True)
    y0 = f'{P}SidePadFirstY - {H} / 2'
    unit = [
        feature(cast, 'AdditiveBox', 'SidePadBottom', 'Side pad, bottom face', {'Length': D, 'Width': H, 'Height': CU}, f'-{W} / 2', y0, f'-{CU}'),
        feature(cast, 'AdditiveBox', 'SidePadTop', 'Side pad, top face', {'Length': DT, 'Width': H, 'Height': CU}, f'-{W} / 2', y0, T),
        feature(cast, 'AdditiveCylinder', 'SideBarrel', 'Side pad, plated barrel', {'Radius': f'{R} + {P}PlatingThickness', 'Height': T},
                f'-{W} / 2', f'{P}SidePadFirstY', '0 mm'),
        feature(cast, 'SubtractiveCylinder', 'SideBore', 'Side pad, half-hole', {'Radius': R, 'Height': f'{T} + 1 mm'},
                f'-{W} / 2', f'{P}SidePadFirstY', '-0.5 mm'),
        feature(cast, 'SubtractiveBox', 'SideTrim', 'Side pad, trim at board edge', {'Length': '1 mm', 'Width': f'{H} + 1 mm', 'Height': f'{T} + 1 mm'},
                f'-{W} / 2 - 1 mm', f'{y0} - 0.5 mm', '-0.5 mm'),
    ]
    pattern(cast, 'LeftPads', 'Pins 1-13 (left)', unit, 'Y_Axis', f'{P}OuterPadCountSide', PITCH)
    mirror_yz(cast, 'RightPads', 'Pins 25-37 (right, mirrored)')
    x0 = f'{P}BottomPadFirstX - {H} / 2'
    unit = [
        feature(cast, 'AdditiveBox', 'BottomPadBottom', 'Bottom pad, bottom face', {'Length': H, 'Width': D, 'Height': CU}, x0, f'-{L} / 2', f'-{CU}'),
        feature(cast, 'AdditiveBox', 'BottomPadTop', 'Bottom pad, top face', {'Length': H, 'Width': DT, 'Height': CU}, x0, f'-{L} / 2', T),
        feature(cast, 'AdditiveCylinder', 'BottomBarrel', 'Bottom pad, plated barrel', {'Radius': f'{R} + {P}PlatingThickness', 'Height': T},
                f'{P}BottomPadFirstX', f'-{L} / 2', '0 mm'),
        feature(cast, 'SubtractiveCylinder', 'BottomBore', 'Bottom pad, half-hole', {'Radius': R, 'Height': f'{T} + 1 mm'},
                f'{P}BottomPadFirstX', f'-{L} / 2', '-0.5 mm'),
        feature(cast, 'SubtractiveBox', 'BottomTrim', 'Bottom pad, trim at board edge', {'Length': f'{H} + 1 mm', 'Width': '1 mm', 'Height': f'{T} + 1 mm'},
                f'{x0} - 0.5 mm', f'-{L} / 2 - 1 mm', '-0.5 mm'),
    ]
    pattern(cast, 'BottomPads', 'Pins 14-24 (bottom edge)', unit, 'X_Axis', f'{P}OuterPadCountBottom', PITCH)
    set_material(cast, 'enig')

    # ---- inner pads 38-55
    inner = new_body(part, 'InnerPads', 'Inner pads 38-55', compound=True)
    ip = feature(inner, 'AdditiveBox', 'InnerPad', 'Inner pad', {'Length': f'{P}InnerPadWidth', 'Height': CU, 'Width': f'{P}InnerPadHeight'},
                 f'-{P}InnerPadColumnX - {P}InnerPadWidth / 2', f'{P}InnerPadFirstY - {P}InnerPadHeight / 2', f'-{CU}')
    pattern(inner, 'InnerPadGrid', 'Inner pad grid', [ip], 'X_Axis', '2', f'2 * {P}InnerPadColumnX',
            'Y_Axis', f'{P}InnerPadCount', f'{P}InnerPadPitch')
    set_material(inner, 'enig')

    # ---- shield can: fully constrained rounded-rectangle sketch, padded
    # (no fillets: their Edge/Face references break on reload + resize in FreeCAD 26.3)
    shield = new_body(part, 'Shield', 'Shield can')
    outline = rounded_rect_sketch(shield, 'ShieldOutline', 'Can outline', f'{P}ShieldWidth', f'{P}ShieldHeight',
                                  f'{P}ShieldCornerRadius', '0 mm', f'{P}ShieldBottomY + {P}ShieldHeight / 2', T)
    can = append(shield, 'Pad', 'ShieldPad')
    can.Label = 'Can'
    can.Profile = outline
    can.setExpression('Length', f'{P}ShieldThickness')
    outline.ViewObject.Visibility = False
    set_material(shield, 'shield')

    # ---- chip antenna
    AW, AH, AT, TW = f'{P}AntennaWidth', f'{P}AntennaHeight', f'{P}AntennaThickness', f'{P}AntennaTerminalWidth'
    ay = f'{L} / 2 - {P}AntennaOffsetTop - {AH}'
    ant = new_body(part, 'Antenna', 'Chip antenna')
    feature(ant, 'AdditiveBox', 'AntennaCeramic', 'Ceramic body', {'Length': f'{AW} - 2 * {TW}', 'Width': AH, 'Height': AT},
            f'-{AW} / 2 + {TW}', ay, T)
    set_material(ant, 'ceramic')
    term = new_body(part, 'AntennaTerminations', 'Chip antenna terminations', compound=True)
    cap = feature(term, 'AdditiveBox', 'AntennaCap', 'End cap', {'Length': TW, 'Width': AH, 'Height': AT}, f'-{AW} / 2', ay, T)
    mirror_yz(term, 'AntennaCapMirror', 'End cap, mirrored', [cap])
    set_material(term, 'silver')

    # ---- markings: silkscreen on the PCB, laser marking on the shield
    marks = group(part, 'Markings', 'Markings')
    s = text('SilkTitleText', 'Silkscreen title (text)', 'HOLYIOT-18010-NRF52840', FONT_SILK, f'{P}SilkTitleSize', 'Bottom-Center')
    offset(s, '0 mm', f'{L} / 2 - {P}SilkTitleOffsetTop', T)
    emboss(marks, 'SilkTitle', 'Silkscreen: HOLYIOT-18010-NRF52840', s, 'silk')
    s = text('SilkVersionText', 'Silkscreen version (text)', 'VER1.0', FONT_SILK, f'0.55 * {P}SilkTitleSize', 'Top-Right')
    offset(s, f'{W} / 2 - 0.25 mm', f'{L} / 2 - {P}AntennaOffsetTop', T)
    emboss(marks, 'SilkVersion', 'Silkscreen: VER1.0', s, 'silk')
    SW, SH = f'{P}ShieldWidth', f'{P}ShieldHeight'
    ytop = f'{P}ShieldBottomY + 0.94 * {SH}'
    down = App.Rotation(App.Vector(0, 0, 1), -90)  # text runs top to bottom, letters face +X, as on the real can
    for name, string, font, size, frac in (
        ('MarkModel', 'Model : HOLYIOT-18010-nRF52840', FONT_MARK, 0.5, 0.06),
        ('MarkFcc', 'FCC ID : 2ALGY-NRF52840', FONT_MARK, 0.5, 0.14),
        ('MarkMaker', 'Manufacturer : Holyiot', FONT_MARK, 0.5, 0.22),
        ('MarkOrigin', 'Made in China', FONT_MARK, 0.5, 0.30),
        ('MarkCert', 'CE   FC   RoHS', FONT_MARK, 0.8, 0.40),
        ('MarkLogo', 'holyiot', FONT_LOGO, 2.2, 0.60),
    ):
        s = text(name + 'Text', f'{string} (text)', string, font, f'{size} mm', 'Bottom-Left')
        offset(s, f'-{SW} / 2 + {frac} * {SW}', ytop, f'{P}ModuleHeight', rot=down)
        emboss(marks, name, f'Laser mark: {string}', s, 'laser')

    # ---- pin labels, positioned from the Pinout sheet
    top_g = group(part, 'LabelsTop', 'Pin labels (top view)')
    over_g = group(part, 'InnerOverlay', 'Inner pad overlay (top view)')
    bot_g = group(part, 'LabelsBottom', 'Pin labels (bottom view)')
    flip = App.Rotation(App.Vector(1, 0, 0), 180)  # readable in FreeCAD's Bottom view (X stays right, Y flips)
    down_flip = App.Rotation(App.Vector(0, 0, 1), -90).multiply(flip)
    gap = f'{P}LabelGap'
    z_edge, z_inner, z_bottom = T, f'{P}ModuleHeight + 2 * {CU}', f'-{CU} - 0.01 mm'
    for k in range(1, 56):
        px, py, loc = f'Pinout.pin{k}_x', f'Pinout.pin{k}_y', pin_location(k)
        if loc == 'left':
            xe = f'{px} - {D} / 2 - {gap}'
            spec = {'T': (xe, py, z_edge, None, 'Middle-Right'), 'B': (xe, py, z_bottom, flip, 'Middle-Right')}
        elif loc == 'right':
            xe = f'{px} + {D} / 2 + {gap}'
            spec = {'T': (xe, py, z_edge, None, 'Middle-Left'), 'B': (xe, py, z_bottom, flip, 'Middle-Left')}
        elif loc == 'bottom':
            ye = f'{py} - {D} / 2 - {gap}'
            spec = {'T': (px, ye, z_edge, down, 'Middle-Left'), 'B': (px, ye, z_bottom, down_flip, 'Middle-Left')}
        elif loc == 'inner-left':
            xe = f'{px} + {P}InnerPadWidth / 2 + {gap}'
            spec = {'T': (xe, py, z_inner, None, 'Middle-Left'), 'B': (xe, py, z_bottom, flip, 'Middle-Left')}
        else:
            xe = f'{px} - {P}InnerPadWidth / 2 - {gap}'
            spec = {'T': (xe, py, z_inner, None, 'Middle-Right'), 'B': (xe, py, z_bottom, flip, 'Middle-Right')}
        for side, grp in (('T', over_g if loc.startswith('inner') else top_g), ('B', bot_g)):
            x, y, z, rot, just = spec[side]
            # labels must be unique, else FreeCAD rewrites trailing digits ('P1.11' -> 'P1.001')
            label = f'{k:02d} {PINS[k]}' + (' (bottom)' if side == 'B' else '')
            s = text(f'Pin{k:02d}{side}', label, f'{k} {PINS[k]}', FONT_LABEL, f'{P}LabelSize', just)
            s.setExpression('String', f'Pinout.pin{k}_label')
            offset(s, x, y, z, rot=rot)
            grp.addObject(s)
            set_label_color(s, LABEL_COLORS[pin_kind(PINS[k])])
    ghost = clone('InnerPadsGhost', 'Inner pads (ghost above shield)', inner)
    offset(ghost, z=f'{P}ModuleHeight + 2 * {CU}')
    over_g.addObject(ghost)
    set_appearance(ghost, 'enig', transparency=55)
    over_g.ViewObject.Visibility = False  # optional datasheet-style see-through view; toggle with Space
    bot_g.ViewObject.Visibility = False
    return part


# --------------------------------------------------------------------------- main
cleanup()
doc.recompute()
setup_params()
setup_pinout()
doc.recompute()
build()
doc.Comment = ('Parametric model of the Holyiot-18010 nRF52840 BLE module for jig design. '
               'Dimensions: Params. Pad coordinates: Pinout. Generated by tools/build_model.py.')
doc.License, doc.LicenseURL = LICENSE
doc.recompute()
doc.recompute()  # a 'Whole shape' Mirrored is invalid on its first recompute and fine on the second
errors = [f'{o.Name}: {o.State}' for o in doc.Objects if 'Invalid' in o.State or 'Error' in o.State]
print('objects:', len(doc.Objects), '| errors:', errors or 'none')
doc.save()
view = Gui.getDocument(doc.Name).ActiveView
view.viewIsometric()
view.fitAll()
