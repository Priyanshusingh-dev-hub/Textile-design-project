"""Step 4, Export: the production package and the vector SVG."""
import os
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from ..models import *
from ..core import store
from ..core import regmarks
from ..core.archive import build_package, encode
from ..core.jobsheet import build_job_sheet
from ..separation_engine import engine as separation
from ..vector_engine import engine as vector
from .common import *

router = APIRouter()


@router.post('/api/export/package')
def export_package(req: PackageRequest):
    """Step 4. One production zip: a colour PNG plate and a print-ready TIFF
    screen (with registration marks) per ink, plus a colour proof."""
    data, _ = _build_package(req)
    return StreamingResponse(BytesIO(data), media_type='application/zip',
                             headers={'Content-Disposition': 'attachment; filename="loomlab-production.zip"'})


def _build_package(req: PackageRequest, dot_check_mm: float = 0):
    """The production zip's bytes, plus what was measured on the way: the
    print size and, when `dot_check_mm` is set, the dots under that size on
    the screens as drawn at print size (before any cleaning) — auto mode
    reads them here rather than redrawing a 30-inch design a second time."""
    if not req.layers:
        raise HTTPException(400, 'Nothing to export — separate the design into inks first.')
    colourways = _colourways(req)
    # Print light inks first and dark ones last, the usual order on a textile
    # press: a dark ink put down early is picked up by the screens after it and
    # dirties the lighter colours. (The white under-base still goes first.)
    # Every list below follows this one order, so plates, films, vectors and the
    # job sheet stay matched.
    layers = sorted(req.layers, key=lambda it: -separation.press_lightness(it.color))
    masks = []
    # An expired image id raises out of the pool; `with` still shuts it down.
    with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1)) as workers:
        native_masks = _one_design(list(workers.map(store.load, [item.id for item in layers])))
        native = native_masks[0].size
        # at a chosen print width the screens are redrawn at that size with
        # smooth edges (still one ink per pixel); otherwise they are untouched
        size = _print_size(native, req.width_in, req.dpi)
        ink_masks = separation.resize_masks(native_masks, size)
        dots = None
        if dot_check_mm:
            report = separation.speck_report(ink_masks, separation.dot_area(dot_check_mm, req.dpi))
            inked = sum(int((np.asarray(m.getchannel('A')) > 0).sum()) for m in ink_masks)
            dots = {'dots': sum(d for d, _ in report), 'pixels': sum(p for _, p in report), 'inked': inked}
        ink_masks = _clean(ink_masks, req.min_dot_mm, req.dpi)
        # what each film prints: the separation itself, or with a trap each
        # lighter ink spread under the darker ones (the design is unchanged)
        try:
            film_masks = separation.trap(ink_masks, [it.color for it in layers], req.trap_px)
        except ValueError as e:
            raise HTTPException(422, str(e))

        def _render(job):
            """One screen's colour proof and film, rendered and encoded. Each ink
            is independent and PIL/numpy release the GIL, so inks run in
            parallel; the zip is still written in order."""
            name, mask, color, label = job
            plate = regmarks.caption_plate(separation.plate(mask, color, req.fabric), label, color, req.dpi)
            screen = separation.to_print_ready(mask)
            if req.reg_marks:                              # margin + corner targets + film label
                screen = regmarks.add_registration_marks(screen, req.dpi, label)
            return name, encode(plate, 'png', req.dpi), encode(screen, 'tiff', req.dpi)

        jobs, sheet_rows = [], []
        # The white base goes down before any colour, so it leads the package.
        if req.underbase:
            ub = separation.underbase(ink_masks, req.underbase_choke)
            if ub is not None:
                cov = round(float((np.asarray(ub)[:, :, 3] > 0).mean() * 100), 1)
                jobs.append(('0-Underbase', ub, '#FFFFFF', f'0  UNDER-BASE (print first)  #FFFFFF  {cov}%'))
                sheet_rows.append((0, 'White under-base', '#FFFFFF', cov, ub))

        for idx, (item, mask, film, nat) in enumerate(zip(layers, ink_masks, film_masks, native_masks), 1):
            alpha = np.asarray(mask.convert('RGBA'))[:, :, 3]
            coverage = round(float((alpha > 0).mean() * 100), 1)
            # vectors trace the design's own pixels; they scale by themselves
            masks.append((item.color, np.asarray(nat.convert('RGBA'))[:, :, 3] > 127))
            jobs.append((item.name, film, item.color, f'{idx}  {item.name}  {item.color}  {coverage}%'
                                                      + (f'  TRAP {req.trap_px}px' if req.trap_px else '')))
            sheet_rows.append((idx, item.name, item.color, coverage, mask))
        rendered = list(workers.map(_render, jobs))
    plates = [(name, p) for name, p, _ in rendered]
    screens = [(name, sc) for name, _, sc in rendered]
    svgs = combined_svg = None
    if req.vector and masks:
        display = _svg_display(native, req.width_in)
        paths = [vector.path_data(m) for _, m in masks]      # trace each ink once
        svgs = [(it.name, vector.layer_svg(m, color, native, d=d, display=display))
                for it, (color, m), d in zip(layers, masks, paths)]
        if req.underbase and len(plates) == len(layers) + 1:
            svgs.insert(0, ('0-Underbase', ''))        # keep svgs index-aligned with plates
        combined_svg = vector.build_svg(masks, native, paths=paths, display=display)
    # the proof is always drawn from the screens in this package, at print size:
    # an image named by the client could be an older preview (before a recolour
    # or a plate marked as fabric) and disagree with the films
    composite = separation.print_preview(list(zip(ink_masks, [it.color for it in layers])), size, req.fabric)
    ub_row = next((r for r in sheet_rows if r[0] == 0), None)
    ink_rows = [r for r in sheet_rows if r[0] != 0]
    def _colourway(way):
        """One colourway's proof and job sheet, encoded. Independent of the
        others, so they are drawn in parallel like the screens."""
        cw, safe, inks, cloth = way
        cw_inks = [inks[it.id] for it in layers]                 # (colour, name) per screen, main order
        proof = separation.print_preview(list(zip(ink_masks, [c for c, _ in cw_inks])), size, cloth)
        # the same screens, printed lightest first in THIS colourway's inks
        order = sorted(range(len(layers)), key=lambda i: -separation.press_lightness(cw_inks[i][0]))
        rows = ([(0, 'White under-base', '#FFFFFF', ub_row[3],
                  separation.preview_thumb([(ub_row[4], '#FFFFFF')], cloth))] if ub_row else [])
        rows += [(n, f'{cw_inks[i][1] or cw_inks[i][0]}  on screen {ink_rows[i][0]} ({layers[i].name})',
                  cw_inks[i][0], ink_rows[i][3], separation.preview_thumb([(ink_rows[i][4], cw_inks[i][0])], cloth))
                 for n, i in enumerate(order, 1)]
        cw_sheet = build_job_sheet(
            rows, separation.preview_thumb(list(zip(ink_masks, [c for c, _ in cw_inks])), cloth, 480),
            title=f'Colourway {cw.name}: the same {len(layers)} screens in other inks',
            print_size=f'{size[0] / req.dpi:.2f} x {size[1] / req.dpi:.2f} in  '
                       f'({size[0] / req.dpi * 25.4:.0f} x {size[1] / req.dpi * 25.4:.0f} mm)',
            cloth=cloth, underbase=bool(req.underbase), dpi=req.dpi,
            dots=f'under {req.min_dot_mm:g} mm cleaned' if req.min_dot_mm else None)
        return [(f'colourways/{safe}/proof.png', encode(proof, 'png', req.dpi)),
                (f'colourways/{safe}/job-sheet.png', encode(cw_sheet, 'png', 150))]

    extra = []
    if colourways:
        with ThreadPoolExecutor(max_workers=min(4, os.cpu_count() or 1, len(colourways))) as pool:
            for files in pool.map(_colourway, colourways):      # in order, so the zip is too
                extra += files
    names = ', '.join(f'{i + 1}. {l.name} ({l.color})' for i, l in enumerate(layers))
    trap_mm = req.trap_px / req.dpi * 25.4
    readme = (
        'LoomLab production package\n'
        '==========================\n\n'
        f'Inks ({len(layers)}): {names}\n\n'
        f'Print size: {size[0] / req.dpi:.2f} x {size[1] / req.dpi:.2f} in at {req.dpi} DPI'
        + (f' (enlarged from {native[0]} x {native[1]} px, edges redrawn smooth)' if size != native else '') + '\n'
        f'Cloth: {req.fabric}\n' + ('Print the UNDER-BASE screen first, then the colours in the order listed.\n' if req.underbase else '')
        + 'Inks are listed lightest first: a dark ink printed early dirties the lighter ones after it.\n'
        + (f'Tiny dots cleaned: every island under {req.min_dot_mm:g} mm across went to the ink around it\n'
           '(a screen cannot hold them). The proof shows the result.\n' if req.min_dot_mm else '')
        + (f'Trap: {req.trap_px} px ({trap_mm:.2f} mm). Each ink is spread under the darker inks it touches,\n'
           'so a screen that slips a little leaves no line of bare cloth. Print in the order listed:\n'
           'the darker ink covers the spread and the print looks exactly like the proof.\n'
           + ('The vector outlines are the design as separated, without the trap.\n' if req.vector else '')
           if req.trap_px else '')
        + '\nplates/   colour proof of each ink on the cloth colour (PNG)\n'
        'screens/  print-ready B&W separations, black = ink '
        f'(TIFF, {req.dpi} DPI'
        + (', with registration marks in the margin)\n' if req.reg_marks else ')\n')
        + 'proof.png full-colour composite of all inks\n'
        + 'job-sheet.png  one page to print and pin up at the press: screens in order,\n'
        + '               ink colours, coverage, print size and cloth\n'
        + ('vector/   scalable SVG outlines (design.svg = all inks)\n' if req.vector else '')
        + '\nPrint one screen per ink. The registration targets in every screen\n'
        'share the same position, so the screens line up when superimposed.\n'
        + ('\nColourways: the same screens printed in other inks (no new screens).\n'
           'colourways/<name>/proof.png and job-sheet.png: which ink goes on which\n'
           'screen (by the number on the film), lightest first.\n'
           + ''.join(f'  {cw.name}: ' + ', '.join(f'screen {i + 1} = {(inks[it.id][1] or inks[it.id][0])}'
                                                   for i, it in enumerate(layers)) + f'; cloth {cloth}\n'
                     for cw, _, inks, cloth in colourways)
           if colourways else '')
    )
    w_in, h_in = size[0] / req.dpi, size[1] / req.dpi
    sheet = build_job_sheet(
        [(order, name, hx, cov, separation.preview_thumb([(m, hx)], req.fabric)) for order, name, hx, cov, m in sheet_rows],
        # its own small proof, from the screens themselves: always there, and cheap
        separation.preview_thumb(list(zip(ink_masks, [it.color for it in layers])), req.fabric, 480),
        title=f'{len(layers)} ink screen{"s" if len(layers) != 1 else ""}'
              + (' + white under-base' if req.underbase else '') + f'  ·  {size[0]} x {size[1]} px',
        print_size=f'{w_in:.2f} x {h_in:.2f} in  ({w_in * 25.4:.0f} x {h_in * 25.4:.0f} mm)',
        cloth=req.fabric, underbase=bool(req.underbase), dpi=req.dpi,
        trap=f'{req.trap_px} px · {trap_mm:.2f} mm' if req.trap_px else None,
        dots=f'under {req.min_dot_mm:g} mm cleaned' if req.min_dot_mm else None)
    data = build_package(plates, screens, req.dpi, composite, readme, svgs, combined_svg, job_sheet=sheet,
                         extra_files=extra)
    return data, {'size': size, 'native': native, 'dots': dots}


def _colourways(req: PackageRequest):
    """[(colourway, folder name, {screen id: (colour, name)}, cloth)], checked:
    every screen gets exactly one ink, names don't collide."""
    if req.colourways and req.trap_px:
        raise HTTPException(422, 'A trap is made for one set of inks (lighter under darker): with colourways '
                                 'the order changes, so leave trap off.')
    ids = [it.id for it in req.layers]
    out, used = [], set()
    for cw in req.colourways:
        inks = {i.id: (i.color.upper(), i.name.strip()) for i in cw.inks}
        missing = [n for n, it in enumerate(req.layers, 1) if it.id not in inks]
        if missing or set(inks) - set(ids):
            raise HTTPException(422, f'Colourway {cw.name} must give one ink for each of the {len(ids)} screens.')
        safe = ''.join(ch if ch.isalnum() or ch in ' -_' else '-' for ch in cw.name).strip() or 'colourway'
        if safe.lower() in used:
            raise HTTPException(422, f'Two colourways are called {cw.name}.')
        used.add(safe.lower())
        out.append((cw, safe, inks, (cw.fabric or req.fabric).upper()))
    return out


@router.post('/api/export/svg')
def export_svg(req: SvgExportRequest):
    """Standalone scalable vector of the whole design — one SVG, inks stacked
    back to front, holes rendered by even-odd fill."""
    if not req.layers:
        raise HTTPException(400, 'Nothing to export — separate the design into inks first.')
    masks = []
    for item, mask in zip(req.layers, _one_design([store.load(item.id) for item in req.layers])):
        alpha = np.asarray(mask.convert('RGBA'))[:, :, 3] > 127
        masks.append((item.color, alpha))
    size = masks[0][1].shape[1], masks[0][1].shape[0]
    svg = vector.build_svg(masks, size, req.simplify, req.smooth, req.min_area,
                           display=_svg_display(size, req.width_in))
    return StreamingResponse(BytesIO(svg.encode()), media_type='image/svg+xml',
                             headers={'Content-Disposition': 'attachment; filename="loomlab-design.svg"'})
