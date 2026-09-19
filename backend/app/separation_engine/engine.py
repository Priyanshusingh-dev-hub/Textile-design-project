import numpy as np
from PIL import Image, ImageFilter
from ..color_engine.engine import hex_rgb, rgb_lab

# cleanup level -> (source median-blur radius, label mode-filter size).
# Real fabric scans/prints carry texture, ink grain and JPEG noise, so a raw
# nearest-colour assignment speckles: single stray pixels get the wrong ink
# and boundaries turn ragged. Pre-blurring the source removes fine grain
# before assignment, and a mode filter on the label map replaces isolated
# mis-assigned pixels with the dominant nearby colour, giving each screen
# solid regions with clean, well-defined edges.
_CLEANUP_LEVELS = {
    0: (0, 0),   # off — raw nearest-colour, may speckle
    1: (0, 3),
    2: (1, 3),   # default — gentle, keeps detail
    3: (1, 5),
    4: (2, 5),
    5: (2, 7),   # aggressive — very solid, softens fine detail
}

def _assign_labels(image, palette, cleanup=2):
    """Nearest-palette-colour assignment with optional denoising so a
    scanned/printed fabric's texture doesn't produce speckled masks. Returns an
    int label array (one palette index per pixel); transparent pixels get -1 so
    they carry no ink on any plate."""
    blur, mode_size = _CLEANUP_LEVELS.get(cleanup, _CLEANUP_LEVELS[2])
    rgba = np.asarray(image.convert('RGBA'))
    opaque = rgba[:, :, 3] >= 128
    src = Image.fromarray(np.ascontiguousarray(rgba[:, :, :3]))
    if blur:
        src = src.filter(ImageFilter.MedianFilter(size=blur * 2 + 1))
    lab = rgb_lab(np.asarray(src))
    palette_lab = np.array([rgb_lab(hex_rgb(hx)) for hx in palette])
    labels = np.argmin(((lab[:, :, None] - palette_lab[None, None, :]) ** 2).sum(-1), axis=-1)
    if mode_size and len(palette) <= 256:
        smoothed = Image.fromarray(labels.astype(np.uint8)).filter(ImageFilter.ModeFilter(size=mode_size))
        labels = np.asarray(smoothed).astype(int)
    labels[~opaque] = -1
    return labels

def create(image, palette, cleanup=2):
    labels = _assign_labels(image, palette, cleanup); layers=[]
    for index,hx in enumerate(palette):
      mask=(labels==index).astype(np.uint8)*255
      rgba=np.zeros((*mask.shape,4),dtype=np.uint8); rgba[:,:,3]=mask
      display=np.full((*mask.shape,4),255,dtype=np.uint8); display[:,:,:3]=255; display[mask>0,:3]=0
      layers.append((hx, Image.fromarray(rgba), Image.fromarray(display), round(float((mask>0).mean()*100),2)))
    return layers

def composite(image,palette,cleanup=2):
    """Rebuild a combined preview from only the enabled spot-color layers,
    using the same cleaned assignment as create() so the preview matches the
    exported screens. Transparent pixels stay transparent."""
    if not palette: return Image.new('RGBA',image.size,(0,0,0,0))
    labels=_assign_labels(image,palette,cleanup)
    out=np.zeros((*labels.shape,4),dtype=np.uint8)
    colors=np.array([hex_rgb(hx) for hx in palette])
    out[:,:,:3]=colors[np.clip(labels,0,len(palette)-1)]
    out[:,:,3]=np.where(labels>=0,255,0).astype(np.uint8)
    return Image.fromarray(out)

def plate(mask, color_hex):
    """Render one screen as its ink colour composited over a white ground —
    the per-plate colour proof a mill reviews (e.g. "Plate 1 — Red" showing
    only the red shapes on white), built from the layer's alpha mask so
    anti-aliased edges stay smooth."""
    alpha = np.asarray(mask.convert('RGBA'))[:, :, 3:4].astype(np.float64) / 255.0
    ink = np.array(hex_rgb(color_hex), dtype=np.float64)
    rgb = (ink * alpha + 255.0 * (1 - alpha)).round().astype(np.uint8)
    return Image.fromarray(rgb)

def to_print_ready(mask):
    """Convert an ink-alpha mask (one of create()'s layer images) into a flat
    8-bit grayscale screen: black where ink prints, white where it doesn't —
    the standard screen-printing film convention mills expect, matching
    production files like a bureau's exported per-color TIFFs."""
    alpha=np.asarray(mask.convert('RGBA'))[:,:,3]
    return Image.fromarray(255-alpha)

def composite_masks(mask_layers, size):
    """mask_layers: list of (mask_image, color_hex, opacity_percent)."""
    out=Image.new('RGBA',size,(0,0,0,0))
    for mask,color,opacity in mask_layers:
      alpha=np.asarray(mask.convert('RGBA'))[:,:,3].astype(np.float64)
      alpha=(alpha*(max(0.0,min(100.0,opacity))/100.0)).round().astype(np.uint8)
      rgba=np.zeros((*alpha.shape,4),dtype=np.uint8); rgba[:,:,:3]=hex_rgb(color); rgba[:,:,3]=alpha
      out.alpha_composite(Image.fromarray(rgba))
    return out
