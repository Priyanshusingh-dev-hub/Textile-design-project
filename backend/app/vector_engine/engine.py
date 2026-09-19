"""Turn a binary ink mask into clean vector outlines.

Screen-printing screens scale better from vector than from pixels, so this
traces the exact boundary between inked and blank pixels, links those unit
edges into closed loops (outer shapes wind one way, holes the other, so
even-odd fill renders holes correctly), then simplifies the loops with
Douglas-Peucker and optionally rounds the corners with Chaikin smoothing.
Because the trace follows the real pixel boundary, one flat colour per shape
and no overlap are preserved — the vector is faithful to the separation.
"""
import numpy as np

# each ON pixel contributes its 4 border edges, walked clockwise so inside is
# always on the right; outer loops come out clockwise, holes counter-clockwise.
_SIDES = (
    ('up',    (0, 0), (1, 0)),   # top edge, left->right
    ('right', (1, 0), (1, 1)),   # right edge, top->bottom
    ('down',  (1, 1), (0, 1)),   # bottom edge, right->left
    ('left',  (0, 1), (0, 0)),   # left edge, bottom->top
)


def _boundary_edges(mask):
    """Directed unit edges on the boundary of the ON region, as a dict
    start_point -> list of end_points (grid coordinates, x=col, y=row)."""
    h, w = mask.shape
    padded = np.zeros((h + 2, w + 2), dtype=bool)
    padded[1:-1, 1:-1] = mask
    ys, xs = np.nonzero(mask)
    edges = {}
    # neighbour lookups on the padded array (shifted by +1)
    up = ~padded[ys, xs + 1]        # pixel above is off
    down = ~padded[ys + 2, xs + 1]
    left = ~padded[ys + 1, xs]
    right = ~padded[ys + 1, xs + 2]
    flags = {'up': up, 'right': right, 'down': down, 'left': left}
    for name, (ax, ay), (bx, by) in _SIDES:
        border = flags[name]
        sel = np.nonzero(border)[0]
        sx = xs[sel]; sy = ys[sel]
        for i in range(len(sel)):
            a = (int(sx[i] + ax), int(sy[i] + ay))
            b = (int(sx[i] + bx), int(sy[i] + by))
            edges.setdefault(a, []).append(b)
    return edges


def _link_loops(edges):
    """Walk the directed edges into closed polygons."""
    loops = []
    for start in list(edges.keys()):
        while edges.get(start):
            loop = [start]
            cur = edges[start].pop()
            while cur != start:
                loop.append(cur)
                nxts = edges.get(cur)
                if not nxts:
                    break                      # open chain (shouldn't happen on a closed mask)
                # prefer to keep going straight to avoid crossing at a pinch vertex
                nxt = nxts.pop()
                cur = nxt
            loops.append(loop)
    return loops


def _collapse_collinear(poly):
    """Drop interior points that lie on a straight run, so a pixel edge becomes
    two endpoints instead of hundreds of unit steps."""
    if len(poly) < 3:
        return poly
    out = []
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i - 1]
        bx, by = poly[i]
        cx, cy = poly[(i + 1) % n]
        # cross product of (b-a) and (c-b); zero => collinear
        if (bx - ax) * (cy - by) - (by - ay) * (cx - bx) != 0:
            out.append((bx, by))
    return out or poly


def _dp(points, eps):
    """Douglas-Peucker simplification of an open polyline."""
    if len(points) < 3 or eps <= 0:
        return points
    a = np.array(points[0], float); b = np.array(points[-1], float)
    pts = np.array(points, float)
    ab = b - a; L = np.hypot(*ab)
    rel = pts - a
    if L == 0:
        d = np.hypot(rel[:, 0], rel[:, 1])
    else:
        d = np.abs(ab[0] * rel[:, 1] - ab[1] * rel[:, 0]) / L   # 2D cross magnitude
    idx = int(np.argmax(d))
    if d[idx] > eps:
        left = _dp(points[:idx + 1], eps)
        right = _dp(points[idx:], eps)
        return left[:-1] + right
    return [points[0], points[-1]]


def _simplify_loop(poly, eps):
    if len(poly) < 4 or eps <= 0:
        return poly
    closed = _dp(poly + [poly[0]], eps)
    return closed[:-1] if len(closed) > 1 and closed[0] == closed[-1] else closed


def _chaikin(poly, iterations):
    """Round corners by cutting each one — turns a blocky outline into smooth
    curves while staying close to the original shape."""
    pts = poly
    for _ in range(max(0, iterations)):
        if len(pts) < 3:
            break
        new = []
        n = len(pts)
        for i in range(n):
            ax, ay = pts[i]; bx, by = pts[(i + 1) % n]
            new.append((ax * 0.75 + bx * 0.25, ay * 0.75 + by * 0.25))
            new.append((ax * 0.25 + bx * 0.75, ay * 0.25 + by * 0.75))
        pts = new
    return pts


def mask_to_loops(mask, simplify=1.0, smooth=0, min_area=6.0):
    """Binary mask -> list of closed float polygons (x,y), simplified/smoothed.
    Loops enclosing less area than min_area (pixels) are dropped as specks."""
    mask = np.asarray(mask).astype(bool)
    if not mask.any():
        return []
    loops = _link_loops(_boundary_edges(mask))
    out = []
    for loop in loops:
        poly = _collapse_collinear(loop)
        if len(poly) < 3:
            continue
        arr = np.array(poly, float)
        area = 0.5 * abs(np.dot(arr[:, 0], np.roll(arr[:, 1], -1)) - np.dot(arr[:, 1], np.roll(arr[:, 0], -1)))
        if area < min_area:
            continue
        poly = _simplify_loop([(float(x), float(y)) for x, y in poly], simplify)
        if len(poly) < 3:
            continue
        if smooth:
            poly = _chaikin(poly, smooth)
        out.append(poly)
    return out


def _path_d(loops):
    parts = []
    for poly in loops:
        if len(poly) < 3:
            continue
        d = 'M' + ' '.join(f'{x:.2f},{y:.2f}' for x, y in poly) + 'Z'
        parts.append(d)
    return ' '.join(parts)


def layer_svg(mask, color, size, simplify=1.0, smooth=0, min_area=6.0):
    """One-ink SVG (its shapes in `color` on a transparent ground)."""
    loops = mask_to_loops(mask, simplify, smooth, min_area)
    d = _path_d(loops)
    w, h = size
    path = f'<path d="{d}" fill="{color}" fill-rule="evenodd"/>' if d else ''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}" shape-rendering="geometricPrecision">{path}</svg>')


def build_svg(layers, size, simplify=1.0, smooth=0, min_area=6.0):
    """Combined SVG of all inks, back (first) to front (last).
    layers: list of (color_hex, binary mask)."""
    w, h = size
    body = []
    for color, mask in layers:
        d = _path_d(mask_to_loops(mask, simplify, smooth, min_area))
        if d:
            body.append(f'<path d="{d}" fill="{color}" fill-rule="evenodd"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}" shape-rendering="geometricPrecision">'
            + ''.join(body) + '</svg>')
