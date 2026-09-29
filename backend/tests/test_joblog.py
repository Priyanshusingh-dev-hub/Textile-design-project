"""The job log: every auto job kept for good, and the month's numbers from it."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.core import joblog, store
from app.core import quote as costing
from app.main import app


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    return tmp_path


def test_every_auto_job_and_stage_is_logged_and_counted(cache):
    c = TestClient(app)
    im = Image.new('RGB', (300, 200), '#F4ECD8'); ImageDraw.Draw(im).ellipse([40, 40, 160, 160], fill='#8A1C1C')
    import io
    buf = io.BytesIO(); im.save(buf, 'PNG')
    for n in range(3):
        up = c.post('/api/image/upload', files={'file': (f'rose{n}.png', buf.getvalue(), 'image/png')}).json()
        rep = c.post('/api/auto', json={'image_id': up['image_id'], 'name': f'rose{n}.png', 'meters': 100,
                                        'colors': 1 if n == 2 else None}).json()
        if n == 0:
            c.post(f"/api/jobs/{rep['job_id']}/stage", json={'stage': 'approved', 'by': 'Ravi'})
    rows = joblog.read()
    assert [r['event'] for r in rows] == ['made', 'stage', 'made', 'made']
    assert rows[0]['name'] == 'rose0.png' and float(rows[0]['quote_total']) > 0
    s = c.get('/api/stats?days=30').json()
    assert s['jobs'] == 3 and s['auto_ok'] + s['needs_review'] == 3
    assert s['stages'].get('approved') == 1 and s['quoted'] > 0 and s['meters'] == 300
    assert s['hours_saved'] > 0 and s['money_saved'] > 0 and s['currency']
    # the log outlives the 48 h cache
    for p in cache.glob('auto-*'):
        p.unlink()
    assert c.get('/api/stats?days=30').json()['jobs'] == 3


def test_the_estimate_follows_the_mills_own_numbers(cache):
    for i, status in enumerate(['auto_ok', 'auto_ok', 'needs_review', 'needs_review']):
        joblog.record(event='made', job_id=f'j{i}', status=status, stage='new', seconds=60, inks=5)
    card = costing.DEFAULTS | {'manual_minutes_per_design': 90, 'review_minutes_per_design': 15,
                               'staff_cost_per_hour': 180}
    s = joblog.stats(30, card)
    # 4 designs x 90 min by hand, less 2 x 15 min checking, less 4 min of engine time
    assert s['hours_saved'] == round((360 - 30 - 4) / 60, 1) and s['money_saved'] == round((326 / 60) * 180)
    assert s['auto_ok_percent'] == 50 and s['avg_seconds'] == 60


def test_old_events_fall_outside_the_window(cache):
    joblog.record(time='2020-01-01T10:00:00', event='made', job_id='old', status='auto_ok')
    joblog.record(event='made', job_id='new', status='auto_ok')
    assert joblog.stats(30, costing.DEFAULTS)['jobs'] == 1
    assert joblog.stats(30, costing.DEFAULTS, now=datetime(2020, 1, 5))['jobs'] == 1


def test_no_log_yet_is_all_zeros(cache):
    s = joblog.stats(7, costing.DEFAULTS)
    assert s['jobs'] == 0 and s['auto_ok_percent'] == 0 and s['hours_saved'] == 0
