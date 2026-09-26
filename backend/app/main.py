import asyncio
import math
import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from io import BytesIO
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from PIL import Image, ImageDraw, UnidentifiedImageError
from .models import *
from .core import store
from .core import regmarks
from .core import inks as ink_library
from .core.archive import build_package, encode
from .core.jobsheet import build_job_sheet
from .core.psd_import import is_psd, open_psd_any
from .color_engine import engine as colors
from .separation_engine import engine as separation
from .vector_engine import engine as vector

CLEANUP_INTERVAL_SECONDS = float(os.environ.get('CLEANUP_INTERVAL_SECONDS', 3600))


async def _cleanup_loop():
    while True:
        try:
            store.cleanup_expired()
        except Exception:
            pass
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app):
    store.cleanup_expired()  # clear stale files once at boot
    task = asyncio.create_task(_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title='LoomLab API', version='1.0.0', lifespan=lifespan)
_origins = [o.strip() for o in os.environ.get('ALLOWED_ORIGINS', 'http://localhost:5173').split(',') if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=['*'], allow_headers=['*'])


@app.exception_handler(FileNotFoundError)
def _missing_image(request: Request, exc: FileNotFoundError):
    """Generated images expire (see store.cleanup_expired), so an id from an
    old tab is an ordinary 'gone', not a server fault. Answer every endpoint
    with the same actionable message instead of a 500."""
    return JSONResponse(status_code=404, content={'detail': str(exc) or 'This image is no longer available. Please import it again.'})


def image_response(image, name='design.png', fmt='PNG', dpi=300, download=False):
    b = BytesIO(); image.save(b, format=fmt, dpi=(dpi, dpi)); b.seek(0)
    headers = {'Content-Disposition': f'attachment; filename="{name}"'} if download else {}
    return StreamingResponse(b, media_type=f'image/{fmt.lower()}', headers=headers)


def image_meta(image_id, image):
    w, h = image.size
    return {'image_id': image_id, 'width': w, 'height': h, 'aspect_ratio': round(w / h, 3), 'url': f'/api/image/{image_id}'}


_MULTICHANNEL_PALETTE = ['#E63946', '#457B9D', '#2A9D8F', '#E9C46A', '#F4A261', '#8338EC',
                         '#3A86FF', '#FF006E', '#06D6A0', '#FFD166', '#118AB2', '#073B4C']

# A bureau names each spot channel after the ink it prints ("2 BROWN 120",
# "GOLD", "WHITE DISCHARGE"). Showing those as arbitrary rainbow swatches makes
# the colour proof lie, so read the ink out of the name where we can and fall
# back to the placeholder palette only for names we don't recognise. The
# operator can still correct any of them on the plate strip.
_INK_WORDS = [
    ('BLACK', '#1A1A1A'), ('WHITE', '#FFFFFF'), ('SILVER', '#C0C4C8'), ('GREY', '#8A8D90'),
    ('GRAY', '#8A8D90'), ('GOLD', '#C8A13A'), ('COPPER', '#B46A3C'), ('BRONZE', '#A97142'),
    ('MAROON', '#7B2233'), ('BROWN', '#6B4530'), ('BEIGE', '#D8C7A8'), ('CREAM', '#EFE3C8'),
    ('NAVY', '#1E2A4A'), ('TURQUOISE', '#2FA5A0'), ('TEAL', '#2A7F7B'), ('OLIVE', '#6B6B3A'),
    ('MUSTARD', '#C8A02A'), ('ORANGE', '#E1701A'), ('PURPLE', '#6B3FA0'), ('VIOLET', '#7A4BB5'),
    ('MAGENTA', '#C2185B'), ('PINK', '#D96A8E'), ('YELLOW', '#E8C317'), ('GREEN', '#3E7C47'),
    ('BLUE', '#2A5DA8'), ('RED', '#C0392B'),
]


def _ink_from_name(name, fallback):
    """Best-effort ink colour for a named spot channel; `fallback` when the
    name says nothing we recognise."""
    upper = (name or '').upper()
    for word, hx in _INK_WORDS:
        if word in upper:
            return hx
    return fallback


def _channels_to_layers(channels):
    """A Multichannel PSD's channels ARE the pre-separated ink screens
    (black = ink). Each becomes (name, ink colour, ink-alpha layer, film,
    coverage) so mill production files skip reduce and go straight to export.
    The channels are kept exactly as separated: overlaps (trapping,
    overprint) and soft edges are the bureau's decisions, not ours."""
    out = []
    for i, (name, gray) in enumerate(channels):
        hx = _ink_from_name(name, _MULTICHANNEL_PALETTE[i % len(_MULTICHANNEL_PALETTE)])
        alpha = 255 - np.asarray(gray)
        rgba = np.zeros((*alpha.shape, 4), dtype=np.uint8); rgba[:, :, 3] = alpha
        out.append((name, hx, Image.fromarray(rgba), gray, round(float((alpha > 0).mean() * 100), 2)))
    return out


def _overlap(built):
    """Percent of the inked area that more than one channel prints on.

    A reduced design never overlaps, but a bureau's separation often does on
    purpose (trapping, so no gap shows if the screens shift; or overprint).
    The UI must not claim one ink per pixel for such a file. Counted on the
    solid part of each channel so anti-aliased rims don't register."""
    count = None
    for _, _, layer, _, _ in built:
        solid = np.asarray(layer)[:, :, 3] > 127
        count = solid.astype(np.uint8) if count is None else count + solid
    inked = int((count > 0).sum()) if count is not None else 0
    return round(float((count > 1).sum()) / inked * 100, 2) if inked else 0.0


@app.post('/api/image/upload')
async def upload(file: UploadFile = File(...)):
    raw = await file.read()
    if len(raw) > 80 * 1024 * 1024:
        raise HTTPException(413, 'Image is larger than the 80 MB import limit.')
    if is_psd(raw):
        try:
            kind, data = open_psd_any(raw)
        except ValueError as e:
            raise HTTPException(422, str(e))
        if kind == 'channels':
            built = _channels_to_layers(data)
            layers = []
            for name, hx, layer, display, coverage in built:
                lid = store.save(layer)
                pid = store.save(separation.preview_thumb([(layer, hx)]))   # chip thumbnail only
                layers.append({'id': lid, 'name': name, 'color': hx, 'coverage': coverage,
                               'edge': separation.edge_share(layer),
                               'url': f'/api/image/{lid}', 'plate_url': f'/api/image/{pid}'})
            preview = separation.composite_masks([(layer, hx, 100) for _, hx, layer, _, _ in built], built[0][2].size)
            image_id = store.save(preview)
            return image_meta(image_id, preview) | {'file_name': file.filename, 'file_size': len(raw),
                                                    'layers': layers, 'overlap': _overlap(built)}
        img = data
    else:
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(415, 'Please choose a PNG, JPG, WEBP, TIFF, or PSD image.')
        try:
            img = Image.open(BytesIO(raw)); img.load()
        except UnidentifiedImageError:
            raise HTTPException(422, 'The selected file is not a valid image.')
    # A 16-bit scan is normalised here, once, so every step downstream — reduce,
    # suggest, accuracy, separate, export and the browser preview — works on the
    # same 8-bit design instead of a clipped one.
    img = colors.to_8bit(img)
    if 'A' in img.getbands() and img.getchannel('A').getextrema()[1] == 0:
        raise HTTPException(422, 'This design is empty — every pixel is transparent. Export it again with the artwork visible.')
    image_id = store.save(img)
    return image_meta(image_id, img) | {'file_name': file.filename, 'file_size': len(raw)}


@app.post('/api/image/sample')
def sample():
    """A small floral pattern so the workflow can be explored without a file."""
    size = 720; image = Image.new('RGBA', (size, size), '#F4E8CC'); d = ImageDraw.Draw(image)
    for y in range(-40, size + 80, 120):
        for x in range(-40, size + 80, 120):
            d.ellipse((x - 48, y - 13, x + 48, y + 13), fill='#477052')
            for angle in range(0, 360, 45):
                dx = math.cos(math.radians(angle)) * 31; dy = math.sin(math.radians(angle)) * 31
                d.ellipse((x + dx - 23, y + dy - 15, x + dx + 23, y + dy + 15), fill='#C95368')
            d.ellipse((x - 12, y - 12, x + 12, y + 12), fill='#D9A43E')
    image_id = store.save(image)
    return image_meta(image_id, image) | {'file_name': 'loomlab-sample-floral.png', 'file_size': 0}


@app.post('/api/image/exists')
def images_exist(req: ImagesExistRequest):
    """Which of a saved job's images the working cache has cleared, so the
    app resumes a job only as far as its images still reach."""
    return {'missing': [i for i in dict.fromkeys(req.ids) if not store.exists(i)]}

@app.get('/api/image/{image_id}')
def get_image(image_id: str, max_side: int | None = Query(None, ge=64, le=20000)):
    """A stored image; with `max_side`, shrunk to fit it — what the screen
    shows. A 30-inch design is 61 MP, which a browser draws as an empty box."""
    if not max_side:
        return image_response(store.load(image_id))
    # made once and kept: stepping back and forth shows it at once (a 61 MP
    # design takes ~3.5s to load and shrink), saved fast rather than small
    path = store.screen_path(image_id, max_side)
    if not path.exists():
        image = store.load(image_id)
        if max(image.size) > max_side:
            image.thumbnail((max_side, max_side), Image.BOX, reducing_gap=2.0)
        tmp = path.with_suffix('.tmp')
        image.save(tmp, 'PNG', compress_level=1)
        os.replace(tmp, path)
    return FileResponse(path, media_type='image/png')


@app.post('/api/colors/reduce')
def reduce(req: ReduceRequest):
    """Step 2. Reduce the design to `colors` print inks. Returns the flat
    reduced image plus its palette (frequency-ranked) and a measured accuracy
    against the original — fewer colours, not less quality."""
    src = store.load(req.image_id)
    smoothing = colors.auto_smoothing(src)[0] if req.smoothing is None else req.smoothing
    image, pal = colors.quantize_full(src, req.colors, smoothing)
    image_id = store.save(image)
    de, acc = colors.reconstruction_accuracy(src, [c.hex for c in pal])
    return image_meta(image_id, image) | {
        'palette': pal, 'accuracy': acc, 'delta_e': de, 'source_id': req.image_id, 'smoothing': smoothing,
        'similar': colors.similar_inks(src, [c.hex for c in pal]),
        # a seamless repeat is processed wrapped round, so it stays seamless
        'repeat': dict(zip(('x', 'y'), map(bool, colors.repeat_to_report(src)))),
        # a flat ink cannot fade, so a soft edge prints as a hard one — say so
        'soft_edge': colors.soft_edge_width(src)}


@app.post('/api/colors/suggest')
def suggest(req: ImageIdRequest):
    """Recommend a sensible ink count for this design."""
    return colors.suggest_colors(store.load(req.image_id))


@app.post('/api/colors/remap')
def remap(req: RemapRequest):
    """Palette manual control: recolour or merge one ink. Repaints every pixel
    near `source` to `target` in the already-reduced image, returning a new
    flat image and its palette."""
    src = store.load(req.image_id)
    image = colors.merge(src, [req.source], req.target, req.threshold)
    image_id = store.save(image)
    return image_meta(image_id, image)


@app.post('/api/colors/small')
def small_inks(req: SmallInksRequest):
    """Inks covering under `below`% — each a whole screen — with what removing
    them costs, and which are too distinct to remove without a visible change."""
    return colors.small_inks(store.load(req.source_id), store.load(req.image_id), req.palette,
                             req.below, req.locked)


@app.post('/api/colors/drop')
def drop_inks(req: DropInksRequest):
    """The reduced design without the `drop` inks, each pixel moved to the
    remaining ink closest to its original colour. Returns the new flat image
    and every remaining ink's coverage."""
    if len({h.upper() for h in req.palette} - {h.upper() for h in req.drop}) < 1:
        raise HTTPException(422, 'At least one ink has to stay.')
    try:
        image = colors.drop_inks(store.load(req.source_id), store.load(req.image_id), req.palette, req.drop)
    except ValueError as e:
        raise HTTPException(422, str(e))
    kept = [h for h in req.palette if h.upper() not in {d.upper() for d in req.drop}]
    counts = colors._ink_counts(image, kept)
    total = max(int(counts.sum()), 1)
    cover = [{'hex': hx, 'pixels': int(n), 'coverage': round(int(n) / total * 100, 2)} for hx, n in zip(kept, counts)]
    image_id = store.save(image)
    return image_meta(image_id, image) | {'palette': cover}


@app.post('/api/colors/accuracy')
def accuracy(req: AccuracyRequest):
    src = store.load(req.image_id)
    de, acc = colors.reconstruction_accuracy(src, req.palette)
    # re-checked after every palette edit, so the merge suggestion never goes stale
    return {'accuracy': acc, 'delta_e': de, 'similar': colors.similar_inks(src, req.palette)}


@app.post('/api/separation/create')
def separate(req: SeparationRequest):
    """Step 3. Split the flat reduced image into one mutually-exclusive screen
    per ink — every pixel on exactly one plate, no overlap."""
    image = store.load(req.image_id)
    built = separation.create(image, req.palette, req.cleanup)
    layers = []
    for i, (hx, layer, coverage) in enumerate(built):
        lid = store.save(layer)
        plate_id = store.save(separation.preview_thumb([(layer, hx)]))   # chip thumbnail only
        layers.append({'id': lid, 'name': f'Ink {i + 1}', 'color': hx, 'coverage': coverage,
                       'edge': separation.edge_share(layer),
                       'url': f'/api/image/{lid}', 'plate_url': f'/api/image/{plate_id}'})
    return {'layers': layers}


# The largest print LoomLab will render. Enlarging holds a few float fields of
# the output size at once (~25 bytes a pixel), so 70 MP peaks under 2 GB —
# e.g. 28 x 28 in at 300 DPI. Bigger than that is a job for the vector SVG.
MAX_PRINT_PX = 70_000_000


def _print_size(native, width_in, dpi):
    """Pixel size of a print `width_in` wide at `dpi`, in the design's
    proportions — or the design's own size when no width is asked for."""
    w, h = native
    if not width_in:
        return native
    tw = max(1, round(width_in * dpi))
    th = max(1, round(h * tw / w))
    if (tw, th) == (w, h):
        return native
    if tw * th > MAX_PRINT_PX:
        widest = (MAX_PRINT_PX * w / h) ** 0.5 / dpi
        raise HTTPException(422, f'{width_in:g} in wide is {tw * th / 1e6:.0f} megapixels at {dpi} DPI, '
                                 f'more than LoomLab renders ({MAX_PRINT_PX // 1_000_000} MP). This design can '
                                 f'go up to {widest:.1f} in wide; for anything bigger use the vector SVG, '
                                 'which scales to any size.')
    return (tw, th)


def _svg_display(native, width_in):
    """Physical width/height attributes, so the SVG opens at its print size."""
    if not width_in:
        return None
    w, h = native
    return f'{width_in:g}in', f'{width_in * h / w:.4g}in'


def _one_design(masks):
    """The screens, if they all come from one design. Screens of different
    sizes (a stale job mixing two separations) cannot be stacked or printed
    in register: say so rather than fail inside the engine."""
    if len({m.size for m in masks}) > 1:
        raise HTTPException(422, 'These screens come from different designs (their sizes differ). '
                                 'Separate the design again and export from that.')
    return masks


def _clean(masks, min_dot_mm, dpi):
    """The screens with dots too small for a mesh given to the ink around them."""
    try:
        return separation.clean_specks(masks, separation.dot_area(min_dot_mm, dpi))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post('/api/separation/specks')
def separation_specks(req: SpeckRequest):
    """Per screen, the dots smaller than `min_dot_mm` at the print size: they
    won't hold on the mesh, so they print as nothing or as dirt."""
    native = _one_design([store.load(l.id) for l in req.layers])
    size = _print_size(native[0].size, req.width_in, req.dpi)
    drawn = separation.resize_masks(native, size)
    try:
        report = separation.speck_report(drawn, separation.dot_area(req.min_dot_mm, req.dpi))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {'min_dot_mm': req.min_dot_mm, 'max_area_px': separation.dot_area(req.min_dot_mm, req.dpi),
            'inks': [{'id': l.id, 'dots': d, 'pixels': p} for l, (d, p) in zip(req.layers, report)]}


@app.post('/api/separation/live-masks')
def live_masks(req: LiveMasksRequest):
    """Each screen shrunk to `max_side` (its alpha box-filtered, so edges stay
    smooth). The browser tints and stacks these to show a colour change the
    moment it is made; the full-size proof follows when the operator is done.
    Only for display: nothing that prints is made from them."""
    out = []
    size = None
    for mask in _one_design([store.load(i) for i in req.ids]):
        small = separation.thumb(mask, req.max_side)
        size = size or small.size
        sid = store.save(small)
        out.append(f'/api/image/{sid}')
    return {'width': size[0], 'height': size[1], 'masks': out}


@app.post('/api/separation/preview')
def separation_preview(req: PreviewRequest):
    """Combined proof of what the enabled screens print — the reconstructed
    design, so the operator can confirm the plates make their design."""
    if not req.layers:
        raise HTTPException(400, 'No ink screens selected.')
    masks = list(zip(_one_design([store.load(l.id) for l in req.layers]), [l.color for l in req.layers]))
    if req.thumb:
        image = separation.preview_thumb(masks, req.fabric)
    else:
        # at a chosen print width, preview the screens as they will be drawn
        size = _print_size(masks[0][0].size, req.width_in, req.dpi)
        drawn = separation.resize_masks([m for m, _ in masks], size)
        drawn = _clean(drawn, req.min_dot_mm, req.dpi)
        image = separation.print_preview(list(zip(drawn, [c for _, c in masks])), size, req.fabric)
        if req.max_side and max(image.size) > req.max_side:
            k = req.max_side / max(image.size)
            image = image.resize((max(1, round(image.width * k)), max(1, round(image.height * k))), Image.BOX)
    image_id = store.save(image)
    return image_meta(image_id, image)


@app.post('/api/export/package')
def export_package(req: PackageRequest):
    """Step 4. One production zip: a colour PNG plate and a print-ready TIFF
    screen (with registration marks) per ink, plus a colour proof."""
    if not req.layers:
        raise HTTPException(400, 'Nothing to export — separate the design into inks first.')
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
    if size != native or req.min_dot_mm:   # the proof shows the screens as they will print
        composite = separation.print_preview(list(zip(ink_masks, [it.color for it in layers])), size, req.fabric)
    else:
        composite = store.load(req.composite_image_id) if req.composite_image_id else None
        if composite is not None and composite.size != size:
            # the screen showed a smaller proof; the package gets it at print size
            composite = separation.print_preview(list(zip(ink_masks, [it.color for it in layers])), size, req.fabric)
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
    data = build_package(plates, screens, req.dpi, composite, readme, svgs, combined_svg, job_sheet=sheet)
    return StreamingResponse(BytesIO(data), media_type='application/zip',
                             headers={'Content-Disposition': 'attachment; filename="loomlab-production.zip"'})


@app.post('/api/export/svg')
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


@app.get('/api/inks')
def get_inks():
    """The mill's ink library."""
    return {'inks': ink_library.load()}


@app.put('/api/inks')
def put_inks(req: InkLibraryRequest):
    """Replace the mill's ink library."""
    return {'inks': ink_library.save([i.model_dump() for i in req.inks])}


@app.post('/api/inks/match')
def match_inks(req: InkMatchRequest):
    """For each palette colour, the nearest ink the mill already has."""
    return {'matches': colors.nearest_library_inks(req.palette, ink_library.load())}


@app.post('/api/colors/repaint')
def repaint(req: RepaintRequest):
    """Recolour every ink of the reduced design in one pass (e.g. to the mill's
    own inks). Two inks sent to the same target become one."""
    if len(req.targets) != len(req.palette):
        raise HTTPException(422, 'Send one target colour for every palette colour.')
    image = colors.repaint(store.load(req.image_id), req.palette, req.targets)
    image_id = store.save(image)
    return image_meta(image_id, image)


@app.get('/api/health')
def health():
    return {'ok': True}
