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


def _loop_area(pts):
    """Shoelace area of a closed (N,2) integer loop. Collapsing collinear runs
    never changes it, so this can be measured on the raw trace."""
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * abs(float(np.dot(x[:-1], y[1:]) - np.dot(y[:-1], x[1:])
                           + x[-1] * y[0] - y[-1] * x[0]))


def _collapse_collinear(pts):
    """Drop interior points that lie on a straight run, so a pixel edge becomes
    two endpoints instead of hundreds of unit steps. Takes and returns (N,2)."""
    if len(pts) < 3:
        return pts.astype(float)
    prev = np.empty_like(pts); prev[0] = pts[-1]; prev[1:] = pts[:-1]
    nxt = np.empty_like(pts); nxt[-1] = pts[0]; nxt[:-1] = pts[1:]
    cross = ((pts[:, 0] - prev[:, 0]) * (nxt[:, 1] - pts[:, 1])
             - (pts[:, 1] - prev[:, 1]) * (nxt[:, 0] - pts[:, 0]))
    corners = pts[cross != 0]
    return (corners if len(corners) else pts).astype(float)


def _dp_keep(pts, eps):
    """Douglas-Peucker over a single (N,2) array, iteratively.

    The straightforward recursive form rebuilds a numpy array at every level,
    which dominated tracing time (a quarter-million allocations for one design).
    Here the points are converted once and recursion is an explicit stack, so
    only a boolean keep-mask is produced. Same result, far less work — and no
    recursion limit to hit on a long boundary."""
    n = len(pts)
    keep = np.zeros(n, dtype=bool)
    if n == 0:
        return keep
    keep[0] = keep[n - 1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        ax, ay = pts[i]; bx, by = pts[j]
        abx, aby = bx - ax, by - ay
        seg = pts[i + 1:j]
        L = np.hypot(abx, aby)
        if L == 0:
            d = np.hypot(seg[:, 0] - ax, seg[:, 1] - ay)
        else:
            d = np.abs(abx * (seg[:, 1] - ay) - aby * (seg[:, 0] - ax)) / L
        k = int(np.argmax(d))
        if d[k] > eps:
            m = i + 1 + k
            keep[m] = True
            stack.append((i, m)); stack.append((m, j))
    return keep


def _simplify_loop(pts, eps):
    """pts: closed loop as an (N,2) float array. Returns the simplified loop."""
    if len(pts) < 4 or eps <= 0:
        return pts
    closed = np.vstack([pts, pts[:1]])          # repeat the first point to close
    keep = _dp_keep(closed, eps)
    out = closed[keep]
    if len(out) > 1 and out[0][0] == out[-1][0] and out[0][1] == out[-1][1]:
        out = out[:-1]
    return out


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
        if len(loop) < 3:
            continue
        pts = np.asarray(loop, dtype=np.int64)
        # Discard specks BEFORE the costly collapse/simplify. A painterly design
        # traces thousands of tiny loops that min_area throws away; measuring
        # area on the raw trace first skips all that work for them.
        if _loop_area(pts) < min_area:
            continue
        poly = _collapse_collinear(pts)
        if len(poly) < 3:
            continue
        poly = _simplify_loop(poly, simplify)
        if len(poly) < 3:
            continue
        if smooth:
            poly = _chaikin([(float(px), float(py)) for px, py in poly], smooth)
        out.append([(float(px), float(py)) for px, py in poly])
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
