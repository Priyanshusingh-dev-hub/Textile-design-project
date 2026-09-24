import os
from concurrent.futures import ThreadPoolExecutor

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


# ---- enlarging screens for a bigger print ---------------------------------
# Films are written at 300 DPI, so a 1254 px design prints 4.2 in wide. A mill
# that wants it 12 in wide needs every pixel enlarged ~2.9x — and enlarging a
# hard pixel mask just makes bigger stair-steps. Instead each ink is treated as
# a field (1 inside, 0 outside), the fields are resampled smoothly, and every
# output pixel goes to the ink whose field is highest there. That keeps one
# ink per pixel by construction while the boundaries come out as smooth curves.
#
# Measured against shapes drawn at 8x and reduced to 1x (edge error relative
# to plain enlarging; survival of 1px lines): Lanczos-resampled fields 83%;
# fields blurred 1.2 px first, 66% — but a blur erases thin lines (a 1px
# diagonal falls to 1%). So every field is blurred for smooth outlines, and
# afterwards each ink's thin parts (under 3 px wide) are painted back wherever
# their *unblurred* field reaches 0.45. Edge error stays at 65%, and thin lines
# survive better than plain enlarging keeps them (1px diagonal 66% -> 92%).
# (0.4 keeps lines a touch better but draws them fat; 0.5 the reverse.)
# Only a thin feature's own outline goes unsmoothed; the inks around it stay
# smooth, which matters on painterly art, where slivers are everywhere.
_UPSCALE_SIGMA = 1.2
_RESTORE_AT = 0.45


def _blur(a, sigma):
    """Separable Gaussian blur of a float32 array (edge-extended)."""
    r = int(3 * sigma + 1)
    x = np.arange(-r, r + 1, dtype=np.float32)
    k = np.exp(-x * x / (2 * sigma * sigma)); k /= k.sum()
    p = np.pad(a, r, mode='edge')
    p = np.lib.stride_tricks.sliding_window_view(p, len(k), axis=0) @ k
    return (np.lib.stride_tricks.sliding_window_view(p, len(k), axis=1) @ k).astype(np.float32)


def _grow(m, r=1):
    for _ in range(r):
        d = m.copy()
        d[1:] |= m[:-1]; d[:-1] |= m[1:]; d[:, 1:] |= m[:, :-1]; d[:, :-1] |= m[:, 1:]
        m = d
    return m


def _shrink(m):
    e = m.copy()
    e[1:] &= m[:-1]; e[:-1] &= m[1:]; e[:, 1:] &= m[:, :-1]; e[:, :-1] &= m[:, 1:]
    return e


def _exclusive_binary(alphas):
    """True when the masks are hard-edged and never overlap — i.e. they came
    from `create`. A bureau's PSD channels may be soft or overlap on purpose,
    and those are resized one by one instead, keeping what the bureau did."""
    total = np.zeros(alphas[0].shape, np.uint16)
    for a in alphas:
        if ((a != 0) & (a != 255)).any():
            return False
        total += a > 0
    return int(total.max()) <= 1


_REPEAT_CHANGE = 2.0   # ink changes across the seam / inside, at or below = a repeat
_WRAP = 8              # px of wrap-around: blur, Lanczos and the thin test combined


def _repeat_axes(label):
    """(left-right, top-bottom) along which a label map repeats seamlessly:
    inks change across the wrap seam no more often than across a typical line
    inside. A reduced repeat tile passes; an ordinary design (the floral: 4x)
    does not."""
    if min(label.shape) < 8:
        return (False, False)
    def ok(across, inner):
        return across <= _REPEAT_CHANGE * inner if inner > 0 else across == 0
    return (ok((label[:, 0] != label[:, -1]).mean(), (label[:, 1:] != label[:, :-1]).mean()),
            ok((label[0] != label[-1]).mean(), (label[1:] != label[:-1]).mean()))


def resize_masks(masks, size, repeat=None):
    """The ink masks redrawn at `size` (w, h) with smooth edges.

    Mutually exclusive masks stay mutually exclusive: every output pixel goes to
    exactly one ink, or to no ink where the design is blank. Anything else (a
    bureau's overlapping or soft channels) is resized mask by mask. At the
    masks' own size they are returned unchanged."""
    if not masks or masks[0].size == tuple(size):
        return list(masks)
    w, h = size
    alphas = [np.asarray(m.convert('RGBA'))[:, :, 3] for m in masks]
    if not _exclusive_binary(alphas):
        out = []
        for a in alphas:
            big = Image.fromarray(a).resize((w, h), Image.LANCZOS)
            rgba = np.zeros((h, w, 4), np.uint8); rgba[:, :, 3] = np.asarray(big)
            out.append(Image.fromarray(rgba))
        return out
    inked = np.zeros(alphas[0].shape, bool)
    for a in alphas:
        inked |= a > 0
    fields = [~inked] + [a > 0 for a in alphas]          # 0 = blank (no ink)

    # A seamless repeat stays seamless: every field is wrapped around along the
    # repeating axes, and resampling reads only the tile itself (`box`) while
    # its filters see the true neighbours across the seam.
    if repeat is None:
        repeat = _repeat_axes(np.argmax(np.stack(fields), 0))
    sh, sw = inked.shape
    py = min(_WRAP, sh) if repeat[1] else 0
    px = min(_WRAP, sw) if repeat[0] else 0
    box = (px, py, px + sw, py + sh)

    def field(f):
        """(smooth field, where this ink's thin parts are painted back)."""
        if px or py:
            f = np.pad(f, ((py, py), (px, px)), mode='wrap')
        ind = f.astype(np.float32)
        smooth = np.asarray(Image.fromarray(_blur(ind, _UPSCALE_SIGMA)).resize((w, h), Image.LANCZOS, box=box))
        thin = f & ~_grow(_shrink(f))                    # parts under 3 px wide
        if not thin.any():
            return smooth, None
        near = np.asarray(Image.fromarray(_grow(thin).astype(np.uint8) * 255).resize((w, h), Image.NEAREST, box=box)) > 0
        raw = np.asarray(Image.fromarray(ind).resize((w, h), Image.LANCZOS, box=box))
        return smooth, near & (raw >= _RESTORE_AT)

    # fields are independent (and PIL/numpy release the GIL), so they are built
    # in parallel; the winner is still chosen in ink order, so ties resolve the
    # same way every time
    best = label = None
    restore = []
    with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as pool:
        for k, (v, back) in enumerate(pool.map(field, fields)):
            if back is not None:
                restore.append((k, back))
            if best is None:
                best, label = np.array(v), np.zeros((h, w), np.uint8)
            else:
                win = v > best
                best[win] = v[win]; label[win] = k
    for k, back in restore:
        label[back] = k
    out = []
    for k in range(1, len(fields)):
        rgba = np.zeros((h, w, 4), np.uint8); rgba[:, :, 3] = (label == k) * np.uint8(255)
        out.append(Image.fromarray(rgba))
    return out


def edge_share(mask):
    """Percent of the design's outer edge (a 1px frame) this ink covers. The
    ink that owns most of the edge is the ground the motifs sit on; a mill
    usually prints on cloth dyed that colour and skips its screen. Coverage
    alone can't tell: a big motif on a transparent ground covers a lot but
    touches no edge."""
    a = np.asarray(mask.convert('RGBA'))[:, :, 3] > 0
    if a.shape[0] < 3 or a.shape[1] < 3:
        return round(float(a.mean() * 100), 1)
    ring = np.concatenate([a[0], a[-1], a[1:-1, 0], a[1:-1, -1]])
    return round(float(ring.mean() * 100), 1)


def press_lightness(hx):
    """How light an ink is (L*): the package prints lightest first."""
    return float(rgb_lab(hex_rgb(hx))[0])


MAX_TRAP = 3   # px; at 300 DPI 3 px is 0.25 mm, beyond any press's register slip


def _spread(m, r, wrap=(False, False)):
    """`m` grown by `r` px, round-ish (cross and square steps alternate, an
    octagon), wrapping round the axes of a seamless repeat."""
    py = r if wrap[1] and m.shape[0] > r else 0
    px = r if wrap[0] and m.shape[1] > r else 0
    g = np.pad(m, ((py, py), (px, px)), mode='wrap') if (px or py) else m
    for step in range(r):
        d = g.copy()
        d[1:] |= g[:-1]; d[:-1] |= g[1:]; d[:, 1:] |= g[:, :-1]; d[:, :-1] |= g[:, 1:]
        if step % 2:                                    # every other step also the diagonals
            d[1:, 1:] |= g[:-1, :-1]; d[:-1, :-1] |= g[1:, 1:]
            d[1:, :-1] |= g[:-1, 1:]; d[:-1, 1:] |= g[1:, :-1]
        g = d
    return g[py:g.shape[0] - py, px:g.shape[1] - px]


def trap(masks, colors, px):
    """The films with a trap: each ink spread `px` pixels under the *darker*
    inks it touches, so a screen that slips a fraction of a millimetre on the
    press leaves no line of bare cloth between two colours.

    Only lighter-under-darker, and only where another printed ink lies: the
    darker ink prints later (the package is ordered light to dark) and covers
    the spread, so the print looks exactly as designed — stacking the films in
    press order still rebuilds the design pixel for pixel. Nothing spreads
    onto bare cloth or a transparent background, so no shape grows.

    This changes the FILMS only, and deliberately breaks "one ink per pixel" on
    them by `px` at each colour boundary; the separation itself stays exclusive.
    Masks that aren't LoomLab's own exclusive separation (a bureau's PSD, which
    carries its own trapping) are refused."""
    px = int(px)
    if px <= 0 or len(masks) < 2:
        return list(masks)
    if px > MAX_TRAP:
        raise ValueError(f'A trap wider than {MAX_TRAP} px is not supported.')
    # the alpha alone: reading whole RGBA masks cost 2.4s at 12 inches
    alphas = [np.asarray(m.getchannel('A') if m.mode == 'RGBA' else m.convert('RGBA').getchannel('A'))
              for m in masks]
    if not _exclusive_binary(alphas):
        raise ValueError('These screens already overlap (a pre-separated PSD keeps the bureau\'s own '
                         'trapping) — trap is only added to LoomLab\'s own separations.')
    # the same lightness the package orders the press by, so every spread goes
    # under an ink that really prints after it
    light = [press_lightness(c) for c in colors]
    order = sorted(range(len(masks)), key=lambda i: (-light[i], i))     # lightest first
    rank = np.full(alphas[0].shape, -1, np.int16)                       # -1 = no ink
    label = np.zeros(alphas[0].shape, np.uint8)
    for r, i in enumerate(order):
        rank[alphas[i] > 0] = r
        label[alphas[i] > 0] = i + 1
    wrap = _repeat_axes(label)
    out = list(masks)
    for r, i in enumerate(order[:-1]):                 # the darkest ink has nothing to go under
        own = alphas[i] > 0
        if not own.any():
            continue
        under = _spread(own, px, wrap) & (rank > r)
        if under.any():
            film = Image.new('RGBA', masks[i].size, (0, 0, 0, 0))
            film.putalpha(Image.fromarray((own | under) * np.uint8(255)))
            out[i] = film
    return out


# ---- dots too small for a screen ------------------------------------------
# A screen's mesh cannot hold a dot below a certain size: it either doesn't
# print or clogs and prints as dirt. At 300 DPI a pixel is 0.085 mm, and a
# painterly design reduced to flat inks leaves thousands of 1-4 px islands
# (the floral at 10 inks: 7,359 under 0.2 mm, 0.8% of the design). Mills clean
# these by hand; `clean_specks` gives each one to the ink around it, so the
# plates stay exactly one ink per pixel.
_EIGHT = np.ones((3, 3), bool)


def dot_area(min_dot_mm, dpi):
    """Largest island, in pixels at `dpi`, smaller than a round dot of
    `min_dot_mm` across."""
    if not min_dot_mm:
        return 0
    return int(np.pi / 4 * (min_dot_mm * dpi / 25.4) ** 2)


def _label_map(masks):
    alphas = [np.asarray(m.getchannel('A') if m.mode == 'RGBA' else m.convert('RGBA').getchannel('A'))
              for m in masks]
    if not _exclusive_binary(alphas):
        raise ValueError('These screens overlap (a pre-separated PSD) — tiny dots are only cleaned on '
                         'LoomLab\'s own separations.')
    label = np.zeros(alphas[0].shape, np.int16)                 # 0 = no ink
    for i, a in enumerate(alphas):
        label[a > 0] = i + 1
    return label


def _specks(label, n_inks, max_area):
    """(component id per pixel, 0 = not a speck; ink of each speck id). Islands
    touching the edge of a repeat tile continue on the next tile, so they are
    never counted as specks there."""
    from scipy import ndimage
    wrap = _repeat_axes(label.astype(np.uint8)) if n_inks < 255 else (False, False)
    comp = np.zeros(label.shape, np.int32); ink_of = [0]
    for i in range(1, n_inks + 1):
        c, n = ndimage.label(label == i, structure=_EIGHT)
        if not n:
            continue
        sizes = np.bincount(c.ravel())
        small = sizes <= max_area; small[0] = False
        if wrap[0]:
            small[np.unique(c[:, [0, -1]])] = False
        if wrap[1]:
            small[np.unique(c[[0, -1], :])] = False
        ids = np.flatnonzero(small)
        if not len(ids):
            continue
        remap = np.zeros(n + 1, np.int32); remap[ids] = np.arange(len(ink_of), len(ink_of) + len(ids))
        hit = small[c]
        comp[hit] = remap[c[hit]]
        ink_of += [i] * len(ids)
    return comp, np.array(ink_of)


def speck_report(masks, max_area):
    """Per ink: (dots too small to hold, pixels in them)."""
    if max_area <= 0:
        return [(0, 0)] * len(masks)
    label = _label_map(masks)
    comp, ink_of = _specks(label, len(masks), max_area)
    dots = np.bincount(ink_of[1:], minlength=len(masks) + 1)[1:]
    px = np.bincount(label[comp > 0], minlength=len(masks) + 1)[1:]
    return [(int(d), int(p)) for d, p in zip(dots, px)]


def clean_specks(masks, max_area):
    """The masks with every island of `max_area` px or less given to the ink
    most of its border touches (or to bare cloth). Still one ink per pixel.
    Two neighbouring specks can join into a new one, so it repeats (3x max)."""
    if max_area <= 0 or not masks:
        return list(masks)
    label = _label_map(masks)
    out_label = label
    for _ in range(3):
        nxt = _clean_once(out_label, len(masks), max_area)
        if nxt is None:
            break
        out_label = nxt
    out = list(masks)
    for i in range(len(masks)):
        before, after = label == i + 1, out_label == i + 1
        if (before != after).any():
            film = Image.new('RGBA', masks[i].size, (0, 0, 0, 0))
            film.putalpha(Image.fromarray(after.astype(np.uint8) * 255))
            out[i] = film
    return out


def _clean_once(label, n_inks, max_area):
    """One pass of `clean_specks` on a label map; None when nothing moved."""
    comp, ink_of = _specks(label, n_inks, max_area)
    n = len(ink_of)
    if n <= 1:
        return None
    k1 = n_inks + 1
    votes = np.zeros(n * k1, np.int64)
    h, w = label.shape
    ys, xs = np.nonzero(comp)
    cid = comp[ys, xs]
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if not (dy or dx):
                continue
            ny, nx = ys + dy, xs + dx
            ok = (ny >= 0) & (ny < h) & (nx >= 0) & (nx < w)
            ny, nx, c = ny[ok], nx[ok], cid[ok]
            other = comp[ny, nx] != c                       # the border, not the speck itself
            np.add.at(votes, c[other] * k1 + label[ny[other], nx[other]], 1)
    votes = votes.reshape(n, k1)
    votes[np.arange(n), ink_of] = 0                         # never back to its own ink
    new = votes.argmax(1)
    keep = votes.max(1) == 0                                # nothing around it: leave it
    new[keep] = ink_of[keep]
    new[0] = 0
    if (new[1:] == ink_of[1:]).all():
        return None
    out_label = label.copy()
    out_label[ys, xs] = new[cid]
    return out_label
