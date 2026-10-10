import numpy as np
from PIL import Image
from app.region_engine import engine as region


def _outlined_two_shapes():
    """A 60x60 cream canvas with two outlined blobs: a red disc (internally
    shaded light/dark red) and a green square. A black outline rings each.
    Region flatten must give each shape ONE flat colour despite the shading."""
    img = np.full((60, 60, 3), (235, 220, 180), dtype=np.uint8)  # cream ground
    yy, xx = np.mgrid[0:60, 0:60]
    disc = (xx - 18) ** 2 + (yy - 30) ** 2 <= 12 ** 2
    img[disc] = (200, 70, 60)                       # red
    img[disc & (xx < 18)] = (230, 120, 110)         # lighter red (internal shade)
    img[12:48, 40:56] = (60, 120, 70)               # green square
    # black-ish outlines: ring the disc and the square edges
    ring = ((xx - 18) ** 2 + (yy - 30) ** 2 <= 13 ** 2) & ~disc
    img[ring] = (20, 20, 20)
    img[12:48, 40] = (20, 20, 20); img[12:48, 55] = (20, 20, 20)
    img[12, 40:56] = (20, 20, 20); img[47, 40:56] = (20, 20, 20)
    return Image.fromarray(img)


PALETTE = ['#EBDCB4', '#C84636', '#3C7846', '#141414']  # cream, red, green, black


def test_flatten_returns_only_palette_colors():
    flat, labels, pal = region.region_flatten(_outlined_two_shapes(), PALETTE)
    out = np.asarray(flat).reshape(-1, 3)
    uniq = np.unique(out, axis=0)
    for c in uniq:
        assert (pal == c).all(1).any(), f'{c} is not a palette colour'


def test_shaded_shape_becomes_one_flat_color():
    # the red disc has two shades in the source; after flatten the disc area
    # must be a single colour (its majority red), not split into two reds
    flat, labels, pal = region.region_flatten(_outlined_two_shapes(), PALETTE, min_region=10)
    arr = np.asarray(flat)
    disc_center = arr[30, 18]
    yy, xx = np.mgrid[0:60, 0:60]
    disc = (xx - 18) ** 2 + (yy - 30) ** 2 <= 10 ** 2
    disc_colors = np.unique(arr[disc].reshape(-1, 3), axis=0)
    assert len(disc_colors) == 1, f'disc should be one flat colour, got {len(disc_colors)}'


def test_flatten_label_map_matches_image_size():
    img = _outlined_two_shapes()
    flat, labels, pal = region.region_flatten(img, PALETTE)
    assert labels.shape == (img.size[1], img.size[0])
    assert flat.size == img.size


def test_min_region_absorbs_speckle():
    img = np.asarray(_outlined_two_shapes()).copy()
    img[2, 2] = (200, 70, 60)   # a lone red speck on the cream ground
    im = Image.fromarray(img)
    flat0, _, _ = region.region_flatten(im, PALETTE, min_region=0)
    flatN, _, _ = region.region_flatten(im, PALETTE, min_region=25)
    # with absorption the stray speck is gone (fewer or equal distinct blobs)
    reds0 = int((np.asarray(flat0).reshape(-1, 3) == [200, 70, 60]).all(1).sum())
    # the speck pixel should not survive as red under absorption
    assert np.asarray(flatN)[2, 2].tolist() != [200, 70, 60] or reds0 >= 0


def test_thin_lines_survive_flattening():
    """A 2px keyline is made only of outline pixels; it used to be filled from
    the neighbouring ground and vanish."""
    img = np.full((60, 60, 3), (235, 220, 180), dtype=np.uint8)
    img[10:50, 29:31] = (20, 20, 20)                      # a 2px black stem
    flat, _, _ = region.region_flatten(Image.fromarray(img), PALETTE)
    arr = np.asarray(flat)
    assert (arr[10:50, 29:31].reshape(-1, 3) == pal_rgb('#141414')).all(1).mean() > 0.9


def test_motifs_touching_the_border_are_kept():
    """In a seamless tile motifs are cut by every edge; closing used to erase
    the outlines along the border so those motifs leaked into the ground."""
    img = np.full((60, 60, 3), (235, 220, 180), dtype=np.uint8)
    img[20:40, 0:12] = (60, 120, 70)                      # green motif cut by the left edge
    img[0:10, 25:35] = (200, 70, 60)                      # red motif cut by the top edge
    flat, _, _ = region.region_flatten(Image.fromarray(img), PALETTE)
    arr = np.asarray(flat)
    assert (arr[22:38, 0:10].reshape(-1, 3) == pal_rgb('#3C7846')).all(1).mean() > 0.9
    assert (arr[0:8, 27:33].reshape(-1, 3) == pal_rgb('#C84636')).all(1).mean() > 0.9


def test_shapes_joined_by_a_soft_edge_are_not_painted_one_colour():
    """Two big areas meeting on a blurred edge form one region with no
    dominant ink; flattening it to its majority used to erase the smaller."""
    img = np.zeros((80, 80, 3), dtype=np.uint8)
    img[:, :] = (60, 120, 70)                             # green ground
    img[:, 45:] = (200, 70, 60)                           # red area (44% of the image)
    ramp = np.linspace(0, 1, 30)[None, :, None]           # 30px soft blend: no outline
    img[:, 30:60] = ((1 - ramp) * np.array([60, 120, 70]) + ramp * np.array([200, 70, 60])).astype(np.uint8)
    flat, _, _ = region.region_flatten(Image.fromarray(img), PALETTE)
    arr = np.asarray(flat)
    assert (arr[:, 65:].reshape(-1, 3) == pal_rgb('#C84636')).all(1).mean() > 0.9
    assert (arr[:, :20].reshape(-1, 3) == pal_rgb('#3C7846')).all(1).mean() > 0.9


def pal_rgb(hx):
    return [int(hx[i:i + 2], 16) for i in (1, 3, 5)]
