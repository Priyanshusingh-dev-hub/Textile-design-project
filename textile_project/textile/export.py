"""Everything a finished design is sent out as, from one index map + palette:

  NAME_final_<S>px_<DPI>dpi.tif   the mill's file (LZW, DPI written in)
  NAME_final_<S>px_<DPI>dpi.png   to look at and share
  NAME_colored_channels_*.zip     one RGBA layer per colour, transparent around
  NAME_bw_separations_*.zip       1-bit black & white separations
  NAME_channels_preview.png       every channel on one sheet
  NAME_report.json                sizes, colours, coverage, checks

This is method1_colorfill.py's output step, moved here unchanged, so every
command writes the same files the same way. Channels are numbered by
coverage, biggest first, and named channel_01_olive_ground_4A5B24.png:
colour name, role (ground / outline / motif, see names.py), hex; no '#'.
"""
from __future__ import annotations

import json
import os
import zipfile

import numpy as np
from PIL import Image, ImageDraw

from .io_utils import hex_of, inches, png_bytes, safe_name, save_png, save_tif, to_image
from .names import colour_name, roles as colour_roles


def size_tag(w, h):
    """'3535px' for a square design (as method1 names it), else '3535x1768px'."""
    return f'{w}px' if w == h else f'{w}x{h}px'


def paths(out_dir, name, w, h, dpi):
    tag = f'{size_tag(w, h)}_{dpi}dpi'
    j = lambda f: os.path.join(out_dir, f)
    return {'png': j(f'{name}_final_{tag}.png'), 'tif': j(f'{name}_final_{tag}.tif'),
            'channels_zip': j(f'{name}_colored_channels_{tag}.zip'),
            'bw_zip': j(f'{name}_bw_separations_{tag}.zip'),
            'preview': j(f'{name}_channels_preview.png'), 'report': j(f'{name}_report.json')}


def channel_file(i, rgb, role):
    return f'channel_{i:02d}_{colour_name(rgb)}_{role}_{hex_of(rgb)}.png'


def export_package(index, pal, out_dir, name, dpi=300, line_index=None):
    """Write every output for the design `pal[index]`. Returns
    {'paths', 'channels', 'size_px', 'dpi'}. `line_index` is the palette entry
    of the line art's colour (its channel is named 'outline'). Nothing is checked here (that is
    verify.py's job, on the files as written)."""
    name = safe_name(name)
    os.makedirs(out_dir, exist_ok=True)
    H, W = index.shape
    K = len(pal)
    p = paths(out_dir, name, W, H, dpi)

    rgb = to_image(pal[index])
    save_png(rgb, p['png'], dpi)
    save_tif(rgb, p['tif'], dpi)

    cnt = np.bincount(index.ravel(), minlength=K)
    order = [k for k in np.argsort(-cnt) if cnt[k] > 0]
    role = colour_roles(cnt, line_index)
    thumb = (500, 500) if W == H else (500, max(1, round(500 * H / W)))
    thumbs, channels = [], []
    with zipfile.ZipFile(p['channels_zip'], 'w', zipfile.ZIP_DEFLATED) as zc, \
         zipfile.ZipFile(p['bw_zip'], 'w', zipfile.ZIP_DEFLATED) as zb:
        for i, k in enumerate(order, 1):
            r, g, b = (int(v) for v in pal[k])
            hx = hex_of(pal[k])                     # file name me '#' nahi
            m = index == k
            rgba = np.zeros((H, W, 4), np.uint8)
            rgba[m] = (r, g, b, 255)
            fn = channel_file(i, pal[k], role[k])
            zc.writestr(fn, png_bytes(to_image(rgba), dpi))
            zb.writestr(fn, png_bytes(to_image(np.where(m, 0, 255).astype(np.uint8)).convert('1'), dpi))
            share = cnt[k] / index.size * 100
            channels.append({'channel': i, 'hex': hx, 'name': colour_name(pal[k]), 'role': role[k],
                             'coverage_percent': round(share, 2)})
            th = np.full((H, W, 3), 255, np.uint8)
            th[m] = (r, g, b)
            thumbs.append((to_image(th).resize(thumb, Image.NEAREST), f'{fn}  {share:.2f}%'))

    _preview_sheet(thumbs, thumb, p['preview'])
    return {'paths': p, 'channels': channels, 'size_px': [W, H], 'dpi': dpi,
            'print_size_inch': inches(W, dpi) if W == H else [inches(W, dpi), inches(H, dpi)]}


def _preview_sheet(thumbs, thumb, path):
    cols = 3
    rows = (len(thumbs) + cols - 1) // cols
    tw, th = thumb
    sheet = Image.new('RGB', (cols * (tw + 40), rows * (th + 70)), 'white')
    d = ImageDraw.Draw(sheet)
    for j, (t, label) in enumerate(thumbs):
        x, y = (j % cols) * (tw + 40) + 20, (j // cols) * (th + 70) + 20
        sheet.paste(t, (x, y))
        d.rectangle([x, y, x + tw - 1, y + th - 1], outline='gray')
        d.text((x, y + th + 8), label, fill='black')
    sheet.save(path)


def compare_sheet(reference, final_rgb, path, label=('reference', 'output')):
    """Reference and result side by side (NEAREST, 1200 px wide each), to look
    at, never to print."""
    h = reference.shape[0]
    out = to_image(final_rgb).resize((reference.shape[1], h), Image.NEAREST)
    sheet = Image.new('RGB', (reference.shape[1] * 2 + 30, h + 40), 'white')
    sheet.paste(to_image(reference), (10, 30))
    sheet.paste(out, (reference.shape[1] + 20, 30))
    d = ImageDraw.Draw(sheet)
    d.text((10, 8), label[0], fill='black')
    d.text((reference.shape[1] + 20, 8), label[1], fill='black')
    sheet.save(path)


def write_report(path, report):
    with open(path, 'w') as f:
        json.dump(report, f, indent=2)
