"""Cost and quote: ink weighed from coverage, prices from the rate card."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.core import quote as costing
from app.main import app

CARD = costing.DEFAULTS | {'wastage_percent': 0.0, 'margin_percent': 0.0, 'gst_percent': 0.0,
                           'setup_per_job': 0.0}
INKS = [{'name': 'Rani Pink 12', 'hex': '#DE1464', 'coverage': 50.0},
        {'name': 'Ink 2', 'hex': '#214440', 'coverage': 25.0}]


def test_ink_is_weighed_from_coverage_and_the_printed_area():
    q = costing.calculate(INKS, 100, CARD, fabric_width_in=39.37)   # 100 m x 1 m = 100 m2
    assert q['area_sqm'] == 100.0
    # half the cloth under pink at 80 g/m2 = 4 kg; a quarter under green = 2 kg
    assert [r['kg'] for r in q['inks']] == [4.0, 2.0]
    assert q['cost']['ink'] == 6 * 450
    assert q['cost']['screens'] == 2 * 1500
    assert q['cost']['printing'] == 100 * 2 * 6
    assert q['total'] == 2700 + 3000 + 1200 and q['per_meter'] == 69.0


def test_margin_wastage_and_gst_are_applied_once_each():
    card = CARD | {'wastage_percent': 10.0, 'margin_percent': 20.0, 'gst_percent': 5.0}
    q = costing.calculate(INKS, 100, card, fabric_width_in=39.37)
    assert [r['kg'] for r in q['inks']] == [4.4, 2.2]                 # wastage on the ink
    subtotal = q['cost']['subtotal']
    assert q['before_tax'] == pytest.approx(subtotal * 1.2, abs=0.05)   # margin inside the lines
    assert q['total'] == pytest.approx(q['before_tax'] * 1.05, abs=0.05)


def test_a_named_ink_uses_its_own_price_and_cloth_is_charged_when_set():
    card = CARD | {'ink_prices': {'rani pink 12': 600}, 'fabric_per_meter': 50.0}
    q = costing.calculate(INKS, 100, card, fabric_width_in=39.37)
    assert q['inks'][0]['per_kg'] == 600 and q['inks'][1]['per_kg'] == 450
    assert q['cost']['fabric'] == 5000


def test_the_white_under_base_is_a_screen_under_every_ink():
    q = costing.calculate(INKS, 100, CARD, fabric_width_in=39.37, underbase=True)
    assert q['screens'] == 3
    ub = q['inks'][0]
    assert ub['name'] == 'White under-base' and ub['coverage'] == 75.0 and ub['kg'] == 6.0
    assert ub['per_kg'] == CARD['underbase_ink_per_kg']


@pytest.mark.parametrize('value,text', [(0, '₹0'), (999, '₹999'), (1000, '₹1,000'),
                                        (123456, '₹1,23,456'), (12345678.4, '₹1,23,45,678')])
def test_money_is_written_the_indian_way(value, text):
    assert costing.money(value) == text


def test_the_rate_card_is_checked(tmp_path):
    card = tmp_path / 'rate-card.json'
    card.write_text('{"screen_cost": 1200, "ink_prices": {"Rani Pink 12": 620}}', encoding='utf-8')
    got = costing.load_card(card)
    assert got['screen_cost'] == 1200 and got['ink_prices'] == {'Rani Pink 12': 620}
    for bad, msg in [('{"screen_cost": -5}', 'screen_cost'), ('{"screen_cst": 5}', 'screen_cst'),
                     ('{"ink_prices": {"a": "cheap"}}', 'ink_prices'), ('{oops', 'not valid JSON')]:
        card.write_text(bad, encoding='utf-8')
        with pytest.raises(ValueError, match=msg):
            costing.load_card(card)


def test_the_shipped_rate_card_is_valid_and_matches_the_defaults():
    assert costing.load_card(costing.CARD_PATH) == costing.DEFAULTS


def test_the_quote_image_is_phone_width_and_grows_with_the_inks():
    q = costing.calculate(INKS, 500, costing.DEFAULTS)
    a = costing.quote_image(q, costing.DEFAULTS, client='Shree Textiles', design='paisley')
    q2 = costing.calculate(INKS * 4, 500, costing.DEFAULTS)
    b = costing.quote_image(q2, costing.DEFAULTS)
    assert a.width == b.width == 1080 and b.height > a.height


@pytest.fixture(scope='module')
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_quote_endpoint_prices_screens_and_returns_an_image(client):
    r = client.post('/api/quote', json={'meters': 250, 'inks': [{'name': 'Ink 1', 'hex': '#DE1464', 'coverage': 40}],
                                        'client': 'Shree Textiles'})
    assert r.status_code == 200, r.text
    q = r.json()
    assert q['screens'] == 1 and q['total'] > 0 and len(q['quote_no']) == 6
    img = Image.open(io.BytesIO(client.get(q['image_url']).content))
    assert img.width == 1080


def test_an_auto_job_can_be_quoted_by_its_id_and_auto_can_quote_itself(client):
    big = Image.new('RGB', (1600, 1000), '#F4ECD8'); ImageDraw.Draw(big).ellipse([200, 200, 900, 900], fill='#8A1C1C')
    b = io.BytesIO(); big.resize((800, 500), Image.LANCZOS).save(b, 'PNG')
    rep = client.post('/api/auto/upload', files={'file': ('d.png', b.getvalue(), 'image/png')},
                      data={'meters': '100'}).json()
    assert rep['quote']['meters'] == 100 and rep['quote']['screens'] == len(rep['inks'])
    again = client.post('/api/quote', json={'meters': 300, 'job_id': rep['job_id']}).json()
    assert again['screens'] == rep['quote']['screens'] and again['total'] > rep['quote']['total']


def test_a_quote_needs_screens_or_a_job(client):
    assert client.post('/api/quote', json={'meters': 10}).status_code == 422
    assert client.post('/api/quote', json={'meters': 0, 'inks': INKS}).status_code == 422
    assert client.post('/api/quote', json={'meters': 10, 'job_id': 'f' * 32}).status_code == 404


def test_a_regular_client_gets_their_own_rates_and_nothing_else_changes():
    card = CARD | {'clients': {'Ravi Textiles': {'margin_percent': 10.0, 'screen_cost': 1000.0}}}
    mine, name = costing.for_client(card, '  ravi textiles ')
    assert name == 'Ravi Textiles' and mine['margin_percent'] == 10 and mine['screen_cost'] == 1000
    assert mine['ink_per_kg'] == card['ink_per_kg'] and mine['gst_percent'] == card['gst_percent']
    assert costing.for_client(card, 'Sunil') == (card, None) and costing.for_client(card, '') == (card, None)
    q = costing.calculate(INKS, 100, mine, fabric_width_in=39.37)
    assert q['cost']['screens'] == 2 * 1000


@pytest.mark.parametrize('clients,msg', [
    ([], 'clients must map'), ({'': {'margin_percent': 5}}, 'client name'),
    ({'Ravi': {}}, 'at least one rate'), ({'Ravi': {'gst_percent': 0}}, 'cannot be set per client'),
    ({'Ravi': {'screen_cost': -1}}, 'screen_cost must be a number'), ({'Ravi': {'margin_percent': True}}, 'must be a number'),
    ({'Ravi': {'margin_percent': 5000}}, 'at most'), ({'Ravi': {'margin_percent': 5}, ' ravi ': {'margin_percent': 6}}, 'twice'),
])
def test_client_rates_are_checked(clients, msg):
    with pytest.raises(ValueError, match=msg):
        costing.check_card({'clients': clients})


def test_the_quote_endpoint_uses_the_clients_rates(client, tmp_path, monkeypatch):
    card = tmp_path / 'rate-card.json'
    card.write_text(json.dumps({'clients': {'Shree Textiles': {'margin_percent': 0, 'setup_per_job': 0}}}), encoding='utf-8')
    monkeypatch.setattr(costing, 'CARD_PATH', card)
    body = {'meters': 250, 'inks': [{'name': 'Ink 1', 'hex': '#DE1464', 'coverage': 40}]}
    theirs = client.post('/api/quote', json=body | {'client': 'shree textiles'}).json()
    anyone = client.post('/api/quote', json=body | {'client': 'Walk-in'}).json()
    assert theirs['client_rate'] == 'Shree Textiles' and anyone['client_rate'] is None
    assert theirs['cost']['setup'] == 0 and anyone['cost']['setup'] == costing.DEFAULTS['setup_per_job']
    assert theirs['total'] < anyone['total']
