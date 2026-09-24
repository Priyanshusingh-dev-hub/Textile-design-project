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
# Modes PIL stores with more than 8 bits per channel. Converting these to RGB
# *clips* at 255 rather than rescaling, so a 16-bit scan — common from mills
# that scan their own strike-offs — would come through as a blank white sheet
# and separate into one empty plate at "100% accuracy". Rescale them first.
_WIDE_MODES = ('I', 'I;16', 'I;16B', 'I;16L', 'I;16N', 'F')


def to_8bit(image):
    """A high-bit-depth image brought down to 8 bits, keeping its tones.
    Anything already 8-bit is returned untouched.

    A 16-bit channel has a known full scale, so it is simply divided by it —
    the design keeps the exact greys it had. Only 32-bit and float images,
    whose scale nothing records, fall back to stretching the observed range."""
    if image.mode not in _WIDE_MODES:
        return image
    a = np.asarray(image).astype(np.float64)
    if image.mode.startswith('I;16'):
        a = a / 257.0                                   # 65535 -> 255, tones intact
    else:
        lo, hi = float(a.min()), float(a.max())
        a = np.zeros_like(a) if hi <= lo else (a - lo) * (255.0 / (hi - lo))
    return Image.fromarray(a.round().clip(0, 255).astype(np.uint8))


def rgb_and_opaque(image):
    """Split any image into an (H,W,3) uint8 RGB array and an (H,W) boolean
    'opaque' mask. Pixels below ALPHA_CUTOFF are treated as blank — they carry
    no ink, so a design with a transparent background never turns into a black
    plate or wastes an ink slot on nothing."""
    a = np.asarray(to_8bit(image).convert('RGBA'))
    return np.ascontiguousarray(a[:, :, :3]), a[:, :, 3] >= ALPHA_CUTOFF

# Anti-aliasing and a feathered edge both leave part-transparent pixels, so
# counting them tells the two apart badly: dense 1px linework is ~99% partial,
# more than a real 2px feather. What separates them is how *wide* the
# transition is. Measured as partial-alpha area over edge length, ordinary
# anti-aliasing sits near 3px whatever the image size, while a feather runs
# from 12px up, so there is a wide gap either side of this threshold.
SOFT_EDGE_PX = 6.0


def soft_edge_width(image):
    """Average width, in pixels, of the design's part-transparent border.

    A flat spot ink cannot fade out: everything below ALPHA_CUTOFF is dropped
    and the rest prints solid, so a soft edge becomes a hard one. This measures
    how much of the design that affects, so the operator can be told rather
    than finding out at the press."""
    a = np.asarray(image.convert('RGBA'))[:, :, 3]
    partial = int(((a > 0) & (a < 255)).sum())
    if not partial:
        return 0.0
    m = a >= ALPHA_CUTOFF                      # what will actually print
    if not m.any():
        return 0.0
    # the printed edge: a printing pixel with a non-printing 4-neighbour
    nb = np.zeros_like(m)
    nb[1:, :] |= ~m[:-1, :]; nb[:-1, :] |= ~m[1:, :]
    nb[:, 1:] |= ~m[:, :-1]; nb[:, :-1] |= ~m[:, 1:]
    edge = int((m & nb).sum())
    return 0.0 if not edge else round(partial / edge, 2)


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
def _distinct(pixels_rgb):
    """(distinct colours as (n,3) uint8, index of each pixel's colour in them).

    Big images go through a 24-bit lookup table, O(pixels) with no sort; small
    ones use np.unique rather than allocate the 16M-entry table."""
    p = np.ascontiguousarray(pixels_rgb, dtype=np.uint8).reshape(-1, 3)
    key = (p[:, 0].astype(np.int32) << 16) | (p[:, 1].astype(np.int32) << 8) | p[:, 2]
    if len(key) < 2_000_000:
        uniq, inverse = np.unique(key, return_inverse=True)
    else:
        present = np.zeros(1 << 24, dtype=bool)
        present[key] = True
        uniq = np.flatnonzero(present).astype(np.int32)
        lut = np.empty(1 << 24, dtype=np.int32)
        lut[uniq] = np.arange(len(uniq), dtype=np.int32)
        inverse = lut[key]
    colours = np.stack([(uniq >> 16) & 255, (uniq >> 8) & 255, uniq & 255], -1).astype(np.uint8)
    return colours, inverse.reshape(-1)


def nearest_centre(pixels_rgb, centers_lab):
    """Nearest centre (squared LAB distance) for every RGB pixel.

    The answer depends only on a pixel's colour, so it is solved once per
    distinct colour and mapped back: identical labels to converting every
    pixel, at a fraction of the cost. A flat reduced design has a handful of
    colours; even a painterly 13 MP source has far fewer colours than pixels."""
    colours, inverse = _distinct(pixels_rgb)
    return _assign(rgb_lab(colours), centers_lab)[inverse]


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
    labels=nearest_centre(pixels,centers_lab); kk=len(centers_lab)
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
    labels=nearest_centre(pixels, rgb_lab(centers))
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
    return _keep_hairlines(rgb, np.asarray(img))


# A median erases anything thinner than its window, and it cannot tell a brush
# speck from a 1px outline: at Light, hard 1px lines lost 98% of their pixels
# (anti-aliased ones survive; their soft edges carry them). A line has a shape
# a speck doesn't: across it, both neighbours differ from it and resemble each
# other (the same ground either side); along it, it continues. Pixels shaped
# like that get their own colour back after the median. Measured on the floral
# it changes nothing that matters (lone pixels 15.6k -> 15.1k, match 91.9% ->
# 91.9%), while hard 1px lines go from 2% kept to 98%. Only pixels the median
# actually moved are examined: at a 12-inch design that is 5s, not 27s.
_LINE_DE = 20.0        # LAB step between a line and the ground either side
_LINE_RUN = 3          # it continues this many px each way (slanted lines may step)


def _keep_hairlines(orig, smoothed, T=_LINE_DE, run=_LINE_RUN):
    """`smoothed`, with the pixels of genuine thin lines restored from `orig`."""
    h, w, _ = orig.shape
    cand = np.abs(orig.astype(np.int16) - smoothed.astype(np.int16)).sum(-1) > 15   # only what the median moved
    if not cand.any():
        return smoothed
    colours, inverse = _distinct(orig)             # LAB per distinct colour, not per pixel
    lab = rgb_lab(colours).astype(np.float32)[inverse].reshape(h, w, 3)
    q = run + 1
    P = np.pad(lab, ((q, q), (q, q), (0, 0)), mode='edge')
    ys, xs = np.nonzero(cand)
    at = lambda dy, dx: P[ys + q + dy, xs + q + dx]
    dist = lambda a, b: np.sqrt(((a - b) ** 2).sum(-1))
    c = at(0, 0)
    line = np.zeros(len(ys), bool)
    for (ay, ax), (ly, lx) in (((0, 1), (1, 0)), ((1, 0), (0, 1)), ((1, 1), (1, -1)), ((1, -1), (1, 1))):
        a, b = at(ay, ax), at(-ay, -ax)            # across the line
        hit = (dist(c, a) > T) & (dist(c, b) > T) & (dist(a, b) < T * 0.6)
        for k in range(1, run + 1):                # along it, both ways
            for sgn in (1, -1):
                if not hit.any():
                    break
                ok = np.zeros(len(ys), bool)
                for j in (-1, 0, 1):               # a slanted line steps sideways
                    ok |= dist(c, at(sgn * ly * k + j * ay, sgn * lx * k + j * ax)) < T * 0.6
                hit &= ok
        line |= hit
    # a real line's pixels touch each other; noise that happens to look
    # line-like for one pixel stands alone
    mask = np.zeros((h, w), bool); mask[ys[line], xs[line]] = True
    mask = _dense(mask.reshape(-1), h, w, 2).reshape(h, w)
    out = smoothed.copy()
    out[mask] = orig[mask]
    return out
# ---- seamless repeats --------------------------------------------------------
# A repeat tile is printed over and over (rotary screens, step-and-repeat), so
# its left edge meets its own right edge on the cloth. Every neighbourhood step
# (texture median, blur, majority filter) treats the image edge as a wall, which
# put a visible seam into a perfectly seamless tile: 1.0x the interior ink-change
# rate across the seam in, 1.7x out (2.9x at stronger cleanup). So a repeat is
# wrapped around before processing and cropped after: edge pixels see their
# real neighbours from the opposite edge.
REPEAT_JUMP = 1.5      # seam jump / interior jump at or below this = seamless
_WRAP = 32             # px of wrap-around: covers every filter's reach combined


def seamless_axes(image):
    """(left-right, top-bottom): whether the design repeats seamlessly along
    each axis — the colour step across the wrap seam is no bigger than a
    typical step inside. A border print can repeat along one axis only. A plain
    ground at both edges also counts, which is harmless: wrapping it changes
    nothing. Transparent-edged designs never count."""
    rgb, opq = rgb_and_opaque(image)
    h, w, _ = rgb.shape
    if h < 8 or w < 8 or not (opq[:, 0].all() and opq[:, -1].all() and opq[0].all() and opq[-1].all()):
        return (False, False)
    a = rgb.astype(np.int32)
    def ratio(across, inner):
        inner = float(inner)
        return float(across) / inner if inner > 0 else (0.0 if across == 0 else np.inf)
    x = ratio(np.abs(a[:, 0] - a[:, -1]).sum(-1).mean(), np.abs(a[:, 1:] - a[:, :-1]).sum(-1).mean())
    y = ratio(np.abs(a[0] - a[-1]).sum(-1).mean(), np.abs(a[1:] - a[:-1]).sum(-1).mean())
    return (x <= REPEAT_JUMP, y <= REPEAT_JUMP)


def repeat_to_report(image):
    """The seamless axes worth telling the operator about: those whose edges
    carry design, not just plain ground. (Plain edges count as seamless too,
    and are wrapped harmlessly, but "this is a repeat" would only confuse.)"""
    rgb, _ = rgb_and_opaque(image)
    axes = seamless_axes(image)
    busy = lambda edge: float(edge.reshape(-1, 3).astype(float).std(0).max()) > 8.0
    return (axes[0] and busy(np.concatenate([rgb[:, 0], rgb[:, -1]])),
            axes[1] and busy(np.concatenate([rgb[0], rgb[-1]])))


def _wrap_pad(a, axes, pad=_WRAP):
    """`a` extended with wrap-around along the repeating axes."""
    wx, wy = axes
    py, px = (min(pad, a.shape[0]) if wy else 0), (min(pad, a.shape[1]) if wx else 0)
    widths = [(py, py), (px, px)] + [(0, 0)] * (a.ndim - 2)
    return np.pad(a, widths, mode='wrap'), py, px


def quantize_full(image, k, smoothing=0, repeat=None):
    """Single quantisation pass returning BOTH the flat reduced RGBA image and
    its palette, so the palette you see is exactly the colours in the image and
    the work is done once instead of twice. `smoothing` (0-3) flattens source
    texture first so painterly/scanned designs give clean, un-speckled plates.
    `repeat` = (left-right, top-bottom) seamless axes; None detects them."""
    rgb,opq=rgb_and_opaque(image)
    h0, w0 = opq.shape
    axes = seamless_axes(image) if repeat is None else tuple(repeat)
    if any(axes):
        rgb, py, px = _wrap_pad(rgb, axes)
        opq, _, _ = _wrap_pad(opq, axes)
    else:
        py = px = 0
    rgb=_presmooth(rgb, smoothing)
    h,w,_=rgb.shape
    if h*w>_MAX_ANALYSIS_PX:
        labels,centers,counts,total=_quantize_large(rgb,opq,k)
    else:
        labels,centers,counts,total=_quantize(rgb,k,opq)
    if py or px:
        # back to the tile itself; count and rank inks on what is really there
        labels = labels[py:py + h0, px:px + w0]
        counts = np.bincount(labels[labels >= 0], minlength=len(centers))
        keep = [i for i in np.argsort(-counts, kind='stable') if counts[i] > 0]
        remap = np.full(len(centers), -1, dtype=np.int64); remap[keep] = np.arange(len(keep))
        labels = np.where(labels >= 0, remap[np.clip(labels, 0, None)], -1)
        centers, counts, total = centers[keep], counts[keep], int((labels >= 0).sum())
    total=max(total,1)
    palette=[Color(hex=_hex(centers[i]),rgb=centers[i].astype(int).tolist(),pixels=int(counts[i]),coverage=round(float(counts[i]/total*100),2)) for i in range(len(centers))]
    idx=np.clip(labels,0,max(len(centers)-1,0))
    out=np.zeros((*labels.shape,4),dtype=np.uint8)
    out[:,:,:3]=centers[idx] if len(centers) else 0
    out[:,:,3]=np.where(labels>=0,255,0).astype(np.uint8)
    return Image.fromarray(out), palette
def suggest_colors(image, candidates=(4, 6, 8, 10, 12, 14), target=92.0):
    """Recommend a sensible ink count: reduce a small proxy at several counts,
    measure accuracy, and pick the fewest inks that either reach `target`% match
    or stop meaningfully improving (each added ink < ~1% better). Fewer screens
    = cheaper for the mill, so the knee of the curve is the sweet spot. Runs on
    a small proxy so the whole sweep is a second or two."""
    rgb, opq = rgb_and_opaque(image)
    h, w, _ = rgb.shape
    small = Image.fromarray(rgb)
    cap = 120_000
    if h * w > cap:
        sc = (cap / (h * w)) ** 0.5
        small = small.resize((max(4, int(w * sc)), max(4, int(h * sc))), Image.BOX)
    curve, prev = [], None
    suggested = None
    for k in candidates:
        # a fast median-cut palette just to trace the accuracy-vs-count curve;
        # the real reduce (LAB k-means) does at least this well at each count.
        q = np.asarray(small.quantize(colors=k, method=Image.MEDIANCUT).convert('RGB')).reshape(-1, 3)
        pal_hex = [_hex(c) for c in np.unique(q, axis=0)]
        de, acc = reconstruction_accuracy(small, pal_hex)
        n = len(pal_hex)
        curve.append({'colors': n, 'accuracy': acc})
        if suggested is None and (acc >= target or (prev is not None and acc - prev < 1.0)):
            suggested = n
        prev = acc
    if suggested is None:
        suggested = max(curve, key=lambda c: c['accuracy'])['colors']
    return {'suggested': int(suggested), 'curve': curve}
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
    return _accuracy_of(_accuracy_sample(image), palette_hex)


def _accuracy_sample(image):
    """The printed (opaque) pixels an accuracy score is measured on, as LAB:
    every one on a small design, an even ~200k sample on a large one."""
    rgb, opq = rgb_and_opaque(image)
    a = rgb.reshape(-1, 3)[opq.reshape(-1)]
    return rgb_lab(a[::max(1, len(a) // 200000)]) if len(a) else np.zeros((0, 3))


def _accuracy_of(sample_lab, palette_hex):
    """(mean CIEDE2000, 0-100 accuracy) of a palette on a prepared sample."""
    if not palette_hex or len(sample_lab) == 0: return 0.0, 0.0
    pal_lab=rgb_lab(np.array([hex_rgb(h) for h in palette_hex]))
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


# Two inks closer than this (CIEDE2000) are hard to tell apart except side by
# side; about 2 is the smallest difference an eye catches, 5 reads as "the
# same colour" at a glance on cloth.
SIMILAR_DE = 5.0


def similar_inks(image, palette_hex, threshold=SIMILAR_DE, limit=3):
    """The closest pairs of inks, each with what merging it would cost.

    Returns up to `limit` pairs closer than `threshold`, closest first:
    {keep, drop, delta_e, accuracy} — `drop` (the smaller ink) folded into
    `keep`, and the measured match of the palette without it. A screen saved
    for a known, small loss is the operator's call; this makes it an informed one."""
    if len(palette_hex) < 3:
        return []
    labs = np.array([rgb_lab(hex_rgb(h)) for h in palette_hex], dtype=float)
    # one sample, the one the accuracy score uses, so each price below is
    # exactly the match the operator will see after merging
    sample = _accuracy_sample(image)
    counts = (np.bincount(np.argmin(((sample[:, None] - labs[None]) ** 2).sum(-1), 1), minlength=len(labs))
              if len(sample) else np.zeros(len(labs)))
    pairs = []
    for i in range(len(palette_hex)):
        de = delta_e2000(labs[i][None].repeat(len(palette_hex), 0), labs)
        for j in range(i + 1, len(palette_hex)):
            if de[j] < threshold:
                pairs.append((float(de[j]), i, j))
    out = []
    for de, i, j in sorted(pairs)[:limit]:
        keep, drop = (i, j) if counts[i] >= counts[j] else (j, i)
        rest = [h for n, h in enumerate(palette_hex) if n != drop]
        out.append({'keep': keep, 'drop': drop, 'delta_e': round(de, 1),
                    'accuracy': _accuracy_of(sample, rest)[1]})
    return out
