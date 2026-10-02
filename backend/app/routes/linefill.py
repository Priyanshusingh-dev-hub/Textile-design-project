"""The second way to a flat design: line art + a coloured reference.

Every closed area of the line art takes the reference's majority colour there
(the user's approved Method 1, and its variants). The code is textile_project's
`textile` package, not a copy of it.

`method=auto` does not trust the fill: `core.filltrial` tries Reduce of the
reference and each fill at the reference's own size, scores them against the
reference, and picks (see its docstring). Every trial is shown to the operator,
who can pick another with one click, and every run is one line in
`fill-trials.jsonl`. The result is a reduced design like any other: the
palette tools, Separate and Export take it from here.
"""
import io
from datetime import datetime
import os
import re
import tempfile

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from ..color_engine import engine as colors
from ..core import filltrial, store
from ..models import ReduceRequest
from .common import image_meta
from .palette import reduce as reduce_route

from textile import fill_auto, fill_method1 as method1, fill_method2 as method2   # noqa: E402  (path set by filltrial)
from textile import fill_method3 as method3, fill_method4 as method4, palette as tpal  # noqa: E402

router = APIRouter()
MAX_BYTES = 80 * 1024 * 1024
FILL_SIZE = 3535            # 11.78 in at 300 DPI: the mill's working format
METHODS = ('auto', '0', '1', '2', '3', '4')     # 0 = the reference alone, through Reduce
CODE = {'reduce': '0', 'method1': '1', 'method2': '2', 'method3': '3', 'method4': '4'}
# the textile tool talks Hinglish to its user; the app answers in its own
# English keys (translated by the frontend like every engine error)
MISFIT = {
    'aspect': 'The two images are not the same shape (width to height). Use the same crop for both.',
    'aligned': 'The line art and the reference do not line up (crop, shift, rotation or a different design). '
               'Tick "Fill even if the two images do not line up well" to fill anyway.',
    'ek rang': 'The reference has only one colour: Method 2 needs a ground colour and a motif colour.',
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
              method: str = Form('auto'), overrides: str = Form('')):
    """Make the flat design from a line art + reference pair. Answers the
    reference as the design's original and the result as its reduced image
    (with palette and match), plus what was tried and why this one.

    method: auto (the judge), 0 (the reference alone, through Reduce), 1
    (aligned), 4 (aligned, line-art gaps sealed), 3 (the same drawing,
    drifted), 2 (a different drawing: two colours from the line art's
    structure). `overrides`: the method auto had chosen, when the operator
    picks another (kept in the log)."""
    if method not in METHODS:
        raise HTTPException(422, 'Method: choose auto, Reference only, or 1, 2, 3, 4.')
    if not 2 <= max_colors <= 20:
        raise HTTPException(422, 'Colours: choose between 2 and 20.')
    if not 256 <= size <= 12000:
        raise HTTPException(422, 'Size: choose between 256 and 12000 px.')
    if line_color != 'auto' and not re.fullmatch(r'#?[0-9A-Fa-f]{6}', line_color):
        raise HTTPException(422, 'Outline colour: "auto" or a code like #1A1A1A.')
    line_raw, line_img = _read(line, 'line art')
    ref_raw, ref_img = _read(ref, 'reference')
    if method != '0' and abs(line_img.size[0] / line_img.size[1] - ref_img.size[0] / ref_img.size[1]) > 0.01:
        # a wrong crop is the operator's to fix, never to hide behind a fallback
        raise HTTPException(422, MISFIT['aspect'])
    source = colors.to_8bit(ref_img)
    source_id = store.save(source)
    lc = line_color.lstrip('#')

    log, decision, red = [], None, None
    with tempfile.TemporaryDirectory() as d:
        lp, rp, fp = (os.path.join(d, n) for n in ('line.png', 'ref.png', 'flat_ref.png'))
        for path, raw in ((lp, line_raw), (rp, ref_raw)):
            with open(path, 'wb') as f:
                f.write(raw)
        try:
            if method == 'auto':
                decision = filltrial.run(lp, rp, source, lc, log=log.append)
                chosen, inks = CODE[decision.chosen], decision.inks
            else:
                chosen = method
                inks = int(colors.suggest_colors(source)['suggested'])
            inks = max(2, min(inks, max_colors))
            # the reference through Reduce: the answer itself for '0', and the
            # fills' colour source otherwise (the few inks Reduce found, not the shading's dozens)
            red = reduce_route(ReduceRequest(image_id=source_id, colors=inks))
            done = None
            if chosen != '0':
                store.load(red['image_id']).convert('RGB').save(fp)
                if chosen == '1':
                    done = method1.fill(lp, fp, size=size, max_colors=inks, line_color=lc,
                                        force=force or method == 'auto', log=log.append)
                elif chosen == '4':
                    done = method4.fill(lp, fp, size, inks, line_color=lc, force=force or method == 'auto',
                                        log=log.append)
                elif chosen == '3':
                    done = method3.fill(lp, fp, size, inks, line_color=lc, log=log.append)
                else:
                    done = method2.fill(lp, rp, size, log=log.append)
        except method1.FillError as e:
            why = next((v for k, v in MISFIT.items() if k in str(e)), 'Could not fill this pair.')
            raise HTTPException(422, why)

    trials = None if decision is None else {
        'rows': decision.trials, 'chosen': decision.chosen, 'reason': decision.reason,
        'margin': decision.margin, 'tolerance': decision.tolerance, 'inks': decision.inks,
        'trial_px': decision.trial_px, 'seconds': decision.seconds}
    original = image_meta(source_id, source) | {'file_name': ref.filename, 'file_size': len(ref_raw)}
    if decision:
        filltrial.record(filltrial.entry(decision, source, size=size, made=chosen, line_file=line.filename))
    else:
        filltrial.record({'time': datetime.now().isoformat(timespec='seconds'),
                          'design': filltrial.design_hash(source), 'event': 'operator',
                          'made': chosen, 'overrides': overrides or None, 'size': size})

    if chosen == '0':
        # the line art is set aside: this is the Reduce step's own answer
        return {'original': original, 'reduced': red,
                'fill': {'method': 0, 'trials': trials, 'alignment': None, 'regions': 0, 'doubtful': 0,
                         'debug_url': None, 'line_color': None, 'reference_was_flat': False,
                         'stray_merged': [], 'size_px': [red['width'], red['height']], 'line_file': line.filename}}

    if chosen == '2':                                 # two colours, no outline of its own
        index, pal, merged, line_hex = done.index, done.pal, [], None
    else:
        index, pal, merged, li = fill_auto.merged(done)
        line_hex = '#' + tpal._hex(pal[li])
    filled = Image.fromarray(pal[index])
    reduced_id = store.save(filled)
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
        'original': original,
        'reduced': image_meta(reduced_id, filled) | {
            'palette': palette, 'accuracy': acc, 'delta_e': de, 'source_id': source_id, 'smoothing': 0,
            'dots': False, 'similar': [], 'repeat': {'x': False, 'y': False}},
        'fill': {'method': int(chosen), 'trials': trials,
                 'alignment': round(done.alignment_score, 3) if chosen != '2' else None, 'regions': done.regions,
                 'doubtful': len(getattr(done, 'doubtful', [])), 'debug_url': debug_url, 'line_color': line_hex,
                 'reference_was_flat': getattr(done, 'reference_was_flat', False), 'stray_merged': merged,
                 'size_px': list(filled.size), 'line_file': line.filename},
    }


@router.get('/api/fill/log')
def fill_log(limit: int = 100):
    """The experiment log: the last runs, newest last (one line each in fill-trials.jsonl)."""
    return {'runs': filltrial.read_log(max(1, min(limit, 1000)))}
