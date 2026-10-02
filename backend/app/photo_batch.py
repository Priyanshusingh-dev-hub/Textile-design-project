"""Every picture in a folder -> a finished mill design, one way for all.

    python -m app.photo_batch D:\\pictures [--out OUT] [--size 3535] [--strength 2]
    (or drag the folder onto run-photo-windows.bat)

What a picture is decided by its name, nothing to click:
  NAME_lineart.png + NAME_ref.png (or _colored / _reference)  a line art and its
      colour reference: the app's fill judge tries Reduce of the reference and
      every fill, scores them against the reference and takes the best (see
      core/filltrial.py); the line art is only used when it carries the design
  any other picture   Reduce alone (the suggested number of inks)

Then the same for every one: the flat result gets clean edges (textile's
`edges`: outlines smoothed along themselves, corners and thin lines kept) on
the mill's grid (--size, 3535 px = 11.78 in at 300 DPI), and is written as
textile's export package: NAME_final_<size>_300dpi.tif (the mill's file) and
.png (every ink stacked: the overlapped design), channels, B/W separations,
preview, report, plus NAME_compare.png (the picture, then the result). One
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


def _make(client, name, line, ref, size):
    """The flat design for one picture: (original image, reduced image, route, why, match)."""
    from .core import store
    if line is None:
        up = _upload(client, ref)
        k = int(client.post('/api/colors/suggest', json={'image_id': up['image_id']}).json()['suggested'])
        r = client.post('/api/colors/reduce', json={'image_id': up['image_id'], 'colors': k})
        _ok(r)
        red = r.json()
        return (store.load(up['image_id']), store.load(red['image_id']), 'reduce', 'no line art: Reduce alone',
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


def _compare(original: Image.Image, final_rgb: np.ndarray, path: str):
    w = 900
    a = original.convert('RGB')
    f = Image.fromarray(final_rgb)
    h = max(1, round(f.size[1] * w / f.size[0]))
    sheet = Image.new('RGB', (2 * w + 20, h), 'white')
    sheet.paste(a.resize((w, h), Image.LANCZOS), (0, 0))
    sheet.paste(f.resize((w, h), Image.NEAREST), (w + 20, 0))
    sheet.save(path)


def process(client, name, line, ref, out: Path, size: int, strength: int) -> dict:
    t0 = time.perf_counter()
    original, flat, route, why, reduce_match, inks = _make(client, name, line, ref, size)
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
    folder = out / safe_name(name)
    folder.mkdir(parents=True, exist_ok=True)
    done = tex.export_package(cleaned, pal, str(folder), safe_name(name), DPI)
    v = verify_package(done['paths'], done['size_px'], DPI)
    match = _match(original, final)
    _compare(original, final, str(folder / f'{safe_name(name)}_compare.png'))
    row = {'design': name, 'status': 'ok' if v['passed'] else 'check', 'route': route, 'why': why,
           'inks': len(pal), 'match': round(float(match), 1), 'reduce_match': reduce_match,
           'size_px': f"{done['size_px'][0]}x{done['size_px'][1]}", 'dpi': DPI,
           'print_in': f"{inches(done['size_px'][0], DPI)} x {inches(done['size_px'][1], DPI)}",
           'edges_strength': strength, 'outlines_smoothed': rep['outlines_smoothed'],
           'verify': 'PASS' if v['passed'] else 'FAIL', 'seconds': round(time.perf_counter() - t0, 1),
           'folder': str(folder)}
    tex.write_report(done['paths']['report'], row | {'channels': done['channels'], 'verify_detail': v})
    return row


def run(folder: Path, out: Path | None = None, size: int = 3535, strength: int = 2, client=None) -> dict:
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
            row = process(client, name, line, ref, out, size, strength)
            print(f"{row['route']} · {row['inks']} inks · match {row['match']}% · {row['verify']} · {row['seconds']}s")
        except Exception as e:                       # a bad picture is a row, not the end
            row = {'design': name, 'status': 'error', 'error': str(e)[:300]}
            print(f'error: {e}')
        rows.append(row)
    (out / 'summary.json').write_text(json.dumps(rows, indent=1), encoding='utf-8')
    keys = ['design', 'status', 'route', 'why', 'inks', 'match', 'reduce_match', 'size_px', 'dpi', 'print_in',
            'verify', 'seconds', 'error', 'folder']
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
    ap.add_argument('--open', action='store_true', help='Output folder khol do')
    a = ap.parse_args(argv)
    folder = Path(a.folder)
    if not folder.is_dir():
        print(f'Folder nahi mila: {folder}')
        return 2
    res = run(folder, Path(a.out) if a.out else None, a.size, a.strength)
    if a.open and hasattr(os, 'startfile'):
        os.startfile(res['out'])                                       # Windows
    return 0 if all(r['status'] == 'ok' for r in res['rows']) else 1


if __name__ == '__main__':
    sys.exit(main())
