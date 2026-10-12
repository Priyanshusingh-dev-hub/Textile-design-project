"""The third way to a flat design: one coloured design (an AI picture) through
textile's `number`, and optionally `final` at the mill's exact repeat size.

`textile number` (textile_project) brings the picture down to a few flat inks
(blend rims and twin inks dropped, thin lines kept, a colour's shading put on
its own screen when `merge_shades`), numbers every one-colour area, draws the
sketch (plain, bold curves, with numbers), the colours CSV, one plate per ink,
the mill's TIF and a layered PSD. `textile final` draws the same flat design
straight at inches x DPI. This runs the tool's own commands (the code, not a
copy: the same files the command line writes), zips everything for download,
and answers the flat design as the reduced image, so the palette tools,
Separate and Export take it from here, as after a line-art fill.
"""
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image

from ..color_engine import engine as colors
from ..core import filltrial, renumber, store  # noqa: F401  (filltrial puts textile_project on the path)
from ..models import NumberAreasRequest, NumberFeedback, NumberRebuildRequest
from .common import MAX_PRINT_PX, image_meta
from .linefill import _read

from textile import cli as tcli  # noqa: E402
from textile import learn  # noqa: E402
from textile.io_utils import safe_name, unique_rgb  # noqa: E402

router = APIRouter()
DETAILS = ('kam', 'normal', 'zyada')        # the tool's own words: 3 / 0.4 / 0.1 sq mm, smaller parts join a neighbour
DPI = 300                                   # the mill's working format (textile_project rule 1)
_INCHES = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*$')
_STORED = ('.png', '.tif', '.tiff', '.zip', '.jpg', '.jpeg')   # already compressed: stored, not deflated again
ONE_BY_ONE = ('Some pixels were moved one by one (small inks removed), so an area is now two colours: undo that, '
              'or number the design again.')
GONE = 'This numbering run is no longer available. Run it again.'
MAX_MIN_AREA_MM2 = 50.0                     # a part under this many sq mm joins the neighbour it touches most like (0 = the Detail choice)


def _zip(parts, dest: Path):
    """Every file under each (folder, name in the zip), built beside the target and renamed whole."""
    part = dest.with_name(dest.name + '.part')
    with zipfile.ZipFile(part, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for folder, top in parts:
            for p in sorted(folder.rglob('*')):
                if p.is_file():
                    z.write(p, f'{top}/{p.relative_to(folder).as_posix()}',
                            compress_type=zipfile.ZIP_STORED if p.suffix.lower() in _STORED else zipfile.ZIP_DEFLATED)
    part.replace(dest)


def _flat_rgb(image: Image.Image) -> Image.Image:
    """The picture the tool reads: RGB, a transparent background laid on white (not on black)."""
    if image.mode in ('RGBA', 'LA', 'PA') or (image.mode == 'P' and 'transparency' in image.info):
        rgba = image.convert('RGBA')
        white = Image.new('RGBA', rgba.size, (255, 255, 255, 255))
        return Image.alpha_composite(white, rgba).convert('RGB')
    return image.convert('RGB')


def _mill_size(inches: str):
    if not inches.strip():
        return None
    m = _INCHES.match(inches)
    if not m:
        raise HTTPException(422, 'Mill size: width x height in inches, like 23.5x20.7.')
    wi, hi = float(m.group(1)), float(m.group(2))
    if not (1 <= wi <= 120 and 1 <= hi <= 120):
        raise HTTPException(422, 'Mill size: each side between 1 and 120 inches.')
    if round(wi * DPI) * round(hi * DPI) > MAX_PRINT_PX:
        raise HTTPException(422, 'That mill size is too big to make at 300 DPI (over 70 megapixels).')
    return wi, hi


@router.post('/api/number')
def number_design(design: UploadFile = File(...), inks: int = Form(8), detail: str = Form('normal'),
                  merge_shades: bool = Form(True), inches: str = Form(''), size: int = Form(3535),
                  min_area_mm2: float = Form(0.0)):
    """Number one coloured design (textile `number`) and, with `inches`
    ('23.5x20.7'), make it at the mill's repeat size too (textile `final`).
    Answers the design as the original, the flat design as its reduced image
    (palette, match), and what was made: areas, inks, the match to the
    picture, the numbered sheets and the zip of every file. `size`: the sheet's
    width in px (3535 = 11.78 in at 300 DPI, the mill's working format)."""
    if not 2 <= inks <= 20:
        raise HTTPException(422, 'Inks: choose between 2 and 20.')
    if detail not in DETAILS:
        raise HTTPException(422, 'Detail: choose less, normal or more.')
    if not 256 <= size <= 12000:
        raise HTTPException(422, 'Size: choose between 256 and 12000 px.')
    if not (min_area_mm2 == min_area_mm2 and 0 <= min_area_mm2 <= MAX_MIN_AREA_MM2):     # NaN fails the first test
        raise HTTPException(422, 'Smallest shape: choose between 0 and 50 sq mm.')
    mill_in = _mill_size(inches)
    raw, img = _read(design, 'design')
    source = colors.to_8bit(img)
    source_id = store.save(source)
    job = uuid4().hex
    work = store.number_path(job, 'dir')
    work.mkdir(parents=True)
    try:
        name = safe_name(Path(design.filename or 'design').stem)
        src = work / f'{name}.png'
        _flat_rgb(source).save(src)
        shades = ['--merge-shades'] if merge_shades else []
        smallest = (['--min-area', str(max(1, round(min_area_mm2 * (DPI / 25.4) ** 2)))] if min_area_mm2 else [])   # px on the sheet
        out = work / 'number'
        if tcli.main(['number', str(src), '--out', str(out), '--name', name, '--colors', str(inks),
                      '--detail', detail, '--size', str(size), '--run-id', job, *shades, *smallest]) != 0:
            raise HTTPException(422, 'Could not number this design.')
        made = json.loads((out / f'{name}_number.json').read_text(encoding='utf-8'))
        finals = sorted((out / 'package').glob(f'{name}_final_*.png'))
        report = json.loads((out / 'package' / f'{name}_report.json').read_text(encoding='utf-8'))
        if not finals:
            raise HTTPException(422, 'Could not number this design.')
        flat = Image.open(finals[0]).convert('RGB')
        sheet = Image.open(out / made['bold_numbers']).convert('RGB')
        coloured = Image.open(out / made['numbers']).convert('RGB')

        parts = [(out, f'{name}_number')]
        mill = None
        if mill_in:
            wi, hi = mill_in
            tag = f'{wi:g}x{hi:g}in'
            mdir = work / 'mill'
            tcli.main(['final', str(src), '--out', str(mdir), '--name', name, '--inches', f'{wi}x{hi}',
                       '--colors', str(inks), '--detail', detail, *shades,
                       *(['--min-mm2', str(min_area_mm2)] if min_area_mm2 else [])])
            rep_path = mdir / f'{name}_report.json'
            if not rep_path.exists():
                raise HTTPException(422, 'Could not make the design at the mill size.')
            rep = json.loads(rep_path.read_text(encoding='utf-8'))
            mill = {'inches': [wi, hi], 'size_px': rep['size_px'], 'dpi': DPI, 'inks': rep['colours'],
                    'design_match': rep['design_match'], 'passed': bool(rep['verify']['passed']),
                    'cropped': rep['crop'] != 'aspect already matches',    # cut to the repeat's shape, never stretched
                    'folder': f'{name}_mill_{tag}'}
            parts.append((mdir, mill['folder']))
        zip_path = store.number_path(job, 'zip')
        _zip(parts, zip_path)
    finally:
        shutil.rmtree(work, ignore_errors=True)       # the zip holds it all

    reduced_id = store.save(flat)
    palette = _palette_of(flat)
    de, acc = colors.pixel_match(source, flat)
    original = image_meta(source_id, source) | {'file_name': design.filename, 'file_size': len(raw)}
    number = {
        'job': job, 'name': name, 'areas': made['areas'], 'groups': made['groups'],
        'size_px': made['size_px'], 'dpi': DPI, 'design_match': made['design_match'],
        'sketch_match': made['match'], 'woven': bool(made['woven']), 'missed': made['missed'],
        'inks': _inks(made), 'shades_merged': [{'from': '#' + a, 'into': '#' + b} for a, b in made.get('shades_merged', [])],
        'merge_shades': merge_shades, 'detail': detail, 'min_area_mm2': min_area_mm2 or None, 'verify': bool(report['verify']['passed']),
        'sheet_url': f'/api/image/{store.save(sheet)}', 'numbers_url': f'/api/image/{store.save(coloured)}',
        'zip_url': f'/api/number/{job}/zip', 'zip_name': f'{name}_LoomLab_number.zip', 'mill': mill,
        'built_from': reduced_id}
    _remember(job, {'root': job, 'parent': None, 'name': name, 'source_id': source_id, 'number': number})
    return {
        'original': original,
        'reduced': image_meta(reduced_id, flat) | {
            'palette': palette, 'accuracy': acc, 'delta_e': de, 'source_id': source_id, 'smoothing': 0,
            'dots': False, 'similar': [], 'repeat': {'x': False, 'y': False}},
        'number': number,
    }


def _palette_of(flat) -> list:
    """The inks of a flat design, biggest first, as the Reduce step lists them."""
    pal, inv = unique_rgb(np.asarray(flat), return_inverse=True)
    counts = np.bincount(inv.ravel(), minlength=len(pal))
    order = [k for k in np.argsort(-counts, kind='stable') if counts[k]]
    return [{'hex': '#%02X%02X%02X' % tuple(int(v) for v in pal[k]), 'rgb': [int(v) for v in pal[k]],
             'pixels': int(counts[k]), 'coverage': round(float(counts[k] / inv.size * 100), 2)} for k in order]


def _inks(made):
    return [{'hex': '#' + h, 'name': n, 'share': s} for h, n, s in made['inks']]


def _remember(job, side):
    """What a rebuild needs to know about a run (number-{job}.json, ages out with its zip). Best effort: without
    it the run still downloads, only its rebuild answers 'run it again'."""
    try:
        store.number_path(job, 'json').write_text(json.dumps({'v': 1} | side), encoding='utf-8')
    except OSError:
        pass


def _recall(job):
    try:
        side = json.loads(store.number_path(job, 'json').read_text(encoding='utf-8'))
        side['root'], side['name'], side['number']          # noqa: B018  (a damaged file is a gone run)
        return side
    except (OSError, ValueError, KeyError, TypeError):
        raise FileNotFoundError(GONE) from None


def _keep(first):
    """A rebuild reads the first run's zip and picture again: keep them (and its sheets) as long as its children."""
    ids = [first['source_id']] + [first['number'][k].rsplit('/', 1)[-1] for k in ('sheet_url', 'numbers_url')]
    paths = [store.number_path(first['root'], 'zip'), store.number_path(first['root'], 'json')]
    for i in ids:
        try:
            paths.append(store.path_for(i))
        except FileNotFoundError:
            pass
    for p in paths:
        try:
            os.utime(p)
        except OSError:
            pass


def _keyed(names):
    """{'#RRGGBB': name} (the card's) -> {'RRGGBB': name} (the tool's)."""
    return {h.lstrip('#').upper(): n for h, n in (names or {}).items()}


def _names(palette, rgba):
    """The mill's names for the inks the design has now, by exact hex."""
    return _names_of(palette, set(renumber.colour_hexes(rgba[..., :3])))


def _names_of(palette, have):
    """The mill's names for inks `have` (set of 'RRGGBB'), by exact hex. A name given to two inks names the first
    only: two screens never carry one ink's name."""
    out, used = {}, set()
    for p in palette:
        h, n = p.hex.lstrip('#').upper(), (p.name or '').strip()
        if n and h in have and h not in out and n.casefold() not in used:
            out[h] = n
            used.add(n.casefold())
    return out


def _rebuild(job, reduced_id, palette, area_changes=None):
    """Make the zip again for the design as it is on screen (`reduced_id`), or with area edits ({number: colour})
    put on it. Answers (number info, changes, new job, final design | None); (info, changes, None, None) when the
    zip already is that. A design whose colours are each exactly one colour of the first run is mapped colour by
    colour (the earlier, byte-exact way); one where an area went its own way (an edit by number, or an earlier
    one) is rebuilt area by area from the first run's sketch."""
    side = _recall(job)
    rgba = np.asarray(store.load(reduced_id))
    first = side if side['root'] == job else _recall(side['root'])
    zip_path = store.number_path(first['root'], 'zip')
    if not zip_path.exists():
        raise FileNotFoundError(GONE)
    if not area_changes:
        names = _names(palette, rgba)
        if (side['number'].get('built_from') == reduced_id and _keyed(side['number'].get('names')) == names
                and store.number_path(job, 'zip').exists()):
            return side['number'], side['number'].get('changes', []), None, None
    name, mill = first['name'], first['number']['mill']
    flat = renumber.first_final(zip_path, name)
    if rgba.shape[:2] != flat.shape[:2] or (rgba[..., 3] < 255).any():
        raise HTTPException(422, 'This is not the numbered design any more: number it again.')
    screen = rgba[..., :3]
    mapping = None if area_changes else renumber.colour_map(flat, screen)
    areas = lab = None
    old_rows = {}
    if mapping is None:
        with tempfile.TemporaryDirectory() as t:
            lab = renumber.area_labels(zip_path, name, Path(t))
        if lab.shape != screen.shape[:2]:
            raise HTTPException(422, 'This is not the numbered design any more: number it again.')
        cols = renumber.area_colours(lab, screen)
        for c in area_changes or []:
            if c.n > int(lab.max()):
                raise HTTPException(422, f'There is no area {c.n}: the sketch has {int(lab.max())}.')
            cols[c.n] = c.hex.lstrip('#').upper()
        areas = {str(k): v for k, v in cols.items()}
        old_rows = renumber.first_rows(zip_path, name)
        if 'lines' in old_rows:                          # the outline ink: what the outline pixels wear now
            m = (lab == 0) & (renumber._pack(flat) == int(old_rows['lines'], 16))
            if m.any():
                v, c = np.unique(renumber._pack(screen)[m], return_counts=True)
                areas['lines'] = renumber._hex(v[c.argmax()])
        names = _names_of(palette, set(areas.values()))
        changes = sorted({('#' + old_rows[k], '#' + v) for k, v in areas.items() if k in old_rows and old_rows[k] != v})
        changes = [{'from': o, 'to': n} for o, n in changes]
        if not changes and not names:
            if not area_changes and not np.array_equal(screen, flat):      # the first colours, but not the first design
                raise HTTPException(422, ONE_BY_ONE)
            return first['number'] | {'built_from': reduced_id}, [], None, None
    else:
        changes = [{'from': '#' + o, 'to': '#' + n} for o, n in mapping.items() if o != n]
        if not changes and not names:                  # back to the first colours: the first zip is the answer
            return first['number'] | {'built_from': reduced_id}, [], None, None
    _keep(first)
    picture = np.asarray(_flat_rgb(store.load(first['source_id'])))
    new = uuid4().hex
    work = store.number_path(new, 'dir')
    work.mkdir(parents=True)
    final_img = None
    try:
        r = renumber.rebuild(zip_path, name, mill, mapping or {}, picture, work, names, areas, lab)
        if r['code'] != 0 or r['final'] is None:
            raise HTTPException(422, 'Could not put your changes in the zip.')
        final_img = Image.open(r['final']).convert('RGB')
        final_img.load()
        if not area_changes and not np.array_equal(np.asarray(final_img), screen):
            raise HTTPException(422, ONE_BY_ONE if mapping is None else 'Could not put your changes in the zip.')   # never plates unlike the screen's
        parts = [(work / 'number', f'{name}_number')]
        if mill:
            parts.append((work / 'mill', mill['folder']))
        _zip(parts, store.number_path(new, 'zip'))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    number = first['number'] | {
        'job': new, 'design_match': r['made']['design_match'], 'inks': _inks(r['made']), 'verify': r['verify'],
        'zip_url': f'/api/number/{new}/zip', 'built_from': reduced_id, 'changes': changes,
        'names': {'#' + h: n for h, n in names.items()}}
    if areas is not None:
        number['areas_changed'] = sum(1 for k, v in areas.items() if k in old_rows and old_rows[k] != v)
    if mill and r['mill']:
        rep = r['mill']['report']
        number['mill'] = mill | {
            'inks': rep['colours'], 'design_match': rep['design_match'], 'passed': bool(rep['verify']['passed']),
            'left': ['#' + h for h in r['mill']['left']], 'shared': ['#' + h for h in r['mill']['shared']],
            'missing': ['#' + h for h in r['mill']['missing']]}
        if r['mill'].get('by_area'):
            number['mill']['by_area'] = True
    _remember(new, {'root': first['root'], 'parent': job, 'name': name, 'source_id': first['source_id'],
                    'number': number})
    return number, changes, new, final_img


@router.post('/api/number/{job}/rebuild')
def rebuild_number(job: str, req: NumberRebuildRequest):
    """Put the operator's palette edits (recolour, merge, 'Use my inks', undo) into the numbering zip: the first
    run's sketch and colours list with each colour swapped as on screen, the plates, PSD and mill files made again
    by the tool's own code. A new job (a zip being downloaded is never replaced); the first run's zip stays the
    source of every rebuild, so undoing an edit simply maps back. Refused (422) when the zip and the screens
    would disagree (small inks removed pixel by pixel)."""
    number, changes, _, _ = _rebuild(job, req.reduced_id, req.palette)
    return {'number': number, 'changes': changes}


@router.post('/api/number/{job}/areas')
def recolour_areas(job: str, req: NumberAreasRequest):
    """Change the colour of single numbered areas (the numbers on the sketch, one or many at once) and make the
    zip again: sketch and colours list, plates, channels, PSD. An area takes the colour whole, so one colour's areas
    may go different ways; the design answered is the plates' own final, the new reduced design the screens take
    from here. The mill-size files keep their colours (that size has no numbered areas): said on the card."""
    number, changes, new, final = _rebuild(job, req.reduced_id, req.palette, req.changes)
    if new is None:
        raise HTTPException(422, 'Those areas already have these colours.')
    side = _recall(new)
    first = side if side['root'] == new else _recall(side['root'])
    source = _flat_rgb(store.load(first['source_id']))
    reduced_id = store.save(final)
    number['built_from'] = reduced_id
    _remember(new, side | {'number': number})
    de, acc = colors.pixel_match(source, final)
    reduced = image_meta(reduced_id, final) | {
        'palette': _palette_of(final), 'accuracy': acc, 'delta_e': de, 'source_id': first['source_id'],
        'smoothing': 0, 'dots': False, 'similar': [], 'repeat': {'x': False, 'y': False}}
    return {'number': number, 'changes': changes, 'reduced': reduced}


@router.post('/api/number/{job}/feedback')
def number_feedback(job: str, req: NumberFeedback):
    """The operator's word on a numbering run (good / bad + a note) into the textile tool's own memory
    (`learn.feedback`, the log `python -m textile learn` reads, never sent anywhere), on exactly that run: the
    run is recorded with its job id, so another design of the same name never takes the word. A word on a
    rebuilt zip goes to its first run, with the palette edits made since. Nothing in the zip changes."""
    side = _recall(job)
    note = req.note.strip()
    try:
        hit = learn.feedback(side['name'], req.verdict, note, run=side['root'],
                             extra={'by': 'LoomLab', 'changes': side['number'].get('changes', [])})
    except OSError:
        raise HTTPException(503, 'Could not write to the tool’s memory: is the disk full?') from None
    if hit is None:
        raise HTTPException(404, 'This run is not in the tool’s memory, so it cannot be rated.')
    return {'verdict': req.verdict, 'note': note}


@router.get('/api/number/{job}/zip')
def number_zip(job: str, name: str = 'LoomLab_number.zip'):
    """Everything a numbering run made, as one zip (ages out with the cache)."""
    path = store.number_path(job, 'zip')
    if not path.exists():
        raise FileNotFoundError(GONE)
    return FileResponse(path, media_type='application/zip', filename=safe_name(name) if name.endswith('.zip') else 'LoomLab_number.zip')
