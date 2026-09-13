import numpy as np
from PIL import Image
from ..color_engine.engine import array, hex_rgb, rgb_lab

def create(image,palette):
    a=array(image); lab=rgb_lab(a); layers=[]
    palette_lab=np.array([rgb_lab(hex_rgb(hx)) for hx in palette])
    labels=np.argmin(((lab[:,:,None]-palette_lab[None,None,:])**2).sum(-1),axis=-1)
    for index,hx in enumerate(palette):
      mask=(labels==index).astype(np.uint8)*255
      rgba=np.zeros((*mask.shape,4),dtype=np.uint8); rgba[:,:,3]=mask
      display=np.full((*mask.shape,4),255,dtype=np.uint8); display[:,:,:3]=255; display[mask>0,:3]=0
      layers.append((hx, Image.fromarray(rgba), Image.fromarray(display), round(float((mask>0).mean()*100),2)))
    return layers

def composite(image,palette):
    """Rebuild a combined preview from only the enabled spot-color layers."""
    a=array(image); lab=rgb_lab(a)
    if not palette: return Image.new('RGBA',image.size,(0,0,0,0))
    palette_lab=np.array([rgb_lab(hex_rgb(hx)) for hx in palette])
    labels=np.argmin(((lab[:,:,None]-palette_lab[None,None,:])**2).sum(-1),axis=-1)
    out=np.zeros((*a.shape[:2],4),dtype=np.uint8)
    colors=np.array([hex_rgb(hx) for hx in palette])
    out[:,:,:3]=colors[labels]; out[:,:,3]=255
    return Image.fromarray(out)

def composite_masks(mask_layers, size):
    """mask_layers: list of (mask_image, color_hex, opacity_percent)."""
    out=Image.new('RGBA',size,(0,0,0,0))
    for mask,color,opacity in mask_layers:
      alpha=np.asarray(mask.convert('RGBA'))[:,:,3].astype(np.float64)
      alpha=(alpha*(max(0.0,min(100.0,opacity))/100.0)).round().astype(np.uint8)
      rgba=np.zeros((*alpha.shape,4),dtype=np.uint8); rgba[:,:,:3]=hex_rgb(color); rgba[:,:,3]=alpha
      out.alpha_composite(Image.fromarray(rgba))
    return out
