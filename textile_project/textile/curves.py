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


def smooth(p, scale):
    """An outline smoothed for a sketch: the source's pixel stairs (`scale` px each at this size) averaged
    away along the line, real corners (two straight arms) held, no point moved more than ~one source px."""
    if len(p) < 8:
        return p
    arm = max(5, int(round(2 * scale)))
    corners = ed.find_corners(p, arm=arm, deg=45, dev_max=max(0.9, 0.35 * scale))
    return ed.smooth_outline(p, 1.2 * scale, 0.9 * scale, corners)


def bold(lab, line_patch, scale, width_px, keep_core=None):
    """The smooth, bold sketch: every part's smoothed outline stroked `width_px` wide in black on white,
    anti-aliased; a part that is a drawn line is filled black. `keep_core` (H x W bool): pixels painted white
    again afterwards, so a small part (a dot, a thin petal) the bold stroke would fill keeps its white middle.
    Returns (image, svg text)."""
    H, W = lab.shape
    img = np.full((H, W), 255, np.uint8)
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
        cv2.polylines(img, [np.round(q * S).astype(np.int32)], True, 0, thickness=int(width_px),
                      lineType=cv2.LINE_AA, shift=4)
    if keep_core is not None:
        img[keep_core] = 255
    for q in fills:
        cv2.fillPoly(img, [np.round(q * S).astype(np.int32)], 0, lineType=cv2.LINE_AA, shift=4)
        cv2.polylines(img, [np.round(q * S).astype(np.int32)], True, 0, thickness=2, lineType=cv2.LINE_AA, shift=4)

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
