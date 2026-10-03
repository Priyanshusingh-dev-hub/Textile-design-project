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
  NAME_sketch_seal0.png        the colours taken away: a 2 px black line where two patches meet, on
                     white. Its areas, as `textile paint` finds them (seal 0: the name says so), ARE the numbers
  NAME_sketch_numbers.png      that sketch with the numbers
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


LINE_WIDTH = 1.25      # a patch at most this many source px from middle to edge (and long) is a drawn line
BLEND_THIN = 0.6       # an ink with 60%+ of its pixels in edge-thin patches...
BLEND_DE_RIM = 20      # ...or within 20 when 95%+ of it is rim (a black outline is ~60% rim: stays)
BLEND_DE = 10          # ...and within dE 10 of the line between two other inks is their blend, not an ink
WOVEN_GRAIN = 4.0      # median dE a 3x3 median makes: the woven photo 8.2, clean digital designs 0-0.7
CLEAN_SAME_DE = 12     # a clean design's inks that close are one ink (its black outline and navy fill: kept apart)


LINE_CORE = 1.5        # a part keeps at least this many px from its middle to the line (a 3 px core)


def _wide_line(lab, bd, half):
    """The line where parts meet, `half` px into each side, but never so wide that a
    part loses its core or is cut in two at a narrow neck: a part where the full width
    would do that keeps the plain 1+1 px line (bd) on its side. Moti line big parts
    me, aur bareek daane / patli patti salamat."""
    if half <= 1:
        return bd
    dt = ndimage.distance_transform_edt(~bd)
    wide = bd | (dt < half)
    n = int(lab.max())
    core = (lab > 0) & ~wide
    # each part must keep exactly one piece of core, at least LINE_CORE deep
    cl, cn = ndimage.label(core)
    has = np.zeros(n + 1, np.int64)
    pairs = np.unique(np.stack([lab[core], cl[core]], 1), axis=0)
    np.add.at(has, pairs[:, 0], 1)
    deep = np.zeros(n + 1)
    deep[1:] = ndimage.maximum(dt, lab, np.arange(1, n + 1))
    ok = (has == 1) & (deep >= half + LINE_CORE)
    ok[0] = True
    return np.where(ok[lab], wide, bd)


SHADE_THIN = 3.0        # a shaded edge up to 3 source px from middle to edge (the leaves' dark dashes were 2-3)
RIM_SHARE = 0.25       # ...sharing at least a quarter of its border with that part
SHADE_DARK_L = 25.0    # ...and near black
RIM_NEAR_DE = 20       # a thin rim this close in colour to the part it edges is that part's darker edge


def shade_rims(index, pal, thin):
    """A thin patch (no point more than `thin` px from its edge) whose ink is within
    RIM_NEAR_DE of a patch it shares RIM_SHARE+ of its border with is that patch's shaded
    edge, not a part: it takes that patch's ink. Only a DARKER rim, and under dE 20: a lighter
    vein, or a truth floral's olive vein in a green leaf (24.4 apart), is a real part. The paisley's navy leaves had a
    near-black edge (black-navy 18.7) that came out as short thick black dashes all
    over the sketch; its real black outlines round the maroon flowers (black-maroon
    48.7) stay."""
    L = nm._lab(pal.astype(np.float64))
    for _ in range(2):
        lab, n = _label(index)
        bd = np.zeros(lab.shape, bool)
        dx, dy = lab[:, 1:] != lab[:, :-1], lab[1:, :] != lab[:-1, :]
        bd[:, 1:] |= dx
        bd[:, :-1] |= dx
        bd[1:, :] |= dy
        bd[:-1, :] |= dy
        thick = np.zeros(n + 1)
        thick[1:] = ndimage.maximum(ndimage.distance_transform_edt(~bd), lab, np.arange(1, n + 1))
        a = np.concatenate([lab[:, 1:][dx], lab[1:, :][dy], lab[:, :-1][dx], lab[:-1, :][dy]]).astype(np.int64)
        b = np.concatenate([lab[:, :-1][dx], lab[:-1, :][dy], lab[:, 1:][dx], lab[1:, :][dy]]).astype(np.int64)
        key, cnt = np.unique(a * (n + 1) + b, return_counts=True)
        pa, pb = key // (n + 1), key % (n + 1)
        ink = np.zeros(n + 1, np.int64)
        ink[lab.ravel()] = index.ravel()
        tot = np.bincount(pa, weights=cnt, minlength=n + 1)
        # among the patches sharing at least RIM_SHARE of its border, the one closest in colour
        dE = np.linalg.norm(L[ink[pa]] - L[ink[pb]], axis=1)
        # a shaded edge is darker than what it edges, and near black (L < SHADE_DARK_L): on the degraded truth
        # floral a dark green vein in an olive leaf is as close (18.4) as the paisley's black to its navy (18.7)
        darker = (L[ink[pa], 0] < L[ink[pb], 0]) & (L[ink[pa], 0] < SHADE_DARK_L)
        ok = (cnt >= RIM_SHARE * tot[pa]) & (dE < RIM_NEAR_DE) & darker
        main = np.zeros(n + 1, np.int64)
        best = np.full(n + 1, np.inf)
        for x, y, e in zip(pa[ok], pb[ok], dE[ok]):
            if e < best[x]:
                best[x], main[x] = e, y
        near = main > 0
        move = (thick <= thin) & near & (main > 0)
        move[0] = False
        if not move.any():
            break
        ink[move] = ink[main[move]]
        index = ink[lab].astype(index.dtype)
    return index


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
        frac = thin_px[k] / all_px[k]
        if frac < BLEND_THIN:
            continue
        de = BLEND_DE_RIM if frac >= 0.95 else BLEND_DE      # all rim: a looser mix still counts (paisley coffee 14)
        for i in range(K):
            for j in range(i + 1, K):
                if k in (i, j):
                    continue
                d = L[j] - L[i]
                t = float(np.dot(L[k] - L[i], d) / max(np.dot(d, d), 1e-9))
                if 0.1 < t < 0.9 and np.linalg.norm(L[i] + t * d - L[k]) < de:
                    out[k] = True
    return out


def grain(rgb):
    """How grainy a picture is: the median CIELAB change a 3x3 median makes, at <= 1254 px."""
    if rgb.shape[1] > 1600:
        rgb = cv2.resize(rgb, (1254, max(1, round(1254 * rgb.shape[0] / rgb.shape[1]))), interpolation=cv2.INTER_AREA)
    a = nm._lab(rgb.reshape(-1, 3).astype(np.float64))
    b = nm._lab(cv2.medianBlur(rgb, 3).reshape(-1, 3).astype(np.float64))
    return float(np.median(np.linalg.norm(a - b, axis=1)))


DETAIL_MM2 = {'kam': 3.0, 'normal': 0.4, 'zyada': 0.1}   # a part smaller than this (mm2 at 300 DPI) is melted
WOVEN_DETAIL = 4.0     # a woven photo's grain is coarser: its smallest part is 4x that (normal: 1.6 mm2 ~ 220 px)
RIM = 1.01             # at the design's own size an edge's blend is 1 px wide (its middle 1 px from the edge)
SEP_GREY = 60          # a separator (two colours meeting, no outline) is drawn this grey; an outline 0 (black)


def number(design_path, out_dir, name=None, size=3535, colours=8, detail='normal', smooth=True, line_mm=0.35,
           separators=True, min_area=None, dpi=300, log=print):
    """Number a coloured design and draw its sketch. See the module doc; returns a dict of what was made."""
    from . import edges as ed
    from . import palette as pl
    rgb = read_cv2(design_path, cv2.IMREAD_COLOR)
    if rgb is None:
        raise FillError('design read nahi hua - path check karo.')
    if detail not in DETAIL_MM2:
        raise FillError(f"detail '{detail}' nahi: kam, normal ya zyada")
    rgb = cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)
    name = safe_name(name or os.path.splitext(os.path.basename(design_path))[0])
    os.makedirs(out_dir, exist_ok=True)
    W, H = output_size(rgb.shape[1], rgb.shape[0], size)
    scale = W / rgb.shape[1]
    g = grain(rgb)
    woven = g >= WOVEN_GRAIN
    log(f"[number] grain {g:.1f}: " + ('photo / buna kapda - daane saaf kiye' if woven else 'saaf design - bareek detail rakhi'))

    px_mm = dpi / 25.4
    keep_mm2 = (min_area / px_mm ** 2) if min_area else DETAIL_MM2[detail] * (WOVEN_DETAIL if woven else 1)
    if woven:
        # a woven photo (as tuned on the user's jaal): its grain cleaned at its own scale, then everything at
        # --size, flecks melted there (on the photo's own grid they came back as 2042 parts, not 425)
        big = cv2.resize(cv2.medianBlur(rgb, 5), (W, H), interpolation=cv2.INTER_AREA if rgb.shape[1] > W
                         else cv2.INTER_LANCZOS4)
        small = cv2.resize(big, (min(W, 1000), max(1, round(min(W, 1000) * H / W))), interpolation=cv2.INTER_AREA)
        pal = pt._ref_palette(small, colours)
        index = pl.map_to_palette(big, pal)
        _, _, index = patches(index, max(20.0, keep_mm2 * px_mm ** 2), rim=0.8 * scale)
        if smooth:                                 # its ragged woven edges smoothed along themselves
            index, _ = ed.clean(index.astype(np.uint8), 1, 3)
    else:
        # a clean design: inks and parts read at its own size, as it is (a median ate its dots; an area average
        # invented blend shades), then drawn at --size with every outline smoothed (textile edges)
        sw = min(rgb.shape[1], 1000)
        small = cv2.resize(rgb, (sw, max(1, round(sw * rgb.shape[0] / rgb.shape[1]))), interpolation=cv2.INTER_NEAREST)
        pal = pt._ref_palette(small, colours, CLEAN_SAME_DE)
        index = pl.map_to_palette(rgb, pal)
        blend = blend_inks(index, pal, RIM)       # an edge's anti-alias blend is no ink
        if blend.any() and not blend.all():
            m = blend[index]
            _, (iy, ix) = ndimage.distance_transform_edt(m, return_indices=True)
            index[m] = index[iy[m], ix[m]]
        keep_px = max(2.0, keep_mm2 * px_mm ** 2 / scale ** 2)
        index = shade_rims(index, pal, SHADE_THIN)
        _, _, index = patches(index, keep_px, thin=0, enclosed_max=0, rim=RIM, rim_area=30)
        if smooth and scale != 1:
            index, _ = ed.clean(index.astype(np.uint8), scale, 2)
        if index.shape != (H, W):
            index = cv2.resize(index.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST)
    lab, _ = _label(index)

    # 4. the sketch. A part that is itself a line (a drawn outline: at most ~2.5 source px wide and long, not a
    # dot) is drawn solid black, as a sketch draws it (outlined on both sides it left a 1-2 px strip that broke
    # into hundreds of bits); where two other parts meet, a line --line-mm wide, grey when --separators
    # (it prints as the colour beside it) and black otherwise
    bd = np.zeros(lab.shape, bool)
    dx, dy = lab[:, 1:] != lab[:, :-1], lab[1:, :] != lab[:-1, :]
    bd[:, 1:] |= dx
    bd[:, :-1] |= dx
    bd[1:, :] |= dy
    bd[:-1, :] |= dy
    p_n = int(lab.max())
    thick = np.zeros(p_n + 1)
    thick[1:] = ndimage.maximum(ndimage.distance_transform_edt(~bd), lab, np.arange(1, p_n + 1))
    p_area = np.bincount(lab.ravel(), minlength=p_n + 1)
    is_line = (thick <= LINE_WIDTH * scale) & (p_area >= 4 * np.pi * np.maximum(thick, 1) ** 2)
    is_line[0] = False
    # only the darkest ink's thin patches are drawn lines (outlines are dark); a thin LIGHT part (a cream vein in
    # a navy leaf) stays a part with its own number, or the CSV's 'lines' ink would print it dark
    p_ink = np.zeros(p_n + 1, np.int64)
    p_ink[lab.ravel()] = index.ravel()
    darkest = int(np.argmin(nm._lab(pal.astype(np.float64))[:, 0]))
    is_line &= p_ink == darkest
    line_px = is_line[lab]
    # the line sits ON the boundary, one px each side (bd), widened evenly: drawn on one side only it moved every
    # edge by a px and the bench's errors sat on the lines (42-65% of them)
    lw = max(2, round(line_mm * px_mm))                       # under 2 px a grey line breaks where it runs slant
    edge = _wide_line(lab, bd, lw / 2) & ~line_px
    sketch = np.full(lab.shape, 255, np.uint8)
    sketch[edge] = SEP_GREY if separators else 0
    sketch[line_px] = 0
    line_ink = (hex_of(pal[int(np.bincount(index[line_px], minlength=len(pal)).argmax())])
                if line_px.any() else None)
    sketch_path = os.path.join(out_dir, f'{name}_sketch_seal0.png')
    save_png(to_image(sketch), sketch_path, dpi)
    black = np.where(sketch < 255, 0, 255).astype(np.uint8)  # the same sketch all in black, to show or share
    save_png(to_image(black), os.path.join(out_dir, f'{name}_sketch_black.png'), dpi)

    # 5. the numbers are the areas `textile paint` itself finds in that sketch (seal 0, from the file name), so
    # the CSV paints it back; each area takes the ink most of it had
    reg = pt.find_regions(sketch_path, size=W, seal=0, log=lambda m: None)
    # a sliver the lines cut off (smaller than --detail's smallest part) is no part of the design: it is inked
    # into the line beside it (a separator when --separators, so it prints as its neighbour), not numbered
    sliver = reg.area < max(20.0, keep_mm2 * px_mm ** 2)
    sliver[0] = False
    if sliver.any():
        m = sliver[reg.lab]
        sketch[m] = SEP_GREY if separators else 0
        save_png(to_image(sketch), sketch_path, dpi)
        save_png(to_image(np.where(sketch < 255, 0, 255).astype(np.uint8)),
                 os.path.join(out_dir, f'{name}_sketch_black.png'), dpi)
        reg = pt.find_regions(sketch_path, size=W, seal=0, log=lambda m: None)
    n = reg.n
    K = len(pal)
    inside = reg.lab > 0
    votes = np.bincount(reg.lab[inside].astype(np.int64) * K + index[inside], minlength=(n + 1) * K).reshape(-1, K)
    ink = votes.argmax(1)
    area = reg.area
    big = cv2.resize(rgb, (W, H), interpolation=cv2.INTER_AREA if rgb.shape[1] > W else cv2.INTER_LANCZOS4)
    path, missed = pt._numbers(reg, out_dir, name, big, kind='numbers', outline=True, full=True)
    sk_path, _ = pt._numbers(reg, out_dir, name, None, kind='sketch_numbers', full=True)
    letters = pt.maps(reg, out_dir, name, numbers=False, template=False)
    flat = pal[index]
    save_png(to_image(flat), os.path.join(out_dir, f'{name}_flat.png'), dpi)
    csv_path = os.path.join(out_dir, f'{name}_colors.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['Number', 'HEX', 'Colour', 'Share %', 'Group'])
        for i in range(1, n + 1):
            c = pal[ink[i]]
            gi = reg.group[i]
            w.writerow([i, '#' + hex_of(c), nm.colour_name(c), round(area[i] / (W * H) * 100, 3),
                        reg.letters[gi] if gi >= 0 else ''])
        if line_ink:                                      # the drawn outlines print in their own ink
            w.writerow(['lines', '#' + line_ink, 'sketch ki kaali line (design ki outline ka rang)', '', ''])
        else:
            w.writerow(['lines', 'fill', 'sketch ki line: paas ke hisse ka rang (koi outline nahi)', '', ''])
        if separators:
            w.writerow(['separators', 'fill', 'grey line: do rangon ki seema, paas ka rang', '', ''])

    # 6. the check: paint the sketch with that CSV, as the user will, and compare with the flat design
    back, bpal, _ = pt.paint(reg, *pt.plan(reg, pt.parse_colors(pt.csv_colours(csv_path)))[:3])
    match = float((np.abs(bpal[back].astype(int) - flat.astype(int)).sum(-1) < 30).mean() * 100)
    tiny = int((area[1:] < DETAIL_MM2['zyada'] * px_mm ** 2).sum())
    log(f'[number] {W}x{H} px, {n} hisse ({tiny} bahut chhote), {len(reg.letters)} group'
        + (f', outline {line_ink} = kaali line' if line_ink else '') + f'; sketch se wapas design: {match:.1f}% match')
    shares = np.bincount(index.ravel(), minlength=len(pal)) / index.size * 100
    return {'name': name, 'size_px': [W, H], 'areas': int(n), 'missed': int(missed), 'numbers': path,
            'sketch': sketch_path, 'sketch_numbers': sk_path, 'letters': letters['map'], 'match': round(match, 1),
            'tiny': tiny, 'groups': len(reg.letters),
            'csv': csv_path, 'inks': [(hex_of(c), nm.colour_name(c), round(float(s), 2)) for c, s in zip(pal, shares) if s > 0.05]}
