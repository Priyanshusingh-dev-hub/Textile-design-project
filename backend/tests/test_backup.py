"""Backup and restore: the mill's library, log, inks and settings survive a new PC."""
import io
import json
import shutil
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app import auto as auto_mode
from app.core import inks as ink_library
from app.core import joblog, library, store
from app.core import quote as costing
from app.main import app


@pytest.fixture
def pc(tmp_path, monkeypatch):
    """A mill PC: its own data folder and settings files."""
    def setup(name):
        root = tmp_path / name
        root.mkdir()
        monkeypatch.setattr(store, 'ROOT', root / 'data')
        (root / 'data').mkdir()
        monkeypatch.setattr(ink_library, 'LIBRARY', root / 'data' / 'inks.json')
        monkeypatch.setattr(costing, 'CARD_PATH', root / 'rate-card.json')
        monkeypatch.setattr(auto_mode, 'CONFIG_PATH', root / 'auto-config.json')
        return root
    return setup


def _approved_job(c, name='rose.png'):
    im = Image.new('RGB', (300, 200), '#F4ECD8'); ImageDraw.Draw(im).ellipse([40, 40, 160, 160], fill='#8A1C1C')
    buf = io.BytesIO(); im.save(buf, 'PNG')
    up = c.post('/api/image/upload', files={'file': (name, buf.getvalue(), 'image/png')}).json()
    job = c.post('/api/auto', json={'image_id': up['image_id'], 'name': name, 'meters': 100}).json()
    c.post(f"/api/jobs/{job['job_id']}/stage", json={'stage': 'approved', 'by': 'Ravi'})
    return job


def test_everything_comes_back_on_a_new_pc(pc):
    c = TestClient(app)
    pc('old')
    job = _approved_job(c)
    c.put('/api/inks', json={'inks': [{'name': 'Rani Pink 12', 'hex': '#DE1464'}]})
    c.put('/api/settings/rate-card', json=costing.DEFAULTS | {'screen_cost': 2100})
    c.put('/api/settings/auto', json={'max_inks': 9})
    r = c.get('/api/backup')
    assert r.status_code == 200 and 'loomlab-backup-' in r.headers['content-disposition']
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert {'manifest.json', 'inks.json', 'job-log.csv', 'settings/rate-card.json',
            f"library/{job['job_id']}/package.zip"} <= set(names)

    pc('new')                                              # a fresh LoomLab
    assert c.get('/api/library').json()['total'] == 0
    got = c.post('/api/backup/restore', files={'file': ('b.zip', r.content, 'application/zip')}).json()
    assert got['library'] == 1 and got['inks'] == 1 and got['rate_card'] and got['auto_limits']
    assert got['job_log_rows_added'] == 2                  # made + approved
    assert c.get('/api/library').json()['designs'][0]['id'] == job['job_id']
    assert c.get('/api/inks').json()['inks'][0]['name'] == 'Rani Pink 12'
    assert costing.load_card()['screen_cost'] == 2100 and auto_mode.load_config()['max_inks'] == 9
    assert c.post('/api/quote', json={'library_id': job['job_id'], 'meters': 50}).json()['repeat']
    # restoring twice adds no second copy of the log
    again = c.post('/api/backup/restore', files={'file': ('b.zip', r.content, 'application/zip')}).json()
    assert again['job_log_rows_added'] == 0 and len(joblog.read()) == 2


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for n, data in files.items():
            z.writestr(n, data)
    return buf.getvalue()


@pytest.mark.parametrize('files,why', [
    (None, 'not a zip'),
    ({'hello.txt': 'x'}, 'not a LoomLab backup'),
    ({'manifest.json': json.dumps({'loomlab_backup': 99})}, 'different LoomLab version'),
    ({'manifest.json': json.dumps({'loomlab_backup': 1}),
      'settings/rate-card.json': json.dumps({'screen_cost': -5})}, 'screen_cost'),
    ({'manifest.json': json.dumps({'loomlab_backup': 1}),
      'library/' + 'a' * 32 + '/proof.png': b'x'}, 'has no report'),
    ({'manifest.json': json.dumps({'loomlab_backup': 1}),
      'library/' + 'a' * 32 + '/report.json': json.dumps({'job_id': 'b' * 32, 'inks': []})}, 'damaged'),
])
def test_a_bad_backup_is_refused_and_nothing_is_written(pc, files, why):
    c = TestClient(app)
    root = pc('pc')
    c.put('/api/settings/rate-card', json=costing.DEFAULTS | {'screen_cost': 1800})
    body = b'not a zip at all' if files is None else _zip(files)
    r = c.post('/api/backup/restore', files={'file': ('b.zip', body, 'application/zip')})
    assert r.status_code == 422 and why in r.text
    assert costing.load_card()['screen_cost'] == 1800 and not (root / 'data' / 'library').exists()


def test_paths_outside_the_known_files_are_ignored(pc):
    c = TestClient(app)
    root = pc('pc')
    body = _zip({'manifest.json': json.dumps({'loomlab_backup': 1}), '../../evil.txt': 'x',
                 'library/../../evil2.txt': 'x', 'library/' + 'a' * 32 + '/evil.exe': 'x'})
    assert c.post('/api/backup/restore', files={'file': ('b.zip', body, 'application/zip')}).status_code == 200
    assert not list(root.parent.rglob('evil*'))


def test_a_film_zip_too_big_to_restore_is_left_out_and_the_entry_says_so(pc, monkeypatch):
    from app.core import backup
    c = TestClient(app)
    pc('old')
    job = _approved_job(c)
    monkeypatch.setattr(backup, 'MAX_FILE', 10)                 # every film zip and proof is "too big"
    body = c.get('/api/backup').content
    z = zipfile.ZipFile(io.BytesIO(body))
    assert f"library/{job['job_id']}/package.zip" not in z.namelist()
    assert f"library/{job['job_id']}/package.zip" in json.loads(z.read('manifest.json'))['skipped_too_big']
    pc('new')
    c.post('/api/backup/restore', files={'file': ('b.zip', body, 'application/zip')})
    e = c.get('/api/library').json()['designs'][0]
    assert not e['has_package'] and not e['has_proof']          # no "⬇ Films" for films it does not have


def test_a_huge_text_file_is_refused_before_it_is_read(pc, monkeypatch):
    from app.core import backup
    c = TestClient(app)
    pc('pc')
    monkeypatch.setattr(backup, 'MAX_LOG', 10)
    body = _zip({'manifest.json': json.dumps({'loomlab_backup': 1}), 'job-log.csv': 'time,event\n' * 5})
    r = c.post('/api/backup/restore', files={'file': ('b.zip', body, 'application/zip')})
    assert r.status_code == 422 and 'larger than LoomLab restores' in r.text


def test_a_library_order_without_its_date_does_not_break_the_list(pc):
    c = TestClient(app)
    pc('pc')
    job = _approved_job(c)
    path = library.folder(job['job_id']) / 'report.json'
    rep = json.loads(path.read_text(encoding='utf-8'))
    rep['repeat_orders'] = [{'meters': 500}, 'junk', {'meters': 300, 'at': '2026-09-29T10:00:00', 'x': 1}]
    path.write_text(json.dumps(rep), encoding='utf-8')
    e = c.get('/api/library').json()['designs'][0]
    assert e['repeats'] == 1 and e['last_repeat'] == {'meters': 300, 'at': '2026-09-29T10:00:00'}
