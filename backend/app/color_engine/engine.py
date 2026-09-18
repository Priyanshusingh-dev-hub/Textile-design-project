import numpy as np
from PIL import Image, ImageFilter
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
def delta_e2000(lab1, lab2):
    """CIEDE2000 colour difference between two LAB colours (or broadcastable
    arrays of them, last axis = L,a,b). This is the modern perceptual standard:
    unlike plain Euclidean LAB (CIE76) it weights lightness, chroma and hue
    separately and corrects the blue-region and neutral-desaturation errors, so
    two shades that *look* equally close get an equal score. Used to decide
    which palette colours are 'the same' when merging — the place where getting
    perceptual distance right actually changes the result."""
    L1,a1,b1=lab1[...,0],lab1[...,1],lab1[...,2]
    L2,a2,b2=lab2[...,0],lab2[...,1],lab2[...,2]
    C1=np.hypot(a1,b1); C2=np.hypot(a2,b2); Cbar=(C1+C2)/2
    Cbar7=Cbar**7; G=0.5*(1-np.sqrt(Cbar7/(Cbar7+25.0**7)))
    a1p=(1+G)*a1; a2p=(1+G)*a2
    C1p=np.hypot(a1p,b1); C2p=np.hypot(a2p,b2)
    h1p=np.degrees(np.arctan2(b1,a1p))%360; h2p=np.degrees(np.arctan2(b2,a2p))%360
    dLp=L2-L1; dCp=C2p-C1p
    dhp=h2p-h1p
    dhp=np.where(dhp>180,dhp-360,dhp); dhp=np.where(dhp<-180,dhp+360,dhp)
    dhp=np.where(C1p*C2p==0,0.0,dhp)
    dHp=2*np.sqrt(C1p*C2p)*np.sin(np.radians(dhp/2))
    Lbarp=(L1+L2)/2; Cbarp=(C1p+C2p)/2
    hsum=h1p+h2p; habsdiff=np.abs(h1p-h2p)
    hbarp=np.where(C1p*C2p==0,hsum,
          np.where(habsdiff<=180,hsum/2,
          np.where(hsum<360,(hsum+360)/2,(hsum-360)/2)))
    T=(1-0.17*np.cos(np.radians(hbarp-30))+0.24*np.cos(np.radians(2*hbarp))
        +0.32*np.cos(np.radians(3*hbarp+6))-0.20*np.cos(np.radians(4*hbarp-63)))
    dTheta=30*np.exp(-((hbarp-275)/25)**2)
    Cbarp7=Cbarp**7; Rc=2*np.sqrt(Cbarp7/(Cbarp7+25.0**7))
    Sl=1+(0.015*(Lbarp-50)**2)/np.sqrt(20+(Lbarp-50)**2)
    Sc=1+0.045*Cbarp; Sh=1+0.015*Cbarp*T
    Rt=-np.sin(np.radians(2*dTheta))*Rc
    return np.sqrt((dLp/Sl)**2+(dCp/Sc)**2+(dHp/Sh)**2+Rt*(dCp/Sc)*(dHp/Sh))
def _kpp_init(points, k, rng):
    """k-means++ seeding: pick the first centre at random, then each next
    centre with probability proportional to its squared distance from the
    nearest centre already chosen. This spreads the initial centres across
    the colour space instead of the old evenly-indexed guess, so k-means
    starts near the real clusters and converges to a more accurate palette
    (fewer runs trapped in a bad local minimum). Seeded RNG keeps it
    deterministic — same image always gives the same palette."""
    n=len(points)
    first=int(rng.randint(n))
    centers=[points[first]]
    d2=((points-points[first])**2).sum(-1)
    for _ in range(1,k):
      total=d2.sum()
      probs=d2/total if total>0 else np.full(n,1.0/n)
      idx=int(rng.choice(n,p=probs))
      centers.append(points[idx])
      d2=np.minimum(d2,((points-points[idx])**2).sum(-1))
    return np.array(centers,dtype=float)
def _cluster(points, k):
    """Deterministic LAB k-means with k-means++ seeding; avoids a heavyweight
    runtime dependency."""
    if len(points) < k: k=len(points)
    rng=np.random.RandomState(42)
    centers=_kpp_init(points,k,rng)
    for _ in range(20):
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
    into its nearest perceptual neighbour adds the least quantisation error,
    cost(i) = counts[i] * deltaE2000(i, nearest_neighbour), where the neighbour
    distance is the CIEDE2000 colour difference (not plain Euclidean LAB). So a
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
      dist=delta_e2000(labs[:,None,:],labs[None,:,:])
      np.fill_diagonal(dist,np.inf)
      nn=np.argmin(dist,axis=1); nnd=dist[np.arange(m),nn]
      cost=np.array(cnt)*nnd
      i=int(np.argmin(cost)); j=int(nn[i])
      w=cnt[i]+cnt[j]
      cen[j]=(arr[i]*cnt[i]+arr[j]*cnt[j])/w if w>0 else cen[j]
      cnt[j]=w; groups[j]=groups[j]+groups[i]
      del cen[i]; del cnt[i]; del groups[i]
    return groups
def _edge_mask(pixels_lab, h, w, thresh=8.0):
    """True where the image has a strong colour transition. An anti-aliased
    source (any AI-render or scan) blends across each shape's edge over a few
    pixels; those in-between pixels are not a real ink but k-means will happily
    spend a palette slot on them, leaving a muddy halo ringing every shape that
    then prints as its own dirty screen. Flagging them lets clustering ignore
    them so the palette holds only the design's true colours."""
    lab = pixels_lab.reshape(h, w, 3)
    gy = np.zeros_like(lab); gx = np.zeros_like(lab)
    gy[1:-1, :] = (lab[2:, :] - lab[:-2, :]) * 0.5
    gx[:, 1:-1] = (lab[:, 2:] - lab[:, :-2]) * 0.5
    mag = np.sqrt((gx ** 2).sum(-1) + (gy ** 2).sum(-1))
    return (mag > thresh).reshape(-1)

def _mode_smooth(labels2d, size=3):
    """Majority filter on the label map: snaps the one/two-pixel stragglers left
    along a boundary to whichever real region dominates around them, so each
    shape meets its neighbour on a clean hard edge. Kept at a 3px window: larger
    windows clear more boundary fringe but start eroding genuinely thin real
    motifs (a 1px stem, a tiny bud), which must be preserved — the bulk of the
    fringe is already gone because clustering ignores edge pixels, so this only
    tidies the last stragglers."""
    return np.asarray(Image.fromarray(labels2d.astype(np.uint8)).filter(ImageFilter.ModeFilter(size=size))).astype(np.int64)

def _quantize(a, k):
    """Palette quantisation shared by analyze() and reduce(), so the palette
    you see and the reduced image use the exact same colours. Returns
    (labels[h,w], centres_rgb, counts, total) sorted by coverage — most common
    first, least common last.

    Two things make the output print-clean rather than a naive posterise:
    - k-means clusters on the shapes' *solid* pixels only (anti-aliased edge
      pixels excluded), so no palette slot is wasted on a transition colour and
      every edge pixel then snaps to a real ink — no muddy halo around shapes.
    - the image is over-segmented then merged back to k by _merge_to()'s
      CIEDE2000 importance ranking, so near-duplicate shades collapse while
      genuinely distinct colours survive, even small ones.
    A final majority filter cleans the last boundary stragglers. Net effect:
    one flat colour per region with hard edges — what a hand separation gives,
    without changing the artwork itself. Asking for more colours than the image
    contains yields fewer real ones rather than duplicate/empty swatches."""
    h,w,_=a.shape; pixels=a.reshape(-1,3).astype(np.uint8)
    pixels_lab=rgb_lab(pixels)
    over=min(len(pixels), max(k, min(2*k+6, 48)))
    # cluster on solid (non-edge) pixels so transition bands don't become inks;
    # fall back to all pixels if the design is almost entirely edges/texture
    edge=_edge_mask(pixels_lab,h,w)
    solid=pixels_lab[~edge]
    if len(solid) < max(over*50, len(pixels)//5): solid=pixels_lab
    sample=solid[::max(1,len(solid)//90000)]
    centers_lab=_cluster(sample,over)
    labels=_assign(pixels_lab,centers_lab); kk=len(centers_lab)
    counts=np.bincount(labels,minlength=kk)
    present=[i for i in range(kk) if counts[i]>0]
    remap=np.full(kk,-1,dtype=np.int32)
    for new,old in enumerate(present): remap[old]=new
    labels=remap[labels]
    # Merge decisions use each cluster's SOLID-pixel count and a solid-only
    # centre, so a cluster that is mostly anti-aliased edge (a transition band)
    # counts as low-importance and is merged away first, and surviving inks
    # take their colour from the shapes' interiors, not the blurred edges.
    solid=~edge
    init_centers=[]; init_counts=[]
    for new in range(len(present)):
      m=labels==new; ms=m&solid
      src=pixels[ms] if ms.any() else pixels[m]
      init_centers.append(src.mean(0)); init_counts.append(int(ms.sum()) if ms.any() else int(m.sum()))
    init_centers=np.array(init_centers); init_counts=np.array(init_counts,dtype=float)
    groups=_merge_to(init_centers,init_counts,k) if len(present)>k else [[i] for i in range(len(present))]
    grp_of=np.zeros(len(present),dtype=np.int32)
    for gi,members in enumerate(groups):
      for mem in members: grp_of[mem]=gi
    final=_mode_smooth(grp_of[labels].reshape(h,w)).reshape(-1); g=len(groups)
    fcounts=np.bincount(final,minlength=g)
    # ink colour from each region's solid interior, so it is the true shape
    # colour rather than an edge-blended average
    fcenters=[]
    for gi in range(g):
      m=final==gi; ms=m&solid
      src=pixels[ms] if ms.any() else (pixels[m] if m.any() else np.zeros((1,3)))
      fcenters.append(src.mean(0))
    fcenters=np.array(fcenters).round().astype(np.uint8)
    keep=[gi for gi in range(g) if fcounts[gi]>0]
    order=sorted(keep, key=lambda i:-fcounts[i])
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
def reconstruction_accuracy(image, palette_hex):
    """How faithfully a palette reproduces the image, measured — not guessed.

    Assigns every pixel to its nearest palette colour and reports the mean
    CIEDE2000 difference from the original (delta_e), plus a 0-100 accuracy
    where 100 = pixel-perfect and it falls off with visible error (a mean
    deltaE of ~25 counts as 0). Sampled to ~200k pixels so the score is
    instant even on mill-sized files. Lets every future tuning change be
    judged objectively: did the number go up?"""
    a=array(image).reshape(-1,3)
    if not palette_hex: return 0.0, 0.0
    sample=a[::max(1,len(a)//200000)]
    pal=np.array([hex_rgb(h) for h in palette_hex])
    sample_lab=rgb_lab(sample); pal_lab=rgb_lab(pal)
    idx=np.argmin(((sample_lab[:,None]-pal_lab[None,:])**2).sum(-1),axis=1)
    de=delta_e2000(sample_lab, pal_lab[idx])
    mean_de=float(de.mean())
    accuracy=round(max(0.0, min(100.0, 100.0*(1-mean_de/25.0))),1)
    return round(mean_de,2), accuracy
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
