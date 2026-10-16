"""A damaged upload (truncated, half-downloaded, empty, not an image) is the
sender's problem: a 422 that says so and what to do, never a 500 telling them
to "try fewer inks", and never an engine fault in Settings -> Help."""
import os
from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app import diagnostics
from app.core.intake import DAMAGED, EMPTY
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def _design(fmt='PNG', size=(600, 400)) -> bytes:
    im = Image.new('RGB', size, '#F4ECD8')
    d = ImageDraw.Draw(im)
    d.ellipse([60, 60, 300, 300], fill='#8A1C1C')
    d.rectangle([340, 80, 540, 320], fill='#1F4E9C')
    # some noise so the compressed data is long enough to cut in the middle
    im = Image.fromarray(np.clip(np.asarray(im, np.int16) + np.random.default_rng(1).integers(-6, 7, (size[1], size[0], 3)), 0, 255).astype(np.uint8))
    b = BytesIO(); im.save(b, fmt)
    return b.getvalue()


def _psd() -> bytes:
    from psd_tools import PSDImage
    b = BytesIO(); PSDImage.frompil(Image.open(BytesIO(_design()))).save(b)
    return b.getvalue()


def half(raw: bytes) -> bytes:
    return raw[:len(raw) // 2]


BAD = {   # name, bytes, content type, the message expected
    'truncated PNG': ('rose.png', lambda: half(_design('PNG')), 'image/png', DAMAGED),
    'truncated JPEG': ('rose.jpg', lambda: half(_design('JPEG')), 'image/jpeg', DAMAGED),
    'zero bytes': ('rose.png', lambda: b'', 'image/png', EMPTY),
    'random bytes named .png': ('rose.png', lambda: os.urandom(4096), 'image/png', DAMAGED),
    'truncated PSD': ('rose.psd', lambda: half(_psd()), 'image/vnd.adobe.photoshop', DAMAGED),
    'PSD header only': ('rose.psd', lambda: _psd()[:20], 'image/vnd.adobe.photoshop', DAMAGED),
}


@pytest.mark.parametrize('path', ['/api/image/upload', '/api/auto/upload'])
@pytest.mark.parametrize('case', list(BAD))
def test_a_damaged_upload_is_a_422_that_says_so_not_an_engine_fault(path, case):
    name, make, ctype, want = BAD[case]
    faults = len(diagnostics.recent_errors())
    r = client.post(path, files={'file': (name, make(), ctype)})
    assert r.status_code == 422, (case, r.status_code, r.text)
    assert r.json()['detail'] == want
    assert 'fewer inks' not in r.text
    assert len(diagnostics.recent_errors()) == faults          # not kept as an engine fault


@pytest.mark.parametrize('case', ['truncated PNG', 'zero bytes', 'random bytes named .png'])
def test_line_fill_and_numbering_say_which_file_is_damaged(case):
    name, make, ctype, want = BAD[case]
    good = _design()
    r = client.post('/api/fill', files={'line': (name, make(), ctype), 'ref': ('ref.png', good, 'image/png')},
                    data={'size': '400', 'method': '1'})
    assert r.status_code == 422 and r.json()['detail'] == f'The line art: {want}'
    r = client.post('/api/fill', files={'line': ('line.png', good, 'image/png'), 'ref': (name, make(), ctype)},
                    data={'size': '400', 'method': '1'})
    assert r.status_code == 422 and r.json()['detail'] == f'The reference: {want}'
    r = client.post('/api/number', files={'design': (name, make(), ctype)})
    assert r.status_code == 422 and r.json()['detail'] == f'The design: {want}'


@pytest.mark.parametrize('fmt', ['PNG', 'JPEG'])
def test_a_whole_file_still_imports(fmt):
    r = client.post('/api/image/upload', files={'file': ('rose.' + fmt.lower(), _design(fmt), f'image/{fmt.lower()}')})
    assert r.status_code == 200 and (r.json()['width'], r.json()['height']) == (600, 400)


def test_a_whole_psd_still_imports():
    r = client.post('/api/image/upload', files={'file': ('rose.psd', _psd(), 'image/vnd.adobe.photoshop')})
    assert r.status_code == 200 and r.json()['width'] == 600


def test_a_real_engine_fault_after_the_file_is_read_is_still_a_500(monkeypatch):
    from app.routes import images
    def broken(img):
        raise RuntimeError('engine bug')
    monkeypatch.setattr(images.colors, 'to_8bit', broken)
    faults = len(diagnostics.recent_errors())
    r = client.post('/api/image/upload', files={'file': ('rose.png', _design(), 'image/png')})
    assert r.status_code == 500 and 'error 500' in r.json()['detail']
    assert len(diagnostics.recent_errors()) == faults + 1      # and Help sees it


def test_an_engine_fault_while_decoding_is_not_called_damaged(monkeypatch):
    """Only the decoding step's own errors mean "damaged"; MemoryError and the
    like stay engine faults."""
    from app.core import pixels
    def boom(raw):
        raise MemoryError()
    monkeypatch.setattr(pixels, 'open_checked', boom)
    r = client.post('/api/image/upload', files={'file': ('rose.png', _design(), 'image/png')})
    assert r.status_code == 500


# -- what the people sending it are told ------------------------------------

def test_the_telegram_client_is_told_in_hinglish_to_send_the_file_again(tmp_path, monkeypatch):
    from conftest import LocalEngine
    from app.core import store
    from app.inbox_bot import BAD_FILE
    from test_bot_orders import CLIENT, OPERATOR, bot, design_msg
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'cache'); (tmp_path / 'cache').mkdir()
    b, tg = bot(tmp_path, LocalEngine())
    tg.download = lambda file_path: half(_design())
    b.handle(design_msg('500 m'))
    assert tg.texts(CLIENT)[-1] == BAD_FILE
    assert any('looks damaged or incomplete' in t for t in tg.texts(OPERATOR))     # the operator gets the engine's words


def test_the_hot_folder_puts_a_damaged_file_in_failed_with_the_reason(tmp_path):
    from conftest import LocalEngine
    from app import hot_folder as H
    logs = []
    h = H.HotFolder(LocalEngine(), tmp_path / 'Hot-Folder', {}, log=logs.append)
    (h.root / 'in' / 'rose.png').write_bytes(half(_design()))
    h.poll(); h.poll()
    why = (h.root / 'failed' / 'rose.png.why.txt').read_text(encoding='utf-8')
    assert 'looks damaged or incomplete' in why


def _multichannel_psd(w=60, h=40) -> bytes:
    """A mill's pre-separated file: Multichannel mode, two 8-bit screens, raw data."""
    import struct
    a = np.zeros((h, w), np.uint8); a[:, : w // 2] = 255
    b = np.zeros((h, w), np.uint8); b[:, w // 2:] = 255
    return (b'8BPS' + struct.pack('>H6sHIIHH', 1, b'\0' * 6, 2, h, w, 8, 7)
            + struct.pack('>I', 0) + struct.pack('>I', 0) + struct.pack('>I', 0)
            + struct.pack('>H', 0) + a.tobytes() + b.tobytes())


def test_a_whole_multichannel_psd_imports_as_screens_and_a_cut_one_is_refused():
    raw = _multichannel_psd()
    r = client.post('/api/image/upload', files={'file': ('screens.psd', raw, 'image/vnd.adobe.photoshop')})
    assert r.status_code == 200 and len(r.json()['layers']) == 2
    r = client.post('/api/image/upload', files={'file': ('screens.psd', raw[:-500], 'image/vnd.adobe.photoshop')})
    assert r.status_code == 422 and r.json()['detail'] == DAMAGED
