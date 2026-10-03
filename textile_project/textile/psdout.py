"""One layered Photoshop file (.psd) with every colour plate as its own layer: the document you would build
by hand in Photoshop on a blank canvas of the design's size, here made in one go.

  write_psd(channels_zip, path, dpi=300, guides=[(name, png_path)])  -> path

Layers, bottom to top: one per colour plate, named `01 beige ground F5E3BB` (the number is the press order,
the plates never overlap: every pixel is in exactly one), transparent outside its own colour; then, hidden,
the guides (the bold sketch and its numbers, blended Multiply so only the lines show) for looking at where
each colour goes. Switching the guides off, the visible layers stacked are the final design pixel for pixel.
Canvas = the plates' own size (3535 px by default), RGB 8 bit, the DPI stored in the file.
"""
from __future__ import annotations

import io
import os
import re
import zipfile

from PIL import Image
from psd_tools import PSDImage
from psd_tools.constants import BlendMode, Compression, Resource
from psd_tools.psd.image_resources import ImageResource, ResoulutionInfo


def layer_name(member):
    """channel_03_rust_motif_A83728.png -> '03 rust motif A83728' (no '#', no extension)."""
    stem = os.path.splitext(os.path.basename(member))[0]
    stem = re.sub(r'^channel_', '', stem)
    return stem.replace('_', ' ')


def write_psd(channels_zip, path, dpi=300, guides=()):
    with zipfile.ZipFile(channels_zip) as z:
        members = sorted(n for n in z.namelist() if n.lower().endswith('.png'))
        if not members:
            raise ValueError('channels zip me koi PNG nahi')
        first = Image.open(io.BytesIO(z.read(members[0])))
        size = first.size
        psd = PSDImage.new('RGB', size, color=(255, 255, 255), depth=8)
        for m in members:                                           # plate 1 at the bottom: press order, bottom to top
            im = Image.open(io.BytesIO(z.read(m))).convert('RGBA')
            psd.create_pixel_layer(im, name=layer_name(m), top=0, left=0, compression=Compression.ZIP)
    for name, png in guides:
        g = Image.open(png).convert('RGB')
        if g.size != size:
            g = g.resize(size, Image.LANCZOS)
        lay = psd.create_pixel_layer(g.convert('RGBA'), name=name, top=0, left=0, compression=Compression.ZIP,
                                     blend_mode=BlendMode.MULTIPLY)
        lay.visible = False                                         # a guide to look at, never part of the design
    fixed = int(round(dpi)) << 16                                   # 16.16 fixed point, pixels per inch
    psd.image_resources[Resource.RESOLUTION_INFO] = ImageResource(
        key=Resource.RESOLUTION_INFO, data=ResoulutionInfo(fixed, 1, 1, fixed, 1, 1))
    psd._record.image_data.compression = Compression.RLE            # the merged preview is flat colour: RLE makes it ~100x smaller than raw
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    psd.save(path)
    return path
