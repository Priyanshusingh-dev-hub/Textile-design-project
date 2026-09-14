from io import BytesIO
from zipfile import ZipFile
import numpy as np
import pytest
from PIL import Image
from app.color_engine.engine import analyze, reduce, rgb_lab
from app.repeat_engine.engine import seam_score, create
from app.separation_engine.engine import composite_masks, soft_create, to_print_ready
from app.project_engine import engine as projects
from app.core.archive import build_zip
from app.core import psd_import
from app.halftone_engine import engine as halftone

def fixture(): return Image.new('RGB',(20,20),'#D84876')
def test_color_analysis(): assert len(analyze(fixture(),2)) == 2
def test_reduction(): assert reduce(fixture(),2).size == (20,20)
def test_lab_is_perceptual_shape(): assert rgb_lab(np.array([255,0,0])).shape == (3,)
def test_repeat_dimensions(): assert create(fixture(),3,2,'grid').size == (60,40)
def test_seam_score(): assert seam_score(fixture())['score'] == 0

def _full_mask():
    return Image.new('RGBA',(10,10),(0,0,0,255))

def test_opacity_changes_composite_output():
    """Fix 1: opacity must actually change the composited pixel values."""
    full = composite_masks([(_full_mask(),'#FF0000',100)], (10,10))
    half = composite_masks([(_full_mask(),'#FF0000',50)], (10,10))
    full_alpha = np.asarray(full)[:,:,3]
    half_alpha = np.asarray(half)[:,:,3]
    assert full_alpha.mean() == 255
    assert half_alpha.mean() == pytest.approx(127.5, abs=1)
    assert not np.array_equal(full_alpha, half_alpha)

def test_opacity_zero_is_fully_transparent():
    invisible = composite_masks([(_full_mask(),'#00FF00',0)], (10,10))
    assert np.asarray(invisible)[:,:,3].max() == 0

def test_project_save_then_load_round_trip(tmp_path, monkeypatch):
    """Fix 2: load must actually retrieve what save wrote, not echo input."""
    monkeypatch.setattr(projects, 'DATA_DIR', tmp_path)
    data = {'version':1,'image_id':'abc123','palette':['#FF0000','#00FF00'],
            'mappings':[],'repeat':{'mode':'brick'},'canvas':{}}
    projects.save(data)
    loaded = projects.load('abc123')
    assert loaded == data

def test_project_load_missing_raises():
    with pytest.raises(FileNotFoundError):
        projects.load('does-not-exist-xyz')

def test_build_zip_contains_one_png_per_entry():
    data = build_zip([('Ink 1', fixture()), ('composite', fixture())])
    with ZipFile(BytesIO(data)) as zf:
        names = zf.namelist()
        assert names == ['Ink-1.png', 'composite.png']
        for name in names:
            assert Image.open(BytesIO(zf.read(name))).size == (20, 20)

def test_build_zip_deduplicates_colliding_names():
    data = build_zip([('Ink 1', fixture()), ('Ink 1', fixture())])
    with ZipFile(BytesIO(data)) as zf:
        assert zf.namelist() == ['Ink-1.png', 'Ink-1-2.png']

def test_is_psd_detects_magic_header():
    assert psd_import.is_psd(b'8BPS' + b'\x00' * 20) is True

def test_is_psd_rejects_other_formats():
    png_bytes = BytesIO(); fixture().save(png_bytes, format='PNG')
    assert psd_import.is_psd(png_bytes.getvalue()) is False
    assert psd_import.is_psd(b'') is False

def test_open_psd_returns_rgba_composite(monkeypatch):
    """Stub PSDImage.open so this doesn't need a real binary PSD fixture."""
    class FakePSD:
        def composite(self):
            return fixture()
    monkeypatch.setattr(psd_import.PSDImage, 'open', staticmethod(lambda _: FakePSD()))
    result = psd_import.open_psd(b'8BPS-fake-bytes')
    assert result.mode == 'RGBA'
    assert result.size == (20, 20)

def test_open_psd_raises_value_error_on_corrupt_data(monkeypatch):
    def boom(_): raise Exception('bad psd')
    monkeypatch.setattr(psd_import.PSDImage, 'open', staticmethod(boom))
    with pytest.raises(ValueError):
        psd_import.open_psd(b'8BPS-corrupt')

def test_open_psd_raises_value_error_when_no_composite(monkeypatch):
    class EmptyPSD:
        def composite(self):
            return None
    monkeypatch.setattr(psd_import.PSDImage, 'open', staticmethod(lambda _: EmptyPSD()))
    with pytest.raises(ValueError):
        psd_import.open_psd(b'8BPS-empty')

def test_soft_create_alphas_sum_to_full_opacity_per_pixel():
    """Every pixel's weights across palette colors are normalized to sum to
    1, so the per-color alphas at any pixel should sum to ~255."""
    image = Image.new('RGB', (10, 10), '#D84876')
    layers = soft_create(image, ['#D84876', '#204060'])
    alphas = [np.asarray(layer)[:, :, 3].astype(int) for _, layer, _, _ in layers]
    total = alphas[0] + alphas[1]
    assert np.all(np.abs(total.astype(int) - 255) <= 1)

def test_soft_create_favors_the_closer_color():
    image = Image.new('RGB', (10, 10), '#D84876')
    layers = soft_create(image, ['#D84876', '#204060'])
    exact_match_alpha = np.asarray(layers[0][1])[:, :, 3].mean()
    far_color_alpha = np.asarray(layers[1][1])[:, :, 3].mean()
    assert exact_match_alpha > far_color_alpha

def test_halftone_full_intensity_mask_produces_dots():
    mask = Image.new('RGBA', (40, 40), (0, 0, 0, 255))
    result = halftone.apply(mask, cell_size=8, angle=0)
    assert result.size == (40, 40)
    alpha = np.asarray(result)[:, :, 3]
    assert alpha.max() == 255
    assert alpha.mean() > 0

def test_halftone_empty_mask_is_blank():
    mask = Image.new('RGBA', (40, 40), (0, 0, 0, 0))
    result = halftone.apply(mask, cell_size=8, angle=45)
    assert np.asarray(result)[:, :, 3].max() == 0

def test_halftone_lower_intensity_yields_less_ink_than_full():
    full = Image.new('RGBA', (40, 40), (0, 0, 0, 255))
    half = Image.new('RGBA', (40, 40), (0, 0, 0, 128))
    full_cov = (np.asarray(halftone.apply(full, cell_size=8, angle=0))[:, :, 3] > 0).mean()
    half_cov = (np.asarray(halftone.apply(half, cell_size=8, angle=0))[:, :, 3] > 0).mean()
    assert half_cov < full_cov

def test_to_print_ready_full_ink_is_black():
    mask = Image.new('RGBA', (10, 10), (0, 0, 0, 255))
    screen = to_print_ready(mask)
    assert screen.mode == 'L'
    assert np.asarray(screen).max() == 0

def test_to_print_ready_no_ink_is_white():
    mask = Image.new('RGBA', (10, 10), (0, 0, 0, 0))
    screen = to_print_ready(mask)
    assert np.asarray(screen).min() == 255

def test_build_zip_tiff_format_uses_tif_extension_and_dpi():
    screen = to_print_ready(Image.new('RGBA', (10, 10), (0, 0, 0, 255)))
    data = build_zip([('Ink 1', screen)], fmt='tiff', dpi=300)
    with ZipFile(BytesIO(data)) as zf:
        assert zf.namelist() == ['Ink-1.tif']
        loaded = Image.open(BytesIO(zf.read('Ink-1.tif')))
        assert loaded.mode == 'L'
        assert loaded.info.get('dpi') == (300.0, 300.0)

class _FakeMultichannelParsed:
    class header:
        color_mode = psd_import.ColorMode.MULTICHANNEL
        depth = 8
        width = 4
        height = 3
    class image_resources:
        @staticmethod
        def get_data(key):
            return ['Screen A', 'Screen B']
    class image_data:
        @staticmethod
        def get_data(header):
            size = header.width * header.height
            return [bytes([10]) * size, bytes([200]) * size]

def test_open_psd_any_extracts_named_multichannel_screens(monkeypatch):
    monkeypatch.setattr(psd_import.RawPSD, 'read', staticmethod(lambda _: _FakeMultichannelParsed()))
    kind, channels = psd_import.open_psd_any(b'8BPS-fake')
    assert kind == 'channels'
    assert [name for name, _ in channels] == ['Screen A', 'Screen B']
    assert channels[0][1].size == (4, 3)
    assert np.asarray(channels[0][1]).mean() == 10
    assert np.asarray(channels[1][1]).mean() == 200

def test_open_psd_any_falls_back_to_flattened_image_for_rgb(monkeypatch):
    class FakeRGBParsed:
        class header:
            color_mode = psd_import.ColorMode.RGB
    monkeypatch.setattr(psd_import.RawPSD, 'read', staticmethod(lambda _: FakeRGBParsed()))
    monkeypatch.setattr(psd_import, 'open_psd', lambda raw: fixture().convert('RGBA'))
    kind, image = psd_import.open_psd_any(b'8BPS-fake')
    assert kind == 'image'
    assert image.mode == 'RGBA'

def test_open_psd_any_rejects_non_8bit_multichannel(monkeypatch):
    class Fake16BitParsed:
        class header:
            color_mode = psd_import.ColorMode.MULTICHANNEL
            depth = 16
    monkeypatch.setattr(psd_import.RawPSD, 'read', staticmethod(lambda _: Fake16BitParsed()))
    with pytest.raises(ValueError):
        psd_import.open_psd_any(b'8BPS-fake')
