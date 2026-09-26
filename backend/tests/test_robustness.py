from app.models import RemapRequest
"""The tool must not crash on the odd files a mill will inevitably feed it:
grayscale scans, palette PNGs, CMYK exports, tiny crops, single-colour art."""
import numpy as np
import pytest
from PIL import Image, ImageDraw
from app.color_engine import engine
from app.color_engine.engine import analyze, reduce, reconstruction_accuracy, merge, quantize_full
from app.separation_engine.engine import create as separation_create


@pytest.mark.parametrize('img,expect_inks', [
    (Image.fromarray(np.tile(np.linspace(0, 255, 40, dtype=np.uint8), (40, 1))), None),  # grayscale gradient
    (Image.fromarray(np.random.RandomState(0).randint(0, 5, (40, 40), np.uint8)).convert('P'), None),  # palette
    (Image.new('CMYK', (30, 30), (10, 200, 50, 0)), 1),   # CMYK solid
    (Image.new('RGB', (1, 1), '#804020'), 1),             # 1x1
    (Image.new('RGB', (2, 3), '#204060'), 1),             # 2x3
    (Image.new('RGB', (50, 50), '#33AA77'), 1),           # single flat colour
])
def test_analyze_and_reduce_survive_odd_inputs(img, expect_inks):
    pal = analyze(img, 4)
    assert len(pal) >= 1
    if expect_inks is not None:
        assert len(pal) == expect_inks
    flat = reduce(img, 4)
    assert flat.mode == 'RGBA' and flat.size == img.size
    layers = separation_create(flat, [p.hex for p in pal], cleanup=0)
    assert len(layers) == len(pal)


def test_quantize_full_palette_matches_reduced_image_exactly():
    a = np.zeros((20, 20, 3), np.uint8); a[:, :10] = (200, 40, 40); a[:, 10:] = (40, 60, 200)
    img, pal = quantize_full(Image.fromarray(a), 3)
    out = np.asarray(img.convert('RGB')).reshape(-1, 3)
    palette_rgb = {tuple(p.rgb) for p in pal}
    image_rgb = {tuple(c) for c in np.unique(out, axis=0)}
    assert image_rgb <= palette_rgb, 'reduced image uses only palette colours'


def _two_flat():
    a = np.zeros((20, 20, 3), np.uint8); a[:, :10] = (216, 72, 118); a[:, 10:] = (40, 64, 96)
    return Image.fromarray(a)


def test_remap_recolor_changes_exactly_one_ink():
    img = reduce(_two_flat(), 2)
    pal = [p.hex for p in analyze(_two_flat(), 2)]
    out = np.asarray(merge(img, [pal[0]], '#00FF00', 6).convert('RGB'))
    uniq = {tuple(c) for c in np.unique(out.reshape(-1, 3), axis=0)}
    assert (0, 255, 0) in uniq                     # the recolored ink is now green
    assert len(uniq) == 2                          # still exactly two inks


def test_remap_does_not_touch_a_distinct_similar_ink():
    """Two perceptually close-but-distinct inks: recoloring one must leave the
    other alone (tight CIEDE2000 threshold)."""
    a = np.zeros((20, 20, 3), np.uint8)
    a[:, :10] = (200, 40, 40)      # red
    a[:, 10:] = (200, 70, 60)      # a nearby but distinct red (dE2000 4.9)
    img = Image.fromarray(a).convert('RGBA')
    out = np.asarray(merge(img, ['#C82828'], '#0000FF', RemapRequest.model_fields['threshold'].default).convert('RGB'))
    uniq = {tuple(c) for c in np.unique(out.reshape(-1, 3), axis=0)}
    # only pixels very near the source were repainted; the other red survives
    assert any(c[0] > 150 and c[2] < 90 for c in uniq), 'the distinct second red was wrongly swallowed'


def test_reconstruction_accuracy_handles_empty_palette():
    assert reconstruction_accuracy(_two_flat(), []) == (0.0, 0.0)


def test_suggest_colors_returns_a_count_and_curve():
    from app.color_engine.engine import suggest_colors
    # a 3-colour image: suggestion should be small, and low counts already fit well
    a = np.zeros((60, 60, 3), np.uint8)
    a[:, :20] = (200, 40, 40); a[:, 20:40] = (40, 60, 200); a[:, 40:] = (230, 220, 190)
    out = suggest_colors(Image.fromarray(a))
    assert 2 <= out['suggested'] <= 14
    assert out['curve'] and all('colors' in c and 'accuracy' in c for c in out['curve'])
    # a near-flat design needs very few inks
    flat = Image.new('RGB', (40, 40), '#334455')
    assert suggest_colors(flat)['suggested'] <= 4


def _antialiased(colours, n=240):
    """Flat shapes and lines drawn at 4x and shrunk: real anti-aliased art."""
    from PIL import ImageDraw
    big = Image.new('RGB', (n * 4, n * 4), colours[0]); d = ImageDraw.Draw(big)
    for i, c in enumerate(colours[1:]):
        for j in range(4):
            x = (j * 223 + i * 131) % (n * 3); y = (j * 97 + i * 181) % (n * 3)
            d.ellipse([x, y, x + 180 + i * 30, y + 120 + j * 20], fill=c)
            d.line([0, x, n * 4, y], fill=c, width=9)
    return big.resize((n, n), Image.LANCZOS)


@pytest.mark.parametrize('colours', [
    ['#f4ecd8', '#8a1c1c'],
    ['#ffffff', '#1b3a6b', '#d94f2a'],
    ['#f7f1e3', '#2d5a27', '#c0392b', '#e5b73b', '#3b2a1a'],
])
def test_flat_art_is_suggested_exactly_its_own_ink_count(colours):
    """The anti-aliased rims between inks are not inks. The old median-cut
    sweep counted them and said 4 for a 2-colour design, 6 for a 5-colour one."""
    from app.color_engine.engine import suggest_colors
    assert suggest_colors(_antialiased(colours))['suggested'] == len(colours)


def test_a_one_colour_design_is_suggested_one_ink():
    from app.color_engine.engine import suggest_colors
    assert suggest_colors(Image.new('RGB', (40, 40), '#334455'))['suggested'] == 1


def test_smooth_shading_is_not_called_flat():
    """A gradient never reaches the flat-art bar, and the curve stays honest
    about it: that is what the continuous-tone warning is driven by."""
    from app.color_engine.engine import suggest_colors
    yy, xx = np.mgrid[0:120, 0:160]
    a = np.stack([xx * 1.5, yy * 2.0, 255 - xx], -1).clip(0, 255).astype(np.uint8)
    out = suggest_colors(Image.fromarray(a))
    assert out['suggested'] >= 6
    assert max(c['accuracy'] for c in out['curve']) < 97


def test_large_image_path_gives_same_shape_and_faithful_palette(monkeypatch):
    """Force the downscale-proxy path on a small image and confirm it still
    produces a full-resolution reduced image and a faithful palette."""
    import app.color_engine.engine as eng
    a = np.full((120, 120, 3), (240, 235, 220), np.uint8)
    yy, xx = np.mgrid[0:120, 0:120]
    a[(xx - 40) ** 2 + (yy - 40) ** 2 <= 22 ** 2] = (200, 60, 80)
    a[(xx - 85) ** 2 + (yy - 85) ** 2 <= 18 ** 2] = (60, 110, 180)
    img = Image.fromarray(a)
    monkeypatch.setattr(eng, '_MAX_ANALYSIS_PX', 2000)   # 120x120 = 14400 -> proxy path
    flat, pal = eng.quantize_full(img, 5)
    assert flat.size == (120, 120) and flat.mode == 'RGBA'
    de, acc = eng.reconstruction_accuracy(img, [p.hex for p in pal])
    assert acc > 92 and len(pal) >= 3       # the three real colours are captured, faithfully


def test_large_path_preserves_transparency(monkeypatch):
    import app.color_engine.engine as eng
    a = np.zeros((100, 100, 4), np.uint8)
    a[20:50, 20:50] = (200, 40, 40, 255)
    a[55:85, 55:85] = (40, 40, 200, 255)
    img = Image.fromarray(a)
    monkeypatch.setattr(eng, '_MAX_ANALYSIS_PX', 2000)
    flat, pal = eng.quantize_full(img, 4)
    alpha = np.asarray(flat)[:, :, 3]
    assert alpha[0, 0] == 0 and alpha[35, 35] == 255   # background stays clear
    # the transparent void never becomes an ink (no near-black background plate)
    assert all(sum(p.rgb) > 60 for p in pal), 'a dark background ink leaked in'
    assert 2 <= len(pal) <= 4


# --- high-bit-depth sources (16-bit scans) -----------------------------------

def _grey_design():
    im = Image.new('RGB', (160, 160), '#EFE3C8')
    d = ImageDraw.Draw(im)
    d.ellipse((24, 24, 136, 136), fill='#C0392B')
    d.line((0, 80, 160, 80), fill='#1A1A1A', width=3)
    return im.convert('L')


def test_16bit_grey_is_rescaled_not_clipped():
    """PIL converts I;16 to RGB by clipping at 255, which turns a 16-bit scan
    into a blank white sheet — the tool would then report one ink at 100%
    accuracy and hand the mill an empty plate."""
    grey = _grey_design()
    wide = Image.fromarray(np.asarray(grey).astype(np.uint16) * 257)
    assert wide.mode == 'I;16'

    rgb, _ = engine.rgb_and_opaque(wide)
    assert len(np.unique(rgb.reshape(-1, 3), axis=0)) >= 3, 'the design was flattened to one colour'

    # and it reduces to the same design the 8-bit original does
    from_wide = sorted(p for p in engine.analyze(wide, 3)[1])
    from_8bit = sorted(p for p in engine.analyze(grey, 3)[1])
    assert from_wide == from_8bit


def test_to_8bit_leaves_ordinary_images_alone():
    im = _grey_design().convert('RGB')
    assert engine.to_8bit(im) is im
    rgba = im.convert('RGBA')
    assert engine.to_8bit(rgba) is rgba


def test_to_8bit_handles_a_flat_high_bit_image():
    """A uniform 16-bit image has no range to stretch — it must not divide by
    zero, just come through as a single flat tone."""
    flat = Image.fromarray(np.full((8, 8), 40000, np.uint16))
    out = engine.to_8bit(flat)
    assert out.mode == 'L' and len(np.unique(np.asarray(out))) == 1
