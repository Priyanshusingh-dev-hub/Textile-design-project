"""Rule 1 of the product: reducing colours must not lose detail or tear
shapes. Thin feature lines (stems, outlines, veins) are the hardest case —
they read as 'edges' to a gradient detector but are real ink the mill must
keep. These lock in that thin structures survive while smooth anti-alias
fringe is still dropped."""
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter
from app.color_engine import engine
from app.color_engine.engine import analyze, reduce, rgb_lab


def _lines(size, lw):
    a = np.full((size, size, 3), (240, 235, 220), np.uint8)  # cream field
    for x in range(size // 5, size, size // 5):
        a[:, x:x + lw] = (180, 40, 40)   # thin red verticals
    for y in range(size // 4, size, size // 4):
        a[y:y + lw, :] = (40, 80, 180)   # thin blue horizontals
    return Image.fromarray(a)


def _has(pal, pred):
    return any(pred(np.array(p.rgb)) for p in pal)


def test_thin_1px_lines_survive_reduction():
    pal = analyze(_lines(400, 1), 6)
    assert _has(pal, lambda c: c[0] > 140 and c[1] < 90), 'red 1px line lost'
    assert _has(pal, lambda c: c[2] > 140 and c[0] < 90), 'blue 1px line lost'


def test_thin_lines_survive_in_reduced_output_not_just_palette():
    img = _lines(500, 2)
    out = np.asarray(reduce(img, 6).convert('RGB'))
    col = out[:, 100:102].reshape(-1, 3)
    assert any(c[0] > 140 and c[1] < 90 for c in np.unique(col, axis=0)), 'red line erased from output'


def test_thin_lines_survive_at_high_resolution():
    pal = analyze(_lines(900, 3), 6)
    assert _has(pal, lambda c: c[0] > 140 and c[1] < 90)
    assert _has(pal, lambda c: c[2] > 140 and c[0] < 90)


def test_smooth_gradient_edge_is_not_kept_as_a_feature():
    """A soft two-tone blob (no thin detail) must still reduce to the two real
    colours, not gain a fringe ink — proving the feature detector doesn't just
    keep every edge."""
    a = np.full((120, 120, 3), (235, 222, 184), np.uint8)
    yy, xx = np.mgrid[0:120, 0:120]
    a[(xx - 60) ** 2 + (yy - 60) ** 2 <= 35 ** 2] = (200, 70, 58)
    img = Image.fromarray(a).filter(ImageFilter.GaussianBlur(2.2))
    reals = [rgb_lab(np.array(c, np.uint8)) for c in [(235, 222, 184), (200, 70, 58)]]
    for p in analyze(img, 4):
        if p.coverage < 2:
            continue
        d = min(float(np.linalg.norm(rgb_lab(np.array(p.rgb, np.uint8)) - r)) for r in reals)
        assert d < 22, f'{p.hex} is a fringe colour, not one of the two real inks'


def _noisy_two_tone():
    """A red and a cream region with added per-pixel noise, like brush grain
    or a woven-fabric scan."""
    rng = np.random.RandomState(0)
    a = np.zeros((80, 80, 3), np.uint8)
    a[:, :40] = (200, 60, 60); a[:, 40:] = (235, 222, 190)
    a = np.clip(a.astype(int) + rng.randint(-18, 18, a.shape), 0, 255).astype(np.uint8)
    return Image.fromarray(a)


def _speckle(flat, palette):
    from app.separation_engine.engine import create as sep
    layers = sep(flat, palette, cleanup=0)
    tot = 0
    for _, m, _ in layers:
        x = np.asarray(m)[:, :, 3] > 0
        up = np.zeros_like(x); up[1:] = x[:-1]; dn = np.zeros_like(x); dn[:-1] = x[1:]
        lf = np.zeros_like(x); lf[:, 1:] = x[:, :-1]; rt = np.zeros_like(x); rt[:, :-1] = x[:, 1:]
        tot += int((x & (up.astype(int) + dn + lf + rt == 0)).sum())
    return tot


def test_smoothing_reduces_speckle_on_noisy_source():
    from app.color_engine.engine import quantize_full
    img = _noisy_two_tone()
    flat0, pal0 = quantize_full(img, 3, smoothing=0)
    flat1, pal1 = quantize_full(img, 3, smoothing=1)
    assert _speckle(flat1, [p.hex for p in pal1]) < _speckle(flat0, [p.hex for p in pal0]) * 0.6


def test_smoothing_default_off_in_engine_keeps_1px_lines():
    # engine functions default to smoothing=0 so nothing is lost unasked
    pal = analyze(_lines(400, 1), 6)   # 1px lines, no smoothing
    assert _has(pal, lambda c: c[0] > 140 and c[1] < 90)


def test_small_motif_not_torn_apart():
    """A small solid dot must map to ONE ink, not be split/speckled."""
    a = np.full((100, 100, 3), (240, 235, 220), np.uint8)
    yy, xx = np.mgrid[0:100, 0:100]
    a[(xx - 50) ** 2 + (yy - 50) ** 2 <= 10 ** 2] = (30, 150, 70)
    out = np.asarray(reduce(Image.fromarray(a), 5).convert('RGB'))
    dot = out[45:55, 45:55].reshape(-1, 3)
    greens = [c for c in np.unique(dot, axis=0) if c[1] > 110 and c[0] < 90]
    assert len(greens) == 1, 'the dot should be a single flat ink'


# --- soft / feathered edges vs ordinary anti-aliasing -------------------------

def _aa(size, ss=4, blur=0):
    """Genuinely anti-aliased art: drawn at 4x and downscaled."""
    big = Image.new('RGBA', (size * ss, size * ss), (255, 255, 255, 0))
    ImageDraw.Draw(big).ellipse((size * ss * .2,) * 2 + (size * ss * .8,) * 2, fill=(192, 57, 43, 255))
    im = big.resize((size, size), Image.LANCZOS)
    return im.filter(ImageFilter.GaussianBlur(blur)) if blur else im


@pytest.mark.parametrize('size', [64, 200, 600])
def test_anti_aliasing_is_not_reported_as_a_soft_edge(size):
    """Nearly every PNG has an anti-aliased rim. Warning about those would fire
    on normal artwork and train the operator to ignore the warning."""
    assert engine.soft_edge_width(_aa(size)) <= engine.SOFT_EDGE_PX


def test_dense_thin_linework_is_not_reported_as_a_soft_edge():
    """The hard case: ~99% of this image's inked pixels are part-transparent,
    so any measure based on counting them would call it feathered."""
    big = Image.new('RGBA', (1200, 1200), (255, 255, 255, 0))
    d = ImageDraw.Draw(big)
    for i in range(0, 1200, 42):
        d.line((0, i, 1200, i + 24), fill=(0, 0, 0, 255), width=6)
    lines = big.resize((300, 300), Image.LANCZOS)
    a = np.asarray(lines)[:, :, 3]
    partial = ((a > 0) & (a < 255)).sum() / max(1, (a > 0).sum())
    assert partial > 0.9, 'this fixture is meant to be almost entirely part-transparent'
    assert engine.soft_edge_width(lines) <= engine.SOFT_EDGE_PX


@pytest.mark.parametrize('blur', [2, 5, 15])
def test_a_feathered_edge_is_reported(blur):
    assert engine.soft_edge_width(_aa(200, blur=blur)) > engine.SOFT_EDGE_PX


def test_a_fully_opaque_design_has_no_soft_edge():
    assert engine.soft_edge_width(Image.new('RGB', (40, 40), '#C0392B')) == 0.0


def test_soft_edge_of_a_fully_transparent_image_is_zero():
    assert engine.soft_edge_width(Image.new('RGBA', (40, 40), (0, 0, 0, 0))) == 0.0


# --- texture cleanup must not erase hairlines ---------------------------------

def _hairline_art(lines=True):
    im = Image.new('RGB', (300, 240), '#F4E8CC'); d = ImageDraw.Draw(im)
    d.ellipse((80, 50, 220, 190), fill='#C0392B')
    if lines:                                  # hard 1px lines: CAD / pixel exports
        for i in range(5):
            d.line((15 + i * 55, 225, 70 + i * 55, 15), fill='#1A1A1A', width=1)
        d.line((0, 215, 299, 215), fill='#1A1A1A', width=1)
        d.line((0, 25, 299, 33), fill='#2A5DA8', width=1)
    return im


def _line_pixels():
    im = Image.new('L', (300, 240), 0); d = ImageDraw.Draw(im)
    for i in range(5):
        d.line((15 + i * 55, 225, 70 + i * 55, 15), fill=255, width=1)
    d.line((0, 215, 299, 215), fill=255, width=1); d.line((0, 25, 299, 33), fill=255, width=1)
    return np.asarray(im) > 0


@pytest.mark.parametrize('smoothing', [1, 2])
def test_texture_cleanup_keeps_hard_1px_lines(smoothing):
    """A median erases anything thinner than its window; before line
    protection, Light kept 2% of a hard 1px line and Strong none."""
    with_lines = np.asarray(engine.quantize_full(_hairline_art(), 5, smoothing)[0].convert('RGB')).astype(int)
    without = np.asarray(engine.quantize_full(_hairline_art(False), 5, smoothing)[0].convert('RGB')).astype(int)
    kept = (np.abs(with_lines - without).sum(-1)[_line_pixels()] > 30).mean()
    assert kept > 0.9


def test_texture_cleanup_still_flattens_grain():
    """Specks are not lines: on pure grain the line protection must leave the
    median's work alone (a chance line-up of noise may slip through, rarely)."""
    from PIL import ImageFilter
    rs = np.random.RandomState(1)
    a = np.clip(np.full((120, 120, 3), (200, 170, 140), np.int16) + rs.randint(-35, 36, (120, 120, 1)), 0, 255)
    a = a.astype(np.uint8)
    median_only = np.asarray(Image.fromarray(a).filter(ImageFilter.MedianFilter(3)))
    restored = (engine._presmooth(a, 1) != median_only).any(-1).mean()
    assert restored < 0.03


def test_a_thin_line_of_the_middle_ink_inside_one_ink_is_kept():
    """A sage vein drawn inside a cream leaf has cream on both sides: it is
    design, not the rim between cream and dark, even with dark dots nearby."""
    import numpy as np
    from PIL import Image, ImageDraw
    from app.color_engine.engine import quantize_full, hex_rgb
    im = Image.new('RGB', (240, 200), '#0D1F14'); d = ImageDraw.Draw(im)
    d.ellipse((20, 20, 220, 180), fill='#F1ECDC')
    d.line((40, 100, 200, 100), fill='#A9AD93', width=2)       # the vein
    for x in range(50, 200, 12):
        d.rectangle((x, 104, x + 2, 106), fill='#0D1F14')     # dark dots beside it
    d.rectangle((0, 0, 30, 30), fill='#A9AD93')               # sage also exists as an area
    red, pal = quantize_full(im, 3, 0)
    r = np.asarray(red.convert('RGB'))
    sage = min((p.hex for p in pal), key=lambda h: abs(sum(hex_rgb(h)) - sum(hex_rgb('#A9AD93'))))
    vein = (r[99:102, 45:195] == np.array(hex_rgb(sage))).all(-1)
    assert vein.any(0).mean() > 0.95                           # the vein runs unbroken


def _mottled_ground_design(seed=3):
    """A ground of one colour painted with blotchy mottling (two shades
    dE 5 apart, woven through each other: the teal floral's ground), with
    motifs on top."""
    rng = np.random.default_rng(seed)
    n = 200
    noise = np.asarray(Image.fromarray((rng.random((n // 8, n // 8)) * 255).astype(np.uint8))
                       .resize((n, n), Image.BICUBIC)) > 128
    a = np.zeros((n, n, 3), np.uint8)
    a[:] = (1, 68, 101); a[noise] = (1, 54, 88)                   # mottled navy, dE 5.1
    yy, xx = np.mgrid[0:n, 0:n]
    a[(xx - 60) ** 2 + (yy - 60) ** 2 < 30 ** 2] = (232, 229, 222)  # cream motif
    a[(xx - 140) ** 2 + (yy - 130) ** 2 < 35 ** 2] = (179, 60, 50)  # red motif
    a[150:156, 20:120] = (60, 110, 160)                           # a blue band
    return Image.fromarray(a)


def test_a_mottled_ground_is_one_ink_and_the_screen_goes_to_a_real_colour():
    """Two shades woven through each other are one colour's mottling: kept
    apart they print as blotches and cost a screen that a motif needed."""
    from app.color_engine.engine import quantize_full, delta_e2000, rgb_lab
    _, pal = quantize_full(_mottled_ground_design(), 4)
    labs = rgb_lab(np.array([p.rgb for p in pal], np.uint8))
    blue = rgb_lab(np.array([[60, 110, 160]], np.uint8))[0]
    dark = [p for p, l in zip(pal, labs) if l[0] < 30]
    assert len(dark) == 1, [p.hex for p in pal]
    assert min(delta_e2000(labs, blue)) < 3, 'the blue band lost its ink to the mottling'


def test_two_close_colours_in_separate_shapes_stay_two_inks():
    """Close colours that are separate motifs (not woven through each other)
    are the designer's choice, not mottling."""
    from app.color_engine.engine import quantize_full
    a = np.zeros((160, 160, 3), np.uint8); a[:] = (245, 240, 230)
    a[20:70, 20:140] = (52, 44, 29)
    a[90:140, 20:140] = (44, 36, 23)
    _, pal = quantize_full(Image.fromarray(a), 3)
    assert len(pal) == 3, [p.hex for p in pal]


def _flowers(noise=0.0, seed=0):
    """Flat motifs with 1px outlines, optionally with scan grain + weave."""
    from PIL import ImageDraw
    big = Image.new('RGB', (1200, 800), (225, 210, 187)); d = ImageDraw.Draw(big)
    for i in range(12):
        x, y = (i * 173) % 1000, (i * 251) % 600
        d.ellipse([x, y, x + 160, y + 120], fill=(243, 168, 176), outline=(202, 61, 90), width=4)
        d.line([x, y + 150, x + 180, y + 60], fill=(61, 74, 40), width=6)
    a = np.asarray(big.resize((300, 200), Image.LANCZOS)).astype(float)
    if noise:
        rng = np.random.default_rng(seed); yy, xx = np.mgrid[0:200, 0:300]
        a = a + rng.normal(0, noise, a.shape) + (np.sin(xx * 1.9) * np.sin(yy * 1.9))[..., None] * noise * 0.8
    return Image.fromarray(a.clip(0, 255).astype(np.uint8))


@pytest.mark.parametrize('noise,level', [(0, 0), (2, 0), (9, 1), (14, 2)])
def test_texture_cleanup_is_chosen_from_the_grain(noise, level):
    """Clean and painterly art gets none — on every real design cleanup only
    erased outlines, dots and veins. A grainy scan gets enough to stop its
    plates speckling."""
    assert engine.auto_smoothing(_flowers(noise))[0] == level


def test_reduce_without_a_cleanup_level_chooses_it():
    import io
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    buf = io.BytesIO(); _flowers(9).save(buf, 'PNG')
    up = c.post('/api/image/upload', files={'file': ('scan.png', buf.getvalue(), 'image/png')}).json()
    assert c.post('/api/colors/suggest', json={'image_id': up['image_id']}).json()['smoothing'] == 1
    assert c.post('/api/colors/reduce', json={'image_id': up['image_id'], 'colors': 3}).json()['smoothing'] == 1
    assert c.post('/api/colors/reduce', json={'image_id': up['image_id'], 'colors': 3, 'smoothing': 0}).json()['smoothing'] == 0
