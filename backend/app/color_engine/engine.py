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
def _assign(pixels_lab, centers_lab, block=200000):
    """Nearest-centre label for every pixel, computed in blocks so the
    (pixels x centres x 3) distance tensor never materialises all at once —
    keeps memory bounded on real mill-sized files even at 20 colours."""
    n=len(pixels_lab); out=np.empty(n,dtype=np.int32)
    for s in range(0,n,block):
      chunk=pixels_lab[s:s+block]
      out[s:s+block]=np.argmin(((chunk[:,None]-centers_lab[None,:])**2).sum(-1),axis=1)
    return out
def _merge_to(centers, counts, target_k):
    """Importance-ranked agglomerative merge. centers:(n,3) rgb, counts:(n,).

    Repeatedly removes the single least-important colour: the one whose merge
    into its nearest perceptual (LAB) neighbour adds the least quantisation
    error, cost(i) = counts[i] * LAB_distance(i, nearest_neighbour). So a
    colour that is both rare AND close to another colour is dropped first
    (it barely changes the image), while a heavily-used colour or a
    perceptually-isolated one survives to the end — exactly the ordering a
    designer uses when hand-reducing a palette: least important out first,
    most important kept last. Returns `groups`, a list of target_k lists of
    the original indices merged into each surviving colour."""
    cen=[c.astype(float).copy() for c in centers]
    cnt=[float(x) for x in counts]
    groups=[[i] for i in range(len(centers))]
    while len(cen)>target_k:
      arr=np.array(cen)
      labs=rgb_lab(arr.round().clip(0,255).astype(np.uint8))
      m=len(cen)
      dist=np.sqrt(((labs[:,None]-labs[None,:])**2).sum(-1))
      np.fill_diagonal(dist,np.inf)
      nn=np.argmin(dist,axis=1); nnd=dist[np.arange(m),nn]
      cost=np.array(cnt)*nnd
      i=int(np.argmin(cost)); j=int(nn[i])
      w=cnt[i]+cnt[j]
      cen[j]=(arr[i]*cnt[i]+arr[j]*cnt[j])/w if w>0 else cen[j]
      cnt[j]=w; groups[j]=groups[j]+groups[i]
      del cen[i]; del cnt[i]; del groups[i]
    return groups
def _quantize(a, k):
    """Palette quantisation shared by analyze() and reduce(), so the palette
    you see and the reduced image use the exact same colours. Returns
    (labels[h,w], centres_rgb, counts, total) sorted by coverage — most common
    first, least common last.

    Rather than asking k-means for exactly k clusters (which can split one
    dominant region in two and lose a small-but-distinct motif), the image is
    first over-segmented into more clusters than requested, then merged back
    down to k by _merge_to()'s importance ranking. The net effect: near-
    duplicate shades collapse together while genuinely distinct colours — even
    small ones — survive, and the least important colours are the ones removed.
    Asking for more colours than the image contains yields fewer real ones
    rather than padding with duplicate/empty swatches."""
    h,w,_=a.shape; pixels=a.reshape(-1,3).astype(np.uint8)
    pixels_lab=rgb_lab(pixels)
    sample=pixels[::max(1,len(pixels)//90000)]
    over=min(len(sample), max(k, min(2*k+6, 48)))
    centers_lab=_cluster(rgb_lab(sample),over)
    labels=_assign(pixels_lab,centers_lab); kk=len(centers_lab)
    counts=np.bincount(labels,minlength=kk)
    present=[i for i in range(kk) if counts[i]>0]
    remap=np.full(kk,-1,dtype=np.int32)
    for new,old in enumerate(present): remap[old]=new
    labels=remap[labels]
    init_centers=np.array([pixels[labels==new].mean(0) for new in range(len(present))])
    init_counts=np.array([counts[old] for old in present],dtype=float)
    groups=_merge_to(init_centers,init_counts,k) if len(present)>k else [[i] for i in range(len(present))]
    grp_of=np.zeros(len(present),dtype=np.int32)
    for gi,members in enumerate(groups):
      for mem in members: grp_of[mem]=gi
    final=grp_of[labels]; g=len(groups)
    fcounts=np.bincount(final,minlength=g)
    fcenters=np.array([pixels[final==gi].mean(0) for gi in range(g)]).round().astype(np.uint8)
    order=sorted(range(g), key=lambda i:-fcounts[i])
    reorder=np.zeros(g,dtype=np.int32)
    for new,old in enumerate(order): reorder[old]=new
    final=reorder[final].reshape(h,w)
    return final, fcenters[order], fcounts[order], len(pixels)
def analyze(image, k):
    labels,centers,counts,total=_quantize(array(image),k)
    return [Color(hex=_hex(centers[i]),rgb=centers[i].astype(int).tolist(),pixels=int(counts[i]),coverage=round(float(counts[i]/total*100),2)) for i in range(len(centers))]
def reduce(image,k):
    labels,centers,counts,total=_quantize(array(image),k)
    return Image.fromarray(centers[labels]).convert('RGBA')
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
