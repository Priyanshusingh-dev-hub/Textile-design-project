"""Things the audit found: a page in the operator's browser must not drive the engine, a cut-off image is a 422,
Pillow's pixel guard stays on, a colour name never overwrites another on Windows, a damaged backup writes nothing."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import auto as auto_mode
from app.core import archive, backup, inks as ink_library, store
from app.core import quote as costing
from app.main import app

client = TestClient(app)


def _png(size=(40, 30)):
    buf = io.BytesIO()
    Image.new('RGB', size, '#336699').save(buf, 'PNG')
    return buf.getvalue()


def test_a_name_that_is_not_this_pc_is_refused_but_ip_addresses_and_localhost_work():
    assert client.get('/api/health', headers={'host': 'evil.example:8003'}).status_code == 400   # DNS rebinding
    for host in ('localhost:8003', '127.0.0.1:8003', '[::1]:8003', '192.168.1.20:8003'):
        assert client.get('/api/health', headers={'host': host}).status_code == 200, host
    assert client.get('/api/health').status_code == 200                                         # the tests' own host


def test_a_post_from_another_websites_page_is_refused_but_ours_works():
    up = lambda origin: client.post('/api/image/upload', files={'file': ('a.png', _png(), 'image/png')},
                                    headers={'origin': origin} if origin else {})
    assert up('https://evil.example').status_code == 403
    assert up('http://localhost:5173').status_code == 200         # the dev server
    assert up('http://127.0.0.1:8003').status_code == 200
    assert up(None).status_code == 200                            # the bot, the hot folder, the MCP: no Origin
    # a LAN page the engine itself serves is same-origin
    r = client.post('/api/image/upload', files={'file': ('a.png', _png(), 'image/png')},
                    headers={'host': '192.168.1.20:8003', 'origin': 'http://192.168.1.20:8003'})
    assert r.status_code == 200
    # reading is never refused by Origin (the browser's CORS decides who reads the answer)
    assert client.get('/api/health', headers={'origin': 'https://evil.example'}).status_code == 200


def test_a_cut_off_or_huge_image_is_a_422_never_a_500():
    data = _png((300, 300))
    r = client.post('/api/image/upload', files={'file': ('a.png', data[:len(data) // 2], 'image/png')})
    assert r.status_code == 422 and 'not a valid image' in r.json()['detail']
    old = Image.MAX_IMAGE_PIXELS
    try:
        store.PIXEL_LIMIT, limit = 100, store.PIXEL_LIMIT
        r = client.post('/api/image/upload', files={'file': ('a.png', _png((50, 50)), 'image/png')})
        assert r.status_code == 422 and 'too many pixels' in r.json()['detail']
    finally:
        store.PIXEL_LIMIT = limit
        Image.MAX_IMAGE_PIXELS = old


def test_the_pixel_guard_is_on_after_the_textile_tool_was_imported():
    assert Image.MAX_IMAGE_PIXELS == store.PIXEL_LIMIT          # io_utils sets None; main puts the bound back


def test_names_that_differ_only_in_case_never_share_a_file():
    z = zipfile.ZipFile(io.BytesIO(archive.build_zip([('Red', Image.new('L', (4, 4))), ('red', Image.new('L', (4, 4)))])))
    names = z.namelist()
    assert len({n.casefold() for n in names}) == 2
    pkg = zipfile.ZipFile(io.BytesIO(archive.build_package(
        [('Red', Image.new('RGB', (4, 4))), ('RED', Image.new('RGB', (4, 4)))],
        [('Red', Image.new('L', (4, 4))), ('RED', Image.new('L', (4, 4)))])))
    assert len({n.casefold() for n in pkg.namelist()}) == len(pkg.namelist())


def test_a_backup_with_a_damaged_member_changes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'data'); (tmp_path / 'data').mkdir()
    monkeypatch.setattr(ink_library, 'LIBRARY', tmp_path / 'data' / 'inks.json')
    monkeypatch.setattr(costing, 'CARD_PATH', tmp_path / 'rate-card.json')
    monkeypatch.setattr(auto_mode, 'CONFIG_PATH', tmp_path / 'auto-config.json')
    from app.core import library
    monkeypatch.setattr(library, 'valid', lambda rep: True)
    entry = 'a' * 32
    report = {'job_id': entry, 'name': 'x', 'status': 'auto_ok', 'settings': {}, 'colors': []}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as z:
        z.writestr('manifest.json', json.dumps({'loomlab_backup': backup.FORMAT}))
        z.writestr('inks.json', json.dumps({'inks': [{'name': 'Lal', 'hex': '#C1392C'}]}))
        z.writestr(f'library/{entry}/report.json', json.dumps(report))
        z.writestr(f'library/{entry}/package.zip', b'0123456789' * 50_000)
    raw = bytearray(buf.getvalue())
    raw[raw.index(b'0123456789') + 100] ^= 0xFF                       # one byte of the film flipped: its CRC fails
    with pytest.raises(ValueError, match='damaged'):
        backup.restore(io.BytesIO(bytes(raw)))
    assert not (tmp_path / 'data' / 'inks.json').exists()                 # settings were not replaced first
    ok = io.BytesIO(buf.getvalue())
    assert backup.restore(ok)['library'] == 1                              # the same backup, undamaged, restores
