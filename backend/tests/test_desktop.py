import socket
from fastapi import FastAPI
from fastapi.testclient import TestClient
import launcher
from app import main

def test_built_ui_is_served_and_api_routes_keep_priority(tmp_path):
    (tmp_path / 'index.html').write_text('<!doctype html><title>LoomLab Studio</title>')
    (tmp_path / 'assets').mkdir(); (tmp_path / 'assets' / 'app.js').write_text('console.log(1)')
    app = FastAPI()
    @app.get('/api/health')
    def health(): return {'ok': True}
    main.mount_ui(app, tmp_path)
    client = TestClient(app)
    assert 'LoomLab Studio' in client.get('/').text
    assert client.get('/assets/app.js').status_code == 200
    assert client.get('/api/health').json() == {'ok': True}

def test_ui_dir_prefers_the_environment_override(tmp_path, monkeypatch):
    (tmp_path / 'index.html').write_text('x')
    monkeypatch.setenv('LOOMLAB_UI_DIR', str(tmp_path))
    assert main.ui_dir() == tmp_path

def test_ui_dir_ignores_a_folder_without_index(tmp_path, monkeypatch):
    monkeypatch.setenv('LOOMLAB_UI_DIR', str(tmp_path))
    assert main.ui_dir() != tmp_path

def test_launcher_keeps_working_files_in_a_user_folder(monkeypatch, tmp_path):
    monkeypatch.delenv('DATA_DIR', raising=False)
    assert launcher.data_dir().parts[-2:] == ('LoomLab', 'data')
    monkeypatch.setenv('DATA_DIR', str(tmp_path))
    assert launcher.data_dir() == tmp_path

def test_launcher_falls_back_to_a_free_port_when_the_usual_one_is_taken():
    with socket.socket() as busy:
        busy.bind(('127.0.0.1', 0)); busy.listen()
        taken = busy.getsockname()[1]
        assert not launcher.port_is_free(taken)
        port = launcher.pick_port(taken)
        assert port != taken and launcher.port_is_free(port)
