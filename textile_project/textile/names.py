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
