"""Bad input must be an actionable client error, never a 500. Generated images
expire, so an operator reopening yesterday's tab hits a stale id — that has to
read as 'import it again', not as a server fault."""
import re

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app

DEAD = 'f' * 32          # correctly shaped id that names no stored image


@pytest.fixture(scope='module')
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope='module')
def reduced(client):
    s = client.post('/api/image/sample').json()
    r = client.post('/api/colors/reduce', json={'image_id': s['image_id'], 'colors': 4}).json()
    return r['image_id'], [p['hex'] for p in r['palette']]


@pytest.mark.parametrize('endpoint,body', [
    ('/api/colors/reduce', {'image_id': DEAD, 'colors': 4}),
    ('/api/colors/suggest', {'image_id': DEAD}),
    ('/api/colors/accuracy', {'image_id': DEAD, 'palette': ['#A15745']}),
    ('/api/separation/create', {'image_id': DEAD, 'palette': ['#A15745']}),
    ('/api/separation/preview', {'layers': [{'id': DEAD, 'color': '#A15745'}]}),
    ('/api/colors/remap', {'image_id': DEAD, 'source': '#A15745', 'target': '#000000'}),
])
def test_expired_image_id_is_404_with_guidance(client, endpoint, body):
    r = client.post(endpoint, json=body)
    assert r.status_code == 404
    assert 'import' in r.json()['detail'].lower()


def test_expired_image_get_is_404(client):
    assert client.get(f'/api/image/{DEAD}').status_code == 404


@pytest.mark.parametrize('bad', ['red', '#GG0000', '', '#12', '#1234567'])
def test_malformed_colour_is_422_not_500(client, reduced, bad):
    image_id, _ = reduced
    assert client.post('/api/separation/create',
                       json={'image_id': image_id, 'palette': [bad]}).status_code == 422


@pytest.mark.parametrize('endpoint,body', [
    ('/api/separation/create', {'image_id': 'x' * 32, 'palette': []}),
    ('/api/separation/preview', {'layers': []}),
    ('/api/export/package', {'layers': []}),
    ('/api/export/svg', {'layers': []}),
])
def test_empty_ink_list_is_422(client, endpoint, body):
    assert client.post(endpoint, json=body).status_code == 422


@pytest.mark.parametrize('bad_id', ['../../etc/passwd', '/etc/hosts', 'abc', '', 'F' * 32])
def test_malformed_image_id_is_rejected(client, bad_id):
    assert client.post('/api/colors/reduce', json={'image_id': bad_id, 'colors': 4}).status_code == 422


def test_too_many_inks_is_rejected(client, reduced):
    image_id, _ = reduced
    assert client.post('/api/separation/create',
                       json={'image_id': image_id, 'palette': ['#112233'] * 100}).status_code == 422


def test_happy_path_still_works(client, reduced):
    image_id, pal = reduced
    layers = client.post('/api/separation/create', json={'image_id': image_id, 'palette': pal}).json()['layers']
    assert layers
    pv = client.post('/api/separation/preview',
                     json={'layers': [{'id': l['id'], 'color': l['color']} for l in layers]})
    assert pv.status_code == 200


# --- ink colour for pre-separated (multichannel) PSD channels -----------------

def test_ink_from_name_recognises_common_ink_words():
    """A multichannel PSD's channels are named by the ink the mill loads
    ("GOLD", "BROWN 120"), so the proof should start from that colour rather
    than an arbitrary placeholder."""
    from app.main import _ink_from_name
    assert _ink_from_name('GOLD', '#000000') == '#C8A13A'
    assert _ink_from_name('BROWN 120', '#000000') == '#6B4530'
    assert _ink_from_name('Navy Blue', '#000000') == '#1E2A4A'      # first match wins
    assert _ink_from_name('black', '#000000') == '#1A1A1A'          # case-insensitive


def test_ink_from_name_falls_back_when_the_name_says_nothing():
    from app.main import _ink_from_name
    for name in ('FOIL 80 JALI', 'CHANNEL 3', '', None):
        assert _ink_from_name(name, '#E63946') == '#E63946'


def test_ink_words_are_all_valid_hex():
    from app.main import _INK_WORDS
    assert all(re.fullmatch(r'#[0-9A-F]{6}', hx) for _, hx in _INK_WORDS)


def test_psd_channel_overlap_is_measured_not_assumed():
    """A pre-separated PSD may overlap on purpose (trapping); the upload
    reports how much, so the UI never claims one ink per pixel for it."""
    from app.main import _overlap
    def layer(box):
        a = np.zeros((20, 20, 4), np.uint8); y0, x0, y1, x1 = box; a[y0:y1, x0:x1, 3] = 255
        return Image.fromarray(a)
    apart = [('A', '#000000', layer((0, 0, 10, 10)), None, 0), ('B', '#000000', layer((10, 10, 20, 20)), None, 0)]
    assert _overlap(apart) == 0.0
    trapped = [('A', '#000000', layer((0, 0, 10, 11)), None, 0), ('B', '#000000', layer((0, 10, 10, 20)), None, 0)]
    assert _overlap(trapped) == 5.0            # one shared column of 10 px, of 200 inked
    assert _overlap([]) == 0.0


def test_images_exist_reports_the_cleared_ones():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    kept = c.post('/api/image/sample').json()['image_id']
    gone = 'f' * 32
    r = c.post('/api/image/exists', json={'ids': [kept, gone, gone]})
    assert r.status_code == 200 and r.json() == {'missing': [gone]}
    assert c.post('/api/image/exists', json={'ids': ['../etc/passwd']}).status_code == 422


def _png(img):
    import io
    b = io.BytesIO(); img.save(b, 'PNG'); return b.getvalue()


def test_fully_transparent_upload_is_a_422_not_a_500():
    from fastapi.testclient import TestClient
    from PIL import Image
    from app.main import app
    c = TestClient(app, raise_server_exceptions=False)
    r = c.post('/api/image/upload', files={'file': ('empty.png', _png(Image.new('RGBA', (40, 40), (0, 0, 0, 0))), 'image/png')})
    assert r.status_code == 422 and 'transparent' in r.json()['detail']


def test_one_colour_design_reduces_to_one_screen():
    from fastapi.testclient import TestClient
    from PIL import Image
    from app.main import app
    c = TestClient(app)
    up = c.post('/api/image/upload', files={'file': ('red.png', _png(Image.new('RGB', (30, 20), '#C0392B')), 'image/png')}).json()
    n = c.post('/api/colors/suggest', json={'image_id': up['image_id']}).json()['suggested']
    assert n == 1
    red = c.post('/api/colors/reduce', json={'image_id': up['image_id'], 'colors': n, 'smoothing': 1}).json()
    assert [p['hex'] for p in red['palette']] == ['#C0392B']
    sep = c.post('/api/separation/create', json={'image_id': red['image_id'], 'palette': ['#C0392B']}).json()
    assert len(sep['layers']) == 1 and sep['layers'][0]['coverage'] == 100


def test_image_can_be_fetched_screen_sized():
    import io
    from fastapi.testclient import TestClient
    from PIL import Image
    from app.core import store
    from app.main import app
    c = TestClient(app)
    iid = store.save(Image.new('RGB', (3000, 1500), '#123456'))
    small = Image.open(io.BytesIO(c.get(f'/api/image/{iid}?max_side=600').content))
    assert small.size == (600, 300)
    assert Image.open(io.BytesIO(c.get(f'/api/image/{iid}').content)).size == (3000, 1500)
    assert c.get(f'/api/image/{iid}?max_side=5').status_code == 422
