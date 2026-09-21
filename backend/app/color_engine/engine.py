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
ALPHA_CUTOFF = 128
# How far (in LAB) a high-gradient pixel must sit from the locally-blurred
# image to count as a genuine thin feature rather than a smooth anti-alias
# blend. Tuned so 1-2px lines survive while soft shape edges stay excluded.
_FEATURE_DELTA = 11.0
# Above this many pixels, the perceptual analysis (clustering, edge and feature
# detection — all O(pixels x clusters)) runs on a downscaled proxy instead of
# the full image. Colours are resolution-independent, so the palette is the
# same; the full-resolution image is then produced by a cheap block-wise
# nearest-ink assignment. Keeps mill-sized files (tens of megapixels) fast and
# memory-bounded instead of taking a minute.
_MAX_ANALYSIS_PX = 2_500_000
def rgb_and_opaque(image):
    """Split any image into an (H,W,3) uint8 RGB array and an (H,W) boolean
    'opaque' mask. Pixels below ALPHA_CUTOFF are treated as blank — they carry
    no ink, so a design with a transparent background never turns into a black
    plate or wastes an ink slot on nothing."""
    a = np.asarray(image.convert('RGBA'))
    return np.ascontiguousarray(a[:, :, :3]), a[:, :, 3] >= ALPHA_CUTOFF
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
def _assign_rgb(pixels_rgb, centers_lab, block=200000):
    """Like _assign but converts each block to LAB on the fly, so the full-image
    LAB array is never materialised — bounds memory on huge files."""
    n=len(pixels_rgb); out=np.empty(n,dtype=np.int32)
    for s in range(0,n,block):
      chunk=rgb_lab(pixels_rgb[s:s+block])
      out[s:s+block]=np.argmin(((chunk[:,None]-centers_lab[None,:])**2).sum(-1),axis=1)
    return out
def _merge_to(centers, counts, target_k, jnd=3.0):
    """Agglomerative merge down to target_k colours, in two phases.

    Phase 1 (perceptual de-duplication): while any two colours are within a
    just-noticeable CIEDE2000 difference (`jnd`), merge the closest such pair —
    regardless of how common they are. Two shades the eye reads as the same
    colour (e.g. two near-identical creams) must collapse into one ink even
    when both cover a lot of the image, so an ink is never wasted on a
    duplicate.

    Phase 2 (importance ranking): once no near-duplicates remain, remove the
    least important colour — the one whose merge into its nearest neighbour
    adds the least quantisation error, cost(i) = counts[i] * deltaE2000(i,
    nearest). A colour that is both rare and close to another goes first, while
    a heavily-used or perceptually-isolated colour survives — the order a
    designer uses when hand-reducing a palette.

    Returns `groups`, target_k lists of the original indices merged into each
    surviving colour."""
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
      closest=int(np.argmin(nnd))
      if nnd[closest]<jnd:                     # phase 1: collapse a perceptual duplicate
        a,b=closest,int(nn[closest])
      else:                                    # phase 2: drop the least important colour
        cost=np.array(cnt)*nnd
        a=int(np.argmin(cost)); b=int(nn[a])
      if cnt[a]>cnt[b]: a,b=b,a                # remove the smaller, keep the larger
      i,j=a,b
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

def _dense(mask_flat, h, w, min_neighbors=2):
    """Keep only the mask pixels that have at least `min_neighbors` of their 8
    neighbours also set. A thin feature line is connected, so its pixels each
    have neighbours along the line and survive; isolated texture/noise specks
    (brush grain, woven-fabric weave) stand alone and are dropped — so they get
    flattened into their region instead of speckling a plate."""
    m = mask_flat.reshape(h, w)
    nb = np.zeros((h, w), dtype=np.uint8)
    mi = m.astype(np.uint8)
    nb[1:, :] += mi[:-1, :]; nb[:-1, :] += mi[1:, :]
    nb[:, 1:] += mi[:, :-1]; nb[:, :-1] += mi[:, 1:]
    nb[1:, 1:] += mi[:-1, :-1]; nb[1:, :-1] += mi[:-1, 1:]
    nb[:-1, 1:] += mi[1:, :-1]; nb[:-1, :-1] += mi[1:, 1:]
    return (m & (nb >= min_neighbors)).reshape(-1)

def _mode_smooth(labels2d, size=3):
    """Majority filter on the label map: snaps the one/two-pixel stragglers left
    along a boundary to whichever real region dominates around them, so each
    shape meets its neighbour on a clean hard edge. Kept at a 3px window: larger
    windows clear more boundary fringe but start eroding genuinely thin real
    motifs (a 1px stem, a tiny bud), which must be preserved — the bulk of the
    fringe is already gone because clustering ignores edge pixels, so this only
    tidies the last stragglers."""
    return np.asarray(Image.fromarray(labels2d.astype(np.uint8)).filter(ImageFilter.ModeFilter(size=size))).astype(np.int64)

def _quantize(a, k, opaque=None):
    """Palette quantisation shared by analyze() and reduce(), so the palette
    you see and the reduced image use the exact same colours. Returns
    (labels[h,w], centres_rgb, counts, total) sorted by coverage — most common
    first, least common last. Transparent pixels (opaque=False) carry no ink:
    they are label -1, excluded from the palette, counts and coverage.

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
    opq=np.ones(len(pixels),dtype=bool) if opaque is None else opaque.reshape(-1).astype(bool)
    n_op=int(opq.sum())
    over=min(max(n_op,1), max(k, min(2*k+6, 48)))
    # An anti-aliased transition band and a genuine thin feature line are both
    # high-gradient "edges", but they differ: a transition pixel's colour is a
    # smooth blend of its neighbours, so it equals the locally-blurred image; a
    # thin line is a spike that the blur washes out, so it sits FAR from the
    # blur. Keeping only smooth transitions out of clustering drops muddy
    # fringe halos WITHOUT erasing fine linework (stems, outlines, veins).
    edge=_edge_mask(pixels_lab,h,w)
    blur_lab=rgb_lab(np.asarray(Image.fromarray(a).filter(ImageFilter.GaussianBlur(2.0))))
    detail=np.sqrt(((pixels_lab-blur_lab.reshape(-1,3))**2).sum(-1))
    # a genuine thin feature is a CONNECTED line; a lone high-detail speck is
    # brush/fabric noise, so require feature pixels to have feature neighbours —
    # keeps linework, lets texture speckle flatten into its region.
    feature=_dense(detail>_FEATURE_DELTA, h, w)   # distinct thin structure, not noise
    interior=~edge                          # flat region body
    keep=opq&(interior|feature)             # everything real: bodies + fine detail
    core=opq&interior                       # pure region colour (no edges at all)
    sol=pixels_lab[keep]
    if len(sol) < max(over*50, n_op//5): sol=pixels_lab[opq] if n_op else pixels_lab
    sample=sol[::max(1,len(sol)//90000)]
    centers_lab=_cluster(sample,over)
    labels=_assign(pixels_lab,centers_lab); kk=len(centers_lab)
    counts=np.bincount(labels[opq],minlength=kk)   # rank by OPAQUE coverage only
    present=[i for i in range(kk) if counts[i]>0]
    remap=np.full(kk,-1,dtype=np.int32)
    for new,old in enumerate(present): remap[old]=new
    labels=remap[labels]
    # Merge importance counts a cluster's real pixels (region body + thin
    # feature), so a transition-band cluster (few real pixels) is merged away
    # first while a small-but-distinct feature colour survives; surviving inks
    # take their colour from the region interior where one exists.
    init_centers=[]; init_counts=[]
    for new in range(len(present)):
      m=labels==new; ms=m&keep; mc=m&core
      csrc=pixels[mc] if mc.any() else (pixels[ms] if ms.any() else pixels[m])
      init_centers.append(csrc.mean(0)); init_counts.append(int(ms.sum()) if ms.any() else int((m&opq).sum()))
    init_centers=np.array(init_centers); init_counts=np.array(init_counts,dtype=float)
    groups=_merge_to(init_centers,init_counts,k) if len(present)>k else [[i] for i in range(len(present))]
    grp_of=np.zeros(len(present),dtype=np.int32)
    for gi,members in enumerate(groups):
      for mem in members: grp_of[mem]=gi
    raw=grp_of[labels]                              # per-pixel ink before smoothing
    sm=_mode_smooth(raw.reshape(h,w)).reshape(-1)
    # The majority filter tidies boundary stragglers but would itself swallow a
    # 1px line, so keep the raw ink on genuine feature pixels — the detail is
    # preserved while flat areas still get cleaned.
    final=np.where(feature, raw, sm); g=len(groups)
    fcounts=np.bincount(final[opq],minlength=g)
    # ink colour from each region's opaque interior, so it is the true shape
    # colour rather than an edge-blended average
    fcenters=[]
    for gi in range(g):
      m=final==gi; ms=m&core; mo=m&keep; ma=m&opq
      src=pixels[ms] if ms.any() else (pixels[mo] if mo.any() else (pixels[ma] if ma.any() else (pixels[m] if m.any() else np.zeros((1,3)))))
      fcenters.append(src.mean(0))
    fcenters=np.array(fcenters).round().astype(np.uint8)
    keep=[gi for gi in range(g) if fcounts[gi]>0]
    order=sorted(keep, key=lambda i:-fcounts[i])
    reorder=np.full(g,-1,dtype=np.int32)
    for new,old in enumerate(order): reorder[old]=new
    final=reorder[final]
    final[~opq]=-1                                  # transparent -> no ink
    return final.reshape(h,w), fcenters[order], fcounts[order], n_op
def _quantize_large(a, opq, k, cap=_MAX_ANALYSIS_PX):
    """Palette from a downscaled proxy, then a full-resolution nearest-ink
    assignment — same colours, a fraction of the work on huge files. The proxy
    keeps the edge/feature awareness; the full image is assigned block-wise so
    memory stays bounded."""
    h,w,_=a.shape
    scale=(cap/(h*w))**0.5
    sw,sh=max(2,int(round(w*scale))),max(2,int(round(h*scale)))
    # Fill transparent pixels with the mean opaque colour before downscaling so
    # the void (RGB 0) doesn't blend into dark halos at every shape edge; area
    # averaging (BOX) then avoids the ringing that sharpen filters add.
    filled=a.copy(); tmask=~opq.reshape(h,w)
    if tmask.any() and (~tmask).any():
        filled[tmask]=a[~tmask].reshape(-1,3).mean(0).round().astype(np.uint8)
    small=np.asarray(Image.fromarray(filled).resize((sw,sh),Image.BOX))
    sopq=np.asarray(Image.fromarray((opq.reshape(h,w).astype(np.uint8)*255)).resize((sw,sh),Image.BOX))>=128
    _,centers,_,_=_quantize(small,k,sopq)           # palette only, from the proxy
    pixels=a.reshape(-1,3).astype(np.uint8); opqf=opq.reshape(-1)
    if len(centers)==0:
        return np.full((h,w),-1,dtype=np.int64), centers, np.zeros(0,int), int(opqf.sum())
    labels=_assign_rgb(pixels, rgb_lab(centers))
    labels=_mode_smooth(labels.reshape(h,w)).reshape(-1)   # clean strays (full-res)
    labels[~opqf]=-1
    valid=labels>=0
    counts=np.bincount(labels[valid],minlength=len(centers))
    order=np.argsort(-counts)                         # rank inks by real coverage
    reorder=np.empty(len(centers),np.int32); reorder[order]=np.arange(len(centers))
    labels=np.where(valid,reorder[np.where(valid,labels,0)],-1)
    return labels.reshape(h,w), centers[order], counts[order], int(opqf.sum())
# Texture cleanup: median passes applied to the source before quantising, to
# flatten brush grain, woven-fabric weave and scan noise so plates come out
# solid instead of speckled. Median is edge-preserving — it only erases detail
# thinner than the window, so level 1 keeps 2px+ lines, level 2 keeps 3px+.
_SMOOTH_PASSES = {0: (), 1: (3,), 2: (5,), 3: (5, 3)}
def _presmooth(rgb, level):
    if not level: return rgb
    img = Image.fromarray(np.ascontiguousarray(rgb))
    for s in _SMOOTH_PASSES.get(level, (3,)):
        img = img.filter(ImageFilter.MedianFilter(s))
    return np.asarray(img)
def quantize_full(image, k, smoothing=0):
    """Single quantisation pass returning BOTH the flat reduced RGBA image and
    its palette, so the palette you see is exactly the colours in the image and
    the work is done once instead of twice. `smoothing` (0-3) flattens source
    texture first so painterly/scanned designs give clean, un-speckled plates."""
    rgb,opq=rgb_and_opaque(image)
    rgb=_presmooth(rgb, smoothing)
    h,w,_=rgb.shape
    if h*w>_MAX_ANALYSIS_PX:
        labels,centers,counts,total=_quantize_large(rgb,opq,k)
    else:
        labels,centers,counts,total=_quantize(rgb,k,opq)
    total=max(total,1)
    palette=[Color(hex=_hex(centers[i]),rgb=centers[i].astype(int).tolist(),pixels=int(counts[i]),coverage=round(float(counts[i]/total*100),2)) for i in range(len(centers))]
    idx=np.clip(labels,0,max(len(centers)-1,0))
    out=np.zeros((*labels.shape,4),dtype=np.uint8)
    out[:,:,:3]=centers[idx] if len(centers) else 0
    out[:,:,3]=np.where(labels>=0,255,0).astype(np.uint8)
    return Image.fromarray(out), palette
def analyze(image, k, smoothing=0):
    return quantize_full(image, k, smoothing)[1]
def reduce(image, k, smoothing=0):
    return quantize_full(image, k, smoothing)[0]
def reconstruction_accuracy(image, palette_hex):
    """How faithfully a palette reproduces the image, measured — not guessed.

    Assigns every pixel to its nearest palette colour and reports the mean
    CIEDE2000 difference from the original (delta_e), plus a 0-100 accuracy
    where 100 = pixel-perfect and it falls off with visible error (a mean
    deltaE of ~25 counts as 0). Sampled to ~200k pixels so the score is
    instant even on mill-sized files. Lets every future tuning change be
    judged objectively: did the number go up?"""
    rgb,opq=rgb_and_opaque(image)
    a=rgb.reshape(-1,3)[opq.reshape(-1)]           # score over printed (opaque) pixels only
    if not palette_hex or len(a)==0: return 0.0, 0.0
    sample=a[::max(1,len(a)//200000)]
    pal=np.array([hex_rgb(h) for h in palette_hex])
    sample_lab=rgb_lab(sample); pal_lab=rgb_lab(pal)
    idx=np.argmin(((sample_lab[:,None]-pal_lab[None,:])**2).sum(-1),axis=1)
    de=delta_e2000(sample_lab, pal_lab[idx])
    mean_de=float(de.mean())
    accuracy=round(max(0.0, min(100.0, 100.0*(1-mean_de/25.0))),1)
    return round(mean_de,2), accuracy
def merge(image,sources,target,threshold):
    """Repaint every pixel perceptually within `threshold` (CIEDE2000) of any
    `source` colour to `target`, preserving transparency. Used for palette
    recolour and merge on the flat reduced image."""
    a=np.asarray(image.convert('RGBA')).copy()
    lab=rgb_lab(a[:,:,:3]); target_rgb=hex_rgb(target); opq=a[:,:,3]>=ALPHA_CUTOFF
    for source in sources:
      d=delta_e2000(lab, rgb_lab(hex_rgb(source)))
      hit=(d<=threshold)&opq
      a[:,:,:3][hit]=target_rgb
    return Image.fromarray(a)
