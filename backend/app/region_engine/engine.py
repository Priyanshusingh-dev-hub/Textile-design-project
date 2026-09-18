"""Region-based flattening: give every enclosed shape a single flat colour.

The per-pixel colour engine assigns each pixel independently, so a shaded
petal gets split into a highlight ink and a shadow ink -- the "hollow / torn"
look. A designer instead sees each outlined shape as ONE flat colour. This
module reproduces that: it finds the design's outlines, treats the areas
between them as closed regions, and fills each whole region with the single
palette colour that is the majority inside it. A shaded petal bounded by an
outline therefore comes out as one clean colour, and boundaries stay crisp.

Pipeline: original -> LAB nearest-palette label per pixel -> outline mask from
LAB gradient (real edges, not gentle shading) -> close small gaps so outlines
seal -> connected regions between outlines -> majority palette colour per
region -> fill outline pixels from the nearest region -> absorb tiny speck
regions into their surroundings.
"""
import numpy as np
from PIL import Image
from scipy import ndimage
from ..color_engine.engine import rgb_lab, hex_rgb


def _palette_labels(rgb, pal_lab, block=200000):
    h, w, _ = rgb.shape
    flat = rgb_lab(rgb).reshape(-1, 3)
    out = np.empty(len(flat), dtype=np.int32)
    for s in range(0, len(flat), block):
        chunk = flat[s:s + block]
        out[s:s + block] = np.argmin(((chunk[:, None] - pal_lab[None, :]) ** 2).sum(-1), axis=1)
    return out.reshape(h, w)


def _edge_map(rgb, edge_strength):
    """Boundary mask: LAB gradient magnitude above edge_strength. LAB (not raw
    RGB) so the edges match what the eye reads as an outline; a lower threshold
    keeps more/finer edges, a higher one only the strong outlines."""
    lab = rgb_lab(rgb)
    gy = np.zeros_like(lab); gx = np.zeros_like(lab)
    gy[1:-1, :] = (lab[2:, :] - lab[:-2, :]) * 0.5
    gx[:, 1:-1] = (lab[:, 2:] - lab[:, :-2]) * 0.5
    mag = np.sqrt((gx ** 2).sum(-1) + (gy ** 2).sum(-1))
    return mag > edge_strength


def _absorb_small(label_img, min_region):
    """Reassign any same-colour blob smaller than min_region px to the nearest
    surviving region's colour, so scan speckle and stray anti-alias fragments
    don't each become their own tiny shape."""
    out = label_img
    h, w = out.shape
    small = np.zeros((h, w), bool)
    for c in range(int(out.max()) + 1):
        m = out == c
        if not m.any():
            continue
        comp, n = ndimage.label(m)
        if n == 0:
            continue
        sizes = np.bincount(comp.ravel())
        tiny_labels = np.nonzero(sizes < min_region)[0]
        tiny_labels = tiny_labels[tiny_labels != 0]
        if len(tiny_labels):
            small |= np.isin(comp, tiny_labels) & m
    if small.any() and not small.all():
        idx = ndimage.distance_transform_edt(small, return_distances=False, return_indices=True)
        out = out.copy()
        out[small] = label_img[tuple(idx)][small]
    return out


def region_flatten(image, palette, edge_strength=12.0, min_region=40, close_gaps=1):
    """Returns (flattened_rgb_image, label_map_2d, palette_rgb). Every pixel of
    the returned image is exactly one palette colour, one colour per enclosed
    shape -- feed it to the normal separation with cleanup=0 for perfectly
    clean masks."""
    rgb = np.asarray(image.convert('RGB'))
    h, w, _ = rgb.shape
    pal = np.array([hex_rgb(hx) for hx in palette])
    pal_lab = rgb_lab(pal)
    plabels = _palette_labels(rgb, pal_lab)

    edges = _edge_map(rgb, edge_strength)
    if close_gaps > 0:
        edges = ndimage.binary_closing(edges, iterations=int(close_gaps))
    region_lbl, n = ndimage.label(~edges)

    p = len(pal)
    combined = region_lbl.ravel() * p + plabels.ravel()
    counts = np.bincount(combined, minlength=(n + 1) * p).reshape(n + 1, p)
    region_color = counts.argmax(axis=1)
    out_label = region_color[region_lbl]
    # edge pixels belong to region 0; give them their nearest real region's colour
    edge_pix = region_lbl == 0
    if edge_pix.any() and not edge_pix.all():
        idx = ndimage.distance_transform_edt(edge_pix, return_distances=False, return_indices=True)
        out_label = out_label.copy()
        out_label[edge_pix] = out_label[tuple(idx)][edge_pix]

    if min_region > 0:
        out_label = _absorb_small(out_label, min_region)

    flat_rgb = pal[out_label].astype(np.uint8)
    return Image.fromarray(flat_rgb), out_label, pal
