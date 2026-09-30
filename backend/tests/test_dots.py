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


def _dotted_masks(k=3):
    from app.separation_engine import engine as S
    img = _photo()
    flat, pal = E.quantize_full(img, k)
    hexes = [c.hex for c in pal]
    return img, hexes, [m for _, m, _ in S.create(E.dither(img, hexes), hexes, cleanup=0)]


def test_at_a_whole_scale_every_dot_is_its_design_pixel():
    from app.separation_engine import engine as S
    _, hexes, masks = _dotted_masks()
    big = S.resize_masks(masks, (960, 720), dots=True, colours=hexes)
    alphas = np.stack([np.asarray(m.getchannel('A')) for m in big])
    assert set(np.unique(alphas)) <= {0, 255} and ((alphas > 0).sum(0) == 1).all()   # exclusive, no gaps
    for a, m in zip(alphas, masks):          # every 3x3 block is its native pixel
        assert np.array_equal(a, np.kron(np.asarray(m.getchannel('A')), np.ones((3, 3), np.uint8)))


def test_at_any_other_scale_the_dots_are_all_one_size_and_keep_the_shading():
    from app.separation_engine import engine as S
    img, hexes, masks = _dotted_masks()
    size = (796, 597)                          # x2.49: scaled dots would be 2 and 3 px by turns
    big = S.resize_masks(masks, size, dots=True, colours=hexes)
    label = np.argmax(np.stack([np.asarray(m.getchannel('A')) for m in big]), 0)
    d = S.dot_pixels(masks[0].size, size)
    assert d == 2
    # the ink only ever changes on the dot grid
    assert not (label[:, 1:] != label[:, :-1])[:, np.arange(label.shape[1] - 1) % d != d - 1].any()
    assert not (label[1:] != label[:-1])[np.arange(label.shape[0] - 1) % d != d - 1].any()
    shown = Image.fromarray(np.array([E.hex_rgb(h) for h in hexes], np.uint8)[label])
    native = E.seen_match(img, E.dither(img, hexes))[1]           # as the Reduce step showed it
    assert E.seen_match(img.resize(size, Image.LANCZOS), shown, radius=1.5 * d)[1] >= native - 2


def test_switching_to_dots_and_back_keeps_the_operators_inks(client):
    iid = _up(client, _photo())
    red = client.post('/api/colors/reduce', json={'image_id': iid, 'colors': 4}).json()
    edited = [p['hex'] for p in red['palette']][:3] + ['#1E2A4A']          # say ink 4 became a shelf ink
    on = client.post('/api/colors/dots', json={'image_id': iid, 'palette': edited, 'dots': True}).json()
    assert on['dots'] and {p['hex'] for p in on['palette']} <= set(edited) and on['similar'] == []
    off = client.post('/api/colors/dots', json={'image_id': iid, 'palette': edited, 'dots': False}).json()
    assert not off['dots'] and {p['hex'] for p in off['palette']} <= set(edited)
    img = Image.open(io.BytesIO(client.get(off['url']).content)).convert('RGB')
    assert {tuple(c) for c in np.asarray(img).reshape(-1, 3)} <= {tuple(E.hex_rgb(h)) for h in edited}   # flat, in these inks
    assert client.post('/api/colors/dots', json={'image_id': iid, 'palette': [], 'dots': True}).status_code == 422


def test_auto_mode_prints_as_dots_only_when_asked(client):
    iid = _up(client, _photo())
    flat = client.post('/api/auto', json={'image_id': iid, 'colors': 5, 'trial': True}).json()
    assert 'photographic' in {w['code'] for w in flat['warnings']} and not flat['dots']
    dotted = client.post('/api/auto', json={'image_id': iid, 'colors': 5, 'trial': True, 'dots': True, 'trap_px': 2}).json()
    codes = {w['code'] for w in dotted['warnings']}
    assert dotted['dots'] and dotted['settings']['dots']
    assert dotted['settings']['trap_px'] == 2          # as asked, so a re-run without dots gets it back
    assert not codes & {'photographic', 'tiny_dots', 'small_inks', 'similar_inks'}
    assert dotted['accuracy'] > flat['accuracy'] and dotted['tiny_dots'] is None
    z = zipfile.ZipFile(io.BytesIO(client.get(dotted['package_url']).content))
    assert 'Index separation' in z.read('README.txt').decode()
    # its colourway keeps the dots
    cw = client.post(f"/api/auto/{dotted['job_id']}/colourway", json={'colours': ['#112233'] * len(dotted['layers'])}).json()
    assert cw['settings']['dots']


def test_dots_are_read_from_a_caption_or_file_name():
    from app.bot_orders import parse_request
    assert parse_request('rose 30in 500m dots') == {'width_in': 30.0, 'meters': 500.0, 'dots': True}
    assert parse_request('Index separation please, 6 inks')['dots']
    assert 'dots' not in parse_request('chhoti bindiyan saaf karo, 6 inks')
    assert 'dots' not in parse_request('0.2 mm dots') and 'dots' not in parse_request('remove tiny dots')


@pytest.mark.parametrize('text,want', [
    ('rose 30in dots', True), ('no dots, 6 inks', False), ('dots hatao', False), ('without dots please', False),
    ('dots mat karo', False), ('bina dots ke', False), ('flat print 5 inks', False), ('dots off', False),
    ('index separation', True), ('6 inks', None),
])
def test_asking_not_to_print_as_dots_is_heard(text, want):
    from app.bot_orders import parse_request
    assert parse_request(text).get('dots') is want


def test_a_dotted_auto_job_with_the_dot_check_off_still_runs(client, tmp_path, monkeypatch):
    from app import auto as auto_mode
    cfg = auto_mode.load_config() | {'tiny_dot_mm': 0}
    monkeypatch.setattr(auto_mode, 'load_config', lambda: cfg)
    iid = _up(client, _photo())
    r = client.post('/api/auto', json={'image_id': iid, 'colors': 4, 'trial': True, 'dots': True})
    assert r.status_code == 200, r.text
    assert r.json()['tiny_dots'] is None
