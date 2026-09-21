import asyncio
import math
import os
from contextlib import asynccontextmanager
from io import BytesIO
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from PIL import Image, ImageDraw, UnidentifiedImageError
from .models import *
from .core import store
from .core import regmarks
from .core.archive import build_package
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


def image_response(image, name='design.png', fmt='PNG', dpi=300, download=False):
    b = BytesIO(); image.save(b, format=fmt, dpi=(dpi, dpi)); b.seek(0)
    headers = {'Content-Disposition': f'attachment; filename="{name}"'} if download else {}
    return StreamingResponse(b, media_type=f'image/{fmt.lower()}', headers=headers)


def image_meta(image_id, image):
    w, h = image.size
    return {'image_id': image_id, 'width': w, 'height': h, 'aspect_ratio': round(w / h, 3), 'url': f'/api/image/{image_id}'}


_MULTICHANNEL_PALETTE = ['#E63946', '#457B9D', '#2A9D8F', '#E9C46A', '#F4A261', '#8338EC',
                         '#3A86FF', '#FF006E', '#06D6A0', '#FFD166', '#118AB2', '#073B4C']


def _channels_to_layers(channels):
    """A Multichannel PSD's channels ARE the pre-separated ink screens
    (black = ink). Turn each into the same (ink-alpha layer, display, coverage)
    shape separation.create() produces, so mill production files skip reduce
    and go straight to export."""
    out = []
    for i, (name, gray) in enumerate(channels):
        hx = _MULTICHANNEL_PALETTE[i % len(_MULTICHANNEL_PALETTE)]
        alpha = 255 - np.asarray(gray)
        rgba = np.zeros((*alpha.shape, 4), dtype=np.uint8); rgba[:, :, 3] = alpha
        out.append((name, hx, Image.fromarray(rgba), gray, round(float((alpha > 0).mean() * 100), 2)))
    return out


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
                pid = store.save(separation.plate(layer, hx))
                layers.append({'id': lid, 'name': name, 'color': hx, 'coverage': coverage,
                               'url': f'/api/image/{lid}', 'plate_url': f'/api/image/{pid}'})
            preview = separation.composite_masks([(layer, hx, 100) for _, hx, layer, _, _ in built], built[0][2].size)
            image_id = store.save(preview)
            return image_meta(image_id, preview) | {'file_name': file.filename, 'file_size': len(raw), 'layers': layers}
        img = data
    else:
        if not file.content_type or not file.content_type.startswith('image/'):
            raise HTTPException(415, 'Please choose a PNG, JPG, WEBP, TIFF, or PSD image.')
        try:
            img = Image.open(BytesIO(raw)); img.load()
        except UnidentifiedImageError:
            raise HTTPException(422, 'The selected file is not a valid image.')
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


@app.get('/api/image/{image_id}')
def get_image(image_id: str):
    try:
        return image_response(store.load(image_id))
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@app.post('/api/colors/reduce')
def reduce(req: ReduceRequest):
    """Step 2. Reduce the design to `colors` print inks. Returns the flat
    reduced image plus its palette (frequency-ranked) and a measured accuracy
    against the original — fewer colours, not less quality."""
    src = store.load(req.image_id)
    image, pal = colors.quantize_full(src, req.colors, req.smoothing)
    image_id = store.save(image)
    de, acc = colors.reconstruction_accuracy(src, [c.hex for c in pal])
    return image_meta(image_id, image) | {'palette': pal, 'accuracy': acc, 'delta_e': de, 'source_id': req.image_id}


@app.post('/api/colors/remap')
def remap(req: RemapRequest):
    """Palette manual control: recolour or merge one ink. Repaints every pixel
    near `source` to `target` in the already-reduced image, returning a new
    flat image and its palette."""
    src = store.load(req.image_id)
    image = colors.merge(src, [req.source], req.target, req.threshold)
    image_id = store.save(image)
    return image_meta(image_id, image)


@app.post('/api/colors/accuracy')
def accuracy(req: AccuracyRequest):
    de, acc = colors.reconstruction_accuracy(store.load(req.image_id), req.palette)
    return {'accuracy': acc, 'delta_e': de}


@app.post('/api/separation/create')
def separate(req: SeparationRequest):
    """Step 3. Split the flat reduced image into one mutually-exclusive screen
    per ink — every pixel on exactly one plate, no overlap."""
    image = store.load(req.image_id)
    built = separation.create(image, req.palette, req.cleanup)
    layers = []
    for i, (hx, layer, display, coverage) in enumerate(built):
        lid = store.save(layer)
        plate_id = store.save(separation.plate(layer, hx))
        layers.append({'id': lid, 'name': f'Ink {i + 1}', 'color': hx, 'coverage': coverage,
                       'url': f'/api/image/{lid}', 'plate_url': f'/api/image/{plate_id}'})
    return {'layers': layers}


@app.post('/api/export/package')
def export_package(req: PackageRequest):
    """Step 4. One production zip: a colour PNG plate and a print-ready TIFF
    screen (with registration marks) per ink, plus a colour proof."""
    if not req.layers:
        raise HTTPException(400, 'Nothing to export — separate the design into inks first.')
    plates, screens, masks = [], [], []
    for item in req.layers:
        mask = store.load(item.id)
        masks.append((item.color, np.asarray(mask.convert('RGBA'))[:, :, 3] > 127))
        plates.append((item.name, separation.plate(mask, item.color)))
        screen = separation.to_print_ready(mask)
        if req.reg_marks:
            screen = regmarks.add_registration_marks(screen, req.dpi)
        screens.append((item.name, screen))
    svgs = combined_svg = None
    if req.vector and masks:
        size = masks[0][1].shape[1], masks[0][1].shape[0]
        svgs = [(it.name, vector.layer_svg(m, color, size)) for it, (color, m) in zip(req.layers, masks)]
        combined_svg = vector.build_svg(masks, size)
    composite = store.load(req.composite_image_id) if req.composite_image_id else None
    names = ', '.join(f'{i + 1}. {l.name} ({l.color})' for i, l in enumerate(req.layers))
    readme = (
        'LoomLab production package\n'
        '==========================\n\n'
        f'Inks ({len(req.layers)}): {names}\n\n'
        'plates/   colour proof of each ink on white (PNG)\n'
        'screens/  print-ready B&W separations, black = ink '
        f'(TIFF, {req.dpi} DPI'
        + (', with registration marks in the margin)\n' if req.reg_marks else ')\n')
        + 'proof.png full-colour composite of all inks\n'
        + ('vector/   scalable SVG outlines (design.svg = all inks)\n' if req.vector else '')
        + '\nPrint one screen per ink. The registration targets in every screen\n'
        'share the same position, so the screens line up when superimposed.\n'
    )
    data = build_package(plates, screens, req.dpi, composite, readme, svgs, combined_svg)
    return StreamingResponse(BytesIO(data), media_type='application/zip',
                             headers={'Content-Disposition': 'attachment; filename="loomlab-production.zip"'})


@app.post('/api/export/svg')
def export_svg(req: SvgExportRequest):
    """Standalone scalable vector of the whole design — one SVG, inks stacked
    back to front, holes rendered by even-odd fill."""
    if not req.layers:
        raise HTTPException(400, 'Nothing to export — separate the design into inks first.')
    masks = []
    for item in req.layers:
        alpha = np.asarray(store.load(item.id).convert('RGBA'))[:, :, 3] > 127
        masks.append((item.color, alpha))
    size = masks[0][1].shape[1], masks[0][1].shape[0]
    svg = vector.build_svg(masks, size, req.simplify, req.smooth, req.min_area)
    return StreamingResponse(BytesIO(svg.encode()), media_type='image/svg+xml',
                             headers={'Content-Disposition': 'attachment; filename="loomlab-design.svg"'})


@app.get('/api/health')
def health():
    return {'ok': True}
