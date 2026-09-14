import numpy as np
from PIL import Image, ImageFilter
from ..color_engine.engine import array, hex_rgb, rgb_lab

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
    scanned/printed fabric's texture doesn't produce speckled masks.
    Returns an int label array (one palette index per pixel)."""
    blur, mode_size = _CLEANUP_LEVELS.get(cleanup, _CLEANUP_LEVELS[2])
    src = image.convert('RGB')
    if blur:
        src = src.filter(ImageFilter.MedianFilter(size=blur * 2 + 1))
    lab = rgb_lab(np.asarray(src))
    palette_lab = np.array([rgb_lab(hex_rgb(hx)) for hx in palette])
    labels = np.argmin(((lab[:, :, None] - palette_lab[None, None, :]) ** 2).sum(-1), axis=-1)
    if mode_size and len(palette) <= 256:
        smoothed = Image.fromarray(labels.astype(np.uint8)).filter(ImageFilter.ModeFilter(size=mode_size))
        labels = np.asarray(smoothed).astype(int)
    return labels

def create(image, palette, cleanup=2):
    labels = _assign_labels(image, palette, cleanup); layers=[]
    for index,hx in enumerate(palette):
      mask=(labels==index).astype(np.uint8)*255
      rgba=np.zeros((*mask.shape,4),dtype=np.uint8); rgba[:,:,3]=mask
      display=np.full((*mask.shape,4),255,dtype=np.uint8); display[:,:,:3]=255; display[mask>0,:3]=0
      layers.append((hx, Image.fromarray(rgba), Image.fromarray(display), round(float((mask>0).mean()*100),2)))
    return layers

def soft_create(image,palette):
    """Tonal/gradient separation: instead of assigning each pixel wholly to
    its nearest palette color (create()'s hard argmin), weight every color
    by inverse LAB distance so a gradient between two palette colors comes
    out as a smooth alpha blend across their two ink layers rather than a
    hard edge — the printable equivalent needs halftone_engine.apply() on
    top of this to become dots, but the continuous alpha is the tonal data."""
    a=array(image); lab=rgb_lab(a); layers=[]
    palette_lab=np.array([rgb_lab(hex_rgb(hx)) for hx in palette])
    dist=np.sqrt(((lab[:,:,None]-palette_lab[None,None,:])**2).sum(-1))
    weights=1.0/(dist+1e-6)
    weights=weights/weights.sum(-1,keepdims=True)
    for index,hx in enumerate(palette):
      alpha=np.clip(weights[:,:,index]*255,0,255).round().astype(np.uint8)
      rgba=np.zeros((*alpha.shape,4),dtype=np.uint8); rgba[:,:,3]=alpha
      display=np.full((*alpha.shape,4),255,dtype=np.uint8); display[:,:,:3]=(255-alpha)[:,:,None]
      layers.append((hx, Image.fromarray(rgba), Image.fromarray(display), round(float(alpha.mean()/255*100),2)))
    return layers

def composite(image,palette,cleanup=2):
    """Rebuild a combined preview from only the enabled spot-color layers,
    using the same cleaned assignment as create() so the preview matches the
    exported screens."""
    if not palette: return Image.new('RGBA',image.size,(0,0,0,0))
    labels=_assign_labels(image,palette,cleanup)
    out=np.zeros((*labels.shape,4),dtype=np.uint8)
    colors=np.array([hex_rgb(hx) for hx in palette])
    out[:,:,:3]=colors[labels]; out[:,:,3]=255
    return Image.fromarray(out)

def to_print_ready(mask):
    """Convert an ink-alpha mask (any of create()/soft_create()'s layer
    images, or a halftone preview) into a flat 8-bit grayscale screen: black
    where ink prints, white where it doesn't — the standard screen-printing
    film convention mills expect, matching production files like a bureau's
    exported per-color TIFFs."""
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
