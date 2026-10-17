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


def test_each_clients_business_is_summed_from_the_log(cache):
    ev = lambda **k: joblog.record(**k)
    # Ravi: two designs, one approved (and re-run before: counted once, by its latest run), one waiting
    ev(event='made', job_id='r1', client='Ravi Textiles', status='auto_ok', design='rose', meters=500, quote_total=40000)
    ev(event='made', job_id='r2', client='ravi  textiles', status='auto_ok', design='rose', meters=800, quote_total=60000)
    ev(event='stage', job_id='r2', client='Ravi Textiles', stage='approved')
    ev(event='made', job_id='r3', client='Ravi Textiles', status='needs_review', design='lotus', meters=100, quote_total=9000)
    ev(event='repeat', job_id='r2', client='Ravi Textiles', meters=1200, quote_total=70000)
    # Sunil: one rejected design; a job with no client is nobody's
    ev(event='made', job_id='s1', client='Sunil', status='auto_ok', design='star', meters=50, quote_total=5000)
    ev(event='stage', job_id='s1', client='Sunil', stage='rejected')
    ev(event='made', job_id='x', client='', status='auto_ok', design='x', meters=10, quote_total=100)
    card = costing.DEFAULTS | {'clients': {'RAVI TEXTILES': {'margin_percent': 10}}}
    ravi, sunil = joblog.clients(30, card)
    assert ravi['designs'] == 2 and ravi['approved'] == 1 and ravi['waiting'] == 1 and ravi['own_rates']
    assert (ravi['approved_meters'], ravi['approved_quoted'], ravi['meters']) == (800, 60000, 900)
    assert (ravi['repeat_orders'], ravi['repeat_meters'], ravi['business']) == (1, 1200, 130000)
    assert sunil['rejected'] == 1 and sunil['business'] == 0 and not sunil['own_rates']
    assert [c['client'] for c in joblog.clients(30, card, client='sun')] == ['Sunil']


def test_the_client_ledger_endpoint(cache):
    joblog.record(event='made', job_id='a', client='Ravi', status='auto_ok', design='d', meters=5, quote_total=50)
    r = TestClient(app).get('/api/clients?days=30').json()
    assert r['days'] == 30 and r['clients'][0]['client'] == 'Ravi' and r['currency']
    assert TestClient(app).get('/api/clients?days=0').status_code == 422
