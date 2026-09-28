"""Step 1 and design files: upload (incl. pre-separated PSDs), stored images, enlarge, download."""
import math
import os
from io import BytesIO
import numpy as np
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from PIL import Image, ImageDraw, UnidentifiedImageError
from ..models import *
from ..core import store
from ..core.psd_import import is_psd, open_psd_any
from ..core import enlarge as enlarger
from ..color_engine import engine as colors
from ..separation_engine import engine as separation
from .common import *

router = APIRouter()


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


@router.post('/api/image/upload')
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


@router.post('/api/image/sample')
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


@router.post('/api/image/exists')
def images_exist(req: ImagesExistRequest):
    """Which of a saved job's images the working cache has cleared, so the
    app resumes a job only as far as its images still reach."""
    return {'missing': [i for i in dict.fromkeys(req.ids) if not store.exists(i)]}

@router.get('/api/image/{image_id}')
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


@router.post('/api/image/enlarge')
def enlarge_image(req: EnlargeRequest):
    """The design enlarged on this PC to print size (Real-ESRGAN if installed,
    else Lanczos), with a match score: brought back to its own size, how
    close it still is to the original. Under 95% the design changed."""
    src = store.load(req.image_id)
    size = _print_size(src.size, req.width_in, req.dpi)
    done = enlarger.enlarge(src, size, req.method)
    image_id = store.save(done['image'])
    return image_meta(image_id, done['image']) | {
        'method': done['method'], 'note': done['note'], 'match': done['match'], 'delta_e': done['delta_e'],
        'ok': done['ok'], 'min_match': enlarger.MIN_MATCH, 'dpi': req.dpi,
        'width_in': round(size[0] / req.dpi, 2), 'height_in': round(size[1] / req.dpi, 2),
        'source_ppi': round(src.width / (size[0] / req.dpi), 1)}


@router.get('/api/image/{image_id}/file')
def image_file(image_id: str, format: str = Query('tif', pattern='^(tif|jpg|png)$'),
               dpi: int = Query(300, ge=72, le=1200), name: str = Query('design', max_length=80)):
    """A stored image as a file to keep, with its DPI written in: TIFF
    (LZW, lossless), JPEG (quality 95, no colour subsampling) or PNG."""
    image = store.load(image_id)
    safe = ''.join(c for c in name if c.isalnum() or c in '-_ ').strip() or 'design'
    buf = BytesIO()
    if format == 'jpg':
        image.convert('RGB').save(buf, 'JPEG', quality=95, subsampling=0, dpi=(dpi, dpi))
        media = 'image/jpeg'
    elif format == 'tif':
        img = image if image.getchannel('A').getextrema()[0] < 255 else image.convert('RGB')
        img.save(buf, 'TIFF', compression='tiff_lzw', dpi=(dpi, dpi))
        media = 'image/tiff'
    else:
        image.save(buf, 'PNG', dpi=(dpi, dpi))
        media = 'image/png'
    buf.seek(0)
    return StreamingResponse(buf, media_type=media,
                             headers={'Content-Disposition': f'attachment; filename="{safe}-{dpi}dpi.{format}"'})
