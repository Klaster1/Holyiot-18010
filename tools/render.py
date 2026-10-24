"""Path-traced product renders of the Holyiot-18010 model with Blender Cycles.

Export the meshes first (tools/export_meshes.py), then:

    blender -b --factory-startup --python tools/render.py -- [--shots hero,pinout_top] [--samples 512] [--scale 100]

Writes renders/<shot>.png. --scale is a percentage of the 2400 x 1800 base resolution.
The scene is in metres: the model is imported at 1/1000 so lights and depth of field are physical.
"""

import argparse
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MESHES = os.path.join(ROOT, 'build', 'meshes')
OUT = os.path.join(ROOT, 'renders')
MM = 0.001

# --------------------------------------------------------------------------- arguments
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument('--shots', default='all')
ap.add_argument('--samples', type=int, default=384)
ap.add_argument('--scale', type=int, default=100)
args = ap.parse_args(argv)


# --------------------------------------------------------------------------- materials
def principled(name, color, metallic=0.0, roughness=0.5, **inputs):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    for k, v in inputs.items():
        bsdf.inputs[k].default_value = v
    return m


def roughness_noise(mat, base, amount, scale):
    """Break up perfectly uniform reflections with a faint noise on roughness."""
    nt = mat.node_tree
    bsdf = nt.nodes['Principled BSDF']
    tex = nt.nodes.new('ShaderNodeTexNoise')
    tex.inputs['Scale'].default_value = scale
    tex.inputs['Detail'].default_value = 8
    ramp = nt.nodes.new('ShaderNodeMapRange')
    ramp.inputs['To Min'].default_value = base - amount
    ramp.inputs['To Max'].default_value = base + amount
    nt.links.new(tex.outputs['Fac'], ramp.inputs['Value'])
    nt.links.new(ramp.outputs['Result'], bsdf.inputs['Roughness'])


def emission(name, color, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (*color, 1)
    em.inputs['Strength'].default_value = strength
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
    return m


def make_materials():
    mats = {
        'soldermask': principled('Solder mask', (0.012, 0.012, 0.014), roughness=0.45,
                                 **{'Coat Weight': 0.7, 'Coat Roughness': 0.12}),
        'fr4': principled('FR-4 edge', (0.22, 0.21, 0.13), roughness=0.8),
        'enig': principled('ENIG gold', (1.0, 0.77, 0.36), metallic=1.0, roughness=0.22),
        'nickel_silver': principled('Nickel silver', (0.80, 0.80, 0.78), metallic=1.0, roughness=0.28),
        'ceramic': principled('Alumina ceramic', (0.86, 0.85, 0.80), roughness=0.55,
                              **{'Subsurface Weight': 0.15}),
        'silver': principled('Silver termination', (0.90, 0.90, 0.90), metallic=1.0, roughness=0.35),
        'silkscreen': principled('Silkscreen', (0.88, 0.88, 0.86), roughness=0.65),
        'laser_mark': principled('Laser marking', (0.06, 0.06, 0.065), metallic=0.5, roughness=0.55),
    }
    roughness_noise(mats['nickel_silver'], 0.28, 0.06, 900)
    roughness_noise(mats['enig'], 0.22, 0.05, 1500)
    return mats


# --------------------------------------------------------------------------- scene
def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def import_model(mats):
    with open(os.path.join(MESHES, 'manifest.json')) as f:
        manifest = json.load(f)
    module = bpy.data.objects.new('Holyiot-18010', None)
    bpy.context.scene.collection.objects.link(module)
    labels = {'top': [], 'bottom': []}
    for m in manifest['meshes']:
        bpy.ops.wm.obj_import(filepath=os.path.join(MESHES, m['file']), global_scale=MM,
                              forward_axis='Y', up_axis='Z')
        obj = bpy.context.selected_objects[0]
        obj.name = m['name']
        obj.parent = module
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))
        obj.data.materials.clear()
        if m['material'] == 'label':
            obj.data.materials.append(emission(f"Label {m['name']}", m['color'], 1.2))
            labels[m['view']].append(obj)
        else:
            obj.data.materials.append(mats[m['material']])
        if m['name'] == 'pcb':
            # the mask covers both faces; the milled outline shows bare FR-4
            obj.data.materials.append(mats['fr4'])
            for poly in obj.data.polygons:
                poly.material_index = 1 if abs(poly.normal.z) < 0.5 else 0
    return module, labels


def cyclorama(color, roughness=0.6):
    """Seamless studio backdrop: floor curving up into a back wall."""
    me = bpy.data.meshes.new('Backdrop')
    bm = bmesh.new()
    w, depth, radius, height, steps = 0.6, 0.35, 0.12, 0.4, 24
    profile = [(-depth, 0.0)]
    for i in range(steps + 1):
        a = math.pi / 2 * i / steps
        profile.append((radius - radius * math.cos(a) + 0.05, radius - radius * math.cos(math.pi / 2 - a)))
    profile = [(-depth, 0.0), (0.05, 0.0)] + [(0.05 + radius * math.sin(math.pi / 2 * i / steps),
                                               radius - radius * math.cos(math.pi / 2 * i / steps)) for i in range(1, steps + 1)]
    profile.append((0.05 + radius, height))
    rows = [[bm.verts.new((x, y, z)) for (y, z) in profile] for x in (-w / 2, w / 2)]
    for i in range(len(profile) - 1):
        bm.faces.new((rows[0][i], rows[1][i], rows[1][i + 1], rows[0][i + 1]))
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new('Backdrop', me)
    bpy.context.scene.collection.objects.link(obj)
    for p in me.polygons:
        p.use_smooth = True
    obj.data.materials.append(principled('Backdrop', color, roughness=roughness))
    return obj


def area_light(name, location, target, size, power, color=(1, 1, 1)):
    data = bpy.data.lights.new(name, 'AREA')
    data.shape = 'DISK'
    data.size = size
    data.energy = power
    data.color = color
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    return obj


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def world(strength):
    w = bpy.data.worlds.new('Studio')
    bpy.context.scene.world = w
    w.use_nodes = True
    nt = w.node_tree
    env = nt.nodes.new('ShaderNodeTexEnvironment')
    path = os.path.join(bpy.utils.system_resource('DATAFILES', path='studiolights/world'), 'studio.exr')
    env.image = bpy.data.images.load(path)
    bg = nt.nodes['Background']
    bg.inputs['Strength'].default_value = strength
    nt.links.new(env.outputs['Color'], bg.inputs['Color'])


def camera(location, target, lens=100, fstop=None, ortho_scale=None):
    # Blender's aperture is lens / (2 * fstop); at 3-8 cm from the part only very high f-numbers keep it sharp
    data = bpy.data.cameras.new('Camera')
    data.clip_start = 0.002
    data.clip_end = 5
    if ortho_scale:
        data.type = 'ORTHO'
        data.ortho_scale = ortho_scale
    else:
        data.lens = lens
        data.sensor_width = 36
    if fstop:
        data.dof.use_dof = True
        data.dof.aperture_fstop = fstop
        data.dof.focus_distance = (Vector(target) - Vector(location)).length
    obj = bpy.data.objects.new('Camera', data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    look_at(obj, target)
    bpy.context.scene.camera = obj
    return obj


def orbit(target, distance, azimuth, elevation):
    """Camera position around target; azimuth 0 = from -Y (the bottom pad edge), counter-clockwise."""
    a, e = math.radians(azimuth), math.radians(elevation)
    t = Vector(target)
    return t + distance * Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


def setup_render(samples, scale):
    s = bpy.context.scene
    s.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    for backend in ('HIP', 'OPTIX', 'CUDA', 'ONEAPI', 'METAL'):
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        prefs.refresh_devices()
        gpus = [d for d in prefs.devices if d.type == backend]
        if gpus:
            for d in prefs.devices:
                d.use = d.type == backend
            s.cycles.device = 'GPU'
            print('Cycles device:', backend, [d.name for d in gpus])
            break
    else:
        print('Cycles device: CPU')
    s.cycles.samples = samples
    s.cycles.use_denoising = True
    s.cycles.denoiser = 'OPENIMAGEDENOISE'
    s.cycles.max_bounces = 16
    s.cycles.glossy_bounces = 8
    s.cycles.transparent_max_bounces = 8
    s.render.resolution_x, s.render.resolution_y = 2400, 1800
    s.render.resolution_percentage = scale
    s.render.film_transparent = False
    s.render.image_settings.file_format = 'PNG'
    s.render.image_settings.color_depth = '8'
    s.view_settings.view_transform = 'AgX'
    for look in ('AgX - Medium High Contrast', 'Medium High Contrast'):
        try:
            s.view_settings.look = look
            break
        except TypeError:
            pass


# --------------------------------------------------------------------------- shots
CENTER = Vector((0, 0, 1.4 * MM))  # roughly the middle of the module
LIGHT_BG = (0.55, 0.56, 0.58)
PINOUT_BG = (0.02, 0.021, 0.024)


def place(module, flipped):
    """Rest the module on the floor, shield up (top) or pads up (flipped)."""
    module.rotation_euler = (math.pi, 0, 0) if flipped else (0, 0, 0)
    module.location = (0, 0, 2.7 * MM) if flipped else (0, 0, 0.035 * MM)


def studio_lights():
    # watts for a part 18 mm across with lights 10-15 cm away (irradiance of a few W/m2)
    k = 1.0
    area_light('Key', (-0.09, -0.07, 0.12), (0, 0, 0), 0.12, 0.25 * k, (1.0, 0.97, 0.93))
    area_light('Fill', (0.11, -0.05, 0.06), (0, 0, 0), 0.15, 0.08 * k, (0.92, 0.96, 1.0))
    area_light('Rim', (0.02, 0.13, 0.07), (0, 0, 0), 0.08, 0.18 * k)


def shot_hero(module, labels):
    place(module, flipped=False)
    cyclorama(LIGHT_BG)
    studio_lights()
    world(0.35)
    camera(orbit(CENTER, 0.075, -30, 40), CENTER, lens=100, fstop=64)


def shot_hero_bottom(module, labels):
    place(module, flipped=True)
    cyclorama(LIGHT_BG)
    studio_lights()
    world(0.35)
    camera(orbit(CENTER, 0.075, 30, 34), CENTER, lens=100, fstop=64)


def shot_macro(module, labels):
    place(module, flipped=False)
    cyclorama(LIGHT_BG)
    studio_lights()
    world(0.35)
    target = Vector((-6.4 * MM, -7.6 * MM, 0.6 * MM))  # bottom-left corner: pins 11-16
    camera(orbit(target, 0.036, -48, 16), target, lens=100, fstop=128)


def shot_pinout(module, labels, view):
    place(module, flipped=(view == 'bottom'))
    for v, objs in labels.items():
        for o in objs:
            o.hide_render = v != view
    cyclorama(PINOUT_BG, roughness=0.9)
    studio_lights()
    # seen straight down, the pads mirror whatever is overhead: give them a softbox, hidden from the camera
    top = area_light('Overhead', (0, 0, 0.12), (0, 0, 0), 0.3, 0.15)
    top.visible_camera = False
    world(0.25)
    # labels span y = -14.3 .. +9 mm (bottom-edge labels hang below); flipping mirrors y
    cy = (-2.65 if view == 'top' else 2.65) * MM
    camera((0, cy, 0.25), (0, cy, 0), ortho_scale=37 * MM)
    bpy.context.scene.view_settings.view_transform = 'Standard'  # keep the label colours saturated


SHOTS = {
    'hero': shot_hero,
    'hero_bottom': shot_hero_bottom,
    'macro_castellations': shot_macro,
    'pinout_top': lambda m, l: shot_pinout(m, l, 'top'),
    'pinout_bottom': lambda m, l: shot_pinout(m, l, 'bottom'),
}


def main():
    names = list(SHOTS) if args.shots == 'all' else args.shots.split(',')
    os.makedirs(OUT, exist_ok=True)
    for name in names:
        clear_scene()
        setup_render(args.samples, args.scale)
        mats = make_materials()
        module, labels = import_model(mats)
        if not name.startswith('pinout'):
            for objs in labels.values():
                for o in objs:
                    o.hide_render = True
        SHOTS[name](module, labels)
        bpy.context.scene.render.filepath = os.path.join(OUT, name + '.png')
        bpy.ops.render.render(write_still=True)
        print('rendered', name)


main()
