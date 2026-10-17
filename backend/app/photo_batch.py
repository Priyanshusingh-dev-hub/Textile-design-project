"""Every picture in a folder -> a finished mill design, one way for all.

    python -m app.photo_batch D:\\pictures [--out OUT] [--size 3535] [--strength 2]
    (or drag the folder onto run-photo-windows.bat)

What a picture is decided by its name, nothing to click:
  NAME_lineart.png + NAME_ref.png (or _colored / _reference)  a line art and its
      colour reference: the app's fill judge tries Reduce of the reference and
      every fill, scores them against the reference and takes the best (see
      core/filltrial.py); the line art is only used when it carries the design
  any other picture   Reduce alone (the suggested number of inks, or the
                      count in its name: rose_6inks.png)

Then the same for every one: the flat result gets clean edges (textile's
`edges`: outlines smoothed along themselves, corners and thin lines kept) on
the mill's grid (--size, 3535 px = 11.78 in at 300 DPI), and is written as
textile's export package: NAME_final_<size>_300dpi.tif (the mill's file) and
.png (every ink stacked: the overlapped design), channels, B/W separations,
preview, report, plus NAME_compare.png (the picture, then the result). A
Reduce of a photo-like design (the app's photographic rule) also gets
NAME/dots/ (same inks as dots of one size; whether the mill's mesh holds them
is the mill's call, so flat stays the main file). One
bad picture is a row marked error, never the end of the folder.

summary.csv / summary.json in the output folder: which way each went and why,
the match, the inks, the checks. Every fill run is also a line in the
experiment log (data/fill-trials.jsonl).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

from .core import filltrial          # puts ../textile_project on sys.path
from textile import cli as tcli
from textile import edges as tedges
from textile import export as tex
from textile.io_utils import inches, safe_name
from textile.verify import verify_package

PICTURES = tcli.IMAGES
_MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
         '.tif': 'image/tiff', '.tiff': 'image/tiff', '.bmp': 'image/bmp'}
DPI = 300
MATCH_PX = 1200          # the match is judged at this width, both sides on one grid
MAX_COLOURS = 64


def find_pictures(folder: Path):
    """(pairs, singles): pairs = [(name, line path, reference path)], singles =
    [(name, path)] — every other picture, in name order."""
    pairs, _ = tcli.pairs(str(folder))
    used = {os.path.normcase(p[1]) for p in pairs} | {os.path.normcase(p[2]) for p in pairs}
    singles = [(Path(f).stem, folder / f) for f in sorted(os.listdir(folder), key=str.lower)
               if f.lower().endswith(PICTURES) and os.path.normcase(str(folder / f)) not in used
               and not Path(f).stem.lower().endswith('_lineart')]
    return [(n, Path(l), Path(r)) for n, l, r in pairs], singles


def _upload(client, path: Path):
    r = client.post('/api/image/upload', files={'file': (path.name, path.read_bytes(),
                                                          _MIME.get(path.suffix.lower(), 'image/png'))})
    _ok(r)
    return r.json()


def _ok(r):
    if r.status_code != 200:
        detail = r.json().get('detail') if r.headers.get('content-type', '').startswith('application/json') else r.text
        raise RuntimeError(str(detail)[:300])


def inks_in_name(name: str) -> int | None:
    """'teal_ikat_4inks' -> 4: the operator's ink count, written in the file name
    (as the hot folder reads it); None = the suggested count."""
    import re
    m = re.search(r'(?<![0-9])([1-9]|1[0-9]|20)[ _-]?inks?(?![a-z])', name.lower())
    return int(m.group(1)) if m else None


def _make(client, name, line, ref, size):
    """The flat design for one picture: (original image, reduced image, route, why, match)."""
    from .core import store
    if line is None:
        up = _upload(client, ref)
        k = inks_in_name(name) or int(client.post('/api/colors/suggest', json={'image_id': up['image_id']}).json()['suggested'])
        r = client.post('/api/colors/reduce', json={'image_id': up['image_id'], 'colors': k})
        _ok(r)
        red = r.json()
        why = 'no line art: Reduce alone' + (f', {k} inks from the file name' if inks_in_name(name) else '')
        return (store.load(up['image_id']), store.load(red['image_id']), 'reduce', why,
                red['accuracy'], len(red['palette']))
    r = client.post('/api/fill', data={'size': str(size), 'method': 'auto'},
                    files={'line': (line.name, line.read_bytes(), _MIME.get(line.suffix.lower(), 'image/png')),
                           'ref': (ref.name, ref.read_bytes(), _MIME.get(ref.suffix.lower(), 'image/png'))})
    _ok(r)
    j = r.json()
    f = j['fill']
    t = f['trials'] or {}
    route = 'reduce (reference alone)' if f['method'] == 0 else f"method {f['method']}"
    why = t.get('reason', 'chosen')
    if t.get('margin') is not None:
        why += f" (best fill {t['margin']:+} vs Reduce)"
    return (store.load(j['original']['image_id']), store.load(j['reduced']['image_id']), route, why,
            j['reduced']['accuracy'], len(j['reduced']['palette']))


def _match(original: Image.Image, final_rgb: np.ndarray):
    from .color_engine.engine import pixel_match
    w = min(MATCH_PX, final_rgb.shape[1])
    h = max(1, round(final_rgb.shape[0] * w / final_rgb.shape[1]))
    a = original.convert('RGB').resize((w, h), Image.LANCZOS)
    b = Image.fromarray(final_rgb).resize((w, h), Image.NEAREST)
    return pixel_match(a, b)[1]


def _dots_version(original: Image.Image, pal: np.ndarray, size, folder: Path, name: str, flat_rgb: np.ndarray):
    """The same inks as dots (the app's own index separation: Floyd-Steinberg at
    the design's size, then redrawn as dots of one size at print size), made
    only for a design with real photographic shading: the app's own rule, the
    best match any ink count reaches (`suggest_colors` curve) under auto's
    `photographic_ceiling` (80). Judging by "looks closer" instead was tried:
    on the AI pictures (ceilings 86-89) dots scored 2-3 seen-match points
    higher, but only by sprinkling the picture's noise over flat grounds as
    stray dots. Returns the row fields, or {} for a flat-printable design."""
    from .color_engine import engine as colors
    from .separation_engine import engine as separation
    from .auto import load_config
    hexes = ['#%02X%02X%02X' % tuple(int(v) for v in c) for c in pal]
    src = original.convert('RGB')
    ceiling = max(float(p['accuracy']) for p in colors.suggest_colors(src)['curve'])
    if ceiling >= float(load_config()['photographic_ceiling']):
        return {}
    flat_small = Image.fromarray(flat_rgb).resize(src.size, Image.NEAREST)
    dotted = colors.dither(src, hexes).convert('RGB')
    flat_seen = colors.seen_match(src, flat_small)[1]
    dots_seen = colors.seen_match(src, dotted)[1]
    out = {'flat_seen': round(float(flat_seen), 1), 'dots_seen': round(float(dots_seen), 1), 'ceiling': round(ceiling, 1)}
    d = np.asarray(dotted)
    masks = []
    for c in pal:
        rgba = np.zeros(d.shape[:2] + (4,), np.uint8)
        rgba[..., 3] = (d == c).all(-1) * np.uint8(255)
        masks.append(Image.fromarray(rgba))
    big = separation.resize_masks(masks, size, dots=True, colours=hexes)
    alphas = np.stack([np.asarray(m)[..., 3] for m in big])
    index = alphas.argmax(0).astype(np.uint8)
    used = np.unique(index)
    remap = np.zeros(len(pal), np.uint8)
    remap[used] = np.arange(len(used))
    sub = folder / 'dots'
    sub.mkdir(exist_ok=True)
    done = tex.export_package(remap[index], pal[used], str(sub), f'{name}_dots', DPI)
    v = verify_package(done['paths'], done['size_px'], DPI)
    dot_mm = round(separation.dot_pixels(src.size, size) * 25.4 / DPI, 2)
    # the app's own limits (Export's dotSizeNote): finer than most mesh holds / big enough to see as a pattern
    note = 'too fine for most mesh' if dot_mm < 0.12 else 'pattern will show' if dot_mm > 0.45 else 'ok'
    return out | {'dots_folder': str(sub), 'dot_mm': dot_mm, 'dots_note': note,
                  'dots_verify': 'PASS' if v['passed'] else 'FAIL'}


def _compare(original: Image.Image, final_rgb: np.ndarray, path: str):
    w = 900
    a = original.convert('RGB')
    f = Image.fromarray(final_rgb)
    h = max(1, round(f.size[1] * w / f.size[0]))
    sheet = Image.new('RGB', (2 * w + 20, h), 'white')
    sheet.paste(a.resize((w, h), Image.LANCZOS), (0, 0))
    sheet.paste(f.resize((w, h), Image.NEAREST), (w + 20, 0))
    sheet.save(path)


def _package(original: Image.Image, flat: Image.Image, folder: Path, fname: str, size: int, strength: int):
    """A flat design -> clean edges on the print grid -> textile's export package
    in `folder`. Returns (final rgb, palette, export result, verify, edge report, match)."""
    rgb = np.asarray(flat.convert('RGB'))
    pal = np.unique(rgb.reshape(-1, 3), axis=0)
    if len(pal) > MAX_COLOURS:
        raise RuntimeError(f'the result has {len(pal)} colours, not a flat design')
    index = tcli.pl.map_to_palette(rgb, pal).astype(np.uint8)      # exact: every colour is in the palette
    cleaned, rep = tedges.clean(index, size / index.shape[1], strength)
    used = np.unique(cleaned)
    remap = np.zeros(len(pal), np.uint8)
    remap[used] = np.arange(len(used))
    cleaned, pal = remap[cleaned], pal[used]
    final = pal[cleaned]
    folder.mkdir(parents=True, exist_ok=True)
    done = tex.export_package(cleaned, pal, str(folder), fname, DPI)
    v = verify_package(done['paths'], done['size_px'], DPI)
    return final, pal, done, v, rep, _match(original, final)


def process(client, name, line, ref, out: Path, size: int, strength: int, versions: bool = True) -> dict:
    t0 = time.perf_counter()
    original, flat, route, why, reduce_match, inks = _make(client, name, line, ref, size)
    folder = out / safe_name(name)
    final, pal, done, v, rep, match = _package(original, flat, folder, safe_name(name), size, strength)
    _compare(original, final, str(folder / f'{safe_name(name)}_compare.png'))
    # a fill is flat by construction (its shapes are the line art's): dots only for a Reduce
    dots = _dots_version(original, pal, done['size_px'], folder, safe_name(name), final) \
        if route.startswith('reduce') else {}
    row = {'design': name, 'status': 'ok' if v['passed'] else 'check', 'route': route, 'why': why,
           'inks': len(pal), 'match': round(float(match), 1), 'reduce_match': reduce_match,
           'size_px': f"{done['size_px'][0]}x{done['size_px'][1]}", 'dpi': DPI,
           'print_in': f"{inches(done['size_px'][0], DPI)} x {inches(done['size_px'][1], DPI)}",
           'edges_strength': strength, 'outlines_smoothed': rep['outlines_smoothed'],
           'verify': 'PASS' if v['passed'] else 'FAIL',
           'folder': str(folder)} | dots
    if versions:
        row['versions'] = _versions(original, flat, final, len(pal), line, route, folder, safe_name(name),
                                    size, strength)
    row['seconds'] = round(time.perf_counter() - t0, 1)
    tex.write_report(done['paths']['report'], row | {'channels': done['channels'], 'verify_detail': v})
    return row


# ---- versions: the same design made a few other ways, side by side, for the operator to pick ----------
# Measured, no one rule wins everywhere: the suggested count dropped a thin cream lattice (2218) and a
# rust accent (teal ikat); ranking palettes by distinctness lost small orange dots (pink paisley).

def distinct_palette(img: Image.Image, k: int, extra: int = 3, near: float = 10.0) -> Image.Image:
    """`distinct`: Reduce to k+extra inks, then merge only near-duplicates
    (CIEDE2000 under `near`, closest pair first) back towards k: a small ink
    that is really another colour (a lattice, an accent) keeps its screen; may
    end with up to `extra` more inks than k. Kept the 2218 cream, the paisley
    orange and the ikat rust; matched or beat auto on six designs."""
    from .color_engine import engine as colors
    _, pal = colors.quantize_full(img, min(20, k + extra), 0)
    cols = [np.array(c.rgb, float) for c in pal]
    cov = [c.coverage for c in pal]
    while len(cols) > k:
        lab = colors.rgb_lab(np.array(cols).round().astype(np.uint8))
        d = colors.delta_e2000(lab[:, None], lab[None])
        np.fill_diagonal(d, np.inf)
        i, j = np.unravel_index(np.argmin(d), d.shape)
        if d[i, j] >= near:
            break
        w = cov[i] + cov[j]
        cols[j] = (cols[i] * cov[i] + cols[j] * cov[j]) / max(w, 1e-9)
        cov[j] = w
        del cols[i], cov[i]
    hexes = ['#%02X%02X%02X' % tuple(int(round(x)) for x in c) for c in cols]
    return colors.quantize_full(img, len(hexes), 0, palette_hex=hexes)[0].convert('RGB')


def lattice_from_lineart(flat: Image.Image, original: Image.Image, line_path: Path):
    """`lattice`: the line art's lines that run over open ground (ground all
    round for 4 px: never a motif outline) painted in the ink the colour image
    shows there (a new ink when the Reduce had none for it); the colour
    image's own broken bits of that ink on open ground (pieces under 200 px)
    go. None when the colour image has no such lines. For a faint AI lattice
    (2218), drawn as the line art draws it (there: denser than the colour's)."""
    import cv2
    from .color_engine import engine as colors
    a = np.asarray(flat.convert('RGB')).copy()
    h, w = a.shape[:2]
    cols, inv = np.unique(a.reshape(-1, 3), axis=0, return_inverse=True)
    inv = inv.reshape(h, w)
    ground = int(np.bincount(inv.ravel()).argmax())
    la = np.asarray(Image.open(line_path).convert('L').resize((w, h), Image.LANCZOS))
    lines = cv2.GaussianBlur(la, (3, 3), 0) < 150
    k9 = np.ones((9, 9), np.uint8)
    on_ground = lines & (cv2.erode((inv == ground).astype(np.uint8), k9) > 0)
    if on_ground.mean() < 0.002:
        return None
    ref = np.asarray(original.convert('RGB').resize((w, h), Image.LANCZOS))
    px = ref[on_ground]
    g_lab = colors.rgb_lab(cols[ground][None].astype(np.uint8))[0]
    off = colors.delta_e2000(colors.rgb_lab(px.astype(np.uint8)), g_lab[None]) > 4
    # the colour image's lattice may be sparser than the line art's (2218: 9% of the line art's lattice
    # pixels show it): its colour is the median of the pixels that are really off the ground
    if off.mean() < 0.05:
        return None                                   # the colour image has no lines there
    colour = np.median(px[off], 0).round().astype(np.uint8)
    lab = colors.rgb_lab(np.vstack([cols, colour[None]]).astype(np.uint8))
    d = colors.delta_e2000(lab[-1][None], lab[:-1])
    d[ground] = np.inf
    ink = int(np.argmin(d))
    if d[ink] > 8:                                    # the Reduce had no ink for it: it becomes one
        cols = np.vstack([cols, colour[None]])
        ink = len(cols) - 1
    from scipy import ndimage
    open_ground = cv2.erode(((inv == ground) | (inv == ink)).astype(np.uint8), k9) > 0
    lab_bits, n = ndimage.label((inv == ink) & open_ground)
    if n:
        sizes = np.bincount(lab_bits.ravel())
        a[(sizes[lab_bits] < 200) & (lab_bits > 0)] = cols[ground]
    a[lines & open_ground] = cols[ink]
    return Image.fromarray(a)


def _versions(original, flat, final, k, line, route, folder, name, size, strength) -> list:
    """Every other version, each a package in folder/versions/<mode>/, and one
    sheet to choose from: NAME_versions.png."""
    from .color_engine import engine as colors
    makers = [('more', lambda: colors.quantize_full(original, min(20, k + 2), 0)[0].convert('RGB')),
              ('distinct', lambda: distinct_palette(original, k))]
    if line is not None and route.startswith('reduce'):
        makers.append(('lattice', lambda: lattice_from_lineart(flat, original, line)))
    shown = [('auto', final, k)]
    rows = []
    for mode, make in makers:
        try:
            img = make()
            if img is None:
                continue
            f, pal, done, v, _, match = _package(original, img, folder / 'versions' / mode, f'{name}_{mode}',
                                                 size, strength)
        except Exception as e:                               # one version failing never loses the design
            rows.append({'mode': mode, 'error': str(e)[:200]})
            continue
        shown.append((mode, f, len(pal)))
        rows.append({'mode': mode, 'inks': len(pal), 'match': round(float(match), 1),
                     'verify': 'PASS' if v['passed'] else 'FAIL', 'folder': str(folder / 'versions' / mode)})
    _versions_sheet(original, shown, folder / f'{name}_versions.png')
    return rows


def _versions_sheet(original: Image.Image, shown: list, path: Path):
    """The picture and every version: whole (top) and the busiest crop zoomed (bottom), each labelled."""
    from PIL import ImageDraw
    from scipy.ndimage import uniform_filter
    from .color_engine import engine as colors
    src = original.convert('RGB')
    W = 420
    H = max(1, round(src.size[1] * W / src.size[0]))
    base = np.asarray(Image.fromarray(shown[0][1]).resize(src.size, Image.NEAREST)).astype(int)
    edge = np.zeros(base.shape[:2])
    edge[:, 1:] += (base[:, 1:] != base[:, :-1]).any(-1)
    c = max(40, min(src.size) // 5)
    dens = uniform_filter(edge, c)
    dens[:c // 2], dens[-c // 2:], dens[:, :c // 2], dens[:, -c // 2:] = 0, 0, 0, 0
    y, x = np.unravel_index(dens.argmax(), dens.shape)
    box = (max(0, x - c // 2), max(0, y - c // 2), max(0, x - c // 2) + c, max(0, y - c // 2) + c)
    cells = [('picture', src, None)] + [(m, Image.fromarray(f).resize(src.size, Image.NEAREST), k) for m, f, k in shown]
    sheet = Image.new('RGB', (len(cells) * (W + 10), H + W + 60), 'white')
    draw = ImageDraw.Draw(sheet)
    for i, (label, img, k) in enumerate(cells):
        x0 = i * (W + 10)
        sheet.paste(img.resize((W, H), Image.LANCZOS if label == 'picture' else Image.NEAREST), (x0, 22))
        sheet.paste(img.crop(box).resize((W, W), Image.NEAREST), (x0, H + 50))
        if k is None:
            text = 'picture'
        else:
            text = (f'{label}: {k} inks, match {colors.pixel_match(src, img)[1]:.1f}, '
                    f'seen {colors.seen_match(src, img)[1]:.1f}')
        draw.text((x0 + 4, 4), text, fill='black')
    sheet.save(path)


def run(folder: Path, out: Path | None = None, size: int = 3535, strength: int = 2, client=None,
        versions: bool = True) -> dict:
    from fastapi.testclient import TestClient
    from .main import app
    client = client or TestClient(app, raise_server_exceptions=False)
    out = out or folder / 'output'
    out.mkdir(parents=True, exist_ok=True)
    pairs, singles = find_pictures(folder)
    jobs = [(n, l, r) for n, l, r in pairs] + [(n, None, p) for n, p in singles]
    if not jobs:
        raise SystemExit(f'Is folder me koi picture nahi: {folder}')
    rows = []
    for i, (name, line, ref) in enumerate(jobs, 1):
        print(f"[{i}/{len(jobs)}] {name} ({'pair' if line else 'single'}) ...", end=' ', flush=True)
        try:
            row = process(client, name, line, ref, out, size, strength, versions)
            print(f"{row['route']} · {row['inks']} inks · match {row['match']}% · {row['verify']} · {row['seconds']}s"
                  + (f" · dots version too ({row['flat_seen']} -> {row['dots_seen']} seen, {row['dot_mm']} mm dots, {row['dots_note']}: "
                     "mill ka mesh pakdega to hi)" if row.get('dots_folder') else ''))
            for vr in row.get('versions', []):
                print(f"      version {vr['mode']}: " + (f"{vr['inks']} inks · match {vr['match']}% · {vr['verify']}"
                                                           if 'error' not in vr else f"error: {vr['error']}"))
        except Exception as e:                       # a bad picture is a row, not the end
            row = {'design': name, 'status': 'error', 'error': str(e)[:300]}
            print(f'error: {e}')
        rows.append(row)
    for r in rows:
        r['other_versions'] = '; '.join(f"{v['mode']} {v['inks']} inks {v['match']}%" for v in r.get('versions', [])
                                        if 'error' not in v)
    (out / 'summary.json').write_text(json.dumps(rows, indent=1), encoding='utf-8')
    keys = ['design', 'status', 'route', 'why', 'inks', 'match', 'reduce_match', 'size_px', 'dpi', 'print_in',
            'verify', 'flat_seen', 'dots_seen', 'dot_mm', 'dots_note', 'dots_verify', 'dots_folder', 'other_versions', 'seconds', 'error', 'folder']
    with open(out / 'summary.csv', 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, keys, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    bad = [r for r in rows if r['status'] != 'ok']
    print(f"\n{len(rows) - len(bad)} of {len(rows)} theek. Files: {out}")
    return {'rows': rows, 'out': str(out)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description='Folder ki har picture -> mill design (judge + kinare saaf + 3535 px export)')
    ap.add_argument('folder')
    ap.add_argument('--out', default=None, help='Output folder (default: <folder>/output)')
    ap.add_argument('--size', type=int, default=3535, help='Width px (default 3535 = 11.78 in @ 300 DPI)')
    ap.add_argument('--strength', type=int, choices=[1, 2, 3], default=2, help='Kinare saaf: 1 halka, 2 normal, 3 zyada')
    ap.add_argument('--quick', action='store_true', help='Sirf auto version (more/distinct/lattice nahi)')
    ap.add_argument('--open', action='store_true', help='Output folder khol do')
    a = ap.parse_args(argv)
    folder = Path(a.folder)
    if not folder.is_dir():
        print(f'Folder nahi mila: {folder}')
        return 2
    res = run(folder, Path(a.out) if a.out else None, a.size, a.strength, versions=not a.quick)
    if a.open and hasattr(os, 'startfile'):
        os.startfile(res['out'])                                       # Windows
    return 0 if all(r['status'] == 'ok' for r in res['rows']) else 1


if __name__ == '__main__':
    sys.exit(main())
