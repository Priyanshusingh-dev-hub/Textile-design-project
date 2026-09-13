import numpy as np
from PIL import Image
from ..models import Color

def _hex(rgb): return '#%02X%02X%02X' % tuple(int(x) for x in rgb)
def hex_rgb(value):
    value=value.lstrip('#'); return np.array([int(value[i:i+2],16) for i in (0,2,4)], dtype=np.uint8)
def rgb_lab(rgb):
    # sRGB -> CIE LAB, adequate for perceptual palette grouping
    x=rgb.astype(float)/255; x=np.where(x<=.04045,x/12.92,((x+.055)/1.055)**2.4)
    xyz=np.dot(x, [[.4124,.3576,.1805],[.2126,.7152,.0722],[.0193,.1192,.9505]]) / [.95047,1.,1.08883]
    xyz=np.where(xyz>.008856, xyz**(1/3), 7.787*xyz+16/116)
    return np.stack([116*xyz[...,1]-16,500*(xyz[...,0]-xyz[...,1]),200*(xyz[...,1]-xyz[...,2])],-1)
def array(image): return np.asarray(image.convert('RGB'))
def _cluster(points, k):
    """Small deterministic LAB k-means; avoids a heavyweight runtime dependency."""
    if len(points) < k: k=len(points)
    centers=points[np.linspace(0,len(points)-1,k,dtype=int)].astype(float)
    for _ in range(14):
      labels=np.argmin(((points[:,None]-centers[None,:])**2).sum(-1),axis=1)
      next_centers=np.array([points[labels==i].mean(0) if np.any(labels==i) else centers[i] for i in range(k)])
      if np.allclose(centers,next_centers,atol=.1): break
      centers=next_centers
    return centers
def analyze(image, k):
    a=array(image); pixels=a.reshape(-1,3); sample=pixels[::max(1,len(pixels)//90000)]
    centers_lab=_cluster(rgb_lab(sample),k); labels=np.argmin(((rgb_lab(pixels)[:,None]-centers_lab[None,:])**2).sum(-1),axis=1); counts=np.bincount(labels,minlength=k); centers=np.array([pixels[labels==i].mean(0) if counts[i] else [0,0,0] for i in range(k)])
    order=np.argsort(counts)[::-1]
    return [Color(hex=_hex(centers[i]),rgb=centers[i].round().astype(int).tolist(),pixels=int(counts[i]),coverage=round(float(counts[i]/len(pixels)*100),2)) for i in order]
def reduce(image,k):
    a=array(image); h,w,_=a.shape; pixels=a.reshape(-1,3); sample=pixels[::max(1,len(pixels)//100000)]
    centers_lab=_cluster(rgb_lab(sample),k); labels=np.argmin(((rgb_lab(pixels)[:,None]-centers_lab[None,:])**2).sum(-1),axis=1); centers=np.array([pixels[labels==i].mean(0) if np.any(labels==i) else [0,0,0] for i in range(k)]).round().astype(np.uint8)
    return Image.fromarray(centers[labels].reshape(h,w,3)).convert('RGBA')
def map_colors(image,mappings,threshold=10):
    a=array(image); lab=rgb_lab(a); result=a.copy()
    for item in mappings:
      if not item.enabled: continue
      d=np.linalg.norm(lab-rgb_lab(hex_rgb(item.source)),axis=-1); result[d<=threshold]=hex_rgb(item.target)
    return Image.fromarray(result).convert('RGBA')
def merge(image,sources,target,threshold):
    a=array(image); lab=rgb_lab(a); result=a.copy(); target_rgb=hex_rgb(target)
    for source in sources:
      d=np.linalg.norm(lab-rgb_lab(hex_rgb(source)),axis=-1); result[d<=threshold]=target_rgb
    return Image.fromarray(result).convert('RGBA')
