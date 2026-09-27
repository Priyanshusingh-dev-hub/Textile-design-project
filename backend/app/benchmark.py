"""Benchmark: auto mode over a folder of real designs, with a report a mill
can read — how many came out print-ready untouched, how long each took,
how well each matched, and what held the rest.

    python -m app.benchmark D:\\designs [--width-in 30] [--meters 500]
    (or drag the folder onto run-benchmark-windows.bat)

Every design goes through the real API in-process (the same code the app and
the bot use). An operator's own separation of a design, saved beside it as
`<name>.operator.<ext>`, is compared with LoomLab's on the same measure: the
colour difference from the original, pixel by pixel.

Writes <folder>/benchmark-<date>/: report.html (open in a browser),
report.csv (Excel) and report.json.
"""
from __future__ import annotations

import argparse
import csv
import html
import io
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

DESIGN_TYPES = {'.png', '.jpg', '.jpeg', '.webp', '.tif', '.tiff', '.psd', '.bmp'}
_MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
         '.tif': 'image/tiff', '.tiff': 'image/tiff', '.psd': 'image/vnd.adobe.photoshop', '.bmp': 'image/bmp'}


def find_designs(folder: Path) -> list[tuple[Path, Path | None]]:
    """(design, the operator's version of it or None), in name order."""
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in DESIGN_TYPES)
    operator = {p.name.lower().split('.operator.')[0]: p for p in files if '.operator.' in p.name.lower()}
    return [(p, operator.get(p.stem.lower())) for p in files if '.operator.' not in p.name.lower()]


def image_match(original: Image.Image, other: Image.Image) -> tuple[float, float]:
    """(mean CIEDE2000, 0-100 match) of `other` against `original`."""
    from .color_engine.engine import pixel_match
    return pixel_match(original, other)


def ink_count(image: Image.Image, floor: float = 0.001) -> int:
    """Flat colours in an image that cover at least `floor` of it (an
    operator's file may carry a few stray anti-aliased pixels)."""
    a = np.asarray(image.convert('RGB')).reshape(-1, 3)
    _, counts = np.unique(a, axis=0, return_counts=True)
    return int((counts >= floor * len(a)).sum())


def run(folder: Path, width_in=None, dpi=300, meters=None, out: Path | None = None, client=None) -> dict:
    from fastapi.testclient import TestClient
    from .core import store
    from .main import app
    client = client or TestClient(app)
    out = out or folder / f"benchmark-{datetime.now():%Y-%m-%d-%H%M}"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    designs = find_designs(folder)
    if not designs:
        raise SystemExit(f'No designs (PNG, JPG, TIFF, PSD, WEBP, BMP) in {folder}')
    for n, (path, op_path) in enumerate(designs, 1):
        print(f'[{n}/{len(designs)}] {path.name} ...', end=' ', flush=True)
        fields = {k: str(v) for k, v in (('width_in', width_in), ('dpi', dpi), ('meters', meters)) if v}
        t0 = time.perf_counter()
        r = client.post('/api/auto/upload', data=fields,
                        files={'file': (path.name, path.read_bytes(), _MIME[path.suffix.lower()])})
        seconds = round(time.perf_counter() - t0, 1)
        if r.status_code != 200:
            detail = r.json().get('detail') if r.headers.get('content-type', '').startswith('application/json') else r.text
            rows.append({'design': path.name, 'status': 'error', 'error': str(detail)[:200], 'seconds': seconds})
            print(f'error: {detail}')
            continue
        rep = r.json()
        row = {'design': path.name, 'status': rep['status'], 'inks': len(rep['inks']),
               'accuracy': rep['accuracy'], 'delta_e': rep['delta_e'], 'seconds': seconds,
               'steps': rep['seconds'], 'print': f"{rep['print']['width_in']:g} x {rep['print']['height_in']:g} in",
               'held_by': [w['code'] for w in rep['warnings'] if w['blocking']],
               'notes': [w['code'] for w in rep['warnings'] if not w['blocking']],
               'quote': (rep.get('quote') or {}).get('total'), 'job_id': rep['job_id']}
        if op_path is not None:
            original = Image.open(path); original.load()
            reduced = store.load(rep['reduced_id'])
            operator = Image.open(op_path); operator.load()
            row['loomlab_match'] = image_match(original, reduced)[1]
            row['operator_match'] = image_match(original, operator)[1]
            row['operator_inks'] = ink_count(operator)
            row['operator_file'] = op_path.name
        rows.append(row)
        print(f"{rep['status']} · {row['inks']} inks · {rep['accuracy']}% · {seconds}s")
    summary = summarise(rows)
    (out / 'report.json').write_text(json.dumps({'summary': summary, 'designs': rows}, indent=1), encoding='utf-8')
    write_csv(out / 'report.csv', rows)
    (out / 'report.html').write_text(render_html(summary, rows, folder, width_in, meters), encoding='utf-8')
    print(f"\n{summary['auto_ok']} of {summary['designs']} print-ready untouched "
          f"({summary['auto_ok_percent']}%). Report: {out / 'report.html'}")
    return {'summary': summary, 'designs': rows, 'out': str(out)}


def summarise(rows: list[dict]) -> dict:
    done = [r for r in rows if r['status'] != 'error']
    ok = [r for r in done if r['status'] == 'auto_ok']
    held: dict[str, int] = {}
    for r in done:
        for code in r['held_by']:
            held[code] = held.get(code, 0) + 1
    paired = [r for r in done if 'operator_match' in r]
    return {
        'designs': len(rows), 'errors': len(rows) - len(done), 'auto_ok': len(ok),
        'auto_ok_percent': round(len(ok) / len(rows) * 100, 1) if rows else 0.0,
        'seconds_mean': round(statistics.mean(r['seconds'] for r in done), 1) if done else None,
        'seconds_median': round(statistics.median(r['seconds'] for r in done), 1) if done else None,
        'accuracy_mean': round(statistics.mean(r['accuracy'] for r in done), 1) if done else None,
        'inks_mean': round(statistics.mean(r['inks'] for r in done), 1) if done else None,
        'held_by': dict(sorted(held.items(), key=lambda kv: -kv[1])),
        'compared_with_operator': len(paired),
        'loomlab_match_mean': round(statistics.mean(r['loomlab_match'] for r in paired), 1) if paired else None,
        'operator_match_mean': round(statistics.mean(r['operator_match'] for r in paired), 1) if paired else None,
        'loomlab_as_good': sum(r['loomlab_match'] >= r['operator_match'] - 0.5 for r in paired),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    cols = ['design', 'status', 'inks', 'accuracy', 'delta_e', 'seconds', 'print', 'held_by', 'notes',
            'quote', 'operator_file', 'operator_inks', 'operator_match', 'loomlab_match', 'error', 'job_id']
    with path.open('w', newline='', encoding='utf-8-sig') as f:   # -sig: Excel on Windows reads it right
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([', '.join(r[c]) if isinstance(r.get(c), list) else r.get(c, '') for c in cols])


def render_html(summary: dict, rows: list[dict], folder: Path, width_in, meters) -> str:
    e = html.escape
    s = summary
    cards = [('Print-ready untouched', f"{s['auto_ok']} / {s['designs']}", f"{s['auto_ok_percent']}%"),
             ('Time per design', f"{s['seconds_median']} s", f"mean {s['seconds_mean']} s"),
             ('Match with original', f"{s['accuracy_mean']}%", f"{s['inks_mean']} inks on average")]
    if s['compared_with_operator']:
        cards.append(('LoomLab vs operator', f"{s['loomlab_match_mean']}% vs {s['operator_match_mean']}%",
                      f"as good or better on {s['loomlab_as_good']} of {s['compared_with_operator']}"))
    from .auto import TITLES
    held = ''.join(f'<tr><td>{e(TITLES.get(k, k))}</td><td>{v}</td></tr>' for k, v in s['held_by'].items()) \
        or '<tr><td colspan=2>nothing held</td></tr>'
    body = []
    for r in rows:
        if r['status'] == 'error':
            body.append(f"<tr class=err><td>{e(r['design'])}</td><td>error</td><td colspan=7>{e(r['error'])}</td></tr>")
            continue
        op = (f"{r['operator_match']}% ({r['operator_inks']} inks)" if 'operator_match' in r else '')
        quote = '' if r['quote'] is None else '₹{:,.0f}'.format(r['quote'])
        body.append(
            f"<tr class={'ok' if r['status'] == 'auto_ok' else 'held'}><td>{e(r['design'])}</td>"
            f"<td>{'auto OK' if r['status'] == 'auto_ok' else 'needs review'}</td><td>{r['inks']}</td>"
            f"<td>{r['accuracy']}%</td><td>{r['seconds']} s</td><td>{e(r['print'])}</td>"
            f"<td>{e(', '.join(TITLES.get(c, c) for c in r['held_by']))}</td><td>{op}</td>"
            f"<td>{quote}</td></tr>")
    setting = f"print width {width_in:g} in" if width_in else 'each design at its own size'
    if meters:
        setting += f', quoted for {meters:g} m'
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>LoomLab benchmark</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:24px;color:#1e1e1e;background:#fafaf7}}
h1{{margin:0 0 4px}} .sub{{color:#666;margin-bottom:18px}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:22px}}
.card{{background:#fff;border:1px solid #ddd;border-radius:8px;padding:12px 16px;min-width:200px}}
.card b{{display:block;font-size:24px;margin:4px 0}} .card small{{color:#666}}
table{{border-collapse:collapse;background:#fff;width:100%;margin-bottom:22px}}
th,td{{border-bottom:1px solid #e5e5e5;padding:6px 10px;text-align:left;font-size:14px}}
th{{background:#f0efe9}} tr.ok td:nth-child(2){{color:#2f7a2a;font-weight:600}}
tr.held td:nth-child(2){{color:#b36b00;font-weight:600}} tr.err td{{color:#b00020}}
</style></head><body>
<h1>LoomLab benchmark</h1>
<div class=sub>{e(str(folder))} · {s['designs']} designs · {e(setting)} · {datetime.now():%d %b %Y %H:%M}</div>
<div class=cards>{''.join(f'<div class=card>{e(t)}<b>{e(v)}</b><small>{e(n)}</small></div>' for t, v, n in cards)}</div>
<h3>What held designs back</h3><table><tr><th>reason</th><th>designs</th></tr>{held}</table>
<h3>Every design</h3><table><tr><th>design</th><th>result</th><th>inks</th><th>match</th><th>time</th>
<th>print</th><th>held by</th><th>operator</th><th>quote</th></tr>{''.join(body)}</table>
</body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='python -m app.benchmark', description=__doc__.split('\n\n')[0])
    ap.add_argument('folder', type=Path)
    ap.add_argument('--width-in', type=float, default=None, help='print width in inches (default: own size)')
    ap.add_argument('--dpi', type=int, default=300)
    ap.add_argument('--meters', type=float, default=None, help='also quote a run of this many meters')
    ap.add_argument('--out', type=Path, default=None)
    ap.add_argument('--open', action='store_true', help='open the report in the browser when done')
    a = ap.parse_args(argv)
    if not a.folder.is_dir():
        print(f'{a.folder} is not a folder')
        return 2
    result = run(a.folder, a.width_in, a.dpi, a.meters, a.out)
    if a.open:
        import webbrowser
        webbrowser.open((Path(result['out']) / 'report.html').resolve().as_uri())
    return 0


if __name__ == '__main__':
    sys.exit(main())
