"""The mill's ink library: store it, match a palette to it, repaint to it."""
import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.color_engine import engine as E
from app.core import inks as ink_library
from app.main import app

SHELF = [{'name': 'Rani Pink 12', 'hex': '#D96A8E'}, {'name': 'Navy 3', 'hex': '#1E2A4A'},
         {'name': 'Haldi', 'hex': '#E8C317'}, {'name': 'Kora (cream)', 'hex': '#EFE3C8'}]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(ink_library, 'LIBRARY', tmp_path / 'inks.json')
    return TestClient(app)


def test_library_starts_empty_and_round_trips(client):
    assert client.get('/api/inks').json() == {'inks': []}
    saved = client.put('/api/inks', json={'inks': SHELF}).json()['inks']
    assert [i['name'] for i in saved] == [i['name'] for i in SHELF]
    assert client.get('/api/inks').json()['inks'] == saved


def test_library_normalises_colours(client):
    saved = client.put('/api/inks', json={'inks': [{'name': ' Haldi ', 'hex': 'e8c317'}]}).json()['inks']
    assert saved == [{'name': 'Haldi', 'hex': '#E8C317'}]


@pytest.mark.parametrize('bad', [
    {'inks': [{'name': '', 'hex': '#FFFFFF'}]},              # no name
    {'inks': [{'name': 'x', 'hex': 'not-a-colour'}]},
    {'inks': [{'name': 'x' * 61, 'hex': '#FFFFFF'}]},
])
def test_bad_library_entries_are_a_4xx(client, bad):
    assert client.put('/api/inks', json=bad).status_code == 422


def test_a_corrupt_library_file_reads_as_empty_not_a_crash(client):
    ink_library.LIBRARY.write_text('{not json', encoding='utf-8')
    assert client.get('/api/inks').json() == {'inks': []}


def test_each_palette_colour_gets_its_nearest_shelf_ink(client):
    client.put('/api/inks', json={'inks': SHELF})
    m = client.post('/api/inks/match', json={'palette': ['#DA6B8C', '#202C4C', '#FFFFFF']}).json()['matches']
    assert [x['name'] for x in m] == ['Rani Pink 12', 'Navy 3', 'Kora (cream)']
    assert m[0]['delta_e'] < 2 and m[2]['delta_e'] > m[0]['delta_e']        # white is a looser match


def test_no_library_means_no_matches(client):
    assert client.post('/api/inks/match', json={'palette': ['#FFFFFF']}).json()['matches'] == [None]


def test_repaint_is_one_pass_so_swaps_do_not_cascade():
    """A->B and B->A at once must swap them, not send both to A."""
    im = Image.new('RGBA', (40, 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 19, 19), fill=(192, 57, 43, 255)); d.rectangle((20, 0, 39, 9), fill=(42, 93, 168, 255))
    out = np.asarray(E.repaint(im, ['#C0392B', '#2A5DA8'], ['#2A5DA8', '#C0392B']))
    assert tuple(out[5, 5, :3]) == (42, 93, 168) and tuple(out[5, 30, :3]) == (192, 57, 43)
    assert out[15, 30, 3] == 0                                              # transparency kept


def test_repaint_endpoint_merges_inks_sent_to_the_same_target(client):
    im = Image.new('RGB', (30, 10), '#C0392B'); ImageDraw.Draw(im).rectangle((15, 0, 29, 9), fill='#BB3A2E')
    b = io.BytesIO(); im.save(b, 'PNG')
    info = client.post('/api/image/upload', files={'file': ('a.png', b.getvalue(), 'image/png')}).json()
    r = client.post('/api/colors/repaint', json={'image_id': info['image_id'], 'palette': ['#C0392B', '#BB3A2E'],
                                                  'targets': ['#D96A8E', '#D96A8E']}).json()
    out = np.asarray(Image.open(io.BytesIO(client.get(r['url']).content)).convert('RGB'))
    assert len(np.unique(out.reshape(-1, 3), axis=0)) == 1


def test_repaint_needs_a_target_per_colour(client):
    im = Image.new('RGB', (4, 4), '#C0392B'); b = io.BytesIO(); im.save(b, 'PNG')
    info = client.post('/api/image/upload', files={'file': ('a.png', b.getvalue(), 'image/png')}).json()
    r = client.post('/api/colors/repaint', json={'image_id': info['image_id'], 'palette': ['#C0392B', '#FFFFFF'],
                                                  'targets': ['#D96A8E']})
    assert r.status_code == 422
