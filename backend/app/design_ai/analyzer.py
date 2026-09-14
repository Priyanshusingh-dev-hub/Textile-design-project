"""Deterministic visual analysis -> Design DNA.

There is NO AI/vision model here. Everything is measured with numpy/Pillow
statistics, or parsed from the user's own description. Fields the maths can
genuinely measure (colours, density, contrast, symmetry, detail) are marked
source='auto'; semantic fields a vision model would be needed for (motif
family, style era) are only filled from the user's description keywords and
are marked source='user', or left 'unspecified' — the code never pretends to
recognise a paisley or a rose from pixels.
"""
import numpy as np
from PIL import Image
from ..color_engine.engine import array, rgb_lab, _hex, analyze as analyze_palette

# --- description keyword vocabularies (user-provided semantics only) ---
_MOTIF_WORDS = {
    'floral': ['floral', 'flower', 'rose', 'lotus', 'blossom', 'phool'],
    'paisley': ['paisley', 'buta', 'buti', 'mango', 'kairi', 'ambi'],
    'creeper': ['creeper', 'bel', 'vine', 'jaal', 'jaali', 'trailing'],
    'geometric': ['geometric', 'geometry', 'check', 'stripe', 'chevron', 'diamond', 'triangle'],
    'botanical': ['botanical', 'leaf', 'leaves', 'foliage', 'branch', 'plant'],
    'abstract': ['abstract', 'freeform', 'organic shapes'],
    'ornamental': ['ornamental', 'ornate', 'damask', 'motif', 'border', 'ethnic'],
    'traditional': ['traditional', 'ethnic', 'heritage'],
}
_STYLE_WORDS = {
    'Mughal-inspired': ['mughal', 'mugal'],
    'Persian': ['persian', 'irani'],
    'Indian traditional': ['indian', 'rajasthani', 'jaipuri', 'banarasi', 'traditional'],
    'botanical': ['botanical', 'naturalistic'],
    'contemporary': ['contemporary', 'modern', 'minimal', 'minimalist'],
    'abstract': ['abstract'],
}

def _keywords(description, table):
    text = (description or '').lower()
    return [label for label, words in table.items() if any(w in text for w in words)]

def _small(image, target=420):
    """Downscale for fast, stable statistics (huge mill files included)."""
    rgb = image.convert('RGB')
    w, h = rgb.size
    scale = min(1.0, target / max(w, h))
    if scale < 1.0:
        rgb = rgb.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    return rgb

def _band(value, thresholds, labels):
    for t, label in zip(thresholds, labels):
        if value < t:
            return label
    return labels[-1]

def _background_hex(a):
    """Estimate the ground colour from the image border (textile grounds
    dominate the edges), returned as a hex string."""
    edge = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]).reshape(-1, 3)
    # mode-ish: nearest to the edge mean is a robust, cheap estimate
    mean = edge.mean(0)
    return _hex(mean.round().astype(int))

def build_dna(image, description=''):
    a = np.asarray(_small(image))
    h, w, _ = a.shape
    total = h * w
    pixels = a.reshape(-1, 3)

    # --- colours (auto) ---
    palette = analyze_palette(Image.fromarray(a), 8)
    distinct = [c for c in palette if c.coverage >= 1.0]
    bg_hex = _background_hex(a)
    bg_lab = rgb_lab(np.array([int(bg_hex[i:i+2], 16) for i in (1, 3, 5)], dtype=np.uint8))
    # coverage of pixels close to the background colour
    lab = rgb_lab(pixels)
    bg_frac = float((np.sqrt(((lab - bg_lab) ** 2).sum(-1)) < 14).mean())
    ink_density = 1.0 - bg_frac

    # near-identical colour candidates (LAB distance < 12 between distinct colours)
    merge_pairs = []
    dl = [rgb_lab(np.array(c.rgb, dtype=np.uint8)) for c in distinct]
    for i in range(len(distinct)):
        for j in range(i + 1, len(distinct)):
            if np.sqrt(((dl[i] - dl[j]) ** 2).sum()) < 12:
                merge_pairs.append([distinct[i].hex, distinct[j].hex])

    # --- contrast (auto): lightness spread across the palette ---
    ls = [rgb_lab(np.array(c.rgb, dtype=np.uint8))[0] for c in distinct] or [0]
    contrast_range = max(ls) - min(ls)
    contrast = _band(contrast_range, [35, 70], ['low', 'medium', 'high'])

    # --- symmetry (auto): compare to mirrors on a small grayscale copy ---
    g = np.asarray(Image.fromarray(a).convert('L').resize((128, 128))).astype(float)
    lr = np.abs(g - np.fliplr(g)).mean() / 255
    tb = np.abs(g - np.flipud(g)).mean() / 255
    sym_score = min(lr, tb)
    symmetry = _band(sym_score, [0.06, 0.13], ['symmetrical', 'semi-symmetrical', 'organic'])

    # --- detail (auto): edge density via gradient magnitude ---
    gy, gx = np.gradient(g)
    edge_density = float((np.hypot(gx, gy) > 24).mean())
    detail = _band(edge_density, [0.06, 0.16], ['minimal', 'moderate', 'detailed'])

    density_label = _band(ink_density, [0.28, 0.52, 0.72], ['sparse', 'medium', 'medium-high', 'dense'])
    negative_space = _band(bg_frac, [0.32, 0.58], ['low', 'medium', 'high'])

    # --- semantics (user description only; never invented from pixels) ---
    motif_families = _keywords(description, _MOTIF_WORDS)
    style_words = _keywords(description, _STYLE_WORDS)
    ow, oh = image.size

    dna = {
        'style': {
            'category': (motif_families[0] + ' pattern') if motif_families else 'unspecified',
            'sub_style': style_words[0] if style_words else 'unspecified',
            'source': 'user' if (motif_families or style_words) else 'unspecified',
        },
        'motif_family': motif_families or ['unspecified'],
        'motif_family_source': 'user' if motif_families else 'unspecified',
        'composition': {
            'density': density_label,
            'symmetry': symmetry,
            'negative_space': negative_space,
            'contrast': contrast,
            'detail': detail,
            'source': 'auto',
        },
        'scale': {
            'dimensions': f'{ow} x {oh}px',
            'aspect_ratio': round(ow / oh, 3),
            'source': 'auto',
        },
        'colors': [{'role': _role(i, c, bg_hex), 'hex': c.hex, 'coverage': c.coverage} for i, c in enumerate(distinct)],
        'background': {'hex': bg_hex, 'coverage': round(bg_frac * 100, 1), 'source': 'auto'},
        'distinct_colors': len(distinct),
        'mergeable_colors': merge_pairs,
        'visual_character': _character(density_label, detail, contrast),
        'production_notes': _production_notes(len(distinct), merge_pairs, ink_density),
        'detected': ['colour palette', 'background colour', 'distinct colour count', 'near-identical colours',
                     'ink density', 'negative space', 'contrast', 'symmetry', 'detail level', 'dimensions'],
        'from_description': _describe_sources(motif_families, style_words),
    }
    return dna

def _role(i, c, bg_hex):
    if c.hex.upper() == bg_hex.upper():
        return 'background'
    if i == 0:
        return 'dominant'
    if c.coverage >= 8:
        return 'primary'
    if c.coverage >= 2:
        return 'secondary'
    return 'accent'

def _character(density, detail, contrast):
    words = []
    words.append('dense and decorative' if density in ('dense', 'medium-high') else 'open and airy' if density == 'sparse' else 'balanced')
    words.append('finely detailed' if detail == 'detailed' else 'bold and simple' if detail == 'minimal' else 'moderately detailed')
    words.append('high-contrast' if contrast == 'high' else 'soft, low-contrast' if contrast == 'low' else 'medium-contrast')
    return ', '.join(words)

def _production_notes(n_distinct, merge_pairs, ink_density):
    notes = [f'Approximately {n_distinct} visually distinct colours detected.']
    if merge_pairs:
        notes.append(f'{len(merge_pairs)} near-identical colour pair(s) could be merged to reduce screen count.')
    if ink_density > 0.72:
        notes.append('High ink coverage — watch for registration and drying on press.')
    return notes

def _describe_sources(motif_families, style_words):
    provided = []
    if motif_families:
        provided.append('motif family')
    if style_words:
        provided.append('style era')
    return provided
