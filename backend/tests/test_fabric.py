"""Printing on coloured/dark cloth. The colour separation stays mutually
exclusive; the white under-base is an ADDITIONAL screen laid down first."""
from io import BytesIO
from zipfile import ZipFile
import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app
from app.separation_engine.engine import underbase, plate


def _mask(box, size=(20, 20)):
    a = np.zeros((size[1], size[0], 4), np.uint8)
    x0, y0, x1, y1 = box
    a[y0:y1, x0:x1, 3] = 255
    return Image.fromarray(a)


def test_underbase_is_the_union_of_every_ink():
    ub = np.asarray(underbase([_mask((2, 2, 8, 8)), _mask((12, 12, 18, 18))], choke=0))[:, :, 3] > 0
    assert ub[4, 4] and ub[15, 15]          # both inks covered
    assert not ub[0, 0]                      # bare cloth stays bare


def test_underbase_choke_keeps_white_under_the_colour():
    masks = [_mask((2, 2, 12, 12))]
    raw = np.asarray(underbase(masks, choke=0))[:, :, 3] > 0
    choked = np.asarray(underbase(masks, choke=1))[:, :, 3] > 0
    assert choked.sum() < raw.sum()          # shrunk...
    assert not (choked & ~raw).any()         # ...and never outside the ink


def test_underbase_of_nothing_is_none():
    assert underbase([], 1) is None


def test_plate_renders_ink_over_the_cloth_colour():
    full = Image.fromarray(np.full((4, 4, 4), 255, np.uint8))
    empty = Image.fromarray(np.zeros((4, 4, 4), np.uint8))
    assert np.asarray(plate(full, '#FFFFFF', '#1B2A1F'))[0, 0].tolist() == [255, 255, 255]
    # where no ink prints, the cloth shows through
    assert np.asarray(plate(empty, '#FFFFFF', '#1B2A1F'))[0, 0].tolist() == [27, 42, 31]


@pytest.fixture(scope='module')
def separated():
    c = TestClient(app)
    s = c.post('/api/image/sample').json()
    r = c.post('/api/colors/reduce', json={'image_id': s['image_id'], 'colors': 4}).json()
    pal = [p['hex'] for p in r['palette']]
    layers = c.post('/api/separation/create', json={'image_id': r['image_id'], 'palette': pal, 'cleanup': 0}).json()['layers']
    return c, [{'id': l['id'], 'name': l['name'], 'color': l['color']} for l in layers]


def test_package_leads_with_the_underbase_on_dark_cloth(separated):
    c, layers = separated
    z = c.post('/api/export/package', json={'layers': layers, 'fabric': '#1B2A1F', 'underbase': True})
    with ZipFile(BytesIO(z.content)) as zf:
        names = zf.namelist()
        assert 'plates/0-Underbase.png' in names and 'screens/0-Underbase.tif' in names
        assert names.index('plates/0-Underbase.png') < names.index('plates/Ink-1.png')
        readme = zf.read('README.txt').decode()
        assert '#1B2A1F' in readme and 'UNDER-BASE' in readme


def test_package_without_underbase_has_none(separated):
    c, layers = separated
    z = c.post('/api/export/package', json={'layers': layers, 'fabric': '#1B2A1F'})
    with ZipFile(BytesIO(z.content)) as zf:
        assert not any('Underbase' in n for n in zf.namelist())


def test_underbase_does_not_disturb_vector_alignment(separated):
    c, layers = separated
    z = c.post('/api/export/package', json={'layers': layers, 'fabric': '#101010',
                                            'underbase': True, 'vector': True})
    with ZipFile(BytesIO(z.content)) as zf:
        svgs = [n for n in zf.namelist() if n.startswith('vector/') and n != 'vector/design.svg']
        assert 'vector/0-Underbase.svg' not in svgs        # no empty placeholder written
        assert len(svgs) == len(layers)                     # one per real ink
        for n in svgs:
            assert zf.read(n).startswith(b'<svg')


def test_preview_shows_the_cloth_where_no_ink_prints(separated):
    c, layers = separated
    pv = c.post('/api/separation/preview', json={'layers': layers[:1], 'fabric': '#1B2A1F'}).json()
    img = np.asarray(Image.open(BytesIO(c.get(pv['url']).content)).convert('RGB'))
    assert ((img[:, :, 0] == 27) & (img[:, :, 1] == 42) & (img[:, :, 2] == 31)).any()
