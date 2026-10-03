"""Number a COLOURED design: every patch of one colour gets a number.

`textile number design.png --out o/`: the user's way to plan a sketch from a
finished colour design. The design is read at --size (3535 px wide by
default), cleaned of weave/print grain (a 5 px median at its own scale), cut
to its distinct inks (paint._ref_palette: k-means 16 in CIELAB, shades closer
than dE 30 are one ink, at most --colors), and every connected patch of one
ink (4-connected, as the sketch areas are) is an area. Grain is melted (see
`patches`: specks under --min-area px, and thin or ragged flecks lying inside
one other patch; small round dots are kept). Then:

  NAME_numbers.png   the coloured design, each patch outlined, its number on it
                     (paint's numbers sheet: inside when it fits, else a dot and
                     a blue number beside it; it grows until every number has a place)
  NAME_flat.png      the design as those flat inks (what was numbered)
  NAME_colors.csv    Number, HEX, Colour, share %: the same CSV `textile paint`
                     reads, so a sketch drawn to these patches can be painted with it

Nothing is printed from here: no package, no mill file. It is a map to work from.
"""
from __future__ import annotations

import csv
import os

import cv2
import numpy as np
from scipy import ndimage

from . import names as nm
from . import paint as pt
from .fill_method1 import FillError, output_size
from .io_utils import hex_of, read_cv2, safe_name, save_png, to_image


def _label(index):
    """4-connected patches of one ink, numbered from 1 across all inks."""
    lab = np.zeros(index.shape, np.int32)
    n = 0
    for k in range(int(index.max()) + 1):
        l, m = ndimage.label(index == k)
        lab[l > 0] = l[l > 0] + n
        n += m
    return lab, n


def patches(index, min_area=250, thin=3.5, enclosed_max=3000, rim=0.0, rim_area=None):
    """(labels H x W int32 from 1, n, the cleaned ink index): the design's areas, its grain melted.

    A patch goes (its pixels to the nearest other patch) when it is under
    `min_area` px, or when it lies wholly inside ONE other patch (a fleck in a
    leaf) and is thin (no point more than `thin` px from its edge: a weave line)
    or small and ragged (under `enclosed_max` px and over 2.5x the area of the
    widest circle in it). A small ROUND patch inside another stays: a flower's
    centre, a dot. Patches that touch two or more others (a leaf, the ground
    and the dark outlines that join it) are never melted, so two leaves parted
    by a dark line stay two areas. On the user's woven jaal photo: 1066 areas,
    most of them weave, -> 426, the yellow flower's dark centre and the pink
    flower's dots and ring kept."""
    for _ in range(5):
        lab, n = _label(index)
        area = np.bincount(lab.ravel(), minlength=n + 1)
        bd = np.zeros(lab.shape, bool)
        dx, dy = lab[:, 1:] != lab[:, :-1], lab[1:, :] != lab[:-1, :]
        bd[:, 1:] |= dx
        bd[:, :-1] |= dx
        bd[1:, :] |= dy
        bd[:-1, :] |= dy
        thick = np.zeros(n + 1)
        thick[1:] = ndimage.maximum(ndimage.distance_transform_edt(~bd), lab, np.arange(1, n + 1))
        a = np.concatenate([lab[:, 1:][dx], lab[1:, :][dy]])
        b = np.concatenate([lab[:, :-1][dx], lab[:-1, :][dy]])
        pairs = np.unique(np.stack([np.r_[a, b], np.r_[b, a]], 1), axis=0)
        neigh = np.bincount(pairs[:, 0], minlength=n + 1)
        one = np.zeros(n + 1, np.int64)
        one[pairs[:, 0]] = pairs[:, 1]                    # for a patch with one neighbour: that neighbour
        edge = np.zeros(n + 1, bool)
        edge[np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])] = True
        inside = (neigh == 1) & ~edge
        ragged = area / (np.pi * np.maximum(thick, 0.5) ** 2) > 2.5
        melt = (area < min_area) | (inside & ((thick < thin) | ((area < enclosed_max) & ragged))) | ((thick < rim) & (area < (np.inf if rim_area is None else rim_area)))
        melt[0] = False
        if not melt.any():
            return lab, n, index
        ink = np.zeros(n + 1, np.int64)
        ink[lab.ravel()] = index.ravel()
        e = melt & inside
        ink[e] = ink[one[e]]                              # a fleck takes the ink of the patch it lies in
        index = ink[lab].astype(index.dtype)
        rest = (melt & ~inside)[lab]
        if rest.any():
            _, (iy, ix) = ndimage.distance_transform_edt(rest, return_indices=True)
            index[rest] = index[iy[rest], ix[rest]]
    lab, n = _label(index)
    return lab, n, index


BLEND_THIN = 0.6       # an ink with 60%+ of its pixels in edge-thin patches...
BLEND_DE = 10          # ...and within dE 10 of the line between two other inks is their blend, not an ink
WOVEN_GRAIN = 4.0      # median dE a 3x3 median makes: the woven photo 8.2, clean digital designs 0-0.7
CLEAN_SAME_DE = 12     # a clean design's inks that close are one ink (its black outline and navy fill: kept apart)


def blend_inks(index, pal, rim):
    """Inks that are only the blend along edges: most of their pixels (BLEND_THIN) lie
    in patches no thicker than `rim` px, AND their colour lies between two other
    inks (within BLEND_DE of the line joining them, not at its ends). A thin black
    outline is thin but no mix of two others, so it stays; the paisley's silver
    (black over cream) and coffee (black over maroon) go."""
    K = len(pal)
    lab, n = _label(index)
    bd = np.zeros(lab.shape, bool)
    dx, dy = lab[:, 1:] != lab[:, :-1], lab[1:, :] != lab[:-1, :]
    bd[:, 1:] |= dx
    bd[:, :-1] |= dx
    bd[1:, :] |= dy
    bd[:-1, :] |= dy
    thick = np.zeros(n + 1)
    thick[1:] = ndimage.maximum(ndimage.distance_transform_edt(~bd), lab, np.arange(1, n + 1))
    thin_px = np.bincount(index.ravel(), weights=(thick[lab] <= rim).ravel(), minlength=K)
    all_px = np.maximum(np.bincount(index.ravel(), minlength=K), 1)
    L = nm._lab(pal.astype(np.float64))
    out = np.zeros(K, bool)
    for k in range(K):
        if thin_px[k] / all_px[k] < BLEND_THIN:
            continue
        for i in range(K):
            for j in range(i + 1, K):
                if k in (i, j):
                    continue
                d = L[j] - L[i]
                t = float(np.dot(L[k] - L[i], d) / max(np.dot(d, d), 1e-9))
                if 0.1 < t < 0.9 and np.linalg.norm(L[i] + t * d - L[k]) < BLEND_DE:
                    out[k] = True
    return out


def grain(rgb):
    """How grainy a picture is: the median CIELAB change a 3x3 median makes, at <= 1254 px."""
    if rgb.shape[1] > 1600:
        rgb = cv2.resize(rgb, (1254, max(1, round(1254 * rgb.shape[0] / rgb.shape[1]))), interpolation=cv2.INTER_AREA)
    a = nm._lab(rgb.reshape(-1, 3).astype(np.float64))
    b = nm._lab(cv2.medianBlur(rgb, 3).reshape(-1, 3).astype(np.float64))
    return float(np.median(np.linalg.norm(a - b, axis=1)))


def number(design_path, out_dir, name=None, size=3535, colours=8, min_area=250, log=print):
    rgb = read_cv2(design_path, cv2.IMREAD_COLOR)
    if rgb is None:
        raise FillError('design read nahi hua - path check karo.')
    rgb = cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)
    name = safe_name(name or os.path.splitext(os.path.basename(design_path))[0])
    os.makedirs(out_dir, exist_ok=True)
    W, H = output_size(rgb.shape[1], rgb.shape[0], size)
    g = grain(rgb)
    woven = g >= WOVEN_GRAIN
    log(f"[number] grain {g:.1f}: " + ('photo / buna kapda - daane saaf kiye' if woven else 'saaf design - bareek detail rakhi'))
    # a woven photo: its grain cleaned at its own scale; a clean design is read as it is (a median ate its dots)
    clean = cv2.medianBlur(rgb, 5) if woven else rgb
    big = cv2.resize(clean, (W, H), interpolation=cv2.INTER_AREA if rgb.shape[1] > W else cv2.INTER_LANCZOS4)
    # a clean design is sampled NEAREST: an area-average invents blend shades that crowd out a small real ink
    small = cv2.resize(big, (min(W, 1000), max(1, round(min(W, 1000) * H / W))),
                       interpolation=cv2.INTER_AREA if woven else cv2.INTER_NEAREST)
    pal = pt._ref_palette(small, colours, None if woven else CLEAN_SAME_DE)
    from . import palette as pl
    index = pl.map_to_palette(big, pal)
    scale = W / rgb.shape[1]
    if woven:
        lab, n, index = patches(index, min_area, rim=0.8 * scale)   # a rim ~1.5 source px wide: an edge's blend
    else:
        # a clean design: an ink under BLEND_SHARE is the blend along edges (anti-aliasing), not a colour:
        # its pixels go to the nearest real patch. Then only specks under ~2x2 source px melt; its fine
        # dots, thin outlines and enclosed bits are design and stay
        blend = blend_inks(index, pal, 0.8 * scale)
        if blend.any() and not blend.all():
            m = blend[index]
            _, (iy, ix) = ndimage.distance_transform_edt(m, return_indices=True)
            index[m] = index[iy[m], ix[m]]
        # a broken bit of outline (thin, under ~30 source px) is a fleck too; a whole outline is long and stays
        lab, n, index = patches(index, max(20, round((2 * scale) ** 2)), thin=0, enclosed_max=0,
                                rim=0.8 * scale, rim_area=round(30 * scale ** 2))
    area = np.bincount(lab.ravel(), minlength=n + 1)
    area[0] = 0
    ink = np.zeros(n + 1, np.int64)
    ink[lab.ravel()] = index.ravel()                      # every pixel of a patch has its ink
    edge = np.zeros(lab.shape, bool)                      # where two patches meet: drawn, and kept free of numbers
    edge[:, 1:] |= lab[:, 1:] != lab[:, :-1]
    edge[1:, :] |= lab[1:, :] != lab[:-1, :]
    log(f'[number] {W}x{H} px, {len(pal)} rang, {n} hisse (patch {min_area} px se chhote ghul gaye)')
    reg = pt.Regions(lab, edge, area, np.zeros(n + 1, np.int64), [], -1, 0, '')
    flat = pal[index]
    path, missed = pt._numbers(reg, out_dir, name, big, kind='numbers', outline=True)
    save_png(to_image(flat), os.path.join(out_dir, f'{name}_flat.png'), 300)
    csv_path = os.path.join(out_dir, f'{name}_colors.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['Number', 'HEX', 'Colour', 'Share %'])
        for i in range(1, n + 1):
            c = pal[ink[i]]
            w.writerow([i, '#' + hex_of(c), nm.colour_name(c), round(area[i] / (W * H) * 100, 3)])
    shares = np.bincount(index.ravel(), minlength=len(pal)) / index.size * 100
    return {'name': name, 'size_px': [W, H], 'areas': int(n), 'missed': int(missed), 'numbers': path,
            'csv': csv_path, 'inks': [(hex_of(c), nm.colour_name(c), round(float(s), 2)) for c, s in zip(pal, shares) if s > 0.05]}
