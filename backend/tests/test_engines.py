from io import BytesIO
from zipfile import ZipFile
import numpy as np
import pytest
from PIL import Image, ImageFilter
from app.color_engine.engine import analyze, reduce, rgb_lab
from app.repeat_engine.engine import seam_score, create
from app.separation_engine.engine import composite_masks, soft_create, to_print_ready
from app.separation_engine.engine import create as separation_create
from app.separation_engine.engine import plate
from app.project_engine import engine as projects
from app.core.archive import build_zip
from app.core import psd_import
from app.halftone_engine import engine as halftone

def fixture(): return Image.new('RGB',(20,20),'#D84876')
def _two_color():
    a=np.zeros((20,20,3),dtype=np.uint8); a[:,:10]=(216,72,118); a[:,10:]=(40,64,96); return Image.fromarray(a)
def test_color_analysis(): assert len(analyze(_two_color(),2)) == 2
def test_analyze_drops_empty_bands_for_solid_image(): assert len(analyze(fixture(),5)) == 1

def test_analyze_is_sorted_by_coverage_most_to_least():
    # 60% red, 30% green, 10% blue — analyze must rank them in that order
    a = np.zeros((10, 10, 3), dtype=np.uint8)
    a[:6] = (200, 30, 30); a[6:9] = (30, 160, 30); a[9:] = (30, 30, 200)
    pal = analyze(Image.fromarray(a), 3)
    covs = [p.coverage for p in pal]
    assert covs == sorted(covs, reverse=True)
    assert covs[0] == pytest.approx(60, abs=1)
    assert covs[-1] == pytest.approx(10, abs=1)

def test_reduce_returns_exactly_n_colors():
    a = np.zeros((10, 10, 3), dtype=np.uint8)
    a[:6] = (200, 30, 30); a[6:9] = (30, 160, 30); a[9:] = (30, 30, 200)
    out = np.asarray(reduce(Image.fromarray(a), 3).convert('RGB')).reshape(-1, 3)
    uniq = np.unique(out, axis=0)
    assert len(uniq) == 3
def test_reduction(): assert reduce(fixture(),2).size == (20,20)

def test_reduce_keeps_distinct_minor_color_over_near_duplicate():
    # a big red field, a near-identical second red (should merge away first),
    # and a small but perceptually distinct blue (should survive to k=2)
    a = np.zeros((10, 10, 3), dtype=np.uint8)
    a[:7] = (200, 30, 30)      # 70% red
    a[7:9] = (210, 40, 40)     # 20% almost-the-same red -> least important, merges first
    a[9:] = (30, 30, 200)      # 10% distinct blue -> important, must remain
    pal = analyze(Image.fromarray(a), 2)
    assert len(pal) == 2
    labs = [rgb_lab(np.array(p.rgb, dtype=np.uint8)) for p in pal]
    # one surviving colour must be clearly blue-ish (b* strongly negative),
    # proving the distinct minority colour was kept, not the duplicate red
    assert min(l[2] for l in labs) < -40

def test_least_important_is_merged_first_by_coverage_and_similarity():
    from app.color_engine.engine import _merge_to
    import numpy as np
    centers = np.array([[200, 30, 30], [205, 35, 35], [30, 30, 200]], dtype=float)
    counts = np.array([500.0, 20.0, 300.0])  # the 2nd (rare + near-duplicate) is least important
    groups = _merge_to(centers, counts, 2)
    # the two near-identical reds (indices 0 and 1) end up in one group;
    # the distinct blue (index 2) stays on its own
    sizes = sorted(len(g) for g in groups)
    assert sizes == [1, 2]
    blue_group = [g for g in groups if g == [2]]
    assert blue_group, 'the distinct blue must survive as its own colour'

def test_antialiased_edges_do_not_add_a_muddy_fringe_colour():
    # a red disc and a green disc on cream, blurred so every shape edge is an
    # anti-aliased transition band (like any AI-render or scan). The palette
    # must be the three real colours, NOT a muddy tan/olive blend ink sitting
    # in the transition band -- that fringe ink is what made dirty overlap plates.
    a = np.full((120, 120, 3), (235, 222, 184), np.uint8)
    yy, xx = np.mgrid[0:120, 0:120]
    a[(xx - 40) ** 2 + (yy - 40) ** 2 <= 25 ** 2] = (200, 70, 58)   # red
    a[(xx - 85) ** 2 + (yy - 85) ** 2 <= 20 ** 2] = (60, 110, 70)   # green
    img = Image.fromarray(a).filter(ImageFilter.GaussianBlur(1.8))
    reals = [rgb_lab(np.array(c, np.uint8)) for c in [(235, 222, 184), (200, 70, 58), (60, 110, 70)]]
    for p in analyze(img, 4):
        if p.coverage < 1.5:
            continue  # ignore negligible residuals
        lab = rgb_lab(np.array(p.rgb, np.uint8))
        d = min(float(np.linalg.norm(lab - r)) for r in reals)
        assert d < 22, f'{p.hex} ({p.coverage}%) is a muddy fringe colour (LAB dist {d:.1f} from every real colour)'

def test_lab_is_perceptual_shape(): assert rgb_lab(np.array([255,0,0])).shape == (3,)

def test_delta_e2000_matches_reference_values():
    # Sharma et al. CIEDE2000 verification pairs (LAB in, dE2000 out)
    from app.color_engine.engine import delta_e2000
    cases = [
        ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
        ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
        ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
        ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ]
    for lab1, lab2, expected in cases:
        got = float(delta_e2000(np.array(lab1), np.array(lab2)))
        assert got == pytest.approx(expected, abs=1e-3)

def test_reconstruction_accuracy_perfect_for_exact_palette():
    from app.color_engine.engine import reconstruction_accuracy
    a = np.zeros((10, 10, 3), dtype=np.uint8)
    a[:, :5] = (216, 72, 118); a[:, 5:] = (40, 64, 96)
    de, acc = reconstruction_accuracy(Image.fromarray(a), ['#D84876', '#284060'])
    assert de == pytest.approx(0.0, abs=0.5)
    assert acc >= 99.0

def test_reconstruction_accuracy_drops_when_palette_is_wrong():
    from app.color_engine.engine import reconstruction_accuracy
    a = np.zeros((10, 10, 3), dtype=np.uint8)
    a[:, :5] = (216, 72, 118); a[:, 5:] = (40, 64, 96)
    de_good, acc_good = reconstruction_accuracy(Image.fromarray(a), ['#D84876', '#284060'])
    de_bad, acc_bad = reconstruction_accuracy(Image.fromarray(a), ['#FFFFFF', '#000000'])
    assert de_bad > de_good
    assert acc_bad < acc_good

def test_kpp_init_returns_k_distinct_seeds():
    from app.color_engine.engine import _kpp_init
    pts = np.array([[0., 0, 0], [100, 0, 0], [0, 100, 0], [0, 0, 100], [50, 50, 50]])
    seeds = _kpp_init(pts, 3, np.random.RandomState(42))
    assert len(seeds) == 3
    # deterministic under the fixed seed
    seeds2 = _kpp_init(pts, 3, np.random.RandomState(42))
    assert np.array_equal(seeds, seeds2)

def test_delta_e2000_identical_colors_is_zero():
    from app.color_engine.engine import delta_e2000
    lab = np.array([53.2, 80.1, 67.2])
    assert float(delta_e2000(lab, lab)) == pytest.approx(0.0, abs=1e-6)

def test_delta_e2000_broadcasts_pairwise_matrix():
    from app.color_engine.engine import delta_e2000
    labs = np.array([[50.0, 2.0, -80.0], [50.0, 0.0, -82.0], [60.0, -34.0, 36.0]])
    d = delta_e2000(labs[:, None, :], labs[None, :, :])
    assert d.shape == (3, 3)
    assert np.allclose(np.diag(d), 0, atol=1e-6)
    assert d[0, 1] < d[0, 2]  # the two blues are closer than blue vs green
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

def test_project_pack_then_unpack_round_trip():
    """A .textileproj carries its own images, so it reopens without the
    server's temporary image store."""
    original, current, layer = _two_color(), fixture(), _full_mask()
    meta = {'name': 'Rose border', 'palette': [{'hex': '#FF0000', 'rgb': [255, 0, 0], 'pixels': 5, 'coverage': 50.0}],
            'settings': {'repeatMode': 'brick'}, 'layers': [{'name': 'Ink 1', 'color': '#FF0000', 'coverage': 100.0}]}
    raw = projects.pack(meta, original, current, [layer])
    loaded, o, c, layers = projects.unpack(raw)
    assert loaded['name'] == 'Rose border' and loaded['settings'] == {'repeatMode': 'brick'}
    assert loaded['palette'] == meta['palette']
    assert np.array_equal(np.asarray(o), np.asarray(original.convert('RGBA')))
    assert np.array_equal(np.asarray(c), np.asarray(current.convert('RGBA')))
    assert len(layers) == 1 and layers[0][0]['color'] == '#FF0000'
    assert np.array_equal(np.asarray(layers[0][1]), np.asarray(layer))

def test_project_unpack_rejects_non_project_files():
    with pytest.raises(ValueError):
        projects.unpack(b'not a zip at all')
    other = BytesIO()
    with ZipFile(other, 'w') as zf:
        zf.writestr('project.json', '{"something": "else"}')
    with pytest.raises(ValueError):
        projects.unpack(other.getvalue())

def test_project_unpack_reports_missing_image():
    raw = BytesIO()
    with ZipFile(raw, 'w') as zf:
        zf.writestr('project.json', '{"format": "loomlab-project", "version": 2, "image": "images/current.png"}')
    with pytest.raises(ValueError, match='missing'):
        projects.unpack(raw.getvalue())

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

def _speckled_image():
    """A solid pink field with one stray dark-blue pixel — stands in for the
    isolated mis-assigned pixels that scan noise produces."""
    a = np.full((20, 20, 3), (216, 72, 118), dtype=np.uint8)  # #D84876
    a[10, 10] = (32, 64, 96)  # one stray #204060 pixel
    return Image.fromarray(a)

def test_separation_cleanup_removes_stray_speckle():
    palette = ['#D84876', '#204060']
    raw = separation_create(_speckled_image(), palette, cleanup=0)
    cleaned = separation_create(_speckled_image(), palette, cleanup=2)
    # index 1 is the blue ink; the lone stray pixel gives it coverage when
    # cleanup is off, and the mode filter absorbs it when cleanup is on.
    assert raw[1][3] > 0
    assert cleaned[1][3] == 0

def test_separation_cleanup_off_matches_raw_assignment():
    palette = ['#D84876', '#204060']
    layers = separation_create(_speckled_image(), palette, cleanup=0)
    assert len(layers) == 2
    assert layers[0][3] > 90  # pink still dominates the field

def test_build_zip_png_embeds_dpi():
    data = build_zip([('Ink 1', fixture())], fmt='png', dpi=300)
    with ZipFile(BytesIO(data)) as zf:
        loaded = Image.open(BytesIO(zf.read('Ink-1.png')))
        dpi = loaded.info.get('dpi')  # PNG stores pixels-per-metre, so allow rounding
        assert dpi is not None
        assert dpi[0] == pytest.approx(300, abs=1)

def test_plate_renders_ink_on_white():
    # a full-ink mask should give a solid ink-coloured plate
    full = Image.new('RGBA', (8, 8), (0, 0, 0, 255))
    p = plate(full, '#A02B28')
    assert p.mode == 'RGB'
    assert np.asarray(p)[0, 0].tolist() == [160, 43, 40]
    # an empty mask should give a white plate
    empty = Image.new('RGBA', (8, 8), (0, 0, 0, 0))
    assert np.asarray(plate(empty, '#A02B28')).min() == 255

def _quadrants(w=8, h=6):
    """A tile whose every pixel is unique, so placement and flips are checkable."""
    a = np.zeros((h, w, 4), dtype=np.uint8)
    a[:, :, 0] = np.arange(w)[None, :] * 20
    a[:, :, 1] = np.arange(h)[:, None] * 30
    a[:, :, 3] = 255
    return Image.fromarray(a)

@pytest.mark.parametrize('mode', ['grid', 'brick', 'half-drop', 'mirror'])
def test_repeat_leaves_no_transparent_gaps(mode):
    out = np.asarray(create(_quadrants(), 4, 3, mode))
    assert out.shape[:2] == (18, 32)
    assert out[:, :, 3].min() == 255

def test_half_drop_shifts_alternate_columns_down_by_half_a_tile():
    tile = np.asarray(_quadrants(8, 6)); out = np.asarray(create(_quadrants(8, 6), 2, 2, 'half-drop'))
    assert np.array_equal(out[0:6, 0:8], tile)                 # column 0 unshifted
    assert np.array_equal(out[3:9, 8:16], tile)                # column 1 dropped by h/2
    assert np.array_equal(out[0:3, 8:16], tile[3:6])           # wrapped tile fills the top
    assert np.array_equal(out[6:12, 0:8], tile)                # rows are NOT shifted sideways

def test_brick_shifts_alternate_rows_sideways_by_half_a_tile():
    tile = np.asarray(_quadrants(8, 6)); out = np.asarray(create(_quadrants(8, 6), 2, 2, 'brick'))
    assert np.array_equal(out[0:6, 0:8], tile)
    assert np.array_equal(out[6:12, 4:12], tile)
    assert np.array_equal(out[6:12, 0:4], tile[:, 4:8])

def test_mirror_repeat_reflects_on_both_axes():
    tile = np.asarray(_quadrants(8, 6)); out = np.asarray(create(_quadrants(8, 6), 2, 2, 'mirror'))
    assert np.array_equal(out[0:6, 8:16], tile[:, ::-1])
    assert np.array_equal(out[6:12, 0:8], tile[::-1, :])
    assert np.array_equal(out[6:12, 8:16], tile[::-1, ::-1])
    assert np.array_equal(out[:, 7], out[:, 8]) and np.array_equal(out[5], out[6])  # seamless joins

def test_transparent_ground_is_read_as_white_not_black():
    a = np.zeros((20, 20, 4), dtype=np.uint8)       # fully transparent (0,0,0,0) ground
    a[5:15, 5:15] = (200, 30, 40, 255)               # one red motif
    palette = [c.hex for c in analyze(Image.fromarray(a), 4)]
    assert '#000000' not in palette
    assert '#FFFFFF' in palette

def test_separation_large_palette_matches_nearest_colour():
    a = np.zeros((30, 30, 3), dtype=np.uint8)
    hexes = ['#%02X%02X%02X' % (i * 12, 255 - i * 12, (i * 37) % 256) for i in range(20)]
    for i, hx in enumerate(hexes):
        a[i:i + 1] = [int(hx[j:j + 2], 16) for j in (1, 3, 5)]
    layers = separation_create(Image.fromarray(a), hexes, cleanup=0)
    for i, (_, layer, _, _) in enumerate(layers):
        assert np.asarray(layer)[i, :, 3].min() == 255

def _ink(mask_bool):
    a = np.zeros((*mask_bool.shape, 4), dtype=np.uint8); a[:, :, 3] = mask_bool * 255
    return Image.fromarray(a)

def _alpha(img): return np.asarray(img)[:, :, 3]

def test_trap_spreads_the_lighter_ink_under_the_darker_one():
    from app.separation_engine.engine import trap
    navy = np.zeros((20, 20), bool); navy[:, :10] = True
    yellow = ~navy
    out = trap([_ink(navy), _ink(yellow)], ['#1E3A8A', '#F2D04B'], 2)
    assert np.array_equal(_alpha(out[0]) > 0, navy)                 # darkest ink never changes
    grown = _alpha(out[1]) > 0
    assert grown[:, 8:].all() and not grown[:, :8].any()             # yellow now reaches 2px into the navy

def test_trap_never_grows_into_bare_fabric():
    from app.separation_engine.engine import trap
    navy = np.zeros((20, 30), bool); navy[:, :10] = True
    yellow = np.zeros((20, 30), bool); yellow[:, 10:20] = True       # columns 20+ carry no ink at all
    out = trap([_ink(navy), _ink(yellow)], ['#1E3A8A', '#F2D04B'], 3)
    grown = _alpha(out[1]) > 0
    assert grown[:, 7:20].all() and not grown[:, 20:].any()

def test_trap_middle_ink_spreads_only_under_darker_inks():
    from app.separation_engine.engine import trap
    dark = np.zeros((10, 30), bool); dark[:, :10] = True
    mid = np.zeros((10, 30), bool); mid[:, 10:20] = True
    light = np.zeros((10, 30), bool); light[:, 20:] = True
    out = trap([_ink(light), _ink(mid), _ink(dark)], ['#F5F0E0', '#C95368', '#202020'], 2)
    mid_out = _alpha(out[1]) > 0
    assert mid_out[:, 8:20].all() and not mid_out[:, 20:].any()      # under the dark ink, not the light one
    light_out = _alpha(out[0]) > 0
    assert light_out[:, 18:].all() and not light_out[:, :18].any()  # the light ink spreads under the mid ink

def test_trap_zero_is_a_no_op():
    from app.separation_engine.engine import trap
    masks = [_ink(np.eye(5, dtype=bool)), _ink(~np.eye(5, dtype=bool))]
    assert trap(masks, ['#000000', '#FFFFFF'], 0) is masks

def test_multichannel_psd_round_trips_through_the_importer():
    from app.core.psd_export import multichannel_psd
    from psd_tools.psd import PSD as RawPSD
    from psd_tools.constants import Resource, AlphaChannelMode
    screens = []
    for i in range(3):
        a = np.full((40, 30), 255, np.uint8); a[i * 10:(i + 1) * 10 + 5, 5:25] = 0; screens.append(Image.fromarray(a))
    names = ['1 RED 120', '2 हरा 90', '3 Gold']
    raw = multichannel_psd([(n, hx, s) for n, hx, s in zip(names, ['#C95368', '#477052', '#D9A43E'], screens)], dpi=300)
    kind, channels = psd_import.open_psd_any(raw)
    assert kind == 'channels'
    assert [n for n, _ in channels] == names
    for (_, got), want in zip(channels, screens):
        assert np.array_equal(np.asarray(got), np.asarray(want))
    res = RawPSD.read(BytesIO(raw)).image_resources
    spots = res.get_data(Resource.DISPLAY_INFO).alpha_channels
    assert all(s.mode == AlphaChannelMode.SPOT for s in spots)
    assert (spots[0].c1, spots[0].c2, spots[0].c3) == (0xC9 * 257, 0x53 * 257, 0x68 * 257)
    assert res.get_data(Resource.RESOLUTION_INFO).horizontal >> 16 == 300

def test_multichannel_psd_rejects_mismatched_sizes():
    from app.core.psd_export import multichannel_psd
    with pytest.raises(ValueError):
        multichannel_psd([('a', '#000000', Image.new('L', (4, 4), 255)), ('b', '#FFFFFF', Image.new('L', (5, 4), 255))])
