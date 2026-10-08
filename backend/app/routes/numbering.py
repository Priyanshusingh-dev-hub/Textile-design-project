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
import re
import shutil
import zipfile
from pathlib import Path
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image

from ..color_engine import engine as colors
from ..core import filltrial, store  # noqa: F401  (filltrial puts textile_project on the path)
from .common import MAX_PRINT_PX, image_meta
from .linefill import _read

from textile import cli as tcli  # noqa: E402
from textile.io_utils import safe_name, unique_rgb  # noqa: E402

router = APIRouter()
DETAILS = ('kam', 'normal', 'zyada')        # the tool's own words: 3 / 0.4 / 0.1 sq mm, smaller parts join a neighbour
DPI = 300                                   # the mill's working format (textile_project rule 1)
_INCHES = re.compile(r'^\s*(\d+(?:\.\d+)?)\s*[xX×*]\s*(\d+(?:\.\d+)?)\s*$')
_STORED = ('.png', '.tif', '.tiff', '.zip', '.jpg', '.jpeg')   # already compressed: stored, not deflated again


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
                  merge_shades: bool = Form(True), inches: str = Form(''), size: int = Form(3535)):
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
        out = work / 'number'
        if tcli.main(['number', str(src), '--out', str(out), '--name', name, '--colors', str(inks),
                      '--detail', detail, '--size', str(size), *shades]) != 0:
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
                       '--colors', str(inks), '--detail', detail, *shades])
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
    arr = np.asarray(flat)
    pal, inv = unique_rgb(arr, return_inverse=True)
    counts = np.bincount(inv.ravel(), minlength=len(pal))
    order = [k for k in np.argsort(-counts, kind='stable') if counts[k]]
    palette = [{'hex': '#%02X%02X%02X' % tuple(int(v) for v in pal[k]), 'rgb': [int(v) for v in pal[k]],
                'pixels': int(counts[k]), 'coverage': round(float(counts[k] / inv.size * 100), 2)} for k in order]
    de, acc = colors.pixel_match(source, flat)
    original = image_meta(source_id, source) | {'file_name': design.filename, 'file_size': len(raw)}
    return {
        'original': original,
        'reduced': image_meta(reduced_id, flat) | {
            'palette': palette, 'accuracy': acc, 'delta_e': de, 'source_id': source_id, 'smoothing': 0,
            'dots': False, 'similar': [], 'repeat': {'x': False, 'y': False}},
        'number': {
            'job': job, 'name': name, 'areas': made['areas'], 'groups': made['groups'],
            'size_px': made['size_px'], 'dpi': DPI, 'design_match': made['design_match'],
            'sketch_match': made['match'], 'woven': bool(made['woven']), 'missed': made['missed'],
            'inks': [{'hex': '#' + h, 'name': n, 'share': s} for h, n, s in made['inks']],
            'shades_merged': [{'from': '#' + a, 'into': '#' + b} for a, b in made.get('shades_merged', [])],
            'merge_shades': merge_shades, 'detail': detail, 'verify': bool(report['verify']['passed']),
            'sheet_url': f'/api/image/{store.save(sheet)}', 'numbers_url': f'/api/image/{store.save(coloured)}',
            'zip_url': f'/api/number/{job}/zip', 'zip_name': f'{name}_LoomLab_number.zip', 'mill': mill},
    }


@router.get('/api/number/{job}/zip')
def number_zip(job: str, name: str = 'LoomLab_number.zip'):
    """Everything a numbering run made, as one zip (ages out with the cache)."""
    path = store.number_path(job, 'zip')
    if not path.exists():
        raise FileNotFoundError('This numbering run is no longer available. Run it again.')
    return FileResponse(path, media_type='application/zip', filename=safe_name(name) if name.endswith('.zip') else 'LoomLab_number.zip')
