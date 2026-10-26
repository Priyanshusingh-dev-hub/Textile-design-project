"""The local review plan flags uncertainty and does not edit the design."""
import io

import numpy as np
from PIL import Image, ImageFilter
from fastapi.testclient import TestClient

from app.color_engine.engine import quantize_full
from app.core import store
from app.core.structure_review import plan
from app.main import app

CREAM = (244, 232, 204)
RED = (192, 57, 43)
GREEN = (30, 140, 70)


def _png(im):
    buf = io.BytesIO()
    im.save(buf, 'PNG')
    return buf.getvalue()


def _aa_square():
    base = np.full((90, 100, 3), CREAM, np.uint8)
    base[25:65, 25:75] = RED
    mask = np.zeros((90, 100), np.float32)
    mask[25:65, 25:75] = 1
    m = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)))
    m = m.astype(np.float32) / 255
    aa = (np.array(CREAM) * (1 - m[:, :, None]) + np.array(RED) * m[:, :, None]).round().astype(np.uint8)
    return Image.fromarray(aa)


def test_a_fringe_ink_is_flagged_and_the_pixels_stay():
    src = _aa_square()
    reduced, pal = quantize_full(src, 3, 0)
    assert len(pal) == 3
    before_s = np.asarray(src)
    before_r = np.asarray(reduced)
    report = plan(src, reduced)
    assert report['provider'] == 'local'
    assert report['applies_pixels'] is False
    assert report['model'] is None
    rims = [i for i in report['issues'] if i['code'] == 'blend_rim']
    assert rims and rims[0]['action'] == 'none'
    assert rims[0]['hex'] not in ('#F4E8CC', '#C0392B')
    assert np.array_equal(np.asarray(src), before_s)
    assert np.array_equal(np.asarray(reduced), before_r)


def test_a_solid_third_colour_is_not_called_a_fringe():
    a = np.full((80, 100, 3), CREAM, np.uint8)
    a[10:70, 8:40] = RED
    a[10:70, 55:90] = GREEN
    src = Image.fromarray(a)
    reduced, _ = quantize_full(src, 3, 0)
    report = plan(src, reduced)
    assert not any(i['code'] == 'blend_rim' for i in report['issues'])
    assert report['needs_human'] is False


def test_a_thin_colour_painted_away_is_named_and_not_restored():
    a = np.full((40, 60, 3), CREAM, np.uint8)
    a[20, 10:50] = RED
    src = Image.fromarray(a)
    wiped = Image.fromarray(np.full_like(a, CREAM))
    before = np.asarray(wiped)
    report = plan(src, wiped)
    missing = [i for i in report['issues'] if i['code'] == 'thin_colour_missing']
    assert missing and missing[0]['hex'] == '#C0392B'
    assert missing[0]['region']['w'] >= 30
    assert np.array_equal(np.asarray(wiped), before)


def test_kept_exact_dots_are_listed_for_review():
    a = np.full((48, 64, 3), CREAM, np.uint8)
    a[8:28, 8:28] = RED
    a[10, 40] = RED
    a[20, 50] = RED
    src = Image.fromarray(a)
    reduced, _ = quantize_full(src, 4, 0)
    report = plan(src, reduced)
    specks = next(i for i in report['issues'] if i['code'] == 'review_specks')
    assert specks['count'] == 2
    assert len(specks['samples']) == 2
    assert report['needs_human'] is True


def test_a_size_mismatch_stops_before_any_pixel_comparison():
    src = Image.fromarray(np.full((20, 20, 3), CREAM, np.uint8))
    reduced = Image.fromarray(np.full((20, 30, 3), RED, np.uint8))
    report = plan(src, reduced)
    assert [i['code'] for i in report['issues']] == ['size_mismatch']
    assert report['needs_human'] is True


def test_the_review_route_writes_no_new_image():
    a = np.full((36, 40, 3), CREAM, np.uint8)
    a[8:28, 8:20] = RED
    c = TestClient(app)
    up = c.post('/api/image/upload', files={'file': ('flat.png', _png(Image.fromarray(a)), 'image/png')}).json()
    red = c.post('/api/colors/reduce', json={'image_id': up['image_id'], 'colors': 3, 'smoothing': 0}).json()
    before = {p.name for p in store.ROOT.glob('*.png')}
    got = c.post('/api/colors/structure-review', json={
        'source_id': up['image_id'], 'reduced_id': red['image_id'],
    })
    assert got.status_code == 200, got.text
    body = got.json()
    assert body['applies_pixels'] is False
    assert body['source_id'] == up['image_id']
    assert {p.name for p in store.ROOT.glob('*.png')} == before
