"""Channel names a person can read: channel_01_olive_ground_4A5B24.png.

The colour's name is the nearest of a fixed list (CIELAB distance), its role
is what it does in the design: `ground` (the colour that covers the most),
`outline` (the line art's colour, when the design was filled from one) or
`motif` (everything else). The hex stays in the name, so two olives are
never confused.
"""
from __future__ import annotations

import numpy as np

# name -> RGB. Plain words a mill uses; one word each so file names stay simple.
COLOURS = {
    'white': (255, 255, 255), 'offwhite': (244, 240, 230), 'cream': (242, 232, 207), 'beige': (227, 211, 176),
    'black': (20, 20, 20), 'grey': (128, 128, 128), 'charcoal': (58, 58, 58), 'silver': (192, 194, 196),
    'red': (200, 16, 46), 'maroon': (122, 31, 43), 'rani': (208, 22, 122), 'pink': (240, 141, 176),
    'babypink': (248, 207, 221), 'peach': (246, 185, 147), 'orange': (240, 112, 34), 'rust': (168, 70, 26),
    'yellow': (246, 209, 15), 'lightyellow': (248, 226, 140), 'mustard': (209, 161, 26), 'gold': (201, 164, 58), 'green': (46, 139, 58),
    'bottlegreen': (15, 74, 42), 'parrot': (124, 194, 66), 'olive': (107, 122, 42), 'mint': (167, 223, 193),
    'teal': (23, 126, 131), 'turquoise': (51, 191, 196), 'blue': (31, 95, 191), 'navy': (27, 42, 74),
    'royalblue': (36, 66, 166), 'skyblue': (134, 199, 234), 'purple': (106, 44, 142), 'lavender': (185, 163, 217),
    'brown': (107, 66, 38), 'coffee': (74, 46, 30), 'khaki': (191, 164, 110),
}
_NAMES = list(COLOURS)


def _lab(rgb):
    c = np.asarray(rgb, np.float64) / 255
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = c @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


_LIST_LAB = _lab(np.array([COLOURS[n] for n in _NAMES]))


def delta_e2000(lab1, lab2):
    """CIEDE2000 between Lab colours (last axis L, a, b): how different two colours LOOK, the scale LoomLab's
    Reduce match uses (backend color_engine.delta_e2000, the same formula)."""
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1, C2 = np.hypot(a1, b1), np.hypot(a2, b2)
    Cb7 = ((C1 + C2) / 2) ** 7
    G = 0.5 * (1 - np.sqrt(Cb7 / (Cb7 + 25.0 ** 7)))
    a1p, a2p = (1 + G) * a1, (1 + G) * a2
    C1p, C2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p, h2p = np.degrees(np.arctan2(b1, a1p)) % 360, np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, C2p - C1p
    dhp = h2p - h1p
    dhp = np.where(dhp > 180, dhp - 360, dhp)
    dhp = np.where(dhp < -180, dhp + 360, dhp)
    dhp = np.where(C1p * C2p == 0, 0.0, dhp)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp / 2))
    Lbp, Cbp = (L1 + L2) / 2, (C1p + C2p) / 2
    hsum, hdiff = h1p + h2p, np.abs(h1p - h2p)
    hbp = np.where(C1p * C2p == 0, hsum, np.where(hdiff <= 180, hsum / 2, np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2)))
    T = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dTheta = 30 * np.exp(-((hbp - 275) / 25) ** 2)
    Cbp7 = Cbp ** 7
    Rc = 2 * np.sqrt(Cbp7 / (Cbp7 + 25.0 ** 7))
    Sl = 1 + (0.015 * (Lbp - 50) ** 2) / np.sqrt(20 + (Lbp - 50) ** 2)
    Sc, Sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * T
    Rt = -np.sin(np.radians(2 * dTheta)) * Rc
    return np.sqrt((dLp / Sl) ** 2 + (dCp / Sc) ** 2 + (dHp / Sh) ** 2 + Rt * (dCp / Sc) * (dHp / Sh))


def colour_name(rgb) -> str:
    """The nearest name in the list, e.g. 'olive'."""
    d = ((_LIST_LAB - _lab(np.asarray(rgb)[None])) ** 2).sum(1)
    return _NAMES[int(d.argmin())]


def roles(counts, line_index=None):
    """index -> 'ground' | 'outline' | 'motif'. The colour covering the most is
    the ground (even if it is also the line colour)."""
    ground = int(np.argmax(counts))
    out = {}
    for k in range(len(counts)):
        out[k] = 'ground' if k == ground else 'outline' if k == line_index else 'motif'
    return out
