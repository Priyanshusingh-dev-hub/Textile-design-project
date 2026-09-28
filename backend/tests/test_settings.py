"""Settings screen: the rate card and auto mode's limits, edited in the app."""
import json

import pytest
from fastapi.testclient import TestClient

from app import auto as auto_mode
from app.core import quote as costing
from app.main import app

client = TestClient(app)


@pytest.fixture
def files(tmp_path, monkeypatch):
    card, cfg = tmp_path / 'rate-card.json', tmp_path / 'auto-config.json'
    card.write_text(json.dumps({'_comment': 'prices in rupees', 'screen_cost': 1200}), encoding='utf-8')
    monkeypatch.setattr(costing, 'CARD_PATH', card)
    monkeypatch.setattr(auto_mode, 'CONFIG_PATH', cfg)
    return card, cfg


def test_settings_are_read_with_defaults_for_what_the_file_leaves_out(files):
    r = client.get('/api/settings').json()
    assert r['rate_card']['error'] is None
    assert r['rate_card']['values']['screen_cost'] == 1200
    assert r['rate_card']['values']['gst_percent'] == costing.DEFAULTS['gst_percent']
    assert r['auto']['values'] == auto_mode.DEFAULTS            # no file: the defaults
    assert r['auto']['codes']['many_inks']


def test_a_saved_rate_card_is_what_the_next_quote_uses_and_keeps_its_note(files):
    card, _ = files
    values = client.get('/api/settings').json()['rate_card']['values']
    values |= {'screen_cost': 2000, 'ink_prices': {'Rani Pink 12': 620}}
    r = client.put('/api/settings/rate-card', json=values)
    assert r.status_code == 200 and r.json()['screen_cost'] == 2000
    saved = json.loads(card.read_text(encoding='utf-8'))
    assert list(saved)[0] == '_comment' and saved['_comment'] == 'prices in rupees'
    assert costing.load_card()['ink_prices'] == {'Rani Pink 12': 620}


@pytest.mark.parametrize('bad', [
    {'screen_cost': -5}, {'screen_cost': 'cheap'}, {'screen_cost': True},
    {'ink_prices': {'Rani': -1}}, {'ink_prices': {'': 10}}, {'mill_name': ''}, {'price_of_tea': 5},
])
def test_a_bad_rate_card_is_refused_and_the_file_is_left_alone(files, bad):
    card, _ = files
    before = card.read_text(encoding='utf-8')
    r = client.put('/api/settings/rate-card', json=bad)
    assert r.status_code == 422 and r.json()['detail']
    assert card.read_text(encoding='utf-8') == before


def test_auto_limits_are_saved_and_checked(files):
    _, cfg = files
    r = client.put('/api/settings/auto', json={'max_inks': 8, 'blocking': ['low_match']})
    assert r.status_code == 200
    assert auto_mode.load_config() == auto_mode.DEFAULTS | {'max_inks': 8, 'blocking': ['low_match']}
    for bad in ({'max_inks': 0}, {'max_inks': 7.5}, {'min_accuracy': 120}, {'min_source_ppi': -1},
                {'blocking': ['not_a_code']}, {'blocking': 'low_match'}):
        r = client.put('/api/settings/auto', json=bad)
        assert r.status_code == 422, bad
    assert json.loads(cfg.read_text(encoding='utf-8'))['max_inks'] == 8


def test_a_broken_file_is_shown_with_the_defaults_to_start_from(files):
    card, _ = files
    card.write_text('{not json', encoding='utf-8')
    r = client.get('/api/settings').json()['rate_card']
    assert 'not valid JSON' in r['error'] and r['values'] == costing.DEFAULTS
    assert client.put('/api/settings/rate-card', json=costing.DEFAULTS).status_code == 200
    assert costing.load_card() == costing.DEFAULTS


def test_the_shipped_files_pass_the_checks():
    costing.load_card()
    auto_mode.load_config()
