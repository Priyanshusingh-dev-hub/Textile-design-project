"""Bad input must be an actionable client error, never a 500. Generated images
expire, so an operator reopening yesterday's tab hits a stale id — that has to
read as 'import it again', not as a server fault."""
import pytest
from fastapi.testclient import TestClient
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
