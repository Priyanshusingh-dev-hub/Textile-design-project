"""Turn a binary ink mask into clean vector outlines.

Screen-printing screens scale better from vector than from pixels, so this
traces the exact boundary between inked and blank pixels, links those unit
edges into closed loops (outer shapes wind one way, holes the other, so
even-odd fill renders holes correctly), then simplifies the loops with
Douglas-Peucker and optionally rounds the corners with Chaikin smoothing.
Because the trace follows the real pixel boundary, one flat colour per shape
and no overlap are preserved — the vector is faithful to the separation.
"""
from array import array

import numpy as np

# each ON pixel contributes its 4 border edges, walked clockwise so inside is
# always on the right; outer loops come out clockwise, holes counter-clockwise.
_SIDES = (
    ('up',    (0, 0), (1, 0)),   # top edge, left->right
    ('right', (1, 0), (1, 1)),   # right edge, top->bottom
    ('down',  (1, 1), (0, 1)),   # bottom edge, right->left
    ('left',  (0, 1), (0, 0)),   # left edge, bottom->top
)


def _trace_loops(mask):
    """The closed boundary loops of the ON region, as (N,2) int64 (x, y) arrays.

    Every ON pixel contributes its border edges (see _SIDES); edges are walked
    into loops by always taking the most recently added unused edge leaving the
    current vertex, starting from vertices in the order their first edge was
    added. That is the same walk a dict of edge lists gives — same loops, same
    order — but held in flat integer arrays: at a 12-inch design a painterly
    ink has millions of edges, and building and walking Python tuples was most
    of the tracing time."""
    h, w = mask.shape
    padded = np.zeros((h + 2, w + 2), dtype=bool)
    padded[1:-1, 1:-1] = mask
    ys, xs = np.nonzero(mask)
    flags = {'up': ~padded[ys, xs + 1], 'down': ~padded[ys + 2, xs + 1],
             'left': ~padded[ys + 1, xs], 'right': ~padded[ys + 1, xs + 2]}
    W = w + 1                                      # vertex grid is (h+1) x (w+1)
    s_parts, e_parts = [], []
    for name, (ax, ay), (bx, by) in _SIDES:
        sel = flags[name]
        sx = xs[sel].astype(np.int64); sy = ys[sel].astype(np.int64)
        s_parts.append((sy + ay) * W + sx + ax)
        e_parts.append((sy + by) * W + sx + bx)
    starts = np.concatenate(s_parts); ends = np.concatenate(e_parts)
    if not len(starts):
        return []
    codes, first = np.unique(starts, return_index=True)
    sv = np.searchsorted(codes, starts)            # compact id of each edge's start
    ev = np.searchsorted(codes, ends)
    ev = np.where(codes[np.minimum(ev, len(codes) - 1)] == ends, ev, -1)
    order = np.argsort(sv, kind='stable')          # grouped by vertex, in the order added
    cnt = np.bincount(sv, minlength=len(codes))
    off = array('q', (np.cumsum(cnt) - cnt).tolist())
    tgt = array('q', ev[order].tolist())
    rem = cnt.tolist()                             # 1 or 2 each: cheap small ints
    flat, bounds = array('q'), [0]
    for v in np.argsort(first, kind='stable').tolist():
        while rem[v]:
            flat.append(v)
            rem[v] -= 1
            cur = tgt[off[v] + rem[v]]
            while cur != v:
                flat.append(cur)
                if cur < 0 or not rem[cur]:
                    break                          # open chain (can't happen on a closed mask)
                rem[cur] -= 1
                cur = tgt[off[cur] + rem[cur]]
            bounds.append(len(flat))
    ids = np.frombuffer(flat, dtype=np.int64)
    pts = np.stack([codes[ids] % W, codes[ids] // W], 1)
    return [pts[bounds[i]:bounds[i + 1]] for i in range(len(bounds) - 1)]


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


_SHORT_SPAN = 48


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
    P = pts.tolist()
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        ax, ay = P[i]; bx, by = P[j]
        abx, aby = bx - ax, by - ay
        L = float(np.hypot(abx, aby))
        if j - i <= _SHORT_SPAN and L != 0:
            # short spans in plain Python: numpy's per-call cost dominated
            # on the tens of thousands of small loops a painterly design
            # traces. Same float operations, and the first maximum wins,
            # exactly as argmax picks it.
            best, k = -1.0, 0
            for q in range(i + 1, j):
                px, py = P[q]
                dq = abs(abx * (py - ay) - aby * (px - ax)) / L
                if dq > best:
                    best, k = dq, q - i - 1
            dk = best
        else:
            seg = pts[i + 1:j]
            if L == 0:
                d = np.hypot(seg[:, 0] - ax, seg[:, 1] - ay)
            else:
                d = np.abs(abx * (seg[:, 1] - ay) - aby * (seg[:, 0] - ax)) / L
            k = int(np.argmax(d)); dk = d[k]
        if dk > eps:
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
    out = []
    for pts in _trace_loops(mask):
        if len(pts) < 3:
            continue
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


def path_data(mask, simplify=1.0, smooth=0, min_area=6.0):
    """The SVG path `d` for one ink's mask — the expensive part (tracing).
    Compute it once and hand it to both `layer_svg` and `build_svg`; a
    package with vectors used to trace every mask twice."""
    return _path_d(mask_to_loops(mask, simplify, smooth, min_area))


def _doc(size, body):
    w, h = size
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
            f'width="{w}" height="{h}" shape-rendering="geometricPrecision">{body}</svg>')


def _path(d, color):
    return f'<path d="{d}" fill="{color}" fill-rule="evenodd"/>' if d else ''


def layer_svg(mask, color, size, simplify=1.0, smooth=0, min_area=6.0, d=None):
    """One-ink SVG (its shapes in `color` on a transparent ground). Pass `d`
    from `path_data` to skip re-tracing."""
    if d is None:
        d = path_data(mask, simplify, smooth, min_area)
    return _doc(size, _path(d, color))


def build_svg(layers, size, simplify=1.0, smooth=0, min_area=6.0, paths=None):
    """Combined SVG of all inks, back (first) to front (last).
    layers: list of (color_hex, binary mask). Pass `paths` (one `d` per layer,
    from `path_data`) to skip re-tracing."""
    if paths is None:
        paths = [path_data(mask, simplify, smooth, min_area) for _, mask in layers]
    return _doc(size, ''.join(_path(d, color) for (color, _), d in zip(layers, paths)))
