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
    # these tests are about the fills themselves: Method 1 unless a test says otherwise (the judge has its own)
    return client.post('/api/fill', files={'line': ('l.png', line, 'image/png'), 'ref': ('r.png', ref, 'image/png')},
                       data={'size': '400', 'method': '1', **{k: str(v) for k, v in form.items()}})


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


def test_auto_tries_everything_scores_it_and_logs_the_run(client):
    """The tree panel: its line art is another drawing than its reference, so
    no fill matches the reference and the judge sets the line art aside. Every
    candidate is in the answer with its numbers, and the run is in the log."""
    r = fill(client, (SAMPLES / 'tree_lineart.png').read_bytes(), (SAMPLES / 'tree_ref.png').read_bytes(),
             method='auto', size=800)
    assert r.status_code == 200, r.text
    f = r.json()['fill']
    t = f['trials']
    assert f['method'] == 0 and t['chosen'] == 'reduce' and t['reason'] == 'fill_far' and t['margin'] < -t['tolerance']
    assert [row['name'] for row in t['rows']] == ['reduce', 'method1', 'method4', 'method3', 'method2']
    assert all('match' in row and row['inks'] >= 2 for row in t['rows'] if row['status'] == 'ok')
    assert [row['chosen'] for row in t['rows']].count(True) == 1
    # the answer is Reduce's own: the usual reduced design, ready for the palette tools
    assert r.json()['reduced']['smoothing'] is not None and len(r.json()['reduced']['palette']) == t['inks']
    log = client.get('/api/fill/log').json()['runs'][-1]
    assert log['chosen'] == 'reduce' and log['reason'] == 'fill_far' and len(log['trials']) == 5 and log['design']


def test_auto_takes_the_fill_when_it_fits_the_reference(client):
    line, ref = pair()
    r = fill(client, line, ref, method='auto')
    assert r.status_code == 200, r.text
    f = r.json()['fill']
    assert f['trials']['reason'] == 'fill_close' and f['trials']['chosen'].startswith('method')
    assert f['method'] == int(f['trials']['chosen'][-1]) and r.json()['reduced']['accuracy'] > 90


def test_each_method_can_be_asked_for_and_an_override_is_logged(client):
    line, ref = pair()
    for m in ('1', '3', '4'):
        r = fill(client, line, ref, method=m)
        assert r.status_code == 200 and r.json()['fill']['method'] == int(m) and r.json()['fill']['trials'] is None, r.text
    r = fill(client, line, ref, method='2')
    assert r.status_code == 200 and len(r.json()['reduced']['palette']) == 2
    r = fill(client, line, ref, method='0', overrides='method4')
    assert r.status_code == 200 and r.json()['fill']['method'] == 0
    last = client.get('/api/fill/log').json()['runs'][-1]
    assert last['event'] == 'operator' and last['made'] == '0' and last['overrides'] == 'method4'


def test_a_wrong_method_or_a_one_colour_reference_is_a_422(client):
    line, ref = pair()
    assert fill(client, line, ref, method='9').status_code == 422
    flat = _png(np.full((200, 200, 3), 90, np.uint8))
    r = fill(client, line, flat, method='2')
    assert r.status_code == 422 and 'only one colour' in r.json()['detail']


def test_a_wrong_crop_is_refused_even_when_auto_could_fall_back(client):
    line, _ = pair()
    r = fill(client, line, pair(300, 200)[1], method='auto')
    assert r.status_code == 422 and 'not the same shape' in r.json()['detail']


def test_a_misaligned_pair_makes_auto_use_the_reference_alone(client):
    """A clean reference, its line art shifted 60 px: Reduce reproduces the
    reference, every fill puts its colours in the wrong shapes, so Reduce wins."""
    line, ref = pair()
    shifted = np.roll(np.asarray(Image.open(io.BytesIO(line))), (60, 45), (0, 1))
    r = fill(client, _png(np.ascontiguousarray(shifted)), ref, method='auto')
    assert r.status_code == 200, r.text
    f = r.json()['fill']
    assert f['method'] == 0 and f['trials']['reason'] == 'fill_far', f['trials']


def test_the_rule_that_decides():
    """filltrial.decide: the best fill wins when it trails Reduce by no more than the tolerance."""
    from app.core import filltrial as ft
    row = lambda name, match, status='ok': {'name': name, 'match': match, 'status': status}
    red = row('reduce', 90)
    assert ft.decide([red, row('method1', 80), row('method4', 76)]) == ('method1', 'fill_close', -10.0)
    assert ft.decide([red, row('method1', 70), row('method4', 76.9)]) == ('reduce', 'fill_far', -13.1)
    assert ft.decide([red, row('method1', 77)]) == ('method1', 'fill_close', -13.0)       # the edge counts as close
    # the calibration's nearest cases: the approved star (-12.2) fills, the teal ikat (-14.2) does not
    assert ft.decide([red, row('method4', 77.8)])[0] == 'method4'
    assert ft.decide([red, row('method4', 75.8)])[0] == 'reduce'
    assert ft.decide([red, row('method1', 0, 'failed')]) == ('reduce', 'no_fill', None)
    assert ft.decide([red]) == ('reduce', 'no_fill', None)
    assert ft.decide([red, row('method1', 80)], tolerance=5) == ('reduce', 'fill_far', -10.0)
