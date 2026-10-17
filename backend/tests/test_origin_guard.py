"""Another web page must not be able to change anything in the engine (CSRF):
every POST / PUT / PATCH / DELETE from a browser has to come from LoomLab's own
page, and the engine answers only to its own host names (DNS rebinding)."""
import pytest
from fastapi.testclient import TestClient

from app import origin_guard
from app.main import app
from app.routes import settings as settings_routes

EVIL = 'http://evil.example'
client = TestClient(app)


@pytest.fixture
def restores(monkeypatch):
    """backups.restore replaced by a recorder: did the request reach it?"""
    calls = []
    monkeypatch.setattr(settings_routes.backups, 'restore', lambda f: calls.append(f.read()) or {'ok': True})
    return calls


def _restore(headers):
    return client.post('/api/backup/restore', headers=headers,
                       files={'file': ('loomlab-backup.zip', b'PK fake backup', 'application/zip')})


@pytest.mark.parametrize('headers', [
    {'Origin': EVIL},
    {'Origin': 'null'},                                    # a sandboxed frame or a local html file
    {'Origin': 'http://localhost:9999'},                   # another program on this PC
    {'Referer': EVIL + '/prices.html'},                    # an old browser that sends only Referer
    {'Sec-Fetch-Site': 'cross-site'},
])
def test_a_fake_backup_from_another_page_is_refused_before_anything_is_written(restores, headers):
    r = _restore(headers)
    assert r.status_code == 403
    assert 'another web page' in r.json()['detail']
    assert restores == []                                  # the restore never ran


@pytest.mark.parametrize('method, path', [
    ('put', '/api/settings/rate-card'), ('put', '/api/settings/auto'), ('put', '/api/inks'),
    ('post', '/api/auto'), ('post', '/api/image/upload'), ('post', '/api/licence'),
    ('post', '/api/jobs/' + 'a' * 32 + '/stage'), ('delete', '/api/settings/auto'), ('patch', '/api/inks'),
])
def test_every_kind_of_change_from_another_page_is_refused(method, path):
    r = client.request(method.upper(), path, headers={'Origin': EVIL}, json={})
    assert r.status_code == 403, (method, path, r.status_code)


@pytest.mark.parametrize('headers', [
    {'Origin': 'http://localhost:8003'},                   # the app the engine serves
    {'Origin': 'http://127.0.0.1:8003'},
    {'Origin': 'http://localhost:5173'},                   # npm run dev (Vite proxies /api)
    {'Origin': 'http://localhost:8003', 'Sec-Fetch-Site': 'same-origin'},
    {'Referer': 'http://localhost:8003/'},
    {},                                                    # no browser: the Telegram bot, MCP, hot folder, scripts
])
def test_loomlab_itself_and_its_own_tools_still_get_through(restores, headers):
    assert _restore(headers).status_code == 200
    assert restores == [b'PK fake backup']


def test_the_engine_started_on_another_port_accepts_its_own_page():
    r = client.post('/api/image/exists', json={'ids': []},
                    headers={'Host': 'localhost:8010', 'Origin': 'http://localhost:8010'})
    assert r.status_code == 200
    r = client.post('/api/image/exists', json={'ids': []},
                    headers={'Host': 'localhost:8010', 'Origin': 'http://localhost:8011'})
    assert r.status_code == 403


def test_reading_is_not_blocked_by_an_origin():
    """<img> and download links carry no Origin, and a foreign page cannot read
    the answer anyway (CORS); only changes are guarded."""
    assert client.get('/api/health', headers={'Origin': EVIL}).status_code == 200


def test_an_origin_added_in_allowed_origins_is_let_through(monkeypatch):
    monkeypatch.setenv('ALLOWED_ORIGINS', 'http://loomlab.mill.lan:8003, http://localhost:5173')
    guard = origin_guard.OriginGuard(app=None)
    scope = {'type': 'http', 'method': 'POST', 'headers': [(b'origin', b'http://loomlab.mill.lan:8003')]}
    assert guard.verdict(scope) is None
    scope['headers'] = [(b'origin', EVIL.encode())]
    assert guard.verdict(scope) == EVIL


def test_the_engine_answers_only_to_its_own_host_names():
    """A page on evil.example re-pointed at 127.0.0.1 (DNS rebinding) sends
    Host: evil.example; the engine does not answer it, not even a read."""
    rebind = TestClient(app, base_url='http://evil.example:8003')
    assert rebind.get('/api/health').status_code == 400
    assert rebind.get('/api/diagnostics').status_code == 400
    assert TestClient(app, base_url='http://localhost:8003').get('/api/health').status_code == 200
    assert TestClient(app, base_url='http://127.0.0.1:8003').get('/api/health').status_code == 200


def test_default_hosts_and_origins_are_localhost_only(monkeypatch):
    monkeypatch.delenv('LOOMLAB_ALLOWED_HOSTS', raising=False)
    monkeypatch.delenv('ALLOWED_ORIGINS', raising=False)
    assert origin_guard.allowed_hosts() == ['localhost', '127.0.0.1']
    assert origin_guard.allowed_origins() == {'http://localhost:8003', 'http://127.0.0.1:8003',
                                              'http://localhost:5173', 'http://127.0.0.1:5173'}
