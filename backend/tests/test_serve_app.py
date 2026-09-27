"""The engine serves the built app: one server, one address for the mill."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import serve_app


def test_the_built_app_is_served_and_the_api_still_wins(tmp_path):
    (tmp_path / 'index.html').write_text('<!doctype html><title>LoomLab</title>')
    (tmp_path / 'assets').mkdir()
    (tmp_path / 'assets' / 'app.js').write_text('console.log(1)')
    api = FastAPI()

    @api.get('/api/health')
    def health():
        return {'ok': True}

    assert serve_app(api, tmp_path)
    c = TestClient(api)
    assert 'LoomLab' in c.get('/').text
    assert c.get('/assets/app.js').headers['content-type'].startswith(('application/javascript', 'text/javascript'))
    assert c.get('/api/health').json() == {'ok': True}
    assert c.get('/nothing-here.js').status_code == 404


def test_without_a_build_nothing_is_mounted(tmp_path):
    api = FastAPI()
    assert not serve_app(api, tmp_path)
    assert TestClient(api).get('/').status_code == 404
