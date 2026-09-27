"""Enlarge on this PC, and catch an enlargement that changed the design."""
import io
import os
import sys

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.core import enlarge as enl
from app.main import app


def _design(mode='RGB'):
    big = Image.new(mode, (800, 500), '#F4ECD8' if mode == 'RGB' else (0, 0, 0, 0)); d = ImageDraw.Draw(big)
    d.ellipse([80, 80, 400, 400], fill='#8A1C1C'); d.rectangle([480, 100, 720, 400], fill='#1B3A6B')
    d.line([0, 450, 800, 20], fill='#2D5A27', width=6)
    return big.resize((400, 250), Image.LANCZOS)


@pytest.fixture
def no_ai(monkeypatch):
    monkeypatch.setattr(enl, 'realesrgan_path', lambda: None)


def _fake_upscaler(tmp_path, monkeypatch, body):
    """A stand-in for realesrgan-ncnn-vulkan: a script taking -i IN -o OUT."""
    exe = tmp_path / 'realesrgan-ncnn-vulkan'
    exe.write_text(f'#!{sys.executable}\nimport sys\nfrom PIL import Image\n'
                   'a = sys.argv; src, dst = a[a.index("-i") + 1], a[a.index("-o") + 1]\n' + body)
    exe.chmod(0o755)
    monkeypatch.setattr(enl, 'realesrgan_path', lambda: exe)


def test_lanczos_enlarges_to_the_size_and_keeps_the_design(no_ai):
    r = enl.enlarge(_design(), (1600, 1000))
    assert r['image'].size == (1600, 1000) and r['method'] == 'lanczos'
    assert r['match'] >= 97 and r['ok'] and r['note'] == ''


def test_a_transparent_design_stays_transparent(no_ai):
    r = enl.enlarge(_design('RGBA'), (1200, 750))
    alpha = r['image'].getchannel('A')
    assert r['image'].mode == 'RGBA' and alpha.getextrema() == (0, 255)


def test_asking_for_realesrgan_without_it_says_so(no_ai):
    r = enl.enlarge(_design(), (800, 500), 'realesrgan')
    assert r['method'] == 'lanczos' and 'not installed' in r['note']


@pytest.mark.skipif(os.name == 'nt', reason='the stand-in program is a POSIX script')
def test_an_ai_upscale_is_used_and_resized_to_the_print_size(tmp_path, monkeypatch):
    _fake_upscaler(tmp_path, monkeypatch,
                   'im = Image.open(src); im.resize((im.width * 4, im.height * 4), Image.LANCZOS).save(dst)\n')
    r = enl.enlarge(_design(), (1000, 625))
    assert r['method'] == 'realesrgan' and r['image'].size == (1000, 625) and r['ok']


@pytest.mark.skipif(os.name == 'nt', reason='the stand-in program is a POSIX script')
def test_an_upscale_that_redraws_the_design_is_caught(tmp_path, monkeypatch):
    # "AI" that shifts every colour: bigger, but no longer the same design
    _fake_upscaler(tmp_path, monkeypatch,
                   'im = Image.open(src).convert("RGB").resize((1600, 1000))\n'
                   'im = Image.merge("RGB", (im.getchannel("B"), im.getchannel("R"), im.getchannel("G")))\n'
                   'im.save(dst)\n')
    r = enl.enlarge(_design(), (1600, 1000))
    assert r['method'] == 'realesrgan' and r['match'] < enl.MIN_MATCH and not r['ok']


@pytest.mark.skipif(os.name == 'nt', reason='the stand-in program is a POSIX script')
def test_a_crashing_upscaler_falls_back_to_lanczos(tmp_path, monkeypatch):
    _fake_upscaler(tmp_path, monkeypatch, 'sys.stderr.write("vkCreateInstance failed\\n"); sys.exit(1)\n')
    r = enl.enlarge(_design(), (1600, 1000))
    assert r['method'] == 'lanczos' and 'vkCreateInstance failed' in r['note'] and r['ok']


def test_enlarge_api_and_the_file_download(no_ai):
    c = TestClient(app, raise_server_exceptions=False)
    buf = io.BytesIO(); _design().save(buf, 'PNG')
    up = c.post('/api/image/upload', files={'file': ('d.png', buf.getvalue(), 'image/png')}).json()
    r = c.post('/api/image/enlarge', json={'image_id': up['image_id'], 'width_in': 4})
    assert r.status_code == 200, r.text
    big = r.json()
    assert (big['width'], big['height']) == (1200, 750) and big['ok'] and big['source_ppi'] == 100.0
    tif = c.get(f"/api/image/{big['image_id']}/file", params={'format': 'tif', 'name': 'rose'})
    assert tif.headers['content-disposition'].endswith('rose-300dpi.tif"')
    im = Image.open(io.BytesIO(tif.content))
    assert im.size == (1200, 750) and round(im.info['dpi'][0]) == 300 and im.info['compression'] == 'tiff_lzw'
    jpg = Image.open(io.BytesIO(c.get(f"/api/image/{big['image_id']}/file", params={'format': 'jpg', 'dpi': 150}).content))
    assert jpg.format == 'JPEG' and round(jpg.info['dpi'][0]) == 150
    assert c.get(f"/api/image/{big['image_id']}/file", params={'format': 'gif'}).status_code == 422
    assert c.post('/api/image/enlarge', json={'image_id': up['image_id'], 'width_in': 200}).status_code == 422
