"""Multichannel (spot-channel) PSD export -- the production format mills use.

Every ink becomes one named spot channel: black = ink prints, white = no
ink, the same print-ready convention as the exported film screens and the
one psd_import reads back, so a file exported here re-imports as the same
screens. Channel names are stored twice (legacy Pascal and Unicode, so a
name like "2 हरा 90" survives), each channel is tagged as a spot colour
in its ink colour so Photoshop previews it correctly, and the resolution
is recorded so the file opens at the intended DPI. Channels are
RLE-compressed: separations are mostly flat runs, so a file that would be
gigabytes raw is typically a few percent of that.
"""
from io import BytesIO
import numpy as np
from PIL import Image
from psd_tools.constants import AlphaChannelMode, ColorMode, Compression, Resource
from psd_tools.psd import PSD
from psd_tools.psd.header import FileHeader
from psd_tools.psd.image_data import ImageData
from psd_tools.psd.image_resources import (AlphaChannel, AlphaNamesPascal, AlphaNamesUnicode, DisplayInfo,
                                           ImageResource, ImageResources, ResoulutionInfo)

MAX_CHANNELS = 56     # Photoshop's limit for a multichannel document
_MAX_SIDE = 30000     # beyond this Photoshop needs the PSB variant


def multichannel_psd(channels: list[tuple[str, str, Image.Image]], dpi: int = 300) -> bytes:
    """channels: [(name, ink_hex, print_ready_screen)] where each screen is an
    8-bit image with black = ink. All screens must share one size."""
    if not channels:
        raise ValueError('No inks to export.')
    if len(channels) > MAX_CHANNELS:
        raise ValueError(f'A multichannel PSD can hold at most {MAX_CHANNELS} inks.')
    w, h = channels[0][2].size
    if any(img.size != (w, h) for _, _, img in channels):
        raise ValueError('All inks must be the same size to share one PSD.')
    if max(w, h) > _MAX_SIDE:
        raise ValueError(f'PSD files are limited to {_MAX_SIDE}px per side; this design is {w}x{h}px.')

    names = [(name.strip() or f'Ink {i + 1}')[:200] for i, (name, _, _) in enumerate(channels)]
    header = FileHeader(version=1, channels=len(channels), height=h, width=w, depth=8, color_mode=ColorMode.MULTICHANNEL)
    resources = ImageResources.new()

    def put(key, data):
        resources[key] = ImageResource(key=key, data=data)

    # Pascal names are Mac Roman and at most 255 bytes; the Unicode copy is exact
    put(Resource.ALPHA_NAMES_PASCAL, AlphaNamesPascal([n.encode('mac_roman', 'replace')[:255].decode('mac_roman') for n in names]))
    put(Resource.ALPHA_NAMES_UNICODE, AlphaNamesUnicode(names))
    # colour space 0 = RGB with 16-bit components; opacity is the spot
    # "solidity" (0 = Photoshop's default for a new spot channel)
    put(Resource.DISPLAY_INFO, DisplayInfo(version=1, alpha_channels=[
        AlphaChannel(0, *(int(hx[k:k + 2], 16) * 257 for k in (1, 3, 5)), 0, 0, AlphaChannelMode.SPOT)
        for _, hx, _ in channels]))
    fixed = int(dpi) << 16   # 16.16 fixed point, unit 1 = pixels per inch, display unit 1 = inches
    put(Resource.RESOLUTION_INFO, ResoulutionInfo(fixed, 1, 1, fixed, 1, 1))

    data = ImageData(compression=Compression.RLE)
    data.set_data([np.asarray(img.convert('L'), dtype=np.uint8).tobytes() for _, _, img in channels], header)
    out = BytesIO()
    PSD(header=header, image_resources=resources, image_data=data).write(out)
    return out.getvalue()
