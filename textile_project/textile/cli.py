"""textile: one command for the mill's design work (ROADMAP Phase 1).

  python -m textile export  design.png --out out/ --name design01
  python -m textile verify  out/ --name design01
  python -m textile palette design.png
  python -m textile paint   sketch.png --out out/ [--colors "A=cream, B=laal, lines=coffee"]

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
from . import edges as ed
from . import fill_auto as fa
from . import fill_method1 as m1
from . import fill_method2 as m2
from . import fill_method3 as m3
from . import fill_method4 as m4
from . import paint as pt
from . import palette as pl
from . import make as mk
from . import repeat as rp
from . import tile as tl
from .io_utils import hex_of, inches, load_rgb, read_cv2, rgb_of, safe_name
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
    line_index = None
    if a.line_color:
        line_index = int(((pal.astype(int) - rgb_of(a.line_color).astype(int)) ** 2).sum(1).argmin())
    done = ex.export_package(index, pal, a.out, name, a.dpi, line_index=line_index)
    v = verify_package(done['paths'], done['size_px'], a.dpi)
    report = {'design': name, 'size_px': done['size_px'], 'dpi': a.dpi,
              'print_size_inch': done['print_size_inch'], 'source': os.path.basename(a.image),
              'source_was_flat': bool(is_flat), 'colors_in_final': v['colors_in_final'],
              'channels': done['channels'], 'stray_merged': merged, 'verify': v}
    ex.write_report(done['paths']['report'], report)
    print('\n' + summary_hinglish(report))
    print(f"Files: {a.out}  (mill ko: {os.path.basename(done['paths']['tif'])})")
    return 0 if v['passed'] else 1


def cmd_fill(a):
    if a.method == 'auto':
        return _fill_auto(a)
    if a.method == '2':
        return _fill_method2(a)
    try:
        if a.method == '3':
            f = m3.fill(a.line, a.ref, a.size, a.max_colors, a.min_share, a.line_threshold, a.line_color,
                        a.reach_align, log=_log)
        elif a.method == '4':
            f = m4.fill(a.line, a.ref, a.size, a.max_colors, a.min_share, a.line_threshold, a.line_color,
                        a.seal, a.min_align, a.force, log=_log)
        else:
            f = m1.fill(a.line, a.ref, a.size, a.max_colors, a.min_share, a.line_threshold, a.line_color,
                        a.min_align, a.force, log=_log)
    except m1.FillError as e:
        print(f'STOP: {e}')
        return 1
    return _export_fill(a, f, int(a.method), *fa.merged(f, a.min_share, a.keep_strays))


def _export_fill(a, f, method, index, pal, merged, line_index, auto=None, more=()):
    """Write and verify a Method 1 or 3 fill (`auto`: what auto mode measured)."""
    name = safe_name(a.name or os.path.splitext(os.path.basename(a.line))[0])
    os.makedirs(a.out, exist_ok=True)
    if f.debug is not None:
        from PIL import Image
        Image.fromarray(f.debug).save(os.path.join(a.out, f'{name}_DEBUG_doubtful_regions.png'))
    done = ex.export_package(index, pal, a.out, name, a.dpi, line_index=line_index)
    label = {1: 'textile fill (method 1)', 3: 'textile fill (method 3: reference khiska kar)',
             4: 'textile fill (method 4: line art ke gap band)'}[method]
    ex.compare_sheet(f.reference, pal[index], os.path.join(a.out, f'{name}_compare.png'),
                     ('reference', label), more)
    v = verify_package(done['paths'], done['size_px'], a.dpi)
    report = {'design': name, 'method': method, 'size_px': done['size_px'], 'dpi': a.dpi,
              'print_size_inch': done['print_size_inch'], 'reference_was_flat': f.reference_was_flat,
              'colors_in_final': v['colors_in_final'], 'channels': done['channels'],
              'line_color_hex': hex_of(pal[line_index]), 'alignment_score': round(f.alignment_score, 3),
              'regions': f.regions, 'doubtful_regions': len(f.doubtful), 'stray_merged': merged, 'verify': v}
    if method == 3:
        report['alignment_before'] = round(f.alignment_before, 3)
        report['max_shift_px'] = f.max_shift_px
    if auto:
        report['auto'] = auto
    ex.write_report(done['paths']['report'], report)
    print('\n' + summary_hinglish(report))
    print(f"Files: {a.out}  (mill ko: {os.path.basename(done['paths']['tif'])})")
    return 0 if v['passed'] else 1


def _fill_auto(a):
    """Method 1, judged; then Method 3 or 2 (see fill_auto.choose)."""
    m2_args = _m2_args(a)
    if m2_args is None:
        return 1
    try:
        c = fa.choose(a.line, a.ref, a.size, a.max_colors, a.min_share, a.line_threshold, a.line_color, a.min_align,
                      a.max_cover_diff, a.reach_align, a.keep_strays, m2_args, log=_log)
    except (m1.FillError, ValueError) as e:
        print(f'STOP: {e}')
        return 1
    if c.method == 2:
        return _export_method2(a, c.fill, c.auto, c.others)
    return _export_fill(a, c.fill, c.method, c.index, c.pal, c.merged, c.line_index, c.auto, c.others)


def _m2_args(a):
    """Method 2's settings from the command line (None: --colors is wrong)."""
    colors = [c.strip() for c in a.colors.split(',')] if a.colors else None
    if colors and len(colors) != 2:
        print('STOP: --colors me do rang do: ground,motif (jaise 10100F,E8DFD2)')
        return None
    return dict(reach=a.reach, dark_level=a.dark_level, seed_area=a.seed_area, seed_dark=a.seed_dark,
                side_band=a.side_band, side_area=a.side_area, side_dark=a.side_dark, colors=colors)


def _fill_method2(a):
    m2_args = _m2_args(a)
    if m2_args is None:
        return 1
    try:
        f = m2.fill(a.line, a.ref, a.size, a.line_threshold, log=_log, **m2_args)
    except (m1.FillError, ValueError) as e:
        print(f'STOP: {e}')
        return 1
    return _export_method2(a, f)


def _export_method2(a, f, auto=None, more=()):
    name = safe_name(a.name or os.path.splitext(os.path.basename(a.line))[0])
    os.makedirs(a.out, exist_ok=True)
    done = ex.export_package(f.index, f.pal, a.out, name, a.dpi)
    ex.compare_sheet(f.reference, f.pal[f.index], os.path.join(a.out, f'{name}_compare.png'),
                     ('reference (sirf rang)', 'textile fill (method 2: line art ki shapes)'), more)
    v = verify_package(done['paths'], done['size_px'], a.dpi)
    report = {'design': name, 'method': 2, 'size_px': done['size_px'], 'dpi': a.dpi,
              'print_size_inch': done['print_size_inch'], 'colors_in_final': v['colors_in_final'],
              'channels': done['channels'], 'ground_hex': hex_of(f.pal[0]), 'motif_hex': hex_of(f.pal[1]),
              'regions': f.regions, 'ground_seeds': f.seeds, 'unreached': f.unreached,
              'depth_hist': f.depth_hist, 'verify': v}
    if auto:
        report['auto'] = auto
    ex.write_report(done['paths']['report'], report)
    print('\n' + summary_hinglish(report))
    print(f"Files: {a.out}  (mill ko: {os.path.basename(done['paths']['tif'])})")
    return 0 if v['passed'] else 1


def cmd_repeat(a):
    r = rp.analyze(a.image)
    print(rp.summary_hinglish(r))
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        name = safe_name(a.name or os.path.splitext(os.path.basename(a.image))[0])
        ex.write_report(os.path.join(a.out, f'{name}_repeat.json'), r)
        print(f"JSON: {os.path.join(a.out, f'{name}_repeat.json')}")
    return 0


def _range(text, centre):
    """'496:514' -> range(496, 514, 4); default the centre +-8 px, step 4."""
    if text:
        lo, hi = (int(v) for v in text.split(':'))
        return range(lo, hi, 4)
    c = int(round(centre))
    return range(c - 8, c + 9, 4)


def cmd_tile(a):
    """Repeat analysis first (always), then the seamless block."""
    from PIL import Image
    name = safe_name(a.name or os.path.splitext(os.path.basename(a.image))[0])
    os.makedirs(a.out, exist_ok=True)
    r = rp.analyze(a.image)
    print(rp.summary_hinglish(r) + '\n')
    ex.write_report(os.path.join(a.out, f'{name}_repeat.json'), r)
    if r['type'] not in ('straight', 'half-drop'):
        print('STOP: is design me all-over repeat (aar-paar + upar-neeche) nahi mila, isliye tile nahi kaata. '
              + ('Panel print hai: mill ko "panel print, straight vertical repeat" bolo.' if r['type'] == 'panel' else ''))
        return 1
    s = a.shear_ratio if a.shear_ratio is not None else (r['shear'] / r['H'] if abs(r['shear']) > 5 else 0.0)
    bgr = read_cv2(a.image, cv2.IMREAD_COLOR)
    ds, valid = tl.deshear(bgr, s)
    if s:
        _log(f'[tile] deshear: har {r["H"]:.0f} px par {s * r["H"]:.1f} px seedha kiya')
    try:
        t, cost, (mse, W, H, x0, y0) = tl.extract(ds, valid, _range(a.w_range, r['W']), _range(a.h_range, r['H']),
                                                 log=_log)
    except ValueError as e:
        print(f'STOP: {e}')
        return 1
    block = cv2.cvtColor(np.clip(t, 0, 255).astype(np.uint8), cv2.COLOR_BGR2RGB)
    Image.fromarray(block).save(os.path.join(a.out, f'{name}_tile_native_{W}x{H}px.png'))
    from .verify import seam_check
    native_seam = seam_check(block)
    ground = None
    if a.clean_ground:
        block, g, share = tl.clean_ground(block, a.clean_ground)
        ground = {'hex': hex_of(g), 'share_percent': round(share * 100, 1)}
        _log(f'[tile] ground {hex_of(g)} saaf kiya ({share * 100:.1f}% pixels)')
    factor = a.size / W
    up = tl.upscale(block, a.size)
    report = {'design': name, 'source': os.path.basename(a.image), 'repeat': r,
              'block_source_px': [W, H], 'block_at': [x0, y0], 'deshear_ratio': round(s, 4),
              'seam_cost': round(float(cost), 1), 'upscale': round(factor, 2), 'clean_ground': ground,
              'native_seam': native_seam, 'dpi': a.dpi}
    if a.colors:
        pal, _ = pl.extract_palette(up, a.colors, a.min_share, log=_log)
        index = pl.map_to_palette(up, pal)
        index, pal, merged = pl.merge_stray(index, pal, a.min_share)
        done = ex.export_package(index, pal, a.out, name, a.dpi)
        v = verify_package(done['paths'], done['size_px'], a.dpi)
        final = pal[index]
        report.update({'size_px': done['size_px'], 'channels': done['channels'], 'stray_merged': merged,
                       'colors_in_final': v['colors_in_final'], 'verify': v})
        rpath, tif = done['paths']['report'], done['paths']['tif']
    else:
        final = up
        h, w = final.shape[:2]
        p = ex.paths(a.out, name, w, h, a.dpi)
        from .io_utils import save_png, save_tif, to_image
        save_png(to_image(final), p['png'], a.dpi)
        save_tif(to_image(final), p['tif'], a.dpi)
        report.update({'size_px': [w, h]})
        rpath, tif = p['report'], p['tif']
    report['seam'] = seam_check(final)
    report['print_size_inch'] = [inches(report['size_px'][0], a.dpi), inches(report['size_px'][1], a.dpi)]
    prev = Image.fromarray(tl.tiled(final))
    prev.thumbnail((1800, 1800), Image.LANCZOS)
    prev.save(os.path.join(a.out, f'{name}_3x3_preview.png'))
    ex.write_report(rpath, report)
    print('\n' + _tile_summary(report))
    print(f"Files: {a.out}  (mill ko: {os.path.basename(tif)})")
    return 0 if report['seam']['seamless'] and report.get('verify', {'passed': True})['passed'] else 1


def _tile_summary(r):
    w, h = r['size_px']
    rep = r['repeat']
    lines = [f"Tile: source me {r['block_source_px'][0]} x {r['block_source_px'][1]} px block "
             f"(jagah {r['block_at'][0]},{r['block_at'][1]}, seam cost {r['seam_cost']})",
             f"Size: {w} x {h} px = {r['print_size_inch'][0]} x {r['print_size_inch'][1]} inch @ {r['dpi']} DPI "
             f"({r['upscale']}x bada kiya)"]
    if r['upscale'] > 3:
        lines.append(f"  Source chhoti hai: {r['upscale']}x upscale soft lagega. Badi source image ho to wahi do.")
    if r['clean_ground']:
        lines.append(f"Ground {r['clean_ground']['hex']} pakka flat kiya ({r['clean_ground']['share_percent']}% pixels)")
    if 'channels' in r:
        lines.append(f"Rang (channels): {len(r['channels'])}")
        lines += [f"  {c['channel']:02d}. {c['hex']}  {c['coverage_percent']}%" for c in r['channels']]
        v = r['verify']
        lines.append('Verify: ' + ('PASS (channels mila kar final same, TIFF LZW)' if v['passed']
                                   else 'FAIL - ' + '; '.join(v['problems'])))
    else:
        lines.append('Rang: flat nahi kiye (photo jaisa tile). Channels chahiye to --colors N do.')
    lines.append('Repeat seam: ' + ('saaf (seamless)' if r['seam']['seamless'] else 'jod dikhega - 3x3 preview dekho'))
    if rep['type'] == 'half-drop':
        lines.append('Mill ko: is block ko STRAIGHT repeat me lagao (half-drop block ke andar hi bana hai).')
    else:
        lines.append('Mill ko: is block ko straight repeat me lagao.')
    return '\n'.join(lines)


def cmd_make(a):
    """An original design from a JSON config (see examples/)."""
    from PIL import Image
    from .verify import seam_check
    try:
        cfg = mk.load(a.config)
        index, pal, names = mk.make(cfg, log=_log)
    except (OSError, ValueError) as e:
        print(f'STOP: {e}')
        return 1
    name = safe_name(a.name or cfg.get('name') or os.path.splitext(os.path.basename(a.config))[0])
    dpi = int(cfg.get('dpi', 300))
    done = ex.export_package(index, pal, a.out, name, dpi)
    v = verify_package(done['paths'], done['size_px'], dpi)
    final = pal[index]
    seam = seam_check(final)
    panel = cfg.get('repeat', 'all-over') == 'panel'
    seamless = seam['top_bottom']['seamless'] if panel else seam['seamless']
    prev = Image.fromarray(np.tile(final, (3, 1, 1) if panel else (3, 3, 1)))
    prev.thumbnail((1800, 1800), Image.NEAREST)
    prev.save(os.path.join(a.out, f'{name}_repeat_preview.png'))
    report = {'design': name, 'size_px': done['size_px'], 'dpi': dpi, 'print_size_inch': done['print_size_inch'],
              'repeat': 'panel' if panel else 'all-over', 'config': cfg, 'colors_in_final': v['colors_in_final'],
              'channels': done['channels'], 'seam': seam, 'verify': v}
    ex.write_report(done['paths']['report'], report)
    print('\n' + summary_hinglish(report))
    print('Repeat: ' + ('panel (sirf upar-neeche): ' if panel else 'all-over: ')
          + ('jod saaf (seamless)' if seamless else 'JOD DIKHEGA - preview dekho'))
    print(f"Files: {a.out}  (mill ko: {os.path.basename(done['paths']['tif'])})")
    return 0 if v['passed'] and seamless else 1


def cmd_vector(a):
    """Trace a flat design's channels and draw them back without anti-aliasing."""
    from PIL import Image
    from . import vector as vc
    with Image.open(a.image) as im:
        rgb = np.asarray(im.convert('RGB'))
        dpi = round(float(im.info.get('dpi', (DPI, DPI))[0])) or DPI
    pal = np.unique(rgb.reshape(-1, 3), axis=0)
    if len(pal) > 64:
        print(f'STOP: is image me {len(pal)} rang hain - ye flat design nahi. Pehle fill/export/make se flat karo.')
        return 1
    index = pl.map_to_palette(rgb, pal).astype(np.uint8)
    pad = 32 if a.repeat else 0
    work = np.pad(index, pad, mode='wrap') if pad else index
    traced, svg, _ = vc.trace(work, pal, a.eps)
    if pad:
        traced = traced[pad:-pad, pad:-pad]
        _, svg, _ = vc.trace(index, pal, a.eps)          # the SVG of the tile itself
    changed = float((traced != index).mean())
    name = safe_name(a.name or os.path.splitext(os.path.basename(a.image))[0].split('_final_')[0] + '_vector')
    done = ex.export_package(traced, pal, a.out, name, dpi)
    with open(os.path.join(a.out, f'{name}.svg'), 'w') as f:
        f.write(svg)
    v = verify_package(done['paths'], done['size_px'], dpi)
    report = {'design': name, 'source': os.path.basename(a.image), 'size_px': done['size_px'], 'dpi': dpi,
              'print_size_inch': done['print_size_inch'], 'eps_px': a.eps, 'changed_percent': round(changed * 100, 2),
              'colors_in_final': v['colors_in_final'], 'channels': done['channels'], 'verify': v}
    if a.repeat:
        from .verify import seam_check
        report['seam'] = seam_check(pal[traced])
    ex.write_report(done['paths']['report'], report)
    print(summary_hinglish(report))
    print(f"Vector: kinare seedhe kiye (eps {a.eps} px = {a.eps * 25.4 / dpi:.2f} mm tak), "
          f"{changed * 100:.2f}% pixel badle. SVG: {name}.svg")
    print(f"Files: {a.out}  (mill ko: {os.path.basename(done['paths']['tif'])})")
    return 0 if v['passed'] and report.get('seam', {'seamless': True})['seamless'] else 1


def cmd_edges(a):
    """Clean edges: every ink's outline redrawn smooth and hard-edged, drawn at --size (default 3535 px)."""
    from PIL import Image
    with Image.open(a.image) as im:
        rgb = np.asarray(im.convert('RGB'))
    pal = np.unique(rgb.reshape(-1, 3), axis=0)
    if len(pal) > 64:
        print(f'STOP: is image me {len(pal)} rang hain - ye flat design nahi. Pehle fill/export/make se flat karo.')
        return 1
    index = pl.map_to_palette(rgb, pal).astype(np.uint8)
    wrap = (a.repeat in ('x', 'both'), a.repeat in ('y', 'both'))
    factor = a.size / index.shape[1]
    cleaned, rep = ed.clean(index, factor, a.strength, wrap, a.specks)
    used = np.unique(cleaned)                                  # an ink made only of crumbs is gone
    remap = np.zeros(len(pal), np.uint8)
    remap[used] = np.arange(len(used))
    cleaned, pal = remap[cleaned], pal[used]
    h, w = cleaned.shape
    # how much of the design moved: against the source drawn plain (nearest) at the same size
    plain = np.asarray(Image.fromarray(rgb).resize((w, h), Image.NEAREST))
    changed = float((pal[cleaned] != plain).any(-1).mean())
    name = safe_name(a.name or os.path.splitext(os.path.basename(a.image))[0].split('_final_')[0] + '_clean')
    done = ex.export_package(cleaned, pal, a.out, name, a.dpi)
    v = verify_package(done['paths'], done['size_px'], a.dpi)
    report = {'design': name, 'source': os.path.basename(a.image), 'size_px': done['size_px'], 'dpi': a.dpi,
              'print_size_inch': done['print_size_inch'], 'edges': rep, 'changed_percent': round(changed * 100, 2),
              'colors_in_final': v['colors_in_final'], 'channels': done['channels'], 'verify': v}
    if a.repeat != 'no':
        from .verify import seam_check
        report['seam'] = seam_check(pal[cleaned])
    ex.write_report(done['paths']['report'], report)
    print(summary_hinglish(report))
    print(f"Kinare saaf (strength {a.strength}): {rep['outlines_smoothed']} outline smooth, {rep['specks_moved']} chhote tukde "
          f"padosi rang me, {changed * 100:.2f}% pixel badle. Rang wahi {len(pal)}, naya koi nahi.")
    print(f"Files: {a.out}  (mill ko: {os.path.basename(done['paths']['tif'])})")
    return 0 if v['passed'] and report.get('seam', {'seamless': True})['seamless'] else 1


def cmd_paint(a):
    """A sketch coloured as the user says: step 1 (no --colors) the lettered map,
    step 2 the design, one channel per named colour."""
    from PIL import Image
    name = safe_name(a.name or os.path.splitext(os.path.basename(a.sketch))[0])
    if a.seal is None:                              # 'peony_seal10.png': the seal rides in the file name (Windows bat)
        import re
        m = re.search(r'seal[_-]?(\d+)', os.path.basename(a.sketch), re.I)
        if m:
            a.seal = int(m.group(1))
            print(f'[seal] file ke naam se: {a.seal} px')
    try:
        reg = pt.find_regions(a.sketch, a.size, a.line_threshold, a.seal, a.group_tolerance, log=_log)
    except m1.FillError as e:
        print(f'STOP: {e}')
        return 1
    os.makedirs(a.out, exist_ok=True)
    mp = pt.maps(reg, a.out, name)
    if not a.colors and pt.filled(mp['colors']):
        a.colors = [mp['colors']]                   # the map's own file, filled in: paint with it
        print(f"[colors] {os.path.basename(mp['colors'])} me rang likhe hain: unse rang bhar raha hoon")
    ref_text, ref_rgb = None, None
    if a.ref:
        try:
            ref_text, ref_rgb = pt.from_reference(reg, a.ref, a.ref_colors, a.out, name, log=_log)
        except m1.FillError as e:
            print(f'STOP: {e}')
            return 1
        print(f'[ref] {name}_ref_numbers.png = rangeen design par har hisse ka number; '
              f'{name}_ref_colors.csv = har number ka rang (badalna ho to --colors se sudhaar do)')
    if not a.colors and not a.ref:
        print(f"\nMap: {os.path.basename(mp['map'])} (group letters), {os.path.basename(mp['numbers'])} "
              f"(har hisse ka number), list: {os.path.basename(mp['groups'])}")
        print(f'{reg.n} band hisse, {len(reg.letters)} group. Ground (sabse bada) = {reg.letters[reg.ground]}.')
        print('Ab rang batao:  --colors "A=cream, B=laal, C D=hara, 12=gold, lines=coffee"')
        print(f"  ya {os.path.basename(mp['colors'])} me likh kar:  --colors {mp['colors']}")
        return 0
    parts = [ref_text] if ref_text else []
    for c in (a.colors or []) if isinstance(a.colors, list) or a.colors is None else [a.colors]:   # later wins
        if os.path.isfile(c) and c.lower().endswith('.csv'):
            try:
                c = pt.csv_colours(c)
            except (m1.FillError, ValueError) as e:
                print(f'STOP: {e}')
                return 1
        elif os.path.isfile(c):
            with open(c, encoding='utf-8') as fh:
                c = fh.read()
        parts.append(c)
    text = '\n'.join(parts)
    old = pt.stamp_mismatch(reg, text)
    if old:
        print(f'STOP: ye rang-file doosre map ki hai ({old[2:]}), abhi {pt.stamp(reg)[2:]}. Letters/numbers '
              'size, seal aur sketch ke saath badalte hain: wahi --size/--seal do, ya naya map dekh kar rang likho.')
        return 1
    try:
        area_col, line, tiny, notes = pt.plan(reg, pt.parse_colors(text))
        index, pal, li = pt.paint(reg, area_col, line, tiny)
    except m1.FillError as e:
        print(f'STOP: {e}')
        return 1
    done = ex.export_package(index, pal, a.out, name, a.dpi, line_index=li)
    with Image.open(a.sketch) as im:
        sk = im.convert('RGB')
        sk = np.asarray(sk.resize((1200, max(1, round(1200 * sk.height / sk.width))), Image.LANCZOS))
    if ref_rgb is not None:
        sk = cv2.resize(ref_rgb, (sk.shape[1], sk.shape[0]), interpolation=cv2.INTER_AREA)
    ex.compare_sheet(sk, pal[index], os.path.join(a.out, f'{name}_compare.png'),
                     ('rangeen design' if ref_rgb is not None else 'sketch', 'textile paint'))
    _, biggest = pt.check(reg, index, pal, a.out, name)
    with open(os.path.join(a.out, f'{name}_colors.txt'), 'w', encoding='utf-8') as fh:
        body = '\n'.join(l for l in text.strip().splitlines() if not l.startswith('# textile paint:'))
        fh.write(pt.stamp(reg) + '\n' + body + '\n')
    v = verify_package(done['paths'], done['size_px'], a.dpi)
    small = [c['hex'] for c in done['channels'] if c['coverage_percent'] < pl.STRAY_SHARE * 100]
    if small:
        notes.append(f"{', '.join(small)}: 0.05% se kam hissa - itne chhote rang ki alag screen chahiye? "
                     'Nahi to us hisse ko kisi aur rang ka bolo.')
    report = {'design': name, 'source': os.path.basename(a.sketch), 'size_px': done['size_px'], 'dpi': a.dpi,
              'print_size_inch': done['print_size_inch'], 'colors_in_final': v['colors_in_final'],
              'channels': done['channels'],
              'paint': {'biggest_areas': biggest, 'colors': text.strip(), 'areas': reg.n, 'groups': len(reg.letters),
                        'ground_group': reg.letters[reg.ground] if reg.ground >= 0 else None,
                        'tiny_areas': int((reg.group[1:] < 0).sum()), 'seal_px': reg.seal,
                        'line_threshold': a.line_threshold, 'sketch': reg.sketch_hash,
                        'lines': line, 'notes': notes},
              'verify': v}
    ex.write_report(done['paths']['report'], report)
    print('\n' + summary_hinglish(report))
    for n in notes:
        print(f'Note: {n}')
    print('Sabse bade hisse aur unka rang (yahi galat ho to rang "failta" dikhta hai):')
    print('  ' + ', '.join(f'{i} ({share}%) {hx} {cname}' for i, share, hx, cname in biggest))
    print(f'Check: {name}_check.png = bana design + har hisse ka number (kis number ko kya rang mila)')
    print(f"Files: {a.out}  (mill ko: {os.path.basename(done['paths']['tif'])}; dekhne ko: {name}_compare.png)")
    return 0 if v['passed'] else 1


def cmd_number(a):
    """A coloured design numbered: every patch of one colour gets a number (a map to plan a sketch on)."""
    from . import number as nb
    import re
    if a.hd or re.search(r'(^|[_-])hd($|[_-])', os.path.splitext(os.path.basename(a.design))[0], re.I):
        a.size *= 2                                  # same 300 DPI, twice the pixels (a bigger sheet: 7070 px = 23.6 inch)
        print(f'[hd] {a.size} px @ {a.dpi} DPI: sketch aur numbers double resolution me')
    try:
        r = nb.number(a.design, a.out, a.name, a.size, a.colors, a.detail, not a.no_smooth, a.line_mm,
                      not a.no_separators, a.min_area, log=_log)
    except m1.FillError as e:
        print(f'STOP: {e}')
        return 1
    w, h = r['size_px']
    print(f"\n{r['name']}: {w}x{h} px, {r['areas']} hisse numbered, {len(r['inks'])} rang:")
    for hx, cname, share in r['inks']:
        print(f'  {hx}  {cname}  {share}%')
    if len(r['tried']) > 1:
        print('Line motai ki tulna (sketch + CSV se wapas design):')
        for mm, m, parts in r['tried']:
            print(f"  {mm} mm: {m}% match, {parts} hisse" + ('   <- chuna' if mm == r['line_mm'] else ''))
    print(f"Sketch se wapas design: {r['match']}% match | {r['tiny']} bahut chhote hisse | {r['groups']} group (letters: "
          f"{os.path.basename(r['letters'])})")
    print(f"Sketch: {os.path.basename(r['sketch'])} (rang hata kar sirf lines), "
          f"{os.path.basename(r['sketch_numbers'])} (sketch + wahi numbers)")
    print(f"Rangeen: {r['name']}_rangeen.png (sketch + CSV se bana design, jaisa paint banayega)")
    print(f"Files: {r['name']}_numbers.png (rangeen design par numbers), {r['name']}_flat.png, "
          f"{r['name']}_colors.csv (har number ka rang)")
    if r['missed']:
        print(f"Note: {r['missed']} hisson ke number ke liye jagah nahi mili (sirf neela dot).")
    return 0


PAIR = ('_lineart', '_ref', '_colored', '_reference')
IMAGES = ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.webp', '.bmp')


def pairs(folder):
    """(name, line art, reference) for every NAME_lineart.* with a
    NAME_ref.* / NAME_colored.* / NAME_reference.* beside it, sorted; and the
    line arts that have none."""
    files = {f.lower(): f for f in os.listdir(folder) if f.lower().endswith(IMAGES)}
    out, alone = [], []
    for low, f in sorted(files.items()):
        stem, ext = os.path.splitext(low)
        if not stem.endswith('_lineart'):
            continue
        base = stem[:-len('_lineart')]
        ref = next((files[c] for s in PAIR[1:] for c in files if os.path.splitext(c)[0] == base + s), None)
        if ref:
            out.append((os.path.splitext(f)[0][:-len('_lineart')], os.path.join(folder, f), os.path.join(folder, ref)))
        else:
            alone.append(f)
    return out, alone


def cmd_batch(a):
    """Every pair in a folder through `fill`, each into out/NAME/; one bad
    pair never stops the rest. A summary table and batch_summary.csv."""
    import csv
    import io
    import json
    from contextlib import redirect_stdout
    found, alone = pairs(a.folder)
    if not found:
        print(f'STOP: {a.folder} me koi NAME_lineart + NAME_ref (ya _colored) jodi nahi mili.')
        return 1
    for f in alone:
        print(f'[skip] {f}: iska reference nahi mila (NAME_ref.png ya NAME_colored.png rakho)')
    os.makedirs(a.out, exist_ok=True)
    rows = []
    for name, line, ref in found:
        out = os.path.join(a.out, safe_name(name))
        args = ['fill', '--method', a.method, '--line', line, '--ref', ref, '--out', out, '--name', name,
                '--size', str(a.size), '--dpi', str(a.dpi), '--max-colors', str(a.max_colors)]
        print(f'[batch] {name} ...', flush=True)
        buf = io.StringIO()
        try:
            with redirect_stdout(buf):
                code = main(args)
        except Exception as e:                      # one broken file never stops the batch
            code, buf = 2, io.StringIO(f'STOP: {type(e).__name__}: {e}')
        text = buf.getvalue()
        with open(os.path.join(out if os.path.isdir(out) else a.out, f'{safe_name(name)}_log.txt'), 'w') as f:
            f.write(text)
        rep = os.path.join(out, f'{safe_name(name)}_report.json')
        r = json.load(open(rep)) if code != 2 and os.path.exists(rep) else {}
        stop = next((l for l in text.splitlines() if l.startswith('STOP')), '')
        rows.append({'design': name, 'result': 'OK' if code == 0 else ('STOP' if stop else 'CHECK'),
                     'method': r.get('method', ''), 'alignment': r.get('alignment_score', ''),
                     'colours': r.get('colors_in_final', ''),
                     'verify': ('PASS' if r['verify']['passed'] else 'FAIL') if r.get('verify') else '',
                     'note': stop[6:] if stop else ''})
        print(f"[batch] {name}: {rows[-1]['result']}" + (f' - {rows[-1]["note"]}' if stop else ''))
    with open(os.path.join(a.out, 'batch_summary.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print('\nDesign | Result | Method | Align | Rang | Verify')
    for r in rows:
        print(f"{r['design']} | {r['result']} | {r['method']} | {r['alignment']} | {r['colours']} | {r['verify']}")
    ok = sum(r['result'] == 'OK' for r in rows)
    print(f'\n{ok}/{len(rows)} theek. Summary: {os.path.join(a.out, "batch_summary.csv")}')
    return 0 if ok == len(rows) else 1


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
            parts = n[:-4].split('_')
            cnt.append({'channel': i, 'hex': parts[-1], 'coverage_percent': round(share, 2),
                        **({'name': parts[2], 'role': parts[3]} if len(parts) == 5 else {})})
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
        p.add_argument('--size', type=int, default=None,
                       help=f'Output width px (default {SIZE} = 11.78 inch at {DPI} DPI; same inches at another --dpi)')
        p.add_argument('--dpi', type=int, default=DPI, help=f'Default {DPI} (mill format). 600 sirf maangne par.')
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
    e.add_argument('--line-color', default=None, help="Outline ka rang (hex, jaise 120F06): uska channel 'outline' kehlata hai")
    e.set_defaults(fn=cmd_export)

    f = sub.add_parser('fill', help='Line art + reference -> flat colour design (Method 1 ya 2)')
    f.add_argument('--method', choices=['1', '2', '3', '4', 'auto'], default='1',
                   help='1: images aligned (default). 2: alag AI generations, sirf 2 rang (ground + motif). '
                        '3: wahi design par reference thoda khiska/khincha, kitne bhi rang. '
                        '4: Method 1 + line art ke tootne wale gap band (AI line art ke liye). '
                        'auto: Method 1 chala kar jaancho, fail ho to 2 ya 3')
    f.add_argument('--line', required=True, help='Black & white line art')
    f.add_argument('--ref', required=True, help='Colored reference (same design, same alignment)')
    common(f)
    f.add_argument('--line-threshold', type=int, default=150, help='Gray < ye = line (0-255)')
    f.add_argument('--line-color', default='auto', help="'auto' ya hex jaise EFCE6A")
    f.add_argument('--min-align', type=float, default=0.55, help='Isse kam alignment score par STOP')
    f.add_argument('--force', action='store_true', help='Alignment warning ke bawajood chalao')
    f.add_argument('--keep-strays', action='store_true', help='Chhote rang merge mat karo (method1 jaisa)')
    f.add_argument('--max-cover-diff', type=float, default=6.0,
                   help='auto: rangon ka hissa reference se itne points se zyada alag = Method 1 fail (default 6)')
    f.add_argument('--seal', type=int, default=None,
                   help='Method 4: gap band karne ka radius (output px). Default: line art ke 1.5 px, output ke hisaab se')
    f.add_argument('--reach-align', type=int, default=96,
                   help='Method 3: reference ko kitne px tak khiska sakte hain (3535 px par, default 96)')
    m = f.add_argument_group('Method 2 (prototype ke default)')
    m.add_argument('--colors', default=None, help='ground,motif hex (default: reference se, sabse common = ground)')
    m.add_argument('--reach', type=int, default=14, help='Line ke aar-paar kitne px tak dekhna (default 14)')
    m.add_argument('--dark-level', type=int, default=110, help='Reference me isse gehra = dark (default 110)')
    m.add_argument('--seed-area', type=int, default=6000, help='Bada band hissa: area > ye (default 6000)')
    m.add_argument('--seed-dark', type=float, default=0.8, help='...aur reference me dark > ye (default 0.8)')
    m.add_argument('--side-band', type=float, default=0.27, help='Side panel: chaudai ka ye hissa (default 0.27)')
    m.add_argument('--side-area', type=int, default=9000, help='Side panel me area > ye (default 9000)')
    m.add_argument('--side-dark', type=float, default=0.55, help='Side panel me dark > ye (default 0.55)')
    f.set_defaults(fn=cmd_fill)

    v = sub.add_parser('verify', help='Ek output folder ki files dobara check karo')
    v.add_argument('folder')
    v.add_argument('--name', default=None)
    v.set_defaults(fn=cmd_verify)

    r = sub.add_parser('repeat', help='All-over design ka repeat type, size, drop, jhukav (JSON)')
    r.add_argument('image')
    r.add_argument('--out', default=None, help='JSON yahan save karo (optional)')
    r.add_argument('--name', default=None)
    r.set_defaults(fn=cmd_repeat)

    t = sub.add_parser('tile', help='All-over design -> ek seamless repeat block (pehle repeat analysis)')
    t.add_argument('image')
    common(t)
    t.add_argument('--colors', type=int, default=None, help='Tile ko itne flat rangon me karo + channels (optional)')
    t.add_argument('--clean-ground', type=float, default=0, help='Ground ke itne paas wale pixels pakka ground (RGB doori, jaise 30)')
    t.add_argument('--shear-ratio', type=float, default=None, help='Jhukav khud do (dx/dy), default analysis se')
    t.add_argument('--w-range', default=None, help="Block chaudai search, jaise 496:514 (default analysis +-8)")
    t.add_argument('--h-range', default=None, help="Block lambai search, jaise 308:326 (default analysis +-8)")
    t.set_defaults(fn=cmd_tile)

    k = sub.add_parser('make', help='Original design (repeat ya panel) ek JSON config se, flat rang')
    k.add_argument('config', help='JSON config (examples/ dekho)')
    k.add_argument('--out', required=True)
    k.add_argument('--name', default=None)
    k.set_defaults(fn=cmd_make)

    vt = sub.add_parser('vector', help='Flat design ke kinare seedhe (trace -> bina AA dobara) + SVG')
    vt.add_argument('image', help='Flat design (jaise *_final_*.png)')
    vt.add_argument('--out', required=True)
    vt.add_argument('--name', default=None)
    vt.add_argument('--eps', type=float, default=0.8, help='Kinara pixels se kitna hil sakta hai (px, default 0.8)')
    vt.add_argument('--repeat', action='store_true', help='Repeat tile hai: kinare wrap karke trace (jod saaf rahe)')
    vt.set_defaults(fn=cmd_vector)

    ed_ = sub.add_parser('edges', help='Kinare saaf: har rang ki outline smooth, kone seedhe, patli line/dot salamat')
    ed_.add_argument('image', help='Flat design (jaise *_final_*.png, ya Reduce/fill ka result)')
    ed_.add_argument('--strength', type=int, choices=[1, 2, 3], default=2, help='1 halka, 2 normal (default), 3 zyada')
    ed_.add_argument('--specks', type=int, default=0, help='Itne pixel tak ke chhote tukde padosi rang me (default 0 = nahi; asli chhote dot bhi ja sakte hain)')
    ed_.add_argument('--repeat', choices=['no', 'x', 'y', 'both'], default='no',
                     help='Repeat tile hai: kinare jod ke aar-paar bhi saaf (x = left-right, y = upar-neeche)')
    common(ed_)
    ed_.set_defaults(fn=cmd_edges)

    pa = sub.add_parser('paint', help='Sketch (line art) + aapke bataye rang -> design, har rang alag channel')
    pa.add_argument('sketch', help='Line art / sketch (safed par kaali lines)')
    common(pa)
    pa.add_argument('--colors', default=None, action='append',
                    help='Rang: "A=cream, B=laal, C D=hara, 12 40-45=gold, lines=coffee, rest=navy" (ya us text ki '
                         'file, ya CSV: Number + HEX columns). Kai baar de sakte ho: baad wala jeetta hai (jaise CSV, phir '
                         '"171 337=cream" sudhaar). Na do to sirf map banta hai (letters + numbers)')
    pa.add_argument('--ref', default=None,
                    help='Usi design ka rangeen version: har hisse ka rang usse padha jaata hai (CSV apne aap), '
                         'aur rangeen design par numbers. --colors se upar se sudhaar')
    pa.add_argument('--ref-colors', type=int, default=8,
                    help='--ref se zyada se zyada itne rang (default 8; milte-julte shade apne aap ek)')
    pa.add_argument('--line-threshold', type=int, default=150, help='Gray < ye = line (0-255)')
    pa.add_argument('--seal', type=int, default=None,
                    help='Line ke chhote gap band karne ka radius (output px). Default: sketch ke 1.5 px; 0 = band nahi')
    pa.add_argument('--group-tolerance', type=float, default=1.0,
                    help='Ek jaise hisse pehchanne ki dheel (1 default; 1.5 = zyada hisse ek group me, 0.5 = kam)')
    pa.set_defaults(fn=cmd_paint)

    nu = sub.add_parser('number', help='Rangeen design ke har rang ke hisse ko number do (sketch banwane ke liye map)')
    nu.add_argument('design', help='Rangeen design (png/jpg)')
    nu.add_argument('--out', required=True)
    nu.add_argument('--name', default=None)
    nu.add_argument('--size', type=int, default=None, help='Kis chaudai par ginna (default 3535)')
    nu.add_argument('--dpi', type=int, default=DPI, help=argparse.SUPPRESS)
    nu.add_argument('--colors', type=int, default=8, help='Zyada se zyada itne rang (default 8; milte-julte shade ek)')
    nu.add_argument('--detail', choices=['kam', 'normal', 'zyada'], default='normal',
                    help='kam: 1.5 sq mm se chhote hisse paas me mila do (saaf, kam numbers); normal 0.4; zyada 0.1')
    nu.add_argument('--min-area', type=int, default=None, help='--detail ki jagah: isse chhote hisse (px) mila do')
    nu.add_argument('--line-mm', default='auto',
                    help='Sketch ki line kitni moti (mm, jaise 0.35). Default auto: 0.17, 0.35, 0.5 teeno banakar '
                         'jo design sabse sahi wapas banaye wahi rakhta hai')
    nu.add_argument('--no-smooth', action='store_true', help='Lines smooth mat karo (pixel jaisi)')
    nu.add_argument('--hd', action='store_true',
                    help='Double resolution (7070 px @ 300 DPI). File ke naam me _hd likhne se bhi (jaise rose_hd.png)')
    nu.add_argument('--no-separators', action='store_true',
                    help='Rang-rang ke beech ki line bhi kaali (default grey: print me paas ka rang)')
    nu.set_defaults(fn=cmd_number)

    b = sub.add_parser('batch', help='Folder ke saare NAME_lineart + NAME_ref jode ek saath (fill)')
    b.add_argument('folder')
    b.add_argument('--out', required=True)
    b.add_argument('--method', choices=['1', '2', '3', '4', 'auto'], default='auto', help='Default auto')
    b.add_argument('--size', type=int, default=None)
    b.add_argument('--dpi', type=int, default=DPI)
    b.add_argument('--max-colors', type=int, default=16)
    b.set_defaults(fn=cmd_batch)

    p = sub.add_parser('palette', help='Image ke rang aur coverage dikhao')
    p.add_argument('image')
    common(p, out=False)
    p.set_defaults(fn=cmd_palette)

    a = ap.parse_args(argv)
    if hasattr(a, 'size') and a.size is None:
        a.size = round(SIZE * a.dpi / DPI)          # 3535 at 300 DPI; the same 11.78 inch at any other
    if getattr(a, 'dpi', DPI) != DPI:
        print(DPI_WARNING.format(dpi=a.dpi))
    code = a.fn(a)
    if getattr(a, 'dpi', DPI) != DPI:
        print(DPI_WARNING.format(dpi=a.dpi))
    return code


DPI_WARNING = ('[CHETAVNI] {dpi} DPI file. Mill ka format 300 DPI hai: unka software ise 300 maan le to design '
               'galat size (600 par double) chhapega. Ye file mill ko tabhi bhejo jab mill ne {dpi} DPI khud maanga ho.')


if __name__ == '__main__':
    sys.exit(main())
