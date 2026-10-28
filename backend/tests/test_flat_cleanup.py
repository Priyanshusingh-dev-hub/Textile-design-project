"""Flat reduce stays flat.

Studio does not run the mill spray / gradient / airbrush path. After the inks
are chosen, leftover micro-islands join the ink they touch. A thin stem, a
cluster of distinct dots, an exact 1px mark, a hard rectangle and a flat
interior stay. Separation at cleanup 0 rebuilds that reduced image.
"""
from pathlib import Path

import numpy as np
from PIL import Image

from app.color_engine.engine import _sweep_crumbs, hex_rgb, quantize_full
from app.models import ReduceRequest
from app.separation_engine.engine import create as separate

CREAM = np.array([244, 232, 204], np.uint8)
RED = np.array([192, 57, 43], np.uint8)
GREEN = np.array([30, 140, 70], np.uint8)
BLUE = np.array([42, 93, 168], np.uint8)
JUNK = np.array([210, 70, 55], np.uint8)   # a shade of red, not an ink of its own
APP = Path(__file__).resolve().parents[1] / 'app'
FRONT = Path(__file__).resolve().parents[2] / 'frontend' / 'src'


def _ink(centers, color):
    hit = [i for i, c in enumerate(centers) if np.array_equal(c, color)]
    assert hit, (color.tolist(), centers.tolist())
    return hit[0]


def test_studio_default_path_does_not_spray_or_gradient():
    """A normal Studio reduce is flat. Spray and gradient films are mill CLI only."""
    watched = (
        'routes/palette.py', 'routes/plates.py', 'routes/automation.py', 'routes/export.py',
        'routes/numbering.py', 'color_engine/engine.py', 'separation_engine/engine.py',
        'photo_batch.py', 'auto.py',
    )
    for rel in watched:
        text = (APP / rel).read_text(encoding='utf-8')
        assert 'run_spray' not in text and 'run_gradients' not in text, rel
        assert 'textile.spray' not in text and 'textile.gradients' not in text, rel
        assert 'import spray' not in text and 'import gradients' not in text, rel
    ui = '\n'.join(p.read_text(encoding='utf-8') for p in FRONT.rglob('*.tsx'))
    assert 'Gradient / tonal' not in ui and 'value="gradient"' not in ui
    assert ReduceRequest.model_fields['dots'].default is False
    # a smooth ramp becomes a few flat bands, not a speckled spray
    ramp = np.zeros((36, 90, 3), np.uint8)
    tone = np.linspace(30, 220, 90).astype(np.uint8)
    ramp[:] = tone[None, :, None]
    ramp[:, :, 1] = tone // 3
    out, pal = quantize_full(Image.fromarray(ramp), 4, 0)
    rgb = np.asarray(out.convert('RGB'))
    assert out.size == (90, 36)
    assert 1 <= len(pal) <= 4
    changes = int((rgb[18, 1:] != rgb[18, :-1]).any(-1).sum())
    assert changes <= 6, changes


def test_tiny_isolated_junk_merges_and_line_dot_and_interior_stay():
    h, w = 48, 90
    labels = np.zeros((h, w), np.int64)
    labels[5:36, 6:34] = 1                          # red field
    labels[4, 18] = 1                               # one-pixel jog on its top edge
    labels[10:12, 50:52] = 2                        # isolated 2x2 junk, sitting in the cream
    labels[40, 8:16] = 2                            # six-pixel stem of that same colour
    labels[16, 44:80] = 3                           # green line
    for y in (12, 20, 28):
        labels[y, 70] = 1                           # exact red dots, a column
    labels[22, 60] = 4                              # one exact blue dot
    for x in (48, 58, 68):
        labels[42, x:x + 2] = 4                     # clustered blue specks, not the exact centre
    centers = np.stack([CREAM, RED, JUNK, GREEN, BLUE])
    pixels = centers[labels].copy()
    pixels[4, 18] = (180, 40, 30)                   # the jog is not the red ink
    pixels[10:12, 50:52] = (208, 72, 58)
    pixels[40, 8:16] = (208, 72, 58)
    pixels[42, 48:50] = (48, 100, 176)
    pixels[42, 58:60] = (48, 100, 176)
    pixels[42, 68:70] = (48, 100, 176)
    out, cen = _sweep_crumbs(labels, centers, pixels)
    cream, red = _ink(cen, CREAM), _ink(cen, RED)
    green, blue, junk = _ink(cen, GREEN), _ink(cen, BLUE), _ink(cen, JUNK)
    assert np.all(out[10:12, 50:52] == cream)       # isolated junk joined the cream
    assert np.all(out[5:36, 6:34] == red)           # flat field, edges included, unchanged
    assert out[4, 18] == cream                      # the jog left the red
    assert np.all(out[40, 8:16] == junk)            # the stem kept its colour
    assert np.all(out[16, 44:80] == green)
    assert all(out[y, 70] == red for y in (12, 20, 28))
    assert out[22, 60] == blue
    assert all(np.all(out[42, x:x + 2] == blue) for x in (48, 58, 68))


def test_hard_rectangle_and_flat_interior_are_unchanged():
    a = np.full((90, 110, 3), CREAM, np.uint8)
    a[20:70, 15:80] = RED
    out, pal = quantize_full(Image.fromarray(a), 3, 0)
    rgb = np.asarray(out.convert('RGB'))
    assert rgb.shape[:2] == a.shape[:2]
    assert np.array_equal(rgb[20:70, 15:80], np.broadcast_to(RED, (50, 65, 3)))
    assert np.array_equal(rgb[:20], np.broadcast_to(CREAM, (20, 110, 3)))
    assert len(pal) == 2


def test_separation_cleanup_0_rebuilds_the_reduced_image():
    a = np.full((64, 80, 3), CREAM, np.uint8)
    a[8:40, 6:30] = RED
    a[48, 4:70] = GREEN
    a[12, 50] = RED
    a[20:24, 50:54] = (205, 68, 50)                 # a near-red crumb the sweep may absorb
    out, pal = quantize_full(Image.fromarray(a), 4, 0)
    rgb = np.asarray(out.convert('RGB'))
    layers = separate(out, [p.hex for p in pal], 0)
    recon = np.zeros_like(rgb)
    for hx, mask, _ in layers:
        recon[np.asarray(mask)[:, :, 3] > 0] = hex_rgb(hx)
    assert np.array_equal(recon, rgb)
    assert int((rgb[48, 4:70] == GREEN).all(-1).sum()) >= 64
    assert (rgb[12, 50] == RED).all()
