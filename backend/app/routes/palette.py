"""Step 2, Reduce: the ink count, reduce, palette edits, small inks, the mill's shelf inks."""
import numpy as np
from fastapi import APIRouter, HTTPException
from ..models import *
from ..core import store
from ..core import inks as ink_library
from ..color_engine import engine as colors
from .common import *

router = APIRouter()


@router.post('/api/colors/reduce')
def reduce(req: ReduceRequest):
    """Step 2. Reduce the design to `colors` print inks. Returns the flat
    reduced image plus its palette (frequency-ranked) and a measured accuracy
    against the original — fewer colours, not less quality."""
    src = store.load(req.image_id)
    smoothing = colors.auto_smoothing(src)[0] if req.smoothing is None else req.smoothing
    image, pal = colors.quantize_full(src, req.colors, smoothing)
    if req.dots:
        # the same inks, placed as dots over the whole design; judged as seen
        image, pal = _dotted(src, [c.hex for c in pal])
    return _reduced(src, req.image_id, image, pal, smoothing, req.dots)


def _reduced(src, source_id, image, pal, smoothing, dots):
    """A reduce's answer. A dotted design is judged as seen, and has no merge
    hints: their price is on the flat-ink scale, not the one it shows."""
    hexes = [c.hex for c in pal]
    de, acc = colors.seen_match(src, image) if dots else colors.reconstruction_accuracy(src, hexes)
    image_id = store.save(image)
    return image_meta(image_id, image) | {
        'palette': pal, 'accuracy': acc, 'delta_e': de, 'source_id': source_id, 'smoothing': smoothing,
        'dots': dots,
        'similar': [] if dots else colors.similar_inks(src, hexes),
        # a seamless repeat is processed wrapped round, so it stays seamless
        'repeat': dict(zip(('x', 'y'), map(bool, colors.repeat_to_report(src)))),
        # a flat ink cannot fade, so a soft edge prints as a hard one — say so
        'soft_edge': colors.soft_edge_width(src)}


def _dotted(src, hexes):
    """The design as dots of `hexes`, and its palette by what the dots cover
    (an ink can cover more or less than as a flat area; one no dot uses goes)."""
    image = colors.dither(src, hexes)
    counts = colors._ink_counts(image, hexes)
    total = max(int(counts.sum()), 1)
    order = [i for i in np.argsort(-counts, kind='stable') if counts[i] > 0]
    pal = [Color(hex=hexes[i].upper(), rgb=colors.hex_rgb(hexes[i]).astype(int).tolist(), pixels=int(counts[i]),
                 coverage=round(float(counts[i] / total * 100), 2)) for i in order]
    return image, pal


@router.post('/api/colors/dots')
def dots(req: DotsRequest):
    """The design with the palette as it is now — as dots, or back to flat
    areas — so switching keeps the operator's edits (shelf inks, merges,
    recolours) and is one undo step, not a fresh reduce."""
    src = store.load(req.image_id)
    smoothing = colors.auto_smoothing(src)[0] if req.smoothing is None else req.smoothing
    if req.dots:
        image, pal = _dotted(src, req.palette)
    else:
        image, pal = colors.quantize_full(src, len(req.palette), smoothing, palette_hex=req.palette)
    return _reduced(src, req.image_id, image, pal, smoothing, req.dots)


@router.post('/api/colors/suggest')
def suggest(req: ImageIdRequest):
    """Recommend a sensible ink count for this design."""
    return colors.suggest_colors(store.load(req.image_id))


@router.post('/api/colors/remap')
def remap(req: RemapRequest):
    """Palette manual control: recolour or merge one ink. Repaints every pixel
    near `source` to `target` in the already-reduced image, returning a new
    flat image and its palette."""
    src = store.load(req.image_id)
    image = colors.merge(src, [req.source], req.target, req.threshold)
    image_id = store.save(image)
    return image_meta(image_id, image)


@router.post('/api/colors/small')
def small_inks(req: SmallInksRequest):
    """Inks covering under `below`% — each a whole screen — with what removing
    them costs, and which are too distinct to remove without a visible change."""
    return colors.small_inks(store.load(req.source_id), store.load(req.image_id), req.palette,
                             req.below, req.locked)


@router.post('/api/colors/drop')
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


@router.post('/api/colors/accuracy')
def accuracy(req: AccuracyRequest):
    src = store.load(req.image_id)
    if req.dots and req.reduced_id:
        de, acc = colors.seen_match(src, store.load(req.reduced_id))
        return {'accuracy': acc, 'delta_e': de, 'similar': []}
    de, acc = colors.reconstruction_accuracy(src, req.palette)
    # re-checked after every palette edit, so the merge suggestion never goes stale
    return {'accuracy': acc, 'delta_e': de, 'similar': colors.similar_inks(src, req.palette)}


@router.get('/api/inks')
def get_inks():
    """The mill's ink library."""
    return {'inks': ink_library.load()}


@router.put('/api/inks')
def put_inks(req: InkLibraryRequest):
    """Replace the mill's ink library."""
    return {'inks': ink_library.save([i.model_dump() for i in req.inks])}


@router.post('/api/inks/match')
def match_inks(req: InkMatchRequest):
    """For each palette colour, the nearest ink the mill already has."""
    return {'matches': colors.nearest_library_inks(req.palette, ink_library.load())}


@router.post('/api/colors/repaint')
def repaint(req: RepaintRequest):
    """Recolour every ink of the reduced design in one pass (e.g. to the mill's
    own inks). Two inks sent to the same target become one."""
    if len(req.targets) != len(req.palette):
        raise HTTPException(422, 'Send one target colour for every palette colour.')
    image = colors.repaint(store.load(req.image_id), req.palette, req.targets)
    image_id = store.save(image)
    return image_meta(image_id, image)
