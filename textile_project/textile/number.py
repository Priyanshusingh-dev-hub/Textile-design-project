"""Number a COLOURED design: every patch of one colour gets a number.

`textile number design.png --out o/`: the user's way to plan a sketch from a
finished colour design. The design is read at --size (3535 px wide by
default), cleaned of weave/print grain (a 5 px median at its own scale), cut
to its distinct inks (paint._ref_palette: k-means 16 in CIELAB, shades closer
than dE 30 are one ink, at most --colors), and every connected patch of one
ink (4-connected, as the sketch areas are) is an area. Patches smaller than
--min-area px are grain, not design: each pixel of one goes to the nearest
bigger patch. Then:

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


def patches(index, min_area):
    """(labels H x W int32 from 1, n): 4-connected patches of one ink; patches
    under `min_area` px melted into the nearest bigger one first."""
    K = int(index.max()) + 1
    for _ in range(3):                                   # melting can leave a new speck; three passes is plenty
        lab = np.zeros(index.shape, np.int32)
        n = 0
        for k in range(K):
            l, m = ndimage.label(index == k)
            lab[l > 0] = l[l > 0] + n
            n += m
        area = np.bincount(lab.ravel(), minlength=n + 1)
        small = area < min_area
        small[0] = False
        sm = small[lab]
        if not sm.any():
            return lab, n
        _, (iy, ix) = ndimage.distance_transform_edt(sm, return_indices=True)
        index = index.copy()
        index[sm] = index[iy[sm], ix[sm]]
    return lab, n


def number(design_path, out_dir, name=None, size=3535, colours=8, min_area=250, log=print):
    rgb = read_cv2(design_path, cv2.IMREAD_COLOR)
    if rgb is None:
        raise FillError('design read nahi hua - path check karo.')
    rgb = cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)
    name = safe_name(name or os.path.splitext(os.path.basename(design_path))[0])
    os.makedirs(out_dir, exist_ok=True)
    W, H = output_size(rgb.shape[1], rgb.shape[0], size)
    clean = cv2.medianBlur(rgb, 5)                        # grain at the design's own scale
    big = cv2.resize(clean, (W, H), interpolation=cv2.INTER_AREA if rgb.shape[1] > W else cv2.INTER_LANCZOS4)
    small = cv2.resize(big, (min(W, 1000), max(1, round(min(W, 1000) * H / W))), interpolation=cv2.INTER_AREA)
    pal = pt._ref_palette(small, colours)
    from . import palette as pl
    index = pl.map_to_palette(big, pal)
    lab, n = patches(index, min_area)
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
            'csv': csv_path, 'inks': [(hex_of(c), nm.colour_name(c), round(float(s), 2)) for c, s in zip(pal, shares)]}
