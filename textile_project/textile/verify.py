"""Checks on the files as written to disk (what the mill will get), not on
the arrays they were made from:

  colors_in_final == number of channels
  channels_overlap_equals_final: the colour layers, stacked, rebuild the
      final pixel for pixel, and no pixel is in two layers or in none
  bw separations agree with the colour layers
  size_px and tif_dpi as asked

Plus `seam_check` for a repeat tile (left edge meets right, top meets bottom).
`summary_hinglish` turns a report into the short lines the user reads.
"""
from __future__ import annotations

import io
import zipfile

import numpy as np
from PIL import Image

from . import palette as pl
from .io_utils import inches


def _layers(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        for n in sorted(z.namelist()):
            with Image.open(io.BytesIO(z.read(n))) as im:
                im.load()
                yield n, im.copy(), im.info.get('dpi')


def verify_package(paths, size_px, dpi):
    """Read every output back and check it. Returns a dict of the checks
    with 'passed' and 'problems' (empty when all is well)."""
    problems = []
    with Image.open(paths['png']) as im:
        final = np.asarray(im.convert('RGB'))
    colors = Image.fromarray(final).getcolors(maxcolors=1 << 16) or []
    with Image.open(paths['tif']) as tif:
        tif_px = np.asarray(tif.convert('RGB'))
        tif_dpi = [round(float(v)) for v in tif.info.get('dpi', (0, 0))]
        tif_lzw = tif.info.get('compression') == 'tiff_lzw'
    H, W = final.shape[:2]

    recon = np.zeros_like(final)
    cover = np.zeros((H, W), np.uint8)
    names, layer_dpi_ok = [], True
    for n, im, ldpi in _layers(paths['channels_zip']):
        names.append(n)
        a = np.asarray(im.convert('RGBA'))
        if a.shape[:2] != (H, W):
            problems.append(f'{n}: size {a.shape[1]}x{a.shape[0]}, final {W}x{H}')
            continue
        on = a[..., 3] > 0
        cover += on
        recon[on] = a[..., :3][on]
        if not ldpi or round(float(ldpi[0])) != dpi:
            layer_dpi_ok = False
    overlap_ok = bool((cover == 1).all() and (recon == final).all())

    bw_ok = True
    with zipfile.ZipFile(paths['channels_zip']) as zc, zipfile.ZipFile(paths['bw_zip']) as zb:
        if sorted(zc.namelist()) != sorted(zb.namelist()):
            bw_ok = False
        else:
            for n in zc.namelist():
                with Image.open(io.BytesIO(zc.read(n))) as c, Image.open(io.BytesIO(zb.read(n))) as b:
                    if not np.array_equal(np.asarray(c.convert('RGBA'))[..., 3] > 0, np.asarray(b.convert('L')) < 128):
                        bw_ok = False
                        break

    checks = {
        'size_px': [W, H],
        'colors_in_final': len(colors),
        'channels': len(names),
        'channels_overlap_equals_final': overlap_ok,
        'bw_matches_channels': bw_ok,
        'tif_dpi': tif_dpi,
        'tif_lzw': tif_lzw,
        'tif_equals_png': bool(np.array_equal(tif_px, final)),
        'no_hash_in_names': all('#' not in n for n in names),
    }
    if [W, H] != list(size_px):
        problems.append(f'size {W}x{H}, chahiye tha {size_px[0]}x{size_px[1]}')
    if len(colors) != len(names):
        problems.append(f'final me {len(colors)} rang, channels {len(names)}')
    if not overlap_ok:
        problems.append('channels mila kar final nahi banta (overlap ya gap)')
    if not bw_ok:
        problems.append('B/W separations colour channels se nahi milte')
    if tif_dpi != [dpi, dpi]:
        problems.append(f'TIFF ka DPI {tif_dpi}, chahiye {dpi}')
    if not layer_dpi_ok:
        problems.append(f'kisi channel me {dpi} DPI likha nahi hai')
    if not tif_lzw:
        problems.append('TIFF LZW me nahi hai')
    if not checks['tif_equals_png']:
        problems.append('TIFF aur PNG alag hain')
    if not checks['no_hash_in_names']:
        problems.append("file naam me '#' hai")
    checks['problems'] = problems
    checks['passed'] = not problems
    return checks


def coverage_diff(ref_rgb, index, pal):
    """How far the fill's colour shares are from the reference's, in
    percentage points (half the sum of the differences, 0-100): each
    reference pixel counted as its nearest palette colour."""
    ref = pl.coverage(pl.map_to_palette(ref_rgb, pal), len(pal)) / (ref_rgb.shape[0] * ref_rgb.shape[1])
    out = pl.coverage(index, len(pal)) / index.size
    return float(np.abs(ref - out).sum() / 2 * 100)


def seam_check(rgb, factor=3.0):
    """Does a tile repeat without a visible join? The colour jump across the
    wrap (last column to first, last row to first) against the jumps between
    neighbouring columns/rows inside. Seamless when the wrap is no worse than
    `factor` x the inside's 99th percentile (+1)."""
    a = np.asarray(rgb, np.int16)
    out = {}
    for name, axis in (('left_right', 1), ('top_bottom', 0)):
        inside = np.abs(np.diff(a, axis=axis)).mean(axis=tuple(i for i in range(3) if i != axis))
        wrap = float(np.abs(a.take([-1], axis) - a.take([0], axis)).mean())
        limit = float(np.percentile(inside, 99)) * factor + 1
        out[name] = {'wrap': round(wrap, 2), 'inside_p99': round(float(np.percentile(inside, 99)), 2),
                     'seamless': wrap <= limit}
    out['seamless'] = out['left_right']['seamless'] and out['top_bottom']['seamless']
    return out


def summary_hinglish(report):
    """The short report the user reads after every command."""
    w, h = report['size_px']
    dpi = report['dpi']
    lines = [f"Size: {w} x {h} px = {inches(w, dpi)} x {inches(h, dpi)} inch @ {dpi} DPI"]
    ch = report.get('channels', [])
    lines.append(f"Rang (channels): {len(ch)}")
    lines += [f"  {c['channel']:02d}. {c['hex']}  {c['coverage_percent']}%"
              + (f"  ({c['name']}, {c['role']})" if c.get('name') else '') for c in ch]
    for m in report.get('stray_merged', []):
        lines.append(f"  (chhota rang {m['hex']}, {m['pixels']} px -> {m['into']} me mila diya)")
    if 'alignment_score' in report:
        s = report['alignment_score']
        lines.append(f"Method {report.get('method', 1)} | alignment {s:.2f} "
                     + ('(achha)' if s >= 0.85 else '(kam hai: preview dhyan se dekho)' if s >= 0.55 else '(fail)'))
        if report.get('doubtful_regions'):
            lines.append(f"Doubtful regions: {report['doubtful_regions']} -> {report['design']}_DEBUG_doubtful_regions.png "
                         'dekho (laal hisson me rang galat ho sakta hai, aksar tooti line)')
    if report.get('method') == 3:
        lines.append(f"Method 3 | reference khiska kar bitha: alignment {report['alignment_before']:.2f} -> "
                     f"{report['alignment_score']:.2f} (shift {report['max_shift_px']} px tak)")
    a = report.get('auto')
    if a:
        m = a['method1']
        if a['chosen'] == 1:
            lines.append(f"Auto: Method 1 theek (alignment {m['alignment_score']:.2f}, rangon ka farak "
                         f"{m['coverage_diff']} points)")
        else:
            lines.append(f"Auto: Method 1 nahi chala ({'; '.join(a['why'])}) -> Method {a['chosen']}, "
                         f"ab rangon ka farak {a['coverage_diff']} points")
        if a.get('only_two'):
            lines.append('  Method 2 sirf 2 rang deta hai (ground + motif). Reference me aur rang hain (laal, grey...) to: '
                         'reference ko hi LoomLab me "Ek design" se reduce karo (saare rang bachte hain), '
                         'ya line art aur reference ek hi tasveer se banwao.')
        if a['coverage_diff'] > a.get('limit', 6):
            lines.append('  Rang ka hissa abhi bhi reference se kaafi alag hai: compare.png dhyan se dekho.')
    if report.get('method') == 2:
        lines.append(f"Method 2 | ground {report['ground_hex']}, motif {report['motif_hex']} | "
                     f"regions {report['regions']}, reference se ground seeds {report['ground_seeds']}"
                     + (f", {report['unreached']} regions kisi se nahi jude (motif maane)" if report['unreached'] else ''))
    v = report.get('verify', {})
    if v:
        if v.get('passed'):
            lines.append(f"Verify: PASS (rang {v['colors_in_final']} = channels {v['channels']}, "
                         f"channels mila kar final same, TIFF {v['tif_dpi'][0]} DPI LZW)")
        else:
            lines.append('Verify: FAIL - ' + '; '.join(v.get('problems', [])) + ' -> ye file mill ko mat bhejna')
    if 'seam' in report:
        lines.append('Repeat seam: ' + ('saaf (seamless)' if report['seam']['seamless'] else 'jod dikhega'))
    return '\n'.join(lines)
