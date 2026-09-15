import numpy as np
from PIL import Image
from app.core.regmarks import add_registration_marks


def _blank_screen(w=200, h=300):
    return Image.new('L', (w, h), 255)  # all white = no ink


def test_adds_margin_and_returns_larger_image():
    out = add_registration_marks(_blank_screen(200, 300), dpi=300)
    assert out.mode == 'L'
    assert out.size[0] > 200 and out.size[1] > 300
    # symmetric margin: extra width == extra height for a square-margin border
    assert (out.size[0] - 200) == (out.size[1] - 300)


def test_marks_are_identical_across_screens_of_the_same_size():
    a = add_registration_marks(_blank_screen(200, 300), dpi=300)
    b = add_registration_marks(_blank_screen(200, 300), dpi=300)
    # two different screens of the same canvas must get pixel-identical marks
    # so they overlay exactly when the operator aligns them
    assert np.array_equal(np.asarray(a), np.asarray(b))


def test_marks_land_in_the_margin_not_over_the_artwork():
    dpi = 300
    src = _blank_screen(200, 300)
    out = add_registration_marks(src, dpi=dpi)
    margin = max(40, int(dpi * 0.4))
    arr = np.asarray(out)
    # the pasted artwork region stays untouched (all white) ...
    interior = arr[margin:margin + 300, margin:margin + 200]
    assert interior.min() == 255
    # ... while black mark pixels exist somewhere in the margin
    assert arr.min() == 0


def test_preserves_artwork_ink_inside_the_border():
    src = Image.new('L', (100, 100), 255)
    src.putpixel((50, 50), 0)  # one ink pixel
    out = add_registration_marks(src, dpi=300)
    margin = max(40, int(300 * 0.4))
    assert out.getpixel((margin + 50, margin + 50)) == 0
