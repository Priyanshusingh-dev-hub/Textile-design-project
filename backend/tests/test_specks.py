"""Dots too small for a screen's mesh: counted, and optionally given to the
ink around them — the plates stay one ink per pixel."""
from io import BytesIO
from zipfile import ZipFile
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.core import store
from app.separation_engine.engine import clean_specks, dot_area, speck_report


def _mask(a):
    rgba = np.zeros((*a.shape, 4), np.uint8); rgba[:, :, 3] = a * np.uint8(255)
    return Image.fromarray(rgba)


def _a(m):
    return np.asarray(m.getchannel('A')) > 0


def _design():
    """Ground (ink 2) with a big shape (ink 1), dust of ink 1 in the ground,
    a 1px hairline of ink 1 and a lone dot of ink 2 inside the shape."""
    shape = np.zeros((60, 80), bool)
    shape[10:40, 10:40] = True
    shape[50, 60] = True                       # 1 px dot
    shape[52:54, 70:72] = True                 # 2x2 dot
    shape[5, 45:75] = True                     # 30 px hairline: long, not a dot
    shape[25, 25] = False                      # a ground dot inside the shape
    ground = ~shape
    ground[0:3, 0:3] = False                   # a bit of bare (transparent) corner
    return shape, ground


def test_dot_area_follows_the_print_resolution():
    assert dot_area(0, 300) == 0
    assert dot_area(0.2, 300) == 4             # 0.2 mm is 2.36 px across at 300 DPI
    assert dot_area(0.2, 600) > dot_area(0.2, 300)


def test_report_counts_only_the_small_islands():
    shape, ground = _design()
    rep = speck_report([_mask(shape), _mask(ground)], 4)
    assert rep == [(2, 5), (1, 1)]             # the two dots of ink 1; the one of ink 2


def test_clean_gives_each_dot_to_the_ink_around_it():
    shape, ground = _design()
    out = clean_specks([_mask(shape), _mask(ground)], 4)
    s, g = _a(out[0]), _a(out[1])
    assert not s[50, 60] and g[50, 60] and not s[52:54, 70:72].any()
    assert s[25, 25]                            # the ground dot joined the shape
    assert s[5, 45:75].all()                    # the hairline is kept
    assert (s[10:40, 10:40]).all()
    assert not (s & g).any()                    # one ink per pixel
    assert ((s | g) == (shape | ground)).all()  # nothing added or lost overall
    assert speck_report(out, 4) == [(0, 0), (0, 0)]


def test_off_changes_nothing():
    shape, ground = _design()
    masks = [_mask(shape), _mask(ground)]
    assert clean_specks(masks, 0) == masks


def test_a_shape_crossing_a_repeat_seam_is_not_a_dot():
    """On a seamless tile a small motif split by the seam is one shape on the
    cloth, not two dots — while the same motif on a plain design is dust."""
    tile = np.zeros((40, 40), bool)
    tile[20:22, 39] = True; tile[20:22, 0] = True   # a 2x2 motif across the left/right seam
    for y in range(0, 40, 4):
        tile[y, 20] = True                         # dust inside the tile
    out = _a(clean_specks([_mask(tile), _mask(~tile)], 4)[0])
    assert out[20:22, 39].all() and out[20:22, 0].all()
    assert not out[:, 20].any()                    # the dust is still cleaned
    plain = tile.copy(); plain[20:22, 0] = False    # no longer a repeat across that seam
    plain[0:3, 0:5] = True                          # (and the edges now differ)
    assert not _a(clean_specks([_mask(plain), _mask(~plain)], 4)[0])[20:22, 39].any()


def _layers(c):
    shape, ground = _design()
    return [{'id': store.save(_mask(shape)), 'name': 'Red', 'color': '#C0392B'},
            {'id': store.save(_mask(ground)), 'name': 'Cream', 'color': '#F4E8CC'}]


def test_specks_endpoint_reports_per_ink():
    c = TestClient(app)
    layers = _layers(c)
    r = c.post('/api/separation/specks', json={'layers': layers, 'min_dot_mm': 0.2}).json()
    assert r['max_area_px'] == 4
    assert [i['dots'] for i in r['inks']] == [2, 1]


def test_package_with_clean_films_and_says_so():
    c = TestClient(app)
    layers = _layers(c)
    z = ZipFile(BytesIO(c.post('/api/export/package', json={'layers': layers, 'min_dot_mm': 0.2}).content))
    film = np.asarray(Image.open(BytesIO(z.read('screens/Red.tif'))).convert('L'))[120:-120, 120:-120] < 128
    assert not film[50, 60] and film[25, 25] and film[5, 45:75].all()
    assert 'Tiny dots cleaned' in z.read('README.txt').decode()


def test_overlapping_bureau_screens_are_a_422():
    c = TestClient(app)
    a = np.ones((20, 20), bool)
    layers = [{'id': store.save(_mask(a)), 'color': '#000000'}, {'id': store.save(_mask(a)), 'color': '#FFFFFF'}]
    assert c.post('/api/separation/specks', json={'layers': layers}).status_code == 422
