"""The design library: approved jobs kept for good, and repeat orders priced without new screens."""
import io
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.core import library, store
from app.main import app


@pytest.fixture
def c(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    return TestClient(app)


def _job(c, name='rose.png', client='Ravi Textiles', meters=500):
    im = Image.new('RGB', (300, 200), '#F4ECD8'); ImageDraw.Draw(im).ellipse([40, 40, 160, 160], fill='#8A1C1C')
    buf = io.BytesIO(); im.save(buf, 'PNG')
    up = c.post('/api/image/upload', files={'file': (name, buf.getvalue(), 'image/png')}).json()
    return c.post('/api/auto', json={'image_id': up['image_id'], 'name': name, 'client': client,
                                     'meters': meters}).json()


def test_an_approved_job_is_kept_after_the_cache_forgets_it(c, tmp_path):
    job = _job(c)
    assert c.get('/api/library').json()['total'] == 0            # not approved yet
    c.post(f"/api/jobs/{job['job_id']}/stage", json={'stage': 'approved', 'by': 'Ravi'})
    for p in list(tmp_path.glob('*.png')) + list(tmp_path.glob('auto-*')):
        p.unlink()                                                 # the 48 h cleanup came
    lib = c.get('/api/library').json()
    assert lib['total'] == 1
    e = lib['designs'][0]
    assert e['id'] == job['job_id'] and e['client'] == 'Ravi Textiles' and e['last_meters'] == 500
    assert e['has_proof'] and e['has_package'] and len(e['inks']) == len(job['inks'])
    assert c.get(f"/api/library/{e['id']}/proof").headers['content-type'] == 'image/png'
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/api/library/{e['id']}/package").content))
    assert any(n.startswith('screens/') for n in z.namelist())


def test_a_repeat_order_is_priced_without_new_screens(c):
    job = _job(c)
    c.post(f"/api/jobs/{job['job_id']}/stage", json={'stage': 'approved'})
    first = c.post('/api/quote', json={'job_id': job['job_id'], 'meters': 800}).json()
    again = c.post('/api/quote', json={'library_id': job['job_id'], 'meters': 800}).json()
    assert first['cost']['screens'] > 0 and again['cost']['screens'] == 0 and again['repeat']
    assert again['cost']['ink'] == first['cost']['ink'] and again['cost']['printing'] == first['cost']['printing']
    assert again['total'] < first['total']


def test_the_library_is_searched_by_design_or_client(c):
    for name, client in (('rose.png', 'Ravi'), ('mandala.png', 'Sunil'), ('paisley.png', 'Ravi')):
        job = _job(c, name, client)
        c.post(f"/api/jobs/{job['job_id']}/stage", json={'stage': 'approved'})
    assert c.get('/api/library?q=ravi').json()['total'] == 2
    assert [d['name'] for d in c.get('/api/library?q=MAND').json()['designs']] == ['mandala.png']


@pytest.mark.parametrize('bad', ['../etc', 'x' * 32, '0' * 31])
def test_a_bad_library_id_is_a_404(c, bad):
    assert c.get(f'/api/library/{bad}/proof').status_code in (404, 422)
    assert c.post('/api/quote', json={'library_id': bad, 'meters': 10}).status_code == 422
