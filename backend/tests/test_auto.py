"""Auto mode: one call from design to package, with an honest status."""
import io
import json
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app import auto as auto_mode
from app.main import app


@pytest.fixture(scope='module')
def client():
    return TestClient(app, raise_server_exceptions=False)


def _png(img):
    b = io.BytesIO(); img.save(b, 'PNG'); return b.getvalue()


def _flat_design():
    """Three flat inks in big shapes, anti-aliased: nothing to worry about."""
    big = Image.new('RGB', (2400, 1600), '#F4ECD8'); d = ImageDraw.Draw(big)
    d.ellipse([200, 200, 1100, 1100], fill='#8A1C1C')
    d.rectangle([1300, 300, 2200, 1300], fill='#1B3A6B')
    return big.resize((1200, 800), Image.LANCZOS)


def _gradient():
    yy, xx = np.mgrid[0:300, 0:400]
    return Image.fromarray(np.stack([xx * 0.6, yy * 0.8, 255 - xx * 0.5], -1).clip(0, 255).astype(np.uint8))


def _upload(client, img):
    return client.post('/api/image/upload', files={'file': ('d.png', _png(img), 'image/png')}).json()['image_id']


FACTS = {'accuracy': 95.0, 'ceiling': 98.0, 'inks': 3, 'soft_edge': 2.0, 'soft_edge_limit': 6.0,
         'dot_share': 0.0, 'similar': [], 'source_ppi': None, 'grain': 0, 'repeat': [], 'small': []}


def test_a_clean_flat_design_runs_end_to_end_and_passes(client):
    r = client.post('/api/auto', json={'image_id': _upload(client, _flat_design())})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep['status'] == 'auto_ok', rep['warnings']
    assert len(rep['inks']) == 3 and rep['suggested_inks'] == 3
    assert rep['accuracy'] >= 90 and rep['texture_cleanup'] == 0
    assert set(rep['seconds']) >= {'suggest', 'reduce', 'separate', 'package'}
    # the package and the report stay available by job id
    z = zipfile.ZipFile(io.BytesIO(client.get(rep['package_url']).content))
    assert sum(n.startswith('screens/') for n in z.namelist()) == 3
    assert client.get(f"/api/auto/{rep['job_id']}").json()['status'] == 'auto_ok'


def test_a_photographic_design_needs_review(client):
    rep = client.post('/api/auto', json={'image_id': _upload(client, _gradient())}).json()
    assert rep['status'] == 'needs_review'
    codes = {w['code'] for w in rep['warnings'] if w['blocking']}
    assert 'photographic' in codes and 'low_match' in codes


def test_one_upload_request_runs_auto_mode(client):
    r = client.post('/api/auto/upload', files={'file': ('d.png', _png(_flat_design()), 'image/png')},
                    data={'width_in': '8', 'dpi': '300'})
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep['print']['width_px'] == 2400
    # 1200 px across 8 in = 150 px per inch: above the default 100
    assert 'low_resolution' not in {w['code'] for w in rep['warnings']}


def test_enlarging_a_small_file_too_far_needs_review(client):
    rep = client.post('/api/auto', json={'image_id': _upload(client, _flat_design()), 'width_in': 20}).json()
    low = [w for w in rep['warnings'] if w['code'] == 'low_resolution']
    assert low and low[0]['blocking'] and low[0]['source_ppi'] == 60.0
    assert rep['status'] == 'needs_review'


def test_thresholds_come_from_the_config_file(client, tmp_path, monkeypatch):
    cfg = tmp_path / 'auto-config.json'
    cfg.write_text(json.dumps({'max_inks': 2}))
    monkeypatch.setattr(auto_mode, 'CONFIG_PATH', cfg)
    rep = client.post('/api/auto', json={'image_id': _upload(client, _flat_design())}).json()
    assert rep['status'] == 'needs_review'
    assert [w['code'] for w in rep['warnings'] if w['blocking']] == ['many_inks']


def test_a_broken_config_is_reported_not_ignored(tmp_path):
    bad = tmp_path / 'c.json'
    bad.write_text('{"min_accuracy": 85,')
    with pytest.raises(ValueError, match='not valid JSON'):
        auto_mode.load_config(bad)
    bad.write_text('{"min_acuracy": 85}')
    with pytest.raises(ValueError, match='min_acuracy'):
        auto_mode.load_config(bad)
    assert auto_mode.load_config(tmp_path / 'missing.json') == auto_mode.DEFAULTS


def test_the_shipped_config_is_valid_and_matches_the_defaults():
    assert auto_mode.load_config(auto_mode.CONFIG_PATH) == auto_mode.DEFAULTS


@pytest.mark.parametrize('change,code', [
    ({'ceiling': 70.0}, 'photographic'), ({'accuracy': 80.0}, 'low_match'),
    ({'soft_edge': 9.0}, 'soft_edges'), ({'dot_share': 2.0}, 'tiny_dots'),
    ({'similar': [{'keep': 1, 'drop': 2, 'delta_e': 2.1, 'accuracy': 90.0}]}, 'similar_inks'),
    ({'inks': 13}, 'many_inks'), ({'source_ppi': 48.0}, 'low_resolution'),
])
def test_each_blocking_warning_stops_the_job(change, code):
    warnings, status = auto_mode.review(FACTS | change, auto_mode.DEFAULTS)
    assert status == 'needs_review' and [w['code'] for w in warnings] == [code]


@pytest.mark.parametrize('change,code', [
    ({'grain': 1}, 'grainy_source'), ({'repeat': ['left-right']}, 'seamless_repeat'),
    ({'small': [{'hex': '#123456', 'coverage': 0.4}]}, 'small_inks'),
])
def test_information_is_reported_but_passes(change, code):
    warnings, status = auto_mode.review(FACTS | change, auto_mode.DEFAULTS)
    assert status == 'auto_ok' and [w['code'] for w in warnings] == [code]
    assert not warnings[0]['blocking']


def test_dots_the_package_cleans_are_not_a_warning():
    warnings, status = auto_mode.review(FACTS | {'dot_share': None}, auto_mode.DEFAULTS)
    assert status == 'auto_ok' and warnings == []


def test_unknown_or_expired_jobs_are_404(client):
    assert client.get('/api/auto/' + 'f' * 32).status_code == 404
    assert client.get('/api/auto/' + 'f' * 32 + '/package').status_code == 404
    assert client.get('/api/auto/..%2F..%2Fetc').status_code == 404


def test_the_dashboard_lists_jobs_and_follows_their_stage(client, tmp_path, monkeypatch):
    from app.core import store
    monkeypatch.setattr(store, 'ROOT', tmp_path)          # a clean cache: only these jobs
    ok = client.post('/api/auto/upload', files={'file': ('rose.png', _png(_flat_design()), 'image/png')},
                     data={'client': 'Ravi', 'meters': '100'}).json()
    held = client.post('/api/auto', json={'image_id': _upload(client, _gradient())}).json()
    listed = client.get('/api/jobs').json()
    assert listed['total'] == 2 and listed['counts'] == {'auto_ok': 1, 'needs_review': 1}
    first = {j['job_id']: j for j in listed['jobs']}[ok['job_id']]
    assert first['name'] == 'rose.png' and first['client'] == 'Ravi' and first['stage'] == 'new'
    assert first['inks'] == 3 and first['total'] > 0 and first['warnings'] == []
    review = client.get('/api/jobs', params={'status': 'needs_review'}).json()['jobs']
    assert [j['job_id'] for j in review] == [held['job_id']]
    assert {w['code'] for w in review[0]['warnings']} >= {'photographic'}
    # the operator deals with it; the list and the report both show it
    r = client.post(f"/api/jobs/{held['job_id']}/stage", json={'stage': 'rejected', 'by': 'Operator', 'note': 'photo'})
    assert r.status_code == 200 and r.json()['history'][-1]['by'] == 'Operator'
    assert client.get('/api/jobs', params={'stage': 'new'}).json()['total'] == 1
    assert client.get(f"/api/auto/{held['job_id']}").json()['stage'] == 'rejected'


def test_a_bad_stage_or_filter_is_a_422_and_an_unknown_job_a_404(client):
    assert client.post('/api/jobs/' + 'f' * 32 + '/stage', json={'stage': 'printed'}).status_code == 422
    assert client.post('/api/jobs/' + 'f' * 32 + '/stage', json={'stage': 'approved'}).status_code == 404
    assert client.get('/api/jobs', params={'status': 'maybe'}).status_code == 422


def test_every_warning_code_has_words_in_the_dashboard_and_the_bot():
    """The owner can make any code blocking in Settings: a held job must never
    show a raw code on the dashboard or in the operator's Telegram message."""
    from pathlib import Path
    from app.bot_orders import WARN_WORDS
    jobs_ts = (Path(__file__).resolve().parents[2] / 'frontend' / 'src' / 'lib' / 'jobs.ts').read_text(encoding='utf-8')
    for code in auto_mode.TITLES:
        assert f'{code}:' in jobs_ts, code
        assert code in WARN_WORDS, code
