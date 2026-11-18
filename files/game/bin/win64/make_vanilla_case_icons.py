"""Regenerate the Vanilla Case artwork (needs Pillow; the PNGs are committed, so preparation does not).

cs2_gc_vanilla_case.png       inventory/case icon: the Black Market Case body recoloured vanilla cream with a
                              crossed-knives-and-star emblem
cs2_gc_vanilla_rare_item.png  unboxing "rare special item" tile: a vanilla coin with a knife silhouette
"""
import colorsys
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
BASE = HERE / 'cs2_gc_black_market_case.png'
CASE = HERE / 'cs2_gc_vanilla_case.png'
RARE = HERE / 'cs2_gc_vanilla_rare_item.png'
SS = 4  # supersampling for the drawn shapes
CREAM = (243, 229, 190)
DARK = (34, 28, 22)


def knife(cx, cy, length, angle):
    """A clip-point combat knife pointing along `angle` (degrees), as a polygon (blade+guard+handle)."""
    k = length / 160.0
    shape = [(-62, -5), (-58, -10), (-12, -9), (-12, -19), (-4, -19), (-4, -12), (50, -12), (60, -14), (78, -9),
             (100, 3), (84, 14), (58, 20), (28, 20), (-4, 13), (-4, 21), (-12, 21), (-12, 11), (-22, 12), (-28, 8),
             (-35, 12), (-42, 8), (-49, 12), (-58, 11), (-62, 6)]
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return [(cx + (x * c - y * s) * k, cy + (x * s + y * c) * k) for x, y in shape]


def star(cx, cy, outer, inner, points=5):
    return [(cx + (outer if i % 2 == 0 else inner) * math.sin(math.pi * i / points),
             cy - (outer if i % 2 == 0 else inner) * math.cos(math.pi * i / points)) for i in range(2 * points)]


def vanilla(rgb, reference):
    """Map a saturated orange pixel to vanilla cream, keeping its shading."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    shade = min(1.15, v / reference)
    return tuple(min(255, round(c * shade)) for c in CREAM)


def case_icon():
    image = Image.open(BASE).convert('RGBA')
    w, h = image.size
    px = image.load()
    # Erase the old front emblem (crown and crossed knives) by blending the front face across it.
    left, top, right, bottom = 55, 84, 115, 152
    for y in range(top, bottom + 1):
        a, b = px[left - 1, y], px[right + 1, y]
        for x in range(left, right + 1):
            t = (x - left + 1) / (right - left + 2)
            px[x, y] = tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(4))
    # Cover the dark crown inside the orange stripe. The crown touches the stripe's right edge, so the
    # fill is bounded by that diagonal edge (measured from the base icon) instead of by orange pixels.
    def orange(p, bright=0.2):
        hue, sat, val = colorsys.rgb_to_hsv(*(c / 255 for c in p[:3]))
        return p[3] > 0 and sat > 0.45 and val > bright and 0.03 < hue < 0.17
    patched = Image.new('L', (w, h), 0)
    for y in range(116, 152):
        line = 233 - 0.4 * (y - 100)
        row = [x for x in range(186, int(line) + 5) if orange(px[x, y], 0.85)]
        if not row:
            continue
        right = max(row[-1], int(line))
        lit = [px[x, y] for x in row]
        fill = tuple(sorted(p[i] for p in lit)[len(lit) // 2] for i in range(3))
        for x in range(199, right):
            if not orange(px[x, y], 0.85):
                px[x, y] = fill + (px[x, y][3],)
            if x < right - 2:
                patched.putpixel((x, y), 255)
    image.paste(image.filter(ImageFilter.GaussianBlur(1.1)), (0, 0), patched)
    px = image.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            hue, sat, val = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if a > 0 and sat > 0.45 and val > 0.2 and 0.03 < hue < 0.17:
                px[x, y] = vanilla((r, g, b), 0.9) + (a,)
    # New artwork, drawn at SS x and scaled down for smooth edges.
    layer = Image.new('RGBA', (w * SS, h * SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    s = SS
    for angle in (-38, 218):
        draw.polygon([(x * s, y * s) for x, y in knife(85, 122, 66, angle)], fill=CREAM + (255,),
                     outline=(120, 104, 70, 255))
    draw.polygon([(x * s, y * s) for x, y in star(85, 99, 9.5, 4)], fill=CREAM + (255,))
    layer = layer.resize((w, h), Image.LANCZOS)
    shadow = layer.split()[3].filter(ImageFilter.GaussianBlur(1.2))
    shaded = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    shaded.putalpha(shadow.point(lambda value: value * 0.6))
    image = Image.alpha_composite(image, shaded)
    image = Image.alpha_composite(image, layer)
    image.save(CASE, optimize=True)


def rare_item():
    w, h = 256, 198
    s = SS
    big = Image.new('RGBA', (w * s, h * s), (0, 0, 0, 0))
    cx, cy, radius = w / 2 * s, h / 2 * s, 88 * s
    # Soft golden glow behind the coin.
    glow = Image.new('L', big.size, 0)
    ImageDraw.Draw(glow).ellipse((cx - radius - 6 * s, cy - radius - 6 * s, cx + radius + 6 * s, cy + radius + 6 * s), fill=150)
    glow = glow.filter(ImageFilter.GaussianBlur(7 * s))
    big.paste(Image.new('RGBA', big.size, (255, 226, 150, 255)), (0, 0), glow)
    # Coin face: a radial vanilla gradient.
    face = Image.new('RGBA', big.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(face)
    steps = 90
    for i in range(steps):
        t = i / (steps - 1)
        r = radius * (1 - t)
        colour = tuple(round(a + (b - a) * t) for a, b in zip((176, 140, 78), (255, 246, 222)))
        offset = t * 14 * s  # light comes from the upper left
        draw.ellipse((cx - r - offset, cy - r - offset, cx + r - offset, cy + r - offset), fill=colour + (255,))
    mask = Image.new('L', big.size, 0)
    ImageDraw.Draw(mask).ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=255)
    big.paste(face, (0, 0), mask)
    draw = ImageDraw.Draw(big)
    # Rope rim: a ring of short diagonal ticks between two thin rings.
    for ring, width in ((radius - 2 * s, 3 * s), (radius - 15 * s, 2 * s)):
        draw.ellipse((cx - ring, cy - ring, cx + ring, cy + ring), outline=(150, 116, 60, 255), width=width)
    for i in range(72):
        a = 2 * math.pi * i / 72
        inner, outer = radius - 14 * s, radius - 4 * s
        draw.line([(cx + inner * math.cos(a), cy + inner * math.sin(a)),
                   (cx + outer * math.cos(a + 0.06), cy + outer * math.sin(a + 0.06))], fill=(196, 160, 96, 255), width=2 * s)
    # Knife silhouette with a warm edge highlight, plus a small star.
    blade = [(x * s, y * s) for x, y in knife(w / 2 + 4, h / 2 + 4, 156, -40)]
    edge = Image.new('L', big.size, 0)
    ImageDraw.Draw(edge).polygon(blade, fill=255)
    edge = edge.filter(ImageFilter.GaussianBlur(3 * s))
    big.paste(Image.new('RGBA', big.size, (255, 236, 170, 255)), (0, 0), edge.point(lambda v: min(255, v * 2)))
    draw.polygon(blade, fill=DARK + (255,))

    big.resize((w, h), Image.LANCZOS).save(RARE, optimize=True)


if __name__ == '__main__':
    case_icon()
    rare_item()
    print('Wrote', CASE.name, 'and', RARE.name)
