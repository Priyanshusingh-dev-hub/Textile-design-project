"""A local review of a reduced design against the upload.

The plan names what a person should look at. It never edits pixels, never calls
a model, and never needs an API key. A future vision provider can return the
same shape; this one is the offline stand-in.
"""
import numpy as np
from PIL import Image
from scipy import ndimage

from ..color_engine import engine as colors

SCHEMA_VERSION = 1
# A rim this thin (area / edge pixels) is a boundary, not a filled motif.
_RIM_THICKNESS = 3.0
# Sitting on the colour path between two larger inks, within this ΔE slack.
_BLEND_SLACK = 4.0


def plan(source: Image.Image, reduced: Image.Image) -> dict:
    """Structured recommendations. `source` and `reduced` are left as they were."""
    issues = []
    if source.size != reduced.size:
        issues.append(_issue(
            'size_mismatch', 'block',
            'The reduced design is a different size from the upload, so plates would not register.',
            'Re-reduce from the original upload. Do not resize one of them to match.',
        ))
        return _envelope(issues)

    src = np.asarray(source.convert('RGBA'))
    red = np.asarray(reduced.convert('RGBA'))
    src_opq = src[:, :, 3] >= colors.ALPHA_CUTOFF
    red_opq = red[:, :, 3] >= colors.ALPHA_CUTOFF
    alpha_changed = int((src_opq != red_opq).sum())
    if alpha_changed:
        issues.append(_issue(
            'alpha_changed', 'review',
            f'{alpha_changed} pixels changed between transparent and opaque.',
            'Check holes and the cloth edge before separating. Nothing here was filled in or punched out.',
            count=alpha_changed,
        ))

    labels, palette = _labels(red, red_opq)
    hexes = [_hex(c) for c in palette]
    specks = colors._isolated_dots(labels)
    if specks:
        issues.append(_issue(
            'review_specks', 'review',
            f'{specks} tiny exact marks survived reduction. They may be texture or dirt.',
            'Look at them before separating. They were kept on purpose and were not deleted.',
            count=specks, samples=_speck_samples(labels),
        ))

    if len(hexes) >= 3:
        pairs = colors.similar_inks(source, hexes)
        if pairs:
            issues.append(_issue(
                'similar_inks', 'review',
                'Some inks are close enough to look like one colour on cloth.',
                'Merge only the pair you mean to merge. Closeness alone is not a reason to merge.',
                pairs=[{'keep': hexes[p['keep']], 'drop': hexes[p['drop']],
                        'delta_e': p['delta_e'], 'accuracy': p['accuracy']} for p in pairs],
            ))

    soft = float(colors.soft_edge_width(source))
    if soft >= 1:
        issues.append(_issue(
            'soft_edge', 'review',
            f'The upload fades out over about {soft:.1f} px. A flat ink will print that edge hard.',
            'Expect a hard edge. This is not repaired by adding another ink.',
            width_px=round(soft, 2),
        ))

    issues.extend(_blend_rims(labels, palette))
    issues.extend(_missing_thin(src[:, :, :3], src_opq, palette))
    return _envelope(issues)


def _envelope(issues: list) -> dict:
    return {
        'schema_version': SCHEMA_VERSION,
        'provider': 'local',
        'model': None,
        'applies_pixels': False,
        'needs_human': any(i['severity'] in ('review', 'block') for i in issues),
        'issues': issues,
    }


def _issue(code, severity, message, recommendation, **extra):
    item = {
        'code': code,
        'severity': severity,
        'confidence': 1.0,
        'message': message,
        'recommendation': recommendation,
        'action': 'none',
    }
    item.update(extra)
    return item


def _hex(rgb) -> str:
    return '#{:02X}{:02X}{:02X}'.format(int(rgb[0]), int(rgb[1]), int(rgb[2]))


def _labels(rgb_image, opaque):
    flat = rgb_image[:, :, :3].reshape(-1, 3)
    opq = opaque.reshape(-1)
    labels = np.full(opaque.shape, -1, np.int32)
    if not opq.any():
        return labels, np.zeros((0, 3), np.uint8)
    colours, inverse = np.unique(flat[opq], axis=0, return_inverse=True)
    labels.reshape(-1)[opq] = inverse.astype(np.int32)
    return labels, colours.astype(np.uint8)


def _speck_samples(labels, limit=3):
    lab = np.asarray(labels)
    h, w = lab.shape
    same = np.zeros((h, w), np.uint8)
    for ys, xs, y2, x2 in (
        (slice(1, None), slice(None), slice(None, -1), slice(None)),
        (slice(None, -1), slice(None), slice(1, None), slice(None)),
        (slice(None), slice(1, None), slice(None), slice(None, -1)),
        (slice(None), slice(None, -1), slice(None), slice(1, None)),
        (slice(1, None), slice(1, None), slice(None, -1), slice(None, -1)),
        (slice(1, None), slice(None, -1), slice(None, -1), slice(1, None)),
        (slice(None, -1), slice(1, None), slice(1, None), slice(None, -1)),
        (slice(None, -1), slice(None, -1), slice(1, None), slice(1, None)),
    ):
        same[ys, xs] += (lab[y2, x2] == lab[ys, xs]) & (lab[ys, xs] >= 0)
    ys, xs = np.where((lab >= 0) & (same == 0))
    return [{'x': int(x), 'y': int(y)} for y, x in list(zip(ys, xs))[:limit]]


def _thickness(mask) -> float:
    area = int(mask.sum())
    if area == 0:
        return 0.0
    inside = ndimage.binary_erosion(mask, border_value=0)
    edge = area - int(inside.sum())
    return area / max(edge, 1)


def _de(a, b) -> float:
    return float(np.asarray(colors.delta_e2000(
        np.asarray(a, np.float64).reshape(1, 3),
        np.asarray(b, np.float64).reshape(1, 3),
    )).reshape(-1)[0])


def _blend_rims(labels, palette):
    """A thin ink that sits between two larger ones may be an anti-aliased rim
    or a real thin colour. Flag it. Do not merge it."""
    if len(palette) < 3:
        return []
    counts = np.bincount(labels[labels >= 0], minlength=len(palette))
    labs = colors.rgb_lab(palette.astype(np.uint8))
    found = []
    for i in range(len(palette)):
        if counts[i] == 0:
            continue
        mask = labels == i
        if _thickness(mask) >= _RIM_THICKNESS:
            continue
        for a in range(len(palette)):
            if a == i or counts[a] < counts[i] * 2:
                continue
            for b in range(a + 1, len(palette)):
                if b == i or counts[b] < counts[i] * 2:
                    continue
                dab = _de(labs[a], labs[b])
                if dab < 8:
                    continue
                if _de(labs[a], labs[i]) + _de(labs[i], labs[b]) <= dab + _BLEND_SLACK:
                    found.append(_issue(
                        'blend_rim', 'review',
                        f'{_hex(palette[i])} is a thin band between {_hex(palette[a])} and {_hex(palette[b])}. '
                        'It may be an anti-aliased rim, or a real thin colour.',
                        'Do not delete it automatically. Merge it only if you can see that it is a fringe.',
                        hex=_hex(palette[i]),
                        between=[_hex(palette[a]), _hex(palette[b])],
                        pixels=int(counts[i]),
                    ))
                    break
            else:
                continue
            break
    return found[:3]


def _missing_thin(rgb, opaque, palette):
    """Connected thin source colours that none of the reduced inks is near."""
    if len(palette) == 0 or not opaque.any():
        return []
    pixels = rgb.reshape(-1, 3)
    _, feature = colors._edges_and_features(rgb, colors.rgb_lab(pixels))
    feature = np.asarray(feature, bool) & opaque.reshape(-1)
    extras = colors._missing_feature_rgb(pixels, feature, colors.rgb_lab(palette.astype(np.uint8)))
    issues = []
    h, w = opaque.shape
    feat = feature.reshape(h, w)
    for rgb_i in extras:
        hit = feat & np.all(rgb == rgb_i, axis=2)
        ys, xs = np.where(hit)
        if len(xs) == 0:
            continue
        issues.append(_issue(
            'thin_colour_missing', 'review',
            f'A connected thin colour {_hex(rgb_i)} is not close to any reduced ink.',
            'Re-reduce with enough inks for that colour, or leave it if it is a shade of a neighbour. It was not repainted by this review.',
            hex=_hex(rgb_i),
            pixels=int(hit.sum()),
            region={'x': int(xs.min()), 'y': int(ys.min()),
                    'w': int(xs.max() - xs.min() + 1), 'h': int(ys.max() - ys.min() + 1)},
        ))
    return issues
