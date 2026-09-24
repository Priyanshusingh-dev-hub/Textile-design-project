"""Small inks: each costs a screen; removing one moves each of its pixels to
the remaining ink closest to its original colour."""
import numpy as np
from io import BytesIO
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from app.main import app
from app.color_engine.engine import quantize_full, small_inks, drop_inks, hex_rgb


def _design():
    """Navy ground, a big red disc, a small patch in a red a shade off (a
    near-duplicate small ink) and a tiny yellow star (small and unique)."""
    d = Image.new('RGB', (400, 300), '#1E2A4A'); dr = ImageDraw.Draw(d)
    dr.ellipse((50, 50, 250, 250), fill='#C0392B')
    dr.rectangle((120, 120, 150, 150), fill='#B8362A')    # 0.8%: barely different red
    dr.rectangle((300, 40, 316, 56), fill='#F1C40F')      # 0.24%: the only yellow
    return d


def test_report_drops_the_near_duplicate_and_keeps_the_unique_ink():
    img = _design()
    red, pal = quantize_full(img, 4, 0)
    hexes = [p.hex for p in pal]
    rep = small_inks(img, red, hexes)
    by_hex = {c['hex']: c for c in rep['inks']}
    yellow = next(h for h in hexes if hex_rgb(h)[2] < 60 and hex_rgb(h)[0] > 200)
    assert by_hex[yellow]['distinct']                     # nothing else is like it: kept
    assert [hexes[i] for i in rep['drop']] and yellow not in [hexes[i] for i in rep['drop']]
    assert rep['accuracy'] is not None


def test_locked_inks_are_never_offered():
    img = _design()
    red, pal = quantize_full(img, 4, 0)
    hexes = [p.hex for p in pal]
    rep = small_inks(img, red, hexes, locked=hexes)
    assert rep['inks'] == []


def test_drop_moves_pixels_to_the_closest_remaining_ink():
    img = _design()
    red, pal = quantize_full(img, 4, 0)
    hexes = [p.hex for p in pal]
    rep = small_inks(img, red, hexes)
    gone = [hexes[i] for i in rep['drop']]
    out = np.asarray(drop_inks(img, red, hexes, gone))
    colours = {'#%02X%02X%02X' % tuple(c) for c in np.unique(out[..., :3].reshape(-1, 3), axis=0)}
    assert not colours & set(gone)
    assert colours <= set(hexes)
    assert tuple(out[135, 135, :3]) == tuple(hex_rgb(next(h for h in hexes if h not in gone and hex_rgb(h)[0] > 150 and hex_rgb(h)[1] < 100)))


def _upload(c, img):
    buf = BytesIO(); img.save(buf, 'PNG')
    return c.post('/api/image/upload', files={'file': ('d.png', buf.getvalue(), 'image/png')}).json()


def test_api_small_then_drop():
    c = TestClient(app)
    up = _upload(c, _design())
    red = c.post('/api/colors/reduce', json={'image_id': up['image_id'], 'colors': 4, 'smoothing': 0}).json()
    pal = [p['hex'] for p in red['palette']]
    rep = c.post('/api/colors/small', json={'image_id': red['image_id'], 'source_id': up['image_id'],
                                            'palette': pal}).json()
    drop = [pal[i] for i in rep['drop']]
    r = c.post('/api/colors/drop', json={'image_id': red['image_id'], 'source_id': up['image_id'],
                                         'palette': pal, 'drop': drop, 'smoothing': 0})
    assert r.status_code == 200
    body = r.json()
    assert [p['hex'] for p in body['palette']] == [h for h in pal if h not in drop]
    assert abs(sum(p['coverage'] for p in body['palette']) - 100) < 0.1


def test_drop_every_ink_is_a_422():
    c = TestClient(app)
    up = _upload(c, _design())
    red = c.post('/api/colors/reduce', json={'image_id': up['image_id'], 'colors': 3, 'smoothing': 0}).json()
    pal = [p['hex'] for p in red['palette']]
    r = c.post('/api/colors/drop', json={'image_id': red['image_id'], 'source_id': up['image_id'],
                                         'palette': pal, 'drop': pal})
    assert r.status_code == 422
