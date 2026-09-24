import numpy as np
from PIL import Image, ImageFilter
from ..color_engine.engine import hex_rgb, nearest_centre, rgb_lab

# cleanup level -> (source median-blur radius, label mode-filter size).
# Real fabric scans/prints carry texture, ink grain and JPEG noise, so a raw
# nearest-colour assignment speckles: single stray pixels get the wrong ink
# and boundaries turn ragged. Pre-blurring the source removes fine grain
# before assignment, and a mode filter on the label map replaces isolated
# mis-assigned pixels with the dominant nearby colour, giving each screen
# solid regions with clean, well-defined edges.
_CLEANUP_LEVELS = {
    0: (0, 0),   # off — raw nearest-colour, may speckle
    1: (0, 3),
    2: (1, 3),   # default — gentle, keeps detail
    3: (1, 5),
    4: (2, 5),
    5: (2, 7),   # aggressive — very solid, softens fine detail
}

def _nearest_ink(rgb, palette):
    """Palette index of the nearest ink (LAB distance) for every pixel of an
    (H,W,3) uint8 array. Solved per distinct colour: separation runs on the
    reduced design, which holds only the palette's own colours."""
    palette_lab = np.array([rgb_lab(hex_rgb(hx)) for hx in palette])
    return nearest_centre(rgb, palette_lab).astype(np.int64).reshape(rgb.shape[:2])


def _assign_labels(image, palette, cleanup=2):
    """Nearest-palette-colour assignment with optional denoising so a
    scanned/printed fabric's texture doesn't produce speckled masks. Returns an
    int label array (one palette index per pixel); transparent pixels get -1 so
    they carry no ink on any plate."""
    blur, mode_size = _CLEANUP_LEVELS.get(cleanup, _CLEANUP_LEVELS[2])
    rgba = np.asarray(image.convert('RGBA'))
    opaque = rgba[:, :, 3] >= 128
    src = Image.fromarray(np.ascontiguousarray(rgba[:, :, :3]))
    if blur:
        src = src.filter(ImageFilter.MedianFilter(size=blur * 2 + 1))
    labels = _nearest_ink(np.asarray(src), palette)
    if mode_size and len(palette) <= 256:
        smoothed = Image.fromarray(labels.astype(np.uint8)).filter(ImageFilter.ModeFilter(size=mode_size))
        labels = np.asarray(smoothed).astype(int)
    labels[~opaque] = -1
    return labels


def create(image, palette, cleanup=2):
    """One mutually-exclusive screen per ink: (hex, ink-alpha RGBA layer,
    coverage %). Every opaque pixel lands on exactly one layer."""
    labels = _assign_labels(image, palette, cleanup)
    layers = []
    for index, hx in enumerate(palette):
        hit = labels == index
        rgba = np.zeros((*hit.shape, 4), dtype=np.uint8)
        rgba[:, :, 3] = hit * np.uint8(255)
        layers.append((hx, Image.fromarray(rgba), round(float(hit.mean() * 100), 2)))
    return layers


def plate(mask, color_hex, ground='#FFFFFF'):
    """Render one screen as its ink colour composited over the cloth colour —
    the per-plate colour proof a mill reviews (e.g. "Plate 1 — Red" showing
    only the red shapes), built from the layer's alpha mask so anti-aliased
    edges stay smooth. `ground` defaults to white; pass the real fabric colour
    so the operator sees how the ink sits on their cloth (and so a white
    under-base is visible at all)."""
    alpha = mask.convert('RGBA').getchannel('A')
    return Image.composite(Image.new('RGB', mask.size, hex_rgb_str(color_hex)),
                           Image.new('RGB', mask.size, hex_rgb_str(ground)), alpha)

def to_print_ready(mask):
    """Convert an ink-alpha mask (one of create()'s layer images) into a flat
    8-bit grayscale screen: black where ink prints, white where it doesn't —
    the standard screen-printing film convention mills expect, matching
    production files like a bureau's exported per-color TIFFs."""
    alpha=np.asarray(mask.convert('RGBA'))[:,:,3]
    return Image.fromarray(255-alpha)

def composite_masks(mask_layers, size):
    """mask_layers: list of (mask_image, color_hex, opacity_percent)."""
    out=Image.new('RGBA',size,(0,0,0,0))
    for mask,color,opacity in mask_layers:
      alpha=np.asarray(mask.convert('RGBA'))[:,:,3].astype(np.float64)
      alpha=(alpha*(max(0.0,min(100.0,opacity))/100.0)).round().astype(np.uint8)
      rgba=np.zeros((*alpha.shape,4),dtype=np.uint8); rgba[:,:,:3]=hex_rgb(color); rgba[:,:,3]=alpha
      out.alpha_composite(Image.fromarray(rgba))
    return out

def underbase(masks, choke=1):
    """The white screen printed FIRST when the cloth is not white.

    On dark fabric an ink laid straight onto the cloth goes muddy, so mills
    print a white base under the whole design and the colours on top. This is
    the union of every printing ink, *choked* (eroded by `choke` pixels) so the
    white never peeks out past the colour that covers it — the standard trap.

    This is an ADDITIONAL screen, not one of the spot colours: the colour
    plates stay mutually exclusive (one ink per pixel) exactly as before.
    """
    if not masks:
        return None
    union = np.zeros(np.asarray(masks[0].convert('RGBA')).shape[:2], dtype=bool)
    for m in masks:
        union |= np.asarray(m.convert('RGBA'))[:, :, 3] > 0

    choke = max(0, int(choke))
    eroded = union
    for _ in range(choke):
        e = eroded.copy()
        e[1:, :] &= eroded[:-1, :]; e[:-1, :] &= eroded[1:, :]
        e[:, 1:] &= eroded[:, :-1]; e[:, :-1] &= eroded[:, 1:]
        eroded = e

    # A feature no wider than 2*choke is erased completely by the choke, so a
    # hairline — a stem, an outline, a vein — would print straight onto dark
    # cloth with no white behind it and go dull while everything around it
    # stays bright. Those are exactly the features the reduce step works
    # hardest to keep. Where the choke wiped the feature out entirely, keep the
    # base unchoked: a hairline with a faint white edge is far better than one
    # that disappears. Wherever the choke left something, only the choked
    # version is used, so solid shapes still get their rim pulled in.
    keep = eroded
    if choke:
        reach = eroded.copy()                      # dilate the survivors back out
        for _ in range(choke):
            d = reach.copy()
            d[1:, :] |= reach[:-1, :]; d[:-1, :] |= reach[1:, :]
            d[:, 1:] |= reach[:, :-1]; d[:, :-1] |= reach[:, 1:]
            reach = d
        keep = eroded | (union & ~reach)

    rgba = np.zeros((*keep.shape, 4), dtype=np.uint8)
    rgba[:, :, 3] = keep.astype(np.uint8) * 255
    return Image.fromarray(rgba)


def print_preview(layers, size, fabric='#FFFFFF'):
    """Combined proof of exactly what the enabled screens will print: each ink's
    mask painted in its colour, stacked back-to-front over the blank fabric
    ground. This is the operator's answer to 'will these plates make my design?'
    — because separation is mutually exclusive, the enabled plates composite
    back to the reduced design with no overlap or gaps."""
    base = np.zeros((size[1], size[0], 3), np.uint8); base[:, :] = hex_rgb(fabric)
    for mask, color in layers:
        a = np.asarray(mask.convert('RGBA'))[:, :, 3] > 0
        base[a] = hex_rgb(color)
    return Image.fromarray(base)


# On-screen thumbnails (the plate chips) are ~100px wide; 320 stays sharp on a
# high-density display. Rendering them at full size cost a 13 MP colour proof
# and PNG per ink for a picture the browser then shrank.
THUMB_SIDE = 320


def thumb(mask, max_side=THUMB_SIDE):
    """A mask shrunk for display. The alpha is box-filtered, so edges come out
    anti-aliased rather than jagged. Never used for anything that prints."""
    w, h = mask.size
    if max(w, h) <= max_side:
        return mask
    k = max_side / max(w, h)
    alpha = mask.convert('RGBA').getchannel('A').resize(
        (max(1, round(w * k)), max(1, round(h * k))), Image.BOX)
    out = Image.new('RGBA', alpha.size, (0, 0, 0, 0))
    out.putalpha(alpha)
    return out


def preview_thumb(layers, fabric='#FFFFFF', max_side=THUMB_SIDE):
    """A small proof of the given inks over the cloth, for display only: each
    mask shrunk with `thumb` and laid on in order, blending the soft edges."""
    base = None
    for mask, color in layers:
        small = thumb(mask, max_side)
        if base is None:
            base = Image.new('RGB', small.size, hex_rgb_str(fabric))
        base = Image.composite(Image.new('RGB', small.size, hex_rgb_str(color)), base, small.getchannel('A'))
    return base


def hex_rgb_str(hx):
    return tuple(int(v) for v in hex_rgb(hx))
