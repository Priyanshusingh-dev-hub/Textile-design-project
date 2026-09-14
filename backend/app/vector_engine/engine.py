"""Raster-to-vector tracing: turns a separation mask into the same kind of
smooth Bezier outlines a designer gets by redrawing a shape with the pen
tool, instead of a jagged pixel staircase.

Pipeline: binary mask -> Gaussian blur (sub-pixel anti-aliased field) ->
marching-squares contour at the 50% level (gives smooth sub-pixel boundary
points, not pixel corners) -> Douglas-Peucker simplification (drops
redundant near-collinear points) -> Catmull-Rom-to-cubic-Bezier fit with
corner detection (sharp turns stay sharp corners, gentle turns become
smooth curves) -> an SVG <path>.
"""
import math
import numpy as np
from PIL import Image, ImageFilter

# ---------- 1. blur: binary mask -> smooth scalar field ----------

def blur_mask(binary_mask: np.ndarray, radius: float = 1.5) -> np.ndarray:
    """binary_mask: 2D array of 0/255 (or 0/1). Returns a float32 field in
    [0,255] with anti-aliased, sub-pixel-accurate transitions at edges."""
    m = (binary_mask > 0).astype(np.uint8) * 255
    img = Image.fromarray(m).filter(ImageFilter.GaussianBlur(radius=radius))
    return np.asarray(img, dtype=np.float32)

# ---------- 2. marching squares ----------

# state -> list of (edge_a, edge_b) segments. Bits: state = a + 2b + 4c + 8d
# where a=TL, b=TR, c=BR, d=BL (1 = inside the shape). Each entry connects
# exactly the edges where the two endpoint corners are on opposite sides of
# the level -- getting this table wrong (as an earlier version of this file
# did) makes neighbouring cells disagree about which shared edges carry a
# crossing, so segments never link into closed contours.
_CASES = {
    0: [], 15: [],
    1: [('top', 'left')],
    2: [('top', 'right')],
    3: [('left', 'right')],
    4: [('bottom', 'right')],
    5: [('top', 'left'), ('bottom', 'right')],
    6: [('top', 'bottom')],
    7: [('left', 'bottom')],
    8: [('left', 'bottom')],
    9: [('top', 'bottom')],
    10: [('top', 'right'), ('left', 'bottom')],
    11: [('bottom', 'right')],
    12: [('left', 'right')],
    13: [('top', 'right')],
    14: [('top', 'left')],
}

def _lerp_point(level, v0, v1, p0, p1):
    t = 0.5 if v1 == v0 else (level - v0) / (v1 - v0)
    t = min(1.0, max(0.0, t))
    # cast to plain python float: a numpy.float32 and an equal-valued python
    # float can hash differently, which silently breaks the dict/set-based
    # endpoint matching used to link segments into contours below.
    return (float(p0[0] + (p1[0] - p0[0]) * t), float(p0[1] + (p1[1] - p0[1]) * t))

def marching_squares(field: np.ndarray, level: float = 127.5):
    """Returns a list of closed contours, each an (N,2) array of (x, y)
    sub-pixel points. Coordinates are in pixel space (x=col, y=row)."""
    h, w = field.shape
    top_cache, left_cache = {}, {}

    def top_pt(i, j):
        key = (i, j)
        if key not in top_cache:
            top_cache[key] = _lerp_point(level, field[i, j], field[i, j + 1], (j, i), (j + 1, i))
        return top_cache[key]

    def bottom_pt(i, j):
        return top_pt(i + 1, j)

    def left_pt(i, j):
        key = (i, j)
        if key not in left_cache:
            left_cache[key] = _lerp_point(level, field[i, j], field[i + 1, j], (j, i), (j, i + 1))
        return left_cache[key]

    def right_pt(i, j):
        return left_pt(i, j + 1)

    getters = {'top': top_pt, 'bottom': bottom_pt, 'left': left_pt, 'right': right_pt}

    segments = []
    for i in range(h - 1):
        row = field[i]; nrow = field[i + 1]
        for j in range(w - 1):
            a, b, c, d = row[j], row[j + 1], nrow[j + 1], nrow[j]
            state = (a > level) | ((b > level) << 1) | ((c > level) << 2) | ((d > level) << 3)
            for e1, e2 in _CASES.get(int(state), []):
                p1 = getters[e1](i, j)
                p2 = getters[e2](i, j)
                segments.append((p1, p2))

    # link segments sharing an endpoint into closed polylines
    adj = {}
    for p1, p2 in segments:
        adj.setdefault(p1, []).append(p2)
        adj.setdefault(p2, []).append(p1)

    visited_edges = set()
    contours = []
    for p1, p2 in segments:
        e = (p1, p2)
        if e in visited_edges or (p2, p1) in visited_edges:
            continue
        path = [p1, p2]
        visited_edges.add(e)
        cur = p2
        while True:
            nexts = [n for n in adj.get(cur, []) if (cur, n) not in visited_edges and (n, cur) not in visited_edges]
            if not nexts:
                break
            nxt = nexts[0]
            visited_edges.add((cur, nxt))
            path.append(nxt)
            cur = nxt
            if cur == path[0]:
                break
        if len(path) >= 4 and path[0] == path[-1]:
            contours.append(np.array(path[:-1], dtype=np.float64))
    return contours

# ---------- 3. Douglas-Peucker simplification ----------

def _perp_dist(pt, a, b):
    if a[0] == b[0] and a[1] == b[1]:
        return math.hypot(pt[0] - a[0], pt[1] - a[1])
    num = abs((b[0] - a[0]) * (a[1] - pt[1]) - (a[0] - pt[0]) * (b[1] - a[1]))
    den = math.hypot(b[0] - a[0], b[1] - a[1])
    return num / den

def douglas_peucker(points, epsilon=0.8):
    if len(points) < 3:
        return points
    a, b = points[0], points[-1]
    idx, dmax = -1, -1.0
    for i in range(1, len(points) - 1):
        d = _perp_dist(points[i], a, b)
        if d > dmax:
            idx, dmax = i, d
    if dmax > epsilon:
        left = douglas_peucker(points[:idx + 1], epsilon)
        right = douglas_peucker(points[idx:], epsilon)
        return np.vstack([left[:-1], right])
    return np.array([a, b])

def simplify_closed(points, epsilon=0.8):
    if len(points) < 5:
        return points
    n = len(points)
    split = n // 2
    a = douglas_peucker(np.vstack([points[split:], points[:1]]), epsilon)
    b = douglas_peucker(points[:split + 1], epsilon)
    return np.vstack([b[:-1], a])

# ---------- 4. Catmull-Rom -> cubic Bezier with corner detection ----------

def _angle_at(p_prev, p, p_next):
    v1 = (p[0] - p_prev[0], p[1] - p_prev[1])
    v2 = (p_next[0] - p[0], p_next[1] - p[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 < 1e-9 or n2 < 1e-9:
        return 180.0
    cos_a = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cos_a))

def path_to_bezier_d(points, corner_angle_deg=32, smoothing=1.0):
    """points: closed polygon (N,2), last point implicitly connects to first.
    A vertex turning sharper than corner_angle_deg is kept as a hard corner
    (no tangent smoothing through it) -- everything else gets a Catmull-Rom
    derived cubic Bezier tangent, i.e. a real smooth pen-tool curve."""
    n = len(points)
    if n < 3:
        return ''
    pts = [tuple(p) for p in points]
    is_corner = [False] * n
    for i in range(n):
        a = pts[(i - 1) % n]; p = pts[i]; b = pts[(i + 1) % n]
        turn = 180 - _angle_at(a, p, b)
        is_corner[i] = turn > corner_angle_deg

    def tangent(i):
        p0 = pts[(i - 1) % n]; p2 = pts[(i + 1) % n]
        return ((p2[0] - p0[0]) * smoothing / 6.0, (p2[1] - p0[1]) * smoothing / 6.0)

    d = f'M {pts[0][0]:.2f},{pts[0][1]:.2f} '
    for i in range(n):
        j = (i + 1) % n
        p1, p2 = pts[i], pts[j]
        if is_corner[i] and is_corner[j]:
            d += f'L {p2[0]:.2f},{p2[1]:.2f} '
            continue
        t1 = (0.0, 0.0) if is_corner[i] else tangent(i)
        t2 = (0.0, 0.0) if is_corner[j] else tangent(j)
        c1 = (p1[0] + t1[0], p1[1] + t1[1])
        c2 = (p2[0] - t2[0], p2[1] - t2[1])
        d += f'C {c1[0]:.2f},{c1[1]:.2f} {c2[0]:.2f},{c2[1]:.2f} {p2[0]:.2f},{p2[1]:.2f} '
    return d + 'Z'

# ---------- 5. mask -> path / full SVG ----------

def mask_to_path_d(binary_mask: np.ndarray, blur_radius=1.5, simplify_epsilon=0.8, corner_angle_deg=32):
    field = blur_mask(binary_mask, blur_radius)
    contours = marching_squares(field, level=127.5)
    parts = []
    for c in contours:
        simplified = simplify_closed(c, simplify_epsilon)
        d = path_to_bezier_d(simplified, corner_angle_deg)
        if d:
            parts.append(d)
    return ' '.join(parts)

def build_svg(layers, size, blur_radius=1.5, simplify_epsilon=0.8, corner_angle_deg=32):
    """layers: list of (color_hex, binary_mask_2d_array). Returns an SVG
    document string: one <path> per ink colour, fill-rule evenodd so holes
    (e.g. a flower centre) render correctly without explicit hole tracking."""
    w, h = size
    body = []
    for color, mask in layers:
        d = mask_to_path_d(mask, blur_radius, simplify_epsilon, corner_angle_deg)
        if d:
            body.append(f'<path d="{d}" fill="{color}" fill-rule="evenodd"/>')
    inner = '\n'.join(body)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}">\n{inner}\n</svg>')
