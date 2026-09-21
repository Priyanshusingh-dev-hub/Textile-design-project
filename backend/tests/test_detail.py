"""Rule 1 of the product: reducing colours must not lose detail or tear
shapes. Thin feature lines (stems, outlines, veins) are the hardest case —
they read as 'edges' to a gradient detector but are real ink the mill must
keep. These lock in that thin structures survive while smooth anti-alias
fringe is still dropped."""
import numpy as np
from PIL import Image, ImageFilter
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
    for _, m, _, _ in layers:
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
