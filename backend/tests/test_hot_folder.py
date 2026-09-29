"""Hot folder: designs dropped in a folder come out as screens, with no one at the app."""
import json

import pytest
from PIL import Image, ImageDraw

from app import hot_folder as H
from app.bot_orders import Engine
from conftest import LocalEngine


def design(path, size=(600, 400)):
    im = Image.new('RGB', size, '#F4ECD8')
    d = ImageDraw.Draw(im)
    d.ellipse([60, 60, 300, 300], fill='#8A1C1C')
    d.rectangle([340, 80, 540, 320], fill='#1F4E9C')
    im.save(path)
    return path


@pytest.fixture
def hot(tmp_path):
    logs = []
    return H.HotFolder(LocalEngine(), tmp_path / 'Hot-Folder', {'meters': 100}, log=logs.append), logs


@pytest.mark.parametrize('name,want', [
    ('rose 30in 500m 6inks.png', {'width_in': 30.0, 'meters': 500.0, 'colors': 6}),
    ('rose_30in_1,500m.png', {'width_in': 30.0, 'meters': 1500.0}),
    ('Rani-pink-6-inks.jpg', {'colors': 6}),
    ('design 2024.png', {}),
])
def test_settings_ride_in_the_file_name(name, want):
    assert H.settings_from_name(name) == want


def test_a_dropped_design_comes_out_ready_with_everything(hot):
    h, logs = hot
    f = design(h.root / 'in' / 'rose 500m.png')
    assert h.poll() == 0                        # first look: is it still being copied?
    assert h.poll() == 1
    assert not f.exists()
    (out,) = (h.root / 'ready').iterdir()
    names = {p.name for p in out.iterdir()}
    assert names == {'rose 500m-screens.zip', 'proof.png', 'quote.png', 'report.txt', 'rose 500m.png'}
    report = (out / 'report.txt').read_text(encoding='utf-8')
    assert 'Status: auto_ok' in report and 'Inks (3' in report and 'for 500 m' in report
    assert 'taiyaar' in logs[-1]


def test_a_held_job_goes_to_check_with_the_reason(hot, tmp_path, monkeypatch):
    from app import auto as auto_mode
    cfg = tmp_path / 'auto.json'
    cfg.write_text(json.dumps({'max_inks': 1}), encoding='utf-8')
    monkeypatch.setattr(auto_mode, 'CONFIG_PATH', cfg)
    h, _ = hot
    design(h.root / 'in' / 'mandala.png')
    h.poll(); h.poll()
    (out,) = (h.root / 'check').iterdir()
    assert 'STOPS THE JOB [many_inks]' in (out / 'report.txt').read_text(encoding='utf-8')


def test_a_file_still_being_copied_waits(hot):
    h, _ = hot
    f = design(h.root / 'in' / 'big.png')
    h.poll()
    with open(f, 'ab') as fh:                   # still growing
        fh.write(b'\0' * 10)
    assert h.poll() == 0 and f.exists()
    (h.root / 'in' / 'next.png.part').write_bytes(b'half')   # a download in progress is never touched
    h.poll()
    assert (h.root / 'in' / 'next.png.part').exists()


def test_when_the_engine_is_down_files_wait_in_the_queue(tmp_path):
    logs = []
    h = H.HotFolder(Engine('http://127.0.0.1:9', timeout=2), tmp_path / 'hf', log=logs.append)
    f = design(h.root / 'in' / 'rose.png')
    h.poll(); h.poll(); h.poll()
    assert f.exists() and len(logs) == 1 and 'band' in logs[0]     # said once, file kept
    h.engine = LocalEngine()
    assert h.poll() == 1 and not f.exists()
    assert 'wapas' in logs[-1]


def test_what_cannot_be_run_goes_to_failed_with_the_reason(hot):
    h, _ = hot
    (h.root / 'in' / 'notes.txt').write_text('hello')
    (h.root / 'in' / 'broken.png').write_bytes(b'not an image at all')
    h.poll(); h.poll()
    failed = {p.name for p in (h.root / 'failed').iterdir()}
    assert {'notes.txt', 'notes.txt.why.txt', 'broken.png', 'broken.png.why.txt'} <= failed
    assert not any((h.root / 'in').iterdir())


def test_the_same_name_twice_never_overwrites(hot):
    h, _ = hot
    design(h.root / 'in' / 'rose.png'); h.poll(); h.poll()
    design(h.root / 'in' / 'rose.png'); h.poll(); h.poll()
    assert len(list((h.root / 'ready').iterdir())) == 2
