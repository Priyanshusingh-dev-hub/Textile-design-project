"""Transparent areas of a design carry no ink: they must never become a
palette colour, a black region in the reduced image, or ink on any plate."""
import numpy as np
from PIL import Image
from app.color_engine.engine import analyze, reduce, reconstruction_accuracy
from app.separation_engine.engine import create as separation_create


def _two_shapes_on_transparent():
    """A red square and a blue square on a fully transparent background."""
    a = np.zeros((40, 40, 4), dtype=np.uint8)  # transparent everywhere
    a[5:20, 5:20] = (200, 40, 40, 255)         # red, opaque
    a[22:37, 22:37] = (40, 40, 200, 255)       # blue, opaque
    return Image.fromarray(a)


def test_analyze_ignores_transparent_background():
    pal = analyze(_two_shapes_on_transparent(), 6)
    # only the two real inks — the transparent void is not a colour
    assert len(pal) == 2
    # coverage is over printed pixels only, so the two shapes sum to ~100%
    assert abs(sum(p.coverage for p in pal) - 100) < 1


def test_reduce_keeps_transparency():
    out = reduce(_two_shapes_on_transparent(), 4)
    assert out.mode == 'RGBA'
    alpha = np.asarray(out)[:, :, 3]
    # the background stays transparent; the two shapes are opaque
    assert alpha[0, 0] == 0
    assert alpha[12, 12] == 255 and alpha[29, 29] == 255
    # transparent pixels are not painted black — they are still zero-alpha
    assert (alpha == 0).sum() > 0


def test_transparent_background_is_not_a_black_plate():
    img = _two_shapes_on_transparent()
    pal = [p.hex for p in analyze(img, 4)]
    flat = reduce(img, 4)
    layers = separation_create(flat, pal, cleanup=0)
    # exactly two ink plates, no third "background" plate
    assert len(layers) == 2
    # every plate only has ink where a shape is — total inked area << full frame
    for hx, mask, _disp, cov in layers:
        assert cov < 20  # each 15x15 shape is ~14% of the 40x40 frame


def test_separation_mutually_exclusive_over_opaque_only():
    img = _two_shapes_on_transparent()
    pal = [p.hex for p in analyze(img, 4)]
    flat = reduce(img, 4)
    layers = separation_create(flat, pal, cleanup=0)
    inked = np.stack([np.asarray(m)[:, :, 3] > 0 for _, m, _, _ in layers]).sum(0)
    opaque = np.asarray(flat)[:, :, 3] > 0
    # opaque pixels: exactly one ink; transparent pixels: zero inks
    assert set(np.unique(inked[opaque]).tolist()) == {1}
    assert inked[~opaque].max() == 0


def test_accuracy_scores_only_printed_pixels():
    img = _two_shapes_on_transparent()
    pal = [p.hex for p in analyze(img, 4)]
    de, acc = reconstruction_accuracy(img, pal)
    # the two flat shapes are reproduced exactly; the transparent void, which
    # would otherwise drag the score, is excluded
    assert acc >= 99.0 and de < 1.0
