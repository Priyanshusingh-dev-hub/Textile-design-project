"""Reading an uploaded design file: a damaged one is the sender's problem, said plainly.

A half-downloaded, truncated or not-really-an-image file makes Pillow (or
psd-tools) raise while decoding: UnidentifiedImageError, OSError ("image file
is truncated"), SyntaxError ("broken PNG file"), EOFError, struct.error and
the like. Those are answered 422 with DAMAGED (what happened, what to do) and
are not engine faults: they never reach Settings -> Help's error list. A
fault after the file is read (in the colour engine) stays a 500.
Truncated images are never "repaired" (ImageFile.LOAD_TRUNCATED_IMAGES stays off).
"""
from __future__ import annotations

import logging
import struct

from PIL import Image, UnidentifiedImageError

from . import pixels

log = logging.getLogger('loomlab.intake')

# the Telegram bot (inbox_bot.py, standard library only) looks for this phrase
MARK = 'looks damaged or incomplete'
DAMAGED = ('This file ' + MARK + ' (it may not have finished downloading or copying), so LoomLab '
           'cannot read it. Save or export the design again and import the new file; on Telegram, '
           'send it again as a File / Document.')
EMPTY = 'This file is empty (0 bytes): it did not arrive. Save the design again and import the new file.'

# what decoding a broken file raises (TooManyPixels is a ValueError and is caught before these)
UNREADABLE = (UnidentifiedImageError, OSError, SyntaxError, EOFError, struct.error, ValueError,
              IndexError, KeyError, TypeError)


class DamagedFile(ValueError):
    """The upload cannot be read as an image: the message is the sender's."""


def refused(name: str, why: str) -> None:
    """A client input problem, noted in the engine's window, not as a fault."""
    log.warning('Upload refused (sender\'s file, not an engine fault): %s: %s', name or '?', why)


def open_image(raw: bytes) -> Image.Image:
    """An uploaded non-PSD image, size-checked (pixels.TooManyPixels) and fully
    decoded, or DamagedFile when it cannot be read."""
    if not raw:
        raise DamagedFile(EMPTY)
    try:
        return pixels.open_checked(raw)
    except pixels.TooManyPixels:
        raise
    except UNREADABLE as e:
        raise DamagedFile(DAMAGED) from e
