"""The second way to a flat design: line art + a coloured reference.

Every closed area of the line art takes the reference's majority colour there
(the user's approved Method 1). The code is textile_project's `textile`
package, the same module its `textile fill` command runs (tested there to
write what reference_code/method1_colorfill.py wrote), not a copy of it.

The result is a reduced design like any other: the Reduce step's palette
tools, Separate and Export take it from here.
"""
import io
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from ..color_engine import engine as colors
from ..core import store
from .common import image_meta

TEXTILE = Path(__file__).resolve().parents[3] / 'textile_project'
if str(TEXTILE) not in sys.path:
    sys.path.insert(0, str(TEXTILE))
from textile import fill_auto  # noqa: E402
from textile import fill_method1 as method1  # noqa: E402
from textile import fill_method2 as method2  # noqa: E402
from textile import fill_method3 as method3  # noqa: E402
from textile import palette as tpal  # noqa: E402

router = APIRouter()
MAX_BYTES = 80 * 1024 * 1024
FILL_SIZE = 3535            # 11.78 in at 300 DPI: the mill's working format
# the textile tool talks Hinglish to its user; the app answers in its own
# English keys (translated by the frontend like every engine error)
MISFIT = {
    'aspect': 'The two images are not the same shape (width to height). Use the same crop for both.',
    'ek rang': 'The reference has only one colour: Method 2 needs a ground colour and a motif colour.',
    'aligned': 'The line art and the reference do not line up (crop, shift, rotation or a different design). '
               'Tick "Fill even if the two images do not line up well" to fill anyway.',
}


def _read(upload: UploadFile, what: str):
    raw = upload.file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, 'Image is larger than the 80 MB import limit.')
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(422, f'The {what} is not a valid image.')
    return raw, img


@router.post('/api/fill')
def line_fill(line: UploadFile = File(...), ref: UploadFile = File(...), max_colors: int = Form(16),
              line_color: str = Form('auto'), size: int = Form(FILL_SIZE), force: bool = Form(False),
              method: str = Form('1')):
    """Fill the line art's areas with the reference's colours. Answers the
    reference as the design's original and the filled design as its reduced
    image (with palette and match), plus what the fill measured.

    method: 1 (aligned), 3 (the same drawing, drifted), 2 (a different
    drawing: two colours from the line art's structure) or auto (1, judged,
    then 3, then 2: the textile tool's own choice)."""
    if method not in ('1', '2', '3', 'auto'):
        raise HTTPException(422, 'Method: choose auto, 1, 2 or 3.')
    if not 2 <= max_colors <= 20:
        raise HTTPException(422, 'Colours: choose between 2 and 20.')
    if not 256 <= size <= 12000:
        raise HTTPException(422, 'Size: choose between 256 and 12000 px.')
    if line_color != 'auto' and not re.fullmatch(r'#?[0-9A-Fa-f]{6}', line_color):
        raise HTTPException(422, 'Outline colour: "auto" or a code like #1A1A1A.')
    line_raw, _ = _read(line, 'line art')
    ref_raw, ref_img = _read(ref, 'reference')

    log = []
    with tempfile.TemporaryDirectory() as d:
        lp, rp = os.path.join(d, 'line.png'), os.path.join(d, 'ref.png')
        with open(lp, 'wb') as f:
            f.write(line_raw)
        with open(rp, 'wb') as f:
            f.write(ref_raw)
        lc = line_color.lstrip('#')
        auto = None
        try:
            if method == 'auto':
                c = fill_auto.choose(lp, rp, size, max_colors, line_color=lc, log=log.append)
                done, chosen, auto = c.fill, c.method, c.auto
            elif method == '3':
                done, chosen = method3.fill(lp, rp, size, max_colors, line_color=lc, log=log.append), 3
            elif method == '2':
                done, chosen = method2.fill(lp, rp, size, log=log.append), 2
            else:
                done = method1.fill(lp, rp, size=size, max_colors=max_colors, line_color=lc, force=force,
                                    log=log.append)
                chosen = 1
        except method1.FillError as e:
            why = next((v for k, v in MISFIT.items() if k in str(e)), 'Could not fill this pair.')
            raise HTTPException(422, why)

    if chosen == 2:                                   # two colours, no outline of its own
        index, pal, merged, line_hex = done.index, done.pal, [], None
    else:
        index, pal, merged, li = fill_auto.merged(done)
        line_hex = '#' + tpal._hex(pal[li])
    filled = Image.fromarray(pal[index])
    reduced_id = store.save(filled)

    source = colors.to_8bit(ref_img)
    source_id = store.save(source)
    counts = np.bincount(index.ravel(), minlength=len(pal))
    order = [k for k in np.argsort(-counts, kind='stable') if counts[k]]
    palette = [{'hex': '#' + tpal._hex(pal[k]), 'rgb': [int(v) for v in pal[k]], 'pixels': int(counts[k]),
                'coverage': round(float(counts[k] / index.size * 100), 2)} for k in order]
    # the filled design against the reference, pixel by pixel (the palette alone
    # would score a flat reference 100% whatever shapes the line art gave)
    de, acc = colors.pixel_match(source, filled)
    debug_url = None
    if getattr(done, 'debug', None) is not None:
        debug_url = f'/api/image/{store.save(Image.fromarray(done.debug))}'
    return {
        'original': image_meta(source_id, source) | {'file_name': ref.filename, 'file_size': len(ref_raw)},
        'reduced': image_meta(reduced_id, filled) | {
            'palette': palette, 'accuracy': acc, 'delta_e': de, 'source_id': source_id, 'smoothing': 0,
            'dots': False, 'similar': [], 'repeat': {'x': False, 'y': False}},
        'fill': {'method': chosen, 'auto': auto,
                 'alignment': round(done.alignment_score, 3) if chosen != 2 else None, 'regions': done.regions,
                 'doubtful': len(getattr(done, 'doubtful', [])), 'debug_url': debug_url, 'line_color': line_hex,
                 'reference_was_flat': getattr(done, 'reference_was_flat', False), 'stray_merged': merged,
                 'size_px': list(filled.size), 'line_file': line.filename},
    }
