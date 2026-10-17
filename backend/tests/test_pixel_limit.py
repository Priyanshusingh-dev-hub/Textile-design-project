"""Decompression bombs: a small file whose header claims a gigantic picture
must be refused from its header (a clear 413), never decoded, and Pillow's own
guard must stay switched on in the engine's process (textile_project, imported
in-process, used to set it to None for everyone)."""
import resource
import struct
import time
import zlib
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app.main  # noqa: F401  (imports textile_project in-process, as the engine does)
from app.core import pixels, store
from app.main import app

client = TestClient(app)


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF)


def bomb_png(w: int, h: int, pixels_too: bool = True) -> bytes:
    """A real 1-bit PNG of w x h, all black: kilobytes on disk, gigabytes once
    decoded to RGBA. pixels_too=False: the header alone (no image data)."""
    data = b''
    if pixels_too:
        z, row, parts = zlib.compressobj(9), b'\x00' * (1 + (w + 7) // 8), []
        for _ in range(h):
            parts.append(z.compress(row))
        parts.append(z.flush())
        data = _chunk(b'IDAT', b''.join(parts))
    ihdr = struct.pack('>IIBBBBB', w, h, 1, 0, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', ihdr) + data + _chunk(b'IEND', b'')


def _peak_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024     # Linux: KB


def test_the_limit_is_on_after_importing_the_engine():
    assert Image.MAX_IMAGE_PIXELS is not None
    assert Image.MAX_IMAGE_PIXELS == pixels.LIMIT == pixels.DEFAULT_MAX_IMAGE_PIXELS == 500_000_000


def test_the_default_covers_a_large_mill_repeat():
    # 2 m x 1.5 m at 300 DPI
    w, h = round(2000 / 25.4 * 300), round(1500 / 25.4 * 300)
    pixels.check((w, h))                                   # does not raise


def test_a_bomb_between_one_and_two_times_the_limit_is_refused_without_decoding():
    """625 MP: Pillow alone would only warn here and then decode 2.5 GB."""
    raw = bomb_png(25_000, 25_000)
    assert len(raw) < 200_000
    before_files, before_mb, t = set(store.ROOT.glob('*.png')), _peak_mb(), time.monotonic()
    r = client.post('/api/image/upload', files={'file': ('bomb.png', raw, 'image/png')})
    assert r.status_code == 413
    assert '25000 x 25000' in r.json()['detail'] and 'LOOMLAB_MAX_IMAGE_PIXELS' in r.json()['detail']
    assert time.monotonic() - t < 5
    assert _peak_mb() - before_mb < 300                    # decoded, it would be > 2000 MB
    assert set(store.ROOT.glob('*.png')) == before_files   # nothing stored


def test_a_header_claiming_over_twice_the_limit_is_refused_with_a_clear_413():
    r = client.post('/api/image/upload', files={'file': ('huge.png', bomb_png(40_000, 30_000, False), 'image/png')})
    assert r.status_code == 413 and 'megapixels' in r.json()['detail']


def test_auto_mode_upload_refuses_a_bomb_too():
    """/api/auto/upload: the Telegram bot, the hot folder and the MCP server all come in here."""
    r = client.post('/api/auto/upload', files={'file': ('bomb.png', bomb_png(25_000, 25_000), 'image/png')})
    assert r.status_code == 413


def test_line_fill_refuses_a_bomb():
    small = BytesIO(); Image.new('RGB', (64, 64), 'white').save(small, 'PNG')
    r = client.post('/api/fill', files={'line': ('line.png', bomb_png(25_000, 25_000), 'image/png'),
                                        'ref': ('ref.png', small.getvalue(), 'image/png')})
    assert r.status_code == 413 and r.json()['detail'].startswith('The line art')


def test_a_psd_claiming_a_gigantic_size_is_refused_from_its_header():
    header = b'8BPS' + struct.pack('>H6sHIIHH', 1, b'\0' * 6, 3, 30_000, 30_000, 8, 3)
    r = client.post('/api/image/upload', files={'file': ('huge.psd', header + b'\0' * 64, 'image/vnd.adobe.photoshop')})
    assert r.status_code == 413 and '30000 x 30000' in r.json()['detail']


def test_a_normal_image_still_imports():
    buf = BytesIO(); Image.new('RGB', (1200, 800), '#8A1C1C').save(buf, 'PNG')
    r = client.post('/api/image/upload', files={'file': ('rose.png', buf.getvalue(), 'image/png')})
    assert r.status_code == 200 and (r.json()['width'], r.json()['height']) == (1200, 800)


@pytest.mark.parametrize('env, want', [
    ({}, 500_000_000),
    ({'LOOMLAB_MAX_IMAGE_PIXELS': '800000000'}, 800_000_000),
    ({'LOOMLAB_MAX_IMAGE_PIXELS': '800_000_000'}, 800_000_000),
    ({'MAX_IMAGE_PIXELS': '300000000'}, 300_000_000),               # the older name still works
    ({'LOOMLAB_MAX_IMAGE_PIXELS': '0'}, 500_000_000),               # never "no limit"
    ({'LOOMLAB_MAX_IMAGE_PIXELS': 'none'}, 500_000_000),
    ({'LOOMLAB_MAX_IMAGE_PIXELS': '-5'}, 500_000_000),
])
def test_the_limit_can_be_changed_per_pc_but_never_switched_off(monkeypatch, env, want):
    monkeypatch.delenv('LOOMLAB_MAX_IMAGE_PIXELS', raising=False)
    monkeypatch.delenv('MAX_IMAGE_PIXELS', raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert pixels.limit_from_env() == want
