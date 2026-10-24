"""Compose the 1280 x 640 GitHub social preview from the renders: renders/social_preview.png.

Run with any Python that has Pillow: `python tools/social_preview.py`.
"""

import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(ROOT, 'renders')
F = os.path.join(ROOT, 'fonts')
W, H = 1280, 640

pinout = Image.open(os.path.join(R, 'pinout_top.png')).convert('RGB')
bg = pinout.getpixel((10, 10))
canvas = Image.new('RGB', (W, H), bg)

# right: the top-view pinout card, cropped to the module and its labels
pw, ph = pinout.size
card = pinout.crop((int(pw * 0.20), 0, int(pw * 0.80), ph)).resize((int(H * 0.60 * pw / ph), H), Image.LANCZOS)
canvas.paste(card, (W - card.width - 24, 0))

# left: title block
draw = ImageDraw.Draw(canvas)
bold = ImageFont.truetype(os.path.join(F, 'RobotoCondensed-Bold.ttf'), 84)
regular = ImageFont.truetype(os.path.join(F, 'RobotoCondensed-Regular.ttf'), 40)
small = ImageFont.truetype(os.path.join(F, 'RobotoCondensed-Regular.ttf'), 30)
x, y = 72, 150
draw.text((x, y), 'Holyiot-18010', font=bold, fill=(240, 240, 240))
y += 104
draw.text((x, y), 'nRF52840 BLE module', font=regular, fill=(205, 170, 95))
y += 70
for line in ('Parametric FreeCAD model', 'All 55 pads labelled', 'STEP export'):
    draw.text((x, y), line, font=small, fill=(185, 185, 190))
    y += 44

out = os.path.join(R, 'social_preview.png')
canvas.save(out, optimize=True)
print('wrote', out, canvas.size, round(os.path.getsize(out) / 1e6, 2), 'MB')
