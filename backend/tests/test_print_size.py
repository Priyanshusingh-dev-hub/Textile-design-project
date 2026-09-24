"""Printing a design bigger than its own pixels: the screens are redrawn at the
print size with smooth edges, and still carry exactly one ink per pixel."""
import io
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.main import app, MAX_PRINT_PX
from app.separation_engine.engine import create, resize_masks

S = 4   # enlargement used by the engine tests


def _scene(n=90, scale=1):
    """Shapes plus 1px lines, drawn at `scale` times the size."""
    k = scale
    im = Image.new('RGB', (n * k, n * k), '#EFE3C8'); d = ImageDraw.Draw(im)
    d.ellipse((5 * k, 5 * k, 45 * k, 45 * k), fill='#C0392B')
    d.ellipse((18 * k, 18 * k, 32 * k, 32 * k), fill='#EFE3C8')          # a hole
    d.polygon([(55 * k, 5 * k), (85 * k, 20 * k), (60 * k, 45 * k)], fill='#2A5DA8')
    d.line((5 * k, 60 * k, 85 * k, 62 * k), fill='#1A1A1A', width=k)       # 1px, near-horizontal
    d.line((50 * k, 50 * k, 85 * k, 85 * k), fill='#1A1A1A', width=k)      # 1px diagonal
    return im


def _masks(im, palette=('#EFE3C8', '#C0392B', '#2A5DA8', '#1A1A1A')):
    return [m for _, m, _ in create(im, list(palette), 0)]


def _labels(masks):
    a = np.stack([np.asarray(m)[:, :, 3] > 0 for m in masks])
    return a.sum(0), a.argmax(0)


def test_every_pixel_keeps_exactly_one_ink_when_enlarged():
    masks = _masks(_scene())
    big = resize_masks(masks, (90 * S, 90 * S))
    count, _ = _labels(big)
    assert big[0].size == (90 * S, 90 * S)
    assert (count == 1).all()


def test_own_size_is_untouched():
    masks = _masks(_scene())
    assert all(a is b for a, b in zip(resize_masks(masks, masks[0].size), masks))


def test_enlarging_keeps_each_ink_the_same_share_of_the_design():
    masks = _masks(_scene())
    big = resize_masks(masks, (90 * S, 90 * S))
    for m, b in zip(masks, big):
        before = (np.asarray(m)[:, :, 3] > 0).mean()
        after = (np.asarray(b)[:, :, 3] > 0).mean()
        assert abs(before - after) < 0.01


def test_enlarged_edges_are_truer_than_plain_pixel_enlargement():
    """Against the same shapes drawn at the big size, the redrawn screens
    disagree on fewer pixels than blowing the pixels up would."""
    small, truth = _scene(), _scene(scale=S)
    masks = _masks(small)
    _, smooth = _labels(resize_masks(masks, truth.size))
    _, blocky = _labels([m.resize(truth.size, Image.NEAREST) for m in masks])
    _, want = _labels(_masks(truth))
    assert (smooth != want).sum() < 0.85 * (blocky != want).sum()


def test_thin_lines_survive_enlargement():
    masks = _masks(_scene())
    line = np.asarray(masks[3])[:, :, 3] > 0
    big = np.asarray(resize_masks(masks, (90 * S, 90 * S))[3])[:, :, 3] > 0
    # every row the 1px lines crossed still has ink in it once enlarged
    rows = np.flatnonzero(line.any(1))
    assert all(big[r * S:(r + 1) * S].any() for r in rows)


def test_transparent_ground_stays_uninked():
    im = Image.new('RGBA', (60, 60), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((10, 10, 50, 50), fill=(192, 57, 43, 255))
    masks = [m for _, m, _ in create(im, ['#C0392B'], 0)]
    big = np.asarray(resize_masks(masks, (240, 240))[0])[:, :, 3] > 0
    assert not big[:20].any() and not big[:, :20].any()     # corners stay blank
    assert big[120, 120]


def test_overlapping_bureau_channels_are_resized_one_by_one():
    """A pre-separated PSD may overlap on purpose; enlarging must keep that,
    not force one ink per pixel on the bureau's work."""
    def ch(box):
        a = np.zeros((40, 40, 4), np.uint8); y0, x0, y1, x1 = box; a[y0:y1, x0:x1, 3] = 255
        return Image.fromarray(a)
    a, b = ch((0, 0, 40, 22)), ch((0, 18, 40, 40))          # 4 px of trap
    big = resize_masks([a, b], (160, 160))
    both = (np.asarray(big[0])[:, :, 3] > 127) & (np.asarray(big[1])[:, :, 3] > 127)
    assert both.any()


# ---- through the API --------------------------------------------------------

@pytest.fixture(scope='module')
def separated():
    c = TestClient(app)
    b = io.BytesIO(); _scene().save(b, 'PNG')
    info = c.post('/api/image/upload', files={'file': ('a.png', b.getvalue(), 'image/png')}).json()
    red = c.post('/api/colors/reduce', json={'image_id': info['image_id'], 'colors': 4, 'smoothing': 0}).json()
    lay = c.post('/api/separation/create', json={'image_id': red['image_id'],
                 'palette': [p['hex'] for p in red['palette']]}).json()['layers']
    return c, [{'id': l['id'], 'name': f'Ink {i + 1}', 'color': l['color']} for i, l in enumerate(lay)]


def test_films_are_drawn_at_the_chosen_print_width(separated):
    c, layers = separated
    z = zipfile.ZipFile(io.BytesIO(c.post('/api/export/package', json={
        'layers': layers, 'width_in': 1.2, 'reg_marks': False}).content))
    film = Image.open(io.BytesIO(z.read('screens/Ink-1.tif')))
    assert film.size == (360, 360)                          # 1.2 in at 300 DPI
    assert Image.open(io.BytesIO(z.read('proof.png'))).size == (360, 360)
    assert 'Print size: 1.20 x 1.20 in' in z.read('README.txt').decode()
    films = [np.asarray(Image.open(io.BytesIO(z.read(f'screens/Ink-{i}.tif')))) < 128 for i in range(1, 5)]
    assert (sum(f.astype(int) for f in films) <= 1).all()   # still never two inks on one spot


def test_no_width_is_exactly_the_old_package(separated):
    c, layers = separated
    plain = zipfile.ZipFile(io.BytesIO(c.post('/api/export/package', json={'layers': layers}).content))
    same = zipfile.ZipFile(io.BytesIO(c.post('/api/export/package', json={
        'layers': layers, 'width_in': 90 / 300}).content))       # its own width
    for n in plain.namelist():
        if n.endswith('.png'):
            assert plain.read(n) == same.read(n), n


def test_a_print_too_large_to_render_is_a_clear_4xx(separated):
    c, layers = separated
    r = c.post('/api/export/package', json={'layers': layers, 'width_in': 200})
    assert r.status_code == 422
    assert 'vector SVG' in r.json()['detail']
    assert f'{MAX_PRINT_PX // 1_000_000} MP' in r.json()['detail']


def test_preview_at_print_width(separated):
    c, layers = separated
    r = c.post('/api/separation/preview', json={'layers': [{'id': l['id'], 'color': l['color']} for l in layers],
                                                 'width_in': 1.2}).json()
    assert (r['width'], r['height']) == (360, 360)


def test_svg_opens_at_its_print_size(separated):
    c, layers = separated
    svg = c.post('/api/export/svg', json={'layers': layers, 'width_in': 12}).text
    assert 'width="12in"' in svg and 'height="12in"' in svg and 'viewBox="0 0 90 90"' in svg
