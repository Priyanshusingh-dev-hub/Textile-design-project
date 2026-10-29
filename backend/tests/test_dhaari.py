"""Thin curved stripes (dhaari / veins) survive a flat reduce.

A vein is tagged from the source and kept through the majority filter. When
its colour is not already an ink, it becomes one — only those pixels move.
A flat interior, a cluster of exact dots, and a junk island of a few pixels
stay on the old rules: the interior is untouched, the dots stay, the junk
joins the ink around it. Nothing is scaled down, and no gradient is sprayed.
"""
import numpy as np
from PIL import Image

from app.color_engine.engine import hex_rgb, quantize_full
from app.separation_engine.engine import create as separate

CREAM = np.array([244, 232, 204], np.uint8)
RED = np.array([192, 57, 43], np.uint8)
GREEN = np.array([30, 140, 70], np.uint8)
BLUE = np.array([42, 93, 168], np.uint8)


def _curve(n=180, jitter=6, width=2, seed=1):
    """A sine stripe whose pixels are not one repeated RGB, plus a red field."""
    a = np.full((n, n, 3), CREAM, np.uint8)
    a[30:90, n - 70:n - 20] = RED
    rng = np.random.RandomState(seed)
    ys = np.arange(20, n - 20)
    xs = (40 + (22 * np.sin(ys / 9.0))).astype(int)
    for y, x in zip(ys, xs):
        for w in range(width):
            a[y, x + w] = np.clip(GREEN.astype(int) + rng.randint(-jitter, jitter + 1, 3), 0, 255)
    return a, ys, xs


def _green_share(rgb, ys, xs):
    got = rgb[ys, xs].astype(int)
    green = np.abs(got - GREEN.astype(int)).sum(-1)
    cream = np.abs(got - CREAM.astype(int)).sum(-1)
    red = np.abs(got - RED.astype(int)).sum(-1)
    return float(((green + 40 < cream) & (green + 40 < red)).mean())


def test_a_thin_curved_stripe_is_kept_even_when_the_ink_budget_is_two():
    """The curve's pixels never repeat one RGB eight times, so the exact-colour
    recovery misses it, and two inks would otherwise spend both on the field."""
    a, ys, xs = _curve()
    out, pal = quantize_full(Image.fromarray(a), 2, 0)
    rgb = np.asarray(out.convert('RGB'))
    assert out.size == (a.shape[1], a.shape[0])
    assert _green_share(rgb, ys, xs) >= 0.90
    assert any(np.abs(np.array(hex_rgb(p.hex), int) - GREEN.astype(int)).sum() < 80 for p in pal)


def test_a_jittered_curve_stays_one_continuous_green():
    a, ys, xs = _curve(jitter=8, width=2)
    out, pal = quantize_full(Image.fromarray(a), 4, 0)
    rgb = np.asarray(out.convert('RGB'))
    assert _green_share(rgb, ys, xs) >= 0.92
    # the red field is not repainted by the vein ink
    assert np.all(np.abs(rgb[40:80, a.shape[1] - 60:a.shape[1] - 30].astype(int) - RED.astype(int)).sum(-1) < 30)


def test_clustered_exact_dots_stay_and_a_junk_island_merges():
    a = np.full((80, 120, 3), CREAM, np.uint8)
    a[8:40, 8:36] = RED
    dots = []
    for y in (12, 22, 32, 50, 62):
        for x in (70, 82, 94):
            a[y, x] = RED
            dots.append((y, x))
    a[18:20, 50:52] = (210, 78, 60)          # 2x2 near-red crumb, not an ink
    out, pal = quantize_full(Image.fromarray(a), 4, 0)
    rgb = np.asarray(out.convert('RGB'))
    assert all(np.abs(rgb[y, x].astype(int) - RED.astype(int)).sum() < 30 for y, x in dots)
    assert np.all(np.abs(rgb[18:20, 50:52].astype(int) - CREAM.astype(int)).sum(-1) < 30)
    # the red field, edge included, is still the field
    assert np.all(np.abs(rgb[8:40, 8:36].astype(int) - RED.astype(int)).sum(-1) < 30)
    assert out.info['review_specks'] >= len(dots)


def test_a_flat_interior_is_unchanged():
    a = np.full((90, 110, 3), CREAM, np.uint8)
    a[20:70, 15:80] = RED
    out, pal = quantize_full(Image.fromarray(a), 3, 0)
    rgb = np.asarray(out.convert('RGB'))
    assert rgb.shape[:2] == a.shape[:2]
    assert np.array_equal(rgb[20:70, 15:80], np.broadcast_to(RED, (50, 65, 3)))
    assert np.array_equal(rgb[:20], np.broadcast_to(CREAM, (20, 110, 3)))
    assert np.array_equal(rgb[70:], np.broadcast_to(CREAM, (20, 110, 3)))
    assert len(pal) == 2


def test_a_faint_olive_curve_is_tagged_and_kept():
    """A petal vein is often only a little greener than the ground. It still
    has to come through as its own hard colour."""
    faint = np.array([112, 148, 78], np.uint8)
    a = np.full((160, 200, 3), CREAM, np.uint8)
    a[20:70, 140:180] = RED
    ys = np.arange(18, 142)
    xs = (36 + (16 * np.sin(ys / 11.0))).astype(int)
    for y, x in zip(ys, xs):
        a[y, x] = faint
        a[y, min(x + 1, 199)] = faint
    out, pal = quantize_full(Image.fromarray(a), 3, 0)
    rgb = np.asarray(out.convert('RGB'))
    got = rgb[ys, xs].astype(int)
    vein = np.abs(got - faint.astype(int)).sum(-1)
    ground = np.abs(got - CREAM.astype(int)).sum(-1)
    assert float((vein + 30 < ground).mean()) >= 0.85
    assert any(np.abs(np.array(hex_rgb(p.hex), int) - faint.astype(int)).sum() < 90 for p in pal)


def test_a_tagged_vein_is_a_thin_hard_stroke():
    """Once tagged, the vein is one flat colour and not a fat soft fringe.
    Nothing is grown past the mark, and the edge is hard."""
    a, ys, xs = _curve(jitter=3, width=2)
    out, pal = quantize_full(Image.fromarray(a), 4, 0)
    rgb = np.asarray(out.convert('RGB'))
    band = np.zeros(rgb.shape[:2], bool)
    band[ys, xs] = True
    band[ys, np.clip(xs + 1, 0, rgb.shape[1] - 1)] = True
    cols, counts = np.unique(rgb[band], axis=0, return_counts=True)
    ink = cols[int(np.argmax(counts))]
    on = np.all(rgb == ink, axis=-1)
    assert counts.max() / int(band.sum()) >= 0.85
    # the stroke's half-width stays a line, not a filled band
    from scipy import ndimage
    rad = ndimage.distance_transform_edt(on)
    assert float(rad.max()) <= 2.6
    # the red field is untouched
    assert np.all(np.abs(rgb[40:80, a.shape[1] - 60:a.shape[1] - 30].astype(int) - RED.astype(int)).sum(-1) < 30)


def test_separation_at_cleanup_0_keeps_the_curve_on_one_plate():
    a, ys, xs = _curve(jitter=0, width=1)
    out, pal = quantize_full(Image.fromarray(a), 4, 0)
    rgb = np.asarray(out.convert('RGB'))
    layers = separate(out, [p.hex for p in pal], 0)
    recon = np.zeros_like(rgb)
    for hx, mask, _ in layers:
        recon[np.asarray(mask)[:, :, 3] > 0] = hex_rgb(hx)
    assert np.array_equal(recon, rgb)
    assert _green_share(rgb, ys, xs) >= 0.80
