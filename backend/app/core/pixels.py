"""How big an image LoomLab agrees to open, checked before it is decoded.

Pillow's guard against "decompression bombs" (a tiny file whose header claims
an enormous picture) is Image.MAX_IMAGE_PIXELS: above it Pillow only *warns*,
and only above twice it does it refuse. So the engine sets the limit (never
None) and checks every uploaded image's size from its header itself, before
any pixel is decoded, and answers a clear 413 instead of running out of memory.

The default, 500 million pixels, covers real mill files with room to spare: a
2 m x 1.5 m repeat at 300 DPI is 23 622 x 17 717 px = 419 MP, and a 10 200 x
19 200 screen is 196 MP. At 500 MP one RGBA copy is already 2 GB, which is
about what a mill PC can hold. Change it per PC with LOOMLAB_MAX_IMAGE_PIXELS
(the older MAX_IMAGE_PIXELS is still read). textile_project/textile/io_utils.py
and colorfill/colorfill.py read the same setting the same way.
"""
from __future__ import annotations

import os
import re
from io import BytesIO

from PIL import Image

DEFAULT_MAX_IMAGE_PIXELS = 500_000_000


def limit_from_env() -> int:
    """LOOMLAB_MAX_IMAGE_PIXELS, else MAX_IMAGE_PIXELS, else the default; a
    value that is not a whole number above 0 is ignored (never 'no limit')."""
    for key in ('LOOMLAB_MAX_IMAGE_PIXELS', 'MAX_IMAGE_PIXELS'):
        raw = os.environ.get(key, '').strip().replace('_', '')
        if raw:
            try:
                value = int(raw)
            except ValueError:
                value = 0
            if value > 0:
                return value
            print(f'{key}={os.environ[key]!r} is not a pixel count above 0; '
                  f'using {DEFAULT_MAX_IMAGE_PIXELS:,} instead.')
    return DEFAULT_MAX_IMAGE_PIXELS


LIMIT = limit_from_env()


class TooManyPixels(ValueError):
    """An image larger than LIMIT: the message is the operator's."""


def _message(pixels: int, limit: int, size: str = '') -> str:
    return (f'This image is {size + " px, " if size else ""}{pixels / 1e6:.0f} megapixels: more than LoomLab '
            f'opens ({limit / 1e6:.0f} megapixels, e.g. about 2 m x 1.5 m at 300 DPI). Save it at a lower '
            f'resolution and import it again (or raise LOOMLAB_MAX_IMAGE_PIXELS on this PC).')


def check(size, limit: int | None = None) -> None:
    """Raise TooManyPixels when (width, height) is over the limit."""
    limit = limit or Image.MAX_IMAGE_PIXELS or LIMIT
    w, h = int(size[0]), int(size[1])
    if w * h > limit:
        raise TooManyPixels(_message(w * h, limit, f'{w} x {h}'))


_BOMB = re.compile(r'\((\d+) pixels\)')


def open_checked(raw: bytes) -> Image.Image:
    """Image.open on uploaded bytes, its size checked from the header first;
    decoded only when it fits. Other read errors are Pillow's own."""
    limit = Image.MAX_IMAGE_PIXELS or LIMIT
    try:
        img = Image.open(BytesIO(raw))
    except Image.DecompressionBombError as e:     # over twice the limit: Pillow's own refusal
        m = _BOMB.search(str(e))
        raise TooManyPixels(_message(int(m.group(1)) if m else 2 * limit, limit)) from None
    check(img.size, limit)                         # between 1x and 2x Pillow would only warn
    img.load()
    return img
