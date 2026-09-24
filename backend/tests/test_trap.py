"""Trap: lighter inks spread under darker neighbours on the films only."""
from io import BytesIO
from zipfile import ZipFile
import numpy as np
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from app.main import app
from app.color_engine.engine import quantize_full
from app.separation_engine.engine import create, trap, press_lightness, MAX_TRAP

LIGHT, DARK = '#F2D16B', '#1E2A4A'


def _mask(a):
    rgba = np.zeros((*a.shape, 4), np.uint8); rgba[:, :, 3] = a * np.uint8(255)
    return Image.fromarray(rgba)


def _alpha(m):
    return np.asarray(m.convert('RGBA'))[:, :, 3] > 0


def _two_inks():
    """Light square left, dark square right, touching; bare cloth around."""
    light = np.zeros((40, 60), bool); dark = np.zeros((40, 60), bool)
    light[10:30, 10:30] = True; dark[10:30, 30:50] = True
    return light, dark


def test_off_returns_the_films_untouched():
    light, dark = _two_inks()
    masks = [_mask(light), _mask(dark)]
    assert trap(masks, [LIGHT, DARK], 0) == masks


def test_light_spreads_under_dark_and_nowhere_else():
    light, dark = _two_inks()
    out = trap([_mask(light), _mask(dark)], [LIGHT, DARK], 2)
    lo, do = _alpha(out[0]), _alpha(out[1])
    assert (do == dark).all()                           # the darker film is unchanged
    assert (lo[10:30, 30:32]).all() and not lo[10:30, 32:].any()   # 2 px under the dark
    assert not (lo & ~(light | dark)).any()             # never onto bare cloth
    # given in the other order, the same ink spreads: direction is by lightness
    out2 = trap([_mask(dark), _mask(light)], [DARK, LIGHT], 2)
    assert (_alpha(out2[1]) == lo).all() and (_alpha(out2[0]) == dark).all()


def test_trapped_films_stacked_in_press_order_rebuild_the_design():
    """The spread is always covered by the darker ink printed after it."""
    img = Image.new('RGB', (160, 120), '#F4E8CC'); d = ImageDraw.Draw(img)
    d.ellipse((20, 15, 110, 105), fill='#C0392B'); d.rectangle((70, 40, 150, 80), fill='#1E2A4A')
    d.line((0, 118, 159, 0), fill='#E8B830', width=1)   # a hairline across everything
    reduced, pal = quantize_full(img, 4, 1)
    layers = create(reduced, [p.hex for p in pal], 0)
    colors = [hx for hx, _, _ in layers]
    masks = [m for _, m, _ in layers]
    order = sorted(range(len(masks)), key=lambda i: -press_lightness(colors[i]))
    for px in range(1, MAX_TRAP + 1):
        films = trap(masks, colors, px)
        plain = np.full(img.size[::-1], -1); stacked = np.full(img.size[::-1], -1)
        for i in order:
            plain[_alpha(masks[i])] = i
            stacked[_alpha(films[i])] = i
        assert (plain == stacked).all()
        grown = sum(_alpha(f).sum() for f in films) - sum(_alpha(m).sum() for m in masks)
        assert grown > 0                                  # the trap really is there


def test_trap_wraps_round_a_seamless_repeat():
    """On a repeat tile the light ground at one edge spreads under the dark
    motif continuing from the other edge, as it will on the printed cloth."""
    from app.separation_engine.engine import _spread
    img = Image.new('RGB', (120, 120), LIGHT); d = ImageDraw.Draw(img)
    for dx in (-120, 0, 120):
        for dy in (-120, 0, 120):
            d.ellipse((70 + dx, 60 + dy, 140 + dx, 100 + dy), fill=DARK)   # motif across the seam
    a = np.asarray(img)
    light = (a == np.array([0xF2, 0xD1, 0x6B])).all(-1); dark = ~light
    out = _alpha(trap([_mask(light), _mask(dark)], [LIGHT, DARK], 2)[0])
    edge = np.zeros((6, 6), bool); edge[:, 0] = True
    assert _spread(edge, 1, (True, False))[:, -1].all()   # grows across the seam...
    assert not _spread(edge, 1)[:, -1].any()              # ...only when asked to
    assert (out == (_spread(light, 2, (True, True)) & dark | light)).all()


def test_overlapping_bureau_screens_are_refused():
    a = np.ones((10, 10), bool)
    with pytest.raises(ValueError):
        trap([_mask(a), _mask(a)], [LIGHT, DARK], 1)


def _client_layers(c):
    img = Image.new('RGB', (80, 60), '#F4E8CC'); d = ImageDraw.Draw(img)
    d.ellipse((10, 10, 50, 50), fill='#C0392B'); d.rectangle((40, 20, 75, 40), fill='#1E2A4A')
    buf = BytesIO(); img.save(buf, 'PNG')
    up = c.post('/api/image/upload', files={'file': ('d.png', buf.getvalue(), 'image/png')}).json()
    red = c.post('/api/colors/reduce', json={'image_id': up['image_id'], 'colors': 3, 'smoothing': 0}).json()
    sep = c.post('/api/separation/create', json={'image_id': red['image_id'],
                                                  'palette': [p['hex'] for p in red['palette']]}).json()
    return [{'id': l['id'], 'name': l['name'], 'color': l['color']} for l in sep['layers']]


def test_package_with_trap_changes_only_the_lighter_films_and_says_so():
    c = TestClient(app)
    layers = _client_layers(c)
    plain = ZipFile(BytesIO(c.post('/api/export/package', json={'layers': layers}).content))
    trapped = ZipFile(BytesIO(c.post('/api/export/package', json={'layers': layers, 'trap_px': 2}).content))
    screens = sorted(n for n in plain.namelist() if n.startswith('screens/'))
    ink = lambda z, n: np.asarray(Image.open(BytesIO(z.read(n))).convert('L'))[120:-120, 120:-120] < 128
    changed = [n for n in screens if not (ink(plain, n) == ink(trapped, n)).all()]
    darkest = min(layers, key=lambda l: press_lightness(l['color']))['name']
    assert changed and f'screens/{darkest}.tif' not in changed
    readme = trapped.read('README.txt').decode()
    assert 'Trap: 2 px (0.17 mm)' in readme and 'Trap' not in plain.read('README.txt').decode()


def test_package_trap_out_of_range_is_a_422():
    c = TestClient(app)
    layers = _client_layers(c)
    assert c.post('/api/export/package', json={'layers': layers, 'trap_px': 9}).status_code == 422
