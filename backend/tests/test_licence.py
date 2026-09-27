"""Licence: one PC, one activation, checked offline with Ed25519."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import licence as L
from app.main import app

SECRET = bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60')
PUBLIC = L.public_key(SECRET)


@pytest.mark.parametrize('secret,public,msg,sig', [
    ('9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60',
     'd75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a', '',
     'e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b'),
    ('4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb',
     '3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c', '72',
     '92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00'),
])
def test_ed25519_matches_the_rfc_8032_test_vectors(secret, public, msg, sig):
    sk, m = bytes.fromhex(secret), bytes.fromhex(msg)
    assert L.public_key(sk).hex() == public
    assert L.sign(sk, m).hex() == sig
    assert L.verify(bytes.fromhex(public), m, bytes.fromhex(sig))
    assert not L.verify(bytes.fromhex(public), m + b'x', bytes.fromhex(sig))


def test_a_key_fits_only_its_pc_and_only_until_it_ends():
    key = L.issue(SECRET, '3f2a-91c0-5b7e-d4a8', 'Shree Textiles', 30, today=date(2026, 9, 1))
    ok = L.check(key, PUBLIC, '3F2A-91C0-5B7E-D4A8', today=date(2026, 9, 27))
    assert ok['valid'] and ok['mill'] == 'Shree Textiles' and ok['expires'] == '2026-10-01'
    assert 'another PC' in L.check(key, PUBLIC, '0000-0000-0000-0000', today=date(2026, 9, 27))['reason']
    assert 'ended on 2026-10-01' in L.check(key, PUBLIC, '3F2A-91C0-5B7E-D4A8', today=date(2026, 10, 2))['reason']
    forever = L.issue(SECRET, 'AAAA-BBBB-CCCC-DDDD', 'Mill', None)
    assert L.check(forever, PUBLIC, 'AAAA-BBBB-CCCC-DDDD', today=date(2040, 1, 1))['valid']


def test_a_changed_or_foreign_key_is_refused():
    key = L.issue(SECRET, 'AAAA-BBBB-CCCC-DDDD', 'Mill', 365)
    tag, body, sig = key.split('.')
    forged = L._b64(L._unb64(body).replace(b'Mill', b'Evil'))
    assert 'not genuine' in L.check(f'{tag}.{forged}.{sig}', PUBLIC, 'AAAA-BBBB-CCCC-DDDD')['reason']
    other = L.issue(bytes(32), 'AAAA-BBBB-CCCC-DDDD', 'Mill', 365)      # signed by someone else
    assert 'not genuine' in L.check(other, PUBLIC, 'AAAA-BBBB-CCCC-DDDD')['reason']
    assert 'not a LoomLab licence' in L.check('hello', PUBLIC, 'AAAA-BBBB-CCCC-DDDD')['reason']


def test_the_machine_code_is_stable_and_hides_the_id():
    assert L.machine_code('abc') == L.machine_code('abc') != L.machine_code('abd')
    code = L.machine_code()
    assert len(code) == 19 and code.count('-') == 3 and code == L.machine_code()


@pytest.fixture
def locked(tmp_path, monkeypatch):
    """LoomLab with a public key shipped: a licence is required."""
    pub = tmp_path / 'licence-public.key'
    pub.write_text(PUBLIC.hex())
    monkeypatch.setattr(L, 'PUBLIC_KEY_PATH', pub)
    monkeypatch.setattr(L, 'LICENCE_PATH', tmp_path / 'licence.key')
    monkeypatch.delenv('LOOMLAB_PUBLIC_KEY', raising=False)
    L._cache.clear()
    yield TestClient(app, raise_server_exceptions=False)
    L._cache.clear()


def test_without_a_public_key_loomlab_runs_open(tmp_path, monkeypatch):
    monkeypatch.setattr(L, 'PUBLIC_KEY_PATH', tmp_path / 'none.key')
    monkeypatch.delenv('LOOMLAB_PUBLIC_KEY', raising=False)
    L._cache.clear()
    c = TestClient(app)
    assert c.get('/api/licence').json()['required'] is False
    assert c.get('/api/inks').status_code == 200
    L._cache.clear()


def test_a_locked_pc_is_asked_for_a_key_then_works(locked):
    c = locked
    r = c.get('/api/inks')
    assert r.status_code == 402 and L.machine_code() in r.json()['detail']
    assert c.get('/api/health').status_code == 200                # the engine still answers
    st = c.get('/api/licence').json()
    assert st['required'] and not st['valid'] and st['machine'] == L.machine_code()
    # a key for another PC is refused and nothing is saved
    wrong = c.post('/api/licence', json={'key': L.issue(SECRET, '0000-0000-0000-0000', 'Mill', 365)})
    assert wrong.status_code == 422 and 'another PC' in wrong.json()['detail']
    assert not L.LICENCE_PATH.exists()
    # the right one activates the PC for good
    good = c.post('/api/licence', json={'key': L.issue(SECRET, L.machine_code(), 'Shree Textiles', 365)})
    assert good.status_code == 200 and good.json()['mill'] == 'Shree Textiles'
    assert L.LICENCE_PATH.exists()
    assert c.get('/api/inks').status_code == 200


def test_the_sellers_tools_make_keys_and_licences(tmp_path, capsys):
    priv, pub = tmp_path / 'private.key', tmp_path / 'public.key'
    assert L.main(['keygen', '--private', str(priv), '--public', str(pub)]) == 0
    assert L.main(['keygen', '--private', str(priv), '--public', str(pub)]) == 2     # never overwrites
    capsys.readouterr()
    assert L.main(['issue', '--machine', 'AAAA-BBBB-CCCC-DDDD', '--mill', 'Mill', '--private', str(priv)]) == 0
    key = capsys.readouterr().out.strip()
    assert L.check(key, bytes.fromhex(pub.read_text().strip()), 'AAAA-BBBB-CCCC-DDDD')['valid']
