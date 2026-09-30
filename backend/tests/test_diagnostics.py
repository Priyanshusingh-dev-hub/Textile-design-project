"""Settings -> Help: a report someone helping the mill can read."""
import pytest
from fastapi.testclient import TestClient

from app import diagnostics
from app.core import store
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    diagnostics._errors.clear()
    return TestClient(app, raise_server_exceptions=False)


def test_the_report_says_what_the_engine_is_and_holds(client):
    r = client.get('/api/diagnostics').json()
    assert r['system']['python'] and r['system']['numpy'] != 'missing'
    assert r['data']['folder'] and r['data']['library_designs'] == 0 and r['data']['disk_free_gb'] is not None
    assert r['settings'] == {'rate_card': 'ok', 'auto_limits': 'ok'} and r['errors'] == []
    text = client.get('/api/diagnostics/report.txt')
    assert text.headers['content-disposition'].endswith('loomlab-report.txt"') and '[system]' in text.text


def test_an_engine_fault_is_kept_logged_and_answered_in_plain_words(client, tmp_path, monkeypatch):
    from app.routes import palette
    def boom(*a, **k):
        raise RuntimeError('something inside broke')
    monkeypatch.setattr(palette.colors, 'suggest_colors', boom)
    up = client.post('/api/image/upload', files={'file': ('d.png', _png(), 'image/png')}).json()
    r = client.post('/api/colors/suggest', json={'image_id': up['image_id']})
    assert r.status_code == 500 and r.json()['detail'].startswith('The engine hit a problem with this design (error 500)')
    err = client.get('/api/diagnostics').json()['errors'][0]
    assert err['path'] == '/api/colors/suggest' and 'RuntimeError: something inside broke' in err['error']
    assert 'boom' in err['where'] or 'test_diagnostics' in err['where'] or err['where']
    log = (tmp_path / 'loomlab-errors.log').read_text(encoding='utf-8')
    assert 'something inside broke' in log and 'Traceback' in log


def test_the_log_is_kept_small(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setattr(diagnostics, 'LOG_MAX_BYTES', 200)
    for i in range(10):
        try:
            raise ValueError(f'fault {i}' * 10)
        except ValueError as e:
            diagnostics.record('GET', '/x', e)
    assert (tmp_path / 'loomlab-errors.log.1').exists()
    assert (tmp_path / 'loomlab-errors.log').stat().st_size < 3000


def _png():
    import io
    from PIL import Image
    b = io.BytesIO(); Image.new('RGB', (40, 30), '#AA3344').save(b, 'PNG'); return b.getvalue()
