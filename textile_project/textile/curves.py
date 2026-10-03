"""The sketch drawn as smooth curves: every part's outline traced, smoothed along
itself (a round edge stays round, a corner with two straight arms stays a sharp
corner: textile edges' own `find_corners` / `smooth_outline`), and drawn in
crisp, dark, anti-aliased strokes, plus the same lines as an SVG that stays sharp
at any zoom. For looking at, sharing and drawing over: the sketch `textile
paint` reads stays the pixel one (`NAME_sketch_seal0.png`), whose areas are the
numbers.

  bold(lab, line_patch, ...)  -> (image H x W uint8, svg text)

`lab` is the design's parts (H x W, 0 unused), `line_patch[i]` says part i is
itself a drawn line (a thin dark outline), filled solid instead of outlined.
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy import ndimage

from . import edges as ed

EDGE_SHIFT = 0.5        # contour points are boundary-pixel centres: half a pixel out is the true edge


def _outlines(mask):
    """The closed outlines (outer and holes) of one part's mask, as float (n, 2) x,y on the true pixel edge."""
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    out = []
    for c in cs:
        p = c[:, 0, :].astype(np.float64)
        if len(p) >= 3:
            t = np.roll(p, -1, 0) - np.roll(p, 1, 0)
            t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-9
            p = p - EDGE_SHIFT * np.stack([t[:, 1], -t[:, 0]], 1)
        out.append(p)
    return out


STRAIGHT_DEV = 0.9      # a stretch within this many source px of its chord is a straight line, drawn straight
SPLINE_SMOOTH = 1.6     # spline smoothing, in source px of allowed wobble per point


def _spline(seg, scale, closed):
    """One stretch (n, 2) fitted by a smoothing cubic spline: a sine-like wave, a long arc, a spiral all come out
    as one flowing curve, the source's pixel stairs (and the stairs' wobble) averaged away. Ends are held when
    the stretch is open (they are corners)."""
    from scipy.interpolate import splprep, splev
    n = len(seg)
    pts = seg
    if closed:
        pts = np.vstack([seg, seg[:1]])
    # drop repeated points (splprep needs distinct ones)
    keep = np.r_[True, np.linalg.norm(np.diff(pts, axis=0), axis=1) > 1e-6]
    pts = pts[keep]
    if len(pts) < 5:
        return seg
    w = np.ones(len(pts))
    blob = 2.5 if closed and n < 60 * scale else 1.0       # a small closed blob (a border dot) wobbles more than it means
    if not closed:
        w[0] = w[-1] = 50.0                              # ends stay where they are
    try:
        tck, u = splprep([pts[:, 0], pts[:, 1]], w=w, s=len(pts) * (SPLINE_SMOOTH * blob * scale) ** 2 * 0.25,
                         per=1 if closed else 0, k=3)
    except Exception:
        return seg
    m = max(int(n), 8)
    t = np.linspace(0, 1, m, endpoint=not closed)
    x, y = splev(t, tck)
    return np.stack([x, y], 1)


def smooth(p, scale):
    """An outline smoothed for a sketch. Real corners (two straight arms) split it into stretches; each stretch
    is a straight line when it never leaves its chord, else a smoothing spline. A round shape with no corner
    is one closed spline."""
    if len(p) < 8:
        return p
    arm = max(5, int(round(2 * scale)))
    corners = ed.find_corners(p, arm=arm, deg=45, dev_max=max(0.9, 0.35 * scale))
    n = len(p)
    if not corners:
        return _spline(p, scale, True)
    out = []
    for a in range(len(corners)):
        s, e = corners[a], corners[(a + 1) % len(corners)]
        idx = np.arange(s, e + 1 if e > s else e + n + 1) % n
        seg = p[idx]
        if len(seg) < 4:
            out.append(seg)
            continue
        c = seg[-1] - seg[0]
        L = np.linalg.norm(c)
        dev = (np.abs((seg[:, 0] - seg[0, 0]) * c[1] - (seg[:, 1] - seg[0, 1]) * c[0]).max() / L) if L > 1e-6 else 9
        if dev <= STRAIGHT_DEV * scale:
            t = np.linspace(0, 1, max(2, int(L)))[:, None]
            out.append(seg[0] + t * c)                  # a straight edge stays dead straight
        else:
            out.append(_spline(seg, scale, False))
    return np.vstack(out)


def bold(lab, line_patch, scale, width_px, keep_core=None, k=1):
    """The smooth, bold sketch: every part's smoothed outline stroked `width_px` wide in black on white,
    anti-aliased; a part that is a drawn line is filled black. `keep_core` (H x W bool): pixels painted white
    again afterwards, so a small part (a dot, a thin petal) the bold stroke would fill keeps its white middle.
    `k`: the canvas is drawn k times bigger, straight from the curves (a blank slate, not an enlarged image):
    every coordinate and the stroke are multiplied by k, so the lines stay as crisp as the first px.
    Returns (image, svg text; the SVG stays in the design's own units)."""
    H, W = lab.shape
    img = np.full((H * k, W * k), 255, np.uint8)
    S = 16                                              # cv2 shift 4: 1/16 px sub-pixel positions
    boxes = ndimage.find_objects(lab)
    fills, strokes, svg = [], [], []
    for i, sl in enumerate(boxes, 1):
        if sl is None:
            continue
        y0, x0 = max(sl[0].start - 1, 0), max(sl[1].start - 1, 0)
        y1, x1 = min(sl[0].stop + 1, H), min(sl[1].stop + 1, W)
        for p in _outlines(lab[y0:y1, x0:x1] == i):
            q = smooth(p, scale) + (x0, y0)
            if line_patch[i]:
                fills.append(q)
            else:
                strokes.append(q)
    for q in strokes:
        cv2.polylines(img, [np.round(q * k * S).astype(np.int32)], True, 0, thickness=int(width_px * k),
                      lineType=cv2.LINE_AA, shift=4)
    if keep_core is not None:
        kc = keep_core if k == 1 else cv2.resize(keep_core.astype(np.uint8), (W * k, H * k),
                                                 interpolation=cv2.INTER_NEAREST) > 0
        img[kc] = 255
    for q in fills:
        cv2.fillPoly(img, [np.round(q * k * S).astype(np.int32)], 0, lineType=cv2.LINE_AA, shift=4)
        cv2.polylines(img, [np.round(q * k * S).astype(np.int32)], True, 0, thickness=2 * k,
                      lineType=cv2.LINE_AA, shift=4)

    def path(q):
        a = cv2.approxPolyDP(q.astype(np.float32).reshape(-1, 1, 2), 0.3, True)[:, 0, :]
        return 'M' + ' L'.join(f'{x:.1f} {y:.1f}' for x, y in a) + ' Z'

    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    svg.append(f'<rect width="{W}" height="{H}" fill="white"/>')
    svg.append(f'<g fill="none" stroke="black" stroke-width="{width_px}" stroke-linejoin="round" stroke-linecap="round">')
    svg += [f'<path d="{path(q)}"/>' for q in strokes]
    svg.append('</g><g fill="black" stroke="none">')
    svg += [f'<path d="{path(q)}"/>' for q in fills]
    svg.append('</g></svg>')
    return img, '\n'.join(svg)


def colour_fill(rgb, k, sigma=1.2):
    """A flat-colour image (H x W x 3, few colours) drawn k times bigger with smooth edges: each colour's mask is
    blurred a little, scaled up (cubic) and the strongest colour wins each pixel, so edges follow the same kind of
    curve as the outlines instead of the source's stairs. One colour per pixel, no mixed colours."""
    H, W = rgb.shape[:2]
    cols, inv = np.unique(rgb.reshape(-1, 3), axis=0, return_inverse=True)
    inv = inv.reshape(H, W)
    best = np.full((H * k, W * k), -1.0, np.float32)
    idx = np.zeros((H * k, W * k), np.uint8)
    for c in range(len(cols)):
        m = cv2.GaussianBlur((inv == c).astype(np.float32), (0, 0), sigma)
        m = cv2.resize(m, (W * k, H * k), interpolation=cv2.INTER_CUBIC) if k > 1 else m
        up = m > best
        best[up] = m[up]
        idx[up] = c
    return cols.astype(np.uint8)[idx]


def colour_sketch(colour, bold_img):
    """The bold lines drawn over the colour fill: where the line is dark the colour goes dark (multiply), so the
    anti-aliased edges blend into the colour instead of leaving a white halo."""
    return (colour.astype(np.uint16) * bold_img[..., None] // 255).astype(np.uint8)
