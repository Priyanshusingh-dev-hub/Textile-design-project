"""Printing on coloured/dark cloth. The colour separation stays mutually
exclusive; the white under-base is an ADDITIONAL screen laid down first."""
from io import BytesIO
from zipfile import ZipFile
import numpy as np
import pytest
from PIL import Image, ImageDraw
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


def _line(box, width):
    im = Image.new('RGBA', (120, 120), (0, 0, 0, 0))
    ImageDraw.Draw(im).line(box, fill=(255, 255, 255, 255), width=width)
    return im


@pytest.mark.parametrize('line_width,choke', [(1, 1), (2, 1), (2, 2), (3, 4)])
def test_choke_never_erases_a_hairline_from_the_under_base(line_width, choke):
    """A feature no wider than 2*choke is wiped out by the erosion. Without a
    white base under it, a stem or outline prints straight onto dark cloth and
    goes dull while everything around it stays bright — and thin linework is
    exactly what the reduce step works hardest to keep."""
    hair = _line((10, 60, 110, 60), line_width)
    blob = Image.new('RGBA', (120, 120), (0, 0, 0, 0))
    ImageDraw.Draw(blob).ellipse((20, 10, 80, 45), fill=(255, 255, 255, 255))

    ub = np.asarray(underbase([blob, hair], choke=choke))[:, :, 3] > 0
    assert (ub & (np.asarray(hair)[:, :, 3] > 0)).any(), 'the hairline lost its white base'


@pytest.mark.parametrize('choke', [1, 2, 4])
def test_solid_shapes_are_still_choked(choke):
    """Keeping hairlines must not quietly stop choking everything else, or the
    white shows past the colour — the trap the choke exists to avoid."""
    blob = Image.new('RGBA', (120, 120), (0, 0, 0, 0))
    ImageDraw.Draw(blob).ellipse((20, 20, 100, 100), fill=(255, 255, 255, 255))
    solid = np.asarray(blob)[:, :, 3] > 0
    ub = np.asarray(underbase([blob], choke=choke))[:, :, 3] > 0
    assert (solid & ~ub).sum() > 0, 'the rim was not pulled in at all'
    assert not (ub & ~solid).any(), 'white extends past the colour'


@pytest.mark.parametrize('choke', [0, 1, 2, 4])
def test_under_base_never_extends_past_the_colour(choke):
    shapes = [Image.new('RGBA', (120, 120), (0, 0, 0, 0)) for _ in range(2)]
    ImageDraw.Draw(shapes[0]).ellipse((10, 10, 60, 60), fill=(255, 255, 255, 255))
    ImageDraw.Draw(shapes[1]).rectangle((70, 20, 110, 100), fill=(255, 255, 255, 255))
    shapes.append(_line((5, 110, 115, 110), 2))
    union = np.zeros((120, 120), bool)
    for s in shapes:
        union |= np.asarray(s)[:, :, 3] > 0
    ub = np.asarray(underbase(shapes, choke=choke))[:, :, 3] > 0
    assert not (ub & ~union).any()


def test_the_ground_is_the_ink_that_owns_the_edge():
    """A mill skips the ground's screen by printing on cloth of that colour;
    the ink that covers the design's outer edge is that ground."""
    from app.separation_engine.engine import create, edge_share
    im = Image.new('RGB', (100, 100), '#F4E8CC')
    ImageDraw.Draw(im).ellipse((30, 30, 70, 70), fill='#C0392B')
    ground, motif = [m for _, m, _ in create(im, ['#F4E8CC', '#C0392B'], 0)]
    assert edge_share(ground) == 100.0 and edge_share(motif) == 0.0


def test_a_big_motif_on_transparent_is_not_a_ground():
    from app.separation_engine.engine import create, edge_share
    im = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((5, 5, 95, 95), fill=(192, 57, 43, 255))
    (disc,) = [m for _, m, _ in create(im, ['#C0392B'], 0)]
    assert edge_share(disc) == 0.0
