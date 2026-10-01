"""textile: one command for the mill's design work (ROADMAP Phase 1).

  python -m textile export  design.png --out out/ --name design01
  python -m textile verify  out/ --name design01
  python -m textile palette design.png

Defaults: --size 3535 (px, the width; a square design is 3535 x 3535),
--dpi 300 (the mill's format). Every command ends with a short report.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import cv2
import numpy as np

from . import export as ex
from . import palette as pl
from .io_utils import inches, load_rgb, safe_name
from .verify import summary_hinglish, verify_package

SIZE, DPI = 3535, 300


def _target(w, h, size):
    """(width, height) for --size: the width is `size`, the height keeps the
    design's proportions (a square stays square)."""
    return size, max(1, round(size * h / w))


def _resize_index(index, size):
    h, w = index.shape
    tw, th = _target(w, h, size)
    if (tw, th) == (w, h):
        return index
    # an index map is only ever resized NEAREST: no new, mixed colours
    return cv2.resize(index, (tw, th), interpolation=cv2.INTER_NEAREST)


def cmd_export(a):
    rgb = load_rgb(a.image)
    min_share = 0.0 if a.keep_strays else a.min_share
    pal, is_flat = pl.extract_palette(rgb, a.max_colors, min_share, log=_log)
    index = pl.map_to_palette(rgb, pal)
    # a flat image's colours under min_share are left out of its palette and
    # their pixels go to the nearest kept colour: say which, like merge_stray does
    merged = pl.dropped_colours(rgb, pal) if is_flat else []
    if not a.keep_strays:
        index, pal, more = pl.merge_stray(index, pal, a.min_share)
        merged += more
    index = _resize_index(index, a.size)
    name = safe_name(a.name or os.path.splitext(os.path.basename(a.image))[0])
    done = ex.export_package(index, pal, a.out, name, a.dpi)
    v = verify_package(done['paths'], done['size_px'], a.dpi)
    report = {'design': name, 'size_px': done['size_px'], 'dpi': a.dpi,
              'print_size_inch': done['print_size_inch'], 'source': os.path.basename(a.image),
              'source_was_flat': bool(is_flat), 'colors_in_final': v['colors_in_final'],
              'channels': done['channels'], 'stray_merged': merged, 'verify': v}
    ex.write_report(done['paths']['report'], report)
    print('\n' + summary_hinglish(report))
    print(f"Files: {a.out}  (mill ko: {os.path.basename(done['paths']['tif'])})")
    return 0 if v['passed'] else 1


def cmd_verify(a):
    name = safe_name(a.name) if a.name else None
    tifs = glob.glob(os.path.join(a.folder, f"{name or '*'}_final_*dpi.tif"))
    if len(tifs) != 1:
        print(f"[ERROR] {a.folder} me ek hi *_final_*.tif chahiye, mile {len(tifs)}. --name do.")
        return 2
    tif = os.path.basename(tifs[0])
    name = tif.split('_final_')[0]
    tag = tif.split('_final_')[1][:-4]                 # e.g. 3535px_300dpi
    dpi = int(tag.rsplit('_', 1)[1][:-3])
    p = ex.paths(a.folder, name, 1, 1, dpi)            # name/report paths; files by tag below
    for k, suffix in (('png', f'_final_{tag}.png'), ('tif', f'_final_{tag}.tif'),
                      ('channels_zip', f'_colored_channels_{tag}.zip'), ('bw_zip', f'_bw_separations_{tag}.zip')):
        p[k] = os.path.join(a.folder, name + suffix)
    missing = [os.path.basename(p[k]) for k in ('png', 'tif', 'channels_zip', 'bw_zip') if not os.path.exists(p[k])]
    if missing:
        print('[ERROR] ye files nahi mili: ' + ', '.join(missing))
        return 2
    from PIL import Image
    with Image.open(p['png']) as im:
        size = list(im.size)
    v = verify_package(p, size, dpi)
    cnt = []
    import zipfile
    with zipfile.ZipFile(p['channels_zip']) as z:
        for i, n in enumerate(sorted(z.namelist()), 1):
            with Image.open(z.open(n)) as im:
                share = (np.asarray(im.convert('RGBA'))[..., 3] > 0).mean() * 100
            cnt.append({'channel': i, 'hex': n.rsplit('_', 1)[-1][:-4], 'coverage_percent': round(share, 2)})
    report = {'size_px': size, 'dpi': dpi, 'channels': cnt, 'verify': v}
    print(summary_hinglish(report))
    return 0 if v['passed'] else 1


def cmd_palette(a):
    rgb = load_rgb(a.image)
    pal, is_flat = pl.extract_palette(rgb, a.max_colors, a.min_share, log=_log)
    index = pl.map_to_palette(rgb, pal)
    cnt = pl.coverage(index, len(pal))
    h, w = index.shape
    print(f"Image: {w} x {h} px ({'flat' if is_flat else 'flat nahi, k-means'})")
    for k in np.argsort(-cnt):
        share = cnt[k] / index.size * 100
        tag = '  <- chhota (stray), merge hoga' if cnt[k] / index.size < a.min_share else ''
        print(f"  {pl._hex(pal[k])}  {share:.2f}%{tag}")
    _, pal2, merged = pl.merge_stray(index, pal, a.min_share)
    print(f"Merge ke baad: {len(pal2)} channels" + (f" ({len(merged)} chhote rang mile)" if merged else ''))
    print(f"{a.size} px par: {inches(a.size, a.dpi)} inch @ {a.dpi} DPI")
    return 0


def _log(msg):
    print(msg, flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='textile', description='Mill ke designs: export, verify, palette')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p, out=True):
        p.add_argument('--size', type=int, default=SIZE, help=f'Output width px (default {SIZE})')
        p.add_argument('--dpi', type=int, default=DPI, help=f'Default {DPI} (mill format)')
        if out:
            p.add_argument('--out', required=True, help='Output folder')
            p.add_argument('--name', default=None, help="File prefix (default: image ka naam; '#' hata diya jaata hai)")
        p.add_argument('--max-colors', type=int, default=16, help='Non-flat image ke liye k-means colors')
        p.add_argument('--min-share', type=float, default=pl.STRAY_SHARE,
                       help='Isse kam share wala rang stray (default 0.0005 = 0.05%%)')

    e = sub.add_parser('export', help='Flat design -> TIF/PNG, channels, B/W seps, preview, report')
    e.add_argument('image')
    common(e)
    e.add_argument('--keep-strays', action='store_true', help='Chhote rang merge mat karo')
    e.set_defaults(fn=cmd_export)

    v = sub.add_parser('verify', help='Ek output folder ki files dobara check karo')
    v.add_argument('folder')
    v.add_argument('--name', default=None)
    v.set_defaults(fn=cmd_verify)

    p = sub.add_parser('palette', help='Image ke rang aur coverage dikhao')
    p.add_argument('image')
    common(p, out=False)
    p.set_defaults(fn=cmd_palette)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == '__main__':
    sys.exit(main())
