"""The third way in: one coloured design through textile's `number` (and `final`
at the mill's size), as LoomLab's POST /api/number."""
import io
import zipfile

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFilter

from app.main import app

client = TestClient(app)
BEIGE, RED, DARK_RED, BLACK = (240, 222, 180), (215, 23, 40), (180, 17, 31), (24, 26, 31)


def _petals_png():
    """A small AI-like design: red petals, each with a darker red shading patch, black stems, soft edges."""
    img = Image.new('RGB', (480, 320), BEIGE)
    d = ImageDraw.Draw(img)
    for cx, cy in ((110, 100), (300, 90), (200, 230), (400, 240)):
        d.line([(cx, cy + 40), (cx - 30, cy + 90)], fill=BLACK, width=7)
        d.ellipse([cx - 55, cy - 40, cx + 55, cy + 40], fill=RED)
        d.ellipse([cx - 40, cy - 5, cx + 5, cy + 30], fill=DARK_RED)
    buf = io.BytesIO()
    img.filter(ImageFilter.GaussianBlur(0.8)).save(buf, 'PNG')
    return buf.getvalue()


def _hexes(palette):
    return {p['hex'] for p in palette}


def _close(hexes, rgb, tol=12):
    return any(max(abs(int(h[i:i + 2], 16) - c) for i, c in zip((1, 3, 5), rgb)) <= tol for h in hexes)


def test_a_design_is_numbered_its_shading_joins_its_colour_and_everything_is_in_one_zip():
    r = client.post('/api/number', files={'design': ('petals.png', _petals_png(), 'image/png')},
                    data={'inks': '8', 'detail': 'normal', 'merge_shades': 'true', 'inches': '3x2', 'size': '900'})
    assert r.status_code == 200, r.text
    j = r.json()
    n = j['number']
    assert n['name'] == 'petals' and n['areas'] > 4 and n['verify']
    assert n['size_px'] == [900, 600]
    assert any(_close([m['from']], DARK_RED) and _close([m['into']], RED) for m in n['shades_merged'])
    red = j['reduced']
    assert (red['width'], red['height']) == (900, 600)
    hexes = _hexes(red['palette'])
    assert _close(hexes, RED) and _close(hexes, BLACK) and _close(hexes, BEIGE)
    assert not _close(hexes, DARK_RED, tol=8)                  # the shading is on the red screen
    assert red['accuracy'] > 80
    assert n['mill'] == {'inches': [3.0, 2.0], 'size_px': [900, 600], 'dpi': 300, 'inks': n['mill']['inks'],
                         'design_match': n['mill']['design_match'], 'passed': True, 'cropped': False,
                         'folder': 'petals_mill_3x2in'}
    for url in (n['sheet_url'], n['numbers_url'], j['original']['url'], red['url']):
        assert client.get(url).status_code == 200
    z = client.get(n['zip_url'], params={'name': n['zip_name']})
    assert z.status_code == 200 and 'petals_LoomLab_number.zip' in z.headers['content-disposition']
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    for want in ('petals_number/petals_sketch_bold_numbers.png', 'petals_number/petals_colors.csv',
                 'petals_number/package/petals_final_900x600px_300dpi.tif', 'petals_number/package/petals_layers_900px_300dpi.psd',
                 'petals_mill_3x2in/petals_final_900x600px_300dpi.tif', 'petals_mill_3x2in/petals_final.svg'):
        assert want in names, want


def test_without_merge_shades_the_shading_keeps_its_own_screen_and_no_mill_file_unless_asked():
    r = client.post('/api/number', files={'design': ('petals.png', _petals_png(), 'image/png')},
                    data={'inks': '8', 'merge_shades': 'false', 'size': '900'})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j['number']['shades_merged'] == [] and j['number']['mill'] is None
    assert _close(_hexes(j['reduced']['palette']), DARK_RED, tol=8)


def test_bad_settings_are_a_4xx_and_a_gone_zip_is_a_404():
    png = _petals_png()
    for data, word in (({'inks': '1'}, 'Inks'), ({'detail': 'lots'}, 'Detail'), ({'inches': 'big'}, 'Mill size'),
                       ({'inches': '200x200'}, 'Mill size'), ({'inches': '100x100'}, 'too big'), ({'size': '10'}, 'Size')):
        r = client.post('/api/number', files={'design': ('p.png', png, 'image/png')}, data=data)
        assert r.status_code == 422 and word in r.json()['detail'], (data, r.text)
    r = client.post('/api/number', files={'design': ('p.png', b'not an image', 'image/png')})
    assert r.status_code == 422
    assert client.get('/api/number/' + '0' * 32 + '/zip').status_code == 404
    assert client.get('/api/number/..%2F..%2Fetc/zip').status_code == 404
