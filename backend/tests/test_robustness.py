"""The tool must not crash on the odd files a mill will inevitably feed it:
grayscale scans, palette PNGs, CMYK exports, tiny crops, single-colour art."""
import numpy as np
import pytest
from PIL import Image
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
    a[:, 10:] = (200, 70, 60)      # a nearby but distinct red
    img = Image.fromarray(a).convert('RGBA')
    out = np.asarray(merge(img, ['#C82828'], '#0000FF', 6).convert('RGB'))
    uniq = {tuple(c) for c in np.unique(out.reshape(-1, 3), axis=0)}
    # only pixels very near the source were repainted; the other red survives
    assert any(c[0] > 150 and c[2] < 90 for c in uniq), 'the distinct second red was wrongly swallowed'


def test_reconstruction_accuracy_handles_empty_palette():
    assert reconstruction_accuracy(_two_flat(), []) == (0.0, 0.0)
