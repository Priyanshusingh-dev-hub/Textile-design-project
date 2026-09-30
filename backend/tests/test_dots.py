"""Index separation ("print as dots"): photo-like shading placed as dots of the
inks, one ink per pixel, enlarged pixel for pixel, never smoothed or cleaned."""
import io
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageFilter

from app.color_engine import engine as E
from app.main import app


@pytest.fixture(scope='module')
def client():
    return TestClient(app)


def _photo():
    """Smooth shading, the kind flat inks print as bands."""
    yy, xx = np.mgrid[0:240, 0:320]
    img = np.stack([80 + 150 * xx / 320, 60 + 160 * yy / 240, 200 - 120 * xx / 320], -1)
    return Image.fromarray(img.clip(0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(3))


def _up(client, img):
    b = io.BytesIO(); img.save(b, 'PNG')
    return client.post('/api/image/upload', files={'file': ('p.png', b.getvalue(), 'image/png')}).json()['image_id']


def test_dots_use_only_the_inks_and_look_closer_than_flat_areas():
    img = _photo()
    flat, pal = E.quantize_full(img, 4)
    hexes = [c.hex for c in pal]
    dotted = E.dither(img, hexes)
    colours = {tuple(c) for c in np.asarray(dotted.convert('RGB')).reshape(-1, 3)}
    assert colours <= {tuple(E.hex_rgb(h)) for h in hexes}                    # one ink per pixel
    assert E.seen_match(img, dotted)[1] > E.seen_match(img, flat)[1] + 5      # the shading comes back


def test_transparency_carries_no_dots():
    rgba = np.zeros((60, 80, 4), np.uint8); rgba[..., :3] = 120; rgba[10:50, 10:70, 3] = 255
    out = np.asarray(E.dither(Image.fromarray(rgba), ['#000000', '#FFFFFF']))
    assert (out[..., 3][rgba[..., 3] == 0] == 0).all() and (out[..., 3][rgba[..., 3] == 255] == 255).all()


def test_a_dotted_design_goes_from_reduce_to_films_without_being_smoothed(client):
    iid = _up(client, _photo())
    red = client.post('/api/colors/reduce', json={'image_id': iid, 'colors': 4, 'dots': True}).json()
    assert red['dots'] and abs(sum(p['coverage'] for p in red['palette']) - 100) < 0.1
    flat = client.post('/api/colors/reduce', json={'image_id': iid, 'colors': 4}).json()
    assert red['accuracy'] > flat['accuracy']
    again = client.post('/api/colors/accuracy', json={'image_id': iid, 'palette': [p['hex'] for p in red['palette']],
                                                      'reduced_id': red['image_id'], 'dots': True}).json()
    assert again['accuracy'] == red['accuracy']
    layers = client.post('/api/separation/create', json={'image_id': red['image_id'],
                                                         'palette': [p['hex'] for p in red['palette']]}).json()['layers']
    body = {'layers': [{'id': l['id'], 'name': l['name'], 'color': l['color']} for l in layers],
            'width_in': 320 * 3 / 300, 'dots': True, 'min_dot_mm': 0.3}          # 3x: each dot a 3x3 square
    z = zipfile.ZipFile(io.BytesIO(client.post('/api/export/package', json=body).content))
    assert 'Index separation: the inks are dots, each 0.25 mm square' in z.read('README.txt').decode()
    for flag in ({'trap_px': 1}, {'vector': True}):
        r = client.post('/api/export/package', json=body | flag)
        assert r.status_code == 422


def test_dots_are_enlarged_as_squares_and_stay_one_ink_per_pixel():
    from app.separation_engine import engine as S
    img = _photo()
    flat, pal = E.quantize_full(img, 3)
    dotted = E.dither(img, [c.hex for c in pal])
    masks = [m for _, m, _ in S.create(dotted, [c.hex for c in pal], cleanup=0)]
    big = S.resize_masks(masks, (960, 720), dots=True)
    alphas = np.stack([np.asarray(m.getchannel('A')) for m in big])
    assert set(np.unique(alphas)) <= {0, 255} and ((alphas > 0).sum(0) == 1).all()   # exclusive, no gaps
    for a, m in zip(alphas, masks):          # every 3x3 block is its native pixel
        assert np.array_equal(a, np.kron(np.asarray(m.getchannel('A')), np.ones((3, 3), np.uint8)))
