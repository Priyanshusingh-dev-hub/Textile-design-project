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
    import io
    for n in range(3):                     # three different designs
        im = Image.new('RGB', (300, 200), '#F4ECD8')
        ImageDraw.Draw(im).ellipse([40 + 20 * n, 40, 160 + 20 * n, 160], fill='#8A1C1C')
        buf = io.BytesIO(); im.save(buf, 'PNG')
        up = c.post('/api/image/upload', files={'file': (f'rose{n}.png', buf.getvalue(), 'image/png')}).json()
        rep = c.post('/api/auto', json={'image_id': up['image_id'], 'name': f'rose{n}.png', 'meters': 100,
                                        'colors': 1 if n == 2 else None}).json()
        if n == 0:
            c.post(f"/api/jobs/{rep['job_id']}/stage", json={'stage': 'approved', 'by': 'Ravi'})
    rows = joblog.read()
    assert [r['event'] for r in rows] == ['made', 'stage', 'made', 'made']
    assert rows[0]['name'] == 'rose0.png' and float(rows[0]['quote_total']) > 0
    s = c.get('/api/stats?days=30').json()
    assert s['designs'] == 3 and s['jobs'] == 3 and s['auto_ok'] + s['needs_review'] == 3
    assert s['stages'].get('approved') == 1 and s['quoted'] > 0 and s['meters'] == 300
    assert s['hours_saved'] > 0 and s['money_saved'] > 0 and s['currency']
    # the log outlives the 48 h cache
    for p in cache.glob('auto-*'):
        p.unlink()
    assert c.get('/api/stats?days=30').json()['designs'] == 3


def test_the_estimate_follows_the_mills_own_numbers(cache):
    for i, status in enumerate(['auto_ok', 'auto_ok', 'needs_review', 'needs_review']):
        joblog.record(event='made', job_id=f'j{i}', status=status, stage='new', seconds=60, inks=5, design=f'd{i}')
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


def test_a_design_run_again_counts_once_by_its_latest_run(cache):
    joblog.record(event='made', job_id='a1', status='needs_review', seconds=30, design='rose', quote_total=1000, meters=100)
    joblog.record(event='made', job_id='a2', status='needs_review', seconds=30, design='rose', quote_total=900, meters=100)
    joblog.record(event='made', job_id='a3', status='auto_ok', seconds=30, design='rose', quote_total=800, meters=100)
    joblog.record(event='stage', job_id='a3', status='auto_ok', stage='approved')
    s = joblog.stats(30, costing.DEFAULTS | {'manual_minutes_per_design': 60, 'review_minutes_per_design': 10})
    assert (s['designs'], s['jobs'], s['auto_ok'], s['stages']) == (1, 3, 1, {'approved': 1})
    assert s['quoted'] == 800 and s['meters'] == 100
    assert s['hours_saved'] == round((60 - 1.5) / 60, 1)          # one design by hand, less 3 runs of engine time


def test_trial_runs_stay_off_the_log_and_the_dashboard(cache):
    import io
    c = TestClient(app)
    im = Image.new('RGB', (200, 120), '#F4ECD8'); ImageDraw.Draw(im).rectangle([20, 20, 90, 90], fill='#1F4E9C')
    buf = io.BytesIO(); im.save(buf, 'PNG')
    r = c.post('/api/auto/upload', data={'trial': 'true'}, files={'file': ('bench.png', buf.getvalue(), 'image/png')})
    assert r.status_code == 200 and r.json()['trial'] is True
    assert joblog.read() == [] and c.get('/api/jobs').json()['total'] == 0


def test_text_that_looks_like_a_formula_is_kept_as_text(cache):
    joblog.record(event='made', job_id='x', client='=HYPERLINK("http://evil","Click")', name='+rose.png', status='auto_ok')
    raw = joblog.log_path().read_text(encoding='utf-8-sig')
    assert "'=HYPERLINK" in raw and "'+rose.png" in raw
    assert joblog.read()[0]['client'].startswith("'=")


def test_a_log_from_an_older_version_gets_the_new_columns(cache):
    old = ['time', 'event', 'job_id', 'status']
    joblog.log_path().write_text(','.join(old) + '\n2026-09-01T10:00:00,made,old1,auto_ok\n', encoding='utf-8-sig')
    joblog.record(event='made', job_id='new1', status='needs_review', design='d1')
    rows = joblog.read()
    assert [r['job_id'] for r in rows] == ['old1', 'new1'] and rows[1]['design'] == 'd1'
