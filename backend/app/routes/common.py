"""Helpers the routes share: image responses, print size, one-design checks."""
from io import BytesIO
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from ..models import *
from ..separation_engine import engine as separation


def image_response(image, name='design.png', fmt='PNG', dpi=300, download=False):
    b = BytesIO(); image.save(b, format=fmt, dpi=(dpi, dpi)); b.seek(0)
    headers = {'Content-Disposition': f'attachment; filename="{name}"'} if download else {}
    return StreamingResponse(b, media_type=f'image/{fmt.lower()}', headers=headers)


def image_meta(image_id, image):
    w, h = image.size
    return {'image_id': image_id, 'width': w, 'height': h, 'aspect_ratio': round(w / h, 3), 'url': f'/api/image/{image_id}'}


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

__all__ = ['image_response', 'image_meta', 'MAX_PRINT_PX', '_print_size', '_svg_display',
           '_one_design', '_clean']
