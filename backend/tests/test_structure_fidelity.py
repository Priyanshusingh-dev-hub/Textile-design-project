"""Where a flat design's geometry first changes.

Measured on synthetic fixtures (no production artwork in this repo): upload/decode
is lossless; with smoothing off and separation cleanup off, the first loss was
inside reduce. A 1px line on a large canvas never became an ink (the k-means
sample strides past it), and a hard 1px dot of an ink that did exist was erased
by the majority filter. These lock both, and the separation default that used
to median-blur that line.
"""
import io

import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

from app.color_engine.engine import _MAX_ANALYSIS_PX, _quantize_large, quantize_full
from app.main import app
from app.separation_engine.engine import create as separate

CREAM = (244, 232, 204)
RED = (192, 57, 43)
BLUE = (42, 93, 168)
GREEN = (30, 140, 70)


def _near(rgb, color, tol=40):
    return np.abs(rgb.astype(int) - np.array(color)).sum(-1) <= tol


def _png(im):
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    return buf.getvalue()


def test_decode_roundtrip_keeps_pixels_and_alpha():
    a = np.zeros((40, 50, 4), np.uint8)
    a[:, :, :3] = CREAM
    a[5:30, 8:40] = (*RED, 255)
    a[10, 10:30] = (*BLUE, 255)
    im = Image.fromarray(a, 'RGBA')
    back = Image.open(io.BytesIO(_png(im)))
    assert np.array_equal(np.asarray(back), a)


def test_a_1px_vertical_line_keeps_its_ink_when_the_sample_stride_is_coarse():
    """900px on a side: the stride sample used to miss this column, and reduce
    returned only cream + the horizontal line. 0 of 900 red pixels survived."""
    n = 900
    a = np.full((n, n, 3), CREAM, np.uint8)
    a[:, n // 5] = RED
    a[n // 3, :] = GREEN
    out, pal = quantize_full(Image.fromarray(a), 6, 0)
    rgb = np.asarray(out.convert('RGB'))
    assert any(p.hex == '#C0392B' for p in pal), [p.hex for p in pal]
    assert int(_near(rgb[:, n // 5], RED).sum()) >= n - 2
    assert int(_near(rgb[n // 3], GREEN).sum()) >= n - 2


def test_proxy_quantize_still_keeps_a_full_res_1px_line():
    """The large-image path builds the palette on a BOX proxy. A 1px line does
    not survive that average; it has to be put back from the full image."""
    n = 96
    a = np.full((n, n, 3), CREAM, np.uint8)
    a[:, 20] = RED
    a[:, 60:62] = BLUE
    opq = np.ones((n, n), bool)
    assert n * n < _MAX_ANALYSIS_PX
    labels, centers, counts, _, _kept = _quantize_large(a, opq, 6, cap=400)
    reds = [i for i, c in enumerate(centers) if _near(c.reshape(1, 3), RED)[0] and counts[i] > 0]
    assert reds, centers.tolist()
    assert int((labels[:, 20] == reds[0]).sum()) >= n - 2


def test_exact_1px_dots_of_a_real_ink_are_kept_and_counted():
    a = np.full((100, 140, 3), CREAM, np.uint8)
    a[20:55, 15:50] = RED
    dots = []
    for y in range(10, 90, 8):
        for x in range(70, 130, 8):
            a[y, x] = RED
            dots.append((y, x))
    out, pal = quantize_full(Image.fromarray(a), 4, 0)
    rgb = np.asarray(out.convert('RGB'))
    kept = sum(1 for y, x in dots if _near(rgb[y, x], RED))
    assert kept == len(dots)
    assert out.info['review_specks'] == len(dots)
    assert any(p.hex == '#C0392B' for p in pal)


def test_a_single_exact_dot_is_kept_when_its_ink_exists():
    a = np.full((80, 80, 3), CREAM, np.uint8)
    a[20:40, 20:40] = GREEN
    a[60, 60] = GREEN
    out, _ = quantize_full(Image.fromarray(a), 4, 0)
    rgb = np.asarray(out.convert('RGB'))
    assert _near(rgb[60, 60], GREEN)
    assert out.info['review_specks'] >= 1


def test_scan_grain_is_not_kept_as_a_field_of_exact_dots():
    """±18 RGB noise already left a few dozen 1px islands after the majority
    filter (measured at 24 before this change). Keeping exact dots must not
    turn that field into a speckle texture."""
    rng = np.random.RandomState(0)
    a = np.zeros((80, 80, 3), np.uint8)
    a[:, :40] = (200, 60, 60)
    a[:, 40:] = CREAM
    a = np.clip(a.astype(int) + rng.randint(-18, 19, a.shape), 0, 255).astype(np.uint8)
    out, _ = quantize_full(Image.fromarray(a), 3, 0)
    assert out.info['review_specks'] < 40


def test_a_1px_gap_between_two_shapes_stays_open():
    a = np.full((80, 120, 3), CREAM, np.uint8)
    a[10:70, 10:40] = RED
    a[10:70, 41:71] = RED
    out, _ = quantize_full(Image.fromarray(a), 4, 0)
    rgb = np.asarray(out.convert('RGB'))
    assert int(_near(rgb[10:70, 40], CREAM).sum()) == 60


def test_transparent_pixels_stay_transparent_and_the_opaque_shape_stays():
    a = np.zeros((60, 70, 4), np.uint8)
    a[:, :, :3] = CREAM
    a[10:50, 10:50, :3] = RED
    a[10:50, 10:50, 3] = 255
    a[30, 30, 3] = 0
    out, _ = quantize_full(Image.fromarray(a, 'RGBA'), 4, 0)
    alpha = np.asarray(out)[:, :, 3] >= 128
    expect = np.zeros((60, 70), bool)
    expect[10:50, 10:50] = True
    expect[30, 30] = False
    assert np.array_equal(alpha, expect)


def test_separation_defaults_to_off_so_a_1px_line_is_not_median_blurred():
    a = np.full((48, 64, 3), CREAM, np.uint8)
    a[:, 20] = RED
    im = Image.fromarray(a)
    pal = ['#F4E8CC', '#C0392B']
    raw = separate(im, pal)
    blurred = separate(im, pal, cleanup=2)
    red_raw = np.asarray(raw[1][1])[:, :, 3] > 0
    red_blur = np.asarray(blurred[1][1])[:, :, 3] > 0
    assert int(red_raw[:, 20].sum()) == 48
    assert int(red_blur[:, 20].sum()) < 48


def test_reduce_reports_the_kept_dots_and_separation_does_not_drop_them():
    a = np.full((48, 64, 3), CREAM, np.uint8)
    a[8:28, 8:28] = RED
    a[10, 40] = RED
    a[20, 50] = RED
    c = TestClient(app)
    up = c.post('/api/image/upload', files={'file': ('dots.png', _png(Image.fromarray(a)), 'image/png')}).json()
    red = c.post('/api/colors/reduce', json={'image_id': up['image_id'], 'colors': 4, 'smoothing': 0}).json()
    assert red['review_specks'] == 2
    sep = c.post('/api/separation/create', json={
        'image_id': red['image_id'], 'palette': [p['hex'] for p in red['palette']],
    }).json()
    # cleanup defaults to 0: both dots are still on the red plate
    from app.core import store
    red_layer = next(l for l in sep['layers'] if l['color'].upper() == '#C0392B')
    mask = np.asarray(store.load(red_layer['id']))[:, :, 3] > 0
    assert mask[10, 40] and mask[20, 50]


def test_diagonal_exact_stipple_is_kept_and_counted():
    a = np.full((90, 90, 3), CREAM, np.uint8)
    dots = []
    for i in range(8, 80, 6):
        a[i, i] = RED
        a[i, 80 - i] = RED
        dots += [(i, i), (i, 80 - i)]
    out, pal = quantize_full(Image.fromarray(a), 4, 0)
    rgb = np.asarray(out.convert('RGB'))
    assert sum(1 for y, x in dots if _near(rgb[y, x], RED)) == len(dots)
    assert out.info['review_specks'] == len(dots)
    assert any(p.hex == '#C0392B' for p in pal)


def test_a_connected_diagonal_line_keeps_its_ink():
    n = 80
    a = np.full((n, n, 3), CREAM, np.uint8)
    for i in range(10, 70):
        a[i, i] = (20, 20, 20)
    out, pal = quantize_full(Image.fromarray(a), 4, 0)
    rgb = np.asarray(out.convert('RGB')).astype(int)
    dark = sum(1 for i in range(10, 70) if rgb[i, i].sum() < 120)
    assert dark >= 58
    assert len(pal) >= 2


def test_a_flat_motif_is_unchanged():
    a = np.full((60, 60, 3), CREAM, np.uint8)
    a[10:50, 10:50] = RED
    a[22:38, 22:38] = GREEN
    out, _ = quantize_full(Image.fromarray(a), 4, 0)
    assert np.array_equal(np.asarray(out.convert('RGB')), a)
    assert out.info['review_specks'] == 0


def test_two_separate_colours_stay_two_inks():
    """A pair about ΔE 10 apart, drawn as two solid shapes, is two inks.
    Asking for them to merge would be a later, explicit operator step."""
    a = np.full((80, 100, 3), CREAM, np.uint8)
    a[15:65, 10:40] = (30, 80, 40)
    a[15:65, 60:90] = (46, 110, 55)
    out, pal = quantize_full(Image.fromarray(a), 3, 0)
    assert len(pal) == 3
    rgb = np.asarray(out.convert('RGB'))
    assert _near(rgb[40, 20], (30, 80, 40), tol=30)
    assert _near(rgb[40, 70], (46, 110, 55), tol=30)


def test_a_smooth_gradient_does_not_leave_exact_dots():
    a = np.zeros((40, 80, 3), np.uint8)
    for x in range(80):
        t = x / 79
        a[:, x] = (np.array(CREAM) * (1 - t) + np.array(RED) * t).astype(np.uint8)
    out, pal = quantize_full(Image.fromarray(a), 4, 0)
    assert len(pal) == 4
    assert out.info['review_specks'] == 0


def test_an_anti_aliased_edge_at_the_true_ink_count_does_not_add_a_fringe_ink():
    """A hard red square whose edge was blurred. At 2 inks the fringe snaps to
    red or cream (no muddy third ink). Asking for a spare ink can still spend
    it on that fringe; that case is flagged by the review plan, not deleted."""
    from PIL import ImageFilter
    base = np.full((90, 100, 3), CREAM, np.uint8)
    base[25:65, 25:75] = RED
    mask = np.zeros((90, 100), np.float32)
    mask[25:65, 25:75] = 1
    m = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)))
    m = m.astype(np.float32) / 255
    aa = (np.array(CREAM) * (1 - m[:, :, None]) + np.array(RED) * m[:, :, None]).round().astype(np.uint8)
    out, pal = quantize_full(Image.fromarray(aa), 2, 0)
    rgb = np.asarray(out.convert('RGB'))
    assert len(pal) == 2
    core = np.zeros((90, 100), bool)
    core[30:60, 30:70] = True
    assert _near(rgb, RED)[core].mean() == 1


def test_separation_of_the_reduced_image_rebuilds_it():
    a = np.full((48, 64, 3), CREAM, np.uint8)
    a[8:40, 8:28] = RED
    a[:, 40] = (20, 20, 20)
    out, pal = quantize_full(Image.fromarray(a), 4, 0)
    hexes = [p.hex for p in pal]
    layers = separate(out, hexes)
    stacked = np.zeros(np.asarray(out).shape[:2], np.uint8)
    rebuilt = np.zeros((*stacked.shape, 3), np.uint8)
    for hx, mask, _cov in layers:
        hit = np.asarray(mask)[:, :, 3] > 0
        stacked += hit
        rebuilt[hit] = [int(hx[i:i + 2], 16) for i in (1, 3, 5)]
    assert stacked.min() == 1 and stacked.max() == 1
    assert np.array_equal(rebuilt, np.asarray(out.convert('RGB')))


def test_reduce_leaves_the_uploaded_image_byte_for_pixel():
    a = np.full((40, 50, 3), CREAM, np.uint8)
    a[10:30, 8:20] = RED
    a[15, 30:45] = (20, 20, 20)
    c = TestClient(app)
    up = c.post('/api/image/upload', files={'file': ('motif.png', _png(Image.fromarray(a)), 'image/png')}).json()
    from app.core import store
    before = np.asarray(store.load(up['image_id']))
    c.post('/api/colors/reduce', json={'image_id': up['image_id'], 'colors': 4, 'smoothing': 0})
    after = np.asarray(store.load(up['image_id']))
    assert np.array_equal(before, after)


def test_hard_square_outline_survives_reduce():
    a = np.full((70, 70, 3), CREAM, np.uint8)
    a[15:55, 15] = (20, 20, 20)
    a[15:55, 54] = (20, 20, 20)
    a[15, 15:55] = (20, 20, 20)
    a[54, 15:55] = (20, 20, 20)
    a[20:50, 20:50] = RED
    out, pal = quantize_full(Image.fromarray(a), 4, 0)
    rgb = np.asarray(out.convert('RGB')).astype(int)
    line = np.zeros((70, 70), bool)
    line[15:55, 15] = line[15:55, 54] = line[15, 15:55] = line[54, 15:55] = True
    dark = rgb.sum(-1) < 120
    assert dark[line].mean() > 0.9
    assert len(pal) >= 2
