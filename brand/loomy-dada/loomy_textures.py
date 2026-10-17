"""Procedural PBR textures for LOOMY DADA (pure numpy + Pillow, deterministic).

One 2048x2048 atlas for every opaque part (base colour, ORM = occlusion /
roughness / metallic, tangent-space normal in the OpenGL/glTF convention,
emissive) plus a 2048x2048 RGBA + emissive pair for the transparent visor.
Nothing here bakes light or shadow: base colour is the material colour, the
only "shading" is the normal map, so the model can be lit by any scene.

Atlas layout (UV, v = 0 at the bottom) -- build_loomy_dada.py maps each part
into its region:

    body    u 0..1      v 0.5..1      the wound thread (teal / cream / teal)
    flange  u 0..1      v 0.375..0.5  light wood of the two spool flanges
    eye     u 0..0.125  v 0.25..0.375 sclera, teal iris, pupil, highlights
    screen  u 0.125..0.375, v 0.25..0.375  the tablet's "L" logo screen
    cells   u 0.5..1    v 0.25..0.375 16 flat material swatches (8 x 2)
    ribbon  u 0..1      v 0.03125..0.09375  violet multi-strand wrap / cuffs
    thread  u 0..1      v 0..0.03125  the loose teal-to-violet thread
"""
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

N = 2048
RNG = np.random.default_rng(7)

# The palette: teal, violet, cream, light wood, dark grey (and a pink tongue).
TEAL = (0.03, 0.55, 0.55)
TEAL_DEEP = (0.02, 0.40, 0.41)
VIOLET = (0.42, 0.30, 0.80)
CREAM = (0.95, 0.91, 0.84)
WOOD = (0.90, 0.80, 0.64)
DARK = (0.17, 0.19, 0.22)

REGIONS = {
    'body': (0.0, 0.5, 1.0, 1.0),
    'flange': (0.0, 0.375, 1.0, 0.5),
    'eye': (0.0, 0.25, 0.125, 0.375),
    'screen': (0.125, 0.25, 0.375, 0.375),
    'cells': (0.5, 0.25, 1.0, 0.375),
    'ribbon': (0.0, 0.03125, 1.0, 0.09375),
    'thread': (0.0, 0.0, 1.0, 0.03125),
}

# flat swatches: name -> (base rgb, roughness, metallic, emissive rgb or None)
CELLS = [
    ('shell', (0.95, 0.93, 0.89), 0.42, 0.0, None),        # limb shells
    ('glove', (0.98, 0.97, 0.94), 0.55, 0.0, None),        # gloved hands
    ('joint', (0.20, 0.22, 0.25), 0.38, 0.35, None),       # robotic joints
    ('graphite', (0.15, 0.16, 0.19), 0.62, 0.10, None),    # pods, strap, tablet back
    ('teal', TEAL, 0.40, 0.0, None),
    ('teal_deep', TEAL_DEEP, 0.55, 0.0, None),             # chunky soles
    ('violet', VIOLET, 0.42, 0.0, None),
    ('tongue', (0.93, 0.52, 0.62), 0.35, 0.0, None),
    ('mouth', (0.27, 0.11, 0.18), 0.65, 0.0, None),
    ('brow', (0.16, 0.15, 0.19), 0.60, 0.0, None),
    ('glow_teal', (0.30, 0.95, 0.90), 0.30, 0.0, (0.25, 1.00, 0.93)),
    ('glow_violet', (0.70, 0.58, 1.00), 0.30, 0.0, (0.66, 0.48, 1.00)),
    ('sneaker', (0.96, 0.93, 0.87), 0.62, 0.0, None),
    ('bezel', (0.24, 0.26, 0.30), 0.28, 0.55, None),       # tablet edge
    ('wood_dark', (0.62, 0.50, 0.36), 0.70, 0.0, None),    # the spool's centre hole
    ('white', (1.0, 1.0, 1.0), 0.30, 0.0, None),
]
CELL_INDEX = {c[0]: i for i, c in enumerate(CELLS)}
EYE_U = 0.115                  # visor u of each eye centre from the middle (set by the build script's geometry)


def cell_rect(name, margin=0.18):
    """UV rect (u0, v0, u1, v1) inside a swatch, inset so filtering never
    reaches the neighbour."""
    i = CELL_INDEX[name]
    u0, v0, u1, v1 = REGIONS['cells']
    cw, ch = (u1 - u0) / 8, (v1 - v0) / 2
    cu, cv = u0 + (i % 8) * cw, v0 + (i // 8) * ch
    return (cu + margin * cw, cv + margin * ch, cu + (1 - margin) * cw, cv + (1 - margin) * ch)


def px_rect(region):
    """Pixel box (x0, y0, x1, y1) of a UV region in a top-down image."""
    u0, v0, u1, v1 = REGIONS[region]
    return int(round(u0 * N)), int(round((1 - v1) * N)), int(round(u1 * N)), int(round((1 - v0) * N))


def smooth_noise(shape, sigma, seed):
    r = np.random.default_rng(seed).standard_normal(shape)
    r = ndimage.gaussian_filter(r, sigma, mode='wrap')
    return r / (np.abs(r).max() + 1e-9)


def height_to_normal(h, strength, wrap=True):
    """Tangent-space normal (glTF/OpenGL: +X right, +Y up) from a height field
    in a top-down image (row 0 = v 1)."""
    mode = 'wrap' if wrap else 'nearest'
    dx = ndimage.sobel(h, axis=1, mode=mode) / 8.0
    dy = -ndimage.sobel(h, axis=0, mode=mode) / 8.0     # image rows run down, v runs up
    n = np.dstack([-dx * strength, -dy * strength, np.ones_like(h)])
    return n / np.linalg.norm(n, axis=2, keepdims=True)


class Atlas:
    def __init__(self):
        self.base = np.zeros((N, N, 3)); self.base[:] = (0.5, 0.5, 0.5)
        self.rough = np.full((N, N), 0.6)
        self.metal = np.zeros((N, N))
        self.normal = np.zeros((N, N, 3)); self.normal[..., 2] = 1.0
        self.emit = np.zeros((N, N, 3))

    def put(self, region, base=None, rough=None, metal=None, normal=None, emit=None):
        x0, y0, x1, y1 = px_rect(region)
        for arr, val in ((self.base, base), (self.rough, rough), (self.metal, metal), (self.normal, normal), (self.emit, emit)):
            if val is not None:
                arr[y0:y1, x0:x1] = val


def _body(atlas):
    """Thread wound on the spool: fine round strands (one winding every 4.5 mm,
    on a slight helix so the texture wraps seamlessly), fibre streaks along
    the strand, a groove between the teal and cream sections."""
    x0, y0, x1, y1 = px_rect('body'); w, h = x1 - x0, y1 - y0
    z0, z1 = 0.31, 0.90                              # body height the region spans (model units)
    v = (np.arange(h)[::-1] + 0.5) / h               # 0 at the bottom row
    z = z0 + v * (z1 - z0)
    u = (np.arange(w) + 0.5) / w
    pitch = 0.0045
    phase = (z[:, None] / pitch + u[None, :]) % 1.0  # one winding of rise per turn
    strand = np.sqrt(np.clip(1 - (2 * phase - 1) ** 2, 0, 1))
    winding = np.floor(z[:, None] / pitch + u[None, :]).astype(int)
    tint = (np.random.default_rng(11).random(winding.max() + 2) - 0.5) * 0.06
    fibre = smooth_noise((h, w), (0.6, 18), 3) * 0.5
    height = strand * 0.9 + fibre * 0.12
    bands = [(0.31, 0.46, TEAL), (0.46, 0.76, CREAM), (0.76, 0.90, TEAL)]
    base = np.zeros((h, w, 3))
    for lo, hi, col in bands:
        m = (z >= lo) & (z < hi)
        base[m] = col
    shade = 0.86 + 0.14 * strand + tint[winding] + fibre * 0.03
    base = base * shade[..., None]
    for edge in (0.46, 0.76):                         # a soft groove where two sections meet
        g = np.exp(-((z - edge) / 0.004) ** 2)
        base *= (1 - 0.35 * g)[:, None, None]
        height -= 1.2 * g[:, None]
    atlas.put('body', base=np.clip(base, 0, 1), rough=0.74 - 0.08 * strand, metal=0.0,
              normal=height_to_normal(height, 2.2))


def _flange(atlas):
    """Light turned wood: soft rings along the profile, faint pores."""
    x0, y0, x1, y1 = px_rect('flange'); w, h = x1 - x0, y1 - y0
    warp = smooth_noise((h, w), (6, 120), 5) * 6
    yy = np.arange(h)[:, None] + warp
    rings = 0.5 + 0.5 * np.sin(yy / h * np.pi * 26 + smooth_noise((h, w), (3, 60), 9) * 2.5)
    pores = smooth_noise((h, w), (0.7, 6), 13)
    base = np.array(WOOD)[None, None, :] * (0.93 + 0.07 * rings[..., None] + 0.03 * pores[..., None])
    atlas.put('flange', base=np.clip(base, 0, 1), rough=0.58 + 0.06 * rings, metal=0.0,
              normal=height_to_normal(rings * 0.25 + pores * 0.15, 1.0))


def _eye(atlas):
    x0, y0, x1, y1 = px_rect('eye'); s = x1 - x0
    yy, xx = np.mgrid[0:s, 0:s]
    x = (xx + 0.5) / s * 2 - 1; y = 1 - (yy + 0.5) / s * 2      # -1..1, y up
    r = np.hypot(x, y)
    base = np.zeros((s, s, 3)); base[:] = (0.985, 0.975, 0.955)
    iris_r, pupil_r = 0.66, 0.34
    ang = np.arctan2(y, x)
    stri = 0.5 + 0.5 * np.sin(ang * 34 + smooth_noise((s, s), 2, 21) * 3)
    t = np.clip(r / iris_r, 0, 1)
    iris = (np.array(TEAL)[None, None] * (1.15 - 0.55 * t[..., None] ** 2) * (0.9 + 0.1 * stri[..., None]))
    m_iris = r < iris_r
    base[m_iris] = iris[m_iris]
    ring = (r > iris_r - 0.05) & (r < iris_r)
    base[ring] = np.array(TEAL_DEEP) * 0.6
    base[r < pupil_r] = (0.05, 0.07, 0.09)
    for cx, cy, rad in ((-0.27, 0.30, 0.17), (0.25, -0.24, 0.075)):       # catch lights
        base[np.hypot(x - cx, y - cy) < rad] = (1.0, 1.0, 1.0)
    atlas.put('eye', base=np.clip(base, 0, 1), rough=0.12, metal=0.0)


def _logo(draw, box, scale=1.0, fill_l=(255, 255, 255), teal=(30, 200, 196), violet=(150, 112, 240)):
    """The LoomLab "L" with a teal and a violet leaf sprouting from its corner."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    cx, cy = x0 + w * 0.5, y0 + h * 0.52
    L = min(w, h) * 0.62 * scale
    t = L * 0.24                                            # stroke thickness
    lx, ly = cx - L * 0.42, cy - L * 0.5                    # top-left of the L
    draw.rounded_rectangle((lx, ly, lx + t, ly + L), radius=t * 0.45, fill=fill_l)
    draw.rounded_rectangle((lx, ly + L - t, lx + L * 0.72, ly + L), radius=t * 0.45, fill=fill_l)

    def leaf(px, py, length, width, angle, colour):
        a = np.radians(angle)
        d = np.array([np.cos(a), -np.sin(a)]); n = np.array([d[1], -d[0]])
        pts = []
        for k in np.linspace(0, 1, 24):
            pts.append((np.array([px, py]) + d * length * k + n * width * np.sin(np.pi * k)))
        for k in np.linspace(1, 0, 24):
            pts.append((np.array([px, py]) + d * length * k - n * width * np.sin(np.pi * k) * 0.55))
        draw.polygon([tuple(p) for p in pts], fill=colour)

    sx, sy = lx + L * 0.72 + t * 0.1, ly + L - t * 0.55
    leaf(sx, sy, L * 0.42, L * 0.13, 58, teal)
    leaf(sx + L * 0.02, sy, L * 0.32, L * 0.10, 18, violet)


def _screen(atlas):
    x0, y0, x1, y1 = px_rect('screen'); w, h = x1 - x0, y1 - y0
    up = 4                                                  # draw large, then downsample (clean edges)
    img = Image.new('RGB', (w * up, h * up), (22, 26, 31))
    d = ImageDraw.Draw(img)
    for i in range(0, h * up, up * 6):                      # very faint scan lines
        d.line((0, i, w * up, i), fill=(26, 31, 37), width=up)
    _logo(d, (0, 0, w * up, h * up))
    rgb = np.asarray(img.resize((w, h), Image.LANCZOS), dtype=np.float64) / 255
    glow = np.clip((rgb - 0.12) * 1.15, 0, 1)
    atlas.put('screen', base=rgb, rough=0.08, metal=0.0, emit=glow * 0.9)


def _cells(atlas):
    for i, (name, rgb, rough, metal, emit) in enumerate(CELLS):
        u0, v0, u1, v1 = REGIONS['cells']
        cw, ch = (u1 - u0) / 8, (v1 - v0) / 2
        cu, cv = u0 + (i % 8) * cw, v0 + (i // 8) * ch
        xa, xb = int(round(cu * N)), int(round((cu + cw) * N))
        ya, yb = int(round((1 - cv - ch) * N)), int(round((1 - cv) * N))
        atlas.base[ya:yb, xa:xb] = rgb
        atlas.rough[ya:yb, xa:xb] = rough
        atlas.metal[ya:yb, xa:xb] = metal
        if emit is not None:
            atlas.emit[ya:yb, xa:xb] = emit


def _ribbon(atlas):
    """Five round violet strands side by side (the diagonal wrap and the wrist
    cuffs), each with a gentle twist."""
    x0, y0, x1, y1 = px_rect('ribbon'); w, h = x1 - x0, y1 - y0
    v = (np.arange(h)[::-1] + 0.5) / h
    u = (np.arange(w) + 0.5) / w
    k = 5
    phase = (v[:, None] * k) % 1.0
    strand = np.sqrt(np.clip(1 - (2 * phase - 1) ** 2, 0, 1)) * np.ones((1, w))
    twist = 0.5 + 0.5 * np.sin((u[None, :] * 900 + v[:, None] * k * 7) * 2 * np.pi)
    height = strand + 0.08 * twist * strand
    which = np.floor(v * k).astype(int)
    tint = np.array([0.0, 0.04, -0.03, 0.02, -0.02])[which][:, None]
    base = np.array(VIOLET)[None, None] * (0.8 + 0.2 * strand[..., None] + tint[..., None])
    atlas.put('ribbon', base=np.clip(base, 0, 1), rough=0.62 - 0.1 * strand, metal=0.0,
              normal=height_to_normal(height, 1.6))


def _thread(atlas):
    """The loose thread: teal at its start, violet at its end, a twisted ply."""
    x0, y0, x1, y1 = px_rect('thread'); w, h = x1 - x0, y1 - y0
    v = (np.arange(h)[::-1] + 0.5) / h
    u = (np.arange(w) + 0.5) / w
    t = np.clip((u - 0.42) / 0.40, 0, 1)            # teal round the body, violet down to the curl
    t = t * t * (3 - 2 * t)
    col = (1 - t)[:, None] * np.array(TEAL) + t[:, None] * np.array(VIOLET)
    ply = (u[None, :] * 140 + v[:, None]) % 1.0
    strand = np.sqrt(np.clip(1 - (2 * ply - 1) ** 2, 0, 1))
    base = col[None, :, :] * (0.82 + 0.18 * strand[..., None])
    atlas.put('thread', base=np.clip(base, 0, 1), rough=0.6, metal=0.0,
              normal=height_to_normal(strand, 1.2))


def visor_maps():
    """The holographic visor: a faint teal tint, brighter HUD marks (brackets
    round each eye, tick rows, a scan line, small rings) -- marks only, no text."""
    up = 2
    W = N * up
    alpha = Image.new('L', (W, W), 42)
    marks = Image.new('L', (W, W), 0)
    d = ImageDraw.Draw(marks)
    s = W / 2048
    lw = int(5 * s)
    for ex in (0.5 - EYE_U, 0.5 + EYE_U):                   # visor u of each eye (see build script)
        cx, cy = ex * W, 0.5 * W
        rx, ry = 0.05 * W, 0.30 * W
        for k in range(4):                                  # corner brackets
            sx, sy = (-1 if k % 2 == 0 else 1), (-1 if k < 2 else 1)
            ax, ay = cx + sx * rx, cy + sy * ry
            d.line((ax, ay, ax - sx * rx * 0.35, ay), fill=255, width=lw)
            d.line((ax, ay, ax, ay - sy * ry * 0.35), fill=255, width=lw)
        d.ellipse((cx - rx * 0.62, cy - ry * 0.62, cx + rx * 0.62, cy + ry * 0.62), outline=150, width=int(3 * s))
    for i in range(36):                                     # tick rows along top and bottom edges
        x = W * (0.2 + 0.6 * i / 35)
        tall = 0.06 if i % 6 == 0 else 0.03
        d.line((x, W * 0.08, x, W * (0.08 + tall)), fill=190, width=int(3 * s))
        d.line((x, W * 0.92, x, W * (0.92 - tall)), fill=190, width=int(3 * s))
    d.line((W * 0.18, W * 0.70, W * 0.82, W * 0.70), fill=120, width=int(4 * s))   # scan line
    for cx, cy, rr in ((0.22, 0.30, 0.012), (0.78, 0.30, 0.012), (0.5, 0.82, 0.008)):
        d.ellipse((W * (cx - rr), W * (cy - rr * 4), W * (cx + rr), W * (cy + rr * 4)), outline=220, width=int(3 * s))
    m = np.asarray(marks.resize((N, N), Image.LANCZOS), dtype=np.float64) / 255
    glow = ndimage.gaussian_filter(m, 3) * 0.6 + m
    a = np.asarray(alpha.resize((N, N)), dtype=np.float64) / 255 + 0.55 * m
    col = np.array([0.30, 0.92, 0.88])
    rgba = np.dstack([np.ones((N, N, 3)) * col, np.clip(a, 0, 1)])
    emit = np.clip(glow[..., None] * np.array([0.35, 1.0, 0.95]) + 0.12 * col, 0, 1)
    return rgba, emit


def build_atlas():
    a = Atlas()
    _cells(a); _body(a); _flange(a); _eye(a); _screen(a); _ribbon(a); _thread(a)
    return a


def to_png(arr, path, mode='RGB'):
    img = np.clip(np.round(arr * 255), 0, 255).astype(np.uint8)
    Image.fromarray(img, mode).save(path, optimize=True)


def write_all(folder):
    """Writes the 6 maps; returns their paths."""
    import os
    a = build_atlas()
    orm = np.dstack([np.ones((N, N)), a.rough, a.metal])     # R occlusion (none baked), G roughness, B metallic
    nrm = a.normal * 0.5 + 0.5
    rgba, vemit = visor_maps()
    paths = {}
    for name, arr, mode in (('atlas_basecolor', a.base, 'RGB'), ('atlas_orm', orm, 'RGB'),
                            ('atlas_normal', nrm, 'RGB'), ('atlas_emissive', a.emit, 'RGB'),
                            ('visor_basecolor', rgba, 'RGBA'), ('visor_emissive', vemit, 'RGB')):
        p = os.path.join(folder, name + '.png'); to_png(arr, p, mode); paths[name] = p
    return paths


if __name__ == '__main__':
    import sys
    print(write_all(sys.argv[1] if len(sys.argv) > 1 else '.'))
