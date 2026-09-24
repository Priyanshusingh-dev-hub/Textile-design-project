"""Seamless repeat tiles stay seamless.

A repeat is printed edge to edge, so its left edge meets its own right edge on
the cloth. Filters that treat the image edge as a wall put a seam into it."""
import numpy as np
import pytest
from PIL import Image, ImageDraw

from app.color_engine import engine as E
from app.separation_engine import engine as S


def _tile(n=240, seed=4):
    """Shapes drawn with every wrapped copy, over periodic texture: seamless."""
    rs = np.random.RandomState(seed)
    im = Image.new('RGB', (n, n), '#E9DCC0'); d = ImageDraw.Draw(im)
    for _ in range(14):
        x, y = rs.randint(0, n, 2); r = rs.randint(10, 34)
        col = ['#B5473A', '#4E6B45', '#2F4A3A', '#D9A441'][rs.randint(4)]
        for dx in (-n, 0, n):
            for dy in (-n, 0, n):
                d.ellipse((x + dx - r, y + dy - r // 2, x + dx + r, y + dy + r // 2), fill=col)
    a = np.asarray(im).astype(float)
    fx = np.sin(np.arange(n) * 2 * np.pi * 7 / n)             # periodic grain
    a += (fx[None, :, None] * fx[:, None, None]) * 5
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _seam_rank(img):
    """Percentile of the seam line's ink-change rate among interior lines."""
    L = np.asarray(img.convert('RGB')).astype(np.int64) @ [65536, 256, 1]
    ranks = []
    for A in (L, L.T):
        inner = (A[:, 1:] != A[:, :-1]).mean(0)
        ranks.append((inner < (A[:, 0] != A[:, -1]).mean()).mean() * 100)
    return sum(ranks) / 2


def test_a_seamless_tile_is_recognised():
    assert E.seamless_axes(_tile()) == (True, True)


def test_an_ordinary_design_is_not_a_repeat():
    im = Image.new('RGB', (200, 120), '#EFE3C8')
    ImageDraw.Draw(im).rectangle((0, 0, 60, 119), fill='#2A5DA8')     # blue on the left edge only
    assert E.seamless_axes(im)[0] is False


def test_a_border_print_can_repeat_along_one_axis_only():
    im = Image.new('RGB', (240, 120), '#EFE3C8')
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 239, 20), fill='#2A5DA8')                      # band along the top
    for x in range(0, 240, 40):
        d.ellipse((x + 5, 50, x + 35, 80), fill='#C0392B')              # motifs repeat every 40px
    assert E.seamless_axes(im) == (True, False)


@pytest.mark.parametrize('cleanup', [1, 2])
def test_reducing_a_repeat_leaves_no_seam(cleanup):
    tile = _tile()
    wrapped, _ = E.quantize_full(tile, 5, cleanup)
    walled, _ = E.quantize_full(tile, 5, cleanup, repeat=(False, False))
    assert _seam_rank(wrapped) < 90
    assert _seam_rank(wrapped) <= _seam_rank(walled)


def test_wrapping_changes_nothing_when_the_edges_are_plain_ground():
    im = Image.new('RGB', (160, 120), '#F4E8CC')
    ImageDraw.Draw(im).ellipse((40, 20, 120, 100), fill='#C0392B')
    a, pa = E.quantize_full(im, 3, 1, repeat=(False, False))
    b, pb = E.quantize_full(im, 3, 1)
    assert np.array_equal(np.asarray(a), np.asarray(b)) and [p.hex for p in pa] == [p.hex for p in pb]


def test_enlarging_a_repeat_leaves_no_seam():
    red, pal = E.quantize_full(_tile(), 5, 1)
    layers = S.create(red, [p.hex for p in pal], 0)
    masks, cols = [m for _, m, _ in layers], [h for h, _, _ in layers]
    size = (600, 600)
    # (how bad the unwrapped seam gets depends on what crosses the edge: 99th
    # percentile on a denser 600px tile; this one only guards the fix)
    wrapped = S.print_preview(list(zip(S.resize_masks(masks, size), cols)), size)
    assert _seam_rank(wrapped) < 90
    # still one ink per pixel, still the requested size
    count = sum((np.asarray(m)[:, :, 3] > 0).astype(int) for m in S.resize_masks(masks, size))
    assert count.shape == (600, 600) and (count == 1).all()


def test_only_a_real_repeat_is_reported():
    assert E.repeat_to_report(_tile()) == (True, True)
    plain = Image.new('RGB', (160, 120), '#F4E8CC')
    ImageDraw.Draw(plain).ellipse((40, 20, 120, 100), fill='#C0392B')
    assert E.seamless_axes(plain) == (True, True)          # wrapped, harmlessly...
    assert E.repeat_to_report(plain) == (False, False)     # ...but not called a repeat


def test_dither_and_noise_are_not_repeats():
    """Noise looks the same at every distance; a repeat's seam looks like a
    neighbouring pair of columns and unlike a far one."""
    rs = np.random.RandomState(3)
    noise = Image.fromarray(rs.randint(0, 256, (160, 160, 3)).astype(np.uint8))
    assert E.seamless_axes(noise) == (False, False)
    dither = Image.new('RGB', (160, 160), '#EFE3C8').convert('1').convert('RGB')
    assert E.repeat_to_report(dither) == (False, False)


def test_one_stripe_across_a_plain_edge_is_not_announced_as_a_repeat():
    im = Image.new('RGB', (200, 160), '#EFE3C8'); d = ImageDraw.Draw(im)
    d.ellipse((50, 30, 150, 130), fill='#C0392B'); d.line((0, 80, 199, 80), fill='#1A1A1A', width=2)
    assert E.repeat_to_report(im) == (False, False)
