"""Build LOOMY DADA, the LoomLab Studio mascot, as a rigged, animated GLB.

    pip install bpy==5.0.1 pillow scipy        # Blender as a Python module (Python 3.11)
    python build_loomy_dada.py --out .         # -> loomy-dada.glb (--blend also saves loomy-dada.blend)
    python render_previews.py --blend loomy-dada.blend --out previews/

Everything is generated from code -- no hand-made files -- so the character
can be rebuilt, tweaked and re-exported the same way every time.

Model: ~1 unit (metre) tall, centred at the origin, feet on the ground plane,
facing +Z in glTF (Blender -Y). One mesh, two materials: an opaque PBR atlas
(base colour, ORM, normal, emissive, 2048 px, see loomy_textures.py) and the
transparent emissive holographic visor. Quad topology from analytic shapes.

Rig: humanoid bone names (Hips, Spine, Head, Left/RightShoulder, ...UpperArm,
...LowerArm, ...Hand, thumb/index/middle/ring fingers, ...UpperLeg,
...LowerLeg, ...Foot, LeftHandProp for the tablet). Rest pose = A-pose.
Animations: Neutral_APose, Idle, Wave, ThumbsUp, Processing.
"""
import argparse
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import loomy_textures as T  # noqa: E402

# ----------------------------------------------------------------------------
# proportions (metres, Blender: Z up, the character looks down -Y)
# ----------------------------------------------------------------------------
BODY_Z0, BODY_Z1 = 0.31, 0.90                 # wound thread
BANDS = [(0.31, 0.46), (0.46, 0.76), (0.76, 0.90)]   # teal / cream face band / teal
FLANGE_R = 0.305
SHOULDER_Z = 0.555
ARM_SPREAD = math.radians(40)                 # A-pose: arms 40 degrees from vertical
UPPER_ARM, FORE_ARM = 0.098, 0.088
HIP_X, HIP_Z, KNEE_Z, ANKLE_Z = 0.105, 0.245, 0.170, 0.105
EYE_X, EYE_Z = 0.080, 0.646
VISOR_Z0, VISOR_Z1, VISOR_R, VISOR_SPAN = 0.585, 0.708, 0.287, math.radians(79)
FACE = 'smile'          # 'calm' (--face calm): a closed gentle mouth and lifted inner brows, for the app's
                        # careful/oops stills; the GLB keeps the open smile


def body_radius(z):
    """Each thread section bulges a little (wound thread), with a groove where
    two sections meet."""
    for lo, hi in BANDS:
        if lo - 1e-9 <= z <= hi + 1e-9:
            s = max(0.0, math.sin(math.pi * (z - lo) / (hi - lo)))
            return 0.244 + 0.009 * s ** 0.6
    return 0.244


def front_point(x, z, off=0.0):
    """A point on the body surface in front (-Y), x measured along the arc."""
    r = body_radius(z) + off
    a = x / r
    return Vector((r * math.sin(a), -r * math.cos(a), z))


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


# ----------------------------------------------------------------------------
# a single mesh builder: vertices, quad faces, per-loop UVs, material per face,
# bone weights per vertex
# ----------------------------------------------------------------------------
class Builder:
    def __init__(self):
        self.verts, self.faces, self.uvs, self.mats, self.smooth = [], [], [], [], []
        self.weights = []                     # per vertex: {bone: weight}

    def add_vert(self, p, w):
        self.verts.append(tuple(p))
        self.weights.append(dict(w) if isinstance(w, dict) else {w: 1.0})
        return len(self.verts) - 1

    def add_face(self, idx, uv, mat=0, smooth=True):
        self.faces.append(tuple(idx)); self.uvs.append(tuple(uv)); self.mats.append(mat); self.smooth.append(smooth)

    def grid(self, P, UV, W, closed_u=False, mat=0, smooth=True, flip=False, closed_v=False):
        """P: rows x cols of points, UV: same shape of (u, v), W: per point weight (bone or dict) or
        a function of the point. closed_u wraps the last column onto the first (UV keeps going to 1),
        closed_v does the same for rows (a torus). A row whose points all coincide (a pole) becomes
        ONE vertex and its quads become triangles, so the surface is closed and clean.
        Face normal = (along a row) x (down the rows); flip reverses it."""
        rows, cols = len(P), len(P[0])
        ids = []
        for i in range(rows):
            row = P[i]
            pole = max((Vector(row[k]) - Vector(row[0])).length for k in range(cols)) < 1e-9
            if pole:
                v = self.add_vert(row[0], W(row[0]) if callable(W) else W)
                ids.append([v] * cols)
            else:
                ids.append([self.add_vert(row[j], W(row[j]) if callable(W) else W) for j in range(cols)])
        ncol = cols if closed_u else cols - 1
        nrow = rows if closed_v else rows - 1
        for i in range(nrow):
            i1 = (i + 1) % rows
            for j in range(ncol):
                j1 = (j + 1) % cols
                uv_a, uv_d = UV[i][j], UV[i1][j]
                uv_b, uv_c = UV[i][j1], UV[i1][j1]
                if j1 == 0:                                   # wrapped column: continue u past the last one
                    du = UV[i][j][0] - UV[i][j - 1][0] if j else 0
                    uv_b = (UV[i][j][0] + du, uv_b[1]); uv_c = (UV[i1][j][0] + du, uv_c[1])
                if i1 == 0:                                   # wrapped row: continue v past the last one
                    dv = UV[i][j][1] - UV[i - 1][j][1] if i else 0
                    uv_d = (uv_d[0], UV[i][j][1] + dv); uv_c = (uv_c[0], UV[i][j1][1] + dv)
                quad = [ids[i][j], ids[i][j1], ids[i1][j1], ids[i1][j]]
                uv = [uv_a, uv_b, uv_c, uv_d]
                if flip:
                    quad.reverse(); uv.reverse()
                keep = [(q, t) for k, (q, t) in enumerate(zip(quad, uv)) if q != quad[k - 1]]
                if len(keep) < 3:
                    continue
                self.add_face([q for q, _ in keep], [t for _, t in keep], mat, smooth)
        return ids


def region_uv(region, u, v):
    u0, v0, u1, v1 = T.REGIONS[region]
    return (u0 + (u1 - u0) * u, v0 + (v1 - v0) * v)


def cell_uv(name, u, v):
    u0, v0, u1, v1 = T.cell_rect(name)
    return (u0 + (u1 - u0) * u, v0 + (v1 - v0) * v)


B = Builder()


# ----------------------------------------------------------------------------
# primitives (all quads, poles collapse to a point)
# ----------------------------------------------------------------------------
def frame_from(axis):
    """Orthonormal (x, y, z) with z = axis."""
    z = Vector(axis).normalized()
    ref = Vector((0, 0, 1)) if abs(z.z) < 0.9 else Vector((1, 0, 0))
    x = ref.cross(z).normalized(); y = z.cross(x)
    return x, y, z


def lathe(profile, segs, uvfun, weight, mat=0, axis_origin=(0, 0, 0), flip=False):
    """profile: list of (r, z). uvfun(i_profile, t_profile, u) -> uv."""
    o = Vector(axis_origin)
    L = [0.0]
    for k in range(1, len(profile)):
        L.append(L[-1] + math.dist(profile[k - 1], profile[k]))
    P, UV = [], []
    for i, (r, z) in enumerate(profile):
        row, rowuv = [], []
        for j in range(segs):
            a = 2 * math.pi * j / segs
            row.append(o + Vector((r * math.sin(a), -r * math.cos(a), z)))
            rowuv.append(uvfun(i, L[i] / L[-1], j / segs))
        P.append(row); UV.append(rowuv)
    return B.grid(P, UV, weight, closed_u=True, mat=mat, flip=flip)


def ellipsoid(center, radii, axis, segs, rings, uvfun, weight, mat=0):
    """Pole on +axis. uvfun(local xyz on unit sphere) -> uv."""
    ax, ay, az = frame_from(axis)
    c = Vector(center)
    P, UV = [], []
    for i in range(rings + 1):
        th = math.pi * i / rings
        row, rowuv = [], []
        for j in range(segs):
            ph = 2 * math.pi * j / segs
            lx, ly, lz = math.sin(th) * math.cos(ph), math.sin(th) * math.sin(ph), math.cos(th)
            row.append(c + ax * (lx * radii[0]) + ay * (ly * radii[1]) + az * (lz * radii[2]))
            rowuv.append(uvfun(lx, ly, lz))
        P.append(row); UV.append(rowuv)
    return B.grid(P, UV, weight, closed_u=True, mat=mat, flip=True)     # (along phi) x (down theta) points in


def capsule(a, b, radius, segs, weight, cell, tip_cell=None, rings_cap=5, rings_body=3, rb=None):
    """Cylinder with round ends from a to b. weight(p) or bone name. rb: radius at b."""
    a, b = Vector(a), Vector(b)
    rb = radius if rb is None else rb
    ax, ay, az = frame_from(b - a)
    L = (b - a).length
    prof = []
    for i in range(rings_cap + 1):                       # bottom hemisphere
        t = -math.pi / 2 + math.pi / 2 * i / rings_cap
        prof.append((radius * math.cos(t), radius * math.sin(t), 'a'))
    for i in range(1, rings_body):
        f = i / rings_body
        prof.append((lerp(radius, rb, f), L * f, 'm'))
    for i in range(rings_cap + 1):                       # top hemisphere
        t = math.pi / 2 * i / rings_cap
        prof.append((rb * math.cos(t), L + rb * math.sin(t), 'b'))
    P, UV = [], []
    n = len(prof)
    for i, (r, z, part) in enumerate(prof):
        row, rowuv = [], []
        name = tip_cell if (tip_cell and part == 'b' and i >= n - rings_cap) else cell
        for j in range(segs):
            ph = 2 * math.pi * j / segs
            row.append(a + ax * (r * math.cos(ph)) + ay * (r * math.sin(ph)) + az * z)
            rowuv.append(cell_uv(name, j / segs, i / (n - 1)))
        P.append(row); UV.append(rowuv)
    return B.grid(P, UV, weight, closed_u=True)


def sphere(c, r, weight, cell, segs=16, rings=10):
    return ellipsoid(c, (r, r, r), (0, 0, 1), segs, rings, lambda x, y, z: cell_uv(cell, 0.5 + 0.5 * x, 0.5 + 0.5 * z), weight)


def torus(center, axis, R, r, weight, uvfun, segs=28, sides=10):
    ax, ay, az = frame_from(axis)
    c = Vector(center)
    P, UV = [], []
    for i in range(sides):
        t = 2 * math.pi * i / sides
        row, rowuv = [], []
        for j in range(segs):
            ph = 2 * math.pi * j / segs
            ring = ax * math.cos(ph) + ay * math.sin(ph)
            row.append(c + ring * (R + r * math.cos(t)) + az * (r * math.sin(t)))
            rowuv.append(uvfun(j / segs, i / sides))
        P.append(row); UV.append(rowuv)
    return B.grid(P, UV, weight, closed_u=True, closed_v=True)


def rounded_box(center, half, radius, frame, weight, cellfun, n=6):
    """Rounded box: a subdivided cube whose points are pushed onto the
    rounded shape (inner box + radius). frame = (x, y, z) axes. cellfun(face, p_local) -> cell name."""
    c = Vector(center); fx, fy, fz = [Vector(v) for v in frame]
    mirrored = fx.cross(fy).dot(fz) < 0                 # a left-handed frame turns every face inside out
    inner = [max(1e-6, h - radius) for h in half]
    faces_def = [((0, 1, 2), 1), ((0, 1, 2), -1), ((1, 2, 0), 1), ((1, 2, 0), -1), ((2, 0, 1), 1), ((2, 0, 1), -1)]
    vid = {}

    def vert(q):
        key = tuple(round(x, 6) for x in q)
        if key in vid:
            return vid[key]
        cl = [max(-inner[k], min(inner[k], q[k] * half[k])) for k in range(3)]
        d = Vector((q[0] * half[0] - cl[0], q[1] * half[1] - cl[1], q[2] * half[2] - cl[2]))
        d = d.normalized() * radius if d.length > 1e-9 else d
        lp = Vector(cl) + d
        p = c + fx * lp.x + fy * lp.y + fz * lp.z
        vid[key] = B.add_vert(p, weight(p) if callable(weight) else weight)
        return vid[key]

    for (a0, a1, a2), s in faces_def:
        for i in range(n):
            for j in range(n):
                quad = []
                for di, dj in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    q = [0.0, 0.0, 0.0]
                    q[a0] = s
                    q[a1] = -1 + 2 * (i + di) / n
                    q[a2] = -1 + 2 * (j + dj) / n
                    quad.append(q)
                if (s < 0) != mirrored:
                    quad.reverse()
                ids = [vert(q) for q in quad]
                mid = [sum(q[k] for q in quad) / 4 for k in range(3)]
                cname = cellfun((a0, s), mid)
                uv = [cell_uv(cname, (q[a1] + 1) / 2, (q[a2] + 1) / 2) for q in quad]
                B.add_face(ids, uv)


def tube(points, radius, sides, weight, uvfun, round_ends=True, radii=None):
    """Swept tube with parallel-transport frames. uvfun(t_along, s_around)."""
    pts = [Vector(p) for p in points]
    n = len(pts)
    tang = []
    for i in range(n):
        d = pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]
        tang.append(d.normalized())
    nx, _, _ = frame_from(tang[0])
    normals = [nx]
    for i in range(1, n):
        prev = normals[-1]
        nn = (prev - tang[i] * prev.dot(tang[i])).normalized()
        normals.append(nn)
    L = [0.0]
    for i in range(1, n):
        L.append(L[-1] + (pts[i] - pts[i - 1]).length)
    rows = []
    rad = radii or [radius] * n
    if round_ends:                                     # taper the last few rings to a closed rounded tip
        k = min(4, n // 4)
        for i in range(k):
            f = math.sqrt(1 - ((k - i) / k) ** 2)            # 0 at the very end: the ring collapses to a pole
            rad[i] = rad[i] * f
            rad[n - 1 - i] = rad[n - 1 - i] * f
    P, UV = [], []
    for i in range(n):
        bn = tang[i].cross(normals[i])
        row, rowuv = [], []
        for j in range(sides):
            ph = 2 * math.pi * j / sides
            row.append(pts[i] + (normals[i] * math.cos(ph) + bn * math.sin(ph)) * rad[i])
            rowuv.append(uvfun(L[i] / L[-1], j / sides))
        P.append(row); UV.append(rowuv)
    return B.grid(P, UV, weight, closed_u=True)


def catmull(points, per_seg=12):
    pts = [Vector(p) for p in points]
    pts = [pts[0]] + pts + [pts[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for k in range(per_seg):
            t = k / per_seg
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(pts[-2])
    return out


def surface_plate(outline, z_center, rings, off_front, depth, weight, cellfun):
    """A flat 2D shape (x along the body arc, z up) laid on the body surface:
    a front cap built from concentric rings (quads) plus a side wall going
    back into the body."""
    cx = sum(p[0] for p in outline) / len(outline)
    cz = sum(p[1] for p in outline) / len(outline)
    n = len(outline)
    P, UV = [], []
    for i in range(rings + 1):                         # ring 0 = outline, last = centre
        f = 1 - i / rings
        row, rowuv = [], []
        for j, (x, z) in enumerate(outline):
            px, pz = cx + (x - cx) * f, cz + (z - cz) * f
            row.append(front_point(px, pz, off_front))
            rowuv.append(cellfun(px, pz))
        P.append(row); UV.append(rowuv)
    B.grid(P, UV, weight, closed_u=True)
    P, UV = [], []                                       # side wall
    for off in (off_front, off_front - depth):
        P.append([front_point(x, z, off) for x, z in outline])
        UV.append([cellfun(x, z) for x, z in outline])
    B.grid(P, UV, weight, closed_u=True, flip=True)


# ----------------------------------------------------------------------------
# the character
# ----------------------------------------------------------------------------
def body_weights(p):
    z = p[2]
    head = smoothstep(0.50, 0.66, z)
    hips = 1 - smoothstep(0.30, 0.43, z)
    spine = max(0.0, 1 - head - hips)
    w = {k: v for k, v in (('Hips', hips), ('Spine', spine), ('Head', head)) if v > 1e-3}
    s = sum(w.values())
    return {k: v / s for k, v in w.items()}


def build_spool():
    # wound thread: one lathe from bottom to top, dense along z for the bulges
    zs = list(np.linspace(BODY_Z0, BODY_Z1, 49))
    prof = [(body_radius(z), z) for z in zs]
    lathe(prof, 64, lambda i, t, u: region_uv('body', u, (prof[i][1] - BODY_Z0) / (BODY_Z1 - BODY_Z0)), body_weights)

    def flange(z_in, z_out, top):
        """z_in: face touching the body, z_out: the outer face. Rounded rim."""
        s = 1 if z_out > z_in else -1
        rr = 0.022
        prof = []
        if top:                                          # the spool's centre hole
            prof += [(0.0, z_out - s * 0.02), (0.036, z_out - s * 0.02), (0.036, z_out - s * 0.004), (0.042, z_out)]
        else:
            prof += [(0.0, z_out)]
        prof += [(r, z_out) for r in np.linspace(0.08 if top else 0.06, FLANGE_R - rr, 6)]
        for k in range(1, 7):                            # outer rounded rim
            a = math.pi / 2 * k / 6
            prof.append((FLANGE_R - rr + rr * math.sin(a), z_out - s * rr * (1 - math.cos(a))))
        for k in range(1, 7):
            a = math.pi / 2 + math.pi / 2 * k / 6
            prof.append((FLANGE_R - rr + rr * math.sin(a), z_in + s * rr * (1 - math.cos(math.pi - a))))
        prof += [(0.27, z_in), (0.236, z_in)]
        if not top:
            prof = prof
        hole = 4 if top else 0
        w = 'Head' if top else 'Hips'

        def uv(i, t, u):
            if i < hole:
                return cell_uv('wood_dark', u, i / max(1, hole))
            return region_uv('flange', u, t)
        return lathe(prof, 64, uv, w, flip=top)

    # outer face first so normals point out: top flange profile runs from the centre outwards on top
    flange(BODY_Z1, BODY_Z1 + 0.07, True)
    flange(BODY_Z0, BODY_Z0 - 0.06, False)


def flip_last_faces(count):
    for k in range(len(B.faces) - count, len(B.faces)):
        B.faces[k] = tuple(reversed(B.faces[k])); B.uvs[k] = tuple(reversed(B.uvs[k]))


def build_face():
    for sx in (-1, 1):
        x = sx * EYE_X
        r = body_radius(EYE_Z)
        a = x / r
        nrm = Vector((math.sin(a), -math.cos(a), 0))
        c = Vector((r * math.sin(a), -r * math.cos(a), EYE_Z)) + nrm * 0.004
        ellipsoid(c, (0.050, 0.060, 0.026), tuple(nrm), 24, 12,
                  lambda lx, ly, lz: region_uv('eye', 0.5 + 0.5 * lx, 0.5 + 0.5 * ly) if True else None, 'Head')
        # eyebrow: an arched tube a little above the visor, tilted friendly
        pts = []
        for k in range(14):
            t = k / 13                                   # 0 = the inner end (towards the nose)
            bx = x + sx * (-0.03 + 0.06 * t)
            if FACE == 'calm':                           # inner ends lifted: concerned, not cross
                bz = 0.726 + 0.007 * math.sin(math.pi * t) + 0.008 * (1 - t)
            else:
                bz = 0.728 + 0.012 * math.sin(math.pi * t) - 0.004 * (1 - t)
            pts.append(front_point(bx, bz, 0.005))
        tube(pts, 0.0058, 8, 'Head', lambda t, s: cell_uv('brow', t, s))

    # the mouth sits low on the face band, where the body follows Spine more than Head: it takes the
    # body's own weights, or a head tilt pushes it into the body (it vanished in Processing)
    if FACE == 'calm':                                   # a small closed smile: an ellipse bent along a curve
        out = []
        for k in range(32):
            a = 2 * math.pi * k / 32
            x = 0.032 * math.cos(a)
            out.append((x, 0.549 - 0.007 * (1 - (x / 0.032) ** 2) + 0.0042 * math.sin(a)))
        surface_plate(out, 0.545, 4, 0.0022, 0.01, body_weights, lambda x, z: cell_uv('mouth', 0.5 + x * 8, 0.5))
        return
    # open friendly smile: wide top, round bottom
    out = []
    for k in range(32):
        a = 2 * math.pi * k / 32
        x = 0.05 * math.cos(a)
        z = 0.556 + (0.004 * (abs(math.cos(a)) ** 2) if math.sin(a) > 0 else 0.048 * math.sin(a))
        out.append((x, z))
    surface_plate(out, 0.535, 6, 0.0022, 0.01, body_weights, lambda x, z: cell_uv('mouth', 0.5 + x * 8, 0.5))
    tongue = []
    for k in range(24):
        a = 2 * math.pi * k / 24
        tongue.append((0.024 * math.cos(a), 0.522 + 0.016 * math.sin(a) * (1.0 if math.sin(a) < 0 else 0.55)))
    surface_plate(tongue, 0.52, 4, 0.0034, 0.004, body_weights, lambda x, z: cell_uv('tongue', 0.5 + x * 10, 0.5))


def build_visor():
    """Curved holographic shell in front of the eyes (material 1), dark pods at its ends and a
    strap round the back."""
    nu, nv = 40, 8
    t_th = 0.005
    for side, R in (('front', VISOR_R + t_th), ('back', VISOR_R)):
        P, UV = [], []
        for i in range(nv + 1):
            v = i / nv
            z = lerp(VISOR_Z0, VISOR_Z1, v)
            row, rowuv = [], []
            for j in range(nu + 1):
                u = j / nu
                th = lerp(-VISOR_SPAN, VISOR_SPAN, u)
                # rounded corners: pull the corner points in
                cu, cv = abs(2 * u - 1), abs(2 * v - 1)
                pinch = max(0.0, (cu - 0.9) / 0.1) * max(0.0, (cv - 0.6) / 0.4)
                zz = lerp(z, (VISOR_Z0 + VISOR_Z1) / 2, 0.35 * pinch)
                row.append(Vector((R * math.sin(th), -R * math.cos(th), zz)))
                rowuv.append((u, v))
            P.append(row); UV.append(rowuv)
        n0 = len(B.faces)
        B.grid(P, UV, 'Head', mat=1, flip=(side == 'back'))
    # visor rims: close the shell along its top and bottom edges (normals up / down)
    for z, radii in ((VISOR_Z0, (VISOR_R, VISOR_R + t_th)), (VISOR_Z1, (VISOR_R + t_th, VISOR_R))):
        P = [[Vector((R * math.sin(lerp(-VISOR_SPAN, VISOR_SPAN, j / nu)), -R * math.cos(lerp(-VISOR_SPAN, VISOR_SPAN, j / nu)), z))
              for j in range(nu + 1)] for R in radii]
        B.grid(P, [[(j / nu, 0.0 if z == VISOR_Z0 else 1.0) for j in range(nu + 1)] for _ in radii], 'Head', mat=1)
    # side pods
    for s in (-1, 1):
        th = s * math.radians(86)
        nrm = Vector((math.sin(th), -math.cos(th), 0))
        base = Vector((0, 0, (VISOR_Z0 + VISOR_Z1) / 2)) + nrm * 0.24
        tip = base + nrm * 0.064
        capsule(base, tip, 0.03, 20, 'Head', 'graphite', rings_cap=4, rings_body=2)
        torus(tip - nrm * 0.004, tuple(nrm), 0.017, 0.0045, 'Head', lambda u, v: cell_uv('glow_teal', u, v), segs=20, sides=8)
    # strap round the back
    P, UV = [], []
    for zi, z in enumerate((0.630, 0.662)):
        row, rowuv = [], []
        for j in range(25):
            th = lerp(math.radians(88), math.radians(272), j / 24)
            r = body_radius(z) + 0.0035
            row.append(Vector((r * math.sin(th), -r * math.cos(th), z)))
            rowuv.append(cell_uv('graphite', j / 24, zi))
        P.append(row); UV.append(rowuv)
    B.grid(P, UV, 'Head')


def build_wrap():
    """Violet multi-strand thread wound diagonally: low across the front, climbing round the back,
    ending under the top flange on the front left."""
    keys = [(-75, 0.322), (-20, 0.36), (40, 0.405), (85, 0.445), (130, 0.50), (180, 0.60), (230, 0.70), (265, 0.775),
            (295, 0.835), (320, 0.875)]
    pts = []
    for k in range(len(keys) - 1):
        for s in range(12):
            t = s / 12
            pts.append((lerp(keys[k][0], keys[k + 1][0], t), lerp(keys[k][1], keys[k + 1][1], t)))
    pts.append(keys[-1])
    width, across = 0.034, 5
    P, UV = [], []
    Lacc = [0.0]
    for i in range(1, len(pts)):
        a0, a1 = math.radians(pts[i - 1][0]), math.radians(pts[i][0])
        Lacc.append(Lacc[-1] + math.hypot((a1 - a0) * 0.25, pts[i][1] - pts[i - 1][1]))
    for i, (deg, z) in enumerate(pts):
        a = math.radians(deg)
        i0, i1 = max(0, i - 1), min(len(pts) - 1, i + 1)
        dz = pts[i1][1] - pts[i0][1]; da = math.radians(pts[i1][0] - pts[i0][0]) * 0.25
        # across-direction on the surface, perpendicular to the path (in (arc, z) space)
        ln = math.hypot(da, dz)
        nx_arc, nz = -dz / ln, da / ln
        taper = min(1.0, Lacc[i] / 0.05, (Lacc[-1] - Lacc[i]) / 0.05)
        row, rowuv = [], []
        for k in range(across + 1):
            f = k / across - 0.5
            zz = z + nz * width * f
            arc = nx_arc * width * f
            r = body_radius(zz) + 0.0016 + 0.0042 * math.cos(math.pi * f) * taper
            aa = a + arc / r
            row.append(Vector((r * math.sin(aa), -r * math.cos(aa), zz)))
            rowuv.append(region_uv('ribbon', (Lacc[i] / Lacc[-1]) * 0.999, k / across))
        P.append(row); UV.append(rowuv)
    B.grid(P, UV, body_weights, flip=True)


def loose_thread():
    """One loose thread: it leaves the winding at the back, loops round the lower body (low in
    front, higher behind, clear of the hands), then falls in an S onto the ground in front of the
    right foot and ends in a small curl."""
    ctrl = [(0.10, 0.232, 0.47)]                          # comes out of the winding at the back
    for deg, r, z in ((150, 0.300, 0.475), (115, 0.312, 0.44), (80, 0.318, 0.405), (45, 0.316, 0.378),
                      (10, 0.312, 0.362), (-25, 0.312, 0.362)):
        a = math.radians(deg)
        ctrl.append((r * math.sin(a), -r * math.cos(a), z))
    ctrl += [(-0.250, -0.255, 0.335), (-0.315, -0.290, 0.250), (-0.330, -0.312, 0.140), (-0.300, -0.330, 0.045),
             (-0.235, -0.360, 0.0068), (-0.165, -0.405, 0.0068), (-0.150, -0.465, 0.0068), (-0.205, -0.490, 0.0068),
             (-0.245, -0.455, 0.0068), (-0.215, -0.425, 0.0068)]
    pts = catmull(ctrl, 10)

    def w(p):
        g = 1 - smoothstep(0.05, 0.24, p[2])              # on the ground it stays put
        return {'Root': g, 'Hips': 1 - g} if g > 1e-3 else {'Hips': 1.0}
    tube(pts, 0.0066, 8, w, lambda t, s: region_uv('thread', t * 0.999, s))


def arm_frames(side):
    """Rest (A-pose) joint positions and the hand's axes for one side (+1 = character's left, +X)."""
    sh = Vector((side * 0.258, 0.0, SHOULDER_Z))
    d = Vector((side * math.sin(ARM_SPREAD), 0.0, -math.cos(ARM_SPREAD)))
    el = sh + d * UPPER_ARM
    wr = el + d * FORE_ARM
    palm_n = Vector((-side * math.cos(ARM_SPREAD), 0.0, -math.sin(ARM_SPREAD)))   # palm faces in and down
    width = Vector((0, -1, 0))                                                     # towards the thumb (front)
    return sh, el, wr, d, palm_n, width


FINGERS = [('Index', -0.0212, 0.047), ('Middle', 0.0, 0.052), ('Ring', 0.0212, 0.044)]


def hand_points(side):
    """Palm centre and every finger's base / knuckle / tip in the rest pose."""
    sh, el, wr, d, n, w = arm_frames(side)
    palm_c = wr + d * 0.042
    out = {}
    for name, off, length in FINGERS:
        base = palm_c + d * 0.020 + w * (-off) * -1 + n * 0.001
        base = palm_c + d * 0.031 + (-w) * off
        out[name] = (base, base + d * length * 0.5, base + d * length)
    tb = palm_c + w * 0.031 - d * 0.004 + n * 0.010
    tdir = (d * 0.55 + w * 0.75 + n * 0.25).normalized()
    out['Thumb'] = (tb, tb + tdir * 0.023, tb + tdir * 0.046)
    return palm_c, out


def build_arm(side):
    S = 'Left' if side > 0 else 'Right'
    sh, el, wr, d, n, w = arm_frames(side)
    sphere(sh, 0.036, f'{S}Shoulder', 'joint', 18, 10)
    capsule(sh + d * 0.014, el - d * 0.012, 0.027, 16, f'{S}UpperArm', 'shell', rb=0.025)
    sphere(el, 0.029, f'{S}LowerArm', 'joint', 16, 10)
    capsule(el + d * 0.012, wr - d * 0.008, 0.025, 16, f'{S}LowerArm', 'shell', rb=0.023)
    torus(wr, tuple(d), 0.026, 0.011, f'{S}LowerArm', lambda u, v: region_uv('ribbon', u * 0.25, v), segs=24, sides=10)
    palm_c, F = hand_points(side)
    frame = (tuple(-w), tuple(n), tuple(d))       # box x across the knuckles, y = palm normal, z = along the hand
    rounded_box(palm_c, (0.037, 0.019, 0.034), 0.017, frame, f'{S}Hand', lambda f, m: 'glove', n=5)
    for name, (base, knuckle, tip) in F.items():
        rad = 0.0150 if name == 'Thumb' else 0.0134

        def fw(p, base=base, knuckle=knuckle, tip=tip, name=name):
            axis = (tip - base).normalized()
            t = (Vector(p) - base).dot(axis) / (tip - base).length
            g = smoothstep(0.38, 0.62, t)
            return {f'{S}{name}Proximal': 1 - g, f'{S}{name}Distal': g} if 0 < g < 1 else (
                {f'{S}{name}Distal': 1.0} if g >= 1 else {f'{S}{name}Proximal': 1.0})
        capsule(base, tip, rad, 12, fw, 'glove', tip_cell='teal', rings_cap=4, rings_body=4)


def tablet_frame():
    """The tablet held against the left palm (rest pose): screen facing the palm's side."""
    sh, el, wr, d, n, w = arm_frames(1)
    palm_c, _ = hand_points(1)
    c = palm_c + n * 0.028 + d * 0.018
    return c, (tuple(w), tuple(d), tuple(n))      # x along the long side, y up the screen, z = screen normal


def build_tablet():
    c, (fx, fy, fz) = tablet_frame()
    fx, fy, fz = Vector(fx), Vector(fy), Vector(fz)
    rounded_box(c, (0.084, 0.058, 0.0065), 0.006, (fx, fy, fz), 'LeftHandProp',
                lambda f, m: 'bezel' if f[0] != 2 else ('graphite' if f[1] < 0 else 'bezel'), n=6)
    # the screen: a slightly raised quad grid on the front face, the logo region of the atlas
    P, UV = [], []
    for i in range(5):
        v = i / 4
        row, rowuv = [], []
        for j in range(7):
            u = j / 6
            row.append(c + fx * lerp(-0.075, 0.075, u) + fy * lerp(-0.049, 0.049, v) + fz * 0.0068)
            rowuv.append(region_uv('screen', lerp(0.98, 0.02, u), lerp(0.03, 0.97, v)))
        P.append(row); UV.append(rowuv)
    B.grid(P, UV, 'LeftHandProp', flip=fx.cross(fy).dot(fz) < 0)


def build_leg(side):
    S = 'Left' if side > 0 else 'Right'
    x = side * HIP_X
    hip, knee, ankle = Vector((x, 0, HIP_Z)), Vector((x, 0, KNEE_Z)), Vector((x, 0, ANKLE_Z))
    sphere(hip, 0.036, f'{S}UpperLeg', 'joint', 16, 10)
    capsule(hip - Vector((0, 0, 0.014)), knee + Vector((0, 0, 0.014)), 0.029, 16, f'{S}UpperLeg', 'shell')
    sphere(knee, 0.033, f'{S}LowerLeg', 'joint', 16, 10)
    torus(knee + Vector((0, -0.027, 0)), (0, -1, 0), 0.018, 0.0052, f'{S}LowerLeg', lambda u, v: cell_uv('glow_teal', u, v), segs=20, sides=8)
    capsule(knee - Vector((0, 0, 0.014)), ankle + Vector((0, 0, 0.012)), 0.027, 16, f'{S}LowerLeg', 'shell', rb=0.025)
    sphere(ankle, 0.029, f'{S}Foot', 'joint', 16, 10)
    torus(ankle + Vector((0, -0.024, 0)), (0, -1, 0), 0.015, 0.0046, f'{S}Foot', lambda u, v: cell_uv('glow_violet', u, v), segs=20, sides=8)
    # chunky sneaker: teal sole, cream upper, violet side stripe, teal heel tab and toe cap line
    shoe_c = Vector((x, -0.024, 0.052))
    frame = ((1, 0, 0), (0, 1, 0), (0, 0, 1))

    def upper_cell(face, m):
        ax, s = face
        if ax == 0 and abs(m[2]) < 0.45 and -0.6 < m[1] < 0.5:         # side stripe
            return 'violet'
        if ax == 1 and s > 0 and m[2] > -0.2:                            # heel tab
            return 'teal'
        return 'sneaker'
    rounded_box(shoe_c, (0.058, 0.098, 0.040), 0.036, frame, f'{S}Foot', upper_cell, n=6)
    rounded_box(Vector((x, -0.026, 0.018)), (0.064, 0.106, 0.018), 0.017, frame, f'{S}Foot', lambda f, m: 'teal_deep', n=6)
    tube([Vector((x - 0.031, -0.086, 0.074)), Vector((x, -0.094, 0.081)), Vector((x + 0.031, -0.086, 0.074))],
         0.0050, 8, f'{S}Foot', lambda t, s: cell_uv('teal', t, s))     # a lace bar


def build_mesh():
    build_spool(); build_face(); build_visor(); build_wrap(); loose_thread()
    for s in (1, -1):
        build_arm(s); build_leg(s)
    build_tablet()


# ----------------------------------------------------------------------------
# Blender objects: mesh, materials, armature, animations
# ----------------------------------------------------------------------------
def make_image(path, non_color=False):
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = 'Non-Color' if non_color else 'sRGB'
    img.pack()
    return img


def make_materials(tex):
    atlas = bpy.data.materials.new('LoomyDada_Atlas'); atlas.use_nodes = True
    nt = atlas.node_tree; bsdf = nt.nodes['Principled BSDF']
    def img_node(name, nc=False):
        n = nt.nodes.new('ShaderNodeTexImage'); n.image = make_image(tex[name], nc); return n
    base = img_node('atlas_basecolor'); nt.links.new(base.outputs['Color'], bsdf.inputs['Base Color'])
    orm = img_node('atlas_orm', True); sep = nt.nodes.new('ShaderNodeSeparateColor')
    nt.links.new(orm.outputs['Color'], sep.inputs['Color'])
    nt.links.new(sep.outputs['Green'], bsdf.inputs['Roughness']); nt.links.new(sep.outputs['Blue'], bsdf.inputs['Metallic'])
    nrm = img_node('atlas_normal', True); nm = nt.nodes.new('ShaderNodeNormalMap')
    nt.links.new(nrm.outputs['Color'], nm.inputs['Color']); nt.links.new(nm.outputs['Normal'], bsdf.inputs['Normal'])
    em = img_node('atlas_emissive'); nt.links.new(em.outputs['Color'], bsdf.inputs['Emission Color'])
    bsdf.inputs['Emission Strength'].default_value = 2.0
    atlas.use_backface_culling = True                  # every opaque part is closed or lies on the body: single-sided

    visor = bpy.data.materials.new('LoomyDada_Visor'); visor.use_nodes = True
    nt = visor.node_tree; vb = nt.nodes['Principled BSDF']
    vcol = nt.nodes.new('ShaderNodeTexImage'); vcol.image = make_image(tex['visor_basecolor'])
    nt.links.new(vcol.outputs['Color'], vb.inputs['Base Color']); nt.links.new(vcol.outputs['Alpha'], vb.inputs['Alpha'])
    vem = nt.nodes.new('ShaderNodeTexImage'); vem.image = make_image(tex['visor_emissive'])
    nt.links.new(vem.outputs['Color'], vb.inputs['Emission Color'])
    vb.inputs['Emission Strength'].default_value = 1.6
    vb.inputs['Roughness'].default_value = 0.08
    try:
        visor.surface_render_method = 'BLENDED'
    except Exception:
        visor.blend_method = 'BLEND'
    visor.use_backface_culling = False
    return atlas, visor


def make_mesh_object(atlas, visor):
    me = bpy.data.meshes.new('LoomyDada')
    me.from_pydata(B.verts, [], B.faces)
    me.validate(clean_customdata=False)
    uv = me.uv_layers.new(name='UVMap')
    flat = [c for face in B.uvs for c in face]
    uv.data.foreach_set('uv', [x for c in flat for x in c])
    me.polygons.foreach_set('material_index', B.mats)
    me.polygons.foreach_set('use_smooth', B.smooth)
    me.materials.append(atlas); me.materials.append(visor)
    ob = bpy.data.objects.new('LOOMY_DADA', me)
    bpy.context.scene.collection.objects.link(ob)
    groups = {}
    for vi, w in enumerate(B.weights):
        for bone, val in w.items():
            groups.setdefault(bone, {}).setdefault(round(val, 4), []).append(vi)
    for bone, by_w in groups.items():
        vg = ob.vertex_groups.new(name=bone)
        for val, ids in by_w.items():
            vg.add(ids, val, 'REPLACE')
    return ob


def bone_specs():
    """name -> (head, tail, parent)."""
    specs = {
        'Root': ((0, 0, 0), (0, 0, 0.08), None),
        'Hips': ((0, 0, 0.25), (0, 0, 0.40), 'Root'),
        'Spine': ((0, 0, 0.40), (0, 0, 0.58), 'Hips'),
        'Head': ((0, 0, 0.58), (0, 0, 0.97), 'Spine'),
    }
    for side in (1, -1):
        S = 'Left' if side > 0 else 'Right'
        sh, el, wr, d, n, w = arm_frames(side)
        palm_c, F = hand_points(side)
        specs[f'{S}Shoulder'] = ((side * 0.12, 0, SHOULDER_Z), tuple(sh), 'Spine')
        specs[f'{S}UpperArm'] = (tuple(sh), tuple(el), f'{S}Shoulder')
        specs[f'{S}LowerArm'] = (tuple(el), tuple(wr), f'{S}UpperArm')
        specs[f'{S}Hand'] = (tuple(wr), tuple(palm_c + d * 0.02), f'{S}LowerArm')
        for name, (base, knuckle, tip) in F.items():
            specs[f'{S}{name}Proximal'] = (tuple(base), tuple(knuckle), f'{S}Hand')
            specs[f'{S}{name}Distal'] = (tuple(knuckle), tuple(tip), f'{S}{name}Proximal')
        x = side * HIP_X
        specs[f'{S}UpperLeg'] = ((x, 0, HIP_Z), (x, 0, KNEE_Z), 'Hips')
        specs[f'{S}LowerLeg'] = ((x, 0, KNEE_Z), (x, 0, ANKLE_Z), f'{S}UpperLeg')
        specs[f'{S}Foot'] = ((x, 0, ANKLE_Z), (x, -0.075, 0.03), f'{S}LowerLeg')
    c, (fx, fy, fz) = tablet_frame()
    specs['LeftHandProp'] = (tuple(c), tuple(Vector(c) + Vector(fy) * 0.04), 'LeftHand')
    return specs


def make_armature(mesh_ob):
    arm = bpy.data.armatures.new('LoomyDada_Rig')
    ob = bpy.data.objects.new('LOOMY_DADA_Rig', arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT')
    specs = bone_specs()
    for name, (h, t, p) in specs.items():
        eb = arm.edit_bones.new(name); eb.head = h; eb.tail = t
        eb.align_roll(Vector((0, -1, 0)) if abs(Vector(t)[1] - Vector(h)[1]) < 0.5 * (Vector(t) - Vector(h)).length else Vector((0, 0, 1)))
    for name, (h, t, p) in specs.items():
        if p:
            arm.edit_bones[name].parent = arm.edit_bones[p]
    bpy.ops.object.mode_set(mode='OBJECT')
    # skinned by the modifier only, not parented: glTF wants a skinned mesh node at the scene root
    mod = mesh_ob.modifiers.new('Armature', 'ARMATURE'); mod.object = ob
    for pb in ob.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    return ob


# ---- posing: each pose gives GLOBAL (armature-space) rotation deltas per bone ----
def q_axis(axis, deg):
    return Quaternion(Vector(axis).normalized(), math.radians(deg))


def q_aim(d0, n0, d1, n1):
    """Rotation taking the frame (d0, n0) onto (d1, n1) (n made perpendicular to d)."""
    def fr(d, n):
        d = Vector(d).normalized(); n = (Vector(n) - d * Vector(n).dot(d)).normalized()
        return Matrix((d, n, d.cross(n))).transposed()
    return (fr(d1, n1) @ fr(d0, n0).transposed()).to_quaternion()


class Pose:
    def __init__(self, rig):
        self.rig = rig
        self.G = {}           # bone -> global rotation delta
        self.loc = {}         # bone -> armature-space offset

    def rest_dir(self, b):
        bone = self.rig.data.bones[b]
        return (bone.tail_local - bone.head_local).normalized()

    def aim(self, b, direction, normal=None, n0=None):
        d0 = self.rest_dir(b)
        if normal is None:
            self.G[b] = d0.rotation_difference(Vector(direction).normalized())
        else:
            self.G[b] = q_aim(d0, n0, direction, normal)

    def apply(self, frame):
        rig = self.rig
        order = [b.name for b in rig.data.bones]            # parents come before children
        G = {}
        for name in order:
            bone = rig.data.bones[name]
            parent_G = G.get(bone.parent.name, Quaternion()) if bone.parent else Quaternion()
            G[name] = self.G.get(name, parent_G)
            rest = bone.matrix_local.to_quaternion()
            local = rest.inverted() @ parent_G.inverted() @ G[name] @ rest
            pb = rig.pose.bones[name]
            pb.rotation_quaternion = local
            pb.keyframe_insert('rotation_quaternion', frame=frame)
            off = self.loc.get(name)
            pb.location = (rest.inverted() @ Vector(off)) if off else Vector((0, 0, 0))
            pb.keyframe_insert('location', frame=frame)


def curl(pose, S, amount, thumb=None, spread_axis=None, only=None):
    """Curl every finger of side S by `amount` degrees per joint about the hand's knuckle axis,
    carried by the hand's own pose rotation."""
    side = 1 if S == 'Left' else -1
    sh, el, wr, d, n, w = arm_frames(side)
    axis = d.cross(n).normalized()                      # rotating d about d x n turns it towards the palm
    Gh = pose.G.get(f'{S}Hand', Quaternion())
    for name, _, _ in FINGERS:
        if only and name not in only:
            a = only.get(name, amount) if isinstance(only, dict) else 0
        else:
            a = amount if not isinstance(only, dict) else only.get(name, amount)
        pose.G[f'{S}{name}Proximal'] = Gh @ q_axis(axis, a)
        pose.G[f'{S}{name}Distal'] = Gh @ q_axis(axis, a * 1.8)
    if thumb is not None:
        taxis = w.cross(n).normalized()                  # folds the thumb in across the palm
        pose.G[f'{S}ThumbProximal'] = Gh @ q_axis(taxis, thumb)
        pose.G[f'{S}ThumbDistal'] = Gh @ q_axis(taxis, thumb * 1.5)


def arm_pose(pose, S, upper_dir, fore_dir, hand_dir, palm):
    side = 1 if S == 'Left' else -1
    sh, el, wr, d, n, w = arm_frames(side)
    pose.aim(f'{S}UpperArm', upper_dir)
    pose.aim(f'{S}LowerArm', fore_dir)
    pose.aim(f'{S}Hand', hand_dir, palm, n0=n)


def V(*a):
    return Vector(a).normalized()


def poses_for(rig):
    """Keyframes for each clip: list of (frame, Pose)."""
    clips = {}

    def base():
        p = Pose(rig); curl(p, 'Left', 38, thumb=10); curl(p, 'Right', 12, thumb=0)
        return p
    clips['Neutral_APose'] = [(1, Pose(rig))]

    idle = []
    for f in range(0, 73, 6):
        t = f / 72 * 2 * math.pi
        p = base()
        p.loc['Hips'] = (0, 0, 0.006 * math.sin(2 * t))
        p.G['Hips'] = q_axis((0, 1, 0), 1.2 * math.sin(t))
        p.G['Spine'] = p.G['Hips'] @ q_axis((1, 0, 0), 1.0 * math.sin(2 * t + 0.6))
        p.G['Head'] = p.G['Spine'] @ q_axis((0, 1, 0), 2.5 * math.sin(t + 0.9)) @ q_axis((1, 0, 0), -1.5)
        for S, sd in (('Left', 1), ('Right', -1)):
            ang = math.radians(36 + 2.5 * math.sin(2 * t + sd))
            dvec = V(sd * math.sin(ang), -0.12, -math.cos(ang))
            arm_pose(p, S, dvec, (dvec + V(0, -0.35, 0.1) * 0.6).normalized(), (dvec + V(0, -0.4, 0.15) * 0.7).normalized(),
                     V(-sd * 0.8, -0.2, -0.5))
        curl(p, 'Left', 38, thumb=10); curl(p, 'Right', 14 + 4 * math.sin(2 * t), thumb=4)
        idle.append((f, p))
    clips['Idle'] = idle

    wave = []
    for f in range(0, 49, 4):
        t = f / 48 * 2 * math.pi
        p = base()
        p.loc['Hips'] = (0, 0, 0.004 * math.sin(2 * t))
        p.G['Head'] = q_axis((0, 1, 0), -5) @ q_axis((1, 0, 0), -2)
        sw = math.sin(2 * t)
        arm_pose(p, 'Right', V(-0.82, -0.12, 0.56), V(-0.25 - 0.32 * sw, -0.18, 0.95), V(-0.2 - 0.4 * sw, -0.12, 0.98),
                 V(0.05, -1.0, 0.0))
        curl(p, 'Right', 4, thumb=-8)
        dl = V(0.62, -0.10, -0.78)
        arm_pose(p, 'Left', dl, V(0.55, -0.35, -0.75), V(0.45, -0.45, -0.7), V(-0.75, -0.25, -0.6))
        curl(p, 'Left', 38, thumb=10)
        wave.append((f, p))
    clips['Wave'] = wave

    thumbs = []
    for f in (0, 8, 14, 20, 45):
        k = {0: 0.0, 8: 0.85, 14: 1.08, 20: 1.0, 45: 1.0}[f]
        p = base()
        p.loc['Hips'] = (0, 0, 0.012 * math.sin(math.pi * min(1, f / 14)) if f <= 14 else 0)
        p.G['Head'] = q_axis((0, 1, 0), -5 * k) @ q_axis((1, 0, 0), -3 * k)
        rest_u = V(-math.sin(ARM_SPREAD), 0, -math.cos(ARM_SPREAD))
        rest_d, rest_n = V(-math.sin(ARM_SPREAD), 0, -math.cos(ARM_SPREAD)), V(math.cos(ARM_SPREAD), 0, -math.sin(ARM_SPREAD))
        up = rest_u.lerp(V(-0.58, -0.32, -0.75), k).normalized()
        fore = rest_u.lerp(V(-0.40, -0.78, 0.48), k).normalized()
        hand = rest_d.lerp(V(-0.22, -0.95, 0.20), k).normalized()
        palm = rest_n.lerp(V(1.0, -0.05, 0.12), k).normalized()
        arm_pose(p, 'Right', up, fore, hand, palm)
        curl(p, 'Right', 12 + 78 * k, thumb=0)
        if k > 0.5:                                      # the thumb points straight up
            p.aim('RightThumbProximal', V(0.08, -0.10, 1.0)); p.aim('RightThumbDistal', V(0.06, -0.08, 1.0))
        lrest = V(math.sin(ARM_SPREAD), 0, -math.cos(ARM_SPREAD))
        lu = lrest.lerp(V(0.62, -0.30, -0.72), k).normalized()
        lf = lrest.lerp(V(0.35, -0.45, 0.82), k).normalized()
        lh = lrest.lerp(V(0.02, -0.10, 1.0), k).normalized()            # fingers up behind the tablet
        arm_pose(p, 'Left', lu, lf, lh, V(-math.cos(ARM_SPREAD), 0, -math.sin(ARM_SPREAD)).lerp(V(-0.42, -0.90, 0.05), k))
        curl(p, 'Left', 38 - 26 * k, thumb=10)            # fingers stay behind the tablet
        thumbs.append((f, p))
    clips['ThumbsUp'] = thumbs

    proc = []
    for f in range(0, 61, 5):
        t = f / 60 * 2 * math.pi
        p = base()
        p.loc['Hips'] = (0, 0, 0.003 * math.sin(2 * t))
        p.G['Spine'] = q_axis((0, 0, 1), 4)
        p.G['Head'] = p.G['Spine'] @ q_axis((0, 0, 1), 9) @ q_axis((1, 0, 0), 9 + 1.5 * math.sin(t))
        # the tablet low in front-left, its screen tilted up towards the face
        arm_pose(p, 'Left', V(0.55, -0.42, -0.72), V(0.05, -0.97, 0.22), V(-0.22, -0.85, 0.48), V(-0.05, 0.50, 0.86))
        curl(p, 'Left', 14, thumb=12)
        cx, cz = 0.10 * math.cos(2 * t), 0.10 * math.sin(2 * t)        # the finger draws small circles
        arm_pose(p, 'Right', V(-0.55, -0.30, -0.78), V(-0.30 + cx, -0.45, 0.84 + cz).normalized(),
                 V(-0.10 + cx, -0.25, 0.96).normalized(), V(0.95, -0.25, 0.1))
        curl(p, 'Right', 80, thumb=40, only={'Index': 4, 'Middle': 85, 'Ring': 90})
        proc.append((f, p))
    clips['Processing'] = proc

    think = []                                           # careful: a finger to the visor pod, head tilted
    for f in range(0, 73, 6):
        t = f / 72 * 2 * math.pi
        p = base()
        p.loc['Hips'] = (0, 0, 0.003 * math.sin(2 * t))
        p.G['Head'] = q_axis((0, 0, 1), -7) @ q_axis((0, 1, 0), -6 + 1.5 * math.sin(t)) @ q_axis((1, 0, 0), -2)
        arm_pose(p, 'Right', V(-0.80, -0.35, -0.50), V(0.0, -0.47, 0.88), V(0.10, 0.30, 0.95), V(1.0, 0.0, -0.10))
        curl(p, 'Right', 80, thumb=40, only={'Index': 6 + 10 * max(0.0, math.sin(2 * t)), 'Middle': 85, 'Ring': 90})
        arm_pose(p, 'Left', V(0.55, -0.42, -0.72), V(0.05, -0.97, 0.22), V(-0.22, -0.85, 0.48), V(-0.05, 0.50, 0.86))
        curl(p, 'Left', 14, thumb=12)
        think.append((f, p))
    clips['Think'] = think

    shrug = []                                           # oops: palms up, head tilted
    for f in (0, 10, 14, 40):
        k = {0: 0.0, 10: 0.9, 14: 1.06, 40: 1.0}[f]
        p = base()
        p.loc['Hips'] = (0, 0, 0.010 * min(1.0, k))
        p.G['Head'] = q_axis((0, 1, 0), 7 * k) @ q_axis((1, 0, 0), -2 * k)
        for S, sd in (('Left', 1), ('Right', -1)):
            rest = V(sd * math.sin(ARM_SPREAD), 0, -math.cos(ARM_SPREAD))
            rest_n = V(-sd * math.cos(ARM_SPREAD), 0, -math.sin(ARM_SPREAD))
            arm_pose(p, S, rest.lerp(V(sd * 0.70, -0.35, -0.62), k).normalized(),
                     rest.lerp(V(sd * 0.42, -0.88, 0.16), k).normalized(),
                     rest.lerp(V(sd * 0.50, -0.82, 0.24), k).normalized(),
                     rest_n.lerp(V(0.0, 0.05, 1.0), k).normalized())
            curl(p, S, 10, thumb=-6)
        shrug.append((f, p))
    clips['Shrug'] = shrug
    return clips


def make_actions(rig):
    rig.animation_data_create()
    scene = bpy.context.scene
    scene.render.fps = 30
    made = []
    for name, keys in poses_for(rig).items():
        act = bpy.data.actions.new(name)
        act.use_fake_user = True
        rig.animation_data.action = act
        for frame, pose in keys:
            pose.apply(frame)
        made.append(act)
        track = rig.animation_data.nla_tracks.new(); track.name = name
        strip = track.strips.new(name, int(keys[0][0]), act)
        rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.rotation_quaternion = Quaternion(); pb.location = Vector()
    return made


def build(out_dir, tex_size=T.N):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    texdir = os.path.join(out_dir, '_textures')
    os.makedirs(texdir, exist_ok=True)
    tex = T.write_all(texdir)
    if tex_size != T.N:                           # a lighter copy (the app's corner widget): same maps, scaled down
        from PIL import Image
        for path in tex.values():
            Image.open(path).resize((tex_size, tex_size), Image.LANCZOS).save(path, optimize=True)
    build_mesh()
    atlas, visor = make_materials(tex)
    mesh_ob = make_mesh_object(atlas, visor)
    rig = make_armature(mesh_ob)
    make_actions(rig)
    return rig, mesh_ob


def export(rig, mesh_ob, path):
    bpy.ops.object.select_all(action='DESELECT')
    rig.select_set(True); mesh_ob.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.export_scene.gltf(
        filepath=path, export_format='GLB', use_selection=True,
        export_image_format='AUTO', export_texcoords=True, export_normals=True, export_tangents=True,
        export_materials='EXPORT', export_skins=True, export_all_influences=False,
        export_animations=True, export_animation_mode='ACTIONS', export_force_sampling=True,
        export_optimize_animation_size=True, export_yup=True, export_apply=False,
        export_cameras=False, export_lights=False)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=HERE)
    ap.add_argument('--blend', action='store_true', help='also save loomy-dada.blend')
    ap.add_argument('--tex-size', type=int, default=T.N, help='texture size (1024 for the app widget)')
    ap.add_argument('--name', default='loomy-dada.glb')
    ap.add_argument('--face', choices=('smile', 'calm'), default='smile', help="'calm' only for the app's stills")
    args, _ = ap.parse_known_args()
    FACE = args.face
    rig, mesh_ob = build(args.out, args.tex_size)
    print('triangles:', sum(len(f) - 2 for f in B.faces), 'vertices:', len(B.verts))
    export(rig, mesh_ob, os.path.join(args.out, args.name))
    if args.blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(args.out, 'loomy-dada.blend'))
