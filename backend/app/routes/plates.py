"""Step 3, Separate: one screen per ink, the proof, tiny dots, live recolouring."""
from fastapi import APIRouter, HTTPException
from PIL import Image
from ..models import *
from ..core import store
from ..separation_engine import engine as separation
from .common import *

router = APIRouter()


@router.post('/api/separation/create')
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


@router.post('/api/separation/specks')
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


@router.post('/api/separation/live-masks')
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


@router.post('/api/separation/preview')
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
