"""The second way in: line art + a coloured reference -> a flat design that
Separate and Export take like any reduced one. The fill itself is
textile_project's (tested there against reference_code); these check the app's
side: the answer, the match, the plates, and bad pairs as 422s."""
import io
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app

COLOURS = [(200, 40, 40), (40, 150, 60), (40, 60, 190), (235, 225, 205)]


@pytest.fixture(scope='module')
def client():
    return TestClient(app, raise_server_exceptions=False)


def _png(a):
    b = io.BytesIO()
    Image.fromarray(a).save(b, 'PNG')
    return b.getvalue()


def pair(w=200, h=200):
    """Four squares split by black lines: the line art, and the same in colour."""
    line = np.full((h, w), 255, np.uint8)
    ref = np.zeros((h, w, 3), np.uint8)
    for k, c in enumerate(COLOURS):
        ref[(k // 2) * h // 2:(k // 2 + 1) * h // 2, (k % 2) * w // 2:(k % 2 + 1) * w // 2] = c
    for a in (line, ref):
        a[h // 2 - 3:h // 2 + 3] = 0
        a[:, w // 2 - 3:w // 2 + 3] = 0
        a[:4] = a[-4:] = 0
        a[:, :4] = a[:, -4:] = 0
    return _png(line), _png(np.ascontiguousarray(ref))


def fill(client, line, ref, **form):
    return client.post('/api/fill', files={'line': ('l.png', line, 'image/png'), 'ref': ('r.png', ref, 'image/png')},
                       data={'size': '400', **{k: str(v) for k, v in form.items()}})


def test_a_pair_fills_to_flat_inks_that_separate_exactly(client):
    r = fill(client, *pair())
    assert r.status_code == 200, r.text
    j = r.json()
    hexes = {p['hex'] for p in j['reduced']['palette']}
    assert hexes == {'#%02X%02X%02X' % c for c in COLOURS} | {'#000000'}
    assert j['fill']['size_px'] == [400, 400] and j['fill']['line_color'] == '#000000'
    assert j['reduced']['accuracy'] > 95          # the filled design looks like the reference
    assert abs(sum(p['coverage'] for p in j['reduced']['palette']) - 100) < 0.1

    # the plates stack back to the filled design, one ink per pixel
    rid = j['reduced']['image_id']
    s = client.post('/api/separation/create', json={'image_id': rid, 'palette': [p['hex'] for p in j['reduced']['palette']]})
    assert s.status_code == 200, s.text
    assert len(s.json()['layers']) == 5

    # Reduce's accuracy, asked again after an edit, judges the fill the same way
    a = client.post('/api/colors/accuracy', json={'image_id': j['original']['image_id'], 'reduced_id': rid,
                                                  'palette': list(hexes), 'filled': True}).json()
    assert a['accuracy'] == j['reduced']['accuracy']


def test_the_match_is_pixel_by_pixel_not_the_palette(client):
    """The line art's divider sits 40 px off the reference's: every ink is
    still exactly a reference colour (a palette check would say 100%), but a
    strip of the design is filled with the wrong one, and the match says so."""
    _, ref = pair()
    line = np.asarray(Image.open(io.BytesIO(pair()[0]))).copy()
    line[:, 97:103] = 255
    line[:, 137:143] = 0
    line[97:103] = 0                                    # the cross line stays whole
    r = fill(client, _png(line), ref, force='true')
    assert r.status_code == 200, r.text
    j = r.json()
    assert {p['hex'] for p in j['reduced']['palette']} == {'#%02X%02X%02X' % c for c in COLOURS} | {'#000000'}
    assert j['reduced']['accuracy'] < 85


@pytest.mark.parametrize('what,files,form,needle', [
    ('not an image', (b'not a png', None), {}, 'line art is not a valid image'),
    ('different shape', (None, 'wide'), {}, 'not the same shape'),
    ('too many colours', (None, None), {'max_colors': 40}, 'between 2 and 20'),
    ('bad outline code', (None, None), {'line_color': 'red'}, 'Outline colour'),
])
def test_bad_input_is_a_422_in_words(client, what, files, form, needle):
    line, ref = pair()
    if files[0] is not None:
        line = files[0]
    if files[1] == 'wide':
        ref = pair(300, 200)[1]
    r = fill(client, line, ref, **form)
    assert r.status_code == 422, (what, r.status_code, r.text)
    assert needle in r.json()['detail']


def test_a_pair_that_does_not_line_up_is_refused_unless_forced(client):
    line, _ = pair()
    rng = np.random.default_rng(1)
    noise = _png(rng.integers(0, 255, (200, 200, 3), dtype=np.uint8))
    r = fill(client, line, noise)
    assert r.status_code == 422 and 'do not line up' in r.json()['detail']
    assert fill(client, line, noise, force='true').status_code == 200


SAMPLES = Path(__file__).resolve().parents[2] / 'textile_project' / 'tests' / 'samples'


def test_auto_picks_the_method_and_says_why(client):
    """The tree panel: Method 1 leaves its motifs out and Method 3 finds no
    shift that fits (another drawing), so auto ends at Method 2's two colours."""
    r = fill(client, (SAMPLES / 'tree_lineart.png').read_bytes(), (SAMPLES / 'tree_ref.png').read_bytes(),
             method='auto', size=1200)
    assert r.status_code == 200, r.text
    f = r.json()['fill']
    assert f['method'] == 2 and f['auto']['only_two'] and f['auto']['method1']['coverage_diff'] > 6
    assert f['alignment'] is None and f['line_color'] is None
    assert len(r.json()['reduced']['palette']) == 2


def test_each_method_can_be_asked_for(client):
    line, ref = pair()
    for m in ('1', '3'):
        r = fill(client, line, ref, method=m)
        assert r.status_code == 200 and r.json()['fill']['method'] == int(m), r.text
    r = fill(client, line, ref, method='2')
    assert r.status_code == 200 and len(r.json()['reduced']['palette']) == 2


def test_a_wrong_method_or_a_one_colour_reference_is_a_422(client):
    line, ref = pair()
    assert fill(client, line, ref, method='4').status_code == 422
    flat = _png(np.full((200, 200, 3), 90, np.uint8))
    r = fill(client, line, flat, method='2')
    assert r.status_code == 422 and 'only one colour' in r.json()['detail']
