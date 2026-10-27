"""Flat-patch edges after Reduce should read as a pen stroke.

The 3x3 majority filter removes a one-pixel crumb and leaves a curve that
wandered in the source — a torn stair. Fairing runs after the inks are
chosen. These lock the things it must not trade away: a torn closed curve
gets smoother, a hard rectangle stays put, a 1px line and an exact dot stay,
a thin connected colour stays, the interior of a solid patch stays, and
separation at cleanup 0 still rebuilds the reduced image.
"""
import numpy as np
from PIL import Image, ImageDraw

from app.color_engine import engine
from app.color_engine.engine import _fat_kink, quantize_full
from app.separation_engine.engine import create as separate

CREAM = (244, 232, 204)
RED = (192, 57, 43)
GREEN = (30, 140, 70)
SAGE = (169, 173, 147)


def _near(rgb, color, tol=40):
    return np.abs(rgb.astype(int) - np.array(color)).sum(-1) <= tol


def _wobbly_disk(n=240, radius=78):
    """A flat disk whose outline jumps by several pixels every few degrees.

    A gentle sine is still a smooth pen curve (its chain never snaps). This
    one is the torn stair a noisy quantise leaves: the radius is constant on
    a 3-degree step and then leaps."""
    yy, xx = np.mgrid[0:n, 0:n]
    cy = cx = n // 2
    theta = np.arctan2(yy - cy, xx - cx)
    r = np.hypot(yy - cy, xx - cx)
    bins = np.floor((theta + np.pi) / (2 * np.pi) * 120).astype(int) % 120
    offsets = np.array(
        [((i * 17) % 9) - 4 for i in range(120)], np.float64)
    a = np.full((n, n, 3), CREAM, np.uint8)
    a[r <= radius + offsets[bins]] = RED
    return Image.fromarray(a), radius, cy


def _rgb(image):
    return np.asarray(image.convert('RGB'))


def test_a_torn_closed_curve_is_faired_and_its_interior_stays(monkeypatch):
    img, radius, c = _wobbly_disk()
    seen = {}
    real = engine._smooth_patch_boundaries

    def _wrap(labels, opaque=None):
        seen['kink'] = _fat_kink(np.asarray(labels))
        return real(labels, opaque)

    monkeypatch.setattr(engine, '_smooth_patch_boundaries', _wrap)
    out, pal = quantize_full(img, 4, 0)
    assert out.size == img.size
    raw = seen['kink']
    fair = _fat_kink(_labels_of(_rgb(out), pal))
    # The fixture is torn after assignment (measured well above a clean disk's
    # ~0.5). Fairing has to bring that down, not merely repaint the same stair.
    assert raw > 2.0, raw
    assert fair <= raw * 0.65, (raw, fair)
    rgb = _rgb(out)
    yy, xx = np.mgrid[0:img.size[1], 0:img.size[0]]
    r = np.hypot(yy - c, xx - c)
    assert _near(rgb[r < radius - 16], RED).all()
    assert _near(rgb[r > radius + 16], CREAM).all()
    assert any(p.hex == '#C0392B' for p in pal)


def test_a_hard_rectangle_is_not_rounded(monkeypatch):
    a = np.full((100, 120, 3), CREAM, np.uint8)
    a[15:85, 20:100] = RED
    img = Image.fromarray(a)
    real = engine._smooth_patch_boundaries
    monkeypatch.setattr(engine, '_smooth_patch_boundaries', lambda labels, opaque=None: np.array(labels, dtype=np.int64, copy=True))
    raw, _ = quantize_full(img, 4, 0)
    monkeypatch.setattr(engine, '_smooth_patch_boundaries', real)
    fair, _ = quantize_full(img, 4, 0)
    assert np.array_equal(_rgb(raw), _rgb(fair))


def test_exact_1px_line_dot_and_gap_stay():
    a = np.full((90, 150, 3), CREAM, np.uint8)
    a[:, 15] = RED
    a[8, 100] = RED
    a[80, 108] = RED
    a[25:65, 40:75] = GREEN
    a[10:70, 120:128] = RED
    a[10:70, 129:140] = RED
    out, _ = quantize_full(Image.fromarray(a), 4, 0)
    rgb = _rgb(out)
    assert int(_near(rgb[:, 15], RED).sum()) >= 90 - 2
    assert bool(_near(rgb[8, 100], RED)) and bool(_near(rgb[80, 108], RED))
    assert out.info['review_specks'] >= 2
    assert int(_near(rgb[10:70, 128], CREAM).sum()) == 60
    assert int(_near(rgb[30:60, 45:70], GREEN).sum()) == 30 * 25


def test_a_thin_connected_colour_stays_a_line():
    im = Image.new('RGB', (220, 160), '#0D1F14')
    d = ImageDraw.Draw(im)
    d.ellipse((20, 16, 200, 140), fill='#F1ECDC')
    d.line((36, 80, 190, 80), fill='#A9AD93', width=2)
    d.rectangle((0, 0, 28, 28), fill='#A9AD93')
    out, pal = quantize_full(im, 4, 0)
    rgb = _rgb(out)
    sage = min((p.hex for p in pal), key=lambda h: abs(sum(int(h[i:i + 2], 16) for i in (1, 3, 5)) - sum(SAGE)))
    ink = np.array([int(sage[i:i + 2], 16) for i in (1, 3, 5)])
    vein = (rgb[78:83, 40:185] == ink).all(-1)
    assert vein.any(0).mean() > 0.95


def test_separation_at_cleanup_0_rebuilds_the_faired_design():
    img, _, _ = _wobbly_disk()
    out, pal = quantize_full(img, 4, 0)
    layers = separate(out, [p.hex for p in pal])
    rgb = _rgb(out)
    stacked = np.zeros_like(rgb)
    covered = np.zeros(rgb.shape[:2], np.uint8)
    for hx, mask, _ in layers:
        alpha = np.asarray(mask)[:, :, 3] > 0
        stacked[alpha] = [int(hx[i:i + 2], 16) for i in (1, 3, 5)]
        covered += alpha.astype(np.uint8)
    assert covered.min() == 1 and covered.max() == 1
    assert np.array_equal(stacked, rgb)


def _labels_of(rgb, pal):
    """Ink index per pixel, in palette order, so kink is read off the flat image."""
    key = rgb[:, :, 0].astype(np.int32) * 65536 + rgb[:, :, 1].astype(np.int32) * 256 + rgb[:, :, 2]
    lab = np.full(rgb.shape[:2], -1, np.int64)
    for i, p in enumerate(pal):
        col = p.rgb
        k = col[0] * 65536 + col[1] * 256 + col[2]
        lab[key == k] = i
    return lab
