"""A numbering run made again with the operator's palette edits (recolour, merge, "Use my inks", undo).

Those edits swap one exact colour for another on the numbered design, so every colour of the first flat design
became exactly one colour now (`colour_map`). That is all a numbering run's colours are: the HEX column of
NAME_colors.csv. So the run's own files are taken from its first zip, the CSV's HEX column rewritten, and the
plates made again by the textile tool's own code (`cli.number_package`: paint + PSD + loose images), which gives
back exactly the edited design, one ink per area. An edit that moved single pixels (small inks removed) leaves an
area in two colours, which no CSV can say: `colour_map` answers None and the zip is not rebuilt.

The mill-size folder (`final`) has its own inks, drawn at the mill's size from the picture (a shade can be merged
there and not at 3535, hex codes differ by a dE or so). Each of its inks follows the numbered ink it is nearest to
(CIEDE2000, within MILL_DE); one with no ink that close keeps its colour, and a changed ink with no screen of its
own at mill size is reported. Both are said on the card: nothing changes there behind the operator's back.
"""
import csv
import io
import json
import re
import shutil
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from ..color_engine import engine as colors
from . import filltrial  # noqa: F401  (puts textile_project on the path)

from textile import cli as tcli  # noqa: E402
from textile import curves  # noqa: E402
from textile import names as tnames  # noqa: E402
from textile import number as tnumber  # noqa: E402
from textile.io_utils import save_png, to_image, unique_rgb  # noqa: E402

MILL_DE = 5.0          # a mill ink follows a numbered ink this close (seen: 0-1.3; the next nearest was 4.5)
_HEX = re.compile(r'^#[0-9A-Fa-f]{6}$')


def _pack(rgb: np.ndarray) -> np.ndarray:
    a = rgb.astype(np.uint32)
    return (a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]


def _hex(v: int) -> str:
    return '%06X' % int(v)


def _rgb(hx: str) -> np.ndarray:
    return np.array([int(hx[i:i + 2], 16) for i in (0, 2, 4)], np.uint8)


def colour_map(first: np.ndarray, now: np.ndarray):
    """{old hex: new hex} (no '#') when every colour of `first` is exactly one colour in `now` (same size, RGB);
    None when some colour went two ways (pixels moved one by one)."""
    pal, inv = unique_rgb(first, return_inverse=True)
    key = (inv.reshape(-1).astype(np.int64) << 24) | _pack(now).reshape(-1)
    pairs = np.unique(key)
    old, new = pairs >> 24, pairs & 0xFFFFFF
    if len(np.unique(old)) != len(old):
        return None
    return {_hex(_pack(pal[o])): _hex(n) for o, n in zip(old, new)}


def colour_hexes(rgb: np.ndarray) -> list:
    """Every colour of an RGB image, as 'RRGGBB'."""
    return [_hex(v) for v in np.unique(_pack(rgb))]


def area_regions(zip_path: Path, name: str, tmp: Path):
    """The first run's numbered areas (textile's `Regions`: `.lab` H x W, 0 = a line), found in its sketch exactly as
    `number` found them, so area N here is the CSV's row N."""
    with zipfile.ZipFile(zip_path) as z:
        made = json.loads(z.read(f'{name}_number/{name}_number.json').decode('utf-8'))
        sketch = tmp / 'sketch_seal0.png'
        sketch.write_bytes(z.read(f'{name}_number/{made["sketch"]}'))
    return tnumber.pt.find_regions(str(sketch), size=made['size_px'][0], seal=0, log=lambda m: None)


def area_labels(zip_path: Path, name: str, tmp: Path) -> np.ndarray:
    return area_regions(zip_path, name, tmp).lab


def area_colours(lab: np.ndarray, rgb: np.ndarray) -> dict:
    """{area number: the colour most of its pixels have ('RRGGBB')} for every numbered area of `rgb`."""
    m = lab > 0
    key = (lab[m].astype(np.int64) << 24) | _pack(rgb)[m].astype(np.int64)
    u, c = np.unique(key, return_counts=True)
    area, col = u >> 24, u & 0xFFFFFF
    order = np.lexsort((c, area))
    last = np.r_[area[order][1:] != area[order][:-1], True]
    sel = order[last]
    return {int(a): _hex(v) for a, v in zip(area[sel], col[sel])}


def first_rows(zip_path: Path, name: str) -> dict:
    """The first run's colours CSV as {'1': 'RRGGBB', ..., 'lines': ...}."""
    with zipfile.ZipFile(zip_path) as z:
        rows = list(csv.reader(io.StringIO(z.read(f'{name}_number/{name}_colors.csv').decode('utf-8-sig'))))
    return {r[0]: r[1][1:].upper() for r in rows[1:] if len(r) > 1 and _HEX.match(r[1])}


def csv_hexes(path: Path) -> dict:
    """{'1': 'RRGGBB', ..., 'lines': 'RRGGBB' (when the outlines print in an ink)} of a colours CSV."""
    with open(path, encoding='utf-8', newline='') as fh:
        rows = list(csv.reader(fh))
    return {r[0]: r[1][1:].upper() for r in rows[1:] if len(r) > 1 and _HEX.match(r[1])}


def recolour_areas(rgb: np.ndarray, lab: np.ndarray, old: dict, new: dict) -> np.ndarray:
    """`rgb` with each area whose colour changed (`old` -> `new`, both {'N' or 'lines': hex}) painted in its new
    colour; the outline pixels (area 0) that wore the old outline ink take the new one."""
    out = rgb.copy()
    n = int(lab.max())
    lut = np.full(n + 1, -1, np.int64)
    for k, v in new.items():
        if k.isdigit() and 1 <= int(k) <= n and old.get(k) != v:
            lut[int(k)] = int(v, 16)
    hit = lut[lab] >= 0
    if hit.any():
        out[hit] = np.stack([(lut[lab[hit]] >> s) & 255 for s in (16, 8, 0)], -1).astype(np.uint8)
    if 'lines' in new and old.get('lines') != new['lines']:
        line = (lab == 0) & (_pack(rgb) == int(old['lines'], 16))
        out[line] = _rgb(new['lines'])
    return out


def recolour(rgb: np.ndarray, mapping: dict) -> np.ndarray:
    """Exact colours swapped by the map; any other colour stays."""
    packed = _pack(rgb)
    out = rgb.copy()
    for old, new in mapping.items():
        if old != new:
            out[packed == int(old, 16)] = _rgb(new)
    return out


def _cell(text: str) -> str:
    """A name as a CSV cell Excel will not run as a formula."""
    return "'" + text if text[:1] in ('=', '+', '-', '@', '\t', '\r') else text


def rewrite_csv(path: Path, mapping: dict, names: dict | None = None, areas: dict | None = None) -> None:
    """NAME_colors.csv with every HEX mapped (the 'lines' row too) and the Colour word of a numbered row for its
    new colour; the Number, Share and Group columns and the notes untouched. Unchanged when the map is and no
    names are given. `areas` ({'N' or 'lines': 'RRGGBB'}) sets single rows instead of mapping colours. `names` ({'RRGGBB': the mill's name}) adds an 'Ink' column (paint reads only the HEX one),
    written with a BOM so Excel shows any script."""
    with open(path, encoding='utf-8', newline='') as fh:
        rows = list(csv.reader(fh))
    for row in rows[1:]:
        if len(row) > 1 and _HEX.match(row[1]):
            new = (areas.get(row[0], row[1][1:].upper()) if areas is not None
                   else mapping.get(row[1][1:].upper(), row[1][1:].upper()))
            if new != row[1][1:].upper():
                row[1] = '#' + new
                if row[0].isdigit() and len(row) > 2:
                    row[2] = tnames.colour_name(_rgb(new))
    if names:
        rows[0].append('Ink')
        for row in rows[1:]:
            name = names.get(row[1][1:].upper(), '') if len(row) > 1 and _HEX.match(row[1]) else ''
            row.append(_cell(name))
    with open(path, 'w', encoding='utf-8-sig' if names else 'utf-8', newline='') as fh:
        csv.writer(fh).writerows(rows)


def _extract(z: zipfile.ZipFile, top: str, dest: Path, skip: str | None = None) -> None:
    """Every file under `top/` in the zip into dest (but `top/skip/...`), never outside it."""
    for info in z.infolist():
        if info.is_dir() or not info.filename.startswith(top + '/'):
            continue
        rel = info.filename[len(top) + 1:]
        if skip and (rel == skip or rel.startswith(skip + '/')):
            continue
        target = (dest / rel).resolve()
        if dest.resolve() not in target.parents:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with z.open(info) as src, open(target, 'wb') as out:
            shutil.copyfileobj(src, out)


def first_final(zip_path: Path, name: str) -> np.ndarray:
    """The first run's flat design (its package's final PNG), RGB."""
    with zipfile.ZipFile(zip_path) as z:
        finals = sorted(n for n in z.namelist()
                        if n.startswith(f'{name}_number/package/{name}_final_') and n.endswith('.png'))
        if not finals:
            raise FileNotFoundError('This numbering run is no longer available. Run it again.')
        with z.open(finals[0]) as fh:
            return np.asarray(Image.open(fh).convert('RGB'))


def _nearest(colours: np.ndarray, to: np.ndarray):
    """For each colour, the index of the nearest of `to` and how far (CIEDE2000)."""
    a = colors.rgb_lab(colours.astype(np.uint8)).astype(float)
    b = colors.rgb_lab(to.astype(np.uint8)).astype(float)
    de = colors.delta_e2000(a[:, None, :].repeat(len(b), 1), b[None, :, :].repeat(len(a), 0))
    k = de.argmin(1)
    return k, de[np.arange(len(a)), k]


def rebuild(zip_path: Path, name: str, mill: dict | None, mapping: dict, picture: np.ndarray, work: Path,
            names: dict | None = None, areas: dict | None = None, lab: np.ndarray | None = None) -> dict:
    """The first run's files (from its zip) into `work`/number and `work`/mill with the colours mapped, the plates
    made again. `picture`: the design as numbered (RGB, its own size), for the match. `names`: {'RRGGBB': the
    mill's name} of the inks as they are now (exact hex): in the channel files, PSD layers, the CSV's Ink column
    and the mill files. Answers {code (paint's exit), verify, final (path), made (the new NAME_number.json), mill
    (None or {report, left, missing})}."""
    out = work / 'number'
    out.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as z:
        _extract(z, f'{name}_number', out, skip='package')
        if mill:
            _extract(z, mill['folder'], work / 'mill')
    old_rows = csv_hexes(out / f'{name}_colors.csv')
    rewrite_csv(out / f'{name}_colors.csv', mapping, names, areas)
    names_file = None
    if names:
        names_file = work / 'ink-names.json'
        names_file.write_text(json.dumps(names, ensure_ascii=False), encoding='utf-8')
    made = json.loads((out / f'{name}_number.json').read_text(encoding='utf-8'))
    dpi = 300
    if areas is None:
        paint = lambda im: recolour(im, mapping)
    else:                                              # area by area: one colour's areas may now go different ways
        paint = lambda im: recolour_areas(im, lab, old_rows, areas)
    flat = paint(np.asarray(Image.open(out / f'{name}_flat.png').convert('RGB')))
    save_png(to_image(flat), out / f'{name}_flat.png', dpi)
    save_png(to_image(paint(np.asarray(Image.open(out / f'{name}_rangeen.png').convert('RGB')))),
             out / f'{name}_rangeen.png', dpi)
    if (out / f'{name}_flat_numbers.png').exists():     # the flat inks with each area's number, in the new colours
        reg = tnumber.pt.find_regions(str(out / made['sketch']), size=made['size_px'][0], seal=0, log=lambda m: None)
        tnumber.pt._numbers(reg, str(out), name, flat, kind='flat_numbers', outline=True, full=True)
    bold = np.asarray(Image.open(out / made['bold']).convert('L'))
    k = max(1, round(bold.shape[1] / flat.shape[1]))
    save_png(to_image(curves.colour_sketch(curves.colour_fill(flat, k), bold)), out / made['bold_colour'], dpi * k)

    w, h = made['size_px']
    code = tcli.number_package(name, str(out / made['sketch']), str(out / made['csv']), str(out / made['bold_numbers']),
                               str(out), (w, h), dpi, True, str(names_file) if names_file else None)
    pkg = out / 'package'
    finals = sorted(pkg.glob(f'{name}_final_*.png'))
    report = json.loads((pkg / f'{name}_report.json').read_text(encoding='utf-8')) if code == 0 else {}

    # NAME_number.json: the inks (merged ones counted once, in the first run's order) and the match to the picture
    shares: dict[str, float] = {}
    pal, inv = unique_rgb(flat, return_inverse=True)
    counts = np.bincount(inv.ravel(), minlength=len(pal)) / inv.size * 100
    by_hex = {_hex(_pack(c)): float(s) for c, s in zip(pal, counts)}
    for hx, _, _ in made['inks']:
        new = mapping.get(hx, hx) if areas is None else hx
        if new in by_hex and new not in shares:
            shares[new] = by_hex[new]
    if areas is not None:                              # colours the area edits made, biggest first
        for hx in sorted(by_hex, key=lambda h: -by_hex[h]):
            shares.setdefault(hx, by_hex[hx])
    made['inks'] = [(hx, tnames.colour_name(_rgb(hx)), round(s, 2)) for hx, s in shares.items() if s > 0.05]
    made['design_match'] = tnumber.design_match(picture, flat)
    if names:
        made['ink_names'] = names
    (out / f'{name}_number.json').write_text(json.dumps(made, indent=1, default=str), encoding='utf-8')

    result = {'code': code, 'verify': bool(report.get('verify', {}).get('passed')), 'final': finals[0] if finals else None,
              'made': made, 'mill': None}
    if mill:
        if areas is None:
            result['mill'] = _mill(work / 'mill', name, mill, mapping, picture, names)
        else:                  # the mill's size has no numbered areas to edit: its files stay as they were
            rp = json.loads((work / 'mill' / f'{name}_report.json').read_text(encoding='utf-8'))
            result['mill'] = {'report': rp, 'left': [], 'shared': [], 'missing': [], 'by_area': True}
    return result


def _mill(mdir: Path, name: str, mill: dict, mapping: dict, picture: np.ndarray, names: dict | None = None) -> dict:
    """The mill-size folder with the operator's edits: each numbered ink is followed by its nearest mill ink (within
    MILL_DE; the closest one if several are near it), which takes the ink's new colour and its name. Every other
    mill ink keeps its own hex: an untouched ink is never moved to the 3535 sheet's hex, and two mill screens are
    made one only when the operator merged their numbered inks. Said on the card: `left` (a mill ink near no
    numbered ink), `shared` (a second mill screen near a changed ink: it kept its colour), `missing` (a changed ink
    with no mill screen). Made again only when a colour or a name changed."""
    finals = sorted(mdir.glob(f'{name}_final_*.png'))
    rgb = np.asarray(Image.open(finals[0]).convert('RGB'))
    pal, inv = unique_rgb(rgb, return_inverse=True)
    keys = list(mapping)
    near, de = _nearest(pal, np.array([_rgb(h) for h in keys]))
    own = [_hex(_pack(c)) for c in pal]
    lead = {}                                          # numbered ink -> the mill ink that follows it
    for i, (k, d) in enumerate(zip(near, de)):
        if d <= MILL_DE and (keys[k] not in lead or d < de[lead[keys[k]]]):
            lead[keys[k]] = i

    def target(key):
        """The mill hex a numbered ink's new colour is: merged into an untouched ink -> that ink's mill screen."""
        v = mapping[key]
        if v != key and mapping.get(v) == v and v in lead:
            return own[lead[v]]
        return v if v != key else own[lead[key]]

    new_hex, left, shared, named = list(own), [], [], {}
    for i, (k, d) in enumerate(zip(near, de)):
        key = keys[k]
        if d > MILL_DE:
            left.append(own[i])
        elif lead[key] == i:
            new_hex[i] = target(key)
            if names and mapping[key] in names:
                named[new_hex[i]] = names[mapping[key]]
        elif mapping[key] != key:
            shared.append(own[i])
    missing = [o for o, n in mapping.items() if o != n and o not in lead]
    report_path = mdir / f'{name}_report.json'
    if new_hex == own and not named:
        return {'report': json.loads(report_path.read_text(encoding='utf-8')), 'left': left, 'shared': shared,
                'missing': missing}
    uniq = list(dict.fromkeys(new_hex))
    remap = np.array([uniq.index(hx) for hx in new_hex], np.uint8)
    index = remap[inv.reshape(rgb.shape[:2])]
    new_pal = np.array([_rgb(hx) for hx in uniq])
    wi, hi = mill['inches']
    Wt, Ht = rgb.shape[1], rgb.shape[0]
    cut, note = tcli.fit_to(picture, Wt, Ht)
    for p in mdir.iterdir():
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
    tcli.final_package(index, new_pal, str(mdir), name, 300, cut, (wi, hi), note, named or None)
    return {'report': json.loads(report_path.read_text(encoding='utf-8')), 'left': left, 'shared': shared,
            'missing': missing}
