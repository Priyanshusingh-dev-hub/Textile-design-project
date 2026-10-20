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

import numpy as np
from PIL import Image
from psd_tools import PSDImage
from psd_tools.constants import AlphaChannelMode, BlendMode, Compression, Resource
from psd_tools.psd.image_resources import (
    AlphaChannel,
    AlphaNamesUnicode,
    DisplayInfo,
    ImageResource,
    ResoulutionInfo,
)


def layer_name(member):
    """channel_03_rust_motif_A83728.png -> '03 rust motif A83728' (no '#', no extension); a mill's ink name
    (channel_01_Rani-Pink-12_motif_D96A8E.png) -> '01 Rani Pink 12 motif D96A8E'. ASCII only, so psd-tools can
    write it (it writes layer names as MacRoman)."""
    stem = os.path.splitext(os.path.basename(member))[0]
    stem = re.sub(r'^channel_', '', stem)
    return stem.replace('_', ' ').replace('-', ' ')


def write_psd_plates(channels_zip, path, dpi=300, guides=()):
    with zipfile.ZipFile(channels_zip) as z:
        members = sorted(n for n in z.namelist() if n.lower().endswith('.png'))
        if not members:
            raise ValueError('channels zip me koi PNG nahi')
        first = Image.open(io.BytesIO(z.read(members[0])))
        size = first.size
        psd = PSDImage.new('RGB', size, color=(255, 255, 255), depth=8)
        merged = Image.new('RGB', size, (255, 255, 255))           # the plates on white: the file's preview
        for m in members:                                           # plate 1 at the bottom: press order, bottom to top
            im = Image.open(io.BytesIO(z.read(m))).convert('RGBA')
            psd.create_pixel_layer(im, name=layer_name(m), top=0, left=0, compression=Compression.ZIP)
            merged.paste(im, (0, 0), im)
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
    # the preview is set here, not by psd.save(): that composites every layer itself (18 of a run's 150 s), while
    # the plates (one ink per pixel, alpha 0 or 255) pasted on white are already it, the same bytes
    psd._record.image_data.set_data([c.tobytes() for c in merged.split()], psd._record.header)
    with open(path, 'wb') as fh:
        psd._record.write(fh)
    return path

def channel_display_name(member: str, rgb=None) -> str:
    """Human channel name: ink token + hex, e.g. 'black 010203' or 'INK 01 F6E9D7'."""
    hx = None
    m = re.search(r"_([0-9A-Fa-f]{6})\.png$", os.path.basename(member))
    if m:
        hx = m.group(1).upper()
    elif rgb is not None:
        hx = "%02X%02X%02X" % tuple(int(x) for x in rgb)
    else:
        hx = "000000"
    stem = os.path.splitext(os.path.basename(member))[0]
    stem = re.sub(r"^channel_\d+_", "", stem)
    stem = re.sub(r"_(tone|motif|ground|outline|underbase)_" + hx + r"$", "", stem, flags=re.I)
    stem = re.sub(r"_" + hx + r"$", "", stem, flags=re.I)
    stem = stem.replace("_", " ").replace("-", " ").strip() or "ink"
    return f"{stem} {hx}"


def _is_tone_member(member: str) -> bool:
    return "_tone_" in os.path.basename(member).lower()


def _hex_rgb(member: str):
    m = re.search(r"_([0-9A-Fa-f]{6})\.png$", os.path.basename(member))
    if not m:
        return None
    hx = m.group(1)
    return (int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16))


def _ink_lum(rgb) -> float:
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _tone_rgba(im: Image.Image, member: str):
    arr = np.asarray(im.convert("RGBA"))
    rgb = _hex_rgb(member)
    if rgb is None:
        on = arr[..., 3] > 0
        rgb = tuple(int(x) for x in arr[on][0, :3]) if on.any() else (0, 0, 0)
    tone = arr[..., 3]
    out = np.zeros_like(arr)
    out[..., 0] = rgb[0]
    out[..., 1] = rgb[1]
    out[..., 2] = rgb[2]
    out[..., 3] = tone
    return Image.fromarray(out, mode="RGBA"), rgb, tone


def _plate_mask(im: Image.Image, member: str) -> tuple[tuple[int, int, int], np.ndarray]:
    """Return (ink_rgb, coverage u8) for a channel plate PNG."""
    _, rgb, tone = _tone_rgba(im, member)
    return rgb, tone


def _multiply_preview(size_wh, tone_rgbs_masks):
    w, h = size_wh
    acc = np.ones((h, w, 3), dtype=np.float64)
    for rgb, tone in tone_rgbs_masks:
        t = tone.astype(np.float64)[..., None] / 255.0
        ink = np.array(rgb, dtype=np.float64)
        acc *= (1.0 - t) + t * (ink / 255.0)
    return np.clip(np.rint(acc * 255.0), 0, 255).astype(np.uint8)


def _merged_from_plates(size, plates, merged_rgb, tone_blend: str):
    """Build RGB merged preview from plates or supplied composite."""
    w, h = size
    if merged_rgb is not None:
        if isinstance(merged_rgb, Image.Image):
            merged = merged_rgb.convert("RGB")
            if merged.size != size:
                merged = merged.resize(size, Image.Resampling.BILINEAR)
            return merged
        arr = np.asarray(merged_rgb, dtype=np.uint8)
        if arr.shape[0] != h or arr.shape[1] != w:
            return Image.fromarray(arr).resize(size, Image.Resampling.BILINEAR).convert("RGB")
        return Image.fromarray(arr, mode="RGB")
    if not plates:
        return Image.new("RGB", size, (255, 255, 255))
    # Prefer linear overprint when all plates have tones; else paste solids
    if all(_is_tone_member(m) for m, _, _ in plates) or any(_is_tone_member(m) for m, _, _ in plates):
        from .gradients import overprint_rgb
        inks_a = np.array([list(rgb) for _, rgb, _ in plates], dtype=np.uint8)
        tones_a = np.stack([tone.astype(np.float64) / 255.0 for _, _, tone in plates], axis=-1)
        if tone_blend == "multiply":
            return Image.fromarray(_multiply_preview(size, [(rgb, t) for _, rgb, t in plates]), mode="RGB")
        return Image.fromarray(overprint_rgb(tones_a, inks_a, (255, 255, 255)), mode="RGB")
    merged = Image.new("RGB", size, (255, 255, 255))
    for m, im, _tone in plates:
        merged.paste(im, (0, 0), im)
    return merged


def _spot_alpha_channel(rgb, opacity: int = 100) -> AlphaChannel:
    r, g, b = rgb
    return AlphaChannel(
        color_space=0,  # RGB
        c1=int(r) * 257,
        c2=int(g) * 257,
        c3=int(b) * 257,
        c4=0,
        opacity=int(opacity),
        mode=AlphaChannelMode.SPOT,
    )


def write_psd_channels(channels_zip, path, dpi=300, merged_rgb=None, tone_blend: str = "linear_burn"):
    """Channels-only PSD: merged RGB + spot alpha channels (darkest first). No ink layers."""
    with zipfile.ZipFile(channels_zip) as z:
        members = sorted(n for n in z.namelist() if n.lower().endswith(".png"))
        if not members:
            raise ValueError("channels zip me koi PNG nahi")
        loaded = [(m, Image.open(io.BytesIO(z.read(m))).convert("RGBA")) for m in members]
        size = loaded[0][1].size
        w, h = size
        plates = []
        for m, im in loaded:
            if im.size != size:
                im = im.resize(size, Image.Resampling.NEAREST)
            rgb, tone = _plate_mask(im, m)
            plates.append((m, im, rgb, tone))
        # Darkest ink first
        plates.sort(key=lambda p: _ink_lum(p[2]))
        if merged_rgb is not None:
            if isinstance(merged_rgb, Image.Image):
                merged = merged_rgb.convert("RGB")
                if merged.size != size:
                    merged = merged.resize(size, Image.Resampling.BILINEAR)
            else:
                arr = np.asarray(merged_rgb, dtype=np.uint8)
                if arr.shape[0] != h or arr.shape[1] != w:
                    merged = Image.fromarray(arr).resize(size, Image.Resampling.BILINEAR).convert("RGB")
                else:
                    merged = Image.fromarray(arr, mode="RGB")
        else:
            from .gradients import overprint_rgb
            inks_a = np.array([list(rgb) for _, _, rgb, _ in plates], dtype=np.uint8)
            tones_a = np.stack([t.astype(np.float64) / 255.0 for _, _, _, t in plates], axis=-1)
            if tone_blend == "multiply":
                merged = Image.fromarray(
                    _multiply_preview(size, [(rgb, t) for _, _, rgb, t in plates]), mode="RGB"
                )
            else:
                # solids (binary) + tones both work as coverage in linear overprint
                merged = Image.fromarray(overprint_rgb(tones_a, inks_a, (255, 255, 255)), mode="RGB")
                # If plates were exclusive solids, also paste for safety when tones empty
                if float(tones_a.max()) <= 0:
                    merged = Image.new("RGB", size, (255, 255, 255))
                    for _, im, _, _ in plates:
                        merged.paste(im, (0, 0), im)

        names = [channel_display_name(m, rgb) for m, _, rgb, _ in plates]
        alphas = [_spot_alpha_channel(rgb) for _, _, rgb, _ in plates]

        psd = PSDImage.new("RGB", size, color=(255, 255, 255), depth=8)
        # No layers — channels only
        n_extra = len(plates)
        psd._record.header.channels = 3 + n_extra
        psd.image_resources[Resource.ALPHA_NAMES_UNICODE] = ImageResource(
            key=Resource.ALPHA_NAMES_UNICODE,
            data=AlphaNamesUnicode(names),
        )
        psd.image_resources[Resource.DISPLAY_INFO] = ImageResource(
            key=Resource.DISPLAY_INFO,
            data=DisplayInfo(version=1, alpha_channels=alphas),
        )
        fixed = int(round(dpi)) << 16
        psd.image_resources[Resource.RESOLUTION_INFO] = ImageResource(
            key=Resource.RESOLUTION_INFO,
            data=ResoulutionInfo(fixed, 1, 1, fixed, 1, 1),
        )
        r, g, b = merged.split()
        planes = [r.tobytes(), g.tobytes(), b.tobytes()]
        for _, _, _, tone in plates:
            if tone.shape != (h, w):
                tone = np.asarray(Image.fromarray(tone).resize((w, h), Image.Resampling.BILINEAR))
            planes.append(np.ascontiguousarray(tone, dtype=np.uint8).tobytes())
        psd._record.image_data.compression = Compression.RLE
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        psd._record.image_data.set_data(planes, psd._record.header)
        with open(path, "wb") as fh:
            psd._record.write(fh)
        return path


def write_psd_layers(channels_zip, path, dpi=300, guides=(), merged_rgb=None,
                     include_composite=False, tone_blend: str = "linear_burn"):
    """Legacy: per-ink layers (Paper + LINEAR_BURN tones / NORMAL solids)."""
    with zipfile.ZipFile(channels_zip) as z:
        members = sorted(n for n in z.namelist() if n.lower().endswith(".png"))
        if not members:
            raise ValueError("channels zip me koi PNG nahi")
        loaded = [(m, Image.open(io.BytesIO(z.read(m))).convert("RGBA")) for m in members]
        size = loaded[0][1].size
        w, h = size

        tones = [(m, im) for m, im in loaded if _is_tone_member(m)]
        solids = [(m, im) for m, im in loaded if not _is_tone_member(m)]
        use_mul = bool(tones)

        psd = PSDImage.new("RGB", size, color=(255, 255, 255), depth=8)
        tone_masks = []

        if use_mul:
            psd.create_pixel_layer(
                Image.new("RGB", size, (255, 255, 255)),
                name="00 Paper",
                top=0, left=0,
                compression=Compression.ZIP,
                blend_mode=BlendMode.NORMAL,
            )
            tones_sorted = sorted(
                tones,
                key=lambda mi: _ink_lum(_hex_rgb(mi[0]) or (0, 0, 0)),
            )
            blend = BlendMode.MULTIPLY if tone_blend == "multiply" else BlendMode.LINEAR_BURN
            for m, im in tones_sorted:
                rgba_im, rgb, tone = _tone_rgba(im, m)
                if tone_blend == "multiply":
                    layer_im = rgba_im
                else:
                    t = tone.astype(np.float64)[..., None] / 255.0
                    ink = np.array(rgb, dtype=np.float64)
                    layer = np.clip(np.rint(255.0 * (1.0 - t) + ink * t), 0, 255).astype(np.uint8)
                    layer_im = Image.fromarray(layer, mode="RGB")
                psd.create_pixel_layer(
                    layer_im,
                    name=layer_name(m),
                    top=0, left=0,
                    compression=Compression.ZIP,
                    blend_mode=blend,
                )
                tone_masks.append((rgb, tone))
            solids_sorted = sorted(
                solids,
                key=lambda mi: _ink_lum(_hex_rgb(mi[0]) or (0, 0, 0)),
            )
            for m, im in solids_sorted:
                psd.create_pixel_layer(
                    im, name=layer_name(m), top=0, left=0,
                    compression=Compression.ZIP, blend_mode=BlendMode.NORMAL,
                )
            if merged_rgb is not None:
                if isinstance(merged_rgb, Image.Image):
                    merged = merged_rgb.convert("RGB")
                    if merged.size != size:
                        merged = merged.resize(size, Image.Resampling.BILINEAR)
                else:
                    arr = np.asarray(merged_rgb, dtype=np.uint8)
                    if arr.shape[0] != h or arr.shape[1] != w:
                        merged = Image.fromarray(arr).resize(size, Image.Resampling.BILINEAR)
                    else:
                        merged = Image.fromarray(arr, mode="RGB")
            else:
                if tone_blend == "multiply":
                    merged = Image.fromarray(_multiply_preview(size, tone_masks), mode="RGB")
                else:
                    from .gradients import overprint_rgb
                    inks_a = np.array([list(rgb) for rgb, _ in tone_masks], dtype=np.uint8)
                    tones_a = np.stack([tone.astype(np.float64) / 255.0 for _, tone in tone_masks], axis=-1)
                    merged = Image.fromarray(overprint_rgb(tones_a, inks_a, (255, 255, 255)), mode="RGB")
            if include_composite:
                psd.create_pixel_layer(
                    merged.convert("RGBA"),
                    name="COMPOSITE (flattened)",
                    top=0, left=0,
                    compression=Compression.ZIP,
                    blend_mode=BlendMode.NORMAL,
                )
        else:
            merged = Image.new("RGB", size, (255, 255, 255))
            loaded_sorted = sorted(
                loaded,
                key=lambda mi: _ink_lum(_hex_rgb(mi[0]) or (0, 0, 0)),
            )
            for m, im in loaded_sorted:
                psd.create_pixel_layer(
                    im, name=layer_name(m), top=0, left=0,
                    compression=Compression.ZIP,
                )
                merged.paste(im, (0, 0), im)

    for name, png in guides:
        g = Image.open(png).convert("RGB")
        if g.size != size:
            g = g.resize(size, Image.LANCZOS)
        lay = psd.create_pixel_layer(
            g.convert("RGBA"), name=name, top=0, left=0,
            compression=Compression.ZIP, blend_mode=BlendMode.MULTIPLY,
        )
        lay.visible = False

    fixed = int(round(dpi)) << 16
    psd.image_resources[Resource.RESOLUTION_INFO] = ImageResource(
        key=Resource.RESOLUTION_INFO,
        data=ResoulutionInfo(fixed, 1, 1, fixed, 1, 1),
    )
    psd._record.image_data.compression = Compression.RLE
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    psd._record.image_data.set_data(
        [c.tobytes() for c in merged.split()], psd._record.header
    )
    with open(path, "wb") as fh:
        psd._record.write(fh)
    return path


def write_psd(channels_zip, path, dpi=300, guides=(), merged_rgb=None,
              include_composite=False, tone_blend="linear_burn", use_layers=None):
    """Photoshop file for a channels zip.

    Called the way LoomLab and ``number`` always have (no ``use_layers``), this
    writes one layer per plate. ``use_layers=False`` writes spot alpha channels
    (spray, reconstruct, auto). ``use_layers=True`` writes the tonal layer stack
    (paper, linear-burn tones, optional composite).
    """
    if use_layers is False:
        return write_psd_channels(
            channels_zip, path, dpi=dpi, merged_rgb=merged_rgb, tone_blend=tone_blend,
        )
    if use_layers is True:
        return write_psd_layers(
            channels_zip, path, dpi=dpi, guides=guides, merged_rgb=merged_rgb,
            include_composite=include_composite, tone_blend=tone_blend,
        )
    return write_psd_plates(channels_zip, path, dpi=dpi, guides=guides)
